# Wijzigingslogboek

Alle noemenswaardige wijzigingen aan dit project staan hier. De opmaak volgt
[Keep a Changelog](https://keepachangelog.com/nl/1.1.0/) en de versienummers
volgen [Semantische versionering](https://semver.org/lang/nl/).

## [0.2.1] — 2026-09-10

### Opgelost
- **De add-on gaf "404: Not Found" in Home Assistant.** De toepassing maakte
  verwijzingen vanaf de wortel van het adres, terwijl ingress haar achter een
  pad als `/api/hassio_ingress/<token>/` zet. De eerste omleiding kwam daardoor
  buiten dat pad terecht en Home Assistant zelf antwoordde met een 404, nog voor
  de toepassing iets te zien kreeg. Er is nu WSGI-tussenlaag die de kop
  `X-Ingress-Path` uitleest en het voorvoegsel in `SCRIPT_NAME` zet, zodat elke
  verwijzing, omleiding, formulieractie en stijlbladverwijzing het pad meeneemt.
- `ProxyFix` toegevoegd, zodat omleidingen achter de proxy van Home Assistant
  het juiste protocol en de juiste hostnaam krijgen.

Rechtstreekse toegang op poort 8099, buiten Home Assistant om, blijft
onveranderd werken.


## [0.2.0] — 2026-09-09

Herstelversie voor het uitrollen in Home Assistant. Aan de toepassing zelf
verandert niets; de indeling van het project wel.

### Gewijzigd
- De mappenstructuur is die van een Home Assistant add-on-repository geworden.
  De toepassing staat nu in `transactie_manager/`, samen met `config.yaml`, de
  `Dockerfile` en `run.sh`.
- `build.yaml` toegevoegd met een basisimage per architectuur. De vorige
  Dockerfile ging voor elke architectuur uit van het amd64-image.
- Het basisimage staat op Python 3.13 met Alpine 3.22. De vorige combinatie
  (Python 3.12 met Alpine 3.19) wordt door Home Assistant niet meer
  onderhouden.
- De Dockerfile installeert nu eerst uit kant-en-klare pakketten en haalt
  alleen bouwgereedschap binnen wanneer dat niet lukt. Op amd64 en aarch64
  scheelt dat een flink stuk bouwtijd.
- `start_windows.bat` en `start_linux.sh` verwijzen naar de nieuwe locatie; de
  virtuele omgeving en de map `data` blijven aan de wortel staan.
- De add-on vraagt geen toegang meer tot `/share` en `/backup`. Ze heeft alleen
  haar eigen `/data` nodig.
- De installatiehandleiding voor Home Assistant staat nu in `docs/ADDON.md`.

### Toegevoegd
- `repository.yaml` aan de wortel, zodat je de repository rechtstreeks aan de
  add-on-winkel kan toevoegen.

### Verwijderd
- `scripts/bouw_addon.py`. Dat script bestond alleen om de bestanden voor het
  bouwen naar één map te kopiëren. Nu de add-on-map zelfdragend is, kan je ze
  gewoon kopiëren.

### Opgelost
- De Dockerfile stond in een aparte map, los van `app/`, `requirements.txt` en
  `wsgi.py`. Home Assistant bouwt met de add-on-map als context en kan er niet
  buiten kijken, waardoor elke `COPY` in de Dockerfile op niets uitkwam en het
  bouwen afbrak.


## [0.1.0] — 2026-09-09

Eerste versie. De toepassing draait als Home Assistant-add-on of lokaal op
Windows, Linux en macOS.

### Toegevoegd

**Toegang en beveiliging**
- Aanmelden met gebruikersnaam en wachtwoord, los van Home Assistant.
- Alle persoonsgegevens in de databank versleuteld met AES-256-GCM. De sleutel
  wordt met scrypt uit het wachtwoord afgeleid en bestaat alleen in het
  geheugen van het draaiende proces.
- Blinde indexen (HMAC-SHA256) zodat zoeken en ontdubbelen werkt zonder de
  waarden zelf leesbaar op te slaan.
- Meerdere gebruikers, elk met een eigen kopie van de datasleutel.
- Rem op herhaalde aanmeldpogingen; logboek van handelingen.

**Transacties**
- Manuele invoer met datum, rekeningnummers, tegenpartij, begunstigde,
  mededelingen, winkel en land van bestemming.
- Bulkinvoer uit Excel en CSV, met kolomherkenning en een controlescherm vooraf.
- Startprofielen voor Argenta, KBC, Belfius en ING. Het Argenta-profiel is
  afgestemd op de elf kolommen van de echte uitvoer van Argenta Bankieren.
- Ontdubbeling op de bankreferentie, met terugval op de inhoud van de rij.
  Overlappende afschriften mogen dus opnieuw ingelezen worden.
- Eerdere invoerbeurten terugdraaien in één handeling.

**Kredietkaart**
- PDF-uittreksels van Mastercard en Visa inlezen en omzetten naar losse
  aankopen. De tekstlaag wordt uitgelezen met `pdfplumber`, met terugval op
  `pypdf`.
- Vier opmaakpatronen die automatisch tegen elkaar afgewogen worden; het
  patroon met de meeste treffers wint, en je kan zelf een ander kiezen.
- Aankopen hangen onder de maandafrekening op het bankafschrift. Die afrekening
  telt daarna niet meer mee in de overzichten, zodat het bedrag maar één keer in
  de cijfers staat.
- Controle of de som van de aankopen overeenkomt met het totaal op het
  uittreksel, en de ruwe tekst ter inzage als er iets niet klopt.

**Automatisch indelen**
- Stap 1: vaste regels op de gecombineerde sleutel, de beschrijving, de
  tegenpartij, het rekeningnummer of de mededeling, met bevat-, gelijk- en
  regex-vergelijking en een optionele bedragvork. Daarmee valt een uitgave bij
  Total onder tien euro bij de boodschappen en erboven bij het tanken.
- Stap 2: fuzzy vergelijking met eerder bevestigde transacties en met de
  referentielijst. Boven de bovenste drempel gaat de indeling automatisch door;
  daartussen komt ze in het nazicht.
- Stap 3: voorstel door een lokaal AI-model via Ollama, met optionele
  webopzoeking over de tegenpartij. Een voorstel moet altijd bevestigd worden.
- Stap 4: manuele toewijzing, waarbij de subcategorieën gefilterd worden op de
  gekozen bovenliggende categorie.
- Tegenpartijen die in de referentielijst onder meer dan één categorie staan,
  worden gemarkeerd en komen altijd in het nazicht in plaats van blind te
  worden toegewezen.
- Bij het bevestigen wordt de keuze desgewenst als vaste regel onthouden.

**Referentielijst**
- Een bestaand categorieënbestand inlezen: de vijf kolommen worden omgezet naar
  de categorieboom van drie niveaus en naar regels.
- De sleutel wordt gesplitst in beschrijving en tegenpartij; welke voorvoegsels
  verrichtingssoorten zijn, wordt uit het bestand zelf afgeleid.
- Verschillen in hoofdlettergebruik worden samengevoegd; de schrijfwijze die het
  vaakst voorkomt, wordt aangehouden.
- Analysescherm vooraf met de boom, de aantallen en de tegenpartijen die naar
  meer dan één categorie verwijzen.

**Instellingen**
- Meerdere rekeningen beheren; transacties uit een bestand met meerdere
  rekeningen worden op rekeningnummer verdeeld.
- Categorieën van drie niveaus toevoegen, hernoemen, verplaatsen, uitzetten en
  verwijderen.
- Regels beheren, met prioriteit en bedragvork.
- Drempels voor de fuzzy vergelijking en de instellingen van het AI-model.

**Overzichten**
- Jaartabel per categorie, uitklapbaar tot het derde niveau, met filters op
  soort, categorie, rekening en periode, en uitvoer naar CSV.
- Grafieken met de evolutie per jaar of per maand, per hoofd- of subcategorie,
  getekend als SVG zonder externe bibliotheken zodat ze ook zonder internet
  werken.
- Startscherm met inkomsten, uitgaven en saldo per jaar.

### Gekend
- De soort van een categorie (inkomst of uitgave) valt niet uit de
  referentielijst af te leiden en staat na het inlezen op "beide". Aan te passen
  bij Instellingen › Categorieën.
- Uittreksels die alleen uit ingescande afbeeldingen bestaan, kunnen niet
  gelezen worden. Er zit bewust geen tekenherkenning in: dat vraagt zware
  pakketten die op een Raspberry Pi nauwelijks te installeren zijn.
