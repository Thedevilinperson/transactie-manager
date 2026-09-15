"""Een referentielijst afleiden uit de transacties die al ingedeeld zijn.

Waar `referentie.py` een bestaand categorieënbestand inleest, werkt deze module
de andere kant op: ze kijkt naar wat er al bevestigd in de databank staat en
leidt daar regels uit af.

Het verschil met een lijst op basis van enkel beschrijving en tegenpartij is dat
hier alle bruikbare velden meedoen. Elk veld levert een eigen soort aanwijzing,
en die verschillen sterk in betrouwbaarheid:

| Aanwijzing                       | Waarom ze werkt                                  |
|----------------------------------|--------------------------------------------------|
| Rekeningnummer van de tegenpartij | Een IBAN hoort bij één partij en verandert niet. Sterkste signaal. |
| Gestructureerde mededeling        | Het `+++...+++`-nummer hoort bij één schuldeiser en één soort betaling. |
| Beschrijving plus tegenpartij     | Onderscheidt een aankoop bij een winkel van een overschrijving aan dezelfde naam. |
| Tegenpartij alleen                | Breed inzetbaar, maar botst wanneer één zaak meerdere posten dekt. |
| Tegenpartij plus bedragvork       | Redt precies die botsingen: tanken tegenover een broodje bij hetzelfde tankstation. |

Een aanwijzing wordt alleen een regel wanneer ze in de hele historiek naar
dezelfde indeling verwijst. Wijst ze naar meerdere, dan proberen we eerst of
het bedrag de gevallen scheidt. Lukt dat niet, dan komt er een regel die als
onzeker gemarkeerd staat: die deelt wel voorlopig in, maar stuurt de transactie
naar het nazicht in plaats van ze blind te bevestigen.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from decimal import Decimal

from ..crypto import normalize, normalize_iban
from ..database import now_iso
from ..transacties import rij_naar_object

# Lage prioriteit gaat voor. De volgorde weerspiegelt hoe hard het signaal is.
PRIORITEIT = {
    "tegenpartij_rekening": 20,
    "mededeling": 30,
    "sleutel": 40,
    "tegenpartij_naam_bedrag": 50,
    "tegenpartij_naam": 60,
    "onzeker": 90,
}

VELDNAAM = {
    "tegenpartij_rekening": "rekeningnummer tegenpartij",
    "mededeling": "gestructureerde mededeling",
    "sleutel": "beschrijving en tegenpartij",
    "tegenpartij_naam_bedrag": "tegenpartij met bedragvork",
    "tegenpartij_naam": "tegenpartij",
}

GESTRUCTUREERD = re.compile(r"\+{3}\d{3}/\d{4}/\d{5}\+{3}|\*{3}\d{3}/\d{4}/\d{5}\*{3}")

# Onder dit aantal waarnemingen leiden we niets af uit een botsing: te weinig
# om te zien of het bedrag de gevallen echt scheidt.
MINIMUM_VOOR_BEDRAGSPLITSING = 4


@dataclass
class Aanwijzing:
    veld: str
    waarde: str
    paden: dict = field(default_factory=dict)          # pad -> aantal
    bedragen: dict = field(default_factory=dict)       # pad -> lijst bedragen
    handelaar: str = ""
    land: str = ""
    richting: str = ""


@dataclass
class Voorstelregel:
    veld: str
    waarde: str
    pad: tuple
    prioriteit: int
    aantal: int
    bedrag_min: float | None = None
    bedrag_max: float | None = None
    richting: str | None = None
    handelaar: str = ""
    land: str = ""
    onzeker: bool = False
    uitleg: str = ""


@dataclass
class Analyse:
    transacties: int = 0
    regels: list = field(default_factory=list)
    per_veld: dict = field(default_factory=dict)
    onzeker: int = 0
    botsingen_opgelost: int = 0
    voorbeelden_bedragsplitsing: list = field(default_factory=list)


# --------------------------------------------------------------------------
# Verzamelen
# --------------------------------------------------------------------------

def _aanwijzingen(conn, crypto, alleen_bevestigd: bool = True) -> dict:
    sql = ("SELECT * FROM transacties WHERE categorie_id IS NOT NULL"
           " AND is_afrekening = 0")
    if alleen_bevestigd:
        sql += " AND status = 'bevestigd'"

    verzameld: dict[tuple, Aanwijzing] = {}
    aantal = 0

    for row in conn.execute(sql):
        tx = rij_naar_object(row, crypto)
        aantal += 1
        pad = (tx.categorie_id, tx.subcategorie_id, tx.subsub_id)
        bedrag = abs(tx.bedrag)

        kandidaten: list[tuple[str, str]] = []
        if tx.tegenpartij_rekening:
            iban = normalize_iban(tx.tegenpartij_rekening)
            if len(iban) >= 8:
                kandidaten.append(("tegenpartij_rekening", iban))
        gestructureerd = GESTRUCTUREERD.search(tx.mededeling or "")
        if gestructureerd:
            kandidaten.append(("mededeling", gestructureerd.group(0)))
        if tx.beschrijving and tx.tegenpartij_naam:
            kandidaten.append(("sleutel", f"{tx.beschrijving}-{tx.tegenpartij_naam}"))
        if tx.tegenpartij_naam:
            kandidaten.append(("tegenpartij_naam", tx.tegenpartij_naam))

        for veld, waarde in kandidaten:
            sleutel = (veld, normalize(waarde) if veld != "tegenpartij_rekening" else waarde)
            aanwijzing = verzameld.get(sleutel)
            if aanwijzing is None:
                aanwijzing = Aanwijzing(veld=veld, waarde=waarde, richting=tx.richting)
                verzameld[sleutel] = aanwijzing
            aanwijzing.paden[pad] = aanwijzing.paden.get(pad, 0) + 1
            aanwijzing.bedragen.setdefault(pad, []).append(bedrag)
            if tx.handelaar and not aanwijzing.handelaar:
                aanwijzing.handelaar = tx.handelaar
            if tx.land and not aanwijzing.land:
                aanwijzing.land = tx.land
            if aanwijzing.richting != tx.richting:
                aanwijzing.richting = ""      # komt in beide richtingen voor

    return {"aanwijzingen": verzameld, "transacties": aantal}


# --------------------------------------------------------------------------
# Botsingen oplossen met het bedrag
# --------------------------------------------------------------------------

def _bedragsplitsing(aanwijzing: Aanwijzing) -> list[Voorstelregel] | None:
    """Kijkt of het bedrag twee indelingen netjes uit elkaar houdt.

    Dit is het geval van het tankstation: kleine bedragen zijn een broodje, grote
    bedragen zijn brandstof. Alleen wanneer de twee reeksen elkaar niet
    overlappen leggen we er een grens tussen.
    """
    if len(aanwijzing.paden) != 2:
        return None
    if sum(aanwijzing.paden.values()) < MINIMUM_VOOR_BEDRAGSPLITSING:
        return None

    (pad_a, lijst_a), (pad_b, lijst_b) = aanwijzing.bedragen.items()
    if not lijst_a or not lijst_b:
        return None
    laag, hoog = (pad_a, lijst_a), (pad_b, lijst_b)
    if min(lijst_a) > min(lijst_b):
        laag, hoog = (pad_b, lijst_b), (pad_a, lijst_a)

    if max(laag[1]) >= min(hoog[1]):
        return None      # de reeksen overlappen: het bedrag scheidt niets

    # De grens ligt tussen de twee reeksen, afgerond op een heel getal.
    grens = (Decimal(max(laag[1])) + Decimal(min(hoog[1]))) / 2
    grens = float(round(grens))
    if grens <= 0:
        return None

    gemeen = {
        "veld": "tegenpartij_naam_bedrag",
        "waarde": aanwijzing.waarde,
        "prioriteit": PRIORITEIT["tegenpartij_naam_bedrag"],
        "richting": aanwijzing.richting or None,
        "handelaar": aanwijzing.handelaar,
        "land": aanwijzing.land,
    }
    return [
        Voorstelregel(pad=laag[0], aantal=len(laag[1]), bedrag_max=grens,
                      uitleg=f"onder {grens:.0f} euro", **gemeen),
        Voorstelregel(pad=hoog[0], aantal=len(hoog[1]), bedrag_min=grens,
                      uitleg=f"vanaf {grens:.0f} euro", **gemeen),
    ]


# --------------------------------------------------------------------------
# Analyse
# --------------------------------------------------------------------------

def analyseer(conn, crypto, alleen_bevestigd: bool = True) -> Analyse:
    verzameld = _aanwijzingen(conn, crypto, alleen_bevestigd)
    analyse = Analyse(transacties=verzameld["transacties"])
    per_veld: collections.Counter = collections.Counter()

    # Een tegenpartij die al via een harder signaal geregeld is, hoeft geen
    # brede regel meer. Dat scheelt ruis in de lijst.
    for aanwijzing in verzameld["aanwijzingen"].values():
        if len(aanwijzing.paden) == 1:
            pad = next(iter(aanwijzing.paden))
            analyse.regels.append(Voorstelregel(
                veld=aanwijzing.veld, waarde=aanwijzing.waarde, pad=pad,
                prioriteit=PRIORITEIT[aanwijzing.veld],
                aantal=aanwijzing.paden[pad],
                richting=aanwijzing.richting or None,
                handelaar=aanwijzing.handelaar, land=aanwijzing.land,
            ))
            per_veld[aanwijzing.veld] += 1
            continue

        gesplitst = (_bedragsplitsing(aanwijzing)
                     if aanwijzing.veld == "tegenpartij_naam" else None)
        if gesplitst:
            analyse.regels.extend(gesplitst)
            per_veld["tegenpartij_naam_bedrag"] += len(gesplitst)
            analyse.botsingen_opgelost += 1
            if len(analyse.voorbeelden_bedragsplitsing) < 8:
                analyse.voorbeelden_bedragsplitsing.append(
                    f"{aanwijzing.waarde[:40]} ({gesplitst[0].uitleg} / "
                    f"{gesplitst[1].uitleg})")
            continue

        # Blijft botsen: de vaakst voorkomende indeling, maar gemarkeerd.
        pad = max(aanwijzing.paden.items(), key=lambda p: p[1])[0]
        analyse.regels.append(Voorstelregel(
            veld=aanwijzing.veld, waarde=aanwijzing.waarde, pad=pad,
            prioriteit=PRIORITEIT["onzeker"], aantal=aanwijzing.paden[pad],
            richting=aanwijzing.richting or None,
            handelaar=aanwijzing.handelaar, land=aanwijzing.land, onzeker=True,
        ))
        analyse.onzeker += 1

    analyse.per_veld = {VELDNAAM.get(k, k): v for k, v in per_veld.items()}
    return analyse


# --------------------------------------------------------------------------
# Wegschrijven
# --------------------------------------------------------------------------

def schrijf(conn, crypto, analyse: Analyse, *, vervang_geleerd: bool = True) -> dict:
    """Zet de voorgestelde regels in de databank.

    `vervang_geleerd` verwijdert alleen wat een vorige keer uit de historiek is
    afgeleid. Regels die je zelf hebt ingevoerd of die uit een categorieënbestand
    komen, blijven staan.
    """
    if vervang_geleerd:
        conn.execute("DELETE FROM regels WHERE herkomst IN ('historiek', 'historiek_onzeker')")

    tijdstip = now_iso()
    geschreven = 0
    for regel in analyse.regels:
        veld = "tegenpartij_naam" if regel.veld == "tegenpartij_naam_bedrag" else regel.veld
        naam = f"{VELDNAAM.get(regel.veld, regel.veld)}: {regel.waarde[:50]}"
        if regel.uitleg:
            naam += f" ({regel.uitleg})"
        waarde_idx = (regel.waarde if veld == "tegenpartij_rekening"
                      else normalize(regel.waarde))
        conn.execute(
            "INSERT INTO regels (naam_enc, prioriteit, veld, operator, waarde_enc,"
            " waarde_idx, bedrag_min, bedrag_max, richting, categorie_id,"
            " subcategorie_id, subsub_id, handelaar_enc, land_enc, herkomst,"
            " aangemaakt_op) VALUES (?,?,?,'gelijk',?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                crypto.enc(naam), regel.prioriteit, veld,
                crypto.enc(regel.waarde), crypto.blind(waarde_idx),
                regel.bedrag_min, regel.bedrag_max, regel.richting,
                regel.pad[0], regel.pad[1], regel.pad[2],
                crypto.enc(regel.handelaar) if regel.handelaar else None,
                crypto.enc(regel.land) if regel.land else None,
                "historiek_onzeker" if regel.onzeker else "historiek",
                tijdstip,
            ),
        )
        geschreven += 1

    return {"regels": geschreven, "onzeker": analyse.onzeker,
            "bedragsplitsingen": analyse.botsingen_opgelost}
