"""Overzichten: jaartabel per categorie en reeksen voor grafieken.

Bedragen staan versleuteld, dus optellen gebeurt in Python na ontsleuteling.
Voor een huishoudboekje (tienduizenden rijen) is dat ruim snel genoeg.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from .categories import Categorie, bouw_boom, laad_alles, nakomelingen


@dataclass
class Regelrij:
    """Eén rij in de overzichtstabel."""
    id: int | None
    naam: str
    niveau: int
    per_jaar: dict[int, Decimal] = field(default_factory=dict)
    totaal: Decimal = Decimal("0")
    kinderen: list["Regelrij"] = field(default_factory=list)
    ouder_pad: str = ""

    @property
    def heeft_kinderen(self) -> bool:
        return bool(self.kinderen)


def _basis_query(filters: dict) -> tuple[str, list]:
    # Kaartafrekeningen tellen niet mee: hun aankopen staan er los onder.
    sql = ("SELECT boekdatum, bedrag_enc, richting, categorie_id, subcategorie_id, subsub_id"
           " FROM transacties WHERE is_afrekening = 0")
    params: list = []
    if filters.get("richting") in ("in", "uit"):
        sql += " AND richting = ?"
        params.append(filters["richting"])
    if filters.get("rekening_id"):
        sql += " AND rekening_id = ?"
        params.append(filters["rekening_id"])
    if filters.get("van"):
        sql += " AND boekdatum >= ?"
        params.append(filters["van"])
    if filters.get("tot"):
        sql += " AND boekdatum <= ?"
        params.append(filters["tot"])
    if filters.get("alleen_bevestigd"):
        sql += " AND status = 'bevestigd'"
    return sql, params


def jaartabel(conn, crypto, filters: dict | None = None):
    """Bouwt de uitklapbare tabel: categorie x jaar.

    Geeft (rijen, jaren, eindtotalen) terug. Bedragen zijn absoluut; de
    richting bepaalt of het om inkomsten of uitgaven gaat.
    """
    filters = filters or {}
    platte = laad_alles(conn, crypto)

    beperking: set[int] | None = None
    if filters.get("categorie_id"):
        beperking = nakomelingen(platte, int(filters["categorie_id"]))

    sql, params = _basis_query(filters)

    # sleutel = (hoofd, sub, subsub) met None voor ontbrekende niveaus
    bedragen: dict[tuple, dict[int, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    jaren: set[int] = set()

    for row in conn.execute(sql, params):
        cat = row["categorie_id"]
        if beperking is not None:
            geraakt = {row["categorie_id"], row["subcategorie_id"], row["subsub_id"]}
            if not (geraakt & beperking):
                continue
        jaar = int(row["boekdatum"][:4])
        jaren.add(jaar)
        bedrag = abs(crypto.dec_amount(row["bedrag_enc"]))
        sleutel = (cat, row["subcategorie_id"], row["subsub_id"])
        bedragen[sleutel][jaar] += bedrag

    jaren_gesorteerd = sorted(jaren)
    wortels = bouw_boom(platte)

    if filters.get("richting") in ("in", "uit"):
        wortels = [c for c in wortels if c.soort in (filters["richting"], "beide")]

    def bouw(cat: Categorie, pad: tuple) -> Regelrij | None:
        eigen_sleutel = pad + (None,) * (3 - len(pad))
        rij = Regelrij(id=cat.id, naam=cat.naam, niveau=cat.niveau)
        rij.per_jaar = defaultdict(Decimal)

        for jaar, bedrag in bedragen.get(eigen_sleutel, {}).items():
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

    rijen: list[Regelrij] = []
    for wortel in wortels:
        if beperking is not None and wortel.id not in beperking:
            continue
        rij = bouw(wortel, (wortel.id,))
        if rij is not None:
            rijen.append(rij)

    # Niet-toegewezen transacties krijgen een eigen rij.
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


def plat(rijen: list[Regelrij], _ouder: str = "") -> list[dict]:
    """Zet de boom om naar platte rijen met een oudersleutel, voor de tabel."""
    resultaat: list[dict] = []

    def loop(rij: Regelrij, ouder_sleutel: str):
        sleutel = f"{ouder_sleutel}-{rij.id or 'x'}"
        resultaat.append({
            "sleutel": sleutel,
            "ouder": ouder_sleutel,
            "id": rij.id,
            "naam": rij.naam,
            "niveau": rij.niveau,
            "per_jaar": rij.per_jaar,
            "totaal": rij.totaal,
            "heeft_kinderen": rij.heeft_kinderen,
        })
        for kind in rij.kinderen:
            loop(kind, sleutel)

    for rij in rijen:
        loop(rij, "")
    return resultaat


def reeksen(conn, crypto, filters: dict | None = None, groepering: str = "jaar"):
    """Tijdreeksen per hoofdcategorie, voor de grafieken.

    groepering is 'jaar' of 'maand'.
    """
    filters = filters or {}
    platte = laad_alles(conn, crypto)
    beperking: set[int] | None = None
    if filters.get("categorie_id"):
        beperking = nakomelingen(platte, int(filters["categorie_id"]))

    # Welk niveau tonen we als aparte lijn?
    detail = filters.get("detailniveau", "hoofd")

    sql, params = _basis_query(filters)
    reeks: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    perioden: set[str] = set()

    for row in conn.execute(sql, params):
        if beperking is not None:
            geraakt = {row["categorie_id"], row["subcategorie_id"], row["subsub_id"]}
            if not (geraakt & beperking):
                continue
        periode = row["boekdatum"][:4] if groepering == "jaar" else row["boekdatum"][:7]
        perioden.add(periode)
        if detail == "sub" and row["subcategorie_id"] in platte:
            label = platte[row["subcategorie_id"]].naam
        elif row["categorie_id"] in platte:
            label = platte[row["categorie_id"]].naam
        else:
            label = "Nog niet toegewezen"
        reeks[label][periode] += abs(crypto.dec_amount(row["bedrag_enc"]))

    labels = sorted(perioden)
    uitvoer = []
    for naam, waarden in reeks.items():
        totaal = sum(waarden.values(), Decimal("0"))
        uitvoer.append({
            "naam": naam,
            "totaal": float(totaal),
            "waarden": [float(waarden.get(p, Decimal("0"))) for p in labels],
        })
    uitvoer.sort(key=lambda r: -r["totaal"])
    return labels, uitvoer


def kerncijfers(conn, crypto) -> dict:
    """Cijfers voor het startscherm."""
    rows = conn.execute(
        "SELECT boekdatum, bedrag_enc, richting, status FROM transacties"
        " WHERE is_afrekening = 0"
    ).fetchall()
    per_jaar_in: dict[int, Decimal] = defaultdict(Decimal)
    per_jaar_uit: dict[int, Decimal] = defaultdict(Decimal)
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
        "aantal": len(rows),
        "nazicht": nazicht,
        "niet_toegewezen": niet_toegewezen,
        "jaren": jaren,
        "inkomsten": {j: per_jaar_in.get(j, Decimal("0")) for j in jaren},
        "uitgaven": {j: per_jaar_uit.get(j, Decimal("0")) for j in jaren},
        "laatste_jaar": jaren[-1] if jaren else None,
    }
