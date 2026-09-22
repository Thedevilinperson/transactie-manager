"""De herindeling, los van het scherm dat ze aanroept.

Ze zat in de route zelf, en dat werkte zolang ze vanaf één knop kwam. Nu ze ook
achter een voortgangsmeter moet kunnen lopen — na het afleiden van regels uit je
historiek, waar het om duizenden rijen gaat — moet ze aanroepbaar zijn vanuit
een aparte draad, met een eigen verbinding en zonder aanvraagcontext.

De telling gaat per stap uiteen, want dat is wat je daarna wil terugvinden: een
vaste regel, een gelijkenis met de historiek en het AI-model belanden alle drie
onder een andere *methode* in de lijst.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field

from .categorizer.engine import Motor
from .transacties import rij_naar_object, werk_bij

# Hoever een herindeling gaat. De eerste is de standaard en het veilige bereik:
# een transactie die al ergens in zit, is daar meestal met opzet beland.
BEREIKEN = {
    "zonder_categorie": ("alleen transacties zonder categorie",
                         "categorie_id IS NULL AND status <> 'bevestigd'"),
    "onbevestigd": ("alles wat nog niet bevestigd is", "status <> 'bevestigd'"),
    # Tot versie 0.25.0 kon de fuzzy stap zichzelf versterken en automatisch
    # bevestigen wat niet klopte. Dit bereik laat die rijen opnieuw beoordelen
    # met de strengere motor.
    "gelijkenis_bevestigd": ("bevestigde transacties die door een gelijkenis zijn ingedeeld",
                             "methode = 'fuzzy' AND status = 'bevestigd'"),
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
