"""Installatie bij eerste start, aanmelden en afmelden."""

from __future__ import annotations

import time

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .. import crypto as cryptomod
from ..auth import (beeindig_sessie, controleer_aanmelding, huidige_sessie,
                    maak_gebruiker, start_sessie)
from ..database import connect, seed_categorieen, seed_voorbeeldregels, heeft_gebruikers

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
                conn.commit()
            finally:
                conn.close()
            flash("Klaar. Meld je aan met je nieuwe account.", "goed")
            return redirect(url_for("auth.login"))

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
            if volgende.startswith("/"):
                return redirect(volgende)
            return redirect(url_for("dashboard.index"))

    return render_template("aanmelden.html", volgende=volgende)


@bp.route("/afmelden", methods=["POST", "GET"])
def logout():
    beeindig_sessie()
    session.clear()
    flash("Je bent afgemeld.", "goed")
    return redirect(url_for("auth.login"))
