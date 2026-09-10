"""Transacties bekijken, toevoegen, aanpassen en nakijken."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..auth import login_vereist
from ..categories import boom, keuzelijst, laad_alles, nakomelingen, pad_tekst
from ..categorizer.ai import maak_regel_van_voorstel
from ..categorizer.engine import Motor, TransactieKenmerken, Voorstel
from ..database import get_db, instelling, log
from ..transacties import bewaar, haal, tel, werk_bij, zoek

bp = Blueprint("tx", __name__, url_prefix="/transacties")


def _rekeningen(conn, crypto):
    return [
        {"id": r["id"], "naam": crypto.dec(r["naam_enc"]),
         "iban": crypto.dec(r["iban_enc"]) or "", "munt": r["munt"]}
        for r in conn.execute("SELECT * FROM rekeningen WHERE actief=1 ORDER BY volgorde, id")
    ]


def _cat_context(conn, crypto):
    platte = laad_alles(conn, crypto)
    return {
        "platte": platte,
        "keuzes_uit": keuzelijst(boom(conn, crypto, "uit", alleen_actief=True)),
        "keuzes_in": keuzelijst(boom(conn, crypto, "in", alleen_actief=True)),
        "alle_keuzes": keuzelijst(boom(conn, crypto, alleen_actief=True)),
    }


@bp.route("/")
@login_vereist
def lijst():
    conn = get_db()
    crypto = g.crypto
    filters = {
        "status": request.args.get("status") or None,
        "rekening_id": request.args.get("rekening_id", type=int),
        "richting": request.args.get("richting") or None,
        "van": request.args.get("van") or None,
        "tot": request.args.get("tot") or None,
        "zoekterm": request.args.get("q", "").strip(),
    }
    categorie_id = request.args.get("categorie_id", type=int)
    platte = laad_alles(conn, crypto)
    categorie_ids = sorted(nakomelingen(platte, categorie_id)) if categorie_id else None

    pagina = max(1, request.args.get("pagina", 1, type=int))
    per_pagina = 100
    rijen = zoek(
        conn, crypto,
        status=filters["status"], rekening_id=filters["rekening_id"],
        richting=filters["richting"], van=filters["van"], tot=filters["tot"],
        zoekterm=filters["zoekterm"], categorie_ids=categorie_ids,
        limiet=per_pagina, offset=(pagina - 1) * per_pagina,
    )

    return render_template(
        "transacties.html",
        rijen=rijen, filters=filters, categorie_id=categorie_id, pagina=pagina,
        rekeningen=_rekeningen(conn, crypto),
        pad_tekst=lambda *ids: pad_tekst(platte, *ids),
        keuzes=keuzelijst(boom(conn, crypto)),
        totaal_aantal=tel(conn),
    )


@bp.route("/nieuw", methods=["GET", "POST"])
@login_vereist
def nieuw():
    conn = get_db()
    crypto = g.crypto
    rekeningen = _rekeningen(conn, crypto)
    if not rekeningen:
        flash("Voeg eerst een rekening toe bij Instellingen.", "fout")
        return redirect(url_for("instellingen.rekeningen"))

    if request.method == "POST":
        try:
            bedrag = Decimal(request.form.get("bedrag", "0").replace(",", "."))
        except InvalidOperation:
            flash("Het bedrag is geen geldig getal.", "fout")
            return redirect(url_for("tx.nieuw"))

        richting = request.form.get("richting", "uit")
        if richting == "uit":
            bedrag = -abs(bedrag)
        else:
            bedrag = abs(bedrag)

        voorstel = Voorstel(
            categorie_id=request.form.get("categorie_id", type=int),
            subcategorie_id=request.form.get("subcategorie_id", type=int),
            subsub_id=request.form.get("subsub_id", type=int),
            handelaar=request.form.get("handelaar", "").strip() or None,
            land=request.form.get("land", "").strip() or None,
            zekerheid=1.0,
            methode="manueel",
            status="bevestigd",
            toelichting="Manueel ingevoerd.",
        )

        kenmerken = TransactieKenmerken(
            tegenpartij_naam=request.form.get("tegenpartij_naam", "").strip(),
            tegenpartij_rekening=request.form.get("tegenpartij_rekening", "").strip(),
            mededeling=request.form.get("mededeling", "").strip(),
            begunstigde=request.form.get("begunstigde", "").strip(),
            bedrag=bedrag,
            richting=richting,
        )

        if not voorstel.gevonden:
            # Zonder handmatige keuze toch proberen automatisch toe te wijzen.
            voorstel = Motor(conn, crypto).beoordeel(kenmerken)

        tx_id = bewaar(
            conn, crypto,
            rekening_id=request.form.get("rekening_id", type=int),
            boekdatum=request.form.get("boekdatum") or date.today().isoformat(),
            valutadatum=request.form.get("valutadatum") or None,
            bedrag=bedrag,
            tegenpartij_naam=kenmerken.tegenpartij_naam,
            tegenpartij_rekening=kenmerken.tegenpartij_rekening,
            begunstigde=kenmerken.begunstigde,
            mededeling=kenmerken.mededeling,
            voorstel=voorstel,
        )
        if tx_id is None:
            flash("Deze transactie bestaat al.", "fout")
        else:
            log(conn, crypto, g.gebruiker, "transactie_toegevoegd", f"id={tx_id}")
            conn.commit()
            flash("Transactie toegevoegd.", "goed")
            return redirect(url_for("tx.lijst"))

    return render_template(
        "transactie_nieuw.html",
        rekeningen=rekeningen, vandaag=date.today().isoformat(), **_cat_context(conn, g.crypto),
    )


@bp.route("/<int:tx_id>/bewerken", methods=["GET", "POST"])
@login_vereist
def bewerken(tx_id: int):
    conn = get_db()
    crypto = g.crypto
    tx = haal(conn, crypto, tx_id)
    if tx is None:
        flash("Die transactie bestaat niet.", "fout")
        return redirect(url_for("tx.lijst"))

    if request.method == "POST":
        werk_bij(
            conn, crypto, tx_id,
            categorie_id=request.form.get("categorie_id", type=int),
            subcategorie_id=request.form.get("subcategorie_id", type=int),
            subsub_id=request.form.get("subsub_id", type=int),
            handelaar=request.form.get("handelaar", "").strip(),
            land=request.form.get("land", "").strip(),
            mededeling=request.form.get("mededeling", "").strip(),
            tegenpartij_naam=request.form.get("tegenpartij_naam", "").strip(),
            status="bevestigd",
            methode="manueel",
            zekerheid=1.0,
            toelichting="Manueel aangepast.",
        )
        if request.form.get("onthouden") == "1":
            bijgewerkt = haal(conn, crypto, tx_id)
            maak_regel_van_voorstel(
                conn, crypto, bijgewerkt.kenmerken,
                Voorstel(
                    categorie_id=bijgewerkt.categorie_id,
                    subcategorie_id=bijgewerkt.subcategorie_id,
                    subsub_id=bijgewerkt.subsub_id,
                    handelaar=bijgewerkt.handelaar or None,
                    land=bijgewerkt.land or None,
                ),
            )
            flash("Opgeslagen en als vaste regel onthouden.", "goed")
        else:
            flash("Transactie opgeslagen.", "goed")
        log(conn, crypto, g.gebruiker, "transactie_gewijzigd", f"id={tx_id}")
        conn.commit()
        return redirect(request.form.get("terug") or url_for("tx.lijst"))

    return render_template(
        "transactie_bewerken.html",
        tx=tx, rekeningen=_rekeningen(conn, crypto),
        terug=request.args.get("terug", ""), **_cat_context(conn, crypto),
    )


@bp.route("/<int:tx_id>/verwijderen", methods=["POST"])
@login_vereist
def verwijderen(tx_id: int):
    conn = get_db()
    conn.execute("DELETE FROM transacties WHERE id = ?", (tx_id,))
    log(conn, g.crypto, g.gebruiker, "transactie_verwijderd", f"id={tx_id}")
    conn.commit()
    flash("Transactie verwijderd.", "goed")
    return redirect(request.form.get("terug") or url_for("tx.lijst"))


@bp.route("/nazicht")
@login_vereist
def nazicht():
    conn = get_db()
    crypto = g.crypto
    platte = laad_alles(conn, crypto)
    onzeker = zoek(conn, crypto, status="nazicht", limiet=100)
    open_rijen = zoek(conn, crypto, status="niet_toegewezen", limiet=100)
    return render_template(
        "nazicht.html",
        onzeker=onzeker, open_rijen=open_rijen,
        pad_tekst=lambda *ids: pad_tekst(platte, *ids),
        ai_actief=instelling(conn, "ai_actief", "0") == "1",
        **_cat_context(conn, crypto),
    )


@bp.route("/<int:tx_id>/bevestigen", methods=["POST"])
@login_vereist
def bevestigen(tx_id: int):
    conn = get_db()
    crypto = g.crypto
    werk_bij(conn, crypto, tx_id, status="bevestigd", zekerheid=1.0)
    if instelling(conn, "leer_van_bevestiging", "1") == "1":
        tx = haal(conn, crypto, tx_id)
        if tx and tx.categorie_id:
            maak_regel_van_voorstel(conn, crypto, tx.kenmerken, Voorstel(
                categorie_id=tx.categorie_id,
                subcategorie_id=tx.subcategorie_id,
                subsub_id=tx.subsub_id,
                handelaar=tx.handelaar or None,
                land=tx.land or None,
            ))
    conn.commit()
    flash("Bevestigd.", "goed")
    return redirect(request.form.get("terug") or url_for("tx.nazicht"))


@bp.route("/alles-bevestigen", methods=["POST"])
@login_vereist
def alles_bevestigen():
    conn = get_db()
    aantal = conn.execute(
        "UPDATE transacties SET status='bevestigd', zekerheid=1.0"
        " WHERE status='nazicht' AND categorie_id IS NOT NULL"
    ).rowcount
    log(conn, g.crypto, g.gebruiker, "bulk_bevestigd", f"aantal={aantal}")
    conn.commit()
    flash(f"{aantal} transacties bevestigd.", "goed")
    return redirect(url_for("tx.nazicht"))


@bp.route("/herindelen", methods=["GET"])
@login_vereist
def herindelen_get():
    return herindelen()


@bp.route("/herindelen", methods=["POST"])
@login_vereist
def herindelen():
    """Laat de motor opnieuw los op alles wat nog niet bevestigd is."""
    conn = get_db()
    crypto = g.crypto
    motor = Motor(conn, crypto)
    aangepast = 0
    rijen = conn.execute(
        "SELECT * FROM transacties WHERE status <> 'bevestigd'"
    ).fetchall()
    from ..transacties import rij_naar_object
    for row in rijen:
        tx = rij_naar_object(row, crypto)
        voorstel = motor.beoordeel(tx.kenmerken)
        if voorstel.gevonden:
            werk_bij(
                conn, crypto, tx.id,
                categorie_id=voorstel.categorie_id,
                subcategorie_id=voorstel.subcategorie_id,
                subsub_id=voorstel.subsub_id,
                handelaar=voorstel.handelaar or tx.handelaar,
                land=voorstel.land or tx.land,
                zekerheid=voorstel.zekerheid,
                methode=voorstel.methode,
                status=voorstel.status,
                toelichting=voorstel.toelichting,
            )
            aangepast += 1
    log(conn, crypto, g.gebruiker, "herindeling", f"aangepast={aangepast}")
    conn.commit()
    flash(f"{aangepast} transacties opnieuw ingedeeld.", "goed")
    return redirect(url_for("tx.nazicht"))
