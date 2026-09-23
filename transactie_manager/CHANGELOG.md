# Wijzigingslogboek

Alle noemenswaardige wijzigingen aan dit project staan hier. De opmaak volgt
[Keep a Changelog](https://keepachangelog.com/nl/1.1.0/) en de versienummers
volgen [Semantische versionering](https://semver.org/lang/nl/).

## [0.26.0] — 2026-09-23

### Opgelost
- **Een AI-voorstel vulde de categorievelden niet in.** Het scherm wachtte op
  één antwoord van de server, en die wachtte op het model. Sinds 0.24.0 krijgt
  het model je volledige indeling met voorbeelden mee, en op een processor
  zonder grafische kaart duurt dat al snel een of twee minuten. Zo lang
  openstaande verbindingen worden onderweg afgebroken (de ingress van Home
  Assistant); de browser kreeg dan geen bruikbaar antwoord en vulde niets in,
  terwijl de server het voorstel wel bewaarde. In een rechtstreekse test,
  zonder proxy ertussen, werkte het wel — daarom viel het niet eerder op.
  De bevraging loopt nu op de server in een aparte draad, net als een grote
  invoer. De knop krijgt meteen een kenmerk terug en vraagt daarna om de twee
  seconden de stand op; zodra het voorstel er is, worden hoofdcategorie,
  subcategorie, sub-subcategorie en winkel ingevuld. Geen enkele aanvraag duurt
  nog langer dan een ogenblik.

### Gewijzigd
- De knop **Vraag het model** / **Vraag het AI-model** toont tijdens het wachten
  hoelang het al duurt (*Bezig… 45 s*).
- Een antwoord dat geen JSON is (een foutpagina van een proxy) geeft nu een
  duidelijke melding met de HTTP-code, in plaats van stil niets te doen. Een
  enkele gemiste stand tijdens het wachten wordt opnieuw geprobeerd.
- Nieuw eindpunt `api/ai-voorstel/stand/<kenmerk>`; `api/ai-voorstel/<id>`
  antwoordt voortaan met `202` en een kenmerk in plaats van met het voorstel
  zelf.


## [0.25.0] — 2026-09-22

### Opgelost
- **De gelijkenisstap (fuzzy) ging te ver en bevestigde dat zelf.** Een regel
  "tegenpartij Axelle Huyge **én** *drinkgeld* in de mededeling" deelde daardoor
  elke transactie van Axelle in bij *Kinderen › drinkgeld* — tandarts,
  frietschap, Turijn — met "100% zeker" en automatisch bevestigd. Drie oorzaken
  die elkaar versterkten:
  - **regels met bijkomende voorwaarden of een bedragvork** gingen mee als
    vergelijkingsmateriaal met alleen de naam. Ze doen daar niet meer mee; ze
    werken alleen nog in de regelstap, precies zoals ze geschreven zijn;
  - **transacties die een regel of de gelijkenisstap zelf had ingedeeld**
    telden als geschiedenis, weer op naam alleen. Zo veralgemeende de motor
    zijn eigen werk. Alleen wat een mens indeelde (met de hand, uit een
    ingelezen historiek, of een bevestigd AI-voorstel) telt nog mee. Ook tijdens
    een invoer stuurt wat de motor net indeelde de volgende rij niet meer;
  - **een tegenpartij onder meer dan één categorie** werd niet als twijfelgeval
    herkend: de zwaarste categorie won en werd automatisch bevestigd. Nu wordt
    ze voorgesteld maar niet bevestigd, met de uitleg dat je zelf moet kiezen.
- **Familieleden met dezelfde familienaam** belandden bij elkaars categorie:
  *Daniel Huyge* kreeg met 91% *Pensioensparen* via een referentie "Huyge". Past
  een naam in een andere, dan telt dat nu alleen als het eerste woord gelijk
  is (*Delhaize* in *Delhaize Gent 1234* wel, *Huyge* in *Daniel Huyge* niet), en
  zo'n gedeeltelijke treffer wordt nooit automatisch bevestigd.
- **De richting telde niet mee**: een uitgave kon aan een inkomst van dezelfde
  tegenpartij gekoppeld worden. Er wordt nu alleen binnen dezelfde richting
  vergeleken.
- De voorbeelden die het AI-model uit je historiek krijgt, bevatten geen
  automatisch bevestigde gelijkenissen meer: niemand heeft die nagekeken.

### Toegevoegd
- **Opnieuw indelen › Automatisch bevestigde gelijkenissen opnieuw bekijken.**
  Beoordeelt de transacties met bron *gelijkenis* die als bevestigd staan
  opnieuw met de strengere motor. Een regel neemt over waar er een past; een
  twijfelgeval gaat naar de voorstellen; wat nergens meer door gedragen wordt,
  verliest zijn categorie en komt bij *Zonder categorie*. Zoals elke
  herindeling begint dit met een kopie van de databank.


## [0.24.0] — 2026-09-22

### Gewijzigd
- **Het AI-model deelt nu in aan de hand van je eigen historiek.** Analyse van
  drie foute voorstellen toonde telkens hetzelfde: het model kende jouw
  indeling niet (restaurants staan onder *Hobby*, tweedehandsverkoop onder
  *Kledij*), niet de Vlaamse context (*chiro* werd een chiropractor), en de
  webopzoeking vond bij personen naamgenoten en merken. De vraag bestaat nu uit:
  - **de paden die je in deze richting echt gebruikt**, alfabetisch, elk met
    jouw omschrijving en tot drie tegenpartijen die je er eerder in zette. Voor
    een inkomst dus geen *Dokter* of *Apotheek* meer, tenzij je daar ooit een
    inkomst boekte. Heb je in een richting nog nauwelijks iets bevestigd, dan
    de volledige boom;
  - **de transactie, met de mededeling voorop**;
  - **tot zes gelijkaardige eerdere transacties** uit je historiek, gezocht op
    zeldzame woorden in tegenpartij en mededeling, in beide richtingen;
  - **webinformatie alleen bij betalingen aan een zaak.** Bij overschrijvingen
    wordt niet meer gezocht; het logboek zegt waarom.
- **De bronnen hebben een vaste volgorde**: mededeling, gelijkaardige eerdere
  transacties, webinformatie, naam. De regel uit 0.23.0 dat webinformatie de
  belangrijkste bron was, is terug weg: ze liet het model een duidelijke
  mededeling ("boekenreeks stephen king") negeren ten voordele van een
  lingeriemerk met dezelfde voornaam.
- **Weer één vraag in plaats van twee.** Een fout in de eerste stap
  (*Gezondheid*) kon de tweede niet meer rechtzetten. Met de kortere,
  verklaarde lijst is één stap weer haalbaar.
- **De zekerheid komt niet meer van het model** (dat gaf "90%" bij drie foute
  antwoorden op drie). Een AI-voorstel toont geen percentage meer. De uitleg
  zegt wel of de keuze overeenkomt met een sterk gelijkende eerdere
  transactie, of er juist van afwijkt.
- **Een paar Vlaamse begrippen** in de spelregels: Chiro, KSA, KLJ en scouts zijn
  jeugdbewegingen, een frituur is een snackbar. En: bij een inkomst betaalt
  iemand jou.
- De time-out voor een antwoord van het model gaat van 60 naar 300 seconden;
  op een processor zonder grafische kaart duurt een grote vraag lang.

### Toegevoegd
- **Omschrijving per categorie** voor het AI-model (*Instellingen ›
  Categorieën*, onderaan): trefwoorden die zeggen wat jij onder een categorie
  verstaat. Ze staan in de boom achter de naam en gaan mee bij elk pad dat door
  die categorie loopt. Versleuteld opgeslagen, zoals de naam. **Schemaversie
  9**: kolom `omschrijving_enc` op de categorietabel; bestaande databanken
  krijgen ze bij het opstarten.
- **Contextvenster (tokens)** bij *Instellingen › Automatisch indelen*,
  standaard 8192. Ollama gebruikt anders een klein standaardvenster en kort een
  te lange vraag **stil** in — bij de lijst van bijna tweehonderd paden uit
  0.22.0 viel er vermoedelijk een deel van de instructies weg. Past de vraag
  niet, dan worden eerst de voorbeeldnamen ingekort en in het uiterste geval
  alleen de meest gebruikte paden meegegeven.
- **Het logboek toont per bevraging** of er op het web gezocht werd (en zo niet
  waarom), hoeveel paden en voorbeelden meegingen, en hoeveel tokens de vraag
  volgens Ollama telde, met de duur. Vult de vraag het venster, dan staat er een
  waarschuwing bij.

### Opgelost
- **Tussenniveaus waarin je rechtstreeks indeelt, ontbraken in de keuzelijst.**
  *Hobby › restaurant* heeft subcategorieën, en alleen de uiteinden werden
  aangeboden. Een bar kon dus nooit bij *Hobby › restaurant* uitkomen.


## [0.23.0] — 2026-09-22

### Gewijzigd
- **Het AI-model kiest nu in twee stappen: eerst de hoofdcategorie, dan het
  pad daarbinnen.** Met één lijst van bijna tweehonderd paden begreep
  `qwen2.5:7b` de zaak wel ("koop van LED-verlichting via een online winkel"),
  maar koos het toch *Vakantie › vakantie-uitgaven › Shopping* met 90%
  zekerheid — op het woord, niet op het product. Nu kiest het eerst uit een
  korte lijst hoofdcategorieën, elk met de namen van wat eronder valt als
  uitleg, en daarna alleen nog uit de paden binnen die hoofdcategorie. Heeft
  die maar één pad, dan valt de tweede vraag weg. Geeft de eerste stap geen
  bruikbaar antwoord, dan valt de tweede terug op de volledige lijst.
- **De webinformatie staat nu bovenaan de vraag** en wordt uitdrukkelijk de
  belangrijkste bron genoemd. Is er geen, dan zegt de vraag dat ook.
- **Stap 1 laat het model eerst de soort zaak en het vermoedelijke product
  benoemen**, en pas dan kiezen. Die beschrijving gaat mee naar stap 2 en staat
  ook in de uitleg bij het voorstel.
- **Nieuwe spelregels in de prompt**, telkens een fout die het model maakte:
  deel in volgens wat er gekocht werd en niet hoe of waar (*online*, *webshop*,
  *shopping*, *eCommerce*, *betaalkaart* zeggen niets); een vakantiecategorie
  alleen bij een echte reis, niet bij een buitenlandse webshop. De soort
  verrichting gaat mee met de vermelding dat ze het betaalmiddel beschrijft.
- De zekerheid van een voorstel is de laagste van beide stappen.
- **Het logboek toont beide stappen apart**, elk met de vraag en het ruwe
  antwoord.

### Opgelost
- Een categorie die letterlijk *Hoofdcategorie* heet — de kopregel van een
  ingelezen categorieënbestand — werd als keuze aan het model voorgelegd. Ze
  blijft nu buiten de lijst.


## [0.22.0] — 2026-09-22

### Gewijzigd
- **Het AI-model kiest nu altijd een categorie.** De uitweg "nummer 0: geen van
  deze past" uit versie 0.19.0 werkte averechts: `qwen2.5:7b` las nummer 0 als
  een gewone categorie en koos die met 80% zekerheid, ook wanneer de
  webopzoeking duidelijk maakte wat voor zaak het was (bijvoorbeeld een
  LED-verlichtingswinkel). Die optie is weg. Twijfel drukt het model voortaan
  uit in de zekerheid; bij minder dan 50% staat *Het model twijfelt* in de
  uitleg. Een voorstel blijft hoe dan ook op nazicht staan tot jij het
  bevestigt.
- **Nieuwe prompt, met een vaste werkwijze**: eerst bepalen wat voor zaak de
  tegenpartij is en wat er vermoedelijk betaald werd, dan pas het pad kiezen.
  Het veld `reden` staat daarom vooraan in het JSON-antwoord, zodat het model
  eerst redeneert en dan beslist. De prompt geeft ook houvast voor de
  zekerheid (0,9 = duidelijk, 0,6 = aannemelijk, 0,3 = gok).
- **Het model geeft naast het nummer ook de tekst van het gekozen pad.** Staat
  die tekst letterlijk in de lijst (op hoofdletters, spaties en het
  scheidingsteken na), dan gaat ze voor op het nummer. Bij een lijst van
  tachtig paden verspringt een klein model al eens een nummer.
- De **soort verrichting** (beschrijving) gaat nu mee in de vraag aan het model.

### Opgelost
- **Het model vulde een land in bij gewone aankopen** — het land waar de winkel
  gevestigd is ("NL" voor een Nederlandse webshop). Een land wordt nu alleen
  overgenomen als het gekozen pad onder een vakantie- of reiscategorie valt, en
  de prompt zegt uitdrukkelijk dat het land van een winkel niet telt.
- **Namen met opvulspaties** uit het bankbestand ("LedLoket               Denekamp")
  gingen zo naar het model en naar Brave Search. De spaties worden nu eerst
  samengevoegd; ook de voorgestelde handelaar wordt zo opgekuist.


## [0.21.0] — 2026-09-22

### Opgelost
- **Een onzekere regel bleef om nazicht vragen nadat je ze bewerkt had.** Een
  regel uit de historiek of de referentielijst die daar naar meer dan één
  categorie wees, krijgt het merkteken *onzeker*: ze deelt in, maar vraagt
  telkens om bevestiging. Bewerken liet dat merkteken staan, ook al had je de
  regel ondertussen zelf rechtgezet. Bewerken haalt het nu weg, net zoals
  *Ze klopt* dat al deed.
- **Transacties bleven op nazicht staan, met de oude uitleg "wijst naar meer
  dan één categorie", ook als de regel ondertussen zeker was.** Bij het
  herbekijken na een bewerking veranderde er niets zolang de categorie
  dezelfde bleef — ook de status en de uitleg niet. Nu gaat zo'n transactie
  naar *bevestigd*, met de uitleg van de regel zoals ze nu is.
- **Ze klopt bevestigde alleen de ene transactie** waarvan je vertrok. De andere
  transacties van dezelfde onzekere regel bleven op nazicht staan. Ze gaan nu
  mee, en de melding zegt hoeveel.
- **Eenmalig herstel voor regels die je al bewerkt had.** Bij het eerste bezoek
  aan het nazicht zoekt de toepassing in het logboek welke onzekere regels je
  vóór deze versie al bewerkt had, haalt het merkteken weg en beoordeelt de
  transacties die eraan hangen opnieuw. Dat gebeurt pas na het aanmelden,
  omdat het logboek versleuteld is. Alleen logregels van ná het aanmaken van
  een regel tellen: regels uit de historiek krijgen bij het opnieuw afleiden
  nieuwe nummers, en een oud nummer mag geen nieuwe regel goedkeuren.
- **Een transactie die haar categorie kwijtraakte** (omdat de regel erachter
  bewerkt, uitgezet of verwijderd werd) stond bij *Voorgesteld, nog te
  bevestigen*, met een lege voorstelkolom en een knop **Klopt** die niets had om
  te bevestigen. Ze staat nu bij *Zonder categorie*, met de reden erbij.

### Gewijzigd
- **Nazicht: de kolom Tegenpartij toont de naam van de tegenpartij met alle
  mededelingen eronder**, in plaats van de winkel die de motor voorstelde. Die
  winkel staat nu bij het voorstel. Ontbreekt de naam, dan valt ze terug op de
  begunstigde. Ook de tabel *Zonder categorie* toont het zo.
- **Nazicht: de kolom Zekerheid heet nu Bron** en zegt wat de bron is: *Vaste
  regel*, *Gelijkenis* of *AI-model*. Een percentage staat er alleen nog bij een
  gelijkenis of een AI-voorstel; bij een regel die om bevestiging vraagt staat
  *vraagt bevestiging*. Voorheen stond er bij zo'n regel enkel "60%", wat las als
  een gelijkenis.
- **Klopt deze regel?** toont nu de volledige regel: alle voorwaarden (ook de
  bijkomende), de bedragvork, inkomst of uitgave, de categorie met winkel en
  land, de prioriteit, de herkomst en de aanmaakdatum — plus de gegevens van de
  transactie zelf. Past de regel niet meer op de transactie, of wijst ze naar
  een andere categorie, dan staat dat er ook.
- Na **Klopt**, **Aanpassen** en **Naar de regel** kom je terug op het nazicht
  met je filters en sortering nog ingesteld.

### Toegevoegd
- **Nazicht: filterbalk** met zoeken (tegenpartij, mededeling, rekening,
  begunstigde, winkel, categorie), soort, rekening, **bron**, jaren, categorie,
  land en winkel — dezelfde als bij de transacties. De filters gelden voor
  beide tabellen.
- **Nazicht: sorteerbare kolommen** — datum, tegenpartij, voorstel, bron en
  bedrag.
- **Deze N voorstellen bevestigen**: staat er een filter aan, dan bevestigt de
  bulkknop alleen wat je op dat moment ziet.
- Naast de titel van elke nazichttabel staat hoeveel transacties erin zitten;
  de tabellen tonen er elk tot 300.


## [0.20.0] — 2026-09-21

### Gewijzigd
- **De webopzoeking bij het AI-model gebruikt nu de Brave Search API in
  plaats van een DuckDuckGo-zoekopdracht.** DuckDuckGo herkende de
  opzoekingen van de add-on als bot-verkeer en toonde een
  captcha-uitdaging ("selecteer alle vakjes met een eend") in plaats van
  zoekresultaten; die tekst kwam vervolgens als "context" bij het model
  terecht en hielp dus niet. Brave's API vraagt in plaats daarvan een
  sleutel, geen menselijke herkenningstest.
- Het veld **Zoekadres** bij *Instellingen › Automatisch indelen* is vervangen
  door **Brave API-sleutel** — een wachtwoordveld naar het voorbeeld van het
  SMTP-wachtwoord: leeg laten behoudt de bestaande sleutel. De sleutel staat,
  net als het SMTP-wachtwoord, versleuteld met de lokale sleutel in
  `lokaal.key` en dus niet in de gewone instellingentabel.
- Staat **Eerst Brave Search raadplegen** aan zonder dat er een sleutel is
  ingevuld, dan meldt het scherm dat expliciet in plaats van stilzwijgend
  niets op te zoeken.

### Verwijderd
- De instelling `ai_zoek_url` (en de standaardwaarde die naar DuckDuckGo
  wees) is vervallen.


## [0.19.0] — 2026-09-21

### Toegevoegd
- **De AI-bevraging wordt nu volledig in het logboek gezet**: de verzonden
  systeeminstructie en vraag (met de tegenpartij, het bedrag, de mededeling en
  de volledige lijst toegelaten categorieën), het ruwe antwoord van het model,
  en het resultaat. Te vinden bij **Instellingen › Logboek** onder de handeling
  **ai bevraagd**. Dat geldt ook wanneer het model geen bruikbaar antwoord gaf
  of te onzeker was — ook dan staat vastgelegd wat er verstuurd en
  teruggekregen werd.
- **Het model mag nu aangeven dat het twijfelt** in plaats van de minst
  slechte categorie te raden: naast de genummerde lijst met categorieën krijgt
  het een uitdrukkelijke optie "geen van deze past goed genoeg". Kiest het
  daarvoor, dan krijg je een duidelijke melding in plaats van een foute
  toewijzing met een hoog zekerheidspercentage.
- **Een AI-voorstel wordt meteen vastgelegd** op de transactie (status
  *nazicht*, methode *ai*), zowel via de knop in het nazicht als via de nieuwe
  knop in het bewerkscherm. Open je de transactie nadien, dan staat het
  voorstel er al in — voorheen bleven de categorieën leeg tot je opnieuw op
  **Vraag het model** klikte.

### Gewijzigd
- De detailkolom van het logboek toont meerdere regels nu ook echt als
  meerdere regels, in plaats van als één lange regel.


## [0.18.0] — 2026-09-21

### Toegevoegd
- **Het AI-model manueel bevragen kan nu ook vanuit het bewerkscherm**, niet
  meer alleen vanuit het nazicht. Bij een transactie zonder categorie staat
  onder **Indeling** de knop **Vraag het AI-model**. Het voorstel wordt meteen
  in de categoriekiezer gezet — hoofdcategorie, subcategorie en
  sub-subcategorie — en vult ook de handelaar en het land in als die nog leeg
  staan. Nakijken en op **Opslaan en bevestigen** klikken blijft nodig.
- Staat **Het model mag bevraagd worden** nog uit, dan toont het bewerkscherm
  nu een link naar **Instellingen › Automatisch indelen** om dat aan te zetten,
  net zoals het nazicht dat al deed.

### Gewijzigd
- De knop **Vraag het model** in het nazicht toont voortaan ook de toelichting
  van het model bij het voorstel, niet enkel het gekozen pad en de zekerheid.


## [0.17.0] — 2026-09-20

### Opgelost
- **Het kredietkaartscherm deed er seconden over.** Op een databank van
  twintigduizend transacties liep het scherm alles twee keer door en deed het
  daarbovenop een zoekopdracht per openstaande afrekening. Of een regel een
  kaartafrekening is, blijkt uit de beschrijving, en die staat versleuteld — er
  valt dus niet met SQL op voor te selecteren, en elke uitgave moest ontsleuteld
  worden. Bij elk bezoek opnieuw.
- **Dat oordeel wordt nu bewaard** in de kolom `kaartafrekening`. Alleen wat nog
  niet bekeken is, wordt ontsleuteld. De eerste keer duurt het dus één keer zo
  lang als vroeger, daarna niet meer. Nieuwe transacties komen als onbekend
  binnen en worden bij het volgende bezoek meegenomen; je hoeft niets te doen.
- **Eén doorloop in plaats van twee.** De lijst, de jaren en de tellingen komen
  nu uit dezelfde ronde. Het jaarfilter werkt op die lijst en niet met een
  tweede zoekopdracht.
- **Het zoeken naar tegenboekingen zit achter een knop.** Dat gebeurde bij elk
  bezoek voor elke openstaande afrekening, en dat was het duurste stuk. Er staat
  nu hoeveel afrekeningen op *nog te doen* staan, met *Tegenboekingen zoeken*
  ernaast.

Gemeten op 21 180 transacties met 180 afrekeningen:

| | eerst | nu |
|---|---|---|
| eerste bezoek | 1,6 s | 0,28 s |
| elk volgend bezoek | 1,6 s | 0,02 s |

### Gewijzigd
- **Schemaversie 8**: de kolom `kaartafrekening` op de transactietabel, met een
  index. Bestaande databanken krijgen ze bij het opstarten.
- De bovengrens op het aantal getoonde afrekeningen gaat van 400 naar 2000. Die
  grens was er om niet te veel te hoeven ontsleutelen; dat argument is weg.


## [0.16.1] — 2026-09-20

### Opgelost
- **Op het kredietkaartscherm gooide een wissel van jaar je statuskeuze weg.**
  Er stonden twee filterformulieren onder elkaar, elk met hun eigen velden; wie
  het jaar veranderde, verloor de status. Het is nu één balk met jaar, status,
  de aantallen en een knop om te wissen.
- Loopt de suggestie *automatisch afvinken* mis, dan haalt ze de pagina niet
  meer mee. Het is een voorstel bovenaan het overzicht, geen onderdeel ervan —
  een fout daarin mag het scherm niet onbereikbaar maken. De fout komt wel in
  het logboek van de add-on terecht.


## [0.16.0] — 2026-09-20

### Erbij
- **Een bevestigde regel blijft bevestigd, en dat is te zien.** *Ze klopt* legde
  de goedkeuring nergens vast: kwam je later terug, dan stond het scherm er weer
  precies zo bij en wist je niet meer of je die regel al had nagekeken. De regel
  onthoudt nu wanneer en door wie ze bevestigd is.
- **Een vinkje achter het merkje *regel* in de transactielijst.** Elke transactie
  die door een bevestigde regel is ingedeeld, krijgt er een; zweef erover en je
  ziet dat de regel nagekeken is. Zo herken je in één oogopslag wat je nog moet
  bekijken.
- **Kolom *Nagekeken* in de regeltabel**, met de datum en de gebruiker in de
  tooltip, en een filter ernaast: alle regels, alleen de bevestigde, of alleen
  wat nog niet nagekeken is. Sorteren op die kolom kan ook.
- **Bevestiging intrekken** op het oordeelscherm, voor wanneer je van gedacht
  verandert. De regel zelf blijft staan en deelt gewoon verder in; alleen het
  vinkje gaat weg.
- Bij een regel die je al bevestigd hebt, staat er *Ze klopt nog steeds* op de
  knop in plaats van *Ze klopt*.

### Gewijzigd
- **Schemaversie 7: `bevestigd_op` en `bevestigd_door` op de regeltabel.**
  Bestaande databanken krijgen de kolommen bij het opstarten; er is niets voor te
  doen. Je bestaande regels staan als nog niet nagekeken — dat klopt ook, want je
  hebt ze nog niet één voor één goedgekeurd.


## [0.15.0] — 2026-09-20

### Opgelost
- **Een regel verwijderen gaf een 404, terwijl ze wel verdwenen was.** Het
  terugadres kwam uit `request.full_path`, en dat is het pad zoals de toepassing
  het ziet — zonder het voorvoegsel dat de ingress van Home Assistant ervoor
  zet. De omleiding wees daardoor buiten de add-on. Het adres wordt nu met
  `url_for` opgebouwd en door `veilig_terug` gehaald, net als elders.
- **De kolom *Treffers* stond altijd op nul.** Ze werd uit een kolom in de
  regeltabel gelezen die nergens werd opgeteld. Sinds een transactie onthoudt
  wélke regel haar indeelde, valt het echte aantal gewoon te tellen; dat gebeurt
  nu, en het getal is doorklikbaar naar die transacties.
- **Een rekeningnummer alleen deelt niets meer in.** Betaalverwerkers innen voor
  tientallen handelaars vanaf één IBAN. Dat nummer wees dan naar evenveel
  categorieën en leverde enkel een regel op die om nazicht bleef vragen — en die
  was nergens terug te vinden, want zoeken op de winkelnaam gaf niets. Het IBAN
  telt nu alleen mee samen met de beschrijving, als gecombineerde regel.

### Erbij
- **Vanuit een transactie doorklikken naar de regel die haar indeelde.** Het
  merkje *regel* in de transactielijst is een link geworden; in het nazicht staat
  er een knop *Naar de regel* bij.
- **Oordelen over die regel, in één handeling.** *Ze klopt* bevestigt de
  transactie, en een regel die om nazicht vroeg doet dat voortaan niet meer.
  *Ze klopt niet* geeft de keuze: de regel bewerken, de regel verwijderen, of
  alleen deze ene transactie aanpassen. Verwijderen volgt dezelfde weg als
  elders: wat eraan hing wordt opnieuw beoordeeld.
- **Filter *van één regel*** in de transactielijst, zodat je ziet wat een regel
  in de praktijk doet. Het getal in de kolom *Treffers* brengt je er rechtstreeks
  naartoe.

### Ter verduidelijking
- Een transactie met bron *regel* die tóch op nazicht staat met 60% zekerheid is
  geen tegenspraak. Dat is een regel die uit je historiek is afgeleid en daar
  naar meer dan één categorie wees: ze deelt wel in, maar vraagt telkens om
  bevestiging. Wat ontbrak was de weg ernaartoe — die is er nu.


## [0.14.0] — 2026-09-20

### Opgelost
- **Regels uit je historiek wegschrijven gaf geen enkel teken van leven.** Bij
  duizenden regels bleef de browser minutenlang op een lege bladzijde staan,
  zonder dat je kon zien of er iets gebeurde. Dat werk loopt nu in de
  achtergrond, met dezelfde voortgangsmeter als een bestandsinvoer: fase, balk,
  teller en verstreken tijd.
- Het herindelen dat erachteraan komt zit in dezelfde meter. De balk loopt dus
  door twee fasen — *Regels wegschrijven* en *Transacties opnieuw beoordelen* —
  en je weet van begin tot eind waar het zit.
- Sluit je het venster, dan loopt het werk gewoon door; er wordt niets
  afgebroken.

### Erbij
- **Het bereik van de herindeling kies je nu ter plekke**, bij het knopje
  *Daarna meteen opnieuw indelen*: alleen wat nog geen categorie heeft, of alles
  wat nog niet bevestigd is. Voordien ging die stap altijd naar het standaard
  bereik zonder dat je erbij kwam.
- Achteraf staat er één zin met alles erin: hoeveel regels, hoeveel met een
  bedragvork, hoeveel die om bevestiging blijven vragen, en hoeveel transacties
  er daarna opnieuw zijn ingedeeld.

### Technisch
- De herindeling staat nu in `app/herindeling.py` in plaats van in de route.
  Ze moest aanroepbaar worden vanuit een aparte draad — met een eigen verbinding
  en zonder aanvraagcontext — en dat gaat niet vanuit een routefunctie. De knop
  op het nazichtscherm gebruikt dezelfde functie, dus beide wegen doen
  gegarandeerd hetzelfde.
- De voortgangsmeter meldt om de honderdste stap, berekend uit het totaal. Een
  vaste afstand van honderd liet de balk bij een korte lijst op nul staan en
  werkte bij een lange lijst honderd keer per seconde bij.
- De JavaScript van de meter was op de bestandsinvoer geschreven: ze telde altijd
  *rijen* en sprak van *inlezen*. De eenheid en de foutzin komen nu uit het
  scherm zelf, en de samenvatting mag de server meegeven.


## [0.13.2] — 2026-09-20

### Opgelost
- **Een categorieënbestand met alleen de boomstructuur kwam een niveau verschoven
  binnen.** De kolommen werden op hun plaats gelezen, niet op hun naam, en de
  eerste kolom werd altijd als sleutel opgevat. Bij een bestand met drie kolommen
  — Hoofdcategorie, Categorie, Subcategorie — schoof daardoor alles op: de
  categorie werd hoofdcategorie, de subcategorie werd categorie, en de echte
  hoofdcategorieën verdwenen. Het resultaat was een boom waarin *Auto* en
  *Transport* niet meer bij elkaar stonden.
- **De kolommen worden nu op hun kopregel herkend**, dus hun volgorde en hun
  aantal doen er niet meer toe. Herkend worden Sleutel (ook Omschrijving,
  Beschrijving, Referentie, Mededeling, Tegenpartij), Hoofdcategorie, Categorie,
  Subcategorie en Winkel (ook Handelaar, Zaak, Land). Bij het zoeken wint het
  langst passende woord, zodat een kolom *Subcategorie* niet als *Categorie*
  gelezen wordt.
- Staat er geen bruikbare kopregel, dan geldt de oude volgorde. Bestanden zonder
  kop blijven dus werken zoals voordien.
- Een rij telt nu mee zodra ze een sleutel **of** een hoofdcategorie heeft. Met
  enkel de oude voorwaarde zou een bestand zonder sleutelkolom volledig
  weggefilterd worden.

### Gewijzigd
- **Het voorbeeldscherm past zich aan het bestand aan.** Zit er geen kolom met
  beschrijvingen in, dan valt er geen enkele regel af te leiden; de keuze tussen
  *volledige lijst* en *alleen de boomstructuur* verschijnt dan niet, en er staat
  bij wat je zou moeten toevoegen om er wel regels uit te halen.
- De analyse telde het aantal afgeleide regels gelijk aan het aantal bruikbare
  rijen, ook wanneer er geen sleutels waren. Bij zo'n bestand staat er nu nul.


## [0.13.1] — 2026-09-20

### Opgelost
- **De handleiding was in de add-on niet te openen** — "Het bestand
  docs/HANDLEIDING.md hoort naast de toepassing te staan". Ze stond aan de wortel
  van de repository, buiten het bouwpad van Docker. Dat bouwpad is de add-on-map
  zelf, en `COPY` kan niet buiten dat pad kijken, dus het bestand zat nooit in
  het image. In een uitgecheckte repository viel dat niet op, want daar staat het
  er wel.
- De handleiding staat nu in `transactie_manager/docs/HANDLEIDING.md`, binnen dat
  bouwpad, en de `Dockerfile` neemt de map mee. Het blijft één bestand: wat je in
  de repository leest en wat de toepassing toont, kan niet uiteenlopen.
- De module kijkt op beide plaatsen, de nieuwe eerst. Een oudere uitgecheckte
  repository blijft dus gewoon werken.
- De verwijzingen in `README.md`, `DOCS.md` en `scripts/versie.py` wijzen mee naar
  de nieuwe plek, zodat het versienummer bovenaan de handleiding meebumpt.


## [0.13.0] — 2026-09-20

### Erbij
- **Kaartafrekeningen hebben nu een status: *nog te doen*, *uitgesplitst* of
  *tegengeboekt*.** Een afrekening die is teruggestort of rechtgezet, hoeft niet
  uitgesplitst te worden in aankopen: ze valt weg tegen haar tegenboeking. Wijs
  die aan en de afrekening verdwijnt uit je werklijst.
- **Automatisch afvinken.** Staat er boven het overzicht hoeveel open
  afrekeningen een eenduidige tegenboeking hebben, met een knop om ze in één
  keer te koppelen. Dat gebeurt alleen wanneer er précies één kandidaat is:
  zijn er meerdere, dan is het een keuze en geen vaststelling, en die blijft aan
  jou.
- Een tegenboeking is een boeking op dezelfde rekening, met hetzelfde bedrag maar
  het tegengestelde teken, binnen tien dagen, die nog nergens aan hangt. Dat
  venster is bewust krap: ruimer maken vergroot de kans dat een toevallig gelijk
  bedrag wordt aangezien voor een tegenboeking.
- **Met de hand aanwijzen of loskoppelen** kan via een eigen scherm per
  afrekening, dat de kandidaten toont met datum, bedrag en omschrijving.
- **Filteren op status** boven het overzicht, met de aantallen per status erbij.
  *Nog te doen* is precies wat je categorie Kredietkaart nog laat oplopen.

### Gewijzigd
- **Schemaversie 6: een transactie kan naar haar tegenboeking wijzen**
  (`tegenboeking_tx_id`). Bestaande databanken krijgen de kolom bij het
  opstarten; er is niets voor te doen.
- Aan de cijfers verandert niets. Een uitgesplitste afrekening telde al niet
  meer mee, en een tegengeboekte valt weg tegen haar tegenboeking — samen komen
  ze op nul uit. De status zegt dus wat er nog te doen is, niet wat er wordt
  geteld.


## [0.12.0] — 2026-09-20

### Erbij
- **Opnieuw beginnen** onder Instellingen. Drie keuzes: alleen de categorieën en
  regels (je transacties blijven, zonder categorie), alleen de transacties (je
  boom en regels blijven klaarstaan), of alles. Bij *alles* kan je er je
  rekeningen bij nemen. Gebruikers, wachtwoorden en instellingen blijven altijd
  staan — je hoeft dus niet opnieuw te installeren en niet opnieuw aan te melden.
- Twee sloten voor het wissen: een bevestigingsvenster én het woord *WISSEN* dat
  je moet intypen. Een vinkje alleen is te makkelijk aangeklikt. Vooraf wordt er
  een kopie van de databank gelegd, en die wordt nooit automatisch opgeruimd.
- **De handleiding staat nu in de toepassing zelf**, met een inhoudstafel die
  meeschuift. Ze wordt gelezen uit `docs/HANDLEIDING.md`, hetzelfde bestand als
  in de repository, dus er is maar één versie om bij te houden.
- Er zit geen markdownbibliotheek achter maar een eigen weergave van een kleine
  honderd regels, precies passend op de opmaak die de handleiding gebruikt. Dat
  scheelt een pakket om te bouwen en te onderhouden in de add-on, voor een
  bestand waarvan wij elke regel zelf typen. Wat er niet in staat, valt terug op
  gewone tekst.

### Gewijzigd
- **De zijbalk is korter.** De elf instellingenschermen stonden er allemaal los
  in; nu is er één regel *Instellingen*, en binnen dat gedeelte kies je het
  scherm via tabbladen bovenaan. De zijbalk gaat van zeventien naar tien punten
  en houdt over wat je dagelijks doet. *Handleiding* staat er als nieuwe regel
  bij.
- De bestaande adressen veranderen niet: elk instellingenscherm blijft op
  hetzelfde pad staan, en een bladwijzer blijft dus werken.


## [0.11.0] — 2026-09-20

### Opgelost
- **Een referentielijst integraal vervangen wiste je hele indeling, ook het
  handwerk.** Koos je daarna niet voor herindelen, dan stond alles zonder
  categorie. Regels opnieuw toepassen haalt dat niet terug: wat je met de hand
  had ingedeeld, of wat via een gelijkenis binnenkwam, is dan niet te
  reconstrueren, en de bron van de toewijzing is hoe dan ook weg.
- **Herindelen raakt voortaan standaard alleen de transacties zonder
  categorie.** Dat is het veilige bereik: wat al ergens in zit, is daar meestal
  met opzet beland. Wie écht alles wil laten herzien, kiest dat uitdrukkelijk.
  Het nazichtscherm biedt beide, met uitleg erbij.

### Erbij
- **Kopieën van de databank, met een terugzetknop.** Er komt automatisch een
  kopie vóór elke ingreep die je indeling in één keer kan herschrijven: een
  referentielijst, een historiek of een ander bestand inlezen, regels uit je
  historiek afleiden, een herindeling, en alle regels opnieuw toepassen.
  Daarnaast één per dag bij de eerste aanmelding. Onder *Instellingen ›
  Kopieën* zet je er een terug, maak je er zelf een, of gooi je er een weg.
- Terugzetten gaat via de backup-API van SQLite en niet via een bestandskopie,
  zodat verbindingen die op dat moment openstaan de nieuwe inhoud zien. Van de
  huidige toestand wordt eerst een kopie gelegd, dus ook het terugzetten zelf is
  ongedaan te maken.
- De laatste 15 automatische kopieën blijven staan. Wat je zelf maakt en wat van
  vlak vóór een terugzetting komt, wordt nooit opgeruimd.
- **Bij de referentielijst kan je kiezen wat je overneemt.** *De volledige
  referentielijst* zoals voordien: categorieën én de koppeling met de
  beschrijvingen, waaruit regels worden afgeleid. Of *alleen de boomstructuur*:
  enkel de categorieën en hun onderverdeling, zonder regels, zodat je manier van
  indelen je eigen werk blijft.
- Na het inlezen van een referentielijst kan je nu ook kiezen om alleen de
  transacties zonder categorie te laten herindelen — precies het geval waarvoor
  deze versie er is.

### Waarschuwingen
- **Bij een referentielijst op een niet-lege databank** staat bovenaan wat er nu
  in staat: hoeveel categorieën, regels en transacties, hoeveel daarvan een
  categorie hebben en hoeveel je met de hand hebt ingedeeld. Bij *integraal
  vervangen* staat er expliciet bij dat ook dat handwerk sneuvelt.
- **Bij het herindelen** staat er dat de bron van de toewijzing verloren gaat:
  een transactie die nu *met de hand* zegt, kan daarna *gelijkenis* of *vaste
  regel* zeggen. De knop vraagt een bevestiging, en na een referentielijst komt
  er een apart scherm dat het nog eens uitlegt voor je doorgaat.
- **Bij het inlezen van een historiek met indeling** staat er dat dit bestand je
  categorieën opbouwt: elke categorie die erin voorkomt en nog niet bestaat,
  wordt aangemaakt. Lees je nadien alsnog een referentielijst in met *integraal
  vervangen*, dan gaat dat werk weer weg.


## [0.10.0] — 2026-09-19

### Erbij
- **Regels kunnen velden combineren.** Onder *En ook* zet je bijkomende
  voorwaarden; ze moeten dan allemaal kloppen. Zo krijg je bijvoorbeeld "naam
  bevat TOTAL én mededeling bevat CARWASH" naar *Autowas*, en met een tweede
  regel "naam bevat TOTAL én mededeling bevat **niet** CARWASH" naar *Tanken*.
  Daarvoor moest je voordien uitwijken naar een reguliere expressie, en dan nog
  alleen binnen één veld.
- **Nieuwe vergelijking *bevat niet*.** Alleen bruikbaar als bijkomende
  voorwaarde: een regel waarvan de énige voorwaarde "bevat niet" is, zou op
  zowat elke transactie passen.
- Er staan altijd drie lege rijen klaar. Een lege rij wordt overgeslagen, en een
  bestaande voorwaarde wis je door haar waarde leeg te maken.
- **Filter *Voorwaarden*** op het regelscherm: alle regels, alleen de
  gecombineerde, of alleen die op één veld.
- Zoeken doorzoekt ook de bijkomende waarden, en het filter op *Kijkt naar*
  vindt een regel zodra één van haar voorwaarden naar dat veld kijkt.

### Gewijzigd
- **Schemaversie 5: een nieuwe tabel `regel_voorwaarden`.** De eerste voorwaarde
  blijft in de regeltabel zelf staan, wat erbij komt staat in die tabel. Zo
  verandert er niets aan bestaande regels en kost een gecombineerde regel niets
  aan de rest. Bestaande databanken krijgen de tabel bij het opstarten; er is
  niets voor te doen.
- De regeltabel toont alle voorwaarden onder elkaar, met *en* ervoor.
- Een gecombineerde regel gaat niet door het snelle woordenboek van de motor,
  want daar wordt maar één veld opgezocht. Ze wordt volledig nagegaan, net als
  regels met een bedragvork. Aan de volgorde waarin regels gekozen worden,
  verandert niets: prioriteit blijft beslissen.


## [0.9.10] — 2026-09-19

### Erbij
- **Filter *Bedragvork* op het regelscherm.** Drie keuzes: alle regels, alleen
  die met een bedragvork, alleen die zonder. Een regel telt als "met vork" zodra
  ze een onder- óf een bovengrens heeft; het paar *tot 10* en *vanaf 10* is juist
  de gewone vorm van zo'n vork.

### Gewijzigd
- *Vangt bedrag* toonde de regels zonder bedragvork mee. Dat is op zich juist —
  die vangen elk bedrag — maar het was niet wat je wil zien als je je vorken
  nakijkt. De twee filters staan nu naast elkaar en zijn te combineren: *vangt
  7,50* geeft vijf regels, met *alleen met bedragvork* erbij blijven de twee over
  die dat bedrag werkelijk verdelen. De tekst onder de filterbalk legt dat uit.


## [0.9.9] — 2026-09-19

### Opgelost
- **De melding na een herindeling klopte niet.** Ze telde elke transactie
  waarvoor de motor íets vond, ook als dat precies was wat er al stond. Een
  tweede herindeling meldde dan opnieuw hetzelfde aantal, terwijl er niets
  gebeurd was. Alleen echte wijzigingen tellen nu mee, en staat er niets bij te
  sturen, dan zegt ze dat ook.

### Gewijzigd
- **De melding splitst uit per stap: vaste regel, gelijkenis, AI-model.** Dat is
  wat de verwarring veroorzaakte. "1300 transacties opnieuw ingedeeld" gaat over
  alle drie de stappen samen, terwijl de filter *Vaste regel* alleen de eerste
  toont. Het leeuwendeel komt doorgaans van de gelijkenis met je historiek, ook
  wanneer die historiek zelf uit je regels is opgebouwd. Nu staat er bijvoorbeeld
  "1281 via gelijkenis, 19 via vaste regel".
- **Na een herindeling land je op de lijst met precies die transacties**, in
  plaats van op het nazichtscherm. Voordien was er geen enkele manier om te zien
  welke rijen er aangepast waren.

### Erbij
- **Filter *aangepast sinds*.** Toont de transacties die sinds een bepaald
  tijdstip gewijzigd zijn; de herindeling zet hem op het moment waarop ze begon.
  Hij reist mee wanneer je er andere filters bij kiest, en het kruisje op het
  merkje laat hem los. Let op: hij kijkt naar het tijdstip van wijzigen, tot op
  de seconde — heb je in diezelfde seconde nog iets anders aangepast, dan staat
  dat er ook bij.


## [0.9.8] — 2026-09-19

### Erbij
- **Knop *Alle regels opnieuw toepassen*, boven de regeltabel.** Elke transactie
  die door een regel is ingedeeld, wordt opnieuw beoordeeld met de regels zoals
  ze nu staan, en daarna worden de regels nog losgelaten op alles wat geen
  categorie heeft.
- Nodig wanneer je prioriteiten hebt verschoven of meerdere regels na elkaar
  hebt aangepast. Het onderhoud per regel kijkt alleen naar wat aan díe regel
  hing: een transactie die aan een andere regel hangt blijft daar hangen, ook
  als je aangepaste regel nu voorgaat. Deze knop zet dat in één keer recht.
- De ingreep loopt over je hele boekhouding en staat daarom apart, achter een
  bevestiging die zegt wat er gaat gebeuren. Wat je zelf hebt ingedeeld, en wat
  de fuzzy stap of het AI-model heeft toegewezen, blijft ook hier staan.

### Gewijzigd
- **Een herbeoordeling laat een transactie met rust wanneer de regel die erop
  past nog naar dezelfde categorie wijst.** Voordien werd ze dan toch
  weggeschreven en als "overgenomen" geteld, wat bij de nieuwe knop op elke
  transactie zou neerkomen. Wel wordt in dat geval alsnog vastgelegd wélke regel
  het is, voor rijen van vóór schemaversie 4 waar dat nog nergens stond. De knop
  vult die dus gaandeweg aan.
- De melding achteraf telt nu drie dingen apart: hoeveel er op nazicht komen,
  hoeveel er een andere categorie kregen, en hoeveel er alsnog een categorie
  bij kregen — met erachter hoeveel er bleven staan zoals ze stonden.

### Technisch
- `herbekijk()` geeft een `Uitkomst` terug in plaats van een tweetal, zodat er
  ruimte is voor die vier tellingen zonder bij elke uitbreiding de aanroepers
  aan te passen.
- `pas_toe()` werkt nu ook zonder `regel_id`, en past dan alle actieve regels
  samen toe op wat geen categorie heeft.


## [0.9.7] — 2026-09-19

### Gewijzigd
- **Transacties waarvan de categorie wegvalt, komen nu op *nazicht* te staan in
  plaats van bij *Zonder categorie*.** Ze duiken dus op in het nazichtscherm,
  waar je ze meteen kan afhandelen, in plaats van stilletjes ergens onderaan een
  lijst te belanden. Dat geldt voor alle drie de gevallen: een regel
  verwijderen, uitzetten of bewerken.

### Erbij
- **Een regel bewerken.** Naast elke regel staat nu *Bewerken*. Het scherm is
  hetzelfde als bij toevoegen, met de huidige waarden ingevuld, en er is een
  keuze *Allebei* bij Soort die voordien alleen via de databank te zetten was.
- Bewaren volgt exact dezelfde weg als verwijderen: eerst wordt opgezocht welke
  transacties aan de oude regel hingen, dan wordt de regel aangepast, dan worden
  net die transacties opnieuw beoordeeld met de regels zoals ze daarna zijn.
  Past de aangepaste regel er nog op, dan blijft alles staan. Past hij er niet
  meer op, dan neemt een andere regel het over of komt de transactie op nazicht.
  Daarna wordt de nieuwe regel nog losgelaten op wat geen categorie heeft, zodat
  een regel die breder wordt ook meteen aanslaat.
- **De regeltabel is te filteren.** Zoeken op naam, waarde, categorie of winkel;
  filteren op hoofdcategorie, op het veld waar de regel naar kijkt, en op actief
  of uitgezet. Daarbij hoort *Vangt bedrag*: vul een bedrag in en je ziet welke
  regels dat bedrag zouden vangen — handig bij bedragvorken, waar het net de
  vraag is welke regel een aankoop van 12,50 te pakken krijgt.
- **De kolommen zijn sorteerbaar.** Prioriteit, naam, voorwaarde, bedrag,
  indeling, treffers en actief; klikken op dezelfde kolom draait de richting om.
  Onder de filter staat hoeveel regels er getoond worden van het totaal.
- De kolom *Treffers* staat er nu bij, zodat je ziet welke regels werk doen en
  welke nooit aanslaan.

### Bevestigd
- *Uitzetten* heeft dezelfde uitwerking op de transacties als verwijderen. Dat
  was al zo sinds 0.9.6; het staat nu ook als zodanig in de code, want beide
  paden lopen door dezelfde twee stappen in plaats van door een eigen variant.

### Technisch
- `regelonderhoud` is opgesplitst in `hangende_transacties()` en `herbekijk()`.
  De eerste vraagt, zolang de oude regel nog geldt, wat eraan hing; de tweede
  beoordeelt net die transacties opnieuw. Verwijderen, uitzetten en bewerken
  gebruiken alle drie dezelfde twee stappen — één weg in plaats van drie.


## [0.9.6] — 2026-09-19

### Opgelost
- **Een regel verwijderen of uitzetten liet de categorie staan.** De transacties
  die de regel had ingedeeld, bleven in hun categorie hangen aan een regel die
  niet meer bestond. Ze lieten zich ook niet meer rechtzetten: een regel zet
  `status='bevestigd'`, en *Opnieuw indelen* raakt alleen wat nog niet bevestigd
  is. Elke transactie met de hand terugzetten was de enige uitweg.
- Verwijder of zet je nu een regel uit, dan laten die transacties hun categorie
  los. Past er nog een andere regel op, dan neemt die het over; is er geen, dan
  komen ze bij *Zonder categorie* te staan. Na afloop staat er hoeveel het er
  waren en hoeveel er overgenomen zijn.
- **Zet je een regel weer aan, dan pakt hij op wat nog geen categorie heeft.**
  De tegenhanger van het uitzetten, zodat je een regel tijdelijk kan uitzetten
  zonder je indeling kwijt te spelen.

### Blijft staan
- Wat je zelf hebt ingedeeld. Een handmatige toewijzing verbreekt de band met de
  regel, zodat een latere wijziging aan die regel jouw keuze niet overschrijft.
- Wat de fuzzy stap of het AI-model heeft toegewezen. Alleen een toewijzing die
  van déze regel kwam, gaat weg.
- Handelaar en land. Die staan los van de indeling, en een regel is meestal niet
  de enige plek waar ze vandaan komen.

### Gewijzigd
- **Schemaversie 4: een transactie onthoudt nu wélke regel haar indeelde.**
  Voordien stond er alleen `methode='regel'`, zonder te zeggen welke. Bestaande
  databanken krijgen de kolom er bij het opstarten vanzelf bij; er is niets voor
  te doen.
- Transacties van vóór deze versie hebben die kolom niet ingevuld. Ze worden
  herkend door de vraag om te draaien: zou déze regel deze transactie ingedeeld
  hebben, gegeven de regels zoals ze stonden? Is een andere regel voorgegaan,
  dan hing ze aan die andere en blijft ze met rust.
- De regelstap van de motor staat nu in een eigen klasse, `Regelboek`, die het
  regelonderhoud deelt met de motor. Dezelfde vraag hoort maar één keer
  beantwoord te worden, anders lopen de twee vroeg of laat uit elkaar. Aan de
  volgorde waarin regels gekozen worden, verandert niets.
- Het regelscherm zegt nu vooraf wat verwijderen met je transacties doet.


## [0.9.5] — 2026-09-17

### Opgelost
- **Boekingen met dezelfde bankreferentie maar een ander bedrag verdwenen bij
  het inlezen.** De vingerafdruk op de referentie bevatte enkel het teken van
  het bedrag, niet het bedrag zelf. Twee afschrijvingen onder één referentie —
  bijvoorbeeld een deelbetaling van 370,20 en een saldo van 140,60 op dezelfde
  kaartafrekening — kregen daardoor exact dezelfde afdruk, waarna de tweede voor
  een dubbel werd aangezien. De aanname erachter, dat een bankreferentie uniek
  is per verrichting, gaat bij Argenta niet altijd op. Het volledige bedrag zit
  nu in de afdruk.
- **Erger dan overslaan alleen: met *Bestaande transacties aanvullen* aangevinkt
  kon de tweede boeking lege velden van de eerste invullen met haar eigen
  gegevens.** Een verrichting die er niet bijkwam, vervuilde zo stilletjes een
  andere. Dat kan nu niet meer.
- De melding op het nazichtscherm klopte evenmin: ze wees naar een rij met een
  ander bedrag. Een rij geldt nu pas als dubbel binnen het bestand wanneer
  referentie én bedrag allebei overeenkomen, en de melding zegt dat er ook bij.

### Terug te halen
- Bied de afschriften waarin dit speelde opnieuw aan. De ontbrekende lijnen
  worden toegevoegd; wat er al staat blijft ongemoeid. Rijen die al onder de
  oudere afdrukken in de databank staan, worden nog steeds teruggevonden — met
  een controle op het bedrag erbij — dus er komt niets dubbel bij en een
  migratie van de databank is niet nodig.
- Wil je weten of het jou raakte: op het scherm *Bekijk wat er niet is
  toegevoegd* staan de betrokken rijen onder de reden *komt twee keer voor in
  dit bestand*. Staan daar rijen met verschillende bedragen naast elkaar, dan
  waren die ten onrechte overgeslagen.

### Blijft zo
- Dezelfde referentie mét hetzelfde bedrag twee keer in één bestand telt nog
  altijd als één verrichting. Hoort dat in jouw geval wel twee keer te staan,
  voeg de rij dan toe via *Toch toevoegen* op het nazichtscherm.


## [0.9.4] — 2026-09-17

### Gewijzigd
- **Uitgaven staan nu als negatief getal, inkomsten als positief**, overal en
  altijd. Voordien werd het teken omgedraaid zodra je één richting koos,
  waardoor een kolom plus en min door elkaar toonde en het jaartotaal niet meer
  te volgen was.
- **De keuze bij *Soort* filtert weer de rijen.** In 0.9.1 werd er per categorie
  gesaldeerd, met als gevolg dat een categorie waar per saldo geld binnenkwam
  volledig uit het uitgavenoverzicht verdween. Bij *Loon* met onkosten die later
  terugbetaald worden, zag je dan niets staan terwijl er wel degelijk uitgaven
  op geboekt zijn. Die onkosten staan er nu gewoon, als negatief bedrag.
- Wil je het saldo van een categorie zien, kies dan *Alle* bij Soort. Loon met
  €3.000 binnen en €180 onkosten geeft dan €2.820; bij *Uitgaven* staat er
  -€180 en bij *Inkomsten* €3.000.
- **De staafgrafiek tekent nu rond een nullijn.** Uitgaven gaan eronder,
  inkomsten erboven, en onder elke staaf staat het saldo van die periode.
- De taart toont de grootte van elk deel. Gaan er onderdelen de andere kant op
  dan de rest, dan blijven die weg en staat erboven hoeveel dat er zijn: plus en
  min door elkaar laat zich niet als verhouding tekenen.


## [0.9.3] — 2026-09-17

### Gewijzigd
- **`build.yaml` is weg; het basisimage staat nu in de Dockerfile.** Home
  Assistant heeft dat bestand afgevoerd en meldde dat in het logboek. Omdat de
  basisimages tegenwoordig als multi-platform manifest gepubliceerd worden,
  volstaat één `FROM`-regel voor alle architecturen; Docker kiest zelf de juiste
  variant. De labels uit `build.yaml` staan nu als `LABEL` in de Dockerfile.
- **`armv7` is uit de lijst met architecturen gehaald.** Home Assistant heeft de
  32-bits varianten afgevoerd en waarschuwde daarvoor. Een Raspberry Pi 3 of 4
  draait tegenwoordig een 64-bits systeem en valt onder `aarch64`. De add-on
  wordt nog gebouwd voor `aarch64` en `amd64`.

Allebei de waarschuwingen uit het logboek van de Supervisor zijn daarmee weg.
Aan de toepassing zelf verandert niets.


## [0.9.2] — 2026-09-17

### Gewijzigd
- **Bedragen staan nu als €1.200,50**, met het muntteken vooraan en een punt als
  duizendtalscheiding. In de jaartabel, waar op hele euro's afgerond wordt, geeft
  dat €1.200.
- **De keuzelijsten in de filters staan alfabetisch**: hoofd-, sub- en
  sub-subcategorieën, winkels, landen en rekeningen. Winkels stonden op aantal
  gesorteerd, wat onbruikbaar is zodra het er honderden zijn. De boom op het
  scherm *Categorieën* houdt wel de volgorde die je daar zelf instelt, want daar
  staan de knoppen om te schikken.
- Waarden die "niets ingevuld" betekenen, zoals een winkel die letterlijk `-`
  heet, staan niet langer in de keuzelijsten.
- *Wissen* heet nu *Alles wissen*, om het verschil met de losse kruisjes
  duidelijk te maken.

### Toegevoegd
- **Land kan nu ook uitgesloten worden**, naast categorie en winkel.
- **Elke actieve keuze staat onderaan de filterbalk met een kruisje** om net die
  ene weg te halen. Voordien kon je alleen alles tegelijk wissen.

### Opgelost
- **De grafiekbladzijde sprong naar boven** zodra je een filter van de onderste
  grafiek aanpaste. Elke filterbalk draagt nu een anker mee, zodat je blijft
  staan waar je bezig was.


## [0.9.1] — 2026-09-17

### Opgelost
- **Terugbetalingen en tegenboekingen gingen niet van de uitgave af.** In de
  jaartabel en de grafieken werkte de keuze *Uitgaven* als een filter op de
  rijen: alles wat de andere kant opging verdween. Een kaartafrekening van
  5 646,24 bleef dan voor het volle bedrag als uitgave staan terwijl de
  tegenboeking van +5 646,24 werd weggelaten. Hetzelfde gold voor een
  terugbetaling binnen een uitgavencategorie.
- In de overzichten telt nu het saldo per categorie. Vraag je om uitgaven, dan
  wordt er over alle rijen van die categorie opgeteld, met teken, en pas daarna
  omgekeerd voor de weergave. Honderd euro boodschappen met dertig euro terug
  geeft zeventig. Een afrekening die volledig teruggedraaid is, komt op nul uit
  en verdwijnt uit het overzicht.
- Categorieën die per saldo de andere kant opgaan blijven weg bij een gekozen
  richting. Een categorie die netto geld opleverde hoort niet tussen de uitgaven.
- Een categorie werd ook niet meer weggelaten op grond van haar soort. Stond er
  een inkomst in een uitgavencategorie, dan verdween die eerder uit beeld zonder
  dat je het merkte.
- In de transactielijst blijft de richting gewoon een filter op de rijen: vraag
  je daar om uitgaven, dan wil je geen inkomsten in de lijst zien.


## [0.9.0] — 2026-09-17

### Toegevoegd
- **Elke rij die niet als nieuwe transactie binnenkomt, wordt nu met reden
  vastgelegd.** Voordien zag je alleen het aantal onleesbare rijen; waar de rest
  gebleven was, viel niet na te gaan. De redenen zijn: stond al in de databank,
  komt twee keer voor in dit bestand, datum of bedrag onleesbaar, of bestond al
  en is aangevuld.
- **Een scherm om die rijen na te kijken.** Per rij zie je de reden, de inhoud
  zoals ze in het bestand stond, en waar van toepassing een knop naar de
  bestaande transactie. Te openen vanaf het resultaat van een invoer en vanaf
  *Bestand inlezen › Eerdere invoer*.
- **Je kan een overgeslagen rij alsnog toevoegen.** De dubbelcontrole wordt dan
  overgeslagen, want jij weet beter dan de toepassing of het om dezelfde
  verrichting gaat. Rijen afvinken als nagekeken kan per stuk of in één keer.
- Het resultaat van een invoer toont nu of de telling sluit: hoeveel van de
  rijen er verklaard zijn. Blijft er iets over, dan zegt het scherm dat dat niet
  hoort.

### Gewijzigd
- Bij een onleesbare rij staat er nu bij of het de datum of het bedrag was.

### Bekend
- Er worden maximaal drieduizend rijen per invoer bewaard om na te kijken. Bij
  meer wordt dat gemeld.


## [0.8.4] — 2026-09-16

### Opgelost
- **Herhaalde identieke betalingen verdwenen bij bestanden zonder
  referentiekolom.** Drie keer hetzelfde bedrag bij dezelfde tegenpartij op
  dezelfde dag — drie rondjes aan een drankstand — kregen dezelfde vingerafdruk,
  waarna er maar één van overbleef. Bij het inlezen wordt nu geteld de
  hoeveelste keer een rij in hetzelfde bestand voorkomt, en dat volgnummer zit
  in de vingerafdruk. Bied je hetzelfde bestand opnieuw aan, dan telt het
  opnieuw op dezelfde manier, dus er komen nog steeds geen dubbels bij.
- Bestanden mét een referentiekolom, zoals de uitvoer van Argenta, raakten dit
  niet: die referentie is uniek per verrichting en wordt ongewijzigd gebruikt.
- De terugval op rekening, datum, bedrag en tegenrekening slaat niet meer toe
  bij een herhaalde lijn. Bij drie identieke betalingen zegt die vergelijking
  niets, en ze zou er alsnog twee kunnen wegnemen.
- Ook bij het inlezen van een kredietkaartuittreksel worden herhaalde identieke
  aankopen nu als aparte aankopen bewaard.

### Terug te halen
- Bied de bestanden zonder referentiekolom opnieuw aan. De ontbrekende herhaalde
  lijnen worden toegevoegd; wat er al staat blijft ongemoeid. Getest op een
  databank waarin er één van de vier stond: er kwamen er drie bij.


## [0.8.3] — 2026-09-16

### Opgelost
- **Tegenboekingen verdwenen bij het inlezen.** De vingerafdruk waarmee dubbels
  herkend worden, gaat door een normalisatie die leestekens weggooit — en
  daarmee ook het minteken. Een afschrijving van 5 646,24 en de tegenboeking van
  +5 646,24 kregen zo dezelfde afdruk, waarna de tweede voor een dubbel werd
  aangezien en niet werd bewaard. Het teken van het bedrag zit nu in de
  vingerafdruk.
- Hetzelfde gold voor de afdruk op de bankreferentie. Sommige banken geven een
  boeking en haar tegenboeking dezelfde referentie; ook daar telt het bedrag nu
  mee.
- Rijen die al onder de oude afdruk in de databank staan, worden nog steeds
  teruggevonden, met een controle op het bedrag erbij. Een eerder ingelezen
  bestand wordt dus niet opnieuw toegevoegd, en een tegenboeking die vroeger
  ontbrak komt er bij een nieuwe invoer alsnog bij.

### Terug te halen
- Bied de afschriften waarin tegenboekingen zaten opnieuw aan. De ontbrekende
  lijnen worden toegevoegd; wat er al staat blijft ongemoeid.


## [0.8.2] — 2026-09-16

### Opgelost
- **Het saldo van vorige maand werd als totaal genomen.** Op een kaartafrekening
  staan meerdere totalen door elkaar: het vorige saldo, wat er intussen betaald
  is, en het nieuwe te betalen bedrag. De toepassing nam het eerste bedrag dat
  op een totaal leek, en dat was vaak het verkeerde. Alle regels worden nu
  bekeken, alles wat naar de vorige periode verwijst valt weg, en van wat
  overblijft wint het duidelijkste label: "totaal te betalen" gaat voor op
  "nieuw saldo", en dat weer op een kaal "totaal". Herkend in het Nederlands en
  het Frans.
- Regels over de vorige periode worden ook niet meer als aankoop ingelezen.
- Op het controlescherm staat nu welke regel het totaal opleverde, zodat je zelf
  kan nakijken of de juiste gekozen is.
- **Alleen afrekeningen van het laatste jaar werden gevonden.** Er werd maar in
  de zeshonderd recentste transacties gezocht, en bij een volle geschiedenis
  zijn dat er enkel uit het lopende jaar. Alle uitgaven worden nu overlopen. Om
  dat snel te houden worden er per transactie maar twee velden ontsleuteld in
  plaats van de hele rij: op twintigduizend transacties duurt dat een tiende
  seconde.

### Toegevoegd
- Een jaarkeuze boven de lijst met afrekeningen, met het aantal gevonden
  afrekeningen ernaast.


## [0.8.1] — 2026-09-16

### Opgelost
- **De raming ging uit van de dag van vandaag in plaats van je laatste
  transactie.** Wie zijn afschriften tot half mei had ingelezen, kreeg in
  september een raming die deed alsof er al driekwart jaar geboekt was. Het
  bedrag werd dan door een veel te groot deel gedeeld en de raming viel ver te
  laag uit. De peildatum is nu de datum van de laatste transactie, en die staat
  ook op het scherm en bij het lopende jaar vermeld.
- Jaren die pas halverwege beginnen tellen niet meer mee als maatstaf. Het
  eerste jaar van je geschiedenis begint zelden op 1 januari, en zo'n jaar zou
  het gemiddelde vertekenen. Er wordt alleen gekeken naar jaren met een
  transactie in januari.
- Is het laatste jaar praktisch rond, dan verschijnt er geen raming meer. Een
  raming die het bedrag met één procent verhoogt, voegt niets toe.


## [0.8.0] — 2026-09-16

### Opgelost
- **Inkomsten werden bij uitgaven opgeteld in plaats van ervan afgetrokken.**
  De bedragen werden overal als grootte behandeld, zonder teken. Koos je bij
  *Soort* voor allebei, dan gaf de jaartabel 48 000 waar 24 000 hoorde te staan.
  Er wordt nu met het teken gerekend: inkomsten tellen op, uitgaven af. Bekijk
  je één richting, dan staan de bedragen zoals voordien gewoon positief; bekijk
  je allebei, dan is het totaal een echt saldo.
- Dezelfde correctie geldt voor de staafgrafiek. In de taart blijven negatieve
  netto bedragen weg, want een taart van gemengde tekens zegt niets.

### Gewijzigd
- **Het meest recente jaar staat bovenaan** op het startscherm, in plaats van
  onderaan.
- Het startscherm rekent nu ook in hele euro's, net als de jaartabel.

### Toegevoegd
- **Een raming voor het lopende jaar.** Dat jaar is nog niet om, dus naast volle
  jaren oogt het altijd te laag. De raming kijkt naar de vijf voorgaande jaren:
  welk deel van het jaartotaal was er op deze dag van het jaar gemiddeld al
  geboekt? Het bedrag tot nu wordt door dat deel gedeeld. Zo telt het seizoen
  mee — wie in juli op vakantie gaat, heeft in maart nog lang niet de helft
  verteerd.
- De raming staat als lichtere balk in dezelfde kleur achter de werkelijke
  balk, met het bedrag ernaast, en met een uitleg boven de grafiek. Ze
  verschijnt alleen wanneer er minstens twee volle jaren zijn om op te steunen.


## [0.7.3] — 2026-09-16

### Gewijzigd
- **Hoofdcategorieën staan nu ook in de uitsluitlijst.** Voordien kon je alleen
  sub- en sub-subcategorieën weglaten. Een hele tak wegnemen kan nu met één
  keuze: sluit je een hoofdcategorie uit, dan valt alles eronder mee weg.
  Dat geldt voor de jaartabel en voor allebei de grafieken.
- Hoofdcategorieën staan vet in die lijst en sub-subcategorieën lichter, zodat
  je ziet of je een hele tak wegneemt of één post.


## [0.7.2] — 2026-09-16

### Opgelost
- **Het stijlblad bleef ook na 0.7.1 op een oude versie hangen.** Het
  versienummer stond als parameter achter het adres, en dat volstaat niet: een
  proxy of een service worker die op het pad bewaart, negeert zo'n parameter en
  geeft gewoon het oude bestand terug. Het nummer zit nu in het pad zelf
  (`/statisch/0.7.2/css/stijl.css`), dus elke versie is een ander adres.
- Schermen worden niet meer bewaard door tussenliggende proxy's. Anders kan er
  een bladzijde van een vorige versie teruggegeven worden die verwijst naar
  bestanden die niet meer bestaan.

### Toegevoegd
- **De toepassing merkt het nu zelf wanneer de browser een oude opmaak
  gebruikt.** Er staat een versiemerk in het stijlblad; komt dat niet overeen met
  de draaiende versie, dan verschijnt er bovenaan een melding met wat je moet
  doen. Voordien zag je alleen een half werkend scherm zonder aanwijzing waarom.
- `scripts/versie.py` zet het versienummer in één keer op alle zes de plaatsen
  waar het staat, inclusief het merk in het stijlblad. Dat handmatig bijhouden
  gaat vroeg of laat mis.


## [0.7.1] — 2026-09-16

### Opgelost
- **Het stijlblad en het script bleven op de oude versie hangen.** Na een
  herbouw serveerde de browser de bestanden van de vorige versie verder. Daardoor
  viel de filterbalk terug op losse velden onder elkaar en tekenden de grafieken
  helemaal niet meer: de bladzijde van vandaag met de opmaak en het script van
  gisteren. Beide adressen dragen nu het versienummer, zodat een nieuwe versie
  altijd opgehaald wordt.

### Gewijzigd
- **De filterbalk staat op één horizontale lijn.** Zoeken, rekening, soort en
  status staan als smalle velden naast elkaar; jaren, bron, categorie, land,
  winkel en uitsluiten zitten achter een knopje dat een paneeltje openklapt. Op
  het knopje staat hoeveel er gekozen is.
- Eén paneel staat tegelijk open; klikken buiten het paneel of op Escape sluit
  het. Bij een knop aan de rechterkant klapt het paneel naar links open zodat het
  in beeld blijft.
- De transactielijst en de twee grafieken gebruiken nu dezelfde filterbalk, dus
  een filter ziet er overal hetzelfde uit en werkt overal hetzelfde.
- De jaartabel kreeg het uitsluiten van categorieën en winkels erbij; dat zat
  alleen bij de grafieken.


## [0.7.0] — 2026-09-16

### Toegevoegd
- **Hetzelfde bestand opnieuw aanbieden vult bestaande transacties aan.** Ben je
  bij een eerdere invoer een kolom vergeten, dan hoef je niets te verwijderen:
  bied het bestand opnieuw aan met die kolom erbij en de lege velden worden
  alsnog ingevuld. Er komen geen dubbels bij. Aan te zetten met *Bestaande
  transacties aanvullen* op het controlescherm; standaard staat dat aan.
- Een mededeling die uitgebreid is wordt vervangen. Stond er "Aankoop | winkel
  12" en komt er "Aankoop | winkel 12 | kassa 3" binnen, dan is het nieuwe een
  uitbreiding van het oude en gaat het erin. Is het iets anders, dan blijft
  staan wat er stond, zodat je eigen aanpassingen niet overschreven worden.
- Het ontdubbelen kreeg er een derde manier bij: rekening, datum, bedrag en de
  rekening van de tegenpartij samen. Die is nodig voor bestanden zonder
  referentiekolom, want daar verandert de vingerafdruk zodra er een kolom
  bijkomt. Ze wordt alleen gebruikt wanneer er precies één kandidaat overblijft.
- **Een voortgangsmeter bij het inlezen.** De invoer loopt nu in de achtergrond
  en het scherm toont de fase, het aantal verwerkte rijen, het percentage en de
  verstreken tijd. Voordien leek er minutenlang niets te gebeuren.
- Het resultaat splitst nu in *nieuw toegevoegd*, *aangevuld*, *al bekend, niets
  nieuws* en *onleesbaar*, in plaats van alles wat niet nieuw was op één hoop te
  gooien.

### Gewijzigd
- Sluit je het venster tijdens een invoer, dan loopt die gewoon door; ze hangt
  niet meer aan je browservenster vast.


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
