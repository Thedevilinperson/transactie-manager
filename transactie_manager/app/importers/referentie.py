"""Inlezen van de categorielijst.

Een categorielijst beschrijft je categorieën in drie niveaus: hoofdcategorie,
categorie en subcategorie. Hieruit wordt alleen de categorieboom opgebouwd.

Tot versie 0.33.0 heette dit de *referentielijst*, en kon dezelfde lijst ook
regels maken uit een kolom met "beschrijving-tegenpartij". Dat is weg: regels
komen voortaan uit je ingelezen historiek (zie importers/regelbouwer.py), waar
je zelf kiest welke kolommen samen naar een categorie wijzen. Een oudere lijst
met die kolom kan nog altijd ingelezen worden; de kolom wordt dan genegeerd.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..crypto import normalize
from ..database import now_iso

# Waarden die "niet ingevuld" betekenen in het bestand.
LEEG = {"", "-", "?", "n/a", "na", "nvt", "none"}

# Hoe een kopregel op onze vijf velden wordt afgebeeld. Een bestand hoeft niet
# alle kolommen te hebben en de volgorde ligt niet vast: er zijn lijsten met
# enkel de boomstructuur (drie kolommen) en lijsten die ook de koppeling met de
# beschrijvingen bevatten (vijf). Vroeger werd er blind op positie gelezen,
# waardoor een bestand van drie kolommen zijn categorie op de plaats van de
# hoofdcategorie kreeg en de boom een niveau verschoof.
KOPWOORDEN = {
    "sleutel": ("sleutel", "omschrijving", "beschrijving", "referentie",
                "mededeling", "tegenpartij"),
    "hoofdcategorie": ("hoofdcategorie", "hoofdcat", "hoofd"),
    "categorie": ("categorie", "cat"),
    "subcategorie": ("subcategorie", "subcat", "sub"),
    "winkel": ("winkel", "handelaar", "zaak", "land"),
}

VELDVOLGORDE = ["sleutel", "hoofdcategorie", "categorie", "subcategorie", "winkel"]


def _kolomindeling(kop: list) -> dict[str, int] | None:
    """Welke kolom hoort bij welk veld? None als er geen bruikbare kop staat.

    Er wordt van achter naar voor gekeken: "subcategorie" bevat het woord
    "categorie", dus het langste passende woord wint. Zonder die volgorde zou
    een kolom Subcategorie als Categorie gelezen worden.
    """
    schoon = [str(c or "").strip().lower() for c in kop]
    indeling: dict[str, int] = {}
    for i, naam in enumerate(schoon):
        if not naam:
            continue
        beste = None
        for veld, woorden in KOPWOORDEN.items():
            for woord in woorden:
                if woord in naam and (beste is None or len(woord) > beste[1]):
                    beste = (veld, len(woord))
        if beste and beste[0] not in indeling:
            indeling[beste[0]] = i
    # Zonder hoofdcategorie valt er niets zinnigs af te leiden.
    return indeling if "hoofdcategorie" in indeling else None


def _schoon(waarde) -> str:
    if waarde is None:
        return ""
    tekst = str(waarde).strip()
    return "" if tekst.lower() in LEEG else tekst


@dataclass
class Analyse:
    """Wat er in het bestand gevonden is, voor het overzicht vooraf."""
    rijen: int = 0
    bruikbaar: int = 0
    overgeslagen: int = 0
    hoofdcategorieen: int = 0
    categorieen: int = 0
    subcategorieen: int = 0
    sleutelregels: int = 0
    # Bevat het bestand de koppeling met de beschrijvingen? Zo niet, dan valt er
    # geen enkele regel uit af te leiden en kan alleen de boom overgenomen worden.
    met_sleutels: bool = True
    partijregels: int = 0
    botsingen: int = 0
    boom: dict = field(default_factory=dict)
    voorbeeld_botsingen: list = field(default_factory=list)


def lees(pad: Path) -> list[tuple]:
    """Leest het werkblad uit als lijst van vijf kolommen.

    De kolommen worden op hun kopregel herkend, niet op hun plaats. Staat er
    geen bruikbare kop, dan wordt teruggevallen op de oude volgorde: sleutel,
    hoofdcategorie, categorie, subcategorie, winkel.
    """
    from openpyxl import load_workbook

    wb = load_workbook(pad, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rijen = []
    indeling: dict[str, int] | None = None
    eerste = True

    for rij in ws.iter_rows(values_only=True):
        if eerste:
            eerste = False
            indeling = _kolomindeling(list(rij))
            if indeling is not None:
                continue

        if indeling is None:
            waarden = list(rij[:5]) + [None] * max(0, 5 - len(rij))
            waarden = waarden[:5]
        else:
            waarden = [rij[indeling[veld]] if veld in indeling
                       and indeling[veld] < len(rij) else None
                       for veld in VELDVOLGORDE]

        # Een rij is bruikbaar zodra ze een sleutel óf een hoofdcategorie heeft.
        # Zonder die tweede voorwaarde zou een bestand met enkel de
        # boomstructuur volledig weggefilterd worden.
        if _schoon(waarden[0]) or _schoon(waarden[1]):
            rijen.append(tuple(waarden))
    wb.close()
    return rijen


def heeft_sleutels(rijen: list[tuple]) -> bool:
    """Bevat dit bestand de koppeling met de beschrijvingen?

    Zo niet, dan valt er niets uit af te leiden en kan alleen de boomstructuur
    overgenomen worden.
    """
    return any(_schoon(rij[0]) for rij in rijen)


# --------------------------------------------------------------------------
# De sleutel opsplitsen in beschrijving en tegenpartij
# --------------------------------------------------------------------------

def leer_beschrijvingen(rijen: list[tuple], minimum: int = 3,
                        maximale_lengte: int = 45) -> list[str]:
    """Leidt uit de sleutels af welke voorvoegsels beschrijvingen zijn.

    De sleutel is "beschrijving-tegenpartij", maar beide delen kunnen zelf een
    koppelteken bevatten (denk aan "SEPA-domiciliëring"). We tellen daarom per
    mogelijk voorvoegsel hoeveel *verschillende* tegenpartijen erachter staan.
    Een echte verrichtingssoort komt bij veel tegenpartijen voor; een sleutel
    die toevallig op een koppelteken eindigt niet.
    """
    achtervoegsels: dict[str, set[str]] = collections.defaultdict(set)
    for rij in rijen:
        sleutel = _schoon(rij[0])
        positie = sleutel.find("-")
        while positie != -1:
            voorvoegsel = sleutel[:positie]
            if 3 <= len(voorvoegsel) <= maximale_lengte:
                achtervoegsels[voorvoegsel].add(sleutel[positie + 1:])
            positie = sleutel.find("-", positie + 1)

    # Langste eerst, zodat "SEPA-domiciliëring" wint van "SEPA".
    return sorted(
        (voorvoegsel for voorvoegsel, rest in achtervoegsels.items()
         if len(rest) >= minimum),
        key=len, reverse=True,
    )


def splits(sleutel: str, beschrijvingen: list[str]) -> tuple[str, str]:
    """Geeft (beschrijving, tegenpartij) terug voor één sleutel."""
    for voorvoegsel in beschrijvingen:
        if sleutel.startswith(voorvoegsel + "-"):
            return voorvoegsel, sleutel[len(voorvoegsel) + 1:]
    if "-" in sleutel:
        voor, na = sleutel.split("-", 1)
        return voor, na
    return "", sleutel


# --------------------------------------------------------------------------
# Analyse
# --------------------------------------------------------------------------

def analyseer(rijen: list[tuple]) -> Analyse:
    analyse = Analyse(rijen=len(rijen), met_sleutels=heeft_sleutels(rijen))
    beschrijvingen = leer_beschrijvingen(rijen)

    # Hoofdlettergebruik verschilt per regel ("Auto" naast "auto"). We houden
    # per genormaliseerde naam de schrijfwijze aan die het vaakst voorkomt.
    spelling: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    boom: dict[str, dict[str, set]] = collections.defaultdict(
        lambda: collections.defaultdict(set))
    per_partij: dict[str, set] = collections.defaultdict(set)

    for rij in rijen:
        hoofd, cat, sub = _schoon(rij[1]), _schoon(rij[2]), _schoon(rij[3])
        if not hoofd:
            analyse.overgeslagen += 1
            continue
        analyse.bruikbaar += 1
        for naam in (hoofd, cat, sub):
            if naam:
                spelling[normalize(naam)][naam] += 1
        boom[normalize(hoofd)][normalize(cat)].add(normalize(sub))

        _, partij = splits(_schoon(rij[0]), beschrijvingen)
        genormaliseerd = normalize(partij)
        if genormaliseerd:
            per_partij[genormaliseerd].add(
                (normalize(hoofd), normalize(cat), normalize(sub)))

    analyse.hoofdcategorieen = len(boom)
    analyse.categorieen = sum(len([c for c in subs if c]) for subs in boom.values())
    analyse.subcategorieen = sum(
        len([s for s in subsubs if s]) for subs in boom.values() for subsubs in subs.values())
    analyse.sleutelregels = analyse.bruikbaar if analyse.met_sleutels else 0
    analyse.partijregels = sum(1 for paden in per_partij.values() if len(paden) == 1)
    analyse.botsingen = sum(1 for paden in per_partij.values() if len(paden) > 1)

    def mooi(genormaliseerd: str) -> str:
        if not genormaliseerd:
            return ""
        return spelling[genormaliseerd].most_common(1)[0][0]

    analyse.boom = {
        mooi(h): {mooi(c): sorted(mooi(s) for s in ss if s)
                  for c, ss in subs.items() if c}
        for h, subs in sorted(boom.items())
    }
    analyse.voorbeeld_botsingen = [
        partij for partij, paden in per_partij.items() if len(paden) > 1
    ][:12]
    return analyse


# --------------------------------------------------------------------------
# Wegschrijven
# --------------------------------------------------------------------------

def importeer(conn, crypto, rijen: list[tuple], *, vervang: bool = False) -> dict:
    """Zet de categorielijst om in categorieën.

    Met `vervang` worden eerst alle categorieën gewist. Regels en indelingen
    van transacties wijzen naar categorieën, dus die gaan dan mee weg: de
    transacties blijven bestaan maar verliezen hun categorie.
    """
    if vervang:
        conn.execute("UPDATE transacties SET categorie_id=NULL, subcategorie_id=NULL,"
                     " subsub_id=NULL, status='niet_toegewezen', methode='geen',"
                     " regel_id=NULL, nagekeken=0")
        conn.execute("DELETE FROM regels")
        conn.execute("DELETE FROM categorieen")

    spelling: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for rij in rijen:
        for naam in (_schoon(rij[1]), _schoon(rij[2]), _schoon(rij[3])):
            if naam:
                spelling[normalize(naam)][naam] += 1

    def mooi(genormaliseerd: str) -> str:
        return spelling[genormaliseerd].most_common(1)[0][0] if genormaliseerd else ""

    # Bestaande categorieën opzoekbaar maken, zodat aanvullen ook werkt.
    bestaand: dict[tuple[int | None, str], int] = {}
    for row in conn.execute("SELECT id, ouder_id, naam_enc FROM categorieen"):
        bestaand[(row["ouder_id"], normalize(crypto.dec(row["naam_enc"])))] = row["id"]
    aantal_categorieen = len(bestaand)
    volgorde: collections.Counter = collections.Counter()

    def categorie_id(naam_genormaliseerd: str, niveau: int, ouder_id: int | None) -> int | None:
        if not naam_genormaliseerd:
            return None
        sleutel = (ouder_id, naam_genormaliseerd)
        if sleutel in bestaand:
            return bestaand[sleutel]
        naam = mooi(naam_genormaliseerd)
        volgorde[ouder_id] += 1
        cur = conn.execute(
            "INSERT INTO categorieen (ouder_id, niveau, soort, naam_enc, naam_idx, volgorde)"
            " VALUES (?,?,?,?,?,?)",
            (ouder_id, niveau, "beide", crypto.enc(naam), crypto.blind(naam),
             volgorde[ouder_id]),
        )
        bestaand[sleutel] = cur.lastrowid
        return cur.lastrowid

    gezien: set[tuple] = set()
    for rij in rijen:
        hoofd = normalize(_schoon(rij[1]))
        if not hoofd:
            continue
        pad = (hoofd, normalize(_schoon(rij[2])), normalize(_schoon(rij[3])))
        if pad in gezien:
            continue
        gezien.add(pad)
        hid = categorie_id(pad[0], 0, None)
        cid = categorie_id(pad[1], 1, hid)
        if cid:
            categorie_id(pad[2], 2, cid)

    return {"categorieen": len(bestaand) - aantal_categorieen}
