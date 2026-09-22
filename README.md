# Transactie Manager

Huishoudboekje op basis van bankafschriften. Draait als Home Assistant-add-on of
lokaal op Windows, Linux en macOS. Toegang met een eigen gebruikersnaam en
wachtwoord; de gegevens staan versleuteld in de databank.

**Versie 0.22.0** — zie [het wijzigingslogboek](transactie_manager/CHANGELOG.md)
voor de wijzigingen en
[transactie_manager/docs/HANDLEIDING.md](transactie_manager/docs/HANDLEIDING.md) voor de volledige handleiding.

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
Referentielijst*. Daaruit komen zowel de categorieboom als de regels; je kiest
of je je huidige categorieën behoudt of integraal vervangt.

Breng je een historiek mee waarin de indeling al staat, dan wordt die
overgenomen. Daarna kan je bij *Regels uit historiek* in één keer een
referentielijst laten opbouwen uit wat er in de databank zit. Daarbij doen alle
bruikbare velden mee: het rekeningnummer van de tegenpartij, de gestructureerde
mededeling, de combinatie van beschrijving en tegenpartij, en de tegenpartij
alleen — en waar een tegenpartij twee categorieën dekt, wordt gekeken of het
bedrag ze scheidt.

## Snel starten

**Windows** — dubbelklik `start_windows.bat`. De eerste keer maakt dat script
een virtuele omgeving aan en installeert het de pakketten.

**Linux of macOS** — `./start_linux.sh`

**Home Assistant** — voeg de URL van deze repository toe bij *Instellingen ›
Add-ons › Add-on-winkel › Repositories*, of kopieer de map `transactie_manager`
naar `/addons/` op je Home Assistant-systeem. Zie [docs/ADDON.md](docs/ADDON.md).

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

Vergeet je je wachtwoord, dan is er herstel in twee stappen: een code van zes
cijfers naar je e-mailadres, plus de herstelsleutel die je bij de installatie
eenmalig te zien kreeg. Je hebt ze allebei nodig. De herstelsleutel wordt
nergens bewaard en zit niet in je mailbox, dus wie in je e-mail raakt komt niet
bij je gegevens.

> Ben je het wachtwoord én de herstelsleutel kwijt, dan zijn de gegevens niet
> meer te ontsleutelen. Dat is de bedoeling: kon de toepassing ze zonder een van
> beide openen, dan kon iemand anders dat ook.

## Mappen

De indeling is die van een Home Assistant add-on-repository: `repository.yaml`
aan de wortel, en daarnaast één map per add-on. Die map is zelfdragend, want
Home Assistant bouwt met de add-on-map als context en kan er niet buiten kijken.

```
transactie-manager/
├── repository.yaml           hierdoor herkent Home Assistant de repository
├── transactie_manager/       de add-on, en tegelijk de toepassing zelf
│   ├── config.yaml           naam, ingress, instellingen
│   ├── Dockerfile
│   ├── run.sh                startscript binnen de add-on
│   ├── CHANGELOG.md          het wijzigingslogboek, gelezen door Home Assistant
│   ├── DOCS.md               het tabblad Documentatie bij de add-on
│   ├── README.md             de inleiding in de add-on-winkel
│   ├── icon.png, logo.png    de afbeeldingen in de winkel
│   ├── requirements.txt
│   ├── start.py              starten buiten Home Assistant
│   ├── wsgi.py
│   ├── docs/HANDLEIDING.md   de volledige handleiding, ook in de app te lezen
│   └── app/
│       ├── categorizer/      de indelingsmotor en het AI-model
│       ├── importers/        Excel, CSV, referentielijst en PDF
│       ├── routes/           de webschermen
│       ├── static/           stijlblad en schermlogica
│       └── templates/        de opmaak van de schermen
├── CHANGELOG.md              verwijzing naar het logboek in de add-on-map
├── docs/ADDON.md             installeren in Home Assistant
├── voorbeelden/              een voorbeeldafschrift om mee te proberen
├── start_windows.bat
└── start_linux.sh
```

## Techniek

Python met Flask en SQLite, geserveerd door waitress. Versleuteling via
`cryptography`, fuzzy vergelijking via `rapidfuzz`, Excel via `openpyxl` en PDF
via `pdfplumber`. De grafieken worden als SVG in de browser getekend, zonder
externe bibliotheken, zodat alles ook zonder internet werkt.
