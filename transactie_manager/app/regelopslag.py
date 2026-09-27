"""Regels wegschrijven, op één plek.

Regels ontstaan op vijf manieren: uit een ingelezen historiek, door de app
afgeleid uit die historiek, met de hand bij *Instellingen › Regels*, vanuit een
transactie die je aanpast, en uit een voorstel dat je in het nazicht met
*Klopt* bevestigt. Vroeger schreef elke plek ze op haar eigen manier weg, met
telkens een iets andere kolomlijst. Nu gaat alles hierlangs, zodat elke regel
een herkomst en een bevestiging krijgt.

Twee begrippen, die los van elkaar staan:

* **herkomst** — waar de regel vandaan komt (zie HERKOMSTEN). Die verandert
  niet meer, ook niet als je de regel later bewerkt;
* **bevestigd** — of de regel zeker indeelt. Wat een bevestigde regel indeelt,
  staat meteen als bevestigd; wat een onbevestigde regel indeelt, komt op
  nazicht. Dat staat in de kolom `bevestigd_op`.
"""

from __future__ import annotations

from .categorizer.engine import Voorwaarde
from .crypto import normalize, normalize_iban
from .database import now_iso

# Waar een regel vandaan komt, in woorden. De volgorde is die van de filter.
HERKOMSTEN = {
    "historiek": "Uit de ingelezen historiek",
    "historiek_onzeker": "Uit de ingelezen historiek — wees naar meer dan één categorie",
    "historiek_afgeleid": "Door de app afgeleid uit de historiek (combinatie van velden)",
    "handmatig": "Met de hand toegevoegd",
    "gelijkenis": "Uit een gelijkenis die je in het nazicht bevestigde",
    "ai": "Uit een AI-voorstel dat je in het nazicht bevestigde",
    "transactie": "Uit het aanpassen van een transactie",
    "referentie": "Uit de vroegere referentielijst",
    "referentie_onzeker": "Uit de vroegere referentielijst — stond daar onder meer dan "
                          "één categorie",
}

# Kort, voor een kolom in een tabel.
HERKOMSTEN_KORT = {
    "historiek": "historiek",
    "historiek_onzeker": "historiek, meerdere categorieën",
    "historiek_afgeleid": "afgeleid uit historiek",
    "handmatig": "met de hand",
    "gelijkenis": "gelijkenis (Klopt)",
    "ai": "AI-voorstel (Klopt)",
    "transactie": "vanuit transactie",
    "referentie": "referentielijst",
    "referentie_onzeker": "referentielijst, meerdere categorieën",
}

# Wat de app zelf maakt uit de historiek. Bij opnieuw afleiden gaat dit weg.
HISTORIEK_HERKOMSTEN = ("historiek", "historiek_onzeker", "historiek_afgeleid")

# Lage prioriteit gaat voor.
PRIORITEIT_BEVESTIGD = 5         # historiek eenduidig, en wat je via Klopt bijleert
PRIORITEIT_AFGELEID_VORK = 40    # door de app afgeleid, met een bedragvork
PRIORITEIT_AFGELEID = 50         # door de app afgeleid, combinatie van velden
PRIORITEIT_ONZEKER = 90          # historiek, wees naar meer dan één categorie

NAAM_MEDEDELING_MAX = 30


def regelnaam(pad: str, mededeling: str | None, tegenpartij: str | None,
              reserve: str = "") -> str:
    """De naam van een regel: de categoriestructuur, gevolgd door de mededeling
    als die korter is dan 30 tekens, en anders door de tegenpartij.

    Is het gekozen veld leeg, dan komt het andere in de plaats, en anders de
    reserve (meestal de waarde van de eerste voorwaarde).
    """
    mededeling = " ".join((mededeling or "").split())
    tegenpartij = " ".join((tegenpartij or "").split())
    if mededeling and len(mededeling) < NAAM_MEDEDELING_MAX:
        achter = mededeling
    else:
        achter = tegenpartij or mededeling[:NAAM_MEDEDELING_MAX] or reserve
    naam = f"{pad} — {achter}" if achter else pad
    return naam[:120]


def _index(veld: str, waarde: str) -> str:
    return normalize_iban(waarde) if veld == "tegenpartij_rekening" else normalize(waarde)


def schrijf_voorwaarden(conn, crypto, regel_id: int, extra: list[Voorwaarde]) -> None:
    """Vervangt de bijkomende voorwaarden van een regel.

    Ze horen bij de regel en hebben geen eigen leven: bij het bewaren worden ze
    in hun geheel opnieuw gezet, zodat een verwijderde rij ook echt weg is.
    """
    conn.execute("DELETE FROM regel_voorwaarden WHERE regel_id = ?", (regel_id,))
    for i, vw in enumerate(extra):
        conn.execute(
            "INSERT INTO regel_voorwaarden (regel_id, volgorde, veld, operator,"
            " waarde_enc, waarde_idx, koppeling) VALUES (?,?,?,?,?,?,?)",
            (regel_id, i, vw.veld, vw.operator, crypto.enc(vw.waarde),
             crypto.blind(_index(vw.veld, vw.waarde)),
             "of" if vw.koppeling == "of" else "en"))


def schrijf_regel(conn, crypto, *, naam: str, prioriteit: int,
                  voorwaarden: list[Voorwaarde], ids=(None, None, None),
                  richting: str | None = None, bedrag_min: float | None = None,
                  bedrag_max: float | None = None, handelaar: str | None = None,
                  land: str | None = None, herkomst: str = "handmatig",
                  bevestigd: bool = True, gebruiker: str | None = None) -> int:
    """Schrijft één regel weg en geeft haar nummer terug.

    De eerste voorwaarde komt in de regeltabel, de rest in regel_voorwaarden.
    """
    eerste, *rest = voorwaarden
    tijdstip = now_iso()
    velden = {
        "naam_enc": crypto.enc(naam or eerste.waarde),
        "prioriteit": prioriteit,
        "veld": eerste.veld,
        "operator": eerste.operator,
        "waarde_enc": crypto.enc(eerste.waarde),
        "waarde_idx": crypto.blind(_index(eerste.veld, eerste.waarde)),
        "bedrag_min": bedrag_min,
        "bedrag_max": bedrag_max,
        "richting": richting if richting in ("in", "uit") else None,
        "categorie_id": ids[0],
        "subcategorie_id": ids[1],
        "subsub_id": ids[2],
        "handelaar_enc": crypto.enc(handelaar) if handelaar else None,
        "land_enc": crypto.enc(land) if land else None,
        "herkomst": herkomst,
        "bevestigd_op": tijdstip if bevestigd else None,
        "bevestigd_door": gebruiker if bevestigd else None,
        "aangemaakt_op": tijdstip,
    }
    cur = conn.execute(
        f"INSERT INTO regels ({', '.join(velden)}) VALUES ({', '.join('?' * len(velden))})",
        tuple(velden.values()))
    if rest:
        schrijf_voorwaarden(conn, crypto, cur.lastrowid, rest)
    return cur.lastrowid


def zet_bevestiging(conn, regel_id: int, bevestigd: bool,
                    gebruiker: str | None = None) -> bool:
    """Bevestigt een regel of trekt de bevestiging in. Geeft terug of er iets
    veranderde."""
    if bevestigd:
        return conn.execute(
            "UPDATE regels SET bevestigd_op = ?, bevestigd_door = ?"
            " WHERE id = ? AND bevestigd_op IS NULL",
            (now_iso(), gebruiker, regel_id)).rowcount > 0
    return conn.execute(
        "UPDATE regels SET bevestigd_op = NULL, bevestigd_door = NULL"
        " WHERE id = ? AND bevestigd_op IS NOT NULL", (regel_id,)).rowcount > 0
