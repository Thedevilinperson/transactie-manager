# Handleiding Transactie Manager

Versie 0.8.3

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
Referentielijst**. Er staat een voorbeeldbestand klaar om te downloaden. Het werkblad moet vijf kolommen hebben, in deze volgorde:

| Kolom | Inhoud                                                          |
|-------|-----------------------------------------------------------------|
| A     | referentiesleutel: de beschrijving en de tegenpartij, met een koppelteken ertussen |
| B     | hoofdcategorie                                                  |
| C     | categorie (eerste subniveau)                                    |
| D     | subcategorie (tweede subniveau)                                 |
| E     | winkel, of bij vakantie het land van bestemming                 |

Je krijgt eerst een analysescherm te zien: hoeveel categorieën eruit volgen, hoe
de boom eruitziet, en welke tegenpartijen in je lijst naar meer dan één
categorie verwijzen. Pas als je op **Referentielijst inlezen** klikt, wordt er
iets weggeschreven.

Daar kies je ook wat er met je huidige categorieën gebeurt:

- **Behouden en aanvullen** — wat er al staat blijft; nieuwe categorieën en
  regels komen erbij. De indeling van je transacties blijft ongemoeid.
- **Integraal vervangen** — alles wordt gewist en vervangen door deze lijst. Je
  transacties blijven bestaan maar verliezen hun categorie. Zet dan meteen
  *opnieuw indelen* aan.

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

**Dubbels.** Ontdubbelen gebeurt op de referentie van de bank, want die is uniek
per verrichting. Ontbreekt die kolom, dan valt de toepassing terug op een
vingerafdruk van datum, bedrag, rekening, tegenpartij en mededeling. Je mag dus
gerust overlappende afschriften inlezen; wat er al staat, komt er niet nog eens
bij.

**Voortgang.** Grote bestanden worden in de achtergrond verwerkt. Je ziet de
fase, het aantal verwerkte rijen en de verstreken tijd. Je mag het venster
sluiten; de invoer loopt door.

**Een vergeten kolom alsnog toevoegen.** Bied hetzelfde bestand gewoon opnieuw
aan met de ontbrekende kolom erbij en laat *Bestaande transacties aanvullen*
aangevinkt. Lege velden worden ingevuld en een mededeling die uitgebreid is
wordt vervangen. Er komen geen dubbels bij, en wat je zelf hebt aangepast blijft
staan.

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

### 5.2 Hoe de PDF gelezen wordt

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

Een treffer via een regel is zeker en wordt meteen bevestigd. Behalve wanneer de
regel als onzeker gemarkeerd staat: dat gebeurt bij tegenpartijen die in je
referentielijst onder meer dan één categorie voorkomen.

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
indelen** bij het nazicht. Alles wat nog niet bevestigd is, gaat opnieuw door de
motor. Bevestigde transacties blijven staan.

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
| Regels                | Vaste regels toevoegen, uitzetten en verwijderen            |
| Referentielijst       | Een categorieënbestand inlezen                              |
| Automatisch indelen   | Drempels en het AI-model                                    |
| Gebruikers            | Extra gebruikers, alleen voor beheerders                    |
| Logboek               | De laatste tweehonderd handelingen                          |

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
basisimages die nog ondersteund worden. Zet in `transactie_manager/build.yaml`
een recentere combinatie van Python en Alpine.

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
