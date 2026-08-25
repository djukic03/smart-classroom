# Smart Classroom — backend

Backend IoT sistema za praćenje mikroklimatskih uslova i popunjenosti učionice.
Uređaj sa senzorima šalje merenja preko MQTT-a, backend ih validira, upisuje kao
vremenske serije, otkriva prekoračenja pragova i obaveštava korisnike push
notifikacijom. Konfiguracija uređaja putuje identičnim načinom, u suprotnom smeru, sa servera na
uređaj.

Deo završnog rada na Fakultetu Organizacionih Nauka, Univerziteta u Beogradu,  
Student Nemanja Đukić 2022/0129

## Sadržaj

- [Arhitektura](#arhitektura)
- [Tok podataka](#tok-podataka)
- [Pokretanje](#pokretanje)
- [Testovi i provere](#testovi-i-provere)
- [Struktura koda](#struktura-koda)
- [API](#api)
- [MQTT](#mqtt)
- [Baza podataka](#baza-podataka)
- [Podešavanja](#podešavanja)

## Arhitektura

```
┌─────────────┐   MQTT/TLS    ┌────────────┐   HTTP hook    ┌─────────────┐
│ IoT uređaj  │──────────────►│ Mosquitto  │───────────────►│             │
│ (RPi+ESP32) │◄──────────────│ (go-auth)  │◄───────────────│   FastAPI   │
└─────────────┘   retained    └────────────┘  auth / acl    │   backend   │
                 konfiguracija                              │             │
                                                            └──────▲────┬─┘
                                                                   │    │
                                                                   │    │
                                                           ┌───────┘    │
                                                           │     ┌──────▼──────┐
        ┌─────────────┐        REST APIs both ways         │     │ TimescaleDB │
        │   PWA app   │◄───────────────────────────────────┘     │ (PostgreSQL)│
        └─────────────┘                                          └─────────────┘
```

Broker vrši autentifikaciju korisnika preko 
`mosquitto-go-auth` koji šalje HTTP zahtev backend-u preko HTTP hook-a (`/api/v1/mqtt/auth`,
`/api/v1/mqtt/acl`). Time su kredencijali uređaja na jednom mestu, u istoj bazi.

## Tok podataka

**Merenja (uređaj → backend)**

1. Uređaj objavljuje(publish) na `classrooms/{classroom_id}/{device_username}`
2. Broker autentifikuje i autorizuje uređaj tako da uređaj sme da piše samo na svoj topic.
3. `mqtt_gateway` validira dostavljeni payload MQTT poruke(opsezi po metrici, odstupanje sata ±5 min,
   bar jedna metrika, nepoznata polja se odbijaju)
4. Merenje se upisuje u hypertable, a u **istoj transakciji** se vrši detekcija anomalija proveravanjem pragova
5. Otvorena anomalija dobija `notified_at = NULL`; zaseban radnik(worker) je pokupi i
   pošalje push svim korisnicima sa registrovanim uređajem

**Konfiguracija (backend → uređaj)**

Baza je izvor istine, a retained MQTT poruka je **projekcija** tog stanja, ne
događaj.

Izmena preko API-ja ide u red(queue), koji gateway prazni i objavljuje `retain=True` 
pri **svakom** povezivanju na broker.

Kako bi se izbegle izgubljene objave, uređaj koji se poveže odmah dobija poslednju konfiguraciju,
što se osigurava proverom usklađenosti polja `version` koje uređaj trenutno poseduje sa onim
koje je uređaj dobio od backend-a.

## Pokretanje

Preduslov za pokretanje je instaliran `docker compose`.

```bash
cp .env.example .env
```

Fajl `.env` popuniti svojim promenljivim okruženja. 

Za korišćenje MQTT-a preko TLS-a potrebno je generisati par sertifikata u `mosquitto/certs/`
(`ca.crt`, `server.crt`, `server.key`).

```bash
docker compose up -d --build
```

Diže četiri servisa:

| Servis | Šta radi |
|---|---|
| `db` | PostgreSQL 16 + TimescaleDB |
| `app` | FastAPI backend |
| `mosquitto` | MQTT broker |
| `rpi-simulator` | simulirani IoT uređaj |

API ruta za proveru da je sve podignuto:

```bash
curl http://localhost:8000/health/ready
```

Interaktivna Swagger API dokumentacija: <http://localhost:8000/docs>

## Testovi i provere

```bash
docker compose exec app uv run pytest
```

**550 testova** — 307 unit testova i 243 integraciona

Provera tipova, lint i migracija:
```bash
docker compose exec app uv run mypy
docker compose exec app uv run ruff check .
docker compose exec app uv run alembic check
```

Sve četiri provere pokreće i CI ([.github/workflows/ci.yml](.github/workflows/ci.yml))
na svaki push i pull request.


## Struktura koda

Slojevita monolitna arhitektura sa loosely coupled servisima.

```
app/
├── api/v1/         # endpoint-i sa zavisnostima
├── services/       # domenska logika, nezavisna od stack-a
├── repositories/   # komunikacija sa bazom podataka
├── models/         # SQLAlchemy tabele
├── schemas/        # Pydantic šeme
├── workers/        # mqtt_gateway, anomaly_notifier
├── core/           # config, database, security, mqtt, publisher, push, notifier
└── utils/
```

Transakciona granica je na jednom mestu — `get_db` u `app/core/database.py`
commit-uje na uspeh i radi rollback na izuzetak. Repozitorijumi zato nikad ne
commit-uju.

## API

40 endpointa, `/api/v1`. Autentifikacija je Bearer token (opaque, u bazi se čuva
samo SHA-256 hash).

| Oblast | Rute | Pristup |
|---|---|---|
| Autentifikacija | `/auth/register`, `/login`, `/logout`, `/me`, `/sessions` | javno / prijavljen |
| Reset lozinke | `/auth/forgot-password`, `/auth/reset-password` | javno |
| Učionice | `/classrooms` CRUD | čitanje: prijavljen, izmene: admin |
| Merenja | `/classrooms/{id}/measurements` + `/latest`, `/raw`, `/summary` | prijavljen |
| Anomalije | `/classrooms/{id}/anomalies` | prijavljen |
| Uređaji | `/devices` CRUD, `/secret` | admin |
| Konfiguracija uređaja | `/devices/{id}/config`, `/config/sensors/{metric}`, `/config/schedules` | admin |
| Korisnici | `/users` CRUD, `/password` | admin |
| Push tokeni | `/me/push-tokens` | prijavljen |
| MQTT hook | `/mqtt/auth`, `/mqtt/acl` | samo broker (allowlist) |


## MQTT

| Topic | Smer | Ko sme |
|---|---|---|
| `classrooms/{classroom_id}/{device}` | uređaj → backend | uređaj piše samo svoj |
| `devices/config/{device}` | backend → uređaj | uređaj samo čita svoj |

Konfiguracija se objavljuje sa `retain=True`. Prazan payload (dužine 0) **briše**
retained poruku — tako se konfiguracija povlači kad se uređaj deaktivira ili
obriše, da je ne bi nasledio novi uređaj sa istim korisničkim imenom.

## Baza podataka

PostgreSQL 16 sa TimescaleDB. Šemu drži isključivo Alembic — `create_all` se ne
poziva u aplikaciji.

- `measurements` je **hypertable** particionisan po `timestamp`
- `measurements_hourly` je **continuous aggregate** koji se osvežava na 30 minuta
- `anomaly_logs` ima parcijalni unique indeks nad `(device_id, metric_type)`
  `WHERE resolved_at IS NULL` — najviše jedna otvorena anomalija po metrici

Deset migracija, od početne šeme do push tokena:

```bash
docker compose exec app uv run alembic history
```

## Podešavanja

Sva podešavanja idu kroz promenljive okruženja (`app/core/config.py`), a spisak
sa podrazumevanim vrednostima je u [.env.example](.env.example).

Ono što se najčešće menja:

| Promenljiva | Značenje |
|---|---|
| `SECRET_KEY` | obavezna, bez podrazumevane vrednosti |
| `DATABASE_URL` | veza ka bazi |
| `MEASUREMENT_AGGREGATE_MIN_RANGE_HOURS` | od kog perioda se čita agregat umesto sirovih podataka |
| `ANOMALY_TRIGGER_SAMPLES` / `ANOMALY_CLEAR_SAMPLES` | koliko uzastopnih uzoraka otvara odnosno zatvara anomaliju |
| `ANOMALY_HYSTERESIS_PERCENT` | koliko vrednost mora da se vrati preko praga da bi se anomalija zatvorila |
| `SCHEDULE_TIMEZONE` | zona u kojoj se tumače rasporedi merenja |
| `MAIL_BACKEND` | `console` za razvoj, `smtp` za produkciju |
| `PUSH_BACKEND` | `console` za razvoj, `expo` za produkciju |

`console` varijante ispisuju poruku u log umesto slanja, pa se reset lozinke i
notifikacije o anomalijama mogu testirati bez ijednog spoljnog naloga.

## Tehnologije

FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic · PostgreSQL + TimescaleDB ·
Mosquitto · aiomqtt · structlog · pytest · uv · Python 3.13
