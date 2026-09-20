"""Transacties bekijken, toevoegen, aanpassen en nakijken."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import backup, herindeling, veilig_terug
from ..auth import login_vereist
from ..categories import boom, keuzelijst, laad_alles, nakomelingen, pad_tekst
from ..filters import METHODEN, STATUSSEN, Filters, keuzes, rekeningen as alle_rekeningen
from ..categorizer.ai import maak_regel_van_voorstel
from ..categorizer.engine import (ONZEKERE_HERKOMSTEN, Motor,
                                  TransactieKenmerken, Voorstel)
from ..database import get_db, instelling, log, now_iso
from ..regelonderhoud import (WIS_TOELICHTING, hangende_transacties,
                              herbekijk, verslag)
from ..transacties import bewaar, haal, tel, werk_bij, zoek

bp = Blueprint("tx", __name__, url_prefix="/transacties")


def _alle_keuzes(conn, crypto):
    return keuzelijst(boom(conn, crypto, alfabetisch=True))


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
    filters = Filters.uit_aanvraag()
    platte = laad_alles(conn, crypto)
    cat_namen = {i: c.naam for i, c in platte.items()}
    categorie_ids = (sorted(nakomelingen(platte, filters.categorie_id))
                     if filters.categorie_id else None)

    sorteer = request.args.get("sorteer", "datum")
    aflopend = request.args.get("richting_sortering", "af") != "op"
    pagina = max(1, request.args.get("pagina", 1, type=int))
    per_pagina = 100

    rijen, aantal_gevonden = zoek(
        conn, crypto, filters=filters, categorie_ids=categorie_ids,
        cat_namen=cat_namen, sorteer=sorteer, aflopend=aflopend,
        limiet=per_pagina, offset=(pagina - 1) * per_pagina,
    )

    return render_template(
        "transacties.html",
        rijen=rijen, filters=filters, pagina=pagina, per_pagina=per_pagina,
        aantal_gevonden=aantal_gevonden, sorteer=sorteer, aflopend=aflopend,
        rekeningen=alle_rekeningen(conn, crypto),
        keuzes=keuzes(conn, crypto),
        methoden=METHODEN, statussen=STATUSSEN,
        pad_tekst=lambda *ids: pad_tekst(platte, *ids),
        hoofdcategorieen=[c for c in _alle_keuzes(conn, crypto) if c["niveau"] == 0],
        alle_categorieen=_alle_keuzes(conn, crypto),
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
            beschrijving=request.form.get("beschrijving", "").strip(),
            tegenpartij_rekening=request.form.get("tegenpartij_rekening", "").strip(),
            begunstigde=request.form.get("begunstigde", "").strip(),
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
            # Wie zelf indeelt, maakt de band met de regel los: een latere
            # wijziging aan die regel mag deze keuze niet meer overschrijven.
            regel_id=None,
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
        return redirect(veilig_terug(request.form.get("terug"), url_for("tx.lijst")))

    return render_template(
        "transactie_bewerken.html",
        tx=tx, rekeningen=_rekeningen(conn, crypto),
        terug=veilig_terug(request.args.get("terug"), url_for("tx.lijst")),
        **_herkomst(conn, crypto, tx), **_cat_context(conn, crypto),
    )


def _herkomst(conn, crypto, tx) -> dict:
    """Alles wat aan een transactie vasthangt, voor het bewerkscherm."""
    rekening = conn.execute(
        "SELECT naam_enc, iban_enc FROM rekeningen WHERE id = ?", (tx.rekening_id,)
    ).fetchone()

    rij = conn.execute(
        "SELECT ruwe_data_enc, batch_id FROM transacties WHERE id = ?", (tx.id,)
    ).fetchone()

    ruwe_data = {}
    if rij and rij["ruwe_data_enc"]:
        try:
            ruwe_data = {k: v for k, v in
                         json.loads(crypto.dec(rij["ruwe_data_enc"])).items() if v}
        except (ValueError, TypeError):
            ruwe_data = {}

    batch = None
    if rij and rij["batch_id"]:
        b = conn.execute("SELECT * FROM import_batches WHERE id = ?",
                         (rij["batch_id"],)).fetchone()
        if b:
            batch = {"bestand": crypto.dec(b["bestand_enc"]) or "—",
                     "tijdstip": b["tijdstip"], "profiel": b["profiel"]}

    # Kredietkaart: de afrekening waaronder deze aankoop hangt, of net omgekeerd
    # de aankopen die onder deze afrekening hangen.
    ouder = haal(conn, crypto, tx.ouder_tx_id) if tx.ouder_tx_id else None
    kinderen = []
    if tx.is_afrekening:
        from ..transacties import rij_naar_object
        kinderen = [rij_naar_object(r, crypto) for r in conn.execute(
            "SELECT * FROM transacties WHERE ouder_tx_id = ? ORDER BY boekdatum",
            (tx.id,))]

    return {
        "rekening_naam": crypto.dec(rekening["naam_enc"]) if rekening else "—",
        "rekening_iban": (crypto.dec(rekening["iban_enc"]) or "") if rekening else "",
        "ruwe_data": ruwe_data,
        "batch": batch,
        "ouder": ouder,
        "kinderen": kinderen,
    }


@bp.route("/<int:tx_id>/verwijderen", methods=["POST"])
@login_vereist
def verwijderen(tx_id: int):
    conn = get_db()
    conn.execute("DELETE FROM transacties WHERE id = ?", (tx_id,))
    log(conn, g.crypto, g.gebruiker, "transactie_verwijderd", f"id={tx_id}")
    conn.commit()
    flash("Transactie verwijderd.", "goed")
    return redirect(veilig_terug(request.form.get("terug"), url_for("tx.lijst")))


@bp.route("/nazicht")
@login_vereist
def nazicht():
    conn = get_db()
    crypto = g.crypto
    platte = laad_alles(conn, crypto)
    onzeker, _ = zoek(conn, crypto, filters=Filters(status="nazicht"), limiet=100)
    open_rijen, _ = zoek(conn, crypto, filters=Filters(status="niet_toegewezen"),
                         limiet=100)
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
    return redirect(veilig_terug(request.form.get("terug"), url_for("tx.nazicht")))


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
    """Laat de motor opnieuw los op alles binnen het gekozen bereik.

    Het werk zelf staat in `app/herindeling.py`, zodat het ook achter een
    voortgangsmeter kan lopen wanneer het vanuit een andere handeling komt.
    """
    conn = get_db()
    crypto = g.crypto
    vanaf = now_iso()

    bereik = herindeling.normaliseer(request.form.get("bereik"))
    hoeveel = conn.execute(
        "SELECT COUNT(*) n FROM transacties WHERE "
        + herindeling.BEREIKEN[bereik][1]).fetchone()["n"]
    if hoeveel:
        backup.maak("herindeling")

    uitslag = herindeling.voer_uit(conn, crypto, bereik)

    log(conn, crypto, g.gebruiker, "herindeling",
        f"bereik={uitslag.bereik} veranderd={uitslag.totaal}"
        f" ongewijzigd={uitslag.ongewijzigd} "
        + " ".join(f"{m}={n}" for m, n in sorted(uitslag.per_methode.items())))
    conn.commit()

    if not uitslag.totaal:
        flash(f"Er viel niets bij te sturen bij {uitslag.omschrijving}. "
              f"{uitslag.ongewijzigd} transacties stonden al zoals de motor ze zou "
              "indelen.", "goed")
        return redirect(url_for("tx.nazicht"))

    flash(herindeling_melding(uitslag), "goed")
    return redirect(url_for("tx.lijst", gewijzigd_na=vanaf))


def herindeling_melding(uitslag) -> str:
    """Eén zin met de uitsplitsing per stap van de motor."""
    namen = dict(METHODEN)
    uitsplitsing = ", ".join(f"{n} via {namen.get(m, m).lower()}"
                             for m, n in uitslag.per_methode.most_common())
    return (f"{uitslag.totaal} transacties opnieuw ingedeeld "
            f"({uitslag.omschrijving}): {uitsplitsing}."
            + (f" {uitslag.ongewijzigd} stonden al goed."
               if uitslag.ongewijzigd else "")
            + " Hieronder staan net die transacties.")


# --------------------------------------------------------------------------
# Oordelen over de regel die een transactie indeelde
# --------------------------------------------------------------------------

@bp.route("/<int:tx_id>/regel", methods=["GET", "POST"])
@login_vereist
def regel_oordeel(tx_id: int):
    """Klopt de regel die deze transactie indeelde, of niet?

    Een regel die uit je historiek is afgeleid en naar meer dan één categorie
    wees, deelt wel in maar vraagt om bevestiging. Je zag dan wel *regel* als
    bron, maar nergens wélke regel — en dus ook niet waar je ze moest gaan
    rechtzetten. Hier kan dat in één handeling.
    """
    conn = get_db()
    crypto = g.crypto
    tx = haal(conn, crypto, tx_id)
    if tx is None:
        flash("Die transactie bestaat niet meer.", "fout")
        return redirect(url_for("tx.nazicht"))
    if not tx.regel_id:
        flash("Deze transactie is niet door een regel ingedeeld.", "fout")
        return redirect(url_for("tx.bewerken", tx_id=tx_id))

    regel = conn.execute("SELECT * FROM regels WHERE id = ?", (tx.regel_id,)).fetchone()
    if regel is None:
        flash("De regel die deze transactie indeelde, bestaat niet meer.", "fout")
        return redirect(url_for("tx.bewerken", tx_id=tx_id))

    if request.method == "POST":
        actie = request.form.get("actie")
        terug = veilig_terug(request.form.get("terug"), url_for("tx.nazicht"))

        if actie == "klopt":
            # De transactie is akkoord, en een regel die om bevestiging vroeg
            # hoeft dat niet meer te doen: ze is nu één keer goedgekeurd.
            werk_bij(conn, crypto, tx_id, status="bevestigd", zekerheid=1.0,
                     toelichting="Regel bevestigd.")
            gepromoveerd = regel["herkomst"] in ONZEKERE_HERKOMSTEN
            if gepromoveerd:
                conn.execute("UPDATE regels SET herkomst = ? WHERE id = ?",
                             (regel["herkomst"].replace("_onzeker", ""), regel["id"]))
            log(conn, crypto, g.gebruiker, "regel_bevestigd",
                f"tx={tx_id} regel={regel['id']}")
            conn.commit()
            flash("Bevestigd." + (" Deze regel vraagt voortaan niet meer om nazicht."
                                  if gepromoveerd else ""), "goed")
            return redirect(terug)

        if actie == "verwijderen":
            hingen = hangende_transacties(conn, crypto, regel["id"])
            conn.execute("DELETE FROM regels WHERE id = ?", (regel["id"],))
            uit = herbekijk(conn, crypto, hingen, toelichting=WIS_TOELICHTING)
            log(conn, crypto, g.gebruiker, "regel_verwijderd_vanuit_transactie",
                f"tx={tx_id} regel={regel['id']}")
            conn.commit()
            flash("Regel verwijderd. " + verslag(uit), "goed")
            return redirect(terug)

    return render_template(
        "transactie_regel.html", tx=tx,
        regel={"id": regel["id"], "naam": crypto.dec(regel["naam_enc"]) or "",
               "veld": regel["veld"], "operator": regel["operator"],
               "waarde": crypto.dec(regel["waarde_enc"]) or "",
               "herkomst": regel["herkomst"],
               "onzeker": regel["herkomst"] in ONZEKERE_HERKOMSTEN},
        treffers=conn.execute("SELECT COUNT(*) n FROM transacties WHERE regel_id = ?",
                              (regel["id"],)).fetchone()["n"],
        terug=veilig_terug(request.args.get("terug"), url_for("tx.nazicht")),
    )
