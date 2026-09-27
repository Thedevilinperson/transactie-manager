"""Een vaste regel maken vanuit één transactie.

Vroeger kon dat alleen met een vinkje, dat altijd dezelfde regel maakte:
"naam van de tegenpartij bevat …". Voor een winkel volstaat dat, voor een
persoon zelden — Axelle krijgt drinkgeld, maar ook geld voor de tandarts. Nu
stel je de regel samen uit de gegevens van de transactie zelf: welke velden,
welke vergelijking, inkomst of uitgave, eventueel een bedragvork.

Het formulier (zie _regelmaker.html) heeft een reeks rijen met telkens een
vinkje, EN of OF, een veld, een vergelijking en een waarde. Alleen aangevinkte
rijen met een waarde tellen. De eerste daarvan wordt de hoofdvoorwaarde van de
regel, de rest hangt er met EN of OF aan — net zoals bij *Instellingen ›
Regels*. Elke groep (wat met OF gescheiden is) heeft een voorwaarde nodig die
iets insluit: met enkel "bevat niet" paste de regel op zowat alles.

Zo'n regel krijgt als herkomst "transactie" (zie regelopslag.HERKOMSTEN).
"""

from __future__ import annotations

from dataclasses import dataclass

from .categories import laad_alles, pad_tekst
from .categorizer.engine import (Regel, Voorwaarde, fout_in_voorwaarden, ordenen,
                                regel_past)
from .crypto import normalize
from .database import now_iso
from .transacties import is_beschermd, rij_naar_object

VELDEN = ("tegenpartij_naam", "tegenpartij_rekening", "beschrijving", "mededeling",
          "sleutel", "alles")
OPERATOREN = ("bevat", "gelijk", "regex", "bevat_niet")


# Lage prioriteit gaat voor. De bevestigde regels uit je historiek krijgen 5,
# wat de app zelf afleidt 40 tot 50, onbevestigde historiekregels 90 (zie
# regelopslag.py). Een regel die je zelf samenstelt uit meerdere voorwaarden
# krijgt 5, even hoog als de bevestigde historiekregels; bij gelijke prioriteit
# gaat de oudste voor. Met één voorwaarde blijft het 50.
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
    bevestigd: bool = True


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
    koppelingen = form.getlist("rv_koppeling")
    waarden = form.getlist("rv_waarde")

    voorwaarden: list[Voorwaarde] = []
    for i, waarde in enumerate(waarden):
        waarde = waarde.strip()
        if str(i) not in gebruikt or not waarde:
            continue
        veld = velden[i] if i < len(velden) and velden[i] in VELDEN else "mededeling"
        operator = (operatoren[i] if i < len(operatoren) and operatoren[i] in OPERATOREN
                    else "bevat")
        koppeling = "of" if i < len(koppelingen) and koppelingen[i] == "of" else "en"
        voorwaarden.append(Voorwaarde(veld, operator, waarde, koppeling))

    if not voorwaarden:
        return None, ("Vink minstens één voorwaarde aan die iets insluit "
                      "(bevat, is gelijk aan of een reguliere expressie).")
    # De eerste aangevinkte rij hangt nergens aan.
    voorwaarden[0] = Voorwaarde(voorwaarden[0].veld, voorwaarden[0].operator,
                                voorwaarden[0].waarde, "en")
    fout = fout_in_voorwaarden(voorwaarden)
    if fout:
        return None, fout
    # De hoofdvoorwaarde mag geen uitsluiting zijn; binnen de eerste EN-groep
    # mag er geschoven worden.
    voorwaarden = ordenen(voorwaarden)

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
        bevestigd=form.get("rv_bevestigd") == "1",
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
        elif row["categorie_id"] is None and not is_beschermd(row):
            uit["zonder"] += 1
            soort = "zonder"
        elif (row["methode"] in ("fuzzy", "ai") and row["status"] != "bevestigd"
              and not is_beschermd(row)):
            # Een gelijkenis of AI-voorstel dat nog op nazicht staat: dat neemt
            # de regel bij het opslaan over (zie regelonderhoud.pas_toe).
            uit["gelijkenis"] += 1
            soort = "gelijkenis"
        elif huidig == doel:
            uit["zelfde"] += 1
            soort = "zelfde"
        else:
            uit["anders"] += 1
            soort = "anders"
            if is_beschermd(row):
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
           land: str | None, gebruiker: str | None = None) -> int:
    """Schrijft de regel weg, met herkomst "transactie"."""
    from .regelopslag import schrijf_regel

    return schrijf_regel(
        conn, crypto, naam=s.naam, prioriteit=s.prioriteit, voorwaarden=s.voorwaarden,
        ids=categorie_ids, richting=s.richting, bedrag_min=s.bedrag_min,
        bedrag_max=s.bedrag_max, handelaar=handelaar, land=land,
        herkomst="transactie", bevestigd=s.bevestigd, gebruiker=gebruiker)
