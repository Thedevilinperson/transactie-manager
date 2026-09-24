"""De herindeling, los van het scherm dat ze aanroept.

Ze zat in de route zelf, en dat werkte zolang ze vanaf één knop kwam. Nu ze ook
achter een voortgangsmeter moet kunnen lopen — na het afleiden van regels uit je
historiek, waar het om duizenden rijen gaat — moet ze aanroepbaar zijn vanuit
een aparte draad, met een eigen verbinding en zonder aanvraagcontext.

De telling gaat per stap uiteen, want dat is wat je daarna wil terugvinden: een
vaste regel, een gelijkenis met de historiek en het AI-model belanden alle drie
onder een andere *methode* in de lijst.

Wat een mens heeft ingedeeld of goedgekeurd — met de hand, zoals het in een
ingelezen bestand stond, of een voorstel dat je met *Klopt* bevestigde — valt
buiten elk bereik. Dat staat zowel in de zoekvraag als,
voor de zekerheid, nog eens in de lus zelf.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field

from .categorizer.engine import Motor
from .database import now_iso
from .transacties import (NIET_BESCHERMD_SQL, is_beschermd, rij_naar_object,
                          werk_bij)

# Hoever een herindeling gaat. De eerste is de standaard en het veilige bereik:
# een transactie die al ergens in zit, is daar meestal met opzet beland.
#
# Elk bereik sluit uitdrukkelijk uit wat met de hand of uit een bestand kwam.
# Voor twee van de drie is dat vandaag al zo door de status (zulke rijen staan
# altijd als bevestigd), maar dat is een toevalligheid en geen garantie: één
# plek die ooit een manuele indeling op *nazicht* zet, en ze zou meegaan.
BEREIKEN = {
    "zonder_categorie": ("alleen transacties zonder categorie",
                         "categorie_id IS NULL AND status <> 'bevestigd'"
                         f" AND {NIET_BESCHERMD_SQL}"),
    "onbevestigd": ("alles wat nog niet bevestigd is",
                    f"status <> 'bevestigd' AND {NIET_BESCHERMD_SQL}"),
    # Tot versie 0.25.0 kon de fuzzy stap zichzelf versterken en automatisch
    # bevestigen wat niet klopte. Dit bereik laat die rijen opnieuw beoordelen
    # met de strengere motor. Alleen wat de motor zelf bevestigde: een
    # gelijkenis waarop jij *Klopt* zei, is nagekeken en blijft staan.
    "gelijkenis_bevestigd": ("automatisch bevestigde gelijkenissen",
                             "methode = 'fuzzy' AND status = 'bevestigd'"
                             f" AND {NIET_BESCHERMD_SQL}"),
}

# Bereiken waarin een transactie waarvoor de motor niets meer vindt, haar
# categorie verliest. In de andere bereiken blijft ze dan staan zoals ze stond:
# daar gaat het om aanvullen, niet om intrekken.
INTREKKEN = {"gelijkenis_bevestigd"}
INGETROKKEN_TOELICHTING = ("De automatische gelijkenis is ingetrokken: er is geen "
                           "regel of betrouwbare gelijkenis meer die deze indeling "
                           "ondersteunt.")


@dataclass
class Uitslag:
    bereik: str = "zonder_categorie"
    omschrijving: str = ""
    ongewijzigd: int = 0
    per_methode: collections.Counter = field(default_factory=collections.Counter)

    @property
    def totaal(self) -> int:
        return sum(self.per_methode.values())


def normaliseer(keuze: str | None) -> str:
    return keuze if keuze in BEREIKEN else "zonder_categorie"


def voer_uit(conn, crypto, bereik: str = "zonder_categorie", taak=None) -> Uitslag:
    """Laat de motor opnieuw los op de transacties binnen dit bereik.

    Er wordt alleen geteld wat er werkelijk verandert. Voordien telde elke rij
    mee waarvoor de motor íets vond, ook als dat precies was wat er al stond —
    een tweede herindeling meldde dan weer hetzelfde aantal.
    """
    bereik = normaliseer(bereik)
    # Eerst zeker zijn dat wat je vroeger al bevestigde, als nagekeken staat.
    markeer_eerder_nagekeken(conn, crypto)
    omschrijving, waar = BEREIKEN[bereik]
    uitslag = Uitslag(bereik=bereik, omschrijving=omschrijving)

    if taak is not None:
        taak.fase = "Regels en geschiedenis laden"
    motor = Motor(conn, crypto)

    rijen = conn.execute(f"SELECT * FROM transacties WHERE {waar}").fetchall()
    if taak is not None:
        taak.totaal = len(rijen)
        taak.vorder(0, "Transacties opnieuw beoordelen")
    # Zie de opmerking bij het wegschrijven: om de honderdste rij melden.
    stap = max(1, len(rijen) // 100)

    for i, row in enumerate(rijen, 1):
        if is_beschermd(row):
            # Kan door de zoekvraag niet voorkomen; staat hier als tweede slot.
            continue
        tx = rij_naar_object(row, crypto)
        voorstel = motor.beoordeel(tx.kenmerken)
        if voorstel.gevonden and not (
                voorstel.categorie_id == row["categorie_id"]
                and voorstel.subcategorie_id == row["subcategorie_id"]
                and voorstel.subsub_id == row["subsub_id"]
                and voorstel.methode == row["methode"]
                and voorstel.status == row["status"]):
            werk_bij(
                conn, crypto, tx.id,
                categorie_id=voorstel.categorie_id,
                subcategorie_id=voorstel.subcategorie_id,
                subsub_id=voorstel.subsub_id,
                handelaar=voorstel.handelaar or tx.handelaar,
                land=voorstel.land or tx.land,
                zekerheid=voorstel.zekerheid,
                status=voorstel.status,
                methode=voorstel.methode,
                toelichting=voorstel.toelichting,
                regel_id=voorstel.regel_id,
            )
            uitslag.per_methode[voorstel.methode] += 1
        elif voorstel.gevonden:
            uitslag.ongewijzigd += 1
        elif bereik in INTREKKEN:
            werk_bij(
                conn, crypto, tx.id,
                categorie_id=None, subcategorie_id=None, subsub_id=None,
                zekerheid=0.0, status="niet_toegewezen", methode="geen",
                toelichting=INGETROKKEN_TOELICHTING, regel_id=None,
            )
            uitslag.per_methode["geen"] += 1

        if taak is not None and i % stap == 0:
            taak.vorder(i)

    if taak is not None:
        taak.vorder(len(rijen))
    return uitslag


# --------------------------------------------------------------------------
# Eenmalig: wat je vóór schemaversie 10 al had nagekeken
# --------------------------------------------------------------------------

NAGEKEKEN_SLEUTEL = "nagekeken_afgeleid"


def markeer_eerder_nagekeken(conn, crypto) -> int | None:
    """Zet `nagekeken` op transacties die je al bevestigde vóór die kolom bestond.

    Uit de gegevens valt dat betrouwbaar af te leiden:

    * met de hand of uit een bestand: altijd door een mens ingedeeld;
    * een bevestigd AI-voorstel: het model bevestigt nooit zelf;
    * een bevestigde gelijkenis waarvan de toelichting *niet* met "Sterke
      gelijkenis" begint: de motor bevestigt alleen onder die toelichting,
      dus een andere ("Vermoedelijke match …", "… Kies zelf welke hier past.")
      stond op nazicht tot jij *Klopt* zei;
    * een bevestigde regeltreffer met de toelichting van een onzekere regel
      ("wijst … naar meer dan één categorie") of "Regel bevestigd." (van
      *Ze klopt*): idem.

    De toelichting staat versleuteld, en daarom gebeurt dit pas wanneer iemand
    aangemeld is. Geeft het aantal gemarkeerde rijen terug, of None als het al
    eerder gebeurde. Een teruggezette kopie van vóór deze versie heeft de
    sleutel niet en wordt dus opnieuw nagelopen.
    """
    if conn.execute("SELECT 1 FROM app_meta WHERE sleutel = ?",
                    (NAGEKEKEN_SLEUTEL,)).fetchone():
        return None

    aantal = conn.execute(
        "UPDATE transacties SET nagekeken = 1 WHERE nagekeken = 0 AND"
        " (methode IN ('manueel', 'bestand')"
        "  OR (methode = 'ai' AND status = 'bevestigd'))").rowcount

    for row in conn.execute(
            "SELECT id, methode, toelichting_enc FROM transacties"
            " WHERE nagekeken = 0 AND status = 'bevestigd'"
            " AND methode IN ('fuzzy', 'regel')").fetchall():
        uitleg = crypto.dec(row["toelichting_enc"]) or ""
        if row["methode"] == "fuzzy":
            door_mens = not uitleg.startswith("Sterke gelijkenis")
        else:
            door_mens = ("meer dan één categorie" in uitleg
                         or uitleg == "Regel bevestigd.")
        if door_mens:
            conn.execute("UPDATE transacties SET nagekeken = 1 WHERE id = ?", (row["id"],))
            aantal += 1

    conn.execute("INSERT INTO app_meta (sleutel, waarde) VALUES (?, ?)",
                 (NAGEKEKEN_SLEUTEL, f"{now_iso()} rijen={aantal}"))
    conn.commit()
    return aantal
