"""Overzichtstabel en grafieken."""

from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, g, render_template, request

from ..auth import login_vereist
from ..categories import boom, keuzelijst
from ..database import get_db
from ..filters import Filters, keuzes, rekeningen as alle_rekeningen
from ..rapporten import jaartabel, plat, reeksen, verdeling

bp = Blueprint("rapport", __name__, url_prefix="/overzicht")


def _context(conn, crypto, filters: Filters) -> dict:
    """Alles wat de filterbalk nodig heeft."""
    alle = keuzelijst(boom(conn, crypto))
    return {
        "filters": filters,
        "keuzes": keuzes(conn, crypto),
        "rekeningen": alle_rekeningen(conn, crypto),
        "hoofdcategorieen": [c for c in alle if c["niveau"] == 0],
        "alle_categorieen": alle,
    }


@bp.route("/tabel")
@login_vereist
def tabel():
    conn = get_db()
    crypto = g.crypto
    filters = Filters.uit_aanvraag("uit")
    rijen, jaren, totalen = jaartabel(conn, crypto, filters)
    return render_template("rapport_tabel.html", rijen=plat(rijen), jaren=jaren,
                           totalen=totalen, **_context(conn, crypto, filters))


@bp.route("/tabel.csv")
@login_vereist
def tabel_csv():
    conn = get_db()
    crypto = g.crypto
    filters = Filters.uit_aanvraag("uit")
    rijen, jaren, totalen = jaartabel(conn, crypto, filters)

    buffer = io.StringIO()
    schrijver = csv.writer(buffer, delimiter=";")
    schrijver.writerow(["Niveau", "Categorie"] + [str(j) for j in jaren] + ["Totaal"])
    for rij in plat(rijen):
        schrijver.writerow(
            [rij["niveau"], rij["naam"]]
            + [f"{round(rij['per_jaar'].get(j, 0)):d}" for j in jaren]
            + [f"{round(rij['totaal']):d}"]
        )
    schrijver.writerow(["", "Alles samen"]
                       + [f"{round(totalen.get(j, 0)):d}" for j in jaren]
                       + [f"{round(totalen.get('totaal', 0)):d}"])
    return Response(buffer.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=overzicht.csv"})


@bp.route("/grafiek")
@login_vereist
def grafiek():
    """Twee grafieken op één bladzijde, elk met een eigen filterbalk.

    De filters van de staafgrafiek dragen geen voorvoegsel, die van de taart
    krijgen `t_`. Zo staan ze los van elkaar in de adresbalk.
    """
    conn = get_db()
    crypto = g.crypto

    staaf = Filters.uit_aanvraag("uit")
    labels, series = reeksen(conn, crypto, staaf)

    taart = Filters.uit_aanvraag("uit")
    taart_args = {k[2:]: v for k, v in request.args.lists() if k.startswith("t_")}
    if taart_args:
        taart = _met_voorvoegsel(taart_args)
    stukken, taart_totaal = verdeling(conn, crypto, taart)

    return render_template(
        "rapport_grafiek.html",
        labels=labels, series=series, stukken=stukken, taart_totaal=taart_totaal,
        taart=taart, **_context(conn, crypto, staaf),
    )


def _met_voorvoegsel(waarden: dict) -> Filters:
    """Bouwt een tweede set filters uit de `t_`-parameters."""
    def eerste(sleutel, standaard=""):
        lijst = waarden.get(sleutel) or []
        return lijst[0] if lijst else standaard

    hoofd = eerste("hoofd_id")
    sub = eerste("sub_id")
    subsub = eerste("subsub_id")

    def getal(waarde):
        return int(waarde) if str(waarde).isdigit() else None

    return Filters(
        jaren=[int(j) for j in waarden.get("jaar", []) if j.isdigit()],
        richting=eerste("richting", "uit"),
        rekening_id=getal(eerste("rekening_id")),
        categorie_id=getal(subsub) or getal(sub) or getal(hoofd),
        hoofd_id=getal(hoofd), sub_id=getal(sub), subsub_id=getal(subsub),
        landen=[w for w in waarden.get("land", []) if w],
        winkels=[w for w in waarden.get("winkel", []) if w],
        alleen_bevestigd=eerste("alleen_bevestigd") == "1",
        uit_winkels=[w for w in waarden.get("uit_winkel", []) if w],
        uit_categorieen=[int(c) for c in waarden.get("uit_categorie", []) if c.isdigit()],
        groepering=eerste("groepering", "hoofd"),
        periode=eerste("periode", "jaar"),
    )
