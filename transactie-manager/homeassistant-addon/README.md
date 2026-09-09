# Transactie Manager als Home Assistant add-on

## Installeren

1. Kopieer de map `homeassistant-addon` samen met `app/`, `wsgi.py`,
   `start.py` en `requirements.txt` naar `/addons/transactie_manager/` op je
   Home Assistant-systeem. De structuur wordt dan:

   ```
   /addons/transactie_manager/
   ├── config.yaml
   ├── Dockerfile
   ├── run.sh
   ├── requirements.txt
   ├── wsgi.py
   ├── start.py
   └── app/
   ```

   Het script `scripts/bouw_addon.py` in de hoofdmap zet dit voor je klaar.

2. Ga in Home Assistant naar **Instellingen › Add-ons › Add-on-winkel**, open
   het menu rechtsboven en kies **Repositories vernieuwen**. De add-on
   verschijnt onder *Lokale add-ons*.

3. Installeer de add-on, zet **Toon in zijbalk** aan en start ze.

4. Open de add-on. Bij de eerste start maak je een beheerder aan.

## Gegevens

Alles staat in `/data` binnen de add-on. Die map zit mee in de
Home Assistant-back-up. De inhoud is versleuteld met een sleutel die alleen met
je wachtwoord te ontgrendelen is: een back-up zonder wachtwoord is onleesbaar.

## Poort 8099

De add-on gebruikt ingress, dus je hebt geen open poort nodig. Wil je de
toepassing ook buiten Home Assistant bereiken, zet dan in de configuratie van de
add-on een poort bij `ports`.
