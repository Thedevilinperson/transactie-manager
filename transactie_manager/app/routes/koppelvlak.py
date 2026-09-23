"""Kleine JSON-eindpunten voor de schermen: afhankelijke keuzelijsten en het
op aanvraag bevragen van het AI-model."""

from __future__ import annotations

import secrets

from flask import Blueprint, g, jsonify, request

from ..auth import login_vereist
from ..categories import laad_alles
from ..categorizer import ai
from .. import regelmaker, taken
from ..database import connect, get_db, log
from ..transacties import haal, werk_bij

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/categorieen")
@login_vereist
def categorieen():
    """Geeft de directe kinderen van een categorie, of de hoofdcategorieën."""
    conn = get_db()
    platte = laad_alles(conn, g.crypto, alleen_actief=True)
    ouder_id = request.args.get("ouder_id", type=int)
    soort = request.args.get("soort")

    if ouder_id:
        kinderen = [c for c in platte.values() if c.ouder_id == ouder_id]
    else:
        kinderen = [c for c in platte.values() if c.niveau == 0]
        if soort in ("in", "uit"):
            kinderen = [c for c in kinderen if c.soort in (soort, "beide")]

    kinderen.sort(key=lambda c: c.naam.lower())
    return jsonify([{"id": c.id, "naam": c.naam} for c in kinderen])


@bp.route("/regel-proef", methods=["POST"])
@login_vereist
def regel_proef():
    """Op welke transacties zou de regel uit het bewerkscherm nu passen?

    Krijgt het hele formulier van het bewerkscherm, zodat ook de gekozen
    categorie meetelt: hoeveel treffers staan er al in, hoeveel elders.
    """
    samenstelling, reden = regelmaker.lees(request.form)
    if samenstelling is None:
        return jsonify({"fout": reden}), 400
    ids = (request.form.get("categorie_id", type=int),
           request.form.get("subcategorie_id", type=int),
           request.form.get("subsub_id", type=int))
    uit = regelmaker.proef(get_db(), g.crypto, samenstelling, ids,
                           huidig_tx=request.form.get("rv_tx", type=int))
    uit["prioriteit"] = samenstelling.prioriteit
    uit["voorwaarden"] = len(samenstelling.voorwaarden)
    return jsonify(uit)


@bp.route("/ai-voorstel/<int:tx_id>", methods=["POST"])
@login_vereist
def ai_voorstel(tx_id: int):
    """Start een AI-bevraging voor één transactie, in een aparte draad.

    Een lokaal model op een processor zonder grafische kaart doet over een
    vraag met je volledige indeling al snel een of twee minuten. Zo lang op
    één antwoord wachten liep mis: onderweg brak een proxy (de ingress van
    Home Assistant) de verbinding af, de browser kreeg geen bruikbaar antwoord
    en vulde de categorie niet in — terwijl de server het voorstel wel
    bewaarde. Nu antwoordt deze aanvraag meteen met een kenmerk, en vraagt het
    scherm om de paar seconden de stand op (zie ai_stand).
    """
    conn = get_db()
    crypto = g.crypto
    if haal(conn, crypto, tx_id) is None:
        return jsonify({"fout": "Die transactie bestaat niet."}), 404
    if not ai.beschikbaar(conn):
        return jsonify({"fout": "Het AI-model staat uitgeschakeld in de instellingen."}), 400

    token = "ai-" + secrets.token_urlsafe(12)
    taken.start(token, f"AI-voorstel voor transactie {tx_id}",
                _bevraag, tx_id, crypto, g.gebruiker)
    return jsonify({"token": token}), 202


@bp.route("/ai-voorstel/stand/<token>")
@login_vereist
def ai_stand(token: str):
    """Hoe ver een AI-bevraging staat. Is ze klaar, dan staat het voorstel (of
    de fout) in `resultaat`."""
    taak = taken.haal(token) if token.startswith("ai-") else None
    if taak is None:
        return jsonify({"fout": "Die bevraging is niet (meer) bekend. Herlaad de "
                                "bladzijde: een voorstel dat intussen klaar was, "
                                "staat dan al bij de transactie."}), 404
    return jsonify(taak.naar_json())


def _bevraag(taak, tx_id: int, crypto, gebruiker: str) -> dict:
    """Draait in een aparte draad, dus met een eigen verbinding."""
    conn = connect()
    try:
        tx = haal(conn, crypto, tx_id)
        if tx is None:
            return {"fout": "Die transactie bestaat niet meer."}
        taak.fase = "Het model denkt na"
        try:
            voorstel = ai.stel_voor(conn, crypto, tx.kenmerken, gebruiker=gebruiker)
        except ai.AIFout as exc:
            # De bevraging zelf staat al in het logboek, ook zonder voorstel.
            conn.commit()
            return {"fout": str(exc)}

        # Het voorstel meteen vastleggen — net als bij een fuzzy- of
        # regelsuggestie — zodat het klaarstaat wanneer de transactie geopend
        # wordt, ook als het scherm intussen gesloten is. Bevestigen moet de
        # gebruiker nog altijd zelf.
        werk_bij(
            conn, crypto, tx_id,
            categorie_id=voorstel.categorie_id,
            subcategorie_id=voorstel.subcategorie_id,
            subsub_id=voorstel.subsub_id,
            handelaar=voorstel.handelaar or tx.handelaar,
            land=voorstel.land or tx.land,
            zekerheid=voorstel.zekerheid,
            methode="ai",
            status="nazicht",
            toelichting=voorstel.toelichting,
            regel_id=None,
        )
        log(conn, crypto, gebruiker, "ai_voorstel_opgeslagen", f"tx={tx_id}")
        conn.commit()

        platte = laad_alles(conn, crypto)

        def naam(cat_id):
            return platte[cat_id].naam if cat_id in platte else None

        return {
            "categorie_id": voorstel.categorie_id,
            "subcategorie_id": voorstel.subcategorie_id,
            "subsub_id": voorstel.subsub_id,
            "pad": " › ".join(
                n for n in (naam(voorstel.categorie_id), naam(voorstel.subcategorie_id),
                            naam(voorstel.subsub_id)) if n
            ),
            "handelaar": voorstel.handelaar,
            "land": voorstel.land,
            "zekerheid": voorstel.zekerheid,
            "toelichting": voorstel.toelichting,
        }
    finally:
        conn.close()
