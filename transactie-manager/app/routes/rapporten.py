"""Overzichtstabel en grafieken."""

from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, g, render_template, request

from ..auth import login_vereist
from ..categories import boom, keuzelijst
from ..database import get_db
from ..rapporten import jaartabel, plat, reeksen

bp = Blueprint("rapport", __name__, url_prefix="/overzicht")


def _filters():
    return {
        "richting": request.args.get("richting", "uit"),
        "categorie_id": request.args.get("categorie_id", type=int),
        "rekening_id": request.args.get("rekening_id", type=int),
        "van": request.args.get("van") or None,
        "tot": request.args.get("tot") or None,
        "alleen_bevestigd": request.args.get("alleen_bevestigd") == "1",
    }


def _rekeningen(conn, crypto):
    return [
        {"id": r["id"], "naam": crypto.dec(r["naam_enc"])}
        for r in conn.execute("SELECT * FROM rekeningen ORDER BY volgorde, id")
    ]


@bp.route("/tabel")
@login_vereist
def tabel():
    conn = get_db()
    crypto = g.crypto
    filters = _filters()
    rijen, jaren, totalen = jaartabel(conn, crypto, filters)
    return render_template(
        "rapport_tabel.html",
        rijen=plat(rijen), jaren=jaren, totalen=totalen, filters=filters,
        keuzes=keuzelijst(boom(conn, crypto, filters["richting"])),
        rekeningen=_rekeningen(conn, crypto),
    )


@bp.route("/tabel.csv")
@login_vereist
def tabel_csv():
    conn = get_db()
    crypto = g.crypto
    filters = _filters()
    rijen, jaren, totalen = jaartabel(conn, crypto, filters)

    buffer = io.StringIO()
    schrijver = csv.writer(buffer, delimiter=";")
    schrijver.writerow(["Niveau", "Categorie"] + [str(j) for j in jaren] + ["Totaal"])
    for rij in plat(rijen):
        schrijver.writerow(
            [rij["niveau"], rij["naam"]]
            + [f"{rij['per_jaar'].get(j, 0):.2f}".replace(".", ",") for j in jaren]
            + [f"{rij['totaal']:.2f}".replace(".", ",")]
        )
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=overzicht.csv"},
    )


@bp.route("/grafiek")
@login_vereist
def grafiek():
    conn = get_db()
    crypto = g.crypto
    filters = _filters()
    filters["detailniveau"] = request.args.get("detailniveau", "hoofd")
    groepering = request.args.get("groepering", "jaar")
    labels, series = reeksen(conn, crypto, filters, groepering)
    return render_template(
        "rapport_grafiek.html",
        labels=labels, series=series[:12], filters=filters, groepering=groepering,
        keuzes=keuzelijst(boom(conn, crypto, filters["richting"])),
        rekeningen=_rekeningen(conn, crypto),
    )
