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

from .categorizer.engine import Regelboek, laad_regels, naar_voorstel
from .transacties import rij_naar_object, werk_bij

WIS_TOELICHTING = "De regel die deze transactie indeelde, bestaat niet meer."
UIT_TOELICHTING = "De regel die deze transactie indeelde, staat uit."
BEWERKT_TOELICHTING = ("De regel die deze transactie indeelde, is aangepast en "
                       "past hier niet meer op.")


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
              toelichting: str = WIS_TOELICHTING) -> tuple[int, int]:
    """Laat de regels zoals ze nu zijn opnieuw los op deze transacties.

    Past er nog een regel op, dan neemt die het over. Past er geen enkele meer
    op, dan gaat de categorie weg en komt de transactie op *nazicht* te staan,
    zodat ze in het nazichtscherm opduikt in plaats van stilletjes ergens
    onderaan een lijst te belanden.

    Geeft (overgenomen, gewist) terug.
    """
    if not tx_ids:
        return 0, 0
    boek = Regelboek(laad_regels(conn, crypto))

    overgenomen = gewist = 0
    for tx_id in tx_ids:
        row = conn.execute("SELECT * FROM transacties WHERE id = ?", (tx_id,)).fetchone()
        if row is None or row["methode"] != "regel":
            # Ondertussen zelf ingedeeld of verwijderd: afblijven.
            continue
        tx = rij_naar_object(row, crypto)
        vervanger = boek.beste(tx.kenmerken)
        if vervanger is not None:
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
            overgenomen += 1
        else:
            werk_bij(
                conn, crypto, tx.id,
                categorie_id=None, subcategorie_id=None, subsub_id=None,
                zekerheid=0.0, methode="geen", status="nazicht",
                toelichting=toelichting, regel_id=None,
            )
            gewist += 1
    return overgenomen, gewist


def pas_toe(conn, crypto, regel_id: int) -> int:
    """Laat één regel los op wat nog geen categorie heeft.

    Voor wanneer je een regel weer aanzet, of hem zo bewerkt dat hij breder
    wordt. Raakt alleen transacties zonder categorie: wat elders al is
    ingedeeld, en zeker wat jij zelf hebt ingedeeld, blijft staan.
    """
    regel = next((r for r in laad_regels(conn, crypto) if r.id == regel_id), None)
    if regel is None:
        return 0
    boek = Regelboek([regel])

    aangepast = 0
    rijen = conn.execute(
        "SELECT * FROM transacties WHERE categorie_id IS NULL"
        " AND methode IN ('geen', 'regel')"
    ).fetchall()

    for row in rijen:
        tx = rij_naar_object(row, crypto)
        if boek.beste(tx.kenmerken) is None:
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


def verslag(overgenomen: int, gewist: int, erbij: int = 0) -> str:
    """Eén zin over wat er met de transacties gebeurd is."""
    stukken = []
    if gewist:
        stukken.append(
            f"{gewist} {'transactie staat' if gewist == 1 else 'transacties staan'}"
            " nu op nazicht zonder categorie")
    if overgenomen:
        stukken.append(f"{overgenomen} {'is' if overgenomen == 1 else 'zijn'}"
                       " overgenomen door een andere regel")
    if erbij:
        stukken.append(f"{erbij} {'kreeg' if erbij == 1 else 'kregen'}"
                       " er alsnog een categorie bij")
    if not stukken:
        return "Er veranderde niets aan je transacties."
    return " en ".join(stukken) + "."
