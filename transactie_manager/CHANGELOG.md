# Wijzigingslogboek

Alle noemenswaardige wijzigingen aan dit project staan hier. De opmaak volgt
[Keep a Changelog](https://keepachangelog.com/nl/1.1.0/) en de versienummers
volgen [Semantische versionering](https://semver.org/lang/nl/).

## [0.6.0] — 2026-09-16

### Toegevoegd
- **Filters gaan vanzelf.** Elke wijziging past de selectie meteen toe; de knop
  *Toepassen* is weg. In het zoekveld wordt even gewacht tot je uitgetikt bent.
  Zonder JavaScript verschijnt er alsnog een knop.
- **Jaren kies je als aanvinkbare blokjes** in plaats van een bereik tussen twee
  datums. Niets aangevinkt betekent alle jaren.
- **Filter op land en op winkel**, allebei als meerkeuzelijst. Bij de winkels
  staat er een zoekveldje boven, want die lijst wordt lang.
- **De transactielijst filtert nu op de bron van de indeling**: vaste regel,
  gelijkenis, AI-model, uit het bestand, met de hand, of niets gevonden.
  Daarmee zie je in één klik wat de fuzzy vergelijking zelf heeft bevestigd.
- **Kolommen zijn sorteerbaar** door op de hoofding te klikken: datum,
  tegenpartij, mededeling, categorie, bron en bedrag. Op bedrag wordt gesorteerd
  op de grootte, niet op het teken, zodat bij een lijst vol uitgaven de zwaarste
  bovenaan komt.
- **De grafiekbladzijde heeft er een taartdiagram bij**, met een eigen
  filterbalk los van die van de staafgrafiek.
- In de grafieken kan je **winkels en sub- of sub-subcategorieën uitsluiten** via
  een meerkeuzelijst, en **verdelen per land**, per winkel of per categorieniveau.
  Voor vakantie geeft dat de verdeling per land van bestemming.
- Het zoekveld van de transactielijst zoekt nu ook **in de categorienamen**, en
  in de beschrijving, het land en de winkel.

### Gewijzigd
- **De jaartabel toont hele euro's**, zonder decimalen en zonder een bedrag van
  nul te schrijven; daar staat een streepje.
- **De jaarkolommen staan van recent naar oud**, want daar kijk je het vaakst
  naar.
- **De categoriefilter is geen lange lijst meer** maar drie keuzelijsten die
  elkaar opvolgen: hoofdcategorie, subcategorie, sub-subcategorie. Het blok
  staat dichtgeklapt tot je het opent. Land, winkel en uitsluiten werken
  hetzelfde.
- **De horizontale schuifbalk blijft in beeld.** De tabel krijgt een vaste
  hoogte met de schuifbalk aan de onderrand, de hoofding blijft bovenaan staan
  en de categoriekolom blijft links staan tijdens het zijwaarts schuiven.
- In de kolom *Tegenpartij* staat nu de naam van de tegenpartij; winkel en land
  staan eronder als bijschrift in plaats van in de plaats ervan.
- De lijst met beschikbare jaren, landen en winkels wordt in het geheugen
  bewaard en pas opnieuw opgebouwd wanneer er transacties veranderen. Op twintig
  duizend transacties blijft elk scherm daardoor onder de seconde.

### Opgelost
- **Betalingen met een debetkaart werden aangezien voor een kaartafrekening.**
  Een regel als "Mastercard Debit betaling — STRADVARIUS GENT" is een gewone
  uitgave die al op je afschrift staat; die mocht nooit als uit te splitsen
  afrekening voorgesteld worden. Herkenning gebeurt nu op de afrekeningsregel
  zelf, met debetkaart, Maestro, Bancontact en V Pay uitdrukkelijk uitgesloten.


## [0.5.0] — 2026-09-15

### Gewijzigd
- **Het bewerkscherm toont nu alles wat aan een transactie vasthangt.** Voordien
  bleven de beschrijving, de referentie van de bank, de begunstigde, de rekening
  waarop ze staat en de valutadatum onzichtbaar, ook al stonden ze wel degelijk
  in de databank. Bij een transactie waar de tegenpartij en de mededeling leeg
  waren, leek het scherm daardoor haast leeg terwijl er genoeg stond om te zien
  waarover het ging.
- Bovenaan staat een blok *Zoals de bank ze aanleverde* met rekening, boekdatum,
  valutadatum, bedrag, richting, referentie en waar de transactie vandaan komt,
  inclusief de naam van het ingelezen bestand en wanneer dat gebeurde.
- De rij zoals ze letterlijk in het bestand stond is uitklapbaar op te vragen,
  met alle kolommen — ook die waarvoor de toepassing geen eigen veld heeft.
- Bij een aankoop van een kredietkaartuittreksel staat er een verwijzing naar de
  afrekening waaronder ze hangt; bij een afrekening een lijst van de
  uitgesplitste aankopen, elk aanklikbaar.
- De zekerheid in procenten staat nu bij de toelichting wanneer de indeling van
  de fuzzy vergelijking of van het AI-model komt.

### Toegevoegd
- De **beschrijving**, de **rekening van de tegenpartij** en de **begunstigde**
  zijn nu aan te passen. Dat waren net de velden waarop de motor werkt, en de
  eerste twee waren voordien niet of alleen als leesveld zichtbaar.
- De gecombineerde sleutel en de index op het rekeningnummer worden na zo'n
  wijziging opnieuw berekend, zodat de regels erop blijven werken.


## [0.4.2] — 2026-09-15

### Opgelost
- **Na het aanmelden opende Home Assistant zichzelf binnen de add-on**, met een
  tweede zijbalk als gevolg. Was je niet aangemeld toen je een scherm opende,
  dan onthield de toepassing dat scherm als pad zonder het ingress-voorvoegsel.
  Na het aanmelden werd daar rechtstreeks naartoe gestuurd, en binnen het venster
  van de add-on wijst zo'n pad naar Home Assistant zelf in plaats van naar de
  add-on. Meegegeven paden worden nu altijd aangevuld met het voorvoegsel.
- Dezelfde fout zat in de knoppen **Opslaan**, **Annuleren**, **Verwijderen** en
  **Klopt** bij het bewerken van een transactie: die gebruikten het onthouden
  adres van de vorige bladzijde en kwamen zo eveneens buiten de add-on terecht.

### Beveiliging
- Een meegegeven terugkeeradres kan niet langer naar een andere site wijzen. Een
  waarde die begint met `//` of met een volledig webadres wordt genegeerd; er
  wordt dan teruggevallen op het startscherm.


## [0.4.1] — 2026-09-15

### Opgelost
- **Home Assistant toonde het wijzigingslogboek niet.** De Supervisor leest
  `CHANGELOG.md` uit de add-on-map, naast `config.yaml`, en niet aan de wortel
  van de repository. Het bestand staat nu op de juiste plaats; aan de wortel
  blijft een verwijzing staan zodat er maar één versie onderhouden wordt.

### Toegevoegd
- `DOCS.md` in de add-on-map. Dat vult het tabblad **Documentatie** bij de
  add-on: installeren, eerste stappen, hoe het indelen werkt, en wat te doen bij
  problemen.
- `README.md` in de add-on-map. Dat is de korte inleiding in de add-on-winkel.
- `icon.png` en `logo.png`, zodat de add-on niet meer als naamloos blokje in de
  winkel staat.


## [0.4.0] — 2026-09-14

### Toegevoegd
- **Historiek met de indeling er al in.** De invoer neemt nu ook de kolommen
  Hoofdcategorie, Subcategorie, Sub-subcategorie, Winkel en Land over.
  Categorieën die nog niet bestaan worden aangemaakt; die transacties komen
  meteen als bevestigd binnen en gaan niet door het nazicht.
- **Voorbeeldbestanden om te downloaden**, één voor de historiek en één voor de
  referentielijst. Elk met een tweede werkblad dat per kolom uitlegt waarvoor
  ze dient en of ze verplicht is.
- Het invoerscherm toont nu een tabel met alle kolommen, of ze verplicht zijn
  en waarvoor ze gebruikt worden.
- **Regels uit historiek**: een referentielijst afleiden uit de transacties die
  al ingedeeld zijn. Vier soorten aanwijzingen doen mee, elk met een eigen
  gewicht: het rekeningnummer van de tegenpartij, de gestructureerde mededeling,
  de combinatie van beschrijving en tegenpartij, en de tegenpartij alleen.
- Botst een tegenpartij tussen twee categorieën, dan wordt gekeken of het bedrag
  de gevallen scheidt. Overlappen de reeksen niet, dan komt er een grens tussen
  en worden het twee regels met een bedragvork. Dat is het geval van het
  tankstation: kleine bedragen zijn een broodje, grote bedragen zijn brandstof.
  Lukt dat niet, dan komt er een regel die om bevestiging blijft vragen.
- Analysescherm vooraf met de aantallen per aanwijzing en de gevonden
  bedragvorken; er wordt pas weggeschreven als je bevestigt.

### Gewijzigd
- De keuze bij het inlezen van een referentielijst is nu een uitdrukkelijke
  keuze tussen **behouden en aanvullen** en **integraal vervangen**, in plaats
  van een aankruisvakje. Behouden is voortaan de standaard.

### Opgelost
- **De kolom Beschrijving werd bij de invoer niet aan de motor doorgegeven.**
  Daardoor kwamen de regels op de gecombineerde sleutel nooit aan bod en deden
  alleen de bredere tegenpartijregels hun werk. Op de Argenta-uitvoer stijgt het
  aantal treffers via een regel daardoor van 147 naar 154.
- **De volgorde waarin regels beoordeeld werden negeerde de prioriteit.** Een
  exacte treffer op de tegenpartij won altijd van een nauwkeurigere regel met
  een bedragvork, waardoor een uitgave van vijf euro bij het tankstation toch
  bij brandstof belandde. Alle passende regels worden nu samen beoordeeld en de
  laagste prioriteit wint.
- Regels met een bedragvork werken nu ook op het rekeningnummer van de
  tegenpartij; dat veld zat niet in de snelle index.


## [0.3.1] — 2026-09-14

### Opgelost
- **De knop “Testbericht sturen” sloeg het e-mailadres op in plaats van een
  bericht te versturen.** In dat formulier stond een verborgen veld `actie` met
  de waarde `adres`, terwijl de testknop diezelfde naam droeg met de waarde
  `test`. De browser stuurt dan allebei de waarden mee en de eerste wint, dus
  kwam elke klik uit bij het opslaan. Het verborgen veld is weg; beide knoppen
  dragen nu zelf hun actie.


## [0.3.0] — 2026-09-10

### Toegevoegd
- **Wachtwoordherstel met een herstelsleutel en een code per e-mail.** Bij de
  installatie krijg je eenmalig een herstelsleutel van 32 tekens te zien. Er
  komt een tweede ingepakte kopie van de datasleutel mee, ontgrendeld met die
  herstelsleutel. Vergeet je je wachtwoord, dan stuurt de toepassing een code
  van zes cijfers naar je e-mailadres; met die code én de herstelsleutel stel
  je een nieuw wachtwoord in.
- De herstelsleutel wordt nergens leesbaar bewaard, ook niet versleuteld. Een
  code uit je mailbox alleen volstaat dus niet: wie in je e-mail raakt, komt
  niet bij je gegevens.
- Bij het overtypen van de herstelsleutel doen hoofdletters, spaties en
  koppeltekens er niet toe. De letters I, L, O en U komen niet in het alfabet
  voor en worden gelezen als 1, 1, 0 en V.
- Nieuw scherm *Instellingen › Herstel en e-mail*: het adres instellen, een
  testbericht sturen, de mailserver invullen en een nieuwe herstelsleutel
  maken.
- Verzenden via SMTP met SSL, STARTTLS of onbeveiligd. De standaardwaarden
  staan op Yahoo Mail.
- Link *Wachtwoord vergeten?* op het aanmeldscherm.

### Beveiliging
- Codes zijn een kwartier geldig, eenmalig, en na vijf foute pogingen vervallen
  ze. Een nieuwe aanvraag laat oudere codes vervallen.
- Het scherm *Wachtwoord vergeten* geeft altijd hetzelfde antwoord, of de
  gebruikersnaam nu bestaat of niet.
- De SMTP-gegevens en het herstelmailadres moeten leesbaar zijn voor je
  aangemeld bent en kunnen dus niet met de datasleutel versleuteld worden. Ze
  staan versleuteld met een aparte sleutel in `lokaal.key`, naast de databank.
  Financiële gegevens blijven onveranderd beschermd.
- De databank kent een lichte migratie: bestaande installaties krijgen de
  nieuwe kolommen erbij zonder gegevensverlies.


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
