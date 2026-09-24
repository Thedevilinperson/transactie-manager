"""Een vaste regel maken vanuit één transactie.

Vroeger kon dat alleen met een vinkje, dat altijd dezelfde regel maakte:
"naam van de tegenpartij bevat …". Voor een winkel volstaat dat, voor een
persoon zelden — Axelle krijgt drinkgeld, maar ook geld voor de tandarts. Nu
stel je de regel samen uit de gegevens van de transactie zelf: welke velden,
welke vergelijking, inkomst of uitgave, eventueel een bedragvork.

Het formulier (zie _regelmaker.html) heeft een reeks rijen met telkens een
vinkje, een veld, een vergelijking en een waarde. Alleen aangevinkte rijen met
een waarde tellen. De eerste daarvan wordt de hoofdvoorwaarde van de regel, de
rest komt er met EN bovenop — net zoals bij *Instellingen › Regels*. Een
hoofdvoorwaarde mag geen "bevat niet" zijn: zo'n regel paste op zowat alles.
"""

from __future__ import annotations

from dataclasses import dataclass

from .categories import laad_alles, pad_tekst
from .categorizer.engine import Regel, Voorwaarde, regel_past
from .crypto import normalize
from .database import now_iso
from .transacties import BESCHERMDE_METHODEN, rij_naar_object

VELDEN = ("tegenpartij_naam", "tegenpartij_rekening", "beschrijving", "mededeling",
          "sleutel", "alles")
OPERATOREN = ("bevat", "gelijk", "regex", "bevat_niet")


# Lage prioriteit gaat voor. De regels uit je referentielijst en historiek
# krijgen 10 tot 90 (zie importers/regelbouwer.py). Een regel die je zelf
# samenstelt uit meerdere voorwaarden is specifieker dan elk daarvan, en moet
# dus voorgaan — anders wint "alles van Axelle" altijd van "Axelle én
# drinkgeld". Met één voorwaarde blijft het 50, zoals de regels die de
# toepassing bij een bevestiging zelf bijleert.
PRIORITEIT_COMBINATIE = 5
PRIORITEIT_ENKEL = 50


def standaard_prioriteit(aantal_voorwaarden: int) -> int:
    return PRIORITEIT_COMBINATIE if aantal_voorwaarden > 1 else PRIORITEIT_ENKEL


@dataclass
class Samenstelling:
    """Wat het formulier beschrijft, nog zonder categorie of opslag."""
    naam: str
    prioriteit: int
    voorwaarden: list[Voorwaarde]
    richting: str | None
    bedrag_min: float | None
    bedrag_max: float | None


def _getal(tekst: str | None) -> float | None:
    try:
        return float(str(tekst).replace(",", ".")) if tekst not in (None, "") else None
    except ValueError:
        return None


def lees(form) -> tuple[Samenstelling | None, str]:
    """Leest de regel uit het formulier. Geeft (samenstelling, "") of
    (None, reden) terug."""
    gebruikt = set(form.getlist("rv_gebruik"))
    velden = form.getlist("rv_veld")
    operatoren = form.getlist("rv_operator")
    waarden = form.getlist("rv_waarde")

    voorwaarden: list[Voorwaarde] = []
    for i, waarde in enumerate(waarden):
        waarde = waarde.strip()
        if str(i) not in gebruikt or not waarde:
            continue
        veld = velden[i] if i < len(velden) and velden[i] in VELDEN else "mededeling"
        operator = (operatoren[i] if i < len(operatoren) and operatoren[i] in OPERATOREN
                    else "bevat")
        voorwaarden.append(Voorwaarde(veld, operator, waarde))

    # De hoofdvoorwaarde mag geen uitsluiting zijn.
    hoofd = next((i for i, v in enumerate(voorwaarden) if v.operator != "bevat_niet"), None)
    if hoofd is None:
        return None, ("Vink minstens één voorwaarde aan die iets insluit "
                      "(bevat, is gelijk aan of een reguliere expressie).")
    voorwaarden.insert(0, voorwaarden.pop(hoofd))

    richting = form.get("rv_richting")
    try:
        prioriteit = int(form.get("rv_prioriteit"))
    except (TypeError, ValueError):
        prioriteit = standaard_prioriteit(len(voorwaarden))
    naam = " ".join((form.get("rv_naam") or "").split()) or voorwaarden[0].waarde
    return Samenstelling(
        naam=naam[:120], prioriteit=prioriteit, voorwaarden=voorwaarden,
        richting=richting if richting in ("in", "uit") else None,
        bedrag_min=_getal(form.get("rv_bedrag_min")),
        bedrag_max=_getal(form.get("rv_bedrag_max")),
    ), ""


def als_regel(s: Samenstelling, categorie_ids=(None, None, None)) -> Regel:
    """Een regelobject zoals de motor het kent, om mee te proberen."""
    eerste, *rest = s.voorwaarden
    return Regel(
        id=0, naam=s.naam, prioriteit=s.prioriteit,
        veld=eerste.veld, operator=eerste.operator, waarde=eerste.waarde,
        bedrag_min=s.bedrag_min, bedrag_max=s.bedrag_max, richting=s.richting,
        categorie_id=categorie_ids[0], subcategorie_id=categorie_ids[1],
        subsub_id=categorie_ids[2], handelaar=None, land=None, extra=list(rest),
    )


def proef(conn, crypto, s: Samenstelling, categorie_ids, voorbeelden: int = 6,
          huidig_tx: int | None = None) -> dict:
    """Op welke transacties zou deze regel nu passen?

    Loopt over de hele boekhouding. Dat kost bij tienduizenden transacties een
    seconde, en het is precies wat je wil weten vóór je een regel bewaart:
    past ze op te veel (een woord dat overal staat), of op te weinig (een
    mededeling die maar één keer voorkwam)?
    """
    regel = als_regel(s)
    platte = laad_alles(conn, crypto)
    doel = tuple(categorie_ids)

    uit = {"aantal": 0, "deze": 0, "zelfde": 0, "anders": 0, "zonder": 0,
           "handmatig_anders": 0, "gelijkenis": 0, "voorbeelden": []}
    for row in conn.execute("SELECT * FROM transacties ORDER BY boekdatum DESC, id DESC"):
        tx = rij_naar_object(row, crypto)
        if not regel_past(regel, tx.kenmerken):
            continue
        uit["aantal"] += 1
        huidig = (row["categorie_id"], row["subcategorie_id"], row["subsub_id"])
        if row["id"] == huidig_tx:
            # De transactie die je nu bewerkt: haar categorie is nog niet
            # bewaard, dus die telt niet mee als "zonder" of "anders".
            uit["deze"] += 1
            soort = "deze"
        elif row["categorie_id"] is None and row["methode"] not in BESCHERMDE_METHODEN:
            uit["zonder"] += 1
            soort = "zonder"
        elif row["methode"] == "fuzzy" and row["status"] != "bevestigd":
            # Een gelijkenis die nog op nazicht staat: die neemt de regel bij
            # het opslaan over (zie regelonderhoud.pas_toe).
            uit["gelijkenis"] += 1
            soort = "gelijkenis"
        elif huidig == doel:
            uit["zelfde"] += 1
            soort = "zelfde"
        else:
            uit["anders"] += 1
            soort = "anders"
            if row["methode"] in BESCHERMDE_METHODEN:
                uit["handmatig_anders"] += 1
        if len(uit["voorbeelden"]) < voorbeelden:
            uit["voorbeelden"].append({
                "datum": tx.boekdatum,
                "tegenpartij": tx.tegenpartij_naam or tx.begunstigde or "",
                "mededeling": (tx.mededeling or "")[:60],
                "bedrag": str(tx.bedrag),
                "categorie": (pad_tekst(platte, *huidig) if row["categorie_id"]
                              else "bewust zonder categorie gelaten"),
                "soort": soort,
            })
    return uit


def bewaar(conn, crypto, s: Samenstelling, categorie_ids, handelaar: str | None,
           land: str | None) -> int:
    """Schrijft de regel weg, met dezelfde velden als *Instellingen › Regels*."""
    from .routes.instellingen import _schrijf_voorwaarden

    eerste, *rest = s.voorwaarden
    velden = {
        "naam_enc": crypto.enc(s.naam),
        "prioriteit": s.prioriteit,
        "veld": eerste.veld,
        "operator": eerste.operator,
        "waarde_enc": crypto.enc(eerste.waarde),
        "waarde_idx": crypto.blind(normalize(eerste.waarde)),
        "bedrag_min": s.bedrag_min,
        "bedrag_max": s.bedrag_max,
        "richting": s.richting,
        "categorie_id": categorie_ids[0],
        "subcategorie_id": categorie_ids[1],
        "subsub_id": categorie_ids[2],
        "handelaar_enc": crypto.enc(handelaar) if handelaar else None,
        "land_enc": crypto.enc(land) if land else None,
        "herkomst": "handmatig",
        "aangemaakt_op": now_iso(),
    }
    cur = conn.execute(
        f"INSERT INTO regels ({', '.join(velden)}) VALUES ({', '.join('?' * len(velden))})",
        tuple(velden.values()))
    _schrijf_voorwaarden(conn, cur.lastrowid, [
        {"volgorde": i, "veld": v.veld, "operator": v.operator,
         "waarde_enc": crypto.enc(v.waarde), "waarde_idx": crypto.blind(normalize(v.waarde))}
        for i, v in enumerate(rest)])
    return cur.lastrowid
