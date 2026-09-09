"""Twee bijzondere invoerwegen: de referentielijst met categorieën, en de
kredietkaartuittreksels in PDF."""

from __future__ import annotations

import secrets
from decimal import Decimal
from pathlib import Path

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from ..auth import login_vereist
from ..categorizer.engine import Motor, TransactieKenmerken
from ..config import UPLOAD_DIR
from ..database import get_db, log, now_iso
from ..importers import kredietkaart as kk
from ..importers import referentie as ref
from ..transacties import bewaar, haal, werk_bij

bp = Blueprint("bijzonder", __name__)


def _bewaar_upload(bestand, toegelaten: set[str]) -> tuple[str, Path] | None:
    veilige_naam = secure_filename(bestand.filename or "")
    achtervoegsel = Path(veilige_naam).suffix.lower()
    if achtervoegsel not in toegelaten:
        return None
    token = secrets.token_urlsafe(16)
    doel = UPLOAD_DIR / f"{token}{achtervoegsel}"
    bestand.save(doel)
    return veilige_naam, doel


def _zoek_upload(token: str) -> Path | None:
    for pad in UPLOAD_DIR.glob(f"{token}.*"):
        return pad
    return None


# ==========================================================================
# Referentielijst met categorieën
# ==========================================================================

@bp.route("/instellingen/referentielijst", methods=["GET", "POST"])
@login_vereist
def referentielijst():
    if request.method == "POST":
        bestand = request.files.get("bestand")
        if not bestand or not bestand.filename:
            flash("Kies eerst een bestand.", "fout")
            return redirect(url_for("bijzonder.referentielijst"))
        bewaard = _bewaar_upload(bestand, {".xlsx", ".xlsm"})
        if bewaard is None:
            flash("Gebruik een Excel-bestand (.xlsx).", "fout")
            return redirect(url_for("bijzonder.referentielijst"))
        naam, pad = bewaard
        return redirect(url_for("bijzonder.referentielijst_voorbeeld",
                                token=pad.stem, naam=naam))

    conn = get_db()
    aantal_regels = conn.execute(
        "SELECT COUNT(*) n FROM regels WHERE herkomst='referentie'").fetchone()["n"]
    aantal_cats = conn.execute("SELECT COUNT(*) n FROM categorieen").fetchone()["n"]
    return render_template("referentielijst.html", aantal_regels=aantal_regels,
                           aantal_cats=aantal_cats)


@bp.route("/instellingen/referentielijst/<token>")
@login_vereist
def referentielijst_voorbeeld(token: str):
    pad = _zoek_upload(token)
    if pad is None:
        flash("Het bestand is niet meer beschikbaar. Probeer opnieuw.", "fout")
        return redirect(url_for("bijzonder.referentielijst"))
    try:
        rijen = ref.lees(pad)
    except Exception as exc:  # noqa: BLE001
        flash(f"Het bestand kon niet gelezen worden: {exc}", "fout")
        return redirect(url_for("bijzonder.referentielijst"))

    return render_template(
        "referentielijst_voorbeeld.html",
        token=token, naam=request.args.get("naam", pad.name),
        analyse=ref.analyseer(rijen),
    )


@bp.route("/instellingen/referentielijst/uitvoeren", methods=["POST"])
@login_vereist
def referentielijst_uitvoeren():
    pad = _zoek_upload(request.form.get("token", ""))
    if pad is None:
        flash("Het bestand is niet meer beschikbaar.", "fout")
        return redirect(url_for("bijzonder.referentielijst"))

    conn = get_db()
    crypto = g.crypto
    resultaat = ref.importeer(
        conn, crypto, ref.lees(pad),
        vervang=request.form.get("vervang") == "1",
        maak_partijregels=request.form.get("partijregels") == "1",
    )
    log(conn, crypto, g.gebruiker, "referentielijst_ingelezen", str(resultaat))
    conn.commit()

    try:
        pad.unlink()
    except OSError:
        pass

    flash(
        f"{resultaat['categorieen']} categorieën en "
        f"{resultaat['sleutelregels'] + resultaat['partijregels']} regels ingelezen.",
        "goed",
    )
    if request.form.get("herindelen") == "1":
        return redirect(url_for("tx.herindelen_get"))
    return redirect(url_for("instellingen.categorieen"))


# ==========================================================================
# Kredietkaartuittreksels
# ==========================================================================

@bp.route("/kredietkaart", methods=["GET", "POST"])
@login_vereist
def kredietkaart():
    conn = get_db()
    crypto = g.crypto

    if request.method == "POST":
        bestand = request.files.get("bestand")
        if not bestand or not bestand.filename:
            flash("Kies eerst een PDF.", "fout")
            return redirect(url_for("bijzonder.kredietkaart"))
        bewaard = _bewaar_upload(bestand, {".pdf"})
        if bewaard is None:
            flash("Gebruik een PDF-bestand.", "fout")
            return redirect(url_for("bijzonder.kredietkaart"))
        naam, pad = bewaard
        return redirect(url_for("bijzonder.kredietkaart_voorbeeld",
                                token=pad.stem, naam=naam))

    hangend = conn.execute(
        "SELECT COUNT(*) n FROM transacties WHERE is_afrekening=1").fetchone()["n"]
    return render_template(
        "kredietkaart.html",
        afrekeningen=kk.zoek_afrekeningen(conn, crypto),
        verwerkt=hangend,
    )


@bp.route("/kredietkaart/<token>")
@login_vereist
def kredietkaart_voorbeeld(token: str):
    pad = _zoek_upload(token)
    if pad is None:
        flash("De PDF is niet meer beschikbaar. Probeer opnieuw.", "fout")
        return redirect(url_for("bijzonder.kredietkaart"))

    conn = get_db()
    crypto = g.crypto
    try:
        uittreksel = kk.lees_pdf(pad, request.args.get("patroon", "automatisch"))
    except kk.PdfFout as exc:
        flash(str(exc), "fout")
        return redirect(url_for("bijzonder.kredietkaart"))

    rekeningen = [
        {"id": r["id"], "naam": crypto.dec(r["naam_enc"])}
        for r in conn.execute("SELECT * FROM rekeningen WHERE actief=1 ORDER BY volgorde")
    ]
    return render_template(
        "kredietkaart_voorbeeld.html",
        token=token, naam=request.args.get("naam", pad.name),
        uittreksel=uittreksel, patronen=list(kk.PATRONEN),
        gekozen_patroon=request.args.get("patroon", "automatisch"),
        afrekeningen=kk.zoek_afrekeningen(conn, crypto),
        rekeningen=rekeningen,
    )


@bp.route("/kredietkaart/uitvoeren", methods=["POST"])
@login_vereist
def kredietkaart_uitvoeren():
    pad = _zoek_upload(request.form.get("token", ""))
    if pad is None:
        flash("De PDF is niet meer beschikbaar.", "fout")
        return redirect(url_for("bijzonder.kredietkaart"))

    conn = get_db()
    crypto = g.crypto
    uittreksel = kk.lees_pdf(pad, request.form.get("patroon", "automatisch"))

    afrekening_id = request.form.get("afrekening_id", type=int)
    afrekening = haal(conn, crypto, afrekening_id) if afrekening_id else None
    rekening_id = (afrekening.rekening_id if afrekening
                   else request.form.get("rekening_id", type=int))
    if not rekening_id:
        flash("Kies een rekening of een afrekening om aan te hangen.", "fout")
        return redirect(url_for("bijzonder.kredietkaart"))

    gekozen = set(request.form.getlist("regel"))
    motor = Motor(conn, crypto)
    kaart = uittreksel.kaart or "Kredietkaart"
    nieuw = dubbel = 0

    for item in uittreksel.herkende:
        if str(item.nummer) not in gekozen:
            continue
        kenmerken = TransactieKenmerken(
            beschrijving="Kredietkaart",
            tegenpartij_naam=item.omschrijving,
            mededeling=item.origineel_bedrag,
            bedrag=item.bedrag,
            richting="in" if item.bedrag >= 0 else "uit",
        )
        voorstel = motor.beoordeel(kenmerken)
        motor.onthoud(kenmerken, voorstel)

        tx_id = bewaar(
            conn, crypto,
            rekening_id=rekening_id,
            boekdatum=item.datum,
            bedrag=item.bedrag,
            beschrijving="Kredietkaart",
            referentie=f"{kaart}|{item.datum}|{item.omschrijving[:40]}|{item.bedrag}",
            tegenpartij_naam=item.omschrijving,
            mededeling=item.origineel_bedrag,
            voorstel=voorstel,
            ouder_tx_id=afrekening.id if afrekening else None,
            bron="kredietkaart",
        )
        if tx_id is None:
            dubbel += 1
        else:
            nieuw += 1

    if afrekening is not None:
        # De afrekening zelf telt niet meer mee; de aankopen eronder wel.
        conn.execute("UPDATE transacties SET is_afrekening=1, status='bevestigd',"
                     " methode='manueel' WHERE id=?", (afrekening.id,))
        werk_bij(conn, crypto, afrekening.id,
                 toelichting=f"Uitgesplitst in {nieuw} aankopen uit het PDF-uittreksel.")

    log(conn, crypto, g.gebruiker, "kredietkaart_ingelezen",
        f"kaart={kaart} nieuw={nieuw} dubbel={dubbel}")
    conn.commit()

    try:
        pad.unlink()
    except OSError:
        pass

    flash(f"{nieuw} aankopen toegevoegd, {dubbel} stonden er al.", "goed")
    return redirect(url_for("tx.nazicht"))


@bp.route("/kredietkaart/afrekening/<int:tx_id>/losmaken", methods=["POST"])
@login_vereist
def losmaken(tx_id: int):
    conn = get_db()
    aantal = conn.execute("DELETE FROM transacties WHERE ouder_tx_id=?", (tx_id,)).rowcount
    conn.execute("UPDATE transacties SET is_afrekening=0 WHERE id=?", (tx_id,))
    log(conn, g.crypto, g.gebruiker, "kredietkaart_losgemaakt", f"tx={tx_id} n={aantal}")
    conn.commit()
    flash(f"{aantal} aankopen verwijderd; de afrekening telt weer mee.", "goed")
    return redirect(url_for("bijzonder.kredietkaart"))
