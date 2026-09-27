"""Wat er met de transacties moet gebeuren als een regel verandert.

Een regel verwijderen, uitzetten of bewerken hield voordien op bij de
regeltabel. De transacties die hij ooit had ingedeeld, bleven in hun categorie
staan — met `methode='regel'` en `status='bevestigd'`, waardoor zelfs *Opnieuw
indelen* ze niet meer aanraakte. De indeling bleef dus hangen aan een regel die
niet meer bestond, en de enige uitweg was elke transactie met de hand
terugzetten.

Hier staat de tegenhanger. De werkwijze is overal dezelfde en bestaat uit drie
stappen, in deze volgorde:

1. `hangende_transacties()` — zoek op, zolang de oude regel nog geldt, welke
   transacties aan hem hingen;
2. wijzig de regel: verwijderen, uitzetten of bewerken;
3. `herbekijk()` — laat de regels zoals ze nú zijn opnieuw los op precies die
   transacties.

Die volgorde is wezenlijk: na stap 2 valt niet meer te achterhalen wat er aan de
oude regel hing.

Eén ding blijft bewust ongemoeid:

* wat je zelf hebt ingedeeld (`methode='manueel'`), wat uit een ingelezen
  bestand kwam (`methode='bestand'`) en wat je met *Klopt* bevestigde
  (`nagekeken=1`) — dat blijft hier altijd staan, zie `is_beschermd` — en wat de fuzzy stap of het AI-model heeft
  toegewezen. Alleen een toewijzing die van een regel kwam, gaat weg. De
  uitzondering is een voorstel dat nog niet bevestigd is: een regel die je
  vanuit een transactie maakt, mag een onbevestigde gelijkenis overnemen (zie
  `pas_toe`), en *Alle regels opnieuw toepassen* ook een onbevestigd
  AI-voorstel (zie `herbekijk_alles`).

Winkel en land volgen de indeling. Heeft de motor ze ingevuld — een regel, een
gelijkenis of het AI-model — dan gaan ze mee weg wanneer die indeling
verandert, en krijgt de transactie wat de nieuwe regel zegt, of niets. Tot
versie 0.31.0 bleven ze staan, wat rare combinaties gaf: de winkel van een
oude gelijkenis naast de categorie van een regel. Wat een mens of een bestand
invulde, blijft wel staan (zie `automatische_velden`).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .categorizer.engine import Regelboek, laad_regels, naar_voorstel
from . import backup
from .database import log, now_iso
from .transacties import (NIET_BESCHERMD_SQL, automatische_velden, is_beschermd,
                          rij_naar_object, werk_bij)

WIS_TOELICHTING = "De regel die deze transactie indeelde, bestaat niet meer."
UIT_TOELICHTING = "De regel die deze transactie indeelde, staat uit."
BEWERKT_TOELICHTING = ("De regel die deze transactie indeelde, is aangepast en "
                       "past hier niet meer op.")
GEEN_REGEL_TOELICHTING = "Geen enkele regel past nog op deze transactie."


@dataclass
class Uitkomst:
    """Wat een herbeoordeling met de transacties gedaan heeft."""
    overgenomen: int = 0   # kreeg een andere categorie van een andere regel
    gewist: int = 0        # geen enkele regel past nog: categorie weg, op nazicht
    ongewijzigd: int = 0   # de regel die erop past, wijst nog naar hetzelfde
    erbij: int = 0         # had geen categorie en kreeg er alsnog een
    vervangen: int = 0     # onbevestigde gelijkenis of AI-voorstel, nu door een regel
    bevestigd: int = 0     # zelfde categorie, maar niet langer op nazicht
    velden: int = 0        # zelfde categorie, maar winkel of land rechtgezet


def hangende_transacties(conn, crypto, regel_id: int) -> list[int]:
    """De transacties die door deze regel zijn ingedeeld.

    Staat de regel expliciet bij de transactie, dan is het antwoord zeker. Voor
    rijen van vóór schemaversie 4 staat er niets, en dan blijft alleen de vraag
    over: zou déze regel deze transactie ingedeeld hebben, gegeven de regels
    zoals ze nu staan? Is een andere regel voorgegaan, dan hing ze aan die
    andere en blijft ze met rust.

    Roep dit aan vóór je de regel wijzigt; daarna is zijn definitie weg.
    """
    alle = laad_regels(conn, crypto, alleen_actief=False)
    deze = next((r for r in alle if r.id == regel_id), None)
    andere = [r for r in laad_regels(conn, crypto) if r.id != regel_id]
    # Zoals het nú is: de regels die gelden, plus degene die gaat veranderen.
    boek = Regelboek(andere + ([deze] if deze is not None else []))

    gevonden = []
    for row in conn.execute(
        "SELECT * FROM transacties WHERE methode = 'regel'"
        " AND (regel_id = ? OR regel_id IS NULL)", (regel_id,)
    ):
        if row["regel_id"] is not None:
            gevonden.append(row["id"])
            continue
        if deze is None:
            continue
        tx = rij_naar_object(row, crypto)
        gekozen = boek.beste(tx.kenmerken)
        if gekozen is not None and gekozen.id == regel_id:
            gevonden.append(row["id"])
    return gevonden


def herbekijk(conn, crypto, tx_ids: list[int], *,
              toelichting: str = WIS_TOELICHTING) -> Uitkomst:
    """Laat de regels zoals ze nu zijn opnieuw los op deze transacties.

    Past er nog een regel op, dan neemt die het over. Past er geen enkele meer
    op, dan gaat de categorie weg en komt de transactie op *nazicht* te staan,
    zodat ze in het nazichtscherm opduikt in plaats van stilletjes ergens
    onderaan een lijst te belanden.

    Wijst de passende regel nog naar dezelfde categorie, dan wordt er niets
    aangepast aan de indeling. Wel wordt dan alsnog vastgelegd wélke regel het
    is, voor rijen van vóór schemaversie 4 waar dat nog nergens stond, en
    krijgen winkel en land wat die regel zegt als de motor ze invulde.
    """
    uit = Uitkomst()
    if not tx_ids:
        return uit
    boek = Regelboek(laad_regels(conn, crypto))

    for tx_id in tx_ids:
        row = conn.execute("SELECT * FROM transacties WHERE id = ?", (tx_id,)).fetchone()
        if row is None or row["methode"] != "regel" or is_beschermd(row):
            # Ondertussen zelf ingedeeld, met Klopt bevestigd, of verwijderd:
            # afblijven.
            continue
        tx = rij_naar_object(row, crypto)
        vervanger = boek.beste(tx.kenmerken)

        if vervanger is None:
            werk_bij(
                conn, crypto, tx.id,
                categorie_id=None, subcategorie_id=None, subsub_id=None,
                **automatische_velden(row, crypto),
                zekerheid=0.0, methode="geen", status="nazicht",
                toelichting=toelichting, regel_id=None,
            )
            uit.gewist += 1
            continue

        zelfde = (vervanger.categorie_id == row["categorie_id"]
                  and vervanger.subcategorie_id == row["subcategorie_id"]
                  and vervanger.subsub_id == row["subsub_id"])
        if zelfde:
            voorstel = naar_voorstel(vervanger)
            # Winkel en land zoals deze regel ze wil. Stond er nog iets van een
            # gelijkenis of van een vorige regel, dan gaat dat nu weg.
            velden = automatische_velden(row, crypto, voorstel)
            veldwerk = {}
            if (velden["handelaar"] != tx.handelaar or velden["land"] != tx.land
                    or velden["auto_velden"] != row["auto_velden"]):
                veldwerk = velden
            if row["status"] == "nazicht" and voorstel.status == "bevestigd":
                # Zelfde categorie, maar de regel is ondertussen zeker
                # geworden (bewerkt of bevestigd). Dan hoeft de transactie
                # niet langer op nazicht te wachten, en moet de oude uitleg
                # ("wijst naar meer dan één categorie") ook weg.
                werk_bij(
                    conn, crypto, tx.id,
                    zekerheid=voorstel.zekerheid, status=voorstel.status,
                    toelichting=voorstel.toelichting, regel_id=vervanger.id,
                    **veldwerk,
                )
                uit.bevestigd += 1
                continue
            # De indeling klopt al. De band met de regel vastleggen, en winkel
            # en land rechtzetten als die niet bij deze regel horen.
            if row["regel_id"] != vervanger.id or veldwerk:
                werk_bij(conn, crypto, tx.id, regel_id=vervanger.id, **veldwerk)
            if veldwerk:
                uit.velden += 1
            else:
                uit.ongewijzigd += 1
            continue

        voorstel = naar_voorstel(vervanger)
        werk_bij(
            conn, crypto, tx.id,
            categorie_id=voorstel.categorie_id,
            subcategorie_id=voorstel.subcategorie_id,
            subsub_id=voorstel.subsub_id,
            **automatische_velden(row, crypto, voorstel),
            zekerheid=voorstel.zekerheid,
            methode=voorstel.methode,
            status=voorstel.status,
            toelichting=voorstel.toelichting,
            regel_id=vervanger.id,
        )
        uit.overgenomen += 1
    return uit


# Wat `pas_toe` mag aanraken. Een gelijkenis die nog niet bevestigd is, is een
# gok van de motor die op jouw oordeel wacht; een regel die je zelf opstelt is
# precies dat oordeel. Een automatisch bevestigde gelijkenis blijft wel staan:
# daarvoor is er *Opnieuw indelen › Automatisch bevestigde gelijkenissen*.
ZONDER_CATEGORIE_SQL = "(categorie_id IS NULL AND methode IN ('geen', 'regel'))"
ONBEVESTIGDE_GELIJKENIS_SQL = "(methode = 'fuzzy' AND status <> 'bevestigd')"
# Een AI-voorstel staat altijd op nazicht tot je het met *Klopt* bevestigt, en
# dan is het nagekeken en dus beschermd. De statusvoorwaarde staat er toch, voor
# het geval dat ooit verandert.
ONBEVESTIGD_AI_SQL = "(methode = 'ai' AND status <> 'bevestigd')"


def pas_toe_geteld(conn, crypto, regel_id: int | None = None, *,
                   ook_onbevestigde_gelijkenis: bool = False,
                   ook_onbevestigd_ai: bool = False) -> Counter:
    """Laat de regels los en telt per soort wat er een categorie kreeg.

    De sleutels van de telling zijn `zonder` (had geen categorie),
    `gelijkenis` (had een nog niet bevestigde gelijkenis, die nu vervangen is
    door de regel) en `ai` (had een nog niet bevestigd AI-voorstel). Zie
    `pas_toe` voor wat er wel en niet geraakt wordt.
    """
    telling: Counter = Counter()
    regels = laad_regels(conn, crypto)
    if regel_id is not None:
        regels = [r for r in regels if r.id == regel_id]
    if not regels:
        return telling
    boek = Regelboek(regels)

    delen = [ZONDER_CATEGORIE_SQL]
    if ook_onbevestigde_gelijkenis:
        delen.append(ONBEVESTIGDE_GELIJKENIS_SQL)
    if ook_onbevestigd_ai:
        delen.append(ONBEVESTIGD_AI_SQL)
    waar = "(" + " OR ".join(delen) + ")"
    rijen = conn.execute(
        f"SELECT * FROM transacties WHERE {waar} AND {NIET_BESCHERMD_SQL}"
    ).fetchall()

    for row in rijen:
        if is_beschermd(row):
            continue
        tx = rij_naar_object(row, crypto)
        regel = boek.beste(tx.kenmerken)
        if regel is None:
            continue
        voorstel = naar_voorstel(regel)
        werk_bij(
            conn, crypto, tx.id,
            categorie_id=voorstel.categorie_id,
            subcategorie_id=voorstel.subcategorie_id,
            subsub_id=voorstel.subsub_id,
            zekerheid=voorstel.zekerheid,
            methode=voorstel.methode,
            status=voorstel.status,
            toelichting=voorstel.toelichting,
            regel_id=regel.id,
            # De gelijkenis bracht een winkel en een land mee van de transactie
            # waarop ze leek, het AI-model deed hetzelfde. Die horen bij die
            # gok en gaan mee weg; de transactie krijgt wat de regel zegt, of
            # niets als de regel er niets over zegt.
            **automatische_velden(row, crypto, voorstel),
        )
        telling[{"fuzzy": "gelijkenis", "ai": "ai"}.get(row["methode"], "zonder")] += 1
    return telling


def pas_toe(conn, crypto, regel_id: int | None = None, *,
            ook_onbevestigde_gelijkenis: bool = False,
            ook_onbevestigd_ai: bool = False) -> int:
    """Laat de regels los op wat nog geen categorie heeft.

    Met een `regel_id` alleen die ene regel — voor wanneer je hem weer aanzet,
    of hem zo bewerkt dat hij breder wordt. Zonder, alle actieve regels samen.

    Raakt standaard alleen transacties zonder categorie. Met
    `ook_onbevestigde_gelijkenis` ook die met een gelijkenis die nog op
    nazicht staat — dat gebeurt wanneer je vanuit een transactie een regel
    maakt. Met `ook_onbevestigd_ai` ook een AI-voorstel dat nog op nazicht
    staat. Wat met de hand of uit een bestand is ingedeeld, blijft hoe dan
    ook staan, net als wat al bevestigd of nagekeken is.
    """
    return sum(pas_toe_geteld(
        conn, crypto, regel_id,
        ook_onbevestigde_gelijkenis=ook_onbevestigde_gelijkenis,
        ook_onbevestigd_ai=ook_onbevestigd_ai).values())


def herbekijk_alles(conn, crypto) -> Uitkomst:
    """Alle regels opnieuw toepassen op alles wat door een regel is ingedeeld.

    Bedoeld voor wanneer je prioriteiten hebt verschoven of meerdere regels na
    elkaar hebt aangepast. Het losmaken bij één regel kijkt namelijk alleen naar
    wat aan díe regel hing: een transactie die correct aan een andere regel
    hangt, blijft daar hangen, ook als jouw aangepaste regel nu voorgaat.

    Daarna gaan de regels ook over alles wat nog op een oordeel wacht: wat
    geen categorie heeft, en een gelijkenis of AI-voorstel dat nog niet
    bevestigd is. Past er een regel, dan neemt die het over. Tot versie 0.30.1
    bleef zo'n onbevestigd voorstel hier staan, ook als er intussen een regel
    was die er precies op paste.

    Dit is een grove ingreep — ze loopt over je hele boekhouding — en staat
    daarom achter een aparte knop. Wat blijft staan: wat je zelf hebt
    ingedeeld, wat uit een ingelezen bestand kwam, wat je met *Klopt*
    bevestigde (`is_beschermd`), en een gelijkenis die de motor zelf zeker
    genoeg vond om te bevestigen — die herbekijk je met *Opnieuw indelen ›
    Automatisch bevestigde gelijkenissen*.
    """
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM transacties WHERE methode = 'regel'")]
    uit = herbekijk(conn, crypto, ids, toelichting=GEEN_REGEL_TOELICHTING)
    telling = pas_toe_geteld(conn, crypto, ook_onbevestigde_gelijkenis=True,
                             ook_onbevestigd_ai=True)
    uit.erbij = telling["zonder"]
    uit.vervangen = telling["gelijkenis"] + telling["ai"]
    return uit


def pas_alle_regels_opnieuw_toe(conn, crypto, gebruiker: str) -> Uitkomst:
    """De knop *Alle regels opnieuw toepassen*, bij de regels en in het nazicht.

    Legt eerst een kopie van de databank, voert `herbekijk_alles` uit en
    schrijft het resultaat in het logboek. Vastleggen (commit) doet de
    aanroeper.
    """
    backup.maak("regels_opnieuw")
    uit = herbekijk_alles(conn, crypto)
    log(conn, crypto, gebruiker, "regels opnieuw toegepast",
        f"gewist={uit.gewist} anders={uit.overgenomen} erbij={uit.erbij}"
        f" vervangen={uit.vervangen} velden={uit.velden}")
    return uit


def veranderd(uit: Uitkomst) -> int:
    """Hoeveel transacties er werkelijk iets veranderde."""
    return uit.gewist + uit.overgenomen + uit.erbij + uit.vervangen + uit.bevestigd + uit.velden


def verslag(uit: Uitkomst) -> str:
    """Eén zin over wat er met de transacties gebeurd is."""
    stukken = []
    if uit.gewist:
        stukken.append(
            f"{uit.gewist} {'transactie staat' if uit.gewist == 1 else 'transacties staan'}"
            " nu op nazicht zonder categorie")
    if uit.overgenomen:
        stukken.append(f"{uit.overgenomen} {'kreeg' if uit.overgenomen == 1 else 'kregen'}"
                       " een andere categorie van een andere regel")
    if uit.erbij:
        stukken.append(f"{uit.erbij} {'kreeg' if uit.erbij == 1 else 'kregen'}"
                       " er alsnog een categorie bij")
    if uit.vervangen:
        stukken.append(f"{uit.vervangen} onbevestigde "
                       f"{'gelijkenis of AI-voorstel werd' if uit.vervangen == 1 else 'gelijkenissen of AI-voorstellen werden'}"
                       " vervangen door een regel")
    if uit.bevestigd:
        stukken.append(f"{uit.bevestigd} {'staat' if uit.bevestigd == 1 else 'staan'}"
                       " niet langer op nazicht")
    if uit.velden:
        stukken.append(f"bij {uit.velden} {'transactie' if uit.velden == 1 else 'transacties'}"
                       " werden winkel of land rechtgezet")
    if not stukken:
        if uit.ongewijzigd:
            return (f"{uit.ongewijzigd} "
                    f"{'transactie hangt' if uit.ongewijzigd == 1 else 'transacties hangen'}"
                    " aan een regel en die wijst nog altijd naar dezelfde categorie.")
        return "Er veranderde niets aan je transacties."
    zin = " en ".join(stukken) + "."
    zin = zin[0].upper() + zin[1:]
    if uit.ongewijzigd:
        zin += f" {uit.ongewijzigd} bleven staan zoals ze stonden."
    return zin


# --------------------------------------------------------------------------
# Onzekere regels die je al zelf hebt rechtgezet
# --------------------------------------------------------------------------

def maak_zeker(conn, regel_id: int) -> bool:
    """Haalt het merkteken "wees naar meer dan één categorie" van een regel.

    Een regel uit je historiek of uit de referentielijst die naar meer dan één
    categorie wees, krijgt een herkomst die op `_onzeker` eindigt: ze deelt in,
    maar vraagt telkens om nazicht. Heb je ze zelf bewerkt of bevestigd, dan
    heb jij de keuze gemaakt en is die twijfel voorbij.

    Geeft terug of er iets veranderde.
    """
    return conn.execute(
        "UPDATE regels SET herkomst = REPLACE(herkomst, '_onzeker', '')"
        " WHERE id = ? AND herkomst LIKE '%\\_onzeker' ESCAPE '\\'",
        (regel_id,),
    ).rowcount > 0


HERSTEL_SLEUTEL = "herstel_onzeker_na_bewerken"


def herstel_bewerkte_onzekere_regels(conn, crypto) -> Uitkomst | None:
    """Eenmalig: onzekere regels die je vóór versie 0.21.0 al bewerkt hebt.

    Tot die versie liet het bewerken van een regel het merkteken `_onzeker`
    staan. De regel wees dan naar één categorie, maar bleef toch om nazicht
    vragen. Welke regels je bewerkt hebt, staat in het logboek; dat is
    versleuteld, en daarom gebeurt dit pas wanneer iemand aangemeld is en niet
    bij het opstarten.

    Alleen logregels van ná het aanmaken van de regel tellen: een regel uit de
    historiek wordt bij het opnieuw afleiden gewist en opnieuw aangemaakt, en
    kan dan het nummer van een eerder bewerkte regel krijgen.

    Geeft None terug als dit al eerder gebeurd is.
    """
    if conn.execute("SELECT 1 FROM app_meta WHERE sleutel = ?",
                    (HERSTEL_SLEUTEL,)).fetchone():
        return None

    onzeker = {
        r["id"]: r["aangemaakt_op"] for r in conn.execute(
            "SELECT id, aangemaakt_op FROM regels"
            " WHERE herkomst LIKE '%\\_onzeker' ESCAPE '\\'")
    }
    te_herstellen: set[int] = set()
    if onzeker:
        for rij in conn.execute(
                "SELECT tijdstip, detail_enc FROM logboek WHERE actie = 'regel bewerkt'"):
            gevonden = re.search(r"regel=(\d+)", crypto.dec(rij["detail_enc"]) or "")
            if not gevonden:
                continue
            regel_id = int(gevonden.group(1))
            if regel_id in onzeker and rij["tijdstip"] >= (onzeker[regel_id] or ""):
                te_herstellen.add(regel_id)

    uit = Uitkomst()
    for regel_id in sorted(te_herstellen):
        hingen = hangende_transacties(conn, crypto, regel_id)
        maak_zeker(conn, regel_id)
        deel = herbekijk(conn, crypto, hingen, toelichting=BEWERKT_TOELICHTING)
        for veld in ("overgenomen", "gewist", "ongewijzigd", "bevestigd", "velden"):
            setattr(uit, veld, getattr(uit, veld) + getattr(deel, veld))

    conn.execute("INSERT INTO app_meta (sleutel, waarde) VALUES (?, ?)",
                 (HERSTEL_SLEUTEL, f"{now_iso()} regels={len(te_herstellen)}"))
    conn.commit()
    return uit if te_herstellen else None
