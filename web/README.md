# Smart Classroom: dashboard

Vite + React PWA za praćenje mikroklimatskih uslova i popunjenosti učionice
uživo. Klijent je onaj „Dashboard" iz dijagrama arhitekture u
[../README.md](../README.md): čita REST API FastAPI backend-a i prikazuje
poslednja merenja, tok dana i otvorene anomalije.

Deo završnog rada na Fakultetu organizacionih nauka, Univerziteta u Beogradu.

## Sadržaj

- [Pokretanje](#pokretanje)
- [Dizajn](#dizajn)
- [Tailwind](#tailwind)
- [Ekrani](#ekrani)
- [Struktura koda](#struktura-koda)
- [Podaci](#podaci)
- [Pragovi](#pragovi)
- [PWA](#pwa)
- [Šta nije urađeno](#šta-nije-urađeno)

## Pokretanje

```bash
npm install
```

Aplikacija **uvek čita pravi backend**; nema simuliranih podataka. Pokrenite
backend, pa:

```bash
npm run dev
```

Kopirajte `.env.example` u `.env.local` ako menjate podrazumevane vrednosti.
Dev server proksira `/api` i `/health` na `VITE_DEV_PROXY_TARGET`
(podrazumevano `http://localhost:8000`), pa nema CORS-a u razvoju. U
produkciji postavite `VITE_API_BASE_URL` na origin backend-a i dodajte taj
origin u `settings.cors_origins`.

| Komanda | Šta radi |
| --- | --- |
| `npm run dev` | Dev server na `:5173` |
| `npm run build` | Type-check (`tsc -b`) pa produkcioni build |
| `npm run preview` | Služi `dist/` lokalno |
| `npm run typecheck` | Samo provera tipova |
| `npm run icons` | Regeneriše PWA ikonice iz vektorskog izvora |
| `npm run sync-fonts` | Prepisuje potrebne `woff2` iz Fontsource paketa |

## Dizajn

Pravac je **hartija i vazduh**: podloga je hladno bela, sa zelenkastim
podtonom svetla u učionici okrenutoj ka severu, a ne topla krem koja se
podrazumevano dobija kad se traži „premijum". Tekst je mastilo.

**Boja je racionisana.** Statusne boje su tamne na hartiji i svetle na
mastilu, pa se čitaju kao trezven signal, a ne kao neon. U listi merenja
**tačno jedan element nosi boju: reč o stanju.** Ikona, naziv, vrednost i
iskrica ostaju u mastilu. Prethodna verzija je isto stanje kodirala pet puta
(ikona, ivica, podloga, tačka i tekst), zbog čega je šest identičnih kartica
delovalo kao šum umesto kao informacija.

**Svih šest metrika koristi istu komponentu.** Nema kartica; redovi su
odvojeni tankom linijom i grupisani blizinom, jer bi ovde uzdignuta površina
saopštavala ništa. Jedina uzdignuta površina je red koji je u alarmu, pa
uzdignuta površina pouzdano znači „reaguj". Nema ni gradijenata ni senki:
jedini ukras na ekranu bio bi ukras, a ovo je merni instrument.

**Karakter nosi iskrica u redu.** Linija menja boju **deonicu po deonicu**,
prema opsegu u kom se nalazi. Statusna reč kaže sadašnjost, linija kaže kako
se do nje došlo: vidi se kako vazduh kroz čas prelazi u jantar i kako se
vraća u zeleno čim se otvore vrata. Učionica koja dotakne 1400 ppm pa padne
na svako zvono je u redu; ona koja tu stoji celo popodne nije, a trenutni
broj im je isti. To je jedini podatak koji trenutno očitavanje ne može da
saopšti.

Tipografija je **Geist** i **Geist Mono**, jedna superfamilija. Aplikacije ne
mešaju tri porodice; brojevi su ovde ceo posao, a Geist je crtan za
interfejse i drži širinu cifara na velikim veličinama.

**Oblik ima jedno pravilo:** površine `18px`, polja `12px`, dugmad i čipovi
puni radijus. Primenjeno svuda.

**Obe teme su pravi dizajn**, ne inverzija. Displej u učionici po danu traži
hartiju; ista soba proverena sa telefona uveče traži mastilo. Podrazumevano
prati sistem, uz prekidač u zaglavlju.

## Tailwind

Stilovi su **Tailwind v4**, bez konfiguracionog fajla: tema je
[`src/styles/global.css`](src/styles/global.css), a `@tailwindcss/vite` je
uključen u `vite.config.ts`. Nema `.module.css` fajlova.

Teme rade tako što se **preklapaju same promenljive**. Tailwind v4 prevodi
`bg-paper` u `background-color: var(--color-paper)`, pa dodela nove vrednosti
toj promenljivoj u media upitu ili pod `[data-theme]` menja svaku utility
klasu odjednom. Zbog toga izbor „sistem / svetla / tamna" i dalje radi u sve
tri varijante, što `dark:` varijanta sama ne bi pokrila.

U `global.css` ostaje samo ono što utility klasa ne može da izrazi:

| Šta | Zašto ne utility |
| --- | --- |
| `--status` po `[data-status]` | vrednost zavisi od atributa pretka |
| `list-rules` | `nth-child` logika za dve kolone na tabletu |
| `skeleton`, `tabular` | višedelne deklaracije, `@utility` |
| `@layer base` | reset, fokus, `::selection`, PWA higijena |
| `--gutter`, `--safe-bottom` | `env()` za notch i home indicator |

SVG poteze (`stroke`) komponente čitaju kao `var(--color-*)` direktno, jer
utility klase ne dopiru do prezentacionih atributa.

## Ekrani

Dva ekrana, u dubinu a ne u tabove: **zgrada je koren, učionica je njen
detalj.** Traka sa tabovima bi značila da su ravnopravni, a nisu, i „trenutna
učionica" ne postoji dok je neko ne izabere.

| Ekran | Šta radi |
| --- | --- |
| **Učionice** (`RoomList`) | Sve učionice onim redom kojim ih API vrati |
| **Učionica** (`RoomDashboard`) | Svih šest merenja u istoj listi, alarmi izdignuti |

Spisak se **ne preuređuje** sam. Svaki red nosi svoju statusnu reč, pa se
učionica kojoj nešto treba vidi bez toga da joj lista skače pod prstom.

Aplikacija se uvek otvara na spisku. Dodir na učionicu ulazi u njen prikaz,
a strelica u zaglavlju vraća nazad. Ulazak gura stavku u istoriju, pa i
sistemski „nazad" izlazi iz učionice umesto iz aplikacije.

Anketiranje prati ekran: `useRooms` radi samo na spisku, `useDashboard` samo
unutar učionice. Napuštanje ekrana gasi njegov poll.

## Struktura koda

```
src/
  api/          klijent i tipovi sa žice
  components/   AppShell, MetricRow, AlertRow, Sparkline, ...
  config/       definicije metrika, opsezi, kapaciteti učionica
  hooks/        useResource (poll), useDashboard, useRooms, useTheme
  lib/          format (sr-Latn), status, storage
  screens/      RoomList (koren), RoomDashboard (učionica)
  styles/       global.css (Tailwind tema) i fonts.css
```

**Kod je na engleskom, interfejs na srpskoj latinici.** Identifikatori,
tipovi, imena fajlova, CSS tokeni i vrednosti atributa (`data-status="watch"`,
`data-theme="dark"`) su engleski. Srpski ostaje samo u onome što korisnik
zaista pročita: nazivi metrika, oznake opsega, saveti i tekst na ekranu, i to
je sve na jednom mestu, u [`src/config/metrics.ts`](src/config/metrics.ts) i u
samim komponentama.

Nema router-a (dva ekrana, stanje u `useState` uz `history.pushState`), nema biblioteke za server
state (šest endpoint-a, nula mutacija) i nema chart biblioteke; linije su
ručno crtan SVG. Ikone su Phosphor, jedna porodica, jedna debljina.
`useResource` radi tačno ono što tabli treba: ponovo dohvata na promenu
ključa, anketira na interval, drži prethodno očitavanje na ekranu tokom
osvežavanja i staje kad je tab u pozadini.

## Podaci

Ekran Sada u jednom `Promise.all` čita tri endpoint-a i drži ih usaglašene:

| Endpoint | Šta daje |
| --- | --- |
| `GET /api/v1/classrooms` | Spisak učionica za izbornik |
| `…/measurements/latest` | Trenutne vrednosti (prosek po uređajima) |
| `…/measurements?from&points` | Kante za Tok dana i iskrice |
| `…/anomalies?only_open=true` | Otvorene anomalije |

Sve iza `get_current_user`, pa postoji minimalna prijava. Token stoji u
`localStorage`, uobičajen kompromis za bearer tokene. Ako deployment pređe
na kolačić-sesiju, menja se samo [`src/api/client.ts`](src/api/client.ts).

Tipovi u [`src/api/types.ts`](src/api/types.ts) odgovaraju jedan-na-jedan
Pydantic modelima backend-a i provereni su prema živom `openapi.json`.

## Pragovi

Opsezi u [`src/config/metrics.ts`](src/config/metrics.ts) su **prikazni**, sa
izvorima u komentaru (EN 16798-1, EN ISO 7730, EN 12464-1, WHO). Oni nisu
pragovi koji pale push notifikaciju. To su `min_threshold` / `max_threshold`
po uređaju u `sensor_configs`.

Zato aplikacija preklapa jedno preko drugog: ako backend ima **otvorenu
anomaliju** za metriku, ona se prebacuje u `alarm`, izdiže se iznad liste i piše „Prag prekoračen", bez
obzira na prikazni opseg. Ekran i telefonska notifikacija tako ne mogu da
protivreče jedno drugom.

## PWA

`vite-plugin-pwa` u `generateSW` režimu, uz `registerType: 'autoUpdate'`.
Ekrani po učionicama stoje uključeni nedeljama i treba da preuzmu novi build
bez pitanja. Merenja se **ne** keširaju; keširana je samo ljuska, fontovi i
spisak učionica (`NetworkFirst`, 24 h).

Fontovi su vendorovani u `src/assets/fonts` skriptom `sync-fonts`, samo
`latin` i `latin-ext` (srpska latinica traži č ć š ž đ). Bez toga bi se u
precache uvukli ćirilični, grčki i vijetnamski rezovi koje aplikacija nikad
ne iscrtava. Ukupno 83 kB fontova.

`theme-color` je definisan dvaput, po jednom za svaku šemu, pa se traka
pregledača slaže sa temom.

## Šta nije urađeno

- **Kapacitet učionice** ne postoji u API-ju, pa broj mesta stoji u
  [`src/config/classrooms.ts`](src/config/classrooms.ts). Učionica koja nije
  navedena prikazuje broj prisutnih kao podatak, bez ocene.
- **Nema live push-a.** Aplikacija anketira na 15 s; WebSocket ili SSE sa
  `mqtt_gateway`-a bi bio sledeći korak.
- **Nema ESLint-a** ni testova komponenti. Postoji samo `tsc -b` u `build`.
- **Ekran „Učionice" šalje po jedan zahtev za svaku učionicu.** To je u redu
  za zgradu sa nekoliko soba i pogrešno za kampus; kolekcijski endpoint
  `/classrooms/latest` bi to sveo na jedan poziv.
