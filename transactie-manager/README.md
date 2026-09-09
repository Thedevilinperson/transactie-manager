# Transactie Manager

Huishoudboekje op basis van bankafschriften. Draait als Home Assistant-add-on of
lokaal op Windows, Linux en macOS. Toegang met een eigen gebruikersnaam en
wachtwoord; de gegevens staan versleuteld in de databank.

**Versie 0.1.0** — zie [CHANGELOG.md](CHANGELOG.md) voor de wijzigingen en
[docs/HANDLEIDING.md](docs/HANDLEIDING.md) voor de volledige handleiding.

## Wat het doet

- Bankafschriften inlezen uit Excel of CSV, met kolomherkenning en een
  controlescherm vooraf. Startprofielen voor Argenta, KBC, Belfius en ING.
- Kredietkaartuittreksels in PDF omzetten naar de echte aankopen, die onder de
  maandafrekening komen te hangen.
- Transacties zelf indelen in categorieën van drie niveaus, met winkel en bij
  vakantie het land van bestemming.
- Overzichtstabel per jaar en per categorie, uitklapbaar en filterbaar, en
  grafieken van de evolutie doorheen de jaren.

## Hoe het indeelt

Vier stappen, in volgorde. Zodra er één lukt, stopt het.

1. **Vaste regels** op de sleutel, de beschrijving, de tegenpartij, het
   rekeningnummer of de mededeling — met bevat-, gelijk- of regex-vergelijking
   en een optionele bedragvork. Zo valt een uitgave bij Total onder tien euro
   bij de boodschappen en erboven bij het tanken.
2. **Fuzzy vergelijking** met eerder bevestigde transacties en met je
   referentielijst. Boven de bovenste drempel gaat het automatisch door,
   daartussen komt het in het nazicht.
3. **Een lokaal AI-model** via Ollama, met optionele webopzoeking. Een voorstel
   moet altijd bevestigd worden.
4. **Met de hand**, waarbij de subcategorieën gefilterd worden op de gekozen
   bovenliggende categorie.

Heb je al een categorieënbestand, lees dat dan in bij *Instellingen ›
Referentielijst*. Daaruit komen zowel de categorieboom als de regels.

## Snel starten

**Windows** — dubbelklik `start_windows.bat`. De eerste keer maakt dat script
een virtuele omgeving aan en installeert het de pakketten.

**Linux of macOS** — `./start_linux.sh`

**Home Assistant** — `python scripts/bouw_addon.py`, kopieer de map die daaruit
komt naar `/addons/transactie_manager/`, vernieuw de repositories in de
add-on-winkel en installeer de add-on. Zie
[homeassistant-addon/README.md](homeassistant-addon/README.md).

Je hebt Python 3.11 of nieuwer nodig. Bij de eerste start maak je een beheerder
aan.

## Beveiliging

Uit je wachtwoord wordt met scrypt een sleutel afgeleid die een willekeurige
datasleutel ontgrendelt. Die versleutelt elk gevoelig veld apart met
AES-256-GCM: rekeningnummers, namen, mededelingen, bedragen, categorienamen,
winkels en landen. Voor zoeken en ontdubbelen bestaat er een blinde index op
basis van HMAC-SHA256.

De datasleutel bestaat alleen in het geheugen van het draaiende proces. Na een
herstart moet je opnieuw aanmelden.

> Er is geen herstelprocedure voor een vergeten wachtwoord. Dat is de bedoeling:
> kon de toepassing je wachtwoord herstellen, dan kon iemand anders dat ook.

## Mappen

```
transactie-manager/
├── app/                    de toepassing zelf
│   ├── categorizer/        de indelingsmotor en het AI-model
│   ├── importers/          Excel, CSV, referentielijst en PDF
│   ├── routes/             de webschermen
│   ├── static/             stijlblad en schermlogica
│   └── templates/          de opmaak van de schermen
├── docs/HANDLEIDING.md     de volledige handleiding
├── homeassistant-addon/    Dockerfile, config en startscript
├── scripts/bouw_addon.py   zet de add-on-map klaar
├── voorbeelden/            een voorbeeldafschrift om mee te proberen
├── start_windows.bat
├── start_linux.sh
└── start.py
```

## Techniek

Python met Flask en SQLite, geserveerd door waitress. Versleuteling via
`cryptography`, fuzzy vergelijking via `rapidfuzz`, Excel via `openpyxl` en PDF
via `pdfplumber`. De grafieken worden als SVG in de browser getekend, zonder
externe bibliotheken, zodat alles ook zonder internet werkt.
