"""Kleine JSON-eindpunten voor de schermen: afhankelijke keuzelijsten en het
op aanvraag bevragen van het AI-model."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..auth import login_vereist
from ..categories import laad_alles
from ..categorizer import ai
from ..database import get_db, log
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


@bp.route("/ai-voorstel/<int:tx_id>", methods=["POST"])
@login_vereist
def ai_voorstel(tx_id: int):
    conn = get_db()
    crypto = g.crypto
    tx = haal(conn, crypto, tx_id)
    if tx is None:
        return jsonify({"fout": "Die transactie bestaat niet."}), 404

    try:
        voorstel = ai.stel_voor(conn, crypto, tx.kenmerken, gebruiker=g.gebruiker)
    except ai.AIFout as exc:
        # De bevraging zelf is al in het logboek gezet, ook al gaf ze geen
        # bruikbaar voorstel; dat moet wel bewaard blijven.
        conn.commit()
        return jsonify({"fout": str(exc)}), 502

    # Het voorstel meteen vastleggen — net als bij een automatische fuzzy- of
    # regelsuggestie — zodat het klaarstaat wanneer de transactie geopend
    # wordt. Bevestigen moet de gebruiker nog altijd zelf.
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
    log(conn, crypto, g.gebruiker, "ai_voorstel_opgeslagen", f"tx={tx_id}")
    conn.commit()

    platte = laad_alles(conn, crypto)

    def naam(cat_id):
        return platte[cat_id].naam if cat_id in platte else None

    return jsonify({
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
    })
