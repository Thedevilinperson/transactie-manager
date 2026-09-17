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
    # Bewust zonder richtingsfilter: zie de uitleg bij Filters.sql. Het saldo
    # per categorie telt, niet de rijen die toevallig één kant op gaan.
    waar, params = filters.sql(met_richting=False)
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
        # Met teken: inkomsten positief, uitgaven negatief. Wie één richting
        # bekijkt krijgt het bedrag bij de weergave weer positief te zien; wie
        # allebei bekijkt krijgt een saldo dat klopt.
        yield row, crypto.dec_amount(row["bedrag_enc"]), land, winkel


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

    # Bij één richting tonen we de grootte: een uitgavenoverzicht vol minnen
    # leest niet. Bij allebei blijft het teken staan, want dan is het een saldo.
    if filters.richting == "uit":
        for sleutel in bedragen:
            for jaar in bedragen[sleutel]:
                bedragen[sleutel][jaar] *= -1

    jaren_gesorteerd = sorted(jaren, reverse=True)
    wortels = bouw_boom(platte)

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
        # Bij een gekozen richting blijft weg wat per saldo de andere kant
        # opgaat: een categorie die netto geld opleverde hoort niet tussen de
        # uitgaven.
        if filters.richting in ("in", "uit") and rij.totaal < 0 and not rij.kinderen:
            return None
        if beperking is not None and cat.id not in beperking and not rij.kinderen:
            return None
        return rij

    rijen = []
    for wortel in wortels:
        if beperking is not None and wortel.id not in beperking:
            continue
        rij = bouw(wortel, (wortel.id,))
        if rij is None:
            continue
        if filters.richting in ("in", "uit") and rij.totaal <= 0:
            continue
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

    if filters.richting == "uit":
        for naam in per_label:
            for periode in per_label[naam]:
                per_label[naam][periode] *= -1
    if filters.richting in ("in", "uit"):
        per_label = {n: w for n, w in per_label.items()
                     if sum(w.values(), Decimal("0")) > 0}

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

    if filters.richting == "uit":
        per_label = {n: -b for n, b in per_label.items()}
    # Een taart van gemengde tekens zegt niets; negatieve delen blijven weg.
    per_label = {n: b for n, b in per_label.items() if b > 0}

    op_totaal = sorted(per_label.items(), key=lambda p: -p[1])
    stukken = [{"naam": n, "waarde": float(b)} for n, b in op_totaal[:maximum]]
    rest = op_totaal[maximum:]
    if rest:
        stukken.append({"naam": f"Overige ({len(rest)})",
                        "waarde": float(sum((b for _n, b in rest), Decimal("0")))})
    return stukken, float(sum(per_label.values(), Decimal("0")))


def kerncijfers(conn, crypto, jaren_tonen: int = 8) -> dict:
    """Cijfers voor het startscherm, met een raming voor het laatste jaar.

    Het laatste jaar waarvoor er gegevens zijn, is meestal nog niet volledig
    ingelezen. Vergelijken met volle jaren geeft dan een vertekend beeld. De
    raming kijkt naar de vijf voorgaande jaren: welk deel van het jaartotaal was
    er op deze dag van het jaar gemiddeld al geboekt? Het bedrag tot nu wordt
    door dat deel gedeeld. Zo telt het seizoen mee: wie in juli op vakantie
    gaat, heeft in maart nog lang niet de helft verteerd.

    De peildatum is de **laatste transactie**, niet de dag van vandaag. Wie zijn
    afschriften tot mei heeft ingelezen, heeft geen gegevens over de zomer; doen
    alsof het jaar al tot september gevorderd is, zou de raming te laag maken.
    """
    per_jaar = {"in": defaultdict(Decimal), "uit": defaultdict(Decimal)}
    tot_dag = {"in": defaultdict(Decimal), "uit": defaultdict(Decimal)}
    eerste_dag: dict = {}
    aantal = nazicht = niet_toegewezen = 0

    rij = conn.execute(
        "SELECT MAX(boekdatum) m FROM transacties WHERE is_afrekening = 0").fetchone()
    laatste = rij["m"] if rij and rij["m"] else None
    if laatste is None:
        return {"aantal": 0, "nazicht": 0, "niet_toegewezen": 0, "jaren": [],
                "inkomsten": {}, "uitgaven": {}, "laatste_jaar": None,
                "raming": {}, "peildatum": None}

    lopend = int(laatste[:4])
    grens = (int(laatste[5:7]), int(laatste[8:10]))

    for row in conn.execute(
        "SELECT boekdatum, bedrag_enc, richting, status FROM transacties"
        " WHERE is_afrekening = 0"
    ):
        aantal += 1
        datum = row["boekdatum"]
        jaar = int(datum[:4])
        maand, dag = int(datum[5:7]), int(datum[8:10])
        bedrag = abs(crypto.dec_amount(row["bedrag_enc"]))
        kant = "in" if row["richting"] == "in" else "uit"
        per_jaar[kant][jaar] += bedrag
        if (maand, dag) <= grens:
            tot_dag[kant][jaar] += bedrag
        if jaar not in eerste_dag or (maand, dag) < eerste_dag[jaar]:
            eerste_dag[jaar] = (maand, dag)
        if row["status"] == "nazicht":
            nazicht += 1
        elif row["status"] == "niet_toegewezen":
            niet_toegewezen += 1

    alle_jaren = sorted(set(per_jaar["in"]) | set(per_jaar["uit"]), reverse=True)
    jaren = alle_jaren[:jaren_tonen]

    # Een jaar dat pas halverwege begint, is geen goede maatstaf: het eerste
    # jaar van je geschiedenis begint zelden op 1 januari.
    referentie = [
        j for j in alle_jaren
        if j < lopend and eerste_dag.get(j, (12, 31)) <= (1, 31)
    ][:5]

    raming: dict = {}
    for kant in ("in", "uit"):
        delen = [
            tot_dag[kant][j] / per_jaar[kant][j]
            for j in referentie if per_jaar[kant].get(j, 0) > 0
        ]
        tot_nu = per_jaar[kant].get(lopend, Decimal("0"))
        if len(delen) >= 2 and tot_nu > 0:
            deel = sum(delen) / len(delen)
            # Is het jaar praktisch rond, dan valt er niets te ramen.
            if Decimal("0.05") < deel < Decimal("0.99"):
                raming[kant] = (tot_nu / deel).quantize(Decimal("1"))
    if raming:
        raming["jaar"] = lopend
        raming["referentiejaren"] = len(referentie)
        raming["op"] = laatste

    return {
        "aantal": aantal, "nazicht": nazicht, "niet_toegewezen": niet_toegewezen,
        "jaren": jaren,
        "inkomsten": {j: per_jaar["in"].get(j, Decimal("0")) for j in jaren},
        "uitgaven": {j: per_jaar["uit"].get(j, Decimal("0")) for j in jaren},
        "laatste_jaar": jaren[0] if jaren else None,
        "raming": raming,
        "peildatum": laatste,
    }
