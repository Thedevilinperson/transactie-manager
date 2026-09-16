"""Overzichten: jaartabel per categorie en reeksen voor de grafieken.

Bedragen staan versleuteld, dus optellen gebeurt in Python na ontsleuteling.
Land en winkel eveneens; die worden alleen ontsleuteld wanneer een filter of een
groepering ze nodig heeft, want dat scheelt bij tienduizenden rijen merkbaar.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from .categories import Categorie, bouw_boom, laad_alles, nakomelingen
from .filters import LEEG, Filters


@dataclass
class Regelrij:
    """Eén rij in de overzichtstabel."""
    id: int | None
    naam: str
    niveau: int
    per_jaar: dict = field(default_factory=dict)
    totaal: Decimal = Decimal("0")
    kinderen: list["Regelrij"] = field(default_factory=list)

    @property
    def heeft_kinderen(self) -> bool:
        return bool(self.kinderen)


def _rijen(conn, crypto, filters: Filters, platte, *, velden_nodig: bool):
    """Haalt de transacties op en levert per rij het nodige, al ontsleuteld."""
    waar, params = filters.sql()
    kolommen = ("boekdatum, bedrag_enc, categorie_id, subcategorie_id, subsub_id"
                + (", land_enc, handelaar_enc" if velden_nodig else ""))
    toegelaten = (nakomelingen(platte, filters.categorie_id)
                  if filters.categorie_id else None)

    for row in conn.execute(f"SELECT {kolommen} FROM transacties WHERE {waar}", params):
        cat_ids = {row["categorie_id"], row["subcategorie_id"], row["subsub_id"]}
        if not filters.past_categorie(cat_ids, toegelaten):
            continue
        land = winkel = ""
        if velden_nodig:
            land = (crypto.dec(row["land_enc"]) or "").strip()
            winkel = (crypto.dec(row["handelaar_enc"]) or "").strip()
            if not filters.past_tekst(land=land, winkel=winkel):
                continue
        yield row, abs(crypto.dec_amount(row["bedrag_enc"])), land, winkel


def jaartabel(conn, crypto, filters: Filters):
    """Bouwt de uitklapbare tabel: categorie tegenover jaar.

    Geeft (rijen, jaren, eindtotalen) terug. De jaren staan van recent naar oud,
    want daar kijk je het vaakst naar.
    """
    platte = laad_alles(conn, crypto)
    beperking = (nakomelingen(platte, filters.categorie_id)
                 if filters.categorie_id else None)
    velden_nodig = filters.vraagt_tekst

    bedragen: dict = defaultdict(lambda: defaultdict(Decimal))
    jaren: set = set()

    for row, bedrag, _land, _winkel in _rijen(conn, crypto, filters, platte,
                                              velden_nodig=velden_nodig):
        jaar = int(row["boekdatum"][:4])
        jaren.add(jaar)
        bedragen[(row["categorie_id"], row["subcategorie_id"],
                  row["subsub_id"])][jaar] += bedrag

    jaren_gesorteerd = sorted(jaren, reverse=True)
    wortels = bouw_boom(platte)
    if filters.richting in ("in", "uit"):
        wortels = [c for c in wortels if c.soort in (filters.richting, "beide")]

    def bouw(cat: Categorie, pad: tuple):
        eigen = pad + (None,) * (3 - len(pad))
        rij = Regelrij(id=cat.id, naam=cat.naam, niveau=cat.niveau)
        rij.per_jaar = defaultdict(Decimal)
        for jaar, bedrag in bedragen.get(eigen, {}).items():
            rij.per_jaar[jaar] += bedrag
        for kind in cat.kinderen:
            kindrij = bouw(kind, pad + (kind.id,))
            if kindrij is not None:
                rij.kinderen.append(kindrij)
                for jaar, bedrag in kindrij.per_jaar.items():
                    rij.per_jaar[jaar] += bedrag
        rij.totaal = sum(rij.per_jaar.values(), Decimal("0"))
        if rij.totaal == 0 and not rij.kinderen:
            return None
        if beperking is not None and cat.id not in beperking and not rij.kinderen:
            return None
        return rij

    rijen = []
    for wortel in wortels:
        if beperking is not None and wortel.id not in beperking:
            continue
        rij = bouw(wortel, (wortel.id,))
        if rij is not None:
            rijen.append(rij)

    zonder = defaultdict(Decimal)
    for sleutel, per_jaar in bedragen.items():
        if sleutel[0] is None:
            for jaar, bedrag in per_jaar.items():
                zonder[jaar] += bedrag
    if zonder:
        rij = Regelrij(id=None, naam="Nog niet toegewezen", niveau=0)
        rij.per_jaar = dict(zonder)
        rij.totaal = sum(zonder.values(), Decimal("0"))
        rijen.append(rij)

    eindtotalen = {jaar: Decimal("0") for jaar in jaren_gesorteerd}
    for rij in rijen:
        for jaar, bedrag in rij.per_jaar.items():
            eindtotalen[jaar] += bedrag
    eindtotalen["totaal"] = sum(eindtotalen.values(), Decimal("0"))
    return rijen, jaren_gesorteerd, eindtotalen


def plat(rijen):
    """Zet de boom om naar platte rijen met een oudersleutel, voor de tabel."""
    resultaat = []

    def loop(rij, ouder_sleutel):
        sleutel = f"{ouder_sleutel}-{rij.id or 'x'}"
        resultaat.append({
            "sleutel": sleutel, "ouder": ouder_sleutel, "id": rij.id,
            "naam": rij.naam, "niveau": rij.niveau, "per_jaar": rij.per_jaar,
            "totaal": rij.totaal, "heeft_kinderen": rij.heeft_kinderen,
        })
        for kind in rij.kinderen:
            loop(kind, sleutel)

    for rij in rijen:
        loop(rij, "")
    return resultaat


# --------------------------------------------------------------------------
# Grafieken
# --------------------------------------------------------------------------

def _label(row, platte, groepering: str, land: str, winkel: str) -> str:
    if groepering == "land":
        return land or LEEG
    if groepering == "winkel":
        return winkel or LEEG
    sleutel = {"sub": "subcategorie_id", "subsub": "subsub_id"}.get(
        groepering, "categorie_id")
    cat_id = row[sleutel]
    if cat_id is None:
        cat_id = row["subcategorie_id"] or row["categorie_id"]
    if cat_id in platte:
        return platte[cat_id].naam
    return "Nog niet toegewezen"


def reeksen(conn, crypto, filters: Filters, maximum: int = 12):
    """Tijdreeksen per groepering, voor de gestapelde staafgrafiek."""
    platte = laad_alles(conn, crypto)
    velden_nodig = filters.vraagt_tekst or filters.groepering in ("land", "winkel")

    per_label = defaultdict(lambda: defaultdict(Decimal))
    perioden = set()

    for row, bedrag, land, winkel in _rijen(conn, crypto, filters, platte,
                                            velden_nodig=velden_nodig):
        periode = (row["boekdatum"][:4] if filters.periode == "jaar"
                   else row["boekdatum"][:7])
        perioden.add(periode)
        per_label[_label(row, platte, filters.groepering, land, winkel)][periode] += bedrag

    labels = sorted(perioden)
    op_totaal = sorted(per_label.items(), key=lambda p: -sum(p[1].values(), Decimal("0")))

    uitvoer = []
    for naam, waarden in op_totaal[:maximum]:
        uitvoer.append({
            "naam": naam,
            "totaal": float(sum(waarden.values(), Decimal("0"))),
            "waarden": [float(waarden.get(p, Decimal("0"))) for p in labels],
        })
    rest = op_totaal[maximum:]
    if rest:
        samen = defaultdict(Decimal)
        for _naam, waarden in rest:
            for periode, bedrag in waarden.items():
                samen[periode] += bedrag
        uitvoer.append({
            "naam": f"Overige ({len(rest)})",
            "totaal": float(sum(samen.values(), Decimal("0"))),
            "waarden": [float(samen.get(p, Decimal("0"))) for p in labels],
        })
    return labels, uitvoer


def verdeling(conn, crypto, filters: Filters, maximum: int = 12):
    """Eén taart: het totaal per groepering over de gekozen selectie."""
    platte = laad_alles(conn, crypto)
    velden_nodig = filters.vraagt_tekst or filters.groepering in ("land", "winkel")

    per_label = defaultdict(Decimal)
    for row, bedrag, land, winkel in _rijen(conn, crypto, filters, platte,
                                            velden_nodig=velden_nodig):
        per_label[_label(row, platte, filters.groepering, land, winkel)] += bedrag

    op_totaal = sorted(per_label.items(), key=lambda p: -p[1])
    stukken = [{"naam": n, "waarde": float(b)} for n, b in op_totaal[:maximum]]
    rest = op_totaal[maximum:]
    if rest:
        stukken.append({"naam": f"Overige ({len(rest)})",
                        "waarde": float(sum((b for _n, b in rest), Decimal("0")))})
    return stukken, float(sum(per_label.values(), Decimal("0")))


def kerncijfers(conn, crypto) -> dict:
    """Cijfers voor het startscherm."""
    rows = conn.execute(
        "SELECT boekdatum, bedrag_enc, richting, status FROM transacties"
        " WHERE is_afrekening = 0").fetchall()
    per_jaar_in = defaultdict(Decimal)
    per_jaar_uit = defaultdict(Decimal)
    nazicht = niet_toegewezen = 0
    for row in rows:
        jaar = int(row["boekdatum"][:4])
        bedrag = abs(crypto.dec_amount(row["bedrag_enc"]))
        if row["richting"] == "in":
            per_jaar_in[jaar] += bedrag
        else:
            per_jaar_uit[jaar] += bedrag
        if row["status"] == "nazicht":
            nazicht += 1
        elif row["status"] == "niet_toegewezen":
            niet_toegewezen += 1

    jaren = sorted(set(per_jaar_in) | set(per_jaar_uit))
    return {
        "aantal": len(rows), "nazicht": nazicht, "niet_toegewezen": niet_toegewezen,
        "jaren": jaren[-8:],
        "inkomsten": {j: per_jaar_in.get(j, Decimal("0")) for j in jaren},
        "uitgaven": {j: per_jaar_uit.get(j, Decimal("0")) for j in jaren},
        "laatste_jaar": jaren[-1] if jaren else None,
    }
