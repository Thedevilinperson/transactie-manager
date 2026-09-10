"""Inlezen van de referentielijst met categorieën.

Het bestand `categorieën.xlsx` bevat per regel:

| kolom | inhoud                                                      |
|-------|-------------------------------------------------------------|
| A     | referentiesleutel: beschrijving en tegenpartij, met `-` ertussen |
| B     | hoofdcategorie                                              |
| C     | categorie (eerste subniveau)                                |
| D     | subcategorie (tweede subniveau)                             |
| E     | winkel, of bij vakantie het land van bestemming             |

Uit dat bestand worden twee dingen opgebouwd:

1. de categorieboom van drie niveaus;
2. de regels waarmee de motor transacties indeelt.

Per sleutel komt er een regel die exact op die sleutel past. Daarnaast komt er
een bredere regel op enkel de tegenpartij, maar alleen wanneer die tegenpartij
in het hele bestand naar één en dezelfde indeling verwijst. Zo verhindert een
tegenpartij die soms bij boodschappen en soms bij vakantie hoort dat er een
verkeerde regel ontstaat.
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

# Deze kolomkoppen worden herkend; de volgorde telt, niet de exacte naam.
VERWACHTE_KOP = ["sleutel", "hoofdcategorie", "categorie", "subcategorie", "winkel"]


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
    partijregels: int = 0
    botsingen: int = 0
    boom: dict = field(default_factory=dict)
    voorbeeld_botsingen: list = field(default_factory=list)


def lees(pad: Path) -> list[tuple]:
    """Leest het werkblad uit als lijst van vijf kolommen."""
    from openpyxl import load_workbook

    wb = load_workbook(pad, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rijen = []
    for i, rij in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            kop = [str(c or "").strip().lower() for c in rij[:5]]
            # Een kopregel herkennen we aan het woord "hoofdcategorie".
            if any("hoofdcategorie" in c for c in kop):
                continue
        waarden = list(rij[:5]) + [None] * max(0, 5 - len(rij))
        if _schoon(waarden[0]):
            rijen.append(tuple(waarden[:5]))
    wb.close()
    return rijen


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
    analyse = Analyse(rijen=len(rijen))
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
    analyse.sleutelregels = analyse.bruikbaar
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

def importeer(conn, crypto, rijen: list[tuple], *, vervang: bool = True,
              maak_partijregels: bool = True) -> dict:
    """Zet de referentielijst om in categorieën en regels."""
    beschrijvingen = leer_beschrijvingen(rijen)

    if vervang:
        conn.execute("UPDATE transacties SET categorie_id=NULL, subcategorie_id=NULL,"
                     " subsub_id=NULL, status='niet_toegewezen', methode='geen'")
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

    # Eerst de boom, dan de regels.
    paden: dict[tuple, tuple] = {}
    per_partij: dict[str, set] = collections.defaultdict(set)
    telling_per_partij: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)
    partij_gegevens: dict[str, tuple] = {}
    aantal_categorieen = len(bestaand)

    def ids_van(alle_paden, gevonden):
        return alle_paden[next(iter(gevonden))]

    for rij in rijen:
        hoofd = normalize(_schoon(rij[1]))
        if not hoofd:
            continue
        cat = normalize(_schoon(rij[2]))
        sub = normalize(_schoon(rij[3]))
        pad = (hoofd, cat, sub)
        if pad not in paden:
            hid = categorie_id(hoofd, 0, None)
            cid = categorie_id(cat, 1, hid)
            sid = categorie_id(sub, 2, cid) if cid else None
            paden[pad] = (hid, cid, sid)

        _, partij = splits(_schoon(rij[0]), beschrijvingen)
        genormaliseerd = normalize(partij)
        if genormaliseerd:
            per_partij[genormaliseerd].add(pad)
            telling_per_partij[genormaliseerd][pad] += 1
            partij_gegevens[genormaliseerd] = (partij, _schoon(rij[4]))

    tijdstip = now_iso()
    gemaakt_sleutel = gemaakt_partij = 0

    def regel(naam, prioriteit, veld, waarde, ids, winkel, herkomst):
        conn.execute(
            "INSERT INTO regels (naam_enc, prioriteit, veld, operator, waarde_enc, waarde_idx,"
            " categorie_id, subcategorie_id, subsub_id, handelaar_enc, herkomst, aangemaakt_op)"
            " VALUES (?,?,?,'gelijk',?,?,?,?,?,?,?,?)",
            (crypto.enc(naam), prioriteit, veld,
             crypto.enc(waarde), crypto.blind(normalize(waarde)),
             ids[0], ids[1], ids[2],
             crypto.enc(winkel) if winkel else None, herkomst, tijdstip),
        )

    gezien_sleutels: set[str] = set()
    for rij in rijen:
        sleutel = _schoon(rij[0])
        hoofd = normalize(_schoon(rij[1]))
        if not hoofd or not sleutel:
            continue
        genormaliseerd = normalize(sleutel)
        if genormaliseerd in gezien_sleutels:
            continue
        gezien_sleutels.add(genormaliseerd)
        ids = paden[(hoofd, normalize(_schoon(rij[2])), normalize(_schoon(rij[3])))]
        regel(sleutel[:80], 10, "sleutel", sleutel, ids, _schoon(rij[4]), "referentie")
        gemaakt_sleutel += 1

    gemaakt_onzeker = 0
    if maak_partijregels:
        for genormaliseerd, gevonden in per_partij.items():
            oorspronkelijk, winkel = partij_gegevens[genormaliseerd]
            if len(gevonden) == 1:
                regel(f"Tegenpartij {oorspronkelijk[:60]}", 60, "tegenpartij_naam",
                      oorspronkelijk, ids_van(paden, gevonden), winkel, "referentie")
                gemaakt_partij += 1
            else:
                # Deze tegenpartij hoort in de lijst bij meer dan één categorie.
                # We leggen wel een regel aan, maar gemarkeerd als onzeker, zodat
                # de transactie in het nazicht belandt in plaats van blind te
                # worden toegewezen.
                keuze = telling_per_partij[genormaliseerd].most_common(1)[0][0]
                regel(f"Tegenpartij {oorspronkelijk[:60]}", 90, "tegenpartij_naam",
                      oorspronkelijk, paden[keuze], winkel, "referentie_onzeker")
                gemaakt_onzeker += 1

    return {
        "categorieen": len(bestaand) - aantal_categorieen,
        "sleutelregels": gemaakt_sleutel,
        "partijregels": gemaakt_partij,
        "onzekere_regels": gemaakt_onzeker,
        "botsingen": sum(1 for paden_ in per_partij.values() if len(paden_) > 1),
    }
