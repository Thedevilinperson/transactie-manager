"""Regels maken uit je ingelezen historiek.

Sinds versie 0.33.0 kies je zelf naar welke kolommen er gekeken wordt. Elke
combinatie van waarden in die kolommen die in je historiek voorkomt, wordt één
regel:

* wijst de combinatie altijd naar dezelfde categorie, dan wordt het een
  **bevestigde** regel met prioriteit 5 (herkomst "historiek");
* wijst ze naar meer dan één categorie, dan wordt het een **onbevestigde**
  regel naar de categorie die het vaakst voorkwam, met prioriteit 90 (herkomst
  "historiek_onzeker"). Wat ze indeelt, komt op nazicht.

Kies je bijvoorbeeld *Beschrijving* en *Naam tegenpartij*, dan wordt
"Betaling Bancontact" + "COLRUYT GENT" één regel, en "Overschrijving" +
"COLRUYT GENT" een andere.

Daarnaast mag de app **zelf** nog regels afleiden, maar alleen onder strikte
voorwaarden:

* alleen voor transacties die je gekozen kolommen niet eenduidig dekken: omdat
  hun combinatie naar meer dan één categorie wees, of omdat een van je gekozen
  kolommen leeg was;
* alleen combinaties van **minstens twee velden**. De datum en of het om een
  inkomst of een uitgave gaat, tellen daarbij niet mee. Het bedrag (als
  bedragvork) telt wel als veld;
* alleen als de combinatie in de hele historiek naar één categorie wijst, en
  op minstens twee transacties steunt;
* zo'n regel is altijd **onbevestigd** (herkomst "historiek_afgeleid").

De naam van elke regel is de categoriestructuur, gevolgd door de mededeling als
die korter is dan 30 tekens, en anders door de tegenpartij (zie
regelopslag.regelnaam).
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from decimal import Decimal

from ..categories import laad_alles, pad_tekst
from ..categorizer.engine import Voorwaarde
from ..crypto import normalize, normalize_iban
from ..regelopslag import (HISTORIEK_HERKOMSTEN, PRIORITEIT_AFGELEID,
                           PRIORITEIT_AFGELEID_VORK, PRIORITEIT_BEVESTIGD,
                           PRIORITEIT_ONZEKER, regelnaam, schrijf_regel)
from ..transacties import rij_naar_object

# De kolommen waaruit je kan kiezen, in de volgorde van het scherm.
KOLOMMEN = {
    "beschrijving": "Beschrijving (soort verrichting)",
    "tegenpartij_naam": "Naam tegenpartij",
    "tegenpartij_rekening": "Rekening tegenpartij",
    "mededeling": "Mededeling",
}
STANDAARD_KOLOMMEN = ("beschrijving", "tegenpartij_naam")

# Waarop de regels gebaseerd worden.
BRONNEN = {
    "bestand": "Alleen de ingelezen historiek (uit een bestand)",
    "mens": "Alles wat een mens indeelde: ingelezen historiek, met de hand, of "
            "met Klopt bevestigd",
}

# Wat de app zelf mag afleiden, sterkste eerst. Elke combinatie heeft minstens
# twee velden; een bedragvork telt als veld.
AFGELEID = [
    ("tegenpartij_rekening", "beschrijving"),
    ("beschrijving", "tegenpartij_naam"),
    ("tegenpartij_naam", "gestructureerd"),
    ("tegenpartij_naam", "mededeling"),
]
AFGELEID_NAAM = {
    ("tegenpartij_rekening", "beschrijving"): "rekening tegenpartij én beschrijving",
    ("beschrijving", "tegenpartij_naam"): "beschrijving én tegenpartij",
    ("tegenpartij_naam", "gestructureerd"): "tegenpartij én gestructureerde mededeling",
    ("tegenpartij_naam", "mededeling"): "tegenpartij én mededeling",
    "vork": "tegenpartij én bedragvork",
}

GESTRUCTUREERD = re.compile(r"\+{3}\d{3}/\d{4}/\d{5}\+{3}|\*{3}\d{3}/\d{4}/\d{5}\*{3}")

MIN_WAARNEMINGEN = 2              # voor een afgeleide regel
MIN_VOOR_BEDRAGSPLITSING = 4      # voor een bedragvork


@dataclass
class Tx:
    """Wat er van één transactie nodig is, al ontsleuteld."""
    id: int
    ruw: dict                  # veld -> waarde zoals ze er staat
    norm: dict                 # veld -> genormaliseerde waarde
    pad: tuple
    richting: str
    bedrag: Decimal
    handelaar: str
    land: str


@dataclass
class Voorstelregel:
    voorwaarden: list
    pad: tuple
    prioriteit: int
    herkomst: str
    bevestigd: bool
    aantal: int
    naam: str = ""
    richting: str | None = None
    bedrag_min: float | None = None
    bedrag_max: float | None = None
    handelaar: str = ""
    land: str = ""
    soort: str = ""            # voor het overzicht


@dataclass
class Analyse:
    transacties: int = 0
    kolommen: tuple = ()
    overgeslagen: int = 0      # een gekozen kolom was leeg
    regels: list = field(default_factory=list)
    bevestigd: int = 0
    onbevestigd: int = 0
    afgeleid: dict = field(default_factory=dict)   # soort -> aantal
    ongedekt: int = 0          # na alles nog zonder eenduidige regel

    @property
    def afgeleid_totaal(self) -> int:
        return sum(self.afgeleid.values())


# --------------------------------------------------------------------------
# Inlezen
# --------------------------------------------------------------------------

def _transacties(conn, crypto, bron: str) -> list[Tx]:
    sql = ("SELECT * FROM transacties WHERE categorie_id IS NOT NULL"
           " AND is_afrekening = 0")
    if bron == "bestand":
        sql += " AND methode = 'bestand'"
    else:
        sql += " AND (methode IN ('bestand', 'manueel') OR nagekeken = 1)"
    uit = []
    for row in conn.execute(sql):
        t = rij_naar_object(row, crypto)
        ruw = {
            "beschrijving": t.beschrijving.strip(),
            "tegenpartij_naam": t.tegenpartij_naam.strip(),
            "tegenpartij_rekening": t.tegenpartij_rekening.strip(),
            "mededeling": t.mededeling.strip(),
        }
        gevonden = GESTRUCTUREERD.search(t.mededeling or "")
        ruw["gestructureerd"] = gevonden.group(0) if gevonden else ""
        norm = {v: (normalize_iban(w) if v == "tegenpartij_rekening" else normalize(w))
                for v, w in ruw.items()}
        if len(norm["tegenpartij_rekening"]) < 8:
            norm["tegenpartij_rekening"] = ""
        uit.append(Tx(id=t.id, ruw=ruw, norm=norm,
                      pad=(t.categorie_id, t.subcategorie_id, t.subsub_id),
                      richting=t.richting, bedrag=abs(t.bedrag),
                      handelaar=t.handelaar or "", land=t.land or ""))
    return uit


def _meest(waarden) -> str:
    teller = collections.Counter(w for w in waarden if w)
    return teller.most_common(1)[0][0] if teller else ""


def _enige(waarden) -> str:
    """De waarde als ze bij alle transacties (die er een hebben) gelijk is."""
    verschillend = {w for w in waarden if w}
    return next(iter(verschillend)) if len(verschillend) == 1 else ""


def _voorwaarde(veld: str, groep: list[Tx]) -> Voorwaarde:
    if veld == "gestructureerd":
        return Voorwaarde("mededeling", "bevat", _meest(t.ruw["gestructureerd"] for t in groep))
    return Voorwaarde(veld, "gelijk", _meest(t.ruw[veld] for t in groep))


def _regel(groep: list[Tx], velden, pad, *, prioriteit, herkomst, bevestigd, soort,
           richting=None, **extra) -> Voorstelregel:
    return Voorstelregel(
        voorwaarden=[_voorwaarde(v, groep) for v in velden],
        pad=pad, prioriteit=prioriteit, herkomst=herkomst, bevestigd=bevestigd,
        aantal=len(groep), richting=richting, soort=soort,
        handelaar=_enige(t.handelaar for t in groep),
        land=_enige(t.land for t in groep),
        naam=_meest(t.ruw["mededeling"] for t in groep) + "\x00"
        + _meest(t.ruw["tegenpartij_naam"] for t in groep),
        **extra,
    )


def _eenzelfde_richting(groep: list[Tx]) -> str | None:
    richtingen = {t.richting for t in groep}
    return next(iter(richtingen)) if len(richtingen) == 1 else None


# --------------------------------------------------------------------------
# Analyse
# --------------------------------------------------------------------------

def analyseer(conn, crypto, kolommen, *, bron: str = "bestand",
              richting_apart: bool = True, afleiden: bool = True) -> Analyse:
    kolommen = tuple(k for k in KOLOMMEN if k in set(kolommen)) or STANDAARD_KOLOMMEN
    alle = _transacties(conn, crypto, bron)
    analyse = Analyse(transacties=len(alle), kolommen=kolommen)

    # 1. De combinaties van de gekozen kolommen.
    groepen: dict[tuple, list[Tx]] = collections.defaultdict(list)
    ongedekt: dict[int, Tx] = {}
    for t in alle:
        if any(not t.norm[k] for k in kolommen):
            analyse.overgeslagen += 1
            ongedekt[t.id] = t
            continue
        sleutel = tuple(t.norm[k] for k in kolommen)
        if richting_apart:
            sleutel += (t.richting,)
        groepen[sleutel].append(t)

    for groep in groepen.values():
        paden = collections.Counter(t.pad for t in groep)
        richting = _eenzelfde_richting(groep) if richting_apart else None
        if len(paden) == 1:
            analyse.regels.append(_regel(
                groep, kolommen, next(iter(paden)), prioriteit=PRIORITEIT_BEVESTIGD,
                herkomst="historiek", bevestigd=True, soort="bevestigd",
                richting=richting))
            analyse.bevestigd += 1
        else:
            analyse.regels.append(_regel(
                groep, kolommen, paden.most_common(1)[0][0],
                prioriteit=PRIORITEIT_ONZEKER, herkomst="historiek_onzeker",
                bevestigd=False, soort="onbevestigd", richting=richting))
            analyse.onbevestigd += 1
            for t in groep:
                ongedekt[t.id] = t

    # 2. Wat de app zelf mag afleiden, voor wat nog niet eenduidig gedekt is.
    if afleiden and ongedekt:
        for velden in AFGELEID:
            if set(velden) == set(kolommen):
                continue
            _leid_af(alle, ongedekt, velden, analyse)
        _leid_vork_af(alle, ongedekt, analyse)

    analyse.ongedekt = len(ongedekt)
    return analyse


def _leid_af(alle: list[Tx], ongedekt: dict, velden: tuple, analyse: Analyse) -> None:
    """Regels op een combinatie van twee velden, voor wat nog ongedekt is.

    De combinatie wordt beoordeeld over de hele historiek, niet alleen over wat
    ongedekt is: anders kon een afgeleide regel tegenspreken wat elders al goed
    stond.
    """
    groepen: dict[tuple, list[Tx]] = collections.defaultdict(list)
    for t in alle:
        if all(t.norm[v] for v in velden):
            groepen[tuple(t.norm[v] for v in velden)].append(t)
    soort = AFGELEID_NAAM[velden]
    for groep in groepen.values():
        open_ = [t for t in groep if t.id in ongedekt]
        if not open_ or len(groep) < MIN_WAARNEMINGEN:
            continue
        paden = {t.pad for t in groep}
        if len(paden) != 1:
            continue
        analyse.regels.append(_regel(
            groep, velden, next(iter(paden)), prioriteit=PRIORITEIT_AFGELEID,
            herkomst="historiek_afgeleid", bevestigd=False, soort=soort,
            richting=_eenzelfde_richting(groep)))
        analyse.afgeleid[soort] = analyse.afgeleid.get(soort, 0) + 1
        for t in open_:
            ongedekt.pop(t.id, None)


def _leid_vork_af(alle: list[Tx], ongedekt: dict, analyse: Analyse) -> None:
    """Een tegenpartij die naar twee categorieën wijst, waar het bedrag de
    gevallen netjes scheidt: kleine bedragen zijn een broodje, grote zijn
    tanken. Twee velden: de tegenpartij en het bedrag."""
    groepen: dict[tuple, list[Tx]] = collections.defaultdict(list)
    for t in alle:
        if t.norm["tegenpartij_naam"]:
            groepen[(t.norm["tegenpartij_naam"], t.richting)].append(t)
    soort = AFGELEID_NAAM["vork"]
    for groep in groepen.values():
        if not any(t.id in ongedekt for t in groep):
            continue
        if len(groep) < MIN_VOOR_BEDRAGSPLITSING:
            continue
        per_pad: dict[tuple, list[Tx]] = collections.defaultdict(list)
        for t in groep:
            per_pad[t.pad].append(t)
        if len(per_pad) != 2:
            continue
        (pad_a, a), (pad_b, b) = per_pad.items()
        laag, hoog = ((pad_a, a), (pad_b, b)) if min(t.bedrag for t in a) <= \
            min(t.bedrag for t in b) else ((pad_b, b), (pad_a, a))
        if max(t.bedrag for t in laag[1]) >= min(t.bedrag for t in hoog[1]):
            continue      # de reeksen overlappen: het bedrag scheidt niets
        grens = float(round((max(t.bedrag for t in laag[1])
                             + min(t.bedrag for t in hoog[1])) / 2))
        if grens <= 0:
            continue
        richting = groep[0].richting
        analyse.regels.append(_regel(
            laag[1], ("tegenpartij_naam",), laag[0], prioriteit=PRIORITEIT_AFGELEID_VORK,
            herkomst="historiek_afgeleid", bevestigd=False, soort=soort,
            richting=richting, bedrag_max=grens))
        analyse.regels.append(_regel(
            hoog[1], ("tegenpartij_naam",), hoog[0], prioriteit=PRIORITEIT_AFGELEID_VORK,
            herkomst="historiek_afgeleid", bevestigd=False, soort=soort,
            richting=richting, bedrag_min=grens))
        analyse.afgeleid[soort] = analyse.afgeleid.get(soort, 0) + 2
        for t in groep:
            ongedekt.pop(t.id, None)


def voorbeelden(conn, crypto, analyse: Analyse, aantal: int = 25) -> list[dict]:
    """Een greep uit de regels, zoals ze in de lijst zouden komen."""
    platte = laad_alles(conn, crypto)
    uit = []
    # Van elke soort iets, en de grootste eerst.
    for regel in sorted(analyse.regels, key=lambda r: (-r.aantal,))[:aantal]:
        uit.append({
            "naam": _naam(platte, regel),
            "voorwaarden": " en ".join(
                f"{KOLOMMEN.get(v.veld, v.veld).split(' (')[0].lower()} "
                f"{'bevat' if v.operator == 'bevat' else '='} “{v.waarde}”"
                for v in regel.voorwaarden)
            + (f", vanaf {regel.bedrag_min:.0f} euro" if regel.bedrag_min else "")
            + (f", onder {regel.bedrag_max:.0f} euro" if regel.bedrag_max else ""),
            "aantal": regel.aantal,
            "bevestigd": regel.bevestigd,
            "soort": regel.soort,
        })
    return uit


def _naam(platte, regel: Voorstelregel) -> str:
    mededeling, _, tegenpartij = regel.naam.partition("\x00")
    return regelnaam(pad_tekst(platte, *regel.pad), mededeling, tegenpartij,
                     reserve=regel.voorwaarden[0].waarde)


# --------------------------------------------------------------------------
# Wegschrijven
# --------------------------------------------------------------------------

def schrijf(conn, crypto, analyse: Analyse, *, vervang_geleerd: bool = True,
            gebruiker: str | None = None, taak=None) -> dict:
    """Zet de regels in de databank.

    `vervang_geleerd` verwijdert eerst wat een vorige keer uit de historiek is
    gemaakt (alle drie de herkomsten uit HISTORIEK_HERKOMSTEN). Regels die je
    zelf maakte, die uit een transactie of uit het nazicht komen, blijven hoe
    dan ook staan.
    """
    if vervang_geleerd:
        plaatsen = ",".join("?" * len(HISTORIEK_HERKOMSTEN))
        conn.execute(f"DELETE FROM regels WHERE herkomst IN ({plaatsen})",
                     HISTORIEK_HERKOMSTEN)

    platte = laad_alles(conn, crypto)
    stap = max(1, len(analyse.regels) // 100)
    for i, regel in enumerate(analyse.regels):
        if taak is not None and i % stap == 0:
            taak.vorder(i)
        schrijf_regel(
            conn, crypto, naam=_naam(platte, regel), prioriteit=regel.prioriteit,
            voorwaarden=regel.voorwaarden, ids=regel.pad, richting=regel.richting,
            bedrag_min=regel.bedrag_min, bedrag_max=regel.bedrag_max,
            handelaar=regel.handelaar or None, land=regel.land or None,
            herkomst=regel.herkomst, bevestigd=regel.bevestigd, gebruiker=gebruiker)
    return {"regels": len(analyse.regels), "bevestigd": analyse.bevestigd,
            "onbevestigd": analyse.onbevestigd, "afgeleid": analyse.afgeleid_totaal}
