"""Bijzondere invoerwegen: de categorielijst, de kredietkaartuittreksels in
PDF, en regels afleiden uit je ingelezen historiek."""

from __future__ import annotations

import collections
import secrets
from decimal import Decimal
from pathlib import Path

from flask import (Blueprint, flash, g, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.utils import secure_filename

from .. import backup, herindeling, taken, veilig_terug
from ..auth import login_vereist
from ..categorizer.engine import Motor, TransactieKenmerken
from ..config import UPLOAD_DIR
from ..database import connect, get_db, log, now_iso
from ..importers import kredietkaart as kk
from ..importers import referentie as ref
from ..importers import regelbouwer
from ..regelonderhoud import verslag
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
# Categorielijst (vroeger: referentielijst)
# ==========================================================================

@bp.route("/instellingen/referentielijst")
@login_vereist
def referentielijst_oud():
    """Het oude adres, voor bladwijzers van vóór versie 0.33.0."""
    return redirect(url_for("bijzonder.categorielijst"))


@bp.route("/instellingen/categorielijst", methods=["GET", "POST"])
@login_vereist
def categorielijst():
    if request.method == "POST":
        bestand = request.files.get("bestand")
        if not bestand or not bestand.filename:
            flash("Kies eerst een bestand.", "fout")
            return redirect(url_for("bijzonder.categorielijst"))
        bewaard = _bewaar_upload(bestand, {".xlsx", ".xlsm"})
        if bewaard is None:
            flash("Gebruik een Excel-bestand (.xlsx).", "fout")
            return redirect(url_for("bijzonder.categorielijst"))
        naam, pad = bewaard
        return redirect(url_for("bijzonder.categorielijst_voorbeeld",
                                token=pad.stem, naam=naam))

    conn = get_db()
    aantal_cats = conn.execute("SELECT COUNT(*) n FROM categorieen").fetchone()["n"]
    return render_template("referentielijst.html", aantal_cats=aantal_cats)


@bp.route("/instellingen/categorielijst/<token>")
@login_vereist
def categorielijst_voorbeeld(token: str):
    pad = _zoek_upload(token)
    if pad is None:
        flash("Het bestand is niet meer beschikbaar. Probeer opnieuw.", "fout")
        return redirect(url_for("bijzonder.categorielijst"))
    try:
        rijen = ref.lees(pad)
    except Exception as exc:  # noqa: BLE001
        flash(f"Het bestand kon niet gelezen worden: {exc}", "fout")
        return redirect(url_for("bijzonder.categorielijst"))

    return render_template(
        "referentielijst_voorbeeld.html",
        token=token, naam=request.args.get("naam", pad.name),
        analyse=ref.analyseer(rijen), staat=_huidige_staat(get_db()),
    )


@bp.route("/instellingen/categorielijst/uitvoeren", methods=["POST"])
@login_vereist
def categorielijst_uitvoeren():
    pad = _zoek_upload(request.form.get("token", ""))
    if pad is None:
        flash("Het bestand is niet meer beschikbaar.", "fout")
        return redirect(url_for("bijzonder.categorielijst"))

    conn = get_db()
    crypto = g.crypto
    vervang = request.form.get("vervang") == "1"

    # Integraal vervangen wist ook je regels en indelingen. Vóór die ingreep
    # gaat er een kopie van de databank op de plank.
    kopie = backup.maak("categorielijst")

    resultaat = ref.importeer(conn, crypto, ref.lees(pad), vervang=vervang)
    log(conn, crypto, g.gebruiker, "categorielijst_ingelezen", str(resultaat))
    conn.commit()

    try:
        pad.unlink()
    except OSError:
        pass

    flash(
        f"{resultaat['categorieen']} categorieën ingelezen."
        + (" Er staat een kopie van je databank van vlak hiervoor klaar."
           if kopie else " Let op: er kon geen kopie van de databank gelegd worden."),
        "goed",
    )
    return redirect(url_for("instellingen.categorieen"))


def _huidige_staat(conn) -> dict:
    """Wat er nu in de databank staat, om vooraf te kunnen waarschuwen."""
    def tel(sql):
        return conn.execute(sql).fetchone()["n"]
    return {
        "categorieen": tel("SELECT COUNT(*) n FROM categorieen"),
        "regels": tel("SELECT COUNT(*) n FROM regels"),
        "transacties": tel("SELECT COUNT(*) n FROM transacties"),
        "ingedeeld": tel("SELECT COUNT(*) n FROM transacties"
                         " WHERE categorie_id IS NOT NULL"),
        "handmatig": tel("SELECT COUNT(*) n FROM transacties"
                         " WHERE methode = 'manueel'"),
        "bevestigd": tel("SELECT COUNT(*) n FROM transacties"
                         " WHERE status = 'bevestigd'"),
    }


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
    jaar = request.args.get("jaar", type=int)
    status = request.args.get("status_f", "")

    # Eén doorloop voor alles: de lijst, de jaren en de tellingen. Het waren er
    # twee, plus een zoekopdracht per open afrekening — op tienduizenden rijen
    # liep dat op tot seconden.
    alles = kk.zoek_afrekeningen(conn, crypto)
    for a in alles:
        a["status"] = _afrekeningsstatus(a)
    jaren = kk.afrekeningsjaren(alles)

    getoond = [a for a in alles
               if (not jaar or a["boekdatum"][:4] == str(jaar))
               and (not status or a["status"] == status)]

    return render_template(
        "kredietkaart.html", afrekeningen=getoond, totaal=len(alles),
        jaren=jaren, gekozen_jaar=jaar, verwerkt=hangend, status=status,
        open_aantal=sum(1 for a in alles if a["status"] == "open"),
        tellingen=collections.Counter(a["status"] for a in alles),
    )


AFREKENINGSSTATUSSEN = [
    ("open", "Nog te doen"),
    ("uitgesplitst", "Uitgesplitst"),
    ("tegengeboekt", "Tegengeboekt"),
]


def _afrekeningsstatus(a: dict) -> str:
    """Uitgesplitst gaat voor: staan er aankopen onder, dan is dat de waarheid."""
    if a["is_afrekening"]:
        return "uitgesplitst"
    if a.get("tegenboeking_tx_id"):
        return "tegengeboekt"
    return "open"


@bp.route("/kredietkaart/tegenboekingen-koppelen", methods=["POST"])
@login_vereist
def tegenboekingen_koppelen():
    """Alle open afrekeningen met een eenduidige tegenboeking in één keer."""
    conn = get_db()
    crypto = g.crypto
    backup.maak("tegenboekingen")
    aantal = kk.koppel_tegenboekingen(conn, crypto)
    log(conn, crypto, g.gebruiker, "tegenboekingen_gekoppeld", f"aantal={aantal}")
    conn.commit()
    flash(f"{aantal} {'afrekening is' if aantal == 1 else 'afrekeningen zijn'}"
          " aan de tegenboeking gehangen." if aantal else
          "Geen enkele open afrekening heeft een eenduidige tegenboeking.", "goed")
    return redirect(veilig_terug(request.form.get("terug"),
                                 url_for("bijzonder.kredietkaart")))


@bp.route("/kredietkaart/afrekening/<int:tx_id>/tegenboeking", methods=["GET", "POST"])
@login_vereist
def tegenboeking(tx_id: int):
    """De tegenboeking van één afrekening met de hand aanwijzen of loskoppelen."""
    conn = get_db()
    crypto = g.crypto
    afrekening = haal(conn, crypto, tx_id)
    if afrekening is None:
        flash("Die transactie bestaat niet meer.", "fout")
        return redirect(url_for("bijzonder.kredietkaart"))

    if request.method == "POST":
        keuze = request.form.get("tegenboeking_id", type=int)
        if keuze:
            conn.execute("UPDATE transacties SET tegenboeking_tx_id=? WHERE id=?",
                         (keuze, tx_id))
            melding = "De afrekening staat nu als tegengeboekt."
        else:
            conn.execute("UPDATE transacties SET tegenboeking_tx_id=NULL WHERE id=?",
                         (tx_id,))
            melding = "De koppeling met de tegenboeking is weg."
        log(conn, crypto, g.gebruiker, "tegenboeking_gezet", f"tx={tx_id} naar={keuze}")
        conn.commit()
        flash(melding, "goed")
        return redirect(url_for("bijzonder.kredietkaart"))

    huidig = None
    if afrekening.tegenboeking_tx_id:
        huidig = haal(conn, crypto, afrekening.tegenboeking_tx_id)
    return render_template(
        "kredietkaart_tegenboeking.html", afrekening=afrekening, huidig=huidig,
        kandidaten=kk.zoek_tegenboekingen(conn, crypto, tx_id),
        venster=kk.VENSTER_DAGEN,
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
    # Drie keer hetzelfde bedrag bij dezelfde zaak op één dag zijn drie
    # aankopen; het volgnummer houdt ze uit elkaar.
    import collections
    herhaling: collections.Counter = collections.Counter()

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
            referentie=(f"{kaart}|{item.datum}|{item.omschrijving[:40]}|{item.bedrag}"
                        + _volgnummer(herhaling, kaart, item)),
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


def _volgnummer(teller, kaart: str, item) -> str:
    """Maakt de referentie uniek wanneer dezelfde aankoop meermaals voorkomt."""
    sleutel = (kaart, str(item.datum), item.omschrijving, str(item.bedrag))
    teller[sleutel] += 1
    return "" if teller[sleutel] == 1 else f"|{teller[sleutel]}"


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


# ==========================================================================
# Voorbeeldbestanden
# ==========================================================================

VOORBEELDEN = {
    "historiek": ("voorbeeld_historiek_met_categorieen.xlsx",
                  "Historiek met kolommen en al toegekende indeling"),
    "categorielijst": ("voorbeeld_categorielijst.xlsx",
                       "Categorielijst met drie kolommen"),
}


@bp.route("/voorbeeld/<naam>")
@login_vereist
def voorbeeldbestand(naam: str):
    if naam not in VOORBEELDEN:
        flash("Dat voorbeeldbestand bestaat niet.", "fout")
        return redirect(url_for("importeren.start"))
    bestand = VOORBEELDEN[naam][0]
    map_ = Path(__file__).resolve().parent.parent / "voorbeelden"
    return send_from_directory(map_, bestand, as_attachment=True)


# ==========================================================================
# Regels maken uit de ingelezen historiek
# ==========================================================================

def _historiek_instellingen(bron) -> dict:
    """De keuzes van het scherm, uit de vraag of het formulier."""
    kolommen = [k for k in bron.getlist("kolom") if k in regelbouwer.KOLOMMEN]
    return {
        "kolommen": tuple(kolommen) or regelbouwer.STANDAARD_KOLOMMEN,
        "bron": bron.get("bron") if bron.get("bron") in regelbouwer.BRONNEN else "bestand",
        # Een formulier stuurt een niet-aangevinkt vakje niet mee. Het verborgen
        # veld "ingevuld" zegt of de keuzes al eens verstuurd zijn.
        "richting_apart": (bron.get("richting_apart") == "1"
                           if bron.get("ingevuld") else True),
        "afleiden": bron.get("afleiden") == "1" if bron.get("ingevuld") else True,
    }


@bp.route("/instellingen/regels-uit-historiek", methods=["GET", "POST"])
@login_vereist
def regels_uit_historiek():
    conn = get_db()
    crypto = g.crypto
    inst = _historiek_instellingen(request.values)

    if request.method == "POST" and request.form.get("actie") == "wegschrijven":
        # Duizenden regels wegschrijven en daarna toepassen duurt te lang om de
        # browser op te laten wachten. Het werk loopt daarom in een aparte
        # draad, met dezelfde voortgangsmeter als een bestandsinvoer.
        token = secrets.token_hex(8)
        nadien = request.form.get("nadien", "regels")
        taken.start(
            token, "Regels maken uit je historiek", _verwerk_historiek, crypto,
            dict(inst, vervang_geleerd=request.form.get("vervang_geleerd") == "1",
                 nadien=nadien if nadien in ("regels", "onbevestigd") else None,
                 gebruiker=g.gebruiker))
        return redirect(url_for("bijzonder.historiek_bezig", token=token))

    analyse = regelbouwer.analyseer(
        conn, crypto, inst["kolommen"], bron=inst["bron"],
        richting_apart=inst["richting_apart"], afleiden=inst["afleiden"])
    return render_template(
        "regels_uit_historiek.html", analyse=analyse, inst=inst,
        kolommen=regelbouwer.KOLOMMEN, bronnen=regelbouwer.BRONNEN,
        voorbeelden=regelbouwer.voorbeelden(conn, crypto, analyse),
        bestaand=conn.execute(
            "SELECT COUNT(*) n FROM regels WHERE herkomst IN"
            " ('historiek', 'historiek_onzeker', 'historiek_afgeleid')").fetchone()["n"],
    )


def _verwerk_historiek(taak, crypto, inst: dict) -> dict:
    """Regels maken, wegschrijven en desgevraagd meteen toepassen.

    Draait in een aparte draad, dus met een eigen verbinding naar de databank.
    """
    from ..regelonderhoud import herbekijk_alles

    conn = connect()
    try:
        taak.fase = "Kopie van de databank leggen"
        backup.maak("regels_uit_historiek")

        taak.fase = "Historiek doorlopen"
        analyse = regelbouwer.analyseer(
            conn, crypto, inst["kolommen"], bron=inst["bron"],
            richting_apart=inst["richting_apart"], afleiden=inst["afleiden"])

        taak.totaal = len(analyse.regels)
        taak.vorder(0, "Regels wegschrijven")
        resultaat = regelbouwer.schrijf(
            conn, crypto, analyse, vervang_geleerd=inst["vervang_geleerd"],
            gebruiker=inst["gebruiker"], taak=taak)
        log(conn, crypto, inst["gebruiker"], "regels_uit_historiek",
            f"kolommen={','.join(inst['kolommen'])} {resultaat}")
        conn.commit()

        uit = dict(resultaat, nadien=None)
        if inst["nadien"] == "regels":
            taak.fase = "Alle regels opnieuw toepassen"
            uitkomst = herbekijk_alles(conn, crypto)
            log(conn, crypto, inst["gebruiker"], "regels opnieuw toegepast",
                f"gewist={uitkomst.gewist} anders={uitkomst.overgenomen}"
                f" erbij={uitkomst.erbij} vervangen={uitkomst.vervangen}")
            conn.commit()
            uit["nadien"] = verslag(uitkomst)
        elif inst["nadien"] == "onbevestigd":
            taak.fase = "Opnieuw indelen"
            taak.stand = 0
            uitslag = herindeling.voer_uit(conn, crypto, "onbevestigd", taak=taak)
            log(conn, crypto, inst["gebruiker"], "herindeling",
                f"bereik={uitslag.bereik} veranderd={uitslag.totaal}")
            conn.commit()
            uit["nadien"] = (f"Daarna zijn {uitslag.totaal} transacties opnieuw "
                             f"ingedeeld ({uitslag.omschrijving}).")

        uit["samenvatting"] = _samenvatting(uit)
        return uit
    finally:
        conn.close()


def _samenvatting(uit: dict) -> str:
    """De zin onder de cijfers, zodat het scherm niet hoeft te rekenen."""
    zin = (f"{uit['regels']} regels gemaakt uit je historiek: {uit['bevestigd']} "
           f"bevestigd, {uit['onbevestigd']} onbevestigd omdat ze naar meer dan één "
           f"categorie wezen, en {uit['afgeleid']} door de app afgeleid (onbevestigd).")
    return zin + (" " + uit["nadien"] if uit["nadien"] else " Er is niets toegepast.")


@bp.route("/instellingen/regels-uit-historiek/bezig/<token>")
@login_vereist
def historiek_bezig(token: str):
    taak = taken.haal(token)
    if taak is None:
        flash("Die bewerking is niet meer bekend.", "fout")
        return redirect(url_for("bijzonder.regels_uit_historiek"))
    return render_template("regels_uit_historiek_bezig.html", token=token, taak=taak)


@bp.route("/instellingen/regels-uit-historiek/voortgang/<token>")
@login_vereist
def historiek_voortgang(token: str):
    taak = taken.haal(token)
    if taak is None:
        return jsonify({"fout": "onbekend"}), 404
    return jsonify(taak.naar_json())
