"""Wat er met de transacties moet gebeuren als een regel verandert.

Een regel verwijderen of uitschakelen hield voordien op bij de regeltabel. De
transacties die hij ooit had ingedeeld, bleven in hun categorie staan — met
`methode='regel'` en `status='bevestigd'`, waardoor zelfs *Opnieuw indelen* ze
niet meer aanraakte. De indeling bleef dus hangen aan een regel die niet meer
bestond, en de enige uitweg was elke transactie met de hand terugzetten.

Hier staat de tegenhanger: haalt de regel weg, dan wordt gekeken of een andere
regel het overneemt, en zo niet wordt de categorie gewist. Zet je hem terug aan,
dan pakt hij op wat nog geen categorie heeft.

Twee dingen blijven bewust ongemoeid:

* wat je zelf hebt ingedeeld (`methode='manueel'`) en wat de fuzzy stap of het
  AI-model heeft toegewezen. Alleen een toewijzing die van déze regel kwam,
  gaat weg;
* handelaar en land. Die staan los van de indeling, en een regel is meestal
  niet de enige plek waar ze vandaan komen.
"""

from __future__ import annotations

from .categorizer.engine import Regelboek, laad_regels, naar_voorstel
from .transacties import rij_naar_object, werk_bij

WIS_TOELICHTING = "De regel die deze transactie indeelde, bestaat niet meer."
UIT_TOELICHTING = "De regel die deze transactie indeelde, staat uit."


def _hing_aan(row, regel_id: int, boek_voor: Regelboek, kenmerken) -> bool:
    """Was deze transactie door die regel ingedeeld?

    Staat de regel er expliciet bij, dan is het antwoord zeker. Voor rijen van
    vóór schemaversie 4 staat er niets, en dan blijft alleen de vraag over: zou
    déze regel deze transactie ingedeeld hebben, gegeven de regels zoals ze
    stonden? Is een andere regel voorgegaan, dan hing ze aan die andere en
    blijft ze met rust.
    """
    if row["regel_id"] is not None:
        return row["regel_id"] == regel_id
    gekozen = boek_voor.beste(kenmerken)
    return gekozen is not None and gekozen.id == regel_id


def maak_los(conn, crypto, regel_id: int, *, toelichting: str = WIS_TOELICHTING
             ) -> tuple[int, int]:
    """Haalt de indeling weg bij alles wat aan deze regel hing.

    Roep dit aan nádat de regel uitgeschakeld is, of vlak vóór hij verwijderd
    wordt — de definitie is nog nodig om de oudere rijen te herkennen.

    Geeft (overgenomen, gewist) terug.
    """
    alle = laad_regels(conn, crypto, alleen_actief=False)
    deze = next((r for r in alle if r.id == regel_id), None)
    resterend = [r for r in laad_regels(conn, crypto) if r.id != regel_id]

    # Zoals het was: de regels die nu nog gelden, plus degene die weggaat.
    boek_voor = Regelboek(resterend + ([deze] if deze is not None else []))
    boek_na = Regelboek(resterend)

    overgenomen = gewist = 0
    rijen = conn.execute(
        "SELECT * FROM transacties WHERE methode = 'regel'"
        " AND (regel_id = ? OR regel_id IS NULL)", (regel_id,)
    ).fetchall()

    for row in rijen:
        tx = rij_naar_object(row, crypto)
        if not _hing_aan(row, regel_id, boek_voor, tx.kenmerken):
            continue

        vervanger = boek_na.beste(tx.kenmerken)
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
                zekerheid=0.0, methode="geen", status="niet_toegewezen",
                toelichting=toelichting, regel_id=None,
            )
            gewist += 1

    return overgenomen, gewist


def pas_toe(conn, crypto, regel_id: int) -> int:
    """Laat een regel los op wat nog geen categorie heeft.

    De tegenhanger van `maak_los`, voor wanneer je een regel weer aanzet. Raakt
    alleen transacties zonder categorie: wat elders al is ingedeeld, en zeker
    wat jij zelf hebt ingedeeld, blijft staan.
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


def verslag(overgenomen: int, gewist: int) -> str:
    """Eén zin over wat er met de transacties gebeurd is."""
    if not overgenomen and not gewist:
        return "Er hingen geen transacties aan deze regel."
    stukken = []
    if gewist:
        stukken.append(f"{gewist} {'transactie staat' if gewist == 1 else 'transacties staan'}"
                       " nu zonder categorie")
    if overgenomen:
        stukken.append(f"{overgenomen} {'is' if overgenomen == 1 else 'zijn'}"
                       " overgenomen door een andere regel")
    return " en ".join(stukken) + "."
