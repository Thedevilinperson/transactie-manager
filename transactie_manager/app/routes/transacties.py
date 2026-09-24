"""Transacties bekijken, toevoegen, aanpassen en nakijken."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from urllib.parse import urlsplit
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import backup, herindeling, veilig_terug
from ..auth import login_vereist
from ..categories import boom, keuzelijst, laad_alles, nakomelingen, pad_tekst
from ..filters import METHODEN, STATUSSEN, Filters, keuzes, rekeningen as alle_rekeningen
from ..categorizer.ai import maak_regel_van_voorstel, webopzoeking_klaar
from ..categorizer.engine import (ONZEKERE_HERKOMSTEN, Motor,
                                  TransactieKenmerken, Voorstel, laad_regels,
                                  regel_past)
from ..database import get_db, instelling, log, now_iso
from .. import regelmaker
from ..regelonderhoud import (WIS_TOELICHTING, hangende_transacties, herbekijk,
                              herstel_bewerkte_onzekere_regels, maak_zeker,
                              pas_toe_geteld, verslag)
from .instellingen import EXTRA_OPERATOREN, HERKOMSTEN, VELDNAMEN, _regelrijen
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
        # De regels die jij hebt nagekeken, zodat de lijst er een vinkje bij
        # kan zetten zonder per rij een vraag te stellen.
        bevestigde_regels={rij["id"] for rij in conn.execute(
            "SELECT id FROM regels WHERE bevestigd_op IS NOT NULL")},
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
            nagekeken=1,
            zekerheid=1.0,
            toelichting="Manueel aangepast.",
            # Wie zelf indeelt, maakt de band met de regel los: een latere
            # wijziging aan die regel mag deze keuze niet meer overschrijven.
            regel_id=None,
        )
        melding = "Transactie opgeslagen."
        soort = "goed"
        if request.form.get("regel_maken") == "1":
            bijgewerkt = haal(conn, crypto, tx_id)
            samenstelling, reden = regelmaker.lees(request.form)
            if bijgewerkt.categorie_id is None:
                melding += " De regel is niet aangemaakt: kies eerst een categorie."
                soort = "fout"
            elif samenstelling is None:
                melding += " De regel is niet aangemaakt: " + reden
                soort = "fout"
            else:
                ids = (bijgewerkt.categorie_id, bijgewerkt.subcategorie_id,
                       bijgewerkt.subsub_id)
                regel_id = regelmaker.bewaar(conn, crypto, samenstelling, ids,
                                             bijgewerkt.handelaar or None,
                                             bijgewerkt.land or None)
                log(conn, crypto, g.gebruiker, "regel toegevoegd",
                    f"regel={regel_id} vanuit tx={tx_id}")
                n = len(samenstelling.voorwaarden)
                melding += (f" Vaste regel “{samenstelling.naam}” aangemaakt"
                            f" ({n} {'voorwaarde' if n == 1 else 'voorwaarden'},"
                            f" prioriteit {samenstelling.prioriteit}).")
                if request.form.get("rv_toepassen") == "1":
                    # Ook de gelijkenissen die nog op nazicht staan: je hebt
                    # net zelf vastgelegd hoe zo'n transactie hoort. Wat met
                    # de hand of uit een bestand kwam, blijft staan.
                    telling = pas_toe_geteld(conn, crypto, regel_id,
                                             ook_onbevestigde_gelijkenis=True)
                    melding += _toegepast_melding(telling)
                    log(conn, crypto, g.gebruiker, "regel toegepast",
                        f"regel={regel_id} zonder={telling['zonder']}"
                        f" gelijkenis={telling['gelijkenis']}")
        flash(melding, soort)
        log(conn, crypto, g.gebruiker, "transactie_gewijzigd", f"id={tx_id}")
        conn.commit()
        return redirect(veilig_terug(request.form.get("terug"), url_for("tx.lijst")))

    terug = veilig_terug(request.args.get("terug"), url_for("tx.lijst"))
    # Kom je uit het nazicht, dan krijgt het blok "Hoe deze indeling tot stand
    # kwam" de knop voor de webopzoeking. Het terugadres zegt waar je vandaan
    # komt; filters en sortering in de vraagstring doen er niet toe.
    vanuit_nazicht = (urlsplit(terug).path.rstrip("/")
                      == url_for("tx.nazicht").rstrip("/"))
    return render_template(
        "transactie_bewerken.html",
        tx=tx, rekeningen=_rekeningen(conn, crypto),
        terug=terug,
        vanuit_nazicht=vanuit_nazicht,
        web_klaar=vanuit_nazicht and webopzoeking_klaar(conn),
        ai_actief=instelling(conn, "ai_actief", "0") == "1",
        veldnamen=VELDNAMEN, extra_operatoren=EXTRA_OPERATOREN,
        **_herkomst(conn, crypto, tx), **_cat_context(conn, crypto),
    )


def _toegepast_melding(telling) -> str:
    """Wat het toepassen van een nieuwe regel deed, in één zin."""
    delen = []
    if telling["zonder"]:
        n = telling["zonder"]
        delen.append(f"{n} {'transactie' if n == 1 else 'transacties'} zonder categorie")
    if telling["gelijkenis"]:
        n = telling["gelijkenis"]
        delen.append(f"{n} {'transactie' if n == 1 else 'transacties'} met een nog niet "
                     "bevestigde gelijkenis")
    if not delen:
        return " Er waren geen andere transacties zonder categorie of met een " \
               "onbevestigde gelijkenis waarop ze past."
    return " Ook toegepast op " + " en ".join(delen) + "."


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


# Waarop de tabellen in het nazicht gesorteerd kunnen worden. De sleutels zijn
# die van zoek(); "categorie" is daar de kolom met het voorstel.
NAZICHT_SORTERINGEN = {"datum", "tegenpartij", "categorie", "bron", "zekerheid",
                       "bedrag"}
NAZICHT_LIMIET = 300


@bp.route("/nazicht")
@login_vereist
def nazicht():
    conn = get_db()
    crypto = g.crypto

    # Eenmalig: wat je vóór schemaversie 10 al bevestigde, als nagekeken
    # markeren (gebeurt normaal al bij het aanmelden).
    herindeling.markeer_eerder_nagekeken(conn, crypto)

    # Eenmalig: onzekere regels die je al bewerkt had, alsnog zeker maken.
    hersteld = herstel_bewerkte_onzekere_regels(conn, crypto)
    if hersteld is not None:
        flash("Regels die je eerder al had rechtgezet, vroegen nog om nazicht. "
              "Dat is nu opgelost: " + verslag(hersteld), "goed")

    platte = laad_alles(conn, crypto)
    cat_namen = {i: c.naam for i, c in platte.items()}

    # Dezelfde filters als op de transactielijst. Status en "alleen bevestigd"
    # legt dit scherm zelf vast: elke tabel toont precies één status.
    filters = replace(Filters.uit_aanvraag(), status="", alleen_bevestigd=False)
    categorie_ids = (sorted(nakomelingen(platte, filters.categorie_id))
                     if filters.categorie_id else None)
    sorteer = request.args.get("sorteer", "datum")
    if sorteer not in NAZICHT_SORTERINGEN:
        sorteer = "datum"
    aflopend = request.args.get("richting_sortering", "af") != "op"

    def lijst_met(voorwaarde):
        return zoek(conn, crypto, filters=filters, categorie_ids=categorie_ids,
                    cat_namen=cat_namen, sorteer=sorteer, aflopend=aflopend,
                    limiet=NAZICHT_LIMIET, tellen=True, extra_waar=voorwaarde)

    # Een transactie op nazicht zónder categorie — bijvoorbeeld omdat de regel
    # die haar indeelde bewerkt of verwijderd is — heeft geen voorstel om te
    # bevestigen. Ze hoort bij "Zonder categorie", niet bij de voorstellen.
    onzeker, aantal_onzeker = lijst_met(
        "status = 'nazicht' AND categorie_id IS NOT NULL")
    open_rijen, aantal_open = lijst_met(
        "status = 'niet_toegewezen' OR (status = 'nazicht' AND categorie_id IS NULL)")

    gefilterd = bool(filters.jaren or filters.richting or filters.rekening_id
                     or filters.categorie_id or filters.landen or filters.winkels
                     or filters.methoden or filters.zoekterm)
    return render_template(
        "nazicht.html",
        onzeker=onzeker, open_rijen=open_rijen,
        aantal_onzeker=aantal_onzeker, aantal_open=aantal_open,
        limiet=NAZICHT_LIMIET, gefilterd=gefilterd,
        filters=filters, sorteer=sorteer, aflopend=aflopend,
        keuzes=keuzes(conn, crypto), rekeningen=alle_rekeningen(conn, crypto),
        methoden=METHODEN, bronnamen=dict(METHODEN),
        hoofdcategorieen=[c for c in _alle_keuzes(conn, crypto) if c["niveau"] == 0],
        pad_tekst=lambda *ids: pad_tekst(platte, *ids),
        ai_actief=instelling(conn, "ai_actief", "0") == "1",
        **_cat_context(conn, crypto),
    )


@bp.route("/<int:tx_id>/bevestigen", methods=["POST"])
@login_vereist
def bevestigen(tx_id: int):
    conn = get_db()
    crypto = g.crypto
    # nagekeken=1: jij hebt dit voorstel goedgekeurd. Daardoor blijft het
    # staan bij elke latere herindeling, ook bij het herbekijken van de
    # automatisch bevestigde gelijkenissen.
    werk_bij(conn, crypto, tx_id, status="bevestigd", zekerheid=1.0, nagekeken=1)
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
    """Bevestigt de voorstellen in één keer.

    Staat er een filter aan in het nazicht, dan stuurt het scherm de nummers
    mee van wat je op dat moment ziet, en worden alleen die bevestigd. Zonder
    nummers: alles wat op nazicht staat en een categorie heeft.
    """
    conn = get_db()
    ids = [i for i in request.form.getlist("id", type=int) if i]
    sql = ("UPDATE transacties SET status='bevestigd', zekerheid=1.0, nagekeken=1"
           " WHERE status='nazicht' AND categorie_id IS NOT NULL")
    params: list = []
    if ids:
        sql += f" AND id IN ({','.join('?' * len(ids))})"
        params = ids
    aantal = conn.execute(sql, params).rowcount
    log(conn, g.crypto, g.gebruiker, "bulk_bevestigd",
        f"aantal={aantal}" + (" (selectie)" if ids else ""))
    conn.commit()
    flash(f"{aantal} transacties bevestigd.", "goed")
    return redirect(veilig_terug(request.form.get("terug"), url_for("tx.nazicht")))


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
            # De transactie is akkoord, en de regel draagt voortaan jouw
            # goedkeuring. Vroeg ze om nazicht, dan hoeft dat niet meer.
            werk_bij(conn, crypto, tx_id, status="bevestigd", zekerheid=1.0,
                     toelichting="Regel bevestigd.", nagekeken=1)
            gepromoveerd = regel["herkomst"] in ONZEKERE_HERKOMSTEN
            conn.execute("UPDATE regels SET bevestigd_op = ?, bevestigd_door = ?"
                         " WHERE id = ?", (now_iso(), g.gebruiker, regel["id"]))
            meegenomen = 0
            if gepromoveerd:
                # De andere transacties van deze regel stonden om dezelfde
                # reden op nazicht; die gaan nu mee.
                hingen = hangende_transacties(conn, crypto, regel["id"])
                maak_zeker(conn, regel["id"])
                meegenomen = herbekijk(conn, crypto, hingen).bevestigd
            log(conn, crypto, g.gebruiker, "regel_bevestigd",
                f"tx={tx_id} regel={regel['id']} mee={meegenomen}")
            conn.commit()
            melding = "Bevestigd."
            if gepromoveerd:
                melding += " Deze regel vraagt voortaan niet meer om nazicht."
            if meegenomen:
                melding += (f" {meegenomen} andere "
                            f"{'transactie' if meegenomen == 1 else 'transacties'}"
                            " van deze regel mee bevestigd.")
            flash(melding, "goed")
            return redirect(terug)

        if actie == "intrekken":
            conn.execute("UPDATE regels SET bevestigd_op = NULL, bevestigd_door = NULL"
                         " WHERE id = ?", (regel["id"],))
            log(conn, crypto, g.gebruiker, "regel_bevestiging_ingetrokken",
                f"regel={regel['id']}")
            conn.commit()
            flash("De bevestiging is ingetrokken. De regel zelf blijft staan en "
                  "deelt gewoon verder in.", "goed")
            return redirect(url_for("tx.regel_oordeel", tx_id=tx_id, terug=terug))

        if actie == "verwijderen":
            hingen = hangende_transacties(conn, crypto, regel["id"])
            conn.execute("DELETE FROM regels WHERE id = ?", (regel["id"],))
            uit = herbekijk(conn, crypto, hingen, toelichting=WIS_TOELICHTING)
            log(conn, crypto, g.gebruiker, "regel_verwijderd_vanuit_transactie",
                f"tx={tx_id} regel={regel['id']}")
            conn.commit()
            flash("Regel verwijderd. " + verslag(uit), "goed")
            return redirect(terug)

    details = next(iter(_regelrijen(conn, crypto, regel["id"])), None)
    engine_regel = next((r for r in laad_regels(conn, crypto, alleen_actief=False)
                         if r.id == regel["id"]), None)
    past_nog = engine_regel is not None and regel_past(engine_regel, tx.kenmerken)
    zelfde_categorie = (tx.categorie_id == regel["categorie_id"]
                        and tx.subcategorie_id == regel["subcategorie_id"]
                        and tx.subsub_id == regel["subsub_id"])
    platte = laad_alles(conn, crypto)

    return render_template(
        "transactie_regel.html", tx=tx, regel=details,
        onzeker=regel["herkomst"] in ONZEKERE_HERKOMSTEN,
        herkomst=HERKOMSTEN.get(regel["herkomst"], regel["herkomst"]),
        veldnamen=VELDNAMEN, operatoren=EXTRA_OPERATOREN,
        past_nog=past_nog, zelfde_categorie=zelfde_categorie,
        tx_pad=pad_tekst(platte, tx.categorie_id, tx.subcategorie_id, tx.subsub_id),
        treffers=details["treffers"],
        terug=veilig_terug(request.args.get("terug"), url_for("tx.nazicht")),
    )
