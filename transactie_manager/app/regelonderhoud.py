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

Twee dingen blijven bewust ongemoeid:

* wat je zelf hebt ingedeeld (`methode='manueel'`) en wat de fuzzy stap of het
  AI-model heeft toegewezen. Alleen een toewijzing die van een regel kwam, gaat
  weg;
* handelaar en land. Die staan los van de indeling, en een regel is meestal niet
  de enige plek waar ze vandaan komen.
"""

from __future__ import annotations

from dataclasses import dataclass

from .categorizer.engine import Regelboek, laad_regels, naar_voorstel
from .transacties import rij_naar_object, werk_bij

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
    is, voor rijen van vóór schemaversie 4 waar dat nog nergens stond.
    """
    uit = Uitkomst()
    if not tx_ids:
        return uit
    boek = Regelboek(laad_regels(conn, crypto))

    for tx_id in tx_ids:
        row = conn.execute("SELECT * FROM transacties WHERE id = ?", (tx_id,)).fetchone()
        if row is None or row["methode"] != "regel":
            # Ondertussen zelf ingedeeld of verwijderd: afblijven.
            continue
        tx = rij_naar_object(row, crypto)
        vervanger = boek.beste(tx.kenmerken)

        if vervanger is None:
            werk_bij(
                conn, crypto, tx.id,
                categorie_id=None, subcategorie_id=None, subsub_id=None,
                zekerheid=0.0, methode="geen", status="nazicht",
                toelichting=toelichting, regel_id=None,
            )
            uit.gewist += 1
            continue

        zelfde = (vervanger.categorie_id == row["categorie_id"]
                  and vervanger.subcategorie_id == row["subcategorie_id"]
                  and vervanger.subsub_id == row["subsub_id"])
        if zelfde:
            # Alleen de band met de regel vastleggen; de indeling klopt al.
            if row["regel_id"] != vervanger.id:
                werk_bij(conn, crypto, tx.id, regel_id=vervanger.id)
            uit.ongewijzigd += 1
            continue

        voorstel = naar_voorstel(vervanger)
        werk_bij(
            conn, crypto, tx.id,
            categorie_id=voorstel.categorie_id,
            subcategorie_id=voorstel.subcategorie_id,
            subsub_id=voorstel.subsub_id,
            zekerheid=voorstel.zekerheid,
            methode=voorstel.methode,
            status=voorstel.status,
            toelichting=voorstel.toelichting,
            regel_id=vervanger.id,
        )
        uit.overgenomen += 1
    return uit


def pas_toe(conn, crypto, regel_id: int | None = None) -> int:
    """Laat de regels los op wat nog geen categorie heeft.

    Met een `regel_id` alleen die ene regel — voor wanneer je hem weer aanzet,
    of hem zo bewerkt dat hij breder wordt. Zonder, alle actieve regels samen.

    Raakt alleen transacties zonder categorie: wat elders al is ingedeeld, en
    zeker wat jij zelf hebt ingedeeld, blijft staan.
    """
    regels = laad_regels(conn, crypto)
    if regel_id is not None:
        regels = [r for r in regels if r.id == regel_id]
    if not regels:
        return 0
    boek = Regelboek(regels)

    aangepast = 0
    rijen = conn.execute(
        "SELECT * FROM transacties WHERE categorie_id IS NULL"
        " AND methode IN ('geen', 'regel')"
    ).fetchall()

    for row in rijen:
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
        )
        aangepast += 1
    return aangepast


def herbekijk_alles(conn, crypto) -> Uitkomst:
    """Alle regels opnieuw toepassen op alles wat door een regel is ingedeeld.

    Bedoeld voor wanneer je prioriteiten hebt verschoven of meerdere regels na
    elkaar hebt aangepast. Het losmaken bij één regel kijkt namelijk alleen naar
    wat aan díe regel hing: een transactie die correct aan een andere regel
    hangt, blijft daar hangen, ook als jouw aangepaste regel nu voorgaat.

    Dit is een grove ingreep — ze loopt over je hele boekhouding — en staat
    daarom achter een aparte knop. Wat je zelf hebt ingedeeld, en wat de fuzzy
    stap of het AI-model heeft toegewezen, blijft ook hier staan.
    """
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM transacties WHERE methode = 'regel'")]
    uit = herbekijk(conn, crypto, ids, toelichting=GEEN_REGEL_TOELICHTING)
    uit.erbij = pas_toe(conn, crypto)
    return uit


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
    if not stukken:
        if uit.ongewijzigd:
            return (f"{uit.ongewijzigd} "
                    f"{'transactie hangt' if uit.ongewijzigd == 1 else 'transacties hangen'}"
                    " aan een regel en die wijst nog altijd naar dezelfde categorie.")
        return "Er veranderde niets aan je transacties."
    zin = " en ".join(stukken) + "."
    if uit.ongewijzigd:
        zin += f" {uit.ongewijzigd} bleven staan zoals ze stonden."
    return zin
