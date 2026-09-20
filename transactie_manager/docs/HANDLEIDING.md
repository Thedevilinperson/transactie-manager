# Handleiding Transactie Manager

Versie 0.13.2

Deze handleiding beschrijft de toepassing van begin tot eind: installeren,
eerste inrichting, transacties toevoegen, indelen en rapporteren.

---

## Inhoud

1. [Wat de toepassing doet](#1-wat-de-toepassing-doet)
2. [Installeren](#2-installeren)
3. [Eerste inrichting](#3-eerste-inrichting)
4. [Transacties toevoegen](#4-transacties-toevoegen)
5. [Kredietkaartuittreksels](#5-kredietkaartuittreksels)
6. [Automatisch indelen](#6-automatisch-indelen)
7. [Nazicht](#7-nazicht)
8. [Overzichten](#8-overzichten)
9. [Instellingen](#9-instellingen)
10. [Beveiliging en back-up](#10-beveiliging-en-back-up)
11. [Bij problemen](#11-bij-problemen)

---

## 1. Wat de toepassing doet

Je leest je bankafschriften in, de toepassing deelt de verrichtingen zelf in
categorieën in, en je krijgt overzichten van wat er per jaar naar welke post
gaat.

Elke transactie bestaat uit een datum, de twee rekeningnummers, de naam van de
tegenpartij, de naam van de begunstigde en één of meer mededelingen. Daarbovenop
komt de indeling: inkomst of uitgave, een hoofdcategorie, een subcategorie, een
sub-subcategorie, de winkel of zaak, en bij vakantie-uitgaven het land van
bestemming.

Alles blijft bij jou. Er gaat niets naar een externe dienst, tenzij je
uitdrukkelijk de webopzoeking bij het AI-model aanzet.

---

## 2. Installeren

### 2.1 Als Home Assistant-add-on

Twee wegen, allebei zonder tussenstap.

**Via de repository-URL.** Zet dit project op GitHub en voeg het adres toe bij
**Instellingen › Add-ons › Add-on-winkel › Repositories**. Het bestand
`repository.yaml` aan de wortel zorgt ervoor dat Home Assistant de repository
herkent.

**Als lokale add-on.** Kopieer de map `transactie_manager` in haar geheel naar
`/addons/` op je Home Assistant-systeem, bijvoorbeeld via de Samba-add-on. Ga
daarna naar de add-on-winkel, open het menu rechtsboven en kies **Repositories
vernieuwen**. De add-on verschijnt onder *Lokale add-ons*.

> Kopieer de hele map, niet enkel de losse bestanden. Home Assistant bouwt met
> de add-on-map als context: alles waar de Dockerfile naar verwijst, moet in
> diezelfde map staan.

Installeer de add-on, zet **Toon in zijbalk** aan en start ze. De eerste keer
bouwen duurt even; op armv7 moet `cryptography` gecompileerd worden en kan dat
een kwartier duren.

Meer daarover in [ADDON.md](ADDON.md).

### 2.2 Lokaal op Windows

Dubbelklik `start_windows.bat`. De eerste keer maakt dat script een virtuele
omgeving aan en installeert het de benodigde pakketten; daarna start het meteen.
Je browser opent vanzelf op `http://127.0.0.1:8099/`.

Je hebt Python 3.11 of nieuwer nodig. Vink bij het installeren van Python
**Add Python to PATH** aan.

### 2.3 Lokaal op Linux of macOS

```
./start_linux.sh
```

### 2.4 Instellingen via omgevingsvariabelen

| Variabele            | Standaard        | Betekenis                            |
|----------------------|------------------|--------------------------------------|
| `TM_DATA_DIR`        | `./data`         | Waar databank en sleutel staan       |
| `TM_PORT`            | `8099`           | Poort                                |
| `TM_HOST`            | `0.0.0.0`        | Adres om op te luisteren             |
| `TM_SESSION_MINUTES` | `120`            | Hoe lang je aangemeld blijft         |
| `TM_MAX_UPLOAD_MB`   | `25`             | Grootste bestand dat je mag opladen  |

---

## 3. Eerste inrichting

### 3.1 Beheerder aanmaken

Bij de allereerste start kom je op het scherm **Eerste start**. Kies een
gebruikersnaam en een wachtwoord van minstens tien tekens.

Daarna krijg je eenmalig je **herstelsleutel** te zien: 32 tekens in acht
groepjes. Schrijf die over of zet hem in je wachtwoordbeheerder. Hij wordt
nergens bewaard en kan niet opnieuw getoond worden.

> **Bewaar het wachtwoord én de herstelsleutel.** Ben je ze allebei kwijt, dan
> zijn de gegevens niet meer te ontsleutelen. Bewaar de herstelsleutel niet in
> dezelfde map als je back-up en niet enkel op het toestel waarop de toepassing
> draait.

### 3.2 Herstel instellen

Ga naar **Instellingen › Herstel en e-mail** en vul in waar de herstelcode
naartoe mag. Vul daaronder de mailserver in en stuur een testbericht.

Voor Yahoo Mail:

| Veld           | Waarde                                  |
|----------------|-----------------------------------------|
| Server         | `smtp.mail.yahoo.com`                   |
| Poort          | 465 met SSL, of 587 met STARTTLS        |
| Gebruikersnaam | je volledige adres, `jij@yahoo.com`     |
| Wachtwoord     | een app-wachtwoord van zestien tekens   |

> Yahoo aanvaardt je gewone wachtwoord niet meer voor SMTP. Maak in je
> Yahoo-account onder **Accountbeveiliging › App-wachtwoord genereren** een
> app-wachtwoord aan en vul dat hier in. Trek het in bij Yahoo als je het
> toestel ooit weggeeft.

### 3.3 Rekening toevoegen

Ga naar **Instellingen › Rekeningen** en voeg je zichtrekening toe. Vul het
rekeningnummer in: daarmee kan de toepassing bij een bestand met meerdere
rekeningen elke rij aan de juiste rekening hangen.

### 3.4 Categorieën

Je kan twee kanten op.

**Je hebt al een categorieënbestand.** Ga naar **Instellingen ›
Referentielijst**. Er staat een voorbeeldbestand klaar om te downloaden.

De kolommen worden herkend aan hun kopregel, dus hun volgorde doet er niet toe
en je hoeft ze niet allemaal te hebben:

| Kop                 | Inhoud                                                      |
|---------------------|-------------------------------------------------------------|
| Sleutel             | de beschrijving en de tegenpartij, met een koppelteken ertussen |
| Hoofdcategorie      | verplicht — zonder deze kolom valt er niets af te leiden     |
| Categorie           | eerste subniveau                                            |
| Subcategorie        | tweede subniveau                                            |
| Winkel              | winkel, of bij vakantie het land van bestemming             |

In plaats van *Sleutel* mag er ook Omschrijving, Beschrijving, Referentie,
Mededeling of Tegenpartij staan; in plaats van *Winkel* ook Handelaar, Zaak of
Land.

**Een bestand met enkel de boomstructuur** — dus alleen Hoofdcategorie,
Categorie en Subcategorie — werkt ook. Er valt dan geen enkele regel uit af te
leiden, want er staat nergens welke transactie in welke categorie hoort. Het
scherm zegt dat en neemt alleen de boom over.

Staat er helemaal geen kopregel in je bestand, dan wordt de oude volgorde
aangehouden: sleutel, hoofdcategorie, categorie, subcategorie, winkel.

Je krijgt eerst een analysescherm te zien: hoeveel categorieën eruit volgen, hoe
de boom eruitziet, en welke tegenpartijen in je lijst naar meer dan één
categorie verwijzen. Pas als je op **Referentielijst inlezen** klikt, wordt er
iets weggeschreven.

Daar kies je ook wat er met je huidige categorieën gebeurt:

- **Behouden en aanvullen** — wat er al staat blijft; nieuwe categorieën en
  regels komen erbij. De indeling van je transacties blijft ongemoeid.
- **Integraal vervangen** — alles wordt gewist en vervangen door deze lijst. Je
  transacties blijven bestaan maar verliezen hun categorie.

> **Integraal vervangen op een databank waar al werk in zit, is ingrijpender dan
> het lijkt.** Ook wat je met de hand hebt ingedeeld verliest zijn categorie, en
> dat is naderhand niet te herstellen door de regels opnieuw toe te passen: een
> handmatige keuze en een gelijkenis met je historiek laten zich niet
> reconstrueren, en de bron van de toewijzing is hoe dan ook weg. Staat er al
> iets, dan toont het scherm bovenaan hoeveel transacties, hoeveel ingedeeld en
> hoeveel met de hand. Er wordt sowieso een kopie van de databank gelegd voor er
> iets verandert; zie *Kopieën* in hoofdstuk 10.

Daarnaast kies je **wat je uit de lijst overneemt**:

- **De volledige referentielijst** — categorieën én de koppeling met de
  beschrijvingen, waaruit regels worden afgeleid. Kies dit wanneer de lijst ook
  je manier van indelen beschrijft.
- **Alleen de boomstructuur** — enkel de categorieën, hun onderverdelingen en
  hun volgorde. Er worden geen regels afgeleid, dus je indeling blijft je eigen
  werk. Kies dit wanneer de lijst je categorieën beschrijft maar niet hoe je
  transacties erin terechtkomen.

En tot slot **wat er daarna moet gebeuren**: niets, of opnieuw indelen — alleen
wat geen categorie heeft, of alles wat nog niet bevestigd is. Het eerste is het
veilige bereik en de standaard.

Uit zo'n bestand komen twee soorten regels. Voor elke rij komt er een regel die
exact op die sleutel past. Daarnaast komt er een bredere regel op enkel de
tegenpartij, maar alleen wanneer die tegenpartij in het hele bestand naar
dezelfde indeling verwijst. Staat een tegenpartij nu eens bij boodschappen en
dan weer bij vakantie, dan wordt ze gemarkeerd als onzeker: transacties van die
tegenpartij komen in het nazicht in plaats van blind toegewezen te worden.

Verschillen in hoofdlettergebruik worden samengevoegd. Staat er in je bestand
zowel `Auto` als `auto`, dan wordt dat één categorie, met de schrijfwijze die
het vaakst voorkomt.

**Je begint van nul.** Er staat al een bruikbare boom klaar met de gebruikelijke
posten. Pas die aan bij **Instellingen › Categorieën**.

> Na het inlezen van een referentielijst staat elke hoofdcategorie op soort
> "beide". Uit de lijst valt namelijk niet af te leiden of het om inkomsten of
> uitgaven gaat. Zet de soort juist bij Instellingen › Categorieën als je wil
> dat de keuzelijsten korter worden.

---

## 4. Transacties toevoegen

### 4.1 Een bestand inlezen

Ga naar **Bestand inlezen** en kies je afschrift. Excel (`.xlsx`, `.xlsm`) en
CSV worden ondersteund. Kies je bank in de lijst, of laat het op *Automatisch
herkennen* staan.

Je komt op het scherm **Kolommen nakijken**. Daar zie je per veld welke kolom
gekozen is, en daaronder de eerste rijen zoals ze ingelezen zouden worden. Staat
er ergens een streepje waar een waarde hoort, pas dan de kolomkeuze aan en klik
**Voorbeeld verversen**.

Voor Argenta staat het profiel al goed. De uitvoer van Argenta Bankieren heeft
deze elf kolommen, en alle elf worden herkend:

```
Rekening · Boekdatum · Valutadatum · Referentie · Beschrijving · Bedrag ·
Munt · Verrichtingsdatum · Rekening tegenpartij · Naam tegenpartij · Mededeling
```

De kolom **Beschrijving** is belangrijker dan ze lijkt: samen met de naam van de
tegenpartij vormt ze de sleutel waarop de referentielijst werkt.

Klik daarna op de knop met het aantal rijen. Je krijgt te zien hoeveel
transacties nieuw zijn, hoeveel er al stonden en hoeveel er onleesbaar waren.

**Dubbels.** Ontdubbelen gebeurt op de referentie van de bank sámen met het
bedrag. Een referentie op zichzelf volstaat niet: Argenta hangt aan één
kaartafrekening soms twee boekingen met dezelfde referentie maar een
verschillend bedrag, en die zijn allebei echt. Ontbreekt de referentiekolom, dan
valt de toepassing terug op een vingerafdruk van datum, bedrag, rekening,
tegenpartij en mededeling. Je mag dus gerust overlappende afschriften inlezen;
wat er al staat, komt er niet nog eens bij.

Staat dezelfde referentie mét hetzelfde bedrag twee keer in één bestand, dan
wordt dat als één verrichting gezien. Hoort ze er in jouw geval wel twee keer te
staan, voeg de tweede dan toe via *Toch toevoegen* op het scherm hieronder.

**Voortgang.** Grote bestanden worden in de achtergrond verwerkt. Je ziet de
fase, het aantal verwerkte rijen en de verstreken tijd. Je mag het venster
sluiten; de invoer loopt door.

**Een vergeten kolom alsnog toevoegen.** Bied hetzelfde bestand gewoon opnieuw
aan met de ontbrekende kolom erbij en laat *Bestaande transacties aanvullen*
aangevinkt. Lege velden worden ingevuld en een mededeling die uitgebreid is
wordt vervangen. Er komen geen dubbels bij, en wat je zelf hebt aangepast blijft
staan.

**Wat er niet is toegevoegd.** Na een invoer staat er een knop *Bekijk wat er
niet is toegevoegd*. Daar zie je per rij waarom ze geen nieuwe transactie werd:
ze stond al in de databank, ze komt met dezelfde referentie én hetzelfde bedrag
twee keer in het bestand voor, of de datum of het bedrag was onleesbaar. Klopt een beoordeling niet, dan voeg je de rij
daar alsnog toe; de dubbelcontrole wordt dan overgeslagen. Hetzelfde scherm is
later terug te vinden via *Eerdere invoer*.

**Terugdraaien.** Ging er iets mis, ga dan naar **Bestand inlezen › Eerdere
invoer** en draai die invoerbeurt terug. Alle transacties uit die beurt worden
dan verwijderd.

### 4.2 Historiek met de indeling er al in

Heb je je transacties elders al ingedeeld, dan kan je die indeling mee inlezen.
Voeg vijf kolommen toe aan je bestand: **Hoofdcategorie**, **Subcategorie**,
**Sub-subcategorie**, **Winkel** en **Land**.

Op het scherm *Bestand inlezen* staat een knop om een voorbeeldbestand te
downloaden. Daarin zit een tweede werkblad dat per kolom uitlegt waarvoor ze
dient en of ze verplicht is. Alleen **Boekdatum** en **Bedrag** zijn echt
verplicht; de volgorde van de kolommen doet er niet toe.

Herkent de toepassing een kolom Hoofdcategorie, dan verschijnt op het
controlescherm de keuze **Indeling uit het bestand overnemen**. Die gaat voor op
het automatisch indelen. Categorieën die nog niet bestaan worden aangemaakt, en
die transacties komen meteen bevestigd binnen.

> **Hiermee bouwt dit bestand je categorieën op.** Elke hoofd-, sub- en
> subsubcategorie die erin voorkomt en nog niet bestaat, wordt aangemaakt — je
> categorieënlijst komt dus uit deze historiek en niet uit een referentielijst.
> Lees je nadien alsnog een referentielijst in met *integraal vervangen*, dan
> gaat dit werk weer weg. Doe het dus in de volgorde waarin je wil eindigen:
> eerst de referentielijst, dan de historiek. Er wordt vooraf een kopie van de
> databank gelegd; zie *Kopieën* in hoofdstuk 10.

### 4.3 Een transactie openen

Klik op de naam van een tegenpartij in de lijst om een transactie te openen. Je
ziet daar alles wat eraan vasthangt:

- **Zoals de bank ze aanleverde** — rekening, boekdatum, valutadatum, bedrag,
  richting, de referentie van de bank, en uit welk bestand ze kwam.
- **Hoe deze indeling tot stand kwam** — welke stap de categorie toekende en
  waarom, met de zekerheid erbij als het om een vergelijking ging.
- **De rij zoals ze in het bestand stond** — uitklapbaar onderaan, met alle
  kolommen, ook die waarvoor de toepassing geen eigen veld heeft. Handig als je
  je afvraagt waar een indeling vandaan komt.

Aanpasbaar zijn de beschrijving, de tegenpartij en diens rekeningnummer, de
begunstigde, de winkel, de mededeling, het land en de indeling. Boekdatum,
bedrag en de referentie van de bank liggen vast.

Gaat het om een aankoop van een kredietkaartuittreksel, dan staat er een
verwijzing naar de afrekening waaronder ze hangt. Bij een afrekening zie je
omgekeerd de lijst van uitgesplitste aankopen.

### 4.4 Met de hand

**Nieuwe transactie** in het menu. Laat de categorie leeg als je wil dat de
toepassing er zelf een kiest.

---

## 5. Kredietkaartuittreksels

Op je bankafschrift staat de maandelijkse kaartafrekening als één bedrag,
bijvoorbeeld `Debet ten voordele van BCC — MASTERCARD 063` van 1 382,53 euro.
Dat zegt niets over waar dat geld naartoe ging. De echte aankopen staan op het
PDF-uittreksel van de kaart.

### 5.1 Werkwijze

1. Ga naar **Kredietkaart-PDF**. Onderaan zie je de afrekeningen die op je
   afschriften herkend zijn.
2. Laad het PDF-uittreksel van die maand op.
3. Je krijgt een controlescherm: welke aankopen herkend zijn, hoeveel ze samen
   bedragen, en of dat overeenkomt met het totaal op het uittreksel. Wijkt het
   af, dan verschijnt daar een waarschuwing.
4. Kies bij **Hang ze onder deze afrekening** de bijhorende afrekening.
5. Vink af wat je wil overnemen en klik **Aankopen overnemen**.

De aankopen komen als losse transacties in de databank en worden ingedeeld zoals
elke andere transactie. De afrekening zelf wordt gemarkeerd en telt daarna niet
meer mee in de overzichten, zodat het bedrag maar één keer in je cijfers staat.

Wil je terug? **Losmaken** bij die afrekening verwijdert de aankopen en laat de
afrekening weer meetellen.

### 5.2 De status van een afrekening

Elke afrekening in het overzicht heeft een status, en je kan erop filteren:

- **Nog te doen** — er is niets mee gebeurd. Dit is precies wat je categorie
  Kredietkaart nog laat oplopen.
- **Uitgesplitst** — er hangen aankopen onder. De afrekening telt niet meer mee;
  de aankopen nemen haar plaats in.
- **Tegengeboekt** — ze valt weg tegen een andere boeking.

Die laatste is er voor afrekeningen die zijn teruggestort of rechtgezet. Zo'n
afrekening hoef je niet uit te splitsen: samen met haar tegenboeking komt ze op
nul uit. Wijs je de tegenboeking aan, dan verdwijnt ze uit je werklijst zonder
dat er iets aan je cijfers verandert.

**Automatisch afvinken.** Staat er boven het overzicht hoeveel open afrekeningen
een eenduidige tegenboeking hebben, met een knop om ze in één keer te koppelen.
Dat gebeurt alleen wanneer er précies één kandidaat is. Zijn er meerdere, dan is
het een keuze en geen vaststelling, en die laat de toepassing aan jou.

Een tegenboeking is een boeking op dezelfde rekening, met hetzelfde bedrag maar
het tegengestelde teken, binnen tien dagen, die nog nergens aan hangt. Dat
venster is krap gehouden: ruimer maken vergroot de kans dat een toevallig gelijk
bedrag wordt aangezien voor een tegenboeking.

**Met de hand** kan ook. Klik bij een afrekening op *Tegenboeking aanwijzen*; je
krijgt de kandidaten met datum, bedrag en omschrijving. Daar zet je ze ook weer
terug op *nog te doen*.

> Waarom komt je categorie Kredietkaart op nul uit? Niet doordat er iets wordt
> weggestreept, maar doordat een uitgesplitste afrekening simpelweg niet meer
> meetelt en een tegengeboekte tegen haar tegenboeking wegvalt. Wat er blijft
> staan, zijn de afrekeningen die nog *nog te doen* zijn.

### 5.3 Hoe de PDF gelezen wordt

Uittreksels van Mastercard en Visa zijn PDF's met een echte tekstlaag. Die tekst
wordt uitgelezen met `pdfplumber`, dat de woorden per regel teruggeeft mét hun
plaats op de bladzijde. Daardoor blijven kolommen die met spaties uitgelijnd
zijn overeind — bij platte tekstextractie lopen die vaak door elkaar. Is
`pdfplumber` niet beschikbaar, dan valt de toepassing terug op `pypdf`.

Vervolgens worden vier opmaakpatronen op de tekst losgelaten:

| Patroon                      | Vorm van de regel                          |
|------------------------------|--------------------------------------------|
| `datum_datum_tekst_bedrag`   | aankoopdatum, verwerkingsdatum, omschrijving, bedrag |
| `datum_tekst_bedrag`         | datum, omschrijving, bedrag                |
| `tekst_datum_bedrag`         | omschrijving, datum, bedrag                |
| `datum_iso_tekst_bedrag`     | datum als jjjj-mm-dd, omschrijving, bedrag |

Het patroon dat de meeste regels verklaart, wint. Klopt dat niet, kies dan
onderaan het controlescherm zelf een ander patroon.

Wat er verder gebeurt:

- Bedragen worden als uitgave geboekt, behalve wanneer er `CR`, `C` of `+`
  achter staat; dat is een terugbetaling.
- Staat er in de datum geen jaartal, dan wordt het jaar uit de kop van het
  uittreksel gehaald.
- Aankopen in vreemde munt worden herkend; het oorspronkelijke bedrag komt in
  de mededeling terecht.
- Regels als *Totaal*, *Vorig saldo* en *Bladzijde* worden overgeslagen.

Onderaan het controlescherm kan je de ruwe tekst uit de PDF openklappen. Handig
om te zien waarom een bepaalde regel niet herkend werd.

> **Ingescande uittreksels werken niet.** Bevat de PDF geen tekstlaag, dan zegt
> de toepassing dat, in plaats van er een gok van te maken. Er zit bewust geen
> tekenherkenning in: die vraagt zware pakketten die op een Raspberry Pi
> nauwelijks te installeren zijn, en ze zou de nauwkeurigheid van de bedragen
> verlagen. Vraag in dat geval bij je kaartuitgever een uittreksel met tekst op.

---

## 6. Automatisch indelen

De toepassing probeert vier dingen, in deze volgorde. Zodra er één lukt, stopt ze.

### Stap 1: vaste regels

Een regel legt vast: als dit veld deze waarde heeft, dan hoort de transactie in
die categorie. Regels worden afgehandeld van lage naar hoge prioriteit.

Je kan kijken naar de gecombineerde sleutel, de beschrijving, de naam van de
tegenpartij, het rekeningnummer van de tegenpartij of de mededeling. De
vergelijking is *bevat*, *is precies gelijk aan* of een reguliere expressie.

Een regel mag ook een bedragvork hebben. Daarmee los je het geval op waarbij
dezelfde tegenpartij verschillende dingen betekent:

| Regel                              | Veld              | Waarde  | Bedrag       | Indeling                   |
|------------------------------------|-------------------|---------|--------------|----------------------------|
| Total onder tien euro              | Naam tegenpartij  | `total` | tot 10       | Boodschappen › Speciaalzaak |
| Total vanaf tien euro              | Naam tegenpartij  | `total` | vanaf 10     | Transport › Auto › Brandstof |

De ondergrens telt mee, de bovengrens niet. `tot 10` betekent dus alles onder
tien euro. Deze twee regels staan als voorbeeld klaar.

**Velden combineren.** Onder *En ook* zet je bijkomende voorwaarden. Ze moeten
dan allemaal kloppen. Daarmee deel je één tegenpartij op naar wat er in de
mededeling staat:

| Regel         | Voorwaarden                                                      | Indeling             |
|---------------|------------------------------------------------------------------|----------------------|
| Total carwash | naam bevat `total` **en** mededeling bevat `carwash`              | Auto › Autowas       |
| Total tanken  | naam bevat `total` **en** mededeling bevat niet `carwash`         | Auto › Brandstof     |

*Bevat niet* is er speciaal voor dat tweede geval: alles van die tegenpartij,
behalve wat je er net uit wil houden. Het kan alleen als bijkomende voorwaarde,
niet als de enige — een regel die enkel zegt wat er níet in staat, zou op zowat
elke transactie passen.

Er staan altijd drie lege rijen klaar; een lege rij wordt overgeslagen. Een
bestaande voorwaarde wis je door haar waarde leeg te maken en te bewaren. Wil je
er meer dan drie bij, bewaar dan tussendoor: bij het heropenen staan er weer
drie klaar.

Combineren en een bedragvork kan samen, en de prioriteit beslist nog altijd
welke regel voorgaat als er meer dan één past. Zet de nauwkeurigste regel dus
op een lager getal.

Een treffer via een regel is zeker en wordt meteen bevestigd. Behalve wanneer de
regel als onzeker gemarkeerd staat: dat gebeurt bij tegenpartijen die in je
referentielijst onder meer dan één categorie voorkomen.

**Een regel bewerken, uitzetten of verwijderen.** In alle drie de gevallen
laten de transacties die hij had ingedeeld die categorie los. Past er nog een
andere regel op, dan neemt die het over; is er geen, dan komen ze op *nazicht*
te staan zonder categorie en vind je ze terug in het nazichtscherm. Na afloop
staat er hoeveel het er waren.

Bewerken volgt dezelfde weg als verwijderen. Eerst wordt opgezocht wat aan de
oude regel hing, dan wordt de regel aangepast, dan worden net die transacties
opnieuw beoordeeld. Past de aangepaste regel er nog op, dan blijft alles gewoon
staan. Daarna wordt de nieuwe regel nog losgelaten op wat geen categorie heeft,
zodat een regel die breder wordt ook meteen aanslaat.

Zet je de regel weer aan, dan pakt hij op wat nog geen categorie heeft. Je kan
een regel dus tijdelijk uitzetten zonder je indeling kwijt te spelen.

**Zoeken en sorteren in de regels.** Boven de tabel staat een filterbalk. Je
kan zoeken op naam, waarde, categorie of winkel, en filteren op hoofdcategorie,
op het veld waar de regel naar kijkt, en op actief of uitgezet.

*Voorwaarden* houdt alleen de gecombineerde regels over, of net alleen die op
één veld. Zoeken kijkt ook in de bijkomende waarden, en *Kijkt naar* vindt een
regel zodra één van haar voorwaarden naar dat veld kijkt.

Twee filters gaan over het bedrag en doen elk iets anders. *Bedragvork* houdt
alleen de regels over die een onder- of bovengrens hebben, of net alleen die
zonder. Gebruik die als je je vorken wil nakijken. *Vangt bedrag* toont welke
regels een bepaald bedrag zouden halen: vul 12,50 in en je ziet wie die aankoop
te pakken krijgt.

Regels zonder vork vangen elk bedrag en staan bij *Vangt bedrag* dus altijd in de
lijst. Zet er *Alleen met bedragvork* bij om net die weg te laten; dan blijven
alleen de regels over die het bedrag werkelijk verdelen.

Klikken op een kolomkop sorteert; nog eens klikken draait de richting om. De
kolom *Treffers* laat zien welke regels werk doen en welke nooit aanslaan.

**Alle regels opnieuw toepassen.** Boven de tabel staat daar een knop voor. Elke
transactie die door een regel is ingedeeld, wordt opnieuw beoordeeld met de
regels zoals ze nu staan, en daarna worden de regels nog losgelaten op alles wat
geen categorie heeft.

Je hebt die knop nodig wanneer je prioriteiten hebt verschoven of meerdere regels
na elkaar hebt aangepast. Een regel aanpassen kijkt namelijk alleen naar wat aan
díe regel hing. Hangt een transactie aan een andere regel die nog altijd past,
dan blijft ze daar hangen, ook als je aangepaste regel nu voorgaat. Geef je
bijvoorbeeld een nieuwe Total-regel prioriteit 1, dan verhuizen de bestaande
Total-transacties pas mee als je op deze knop klikt.

De ingreep loopt over je hele boekhouding, dus er komt eerst een bevestiging.
Wat je zelf hebt ingedeeld blijft staan, en wat de fuzzy stap of het AI-model
heeft toegewezen ook. Alleen wat door een regel is ingedeeld, wordt herbekeken.

Drie dingen blijven ongemoeid. Wat je zelf hebt ingedeeld, blijft altijd staan:
zodra jij een categorie kiest, is de band met de regel verbroken en overschrijft
een latere wijziging aan die regel jouw keuze niet meer. Wat de fuzzy stap of het
AI-model heeft toegewezen, blijft eveneens staan — alleen een toewijzing die van
déze regel kwam, gaat weg. En handelaar en land blijven zoals ze waren; die staan
los van de indeling.

### Stap 2: fuzzy vergelijking

Lukt stap 1 niet, dan vergelijkt de toepassing de naam van de tegenpartij met
alles wat ze al kent: je eerder bevestigde transacties én je referentielijst.
Die tweede bron is wat de motor bij een allereerste invoer al bruikbaar maakt,
wanneer er nog geen geschiedenis is.

Twee drempels bepalen wat er gebeurt, in te stellen bij **Instellingen ›
Automatisch indelen**:

- **Automatisch vanaf** (standaard 92%) — de indeling gaat door en wordt als
  zeker gemarkeerd.
- **Voorstellen vanaf** (standaard 72%) — de indeling wordt voorgesteld, maar de
  transactie komt in het nazicht.

Daaronder gebeurt er niets.

De vergelijking gebruikt bewust niet de gulste methode. Anders zou "Brico"
evengoed op "Brico Plan-It 4214 Gent" passen als op om het even welke andere
Brico, en zou een overschrijving naar een familielid bij de eerste de beste
naamgenoot belanden.

### Stap 3: het lokale AI-model

Voor wat overblijft kan je een lokaal model bevragen. Dat werkt met een
Ollama-server op je eigen netwerk. Het model krijgt de transactiegegevens en de
lijst met toegelaten categoriepaden, en moet er één kiezen.

Aanzetten bij **Instellingen › Automatisch indelen**. Vul het adres van je
Ollama-server in en de naam van het model, bijvoorbeeld `llama3.1:8b`. Met
**Verbinding testen** zie je meteen welke modellen klaarstaan.

Je kan het model ook eerst het web laten raadplegen over de tegenpartij. Dat
helpt bij namen die je zelf niet herkent. Houd er rekening mee dat de naam van
de tegenpartij daarbij je netwerk verlaat; laat dit uit als je dat liever niet
hebt.

Een voorstel van het model moet je altijd bevestigen. Je vraagt het aan per
transactie, met de knop **Vraag het model** in het nazicht.

### Stap 4: met de hand

Wat overblijft, deel je zelf in. De subcategorieën worden daarbij gefilterd op
de gekozen hoofdcategorie, en de sub-subcategorieën op de gekozen subcategorie.

Vink **Deze keuze onthouden als vaste regel** aan om er meteen een regel van te
maken. De volgende keer gaat het dan vanzelf.

### Regels afleiden uit je historiek

Staat je historiek eenmaal ingedeeld in de databank, dan kan je daar in één keer
een referentielijst uit laten opbouwen: **Regels uit historiek** in het menu.

Er wordt gekeken naar elke transactie die al een categorie heeft, en per veld
nagegaan of dat veld steeds naar dezelfde indeling verwijst. Vier soorten
aanwijzingen doen mee, in volgorde van hoe hard ze zijn:

| Aanwijzing                        | Waarom ze werkt |
|-----------------------------------|-----------------|
| Rekeningnummer van de tegenpartij | Een IBAN hoort bij één partij en verandert niet |
| Gestructureerde mededeling        | Het `+++...+++`-nummer hoort bij één schuldeiser |
| Beschrijving plus tegenpartij     | Onderscheidt een aankoop van een overschrijving aan dezelfde naam |
| Tegenpartij alleen                | Breed inzetbaar, maar botst het vaakst |

Verwijst een aanwijzing naar meerdere categorieën, dan wordt eerst geprobeerd of
het **bedrag** de gevallen scheidt. Zijn alle broodjes bij het tankstation onder
de tien euro en alle tankbeurten erboven, dan legt de toepassing daar zelf een
grens en maakt ze er twee regels van. Overlappen de bedragen wel, dan komt er
een regel die om bevestiging blijft vragen.

Je krijgt eerst een overzicht van wat eruit zou komen. Pas als je bevestigt,
wordt er weggeschreven. Regels die je zelf hebt ingevoerd en regels uit een
categorieënbestand blijven daarbij staan.

### Alles opnieuw laten indelen

Heb je regels toegevoegd of je referentielijst vernieuwd? Klik dan op **Opnieuw
indelen** bij het nazicht. Daar kies je eerst hoever het gaat:

**Alleen wat nog geen categorie heeft** — de standaard, en het veilige bereik.
Alles wat al ergens in zit blijft staan zoals het staat, met de bron erbij. Dit
is wat je wil na het inlezen van een referentielijst of een historiek waarin al
werk zit.

**Alles wat nog niet bevestigd is** — ook transacties die al een categorie
hebben worden herbekeken. Bevestigde transacties blijven hoe dan ook staan, en
een treffer via een regel geldt als bevestigd.

Een regel uitzetten of verwijderen regelt zichzelf: zie *Een regel bewerken,
uitzetten of verwijderen* hierboven.

**De bron gaat verloren.** Bij een herindeling herschrijft de motor niet alleen
de categorie maar ook de methode. Een transactie die nu *met de hand* zegt, kan
daarna *gelijkenis* of *vaste regel* zeggen. De categorie kan dezelfde blijven,
maar waar ze vandaan kwam niet. Daarom wordt er vooraf een kopie van de databank
gelegd — zie *Kopieën* verderop.

**Wat die melding betekent.** Achteraf staat er hoeveel transacties er opnieuw
ingedeeld zijn, uitgesplitst per stap: *via vaste regel*, *via gelijkenis*, *via
AI-model*. Dat onderscheid is belangrijk, want het is niet hetzelfde als de
filter *Vaste regel* in de transactielijst.

Staat er "1300 opnieuw ingedeeld" en zie je er maar twintig onder *Vaste regel*,
dan is dat geen fout: de overige 1280 komen van stap 2, de gelijkenis met je
historiek. Die krijgen methode *Gelijkenis*. Dat gebeurt ook wanneer je net
regels uit je historiek hebt afgeleid — de motor bouwt zijn
vergelijkingsmateriaal mee op uit die regels, maar een transactie die via de
gelijkenis binnenkomt en niet via de regel zelf, telt als gelijkenis.

**Welke lijnen precies.** Na een herindeling kom je meteen op de transactielijst
uit, gefilterd op *aangepast sinds* het moment waarop de herindeling begon. Daar
staan dus net die transacties. Wil je ze per stap bekijken, zet er dan de filter
*Bron* bij. Het merkje *aangepast sinds* reist mee wanneer je andere filters
aanvinkt; het kruisje erop laat het los.

Dat filter kijkt naar het tijdstip van wijzigen, tot op de seconde. Heb je in
diezelfde seconde nog iets anders aangepast, dan staat dat er ook bij.

---

## 7. Nazicht

Het scherm **Nazicht** heeft twee delen.

**Voorgesteld, nog te bevestigen.** Transacties die op iets bekends lijken, maar
niet zeker genoeg. Je ziet het voorstel, de zekerheid in procenten en waarom de
toepassing tot die keuze kwam. Klopt het, klik dan **Klopt**. Klopt het niet,
klik **Aanpassen**.

Met **Alle voorstellen bevestigen** neem je alles in één keer over. Handig na
een grote invoer, maar kijk het toch even door.

**Zonder categorie.** Transacties waar niets voor gevonden is. Deel ze zelf in,
of vraag het AI-model om een voorstel.

---

## 8. Overzichten

### 8.1 Jaartabel

**Jaartabel** in het menu. De rijen zijn je categorieën, de kolommen zijn de
jaren. Klik op het driehoekje om een categorie open te klappen tot het derde
niveau.

Uitgaven staan als negatief bedrag, inkomsten als positief. Kies je bij *Soort*
voor uitgaven, dan zie je alleen de uitgaande boekingen; wil je het saldo van een
categorie, kies dan *Alle*. Een categorie als Loon waar zowel loon binnenkomt als
onkosten uitgaan, toont bij *Alle* dus het verschil.

Filteren kan op soort, op hoofdcategorie, op rekening en op periode. Met
**Nazicht weglaten** reken je alleen met wat je bevestigd hebt.

**Uitvoer als CSV** geeft je de tabel zoals ze op het scherm staat, met
puntkomma als scheidingsteken en komma als decimaalteken, klaar voor Excel.

### 8.2 Grafieken

**Grafieken** toont de evolutie doorheen de tijd. Per jaar of per maand, met een
lijn per hoofdcategorie of per subcategorie. Er worden hoogstens twaalf lijnen
getekend, gesorteerd op totaalbedrag.

De grafieken worden als SVG in je browser getekend, zonder externe
bibliotheken. Ze werken dus ook zonder internet.

---

## 9. Instellingen

| Scherm                | Waarvoor                                                    |
|-----------------------|-------------------------------------------------------------|
| Rekeningen            | Rekeningen toevoegen en aanpassen                           |
| Categorieën           | De boom van drie niveaus beheren                            |
| Regels                | Vaste regels toevoegen, bewerken, uitzetten en verwijderen  |
| Referentielijst       | Een categorieënbestand inlezen                              |
| Automatisch indelen   | Drempels en het AI-model                                    |
| Gebruikers            | Extra gebruikers, alleen voor beheerders                    |
| Kopieën               | Kopieën van de databank terugzetten, alleen voor beheerders |
| Opnieuw beginnen      | De databank leegmaken, alleen voor beheerders               |
| Logboek               | De laatste tweehonderd handelingen                          |

Je bereikt ze allemaal via de tabbladen bovenaan het instellingengedeelte. In de
zijbalk staat daarom één regel *Instellingen*; wat je dagelijks doet staat
daarboven, wat je één keer instelt zit achter die tabbladen.

### Opnieuw beginnen

Wil je van voren af aan, dan hoef je niets opnieuw te installeren. Onder
**Instellingen › Opnieuw beginnen** kies je wat er weg moet:

- **Alleen de categorieën en regels** — de boom, alle regels en alle indelingen
  gaan weg. Je transacties blijven staan, maar zonder categorie. Hiermee
  herbegin je met een schone categorieënlijst op dezelfde gegevens.
- **Alleen de transacties** — alle transacties en de geschiedenis van je
  ingelezen bestanden gaan weg. Je categorieën en regels blijven klaarstaan.
- **Alles** — allebei. Eventueel met je rekeningen erbij.

Je gebruikers, wachtwoorden en instellingen blijven in alle gevallen staan.

Er zitten twee sloten op. Eerst een bevestigingsvenster, en daarna moet je het
woord `WISSEN` intypen. Vooraf wordt er een kopie van de databank gelegd, die
nooit automatisch opgeruimd wordt. Dat is het enige vangnet: het wissen zelf is
niet terug te draaien.

### De handleiding in de toepassing

Deze handleiding staat ook in de toepassing zelf, via **Handleiding** in de
zijbalk, met een inhoudstafel die meeschuift. Het is hetzelfde bestand als in de
repository, dus wat je hier leest en wat je daar ziet lopen nooit uiteen.

Een rekening of categorie die al in gebruik is, kan je niet verwijderen. Zet ze
op niet-actief: bestaande transacties blijven dan kloppen, maar de waarde
verschijnt niet meer in de keuzelijsten.

---

## 10. Beveiliging en back-up

### Hoe de versleuteling werkt

Uit je wachtwoord wordt met scrypt een sleutel afgeleid. Daarmee wordt een
willekeurige datasleutel van 32 bytes ontgrendeld. Die datasleutel versleutelt
elk gevoelig veld apart met AES-256-GCM: rekeningnummers, namen, mededelingen,
bedragen, categorienamen, winkels en landen.

Heeft iemand je databankbestand maar niet je wachtwoord, dan ziet die alleen
onleesbare tekst.

Voor zoeken en ontdubbelen bestaat er per veld een blinde index: een
HMAC-SHA256 van de genormaliseerde waarde. Daarmee kan de toepassing vergelijken
zonder de waarde zelf leesbaar op te slaan.

Wat wél leesbaar in de databank staat: de boekdatum, of het om een inkomst of
uitgave gaat, en de nummers die naar categorieën verwijzen. Dat is nodig om te
kunnen sorteren en filteren zonder de hele databank te ontsleutelen. De namen
achter die nummers staan wel versleuteld.

De datasleutel bestaat alleen in het geheugen van het draaiende proces, gekoppeld
aan je aanmelding. Na een herstart moet je opnieuw aanmelden. Er is geen manier
om de gegevens te lezen zonder dat iemand zich aanmeldt.

Werk je met meerdere gebruikers, dan krijgt elke gebruiker een eigen kopie van
dezelfde datasleutel, versleuteld met zijn eigen wachtwoord. Iedereen ziet
dezelfde gegevens; iedereen heeft zijn eigen wachtwoord.

### Wachtwoord vergeten

Klik op **Wachtwoord vergeten?** op het aanmeldscherm en vul je gebruikersnaam
in. Er gaat een code van zes cijfers naar je e-mailadres, een kwartier geldig.
Op het volgende scherm vul je die code in, samen met je herstelsleutel en je
nieuwe wachtwoord.

Je hebt ze **allebei** nodig. De code bewijst dat jij het bent; de
herstelsleutel is het enige waarmee je gegevens ontsleuteld kunnen worden. Die
sleutel zit niet in je mailbox en staat nergens op de machine, dus wie in je
e-mail raakt, komt niet bij je boekhouding.

Koppeltekens, spaties en hoofdletters in de herstelsleutel doen er niet toe. De
letters I, L, O en U komen niet voor in het alfabet: lees ze als 1, 1, 0 en V.

Een nieuwe sleutel maken kan bij **Instellingen › Herstel en e-mail**. De oude
werkt daarna niet meer.

### Waar de mailgegevens staan

Het herstelmailadres en het app-wachtwoord van de mailserver moeten leesbaar
zijn op het moment dat je je wachtwoord kwijt bent, dus voor je aangemeld bent.
Ze kunnen daarom niet met je datasleutel versleuteld worden en staan versleuteld
met een aparte sleutel in `lokaal.key`, naast de databank. Wie bij die map kan,
kan bij je mailadres en dat app-wachtwoord — maar niet bij je transacties.

### Back-up

Alles staat in de map die `TM_DATA_DIR` aanwijst: `/data` in de add-on,
`./data` bij een lokale installatie. Kopieer die map om een back-up te maken.
In Home Assistant zit `/data` mee in de gewone back-up.

> Een back-up zonder je wachtwoord is onleesbaar. Bewaar het wachtwoord dus
> ergens anders dan bij de back-up — in een wachtwoordbeheerder bijvoorbeeld.

Het bestand `secret.key` in dezelfde map ondertekent alleen de sessiecookie. Het
ontsleutelt niets. Verlies je dat bestand, dan moet iedereen zich gewoon opnieuw
aanmelden.

### Kopieën en ongedaan maken

Naast die back-up van de hele map houdt de toepassing zelf kopieën van de
databank bij, onder **Instellingen › Kopieën**. Die zijn er voor iets anders:
niet voor een kapotte schijf, maar voor een handeling die je liever niet had
gedaan.

Er komt automatisch een kopie vóór elke ingreep die je indeling in één keer kan
herschrijven:

- een referentielijst inlezen;
- een historiek of een ander bestand inlezen;
- regels afleiden uit je historiek;
- een herindeling;
- alle regels opnieuw toepassen.

Daarnaast komt er één per dag, bij de eerste aanmelding van die dag.

Op het scherm zie je per kopie het tijdstip, de aanleiding en de grootte.
**Terugzetten** maakt die kopie weer de werkende databank. Alles wat je sindsdien
hebt gedaan verdwijnt daarmee — ingelezen bestanden, indelingen, regels. Van de
huidige toestand wordt eerst nog een kopie gelegd, dus ook het terugzetten zelf
is ongedaan te maken.

De laatste vijftien automatische kopieën blijven staan; oudere verdwijnen
vanzelf. Kopieën die je zelf maakt en die van vlak vóór een terugzetting worden
nooit opgeruimd.

> Een kopie is even versleuteld als het origineel, en de sleutel wordt uit je
> wachtwoord afgeleid. Een kopie van vóór een wachtwoordwijziging valt dus niet
> meer te openen.

---

## 11. Bij problemen

**Ik ben mijn wachtwoord vergeten.** Gebruik *Wachtwoord vergeten?* op het
aanmeldscherm. Je hebt de code uit je e-mail én je herstelsleutel nodig.

**Ik ben mijn wachtwoord én mijn herstelsleutel kwijt.** Dan zijn de gegevens
niet meer leesbaar. Verwijder de map `data` en begin opnieuw. Dit is geen
tekortkoming maar de bedoeling: kon de toepassing je gegevens zonder een van
beide openen, dan kon iemand anders dat ook.

**De herstelcode komt niet aan.** Kijk in je map met ongewenste post. Stuur een
testbericht bij *Instellingen › Herstel en e-mail*; de foutmelding van de
mailserver komt dan rechtstreeks op het scherm. Weigert Yahoo de aanmelding, dan
gebruik je waarschijnlijk je gewone wachtwoord in plaats van een
app-wachtwoord.

**Een kolom wordt niet herkend bij het inlezen.** Kies de juiste kolom zelf op
het scherm *Kolommen nakijken* en klik *Voorbeeld verversen*.

**De bedragen kloppen niet na het inlezen.** Waarschijnlijk gaat het om het
decimaalteken. Zet op het scherm *Kolommen nakijken* de keuze op *Komma* of
*Punt* in plaats van *Zelf bepalen*.

**Alles staat in de verkeerde categorie na een invoer.** Draai die invoerbeurt
terug via *Bestand inlezen › Eerdere invoer*, pas je regels aan en lees opnieuw
in.

**Het AI-model antwoordt niet.** Test de verbinding bij *Instellingen ›
Automatisch indelen*. Draait de add-on in Home Assistant en Ollama op dezelfde
machine, gebruik dan `http://homeassistant.local:11434` of het IP-adres; niet
`localhost`, want dat wijst binnen de add-on naar de add-on zelf.

**Geen aankopen herkend in een PDF-uittreksel.** Klap onderaan de ruwe tekst
open. Zie je daar leesbare regels staan, kies dan een ander patroon. Zie je
niets of alleen losse tekens, dan is het een scan en kan de toepassing er niets
mee.

**De som van de kaartaankopen wijkt af van het totaal.** Er ontbreken regels, of
er zit een regel bij die geen aankoop is. Kijk de lijst na op het
controlescherm en vink af wat niet klopt.

**De add-on start niet.** Kijk in het logboek van de add-on in Home Assistant.
Duurt het bouwen erg lang op een Raspberry Pi, dan is dat normaal:
`cryptography` moet daar gecompileerd worden.

**Het bouwen stopt op het basisimage.** Home Assistant onderhoudt alleen
basisimages die nog ondersteund worden. Zet in de `FROM`-regel bovenaan
`transactie_manager/Dockerfile` een recentere combinatie van Python en Alpine.

**Ik zie plots een tweede zijbalk van Home Assistant binnen de add-on.** Dat
hoort niet meer voor te vallen vanaf versie 0.4.2. Kom je het toch tegen,
herlaad dan de bladzijde met Ctrl+F5.

**Ik krijg "404: Not Found" bij het openen van de add-on.** Die melding komt van
Home Assistant, niet van de toepassing. Vanaf versie 0.2.1 hoort dat niet meer
voor te vallen. Zie je het toch, herstart dan de add-on en ververs de
bladzijde met Ctrl+F5; een oude verwijzing kan nog in de cache van je browser
zitten.

**Home Assistant ziet de add-on niet.** Controleer dat je de map
`transactie_manager` als geheel gekopieerd hebt, met `config.yaml` en de
`Dockerfile` er rechtstreeks in. Staan die in een onderliggende map, dan vindt
de Supervisor ze niet.
