"""Installatie bij eerste start, aanmelden en afmelden."""

from __future__ import annotations

import time

from flask import (Blueprint, current_app, flash, g, redirect, render_template, request,
                   session, url_for)

from .. import veilig_terug
from .. import crypto as cryptomod
from .. import lokaal, mail
from .. import backup, herindeling
from ..auth import (HERSTELCODE_MINUTEN, beeindig_sessie, controleer_aanmelding,
                    herstel_wachtwoord, huidige_sessie, login_vereist, maak_gebruiker,
                    maak_herstelcode, start_sessie, zet_herstelsleutel)
from ..database import connect, get_db, seed_categorieen, seed_voorbeeldregels, heeft_gebruikers

bp = Blueprint("auth", __name__)

MIN_WACHTWOORD = 10

# Eenvoudige rem op herhaalde pogingen per IP-adres.
_POGINGEN: dict[str, list[float]] = {}
MAX_POGINGEN = 8
VENSTER_SECONDEN = 300


def _te_veel_pogingen(ip: str) -> bool:
    nu = time.time()
    pogingen = [t for t in _POGINGEN.get(ip, []) if nu - t < VENSTER_SECONDEN]
    _POGINGEN[ip] = pogingen
    return len(pogingen) >= MAX_POGINGEN


def _noteer_poging(ip: str) -> None:
    _POGINGEN.setdefault(ip, []).append(time.time())


@bp.route("/installatie", methods=["GET", "POST"])
def installatie():
    if heeft_gebruikers():
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        naam = request.form.get("gebruikersnaam", "").strip()
        wachtwoord = request.form.get("wachtwoord", "")
        herhaling = request.form.get("herhaling", "")

        if len(naam) < 3:
            flash("Kies een gebruikersnaam van minstens 3 tekens.", "fout")
        elif len(wachtwoord) < MIN_WACHTWOORD:
            flash(f"Het wachtwoord moet minstens {MIN_WACHTWOORD} tekens lang zijn.", "fout")
        elif wachtwoord != herhaling:
            flash("De twee wachtwoorden zijn niet gelijk.", "fout")
        else:
            dek = cryptomod.new_dek()
            maak_gebruiker(naam, wachtwoord, dek, is_beheerder=True)
            crypto = cryptomod.Crypto(dek)
            conn = connect()
            try:
                seed_categorieen(conn, crypto)
                seed_voorbeeldregels(conn, crypto)
                rij = conn.execute(
                    "SELECT id FROM gebruikers WHERE gebruikersnaam=?", (naam,)).fetchone()
                conn.commit()
            finally:
                conn.close()

            herstelsleutel = zet_herstelsleutel(rij["id"], dek)
            # Eén keer tonen, daarna nergens meer leesbaar.
            session["nieuwe_herstelsleutel"] = herstelsleutel
            return redirect(url_for("auth.herstelsleutel_tonen"))

    return render_template("installatie.html", min_wachtwoord=MIN_WACHTWOORD)


@bp.route("/aanmelden", methods=["GET", "POST"])
def login():
    if huidige_sessie() is not None:
        return redirect(url_for("dashboard.index"))

    volgende = request.args.get("volgende") or request.form.get("volgende") or ""
    ip = request.remote_addr or "onbekend"

    if request.method == "POST":
        if _te_veel_pogingen(ip):
            flash("Te veel mislukte pogingen. Wacht een paar minuten.", "fout")
            return render_template("aanmelden.html", volgende=volgende), 429

        naam = request.form.get("gebruikersnaam", "")
        wachtwoord = request.form.get("wachtwoord", "")
        rij, dek = controleer_aanmelding(naam, wachtwoord)
        if rij is None:
            _noteer_poging(ip)
            flash("Gebruikersnaam of wachtwoord klopt niet.", "fout")
        else:
            _POGINGEN.pop(ip, None)
            start_sessie(rij, dek)
            # Eén kopie per dag, bij de eerste aanmelding. Een vaste taak zou
            # hier niets toevoegen: wat niet gebruikt wordt, verandert ook niet.
            backup.dagelijks()
            # Eenmalig na de update naar schemaversie 10: wat je vroeger al
            # bevestigde, als nagekeken markeren. Dat vraagt de sleutel, en
            # die is er pas nu.
            try:
                herindeling.markeer_eerder_nagekeken(get_db(), cryptomod.Crypto(dek))
            except Exception:  # noqa: BLE001 — aanmelden mag hier nooit op vastlopen
                current_app.logger.exception("Markeren van nagekeken transacties mislukt")
            return redirect(veilig_terug(volgende, url_for("dashboard.index")))

    return render_template("aanmelden.html", volgende=volgende)


@bp.route("/afmelden", methods=["POST", "GET"])
def logout():
    beeindig_sessie()
    session.clear()
    flash("Je bent afgemeld.", "goed")
    return redirect(url_for("auth.login"))


@bp.route("/herstelsleutel")
def herstelsleutel_tonen():
    sleutel = session.pop("nieuwe_herstelsleutel", None)
    if not sleutel:
        return redirect(url_for("auth.login"))
    return render_template("herstelsleutel.html", sleutel=sleutel, na_installatie=True)


# --------------------------------------------------------------------------
# Wachtwoord vergeten
# --------------------------------------------------------------------------

@bp.route("/wachtwoord-vergeten", methods=["GET", "POST"])
def wachtwoord_vergeten():
    conn = get_db()
    kan_mailen = mail.actief(conn)

    if request.method == "POST":
        naam = request.form.get("gebruikersnaam", "").strip()
        ip = request.remote_addr or "onbekend"
        if _te_veel_pogingen(ip):
            flash("Te veel aanvragen. Wacht een paar minuten.", "fout")
            return render_template("wachtwoord_vergeten.html", kan_mailen=kan_mailen), 429
        _noteer_poging(ip)

        rij = conn.execute(
            "SELECT id, gebruikersnaam, email_lok, herstel_wrapped FROM gebruikers"
            " WHERE gebruikersnaam=? AND actief=1", (naam,)).fetchone()

        # Altijd hetzelfde antwoord: zo verraadt dit scherm niet welke
        # gebruikersnamen bestaan.
        if rij is not None and rij["herstel_wrapped"] and kan_mailen:
            adres = lokaal.ontsleutel(rij["email_lok"])
            if adres:
                try:
                    code = maak_herstelcode(rij["id"])
                    mail.verstuur_herstelcode(conn, adres, rij["gebruikersnaam"], code,
                                              HERSTELCODE_MINUTEN)
                except mail.MailFout:
                    pass
        session["herstel_naam"] = naam
        return redirect(url_for("auth.wachtwoord_herstellen"))

    return render_template("wachtwoord_vergeten.html", kan_mailen=kan_mailen)


@bp.route("/wachtwoord-herstellen", methods=["GET", "POST"])
def wachtwoord_herstellen():
    naam = session.get("herstel_naam", "")

    if request.method == "POST":
        naam = request.form.get("gebruikersnaam", naam).strip()
        wachtwoord = request.form.get("wachtwoord", "")
        herhaling = request.form.get("herhaling", "")

        if len(wachtwoord) < MIN_WACHTWOORD:
            flash(f"Het nieuwe wachtwoord moet minstens {MIN_WACHTWOORD} tekens "
                  "lang zijn.", "fout")
        elif wachtwoord != herhaling:
            flash("De twee wachtwoorden zijn niet gelijk.", "fout")
        else:
            gelukt, boodschap = herstel_wachtwoord(
                naam, request.form.get("code", ""),
                request.form.get("herstelsleutel", ""), wachtwoord)
            if gelukt:
                session.pop("herstel_naam", None)
                flash("Je wachtwoord is aangepast. Meld je aan.", "goed")
                return redirect(url_for("auth.login"))
            flash(boodschap, "fout")

    return render_template("wachtwoord_herstellen.html", gebruikersnaam=naam,
                           min_wachtwoord=MIN_WACHTWOORD,
                           geldig_minuten=HERSTELCODE_MINUTEN)


@bp.route("/nieuwe-herstelsleutel", methods=["POST"])
@login_vereist
def nieuwe_herstelsleutel():
    sleutel = zet_herstelsleutel(g.sessie["id"], g.sessie["dek"])
    return render_template("herstelsleutel.html", sleutel=sleutel, na_installatie=False)
