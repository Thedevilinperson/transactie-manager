# Installeren als Home Assistant-add-on

Er zijn twee wegen. De eerste is de gewone; de tweede is handig als je niets op
GitHub wil zetten.

## 1. Via de repository-URL

Zet dit project op GitHub. De structuur is al die van een geldige
add-on-repository:

```
transactie-manager/
├── repository.yaml          ← hierdoor herkent Home Assistant de repository
└── transactie_manager/      ← de add-on zelf
    ├── config.yaml
    ├── build.yaml
    ├── Dockerfile
    ├── run.sh
    ├── requirements.txt
    ├── wsgi.py
    ├── start.py
    └── app/
```

Pas in `repository.yaml` en in `transactie_manager/config.yaml` het adres bij
`url` aan naar dat van je eigen repository.

Ga daarna in Home Assistant naar **Instellingen › Add-ons › Add-on-winkel**,
open het menu rechtsboven, kies **Repositories** en plak de URL van je
repository. Na een ogenblik verschijnt *Transactie Manager* in de winkel.

## 2. Als lokale add-on

Kopieer de map `transactie_manager` in haar geheel naar `/addons/` op je
Home Assistant-systeem, bijvoorbeeld via de Samba- of de Studio Code
Server-add-on. Het resultaat is:

```
/addons/transactie_manager/
├── config.yaml
├── build.yaml
├── Dockerfile
├── run.sh
├── requirements.txt
├── wsgi.py
├── start.py
└── app/
```

Ga daarna naar **Instellingen › Add-ons › Add-on-winkel**, open het menu
rechtsboven en kies **Repositories vernieuwen**. De add-on verschijnt onder
*Lokale add-ons*.

> Kopieer de hele map, niet enkel de losse bestanden. Home Assistant bouwt met
> de add-on-map als context: alles waar de Dockerfile naar verwijst — `app`,
> `requirements.txt`, `wsgi.py`, `start.py`, `run.sh` — moet in diezelfde map
> staan. Er kan niet buiten die map gekeken worden.

## Daarna

Installeer de add-on, zet **Toon in zijbalk** aan en start ze. Bij de eerste
start maak je een beheerder aan.

De eerste keer bouwen duurt even. Op amd64 en aarch64 bestaan er kant-en-klare
pakketten en gaat het vlot; op armv7 moet `cryptography` gecompileerd worden en
kan het een kwartier duren.

## Instellingen van de add-on

| Instelling            | Standaard | Betekenis                        |
|-----------------------|-----------|----------------------------------|
| `sessieduur_minuten`  | 120       | Hoe lang je aangemeld blijft     |
| `maximale_upload_mb`  | 25        | Grootste bestand dat je mag opladen |

## Gegevens en rechten

Alles staat in `/data` binnen de add-on. Die map zit mee in de gewone
Home Assistant-back-up. De inhoud is versleuteld met een sleutel die alleen met
je wachtwoord te ontgrendelen is: een back-up zonder wachtwoord is onleesbaar.

De add-on vraagt bewust geen toegang tot `/config`, `/share` of `/backup`. Ze
heeft alleen haar eigen `/data` nodig; bestanden komen via de browser binnen.

## Poort 8099

De add-on gebruikt ingress, dus je hebt geen open poort nodig. Wil je de
toepassing ook buiten Home Assistant bereiken, zet dan in de configuratie van
de add-on een poort bij *Netwerk*.

## Basisimages

`build.yaml` bepaalt op welk basisimage gebouwd wordt. Home Assistant
onderhoudt alleen versies die nog ondersteund worden; loopt het bouwen ooit
vast op een basisimage dat niet meer bestaat, zet dan in `build.yaml` een
recentere combinatie van Python en Alpine.
