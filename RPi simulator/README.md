# Klijent uređaja (Raspberry Pi)

MQTT klijent koji objavljuje merenja na backend i prima konfiguraciju od njega.
Napisan je kao pravi klijent uređaja — na Raspberry Pi se prenosi bez izmena;
menja se samo izvor podataka o senzorima.

## Pokretanje

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Uređaj mora prethodno da postoji u sistemu. Administrator ga kreira preko API-ja,
koji **jednom** vrati tajnu:

```bash
POST /api/v1/devices/   {"classroom_id": 1, "username": "rpi-a101"}
PATCH /api/v1/devices/{id}   {"status": "ACTIVE"}
```

Vrednosti `username`, `secret` i `classroom_id` iz odgovora upisuju se u `.env`.
Dok je uređaj `INACTIVE`, broker mu odbija prijavu.

## Podešavanja

| Promenljiva | Podrazumevano | Značenje |
|---|---|---|
| `MQTT_HOST` | `localhost` | adresa brokera |
| `MQTT_PORT` | `8883` | port; 8883 je TLS |
| `MQTT_CA_FILE` | — | putanja do `ca.crt`; prazno isključuje TLS |
| `DEVICE_USERNAME` | — | korisničko ime uređaja |
| `DEVICE_SECRET` | — | tajna dobijena pri kreiranju |
| `CLASSROOM_ID` | — | učionica u kojoj je uređaj |
| `MEASUREMENT_INTERVAL` | `60` | razmak između merenja u sekundama |
| `MQTT_KEEPALIVE_SECONDS` | `60` | MQTT keepalive |
| `MQTT_RECONNECT_SECONDS` | `5` | pauza pre ponovnog povezivanja |
| `BUFFER_SIZE` | `500` | koliko merenja se čuva dok nema veze |

## Teme

Objavljuje na `classrooms/{classroom_id}/{username}`, sluša
`devices/config/{username}`. Broker dozvoljava tačno te dve teme i ništa više,
pa pogrešno podešen `CLASSROOM_ID` znači odbijenu objavu.

Format poruke sa merenjem:

```json
{
  "timestamp": "2026-08-11T13:04:48.379054+00:00",
  "co2": 600.8,
  "temperature": 21.44,
  "humidity": 42.5,
  "illuminance": 900.6,
  "sound": 57.6,
  "occupancy": 14
}
```

Vreme šalje uređaj, u UTC. Sve metrike su opcione, ali bar jedna mora da postoji.
Nepoznato polje backend odbija, pa se šema poruke mora poklapati sa
`app/schemas/measurement.py`.

## Konfiguracija sa servera

```json
{
  "measurement_interval": 60,
  "enabled": true,
  "sensors": {"co2": true, "sound": false}
}
```

Sva polja su opciona — primenjuje se samo ono što je poslato. Interval mora biti
između 5 i 3600 sekundi, inače se ignoriše uz upozorenje u logu. Neispravna
poruka ne ruši uređaj: zadržava se prethodna konfiguracija.

Server treba da objavljuje konfiguraciju kao **retained** poruku. Tako je uređaj
dobija odmah po povezivanju, umesto da radi sa podrazumevanim vrednostima dok ne
stigne sledeća izmena.

## Ponašanje pri prekidu veze

Merenja se prikupljaju nezavisno od veze sa brokerom i skladište u bafer. Kada se
veza vrati, šalju se redom, sa vremenom kada su **stvarno nastala**. Kad se bafer
napuni, najstarije merenje se odbacuje.

## Prelazak na stvarne senzore

`sensors.py` definiše `SensorSource` sa jednom metodom:

```python
def read(self, enabled: dict[str, bool]) -> dict[str, float | int]
```

`SimulatedSensors` je jedna implementacija. Za stvarni hardver napiše se druga —
na primer `HardwareSensors` koja čita BME280 i SCD40 preko I2C, BH1750 i INMP441,
a broj prisutnih dobija od modela za detekciju osoba. U `main.py` se menja jedan
red:

```python
device = Device(settings, HardwareSensors())
```

Ostatak koda ostaje netaknut.

## Napomena o `client_id`

Klijent se brokeru predstavlja svojim korisničkim imenom. Ako se dva procesa
pokrenu sa istim `DEVICE_USERNAME`, broker će prekidati stariju vezu i uređaji će
se međusobno izbacivati u krug. Jedan uređaj — jedan proces.
