# Transactie Manager

Een huishoudboekje dat draait op je eigen Home Assistant. Je leest je
bankafschriften in, de toepassing deelt de verrichtingen zelf in categorieën in,
en je krijgt overzichten van wat er per jaar naar welke post gaat.

## Installeren

1. Installeer de add-on en zet **Toon in zijbalk** aan.
2. Start ze. De eerste keer bouwen duurt even; op armv7 moet `cryptography`
   gecompileerd worden en kan dat een kwartier duren.
3. Open de add-on. Je komt op het scherm **Eerste start** en maakt een beheerder
   aan.
4. Daarna krijg je eenmalig een **herstelsleutel** te zien. Schrijf die over of
   zet hem in je wachtwoordbeheerder. Hij wordt nergens bewaard en kan niet
   opnieuw getoond worden.

## Instellingen van de add-on

| Instelling            | Standaard | Betekenis                              |
|-----------------------|-----------|----------------------------------------|
| `sessieduur_minuten`  | 120       | Hoe lang je aangemeld blijft           |
| `maximale_upload_mb`  | 25        | Grootste bestand dat je mag opladen    |

De add-on gebruikt ingress, dus je hebt geen open poort nodig. Wil je de
toepassing ook buiten Home Assistant bereiken, zet dan bij *Netwerk* een poort.

## Eerste stappen

**Rekening toevoegen.** Instellingen › Rekeningen. Vul het rekeningnummer in:
daarmee kan een bestand met meerdere rekeningen vanzelf juist verdeeld worden.

**Categorieën.** Er staat een bruikbare boom klaar. Heb je al een eigen
categorieënbestand, lees dat dan in bij Instellingen › Referentielijst. Je kiest
daarbij of je je huidige categorieën behoudt of integraal vervangt. Er staat een
voorbeeldbestand klaar om te downloaden.

**Afschrift inlezen.** Bestand inlezen. Excel en CSV worden ondersteund, met
startprofielen voor Argenta, KBC, Belfius en ING. Je krijgt de kolomindeling
eerst ter controle. Alleen Boekdatum en Bedrag zijn verplicht.

Staat de indeling al in je bestand, voeg dan de kolommen Hoofdcategorie,
Subcategorie, Sub-subcategorie, Winkel en Land toe. Die worden overgenomen en
de transacties komen meteen bevestigd binnen.

**Herstel instellen.** Instellingen › Herstel en e-mail. Vul in waar de
herstelcode naartoe mag en geef de gegevens van je mailserver op. Bij Yahoo is
dat `smtp.mail.yahoo.com`, poort 465 met SSL, en een app-wachtwoord van zestien
tekens in plaats van je gewone wachtwoord.

## Hoe het indelen werkt

Vier stappen, in volgorde. Zodra er één lukt, stopt het.

1. **Vaste regels** op de sleutel, de beschrijving, de tegenpartij, het
   rekeningnummer of de mededeling, met bevat-, gelijk- of regex-vergelijking en
   een optionele bedragvork. Zo valt een uitgave bij een tankstation onder tien
   euro bij de boodschappen en erboven bij het tanken.
2. **Fuzzy vergelijking** met eerder bevestigde transacties en met je
   referentielijst. Boven de bovenste drempel gaat het automatisch door,
   daartussen komt het in het nazicht.
3. **Een lokaal AI-model** via Ollama, met optionele webopzoeking. Een voorstel
   moet altijd bevestigd worden.
4. **Met de hand**, waarbij de subcategorieën gefilterd worden op de gekozen
   bovenliggende categorie.

Bij **Regels uit historiek** laat je een referentielijst afleiden uit wat je al
ingedeeld hebt. Daarbij doen alle bruikbare velden mee: het rekeningnummer van
de tegenpartij, de gestructureerde mededeling, de combinatie van beschrijving en
tegenpartij, en de tegenpartij alleen.

## Kredietkaart

Op je bankafschrift staat de maandafrekening als één bedrag. Laad bij
**Kredietkaart-PDF** het uittreksel van die maand op; de aankopen komen er als
losse transacties onder te hangen en de afrekening telt daarna niet meer mee in
de overzichten. Uittreksels die alleen uit ingescande afbeeldingen bestaan,
kunnen niet gelezen worden.

## Gegevens en beveiliging

Alles staat in `/data` binnen de add-on en zit mee in de gewone Home
Assistant-back-up.

Uit je wachtwoord wordt met scrypt een sleutel afgeleid die een willekeurige
datasleutel ontgrendelt. Die versleutelt elk gevoelig veld apart met AES-256-GCM:
rekeningnummers, namen, mededelingen, bedragen, categorienamen, winkels en
landen. De datasleutel bestaat alleen in het geheugen van het draaiende proces;
na een herstart moet je opnieuw aanmelden.

De add-on vraagt bewust geen toegang tot `/config`, `/share` of `/backup`.

> Een back-up zonder je wachtwoord of herstelsleutel is onleesbaar. Bewaar de
> herstelsleutel dus ergens anders dan bij de back-up.

## Bij problemen

**De herstelcode komt niet aan.** Stuur een testbericht bij Instellingen ›
Herstel en e-mail; de foutmelding van de mailserver komt rechtstreeks op het
scherm. Weigert Yahoo de aanmelding, dan gebruik je waarschijnlijk je gewone
wachtwoord in plaats van een app-wachtwoord.

**Het AI-model antwoordt niet.** Draait Ollama op dezelfde machine, gebruik dan
`http://homeassistant.local:11434` of het IP-adres. Niet `localhost`: dat wijst
binnen de add-on naar de add-on zelf.

**Het bouwen stopt op het basisimage.** Zet in de `FROM`-regel bovenaan de
`Dockerfile` een recentere combinatie van Python en Alpine.

De volledige handleiding staat onder **Handleiding** in de toepassing zelf,
en als bestand in `transactie_manager/docs/HANDLEIDING.md`.
