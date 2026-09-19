"""Instellingen: rekeningen, categorieën, regels, AI-model en gebruikers."""

from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import lokaal, mail
from ..auth import (beheerder_vereist, herstelstatus, login_vereist, maak_gebruiker,
                    wijzig_wachtwoord, zet_herstelmail)
from ..categories import boom, keuzelijst, laad_alles
from ..categorizer.ai import test_verbinding
from ..crypto import normalize, normalize_iban
from ..database import connect, get_db, instelling, log, now_iso, zet_instelling
from ..regelonderhoud import (BEWERKT_TOELICHTING, UIT_TOELICHTING, WIS_TOELICHTING,
                              Uitkomst, hangende_transacties, herbekijk, herbekijk_alles,
                              pas_toe, verslag)

bp = Blueprint("instellingen", __name__, url_prefix="/instellingen")


@bp.route("/")
@login_vereist
def index():
    return redirect(url_for("instellingen.rekeningen"))


# --------------------------------------------------------------------------
# Rekeningen
# --------------------------------------------------------------------------

@bp.route("/rekeningen", methods=["GET", "POST"])
@login_vereist
def rekeningen():
    conn = get_db()
    crypto = g.crypto

    if request.method == "POST":
        actie = request.form.get("actie")
        if actie == "toevoegen":
            naam = request.form.get("naam", "").strip()
            iban = normalize_iban(request.form.get("iban", ""))
            if not naam:
                flash("Geef de rekening een naam.", "fout")
            else:
                conn.execute(
                    "INSERT INTO rekeningen (naam_enc, iban_enc, iban_idx, bank_enc, munt,"
                    " volgorde) VALUES (?,?,?,?,?,?)",
                    (crypto.enc(naam), crypto.enc(iban) if iban else None,
                     crypto.blind(iban, iban=True) if iban else None,
                     crypto.enc(request.form.get("bank", "").strip()) or None,
                     request.form.get("munt", "EUR"),
                     conn.execute("SELECT COUNT(*) n FROM rekeningen").fetchone()["n"]),
                )
                conn.commit()
                flash("Rekening toegevoegd.", "goed")
        elif actie == "wijzigen":
            rek_id = request.form.get("id", type=int)
            iban = normalize_iban(request.form.get("iban", ""))
            conn.execute(
                "UPDATE rekeningen SET naam_enc=?, iban_enc=?, iban_idx=?, bank_enc=?,"
                " munt=?, actief=? WHERE id=?",
                (crypto.enc(request.form.get("naam", "").strip()),
                 crypto.enc(iban) if iban else None,
                 crypto.blind(iban, iban=True) if iban else None,
                 crypto.enc(request.form.get("bank", "").strip()) or None,
                 request.form.get("munt", "EUR"),
                 1 if request.form.get("actief") == "1" else 0, rek_id),
            )
            conn.commit()
            flash("Rekening bijgewerkt.", "goed")
        elif actie == "verwijderen":
            rek_id = request.form.get("id", type=int)
            in_gebruik = conn.execute(
                "SELECT COUNT(*) n FROM transacties WHERE rekening_id=?", (rek_id,)
            ).fetchone()["n"]
            if in_gebruik:
                flash(f"Deze rekening heeft {in_gebruik} transacties. Zet ze op niet-actief "
                      "in plaats van te verwijderen.", "fout")
            else:
                conn.execute("DELETE FROM rekeningen WHERE id=?", (rek_id,))
                conn.commit()
                flash("Rekening verwijderd.", "goed")
        return redirect(url_for("instellingen.rekeningen"))

    rijen = []
    for r in conn.execute("SELECT * FROM rekeningen ORDER BY volgorde, id"):
        aantal = conn.execute(
            "SELECT COUNT(*) n FROM transacties WHERE rekening_id=?", (r["id"],)
        ).fetchone()["n"]
        rijen.append({
            "id": r["id"], "naam": crypto.dec(r["naam_enc"]),
            "iban": crypto.dec(r["iban_enc"]) or "", "bank": crypto.dec(r["bank_enc"]) or "",
            "munt": r["munt"], "actief": bool(r["actief"]), "aantal": aantal,
        })
    return render_template("instellingen_rekeningen.html", rijen=rijen)


# --------------------------------------------------------------------------
# Categorieën
# --------------------------------------------------------------------------

@bp.route("/categorieen", methods=["GET", "POST"])
@login_vereist
def categorieen():
    conn = get_db()
    crypto = g.crypto

    if request.method == "POST":
        actie = request.form.get("actie")
        if actie == "toevoegen":
            naam = request.form.get("naam", "").strip()
            ouder_id = request.form.get("ouder_id", type=int)
            soort = request.form.get("soort", "uit")
            niveau = 0
            if ouder_id:
                ouder = conn.execute(
                    "SELECT niveau, soort FROM categorieen WHERE id=?", (ouder_id,)
                ).fetchone()
                if ouder is None:
                    flash("De gekozen bovenliggende categorie bestaat niet.", "fout")
                    return redirect(url_for("instellingen.categorieen"))
                if ouder["niveau"] >= 2:
                    flash("Er zijn maximaal drie niveaus: hoofd, sub en sub-sub.", "fout")
                    return redirect(url_for("instellingen.categorieen"))
                niveau = ouder["niveau"] + 1
                soort = ouder["soort"]
            if not naam:
                flash("Geef de categorie een naam.", "fout")
            else:
                conn.execute(
                    "INSERT INTO categorieen (ouder_id, niveau, soort, naam_enc, naam_idx,"
                    " volgorde) VALUES (?,?,?,?,?,?)",
                    (ouder_id or None, niveau, soort, crypto.enc(naam), crypto.blind(naam),
                     conn.execute(
                         "SELECT COUNT(*) n FROM categorieen WHERE IFNULL(ouder_id,0)=?",
                         (ouder_id or 0,)).fetchone()["n"]),
                )
                conn.commit()
                flash(f"Categorie “{naam}” toegevoegd.", "goed")
        elif actie == "hernoemen":
            cat_id = request.form.get("id", type=int)
            naam = request.form.get("naam", "").strip()
            if naam:
                conn.execute(
                    "UPDATE categorieen SET naam_enc=?, naam_idx=? WHERE id=?",
                    (crypto.enc(naam), crypto.blind(naam), cat_id),
                )
                conn.commit()
                flash("Naam aangepast.", "goed")
        elif actie == "verplaatsen":
            cat_id = request.form.get("id", type=int)
            richting = request.form.get("richting")
            rij = conn.execute("SELECT * FROM categorieen WHERE id=?", (cat_id,)).fetchone()
            if rij:
                buur = conn.execute(
                    "SELECT * FROM categorieen WHERE IFNULL(ouder_id,0)=IFNULL(?,0)"
                    f" AND volgorde {'<' if richting == 'omhoog' else '>'} ?"
                    f" ORDER BY volgorde {'DESC' if richting == 'omhoog' else 'ASC'} LIMIT 1",
                    (rij["ouder_id"], rij["volgorde"]),
                ).fetchone()
                if buur:
                    conn.execute("UPDATE categorieen SET volgorde=? WHERE id=?",
                                 (buur["volgorde"], rij["id"]))
                    conn.execute("UPDATE categorieen SET volgorde=? WHERE id=?",
                                 (rij["volgorde"], buur["id"]))
                    conn.commit()
        elif actie == "actief":
            cat_id = request.form.get("id", type=int)
            conn.execute("UPDATE categorieen SET actief = 1 - actief WHERE id=?", (cat_id,))
            conn.commit()
        elif actie == "verwijderen":
            cat_id = request.form.get("id", type=int)
            gebruikt = conn.execute(
                "SELECT COUNT(*) n FROM transacties WHERE categorie_id=? OR subcategorie_id=?"
                " OR subsub_id=?", (cat_id, cat_id, cat_id)
            ).fetchone()["n"]
            if gebruikt:
                flash(f"Deze categorie wordt door {gebruikt} transacties gebruikt. "
                      "Zet ze op niet-actief of wijs de transacties eerst opnieuw toe.", "fout")
            else:
                conn.execute("DELETE FROM categorieen WHERE id=?", (cat_id,))
                conn.commit()
                flash("Categorie verwijderd.", "goed")
        return redirect(url_for("instellingen.categorieen"))

    wortels_uit = boom(conn, crypto, "uit")
    wortels_in = boom(conn, crypto, "in")
    return render_template(
        "instellingen_categorieen.html",
        wortels_uit=wortels_uit, wortels_in=wortels_in,
        keuzes=keuzelijst(boom(conn, crypto)),
    )


# --------------------------------------------------------------------------
# Regels

VELDNAMEN = {
    "tegenpartij_naam": "Naam tegenpartij",
    "tegenpartij_rekening": "Rekening tegenpartij",
    "mededeling": "Mededeling",
    "beschrijving": "Beschrijving",
    "sleutel": "Gecombineerde sleutel",
    "alles": "Alle tekstvelden samen",
}

SORTEERSLEUTELS = {
    "prioriteit": lambda r: (r["prioriteit"], r["id"]),
    "naam": lambda r: (normalize(r["naam"]), r["prioriteit"]),
    "voorwaarde": lambda r: (r["veld"], normalize(r["waarde"])),
    # Regels zonder ondergrens vooraan, daarna oplopend.
    "bedrag": lambda r: (r["bedrag_min"] is None and r["bedrag_max"] is None,
                         r["bedrag_min"] if r["bedrag_min"] is not None else -1e18,
                         r["bedrag_max"] if r["bedrag_max"] is not None else 1e18),
    "indeling": lambda r: (normalize(r["pad"]), r["prioriteit"]),
    "actief": lambda r: (not r["actief"], r["prioriteit"]),
    "treffers": lambda r: (-r["treffers"], r["prioriteit"]),
}


def _regelvelden(form, crypto):
    """De velden van het formulier, klaar om weg te schrijven.

    Geeft None terug wanneer er geen waarde is ingevuld; zonder waarde kan een
    regel nergens op passen.
    """
    waarde = form.get("waarde", "").strip()
    if not waarde:
        return None
    handelaar = form.get("handelaar", "").strip()
    land = form.get("land", "").strip()
    return {
        "naam_enc": crypto.enc(form.get("naam", "").strip() or waarde),
        "prioriteit": form.get("prioriteit", 100, type=int),
        "veld": form.get("veld", "tegenpartij_naam"),
        "operator": form.get("operator", "bevat"),
        "waarde_enc": crypto.enc(waarde),
        "waarde_idx": crypto.blind(normalize(waarde)),
        "bedrag_min": form.get("bedrag_min", type=float),
        "bedrag_max": form.get("bedrag_max", type=float),
        "richting": form.get("richting") or None,
        "categorie_id": form.get("categorie_id", type=int),
        "subcategorie_id": form.get("subcategorie_id", type=int),
        "subsub_id": form.get("subsub_id", type=int),
        "handelaar_enc": crypto.enc(handelaar) if handelaar else None,
        "land_enc": crypto.enc(land) if land else None,
    }


def _regelfilters(args):
    return {
        "q": args.get("q", "").strip(),
        "categorie": args.get("categorie", type=int),
        "veld": args.get("veld_f", ""),
        "actief": args.get("actief_f", ""),
        "bedrag": args.get("bedrag_f", type=float),
        "sorteer": args.get("sorteer", "prioriteit"),
        "omgekeerd": args.get("omgekeerd") == "1",
    }


def _past_op_filter(rij, f) -> bool:
    if f["q"]:
        naald = normalize(f["q"])
        hooi = normalize(" ".join([rij["naam"], rij["waarde"], rij["pad"],
                                   rij["handelaar"]]))
        if naald not in hooi:
            return False
    if f["categorie"] and f["categorie"] not in rij["cat_ids"]:
        return False
    if f["veld"] and rij["veld"] != f["veld"]:
        return False
    if f["actief"] == "ja" and not rij["actief"]:
        return False
    if f["actief"] == "nee" and rij["actief"]:
        return False
    if f["bedrag"] is not None:
        # Welke regels zou dit bedrag halen? Ondergrens telt mee, bovengrens niet.
        bedrag = abs(f["bedrag"])
        if rij["bedrag_min"] is not None and bedrag < rij["bedrag_min"]:
            return False
        if rij["bedrag_max"] is not None and bedrag >= rij["bedrag_max"]:
            return False
    return True


@bp.route("/regels", methods=["GET", "POST"])
@login_vereist
def regels():
    conn = get_db()
    crypto = g.crypto

    if request.method == "POST":
        actie = request.form.get("actie")
        bestemming = request.form.get("terug") or url_for("instellingen.regels")

        if actie == "toevoegen":
            velden = _regelvelden(request.form, crypto)
            if velden is None:
                flash("Geef aan waarop de regel moet passen.", "fout")
            else:
                kolommen = list(velden) + ["aangemaakt_op"]
                conn.execute(
                    f"INSERT INTO regels ({', '.join(kolommen)})"
                    f" VALUES ({', '.join('?' * len(kolommen))})",
                    tuple(velden.values()) + (now_iso(),),
                )
                conn.commit()
                flash("Regel toegevoegd.", "goed")

        elif actie == "bewerken":
            regel_id = request.form.get("id", type=int)
            velden = _regelvelden(request.form, crypto)
            if velden is None:
                flash("Geef aan waarop de regel moet passen.", "fout")
                return redirect(url_for("instellingen.regel_bewerken", regel_id=regel_id))
            # Dezelfde weg als verwijderen: eerst opzoeken wat eraan hing,
            # zolang de oude definitie nog geldt.
            hingen = hangende_transacties(conn, crypto, regel_id)
            conn.execute(
                f"UPDATE regels SET {', '.join(k + ' = ?' for k in velden)} WHERE id = ?",
                tuple(velden.values()) + (regel_id,),
            )
            uit = herbekijk(conn, crypto, hingen, toelichting=BEWERKT_TOELICHTING)
            uit.erbij = pas_toe(conn, crypto, regel_id)
            conn.commit()
            log(conn, crypto, g.gebruiker, "regel bewerkt", f"regel={regel_id}")
            flash("Regel aangepast. " + verslag(uit), "goed")

        elif actie == "verwijderen":
            regel_id = request.form.get("id", type=int)
            hingen = hangende_transacties(conn, crypto, regel_id)
            conn.execute("DELETE FROM regels WHERE id=?", (regel_id,))
            uit = herbekijk(conn, crypto, hingen, toelichting=WIS_TOELICHTING)
            conn.commit()
            flash("Regel verwijderd. " + verslag(uit), "goed")

        elif actie == "actief":
            regel_id = request.form.get("id", type=int)
            rij = conn.execute("SELECT actief FROM regels WHERE id=?",
                               (regel_id,)).fetchone()
            if rij is None:
                flash("Die regel bestaat niet meer.", "fout")
                return redirect(bestemming)
            if rij["actief"]:
                # Uitzetten volgt exact dezelfde weg als verwijderen.
                hingen = hangende_transacties(conn, crypto, regel_id)
                conn.execute("UPDATE regels SET actief = 0 WHERE id=?", (regel_id,))
                uit = herbekijk(conn, crypto, hingen, toelichting=UIT_TOELICHTING)
                conn.commit()
                flash("Regel uitgezet. " + verslag(uit), "goed")
            else:
                conn.execute("UPDATE regels SET actief = 1 WHERE id=?", (regel_id,))
                uit = Uitkomst(erbij=pas_toe(conn, crypto, regel_id))
                conn.commit()
                flash("Regel weer aangezet. " + verslag(uit), "goed")

        elif actie == "alles":
            uit = herbekijk_alles(conn, crypto)
            conn.commit()
            log(conn, crypto, g.gebruiker, "regels opnieuw toegepast",
                f"gewist={uit.gewist} anders={uit.overgenomen} erbij={uit.erbij}")
            flash("Alle regels opnieuw toegepast. " + verslag(uit), "goed")

        return redirect(bestemming)

    filters = _regelfilters(request.args)
    rijen = _regelrijen(conn, crypto)
    getoond = [r for r in rijen if _past_op_filter(r, filters)]
    sleutel = SORTEERSLEUTELS.get(filters["sorteer"], SORTEERSLEUTELS["prioriteit"])
    getoond.sort(key=sleutel, reverse=filters["omgekeerd"])

    return render_template(
        "instellingen_regels.html", rijen=getoond, totaal=len(rijen),
        filters=filters, veldnamen=VELDNAMEN,
        hoofdcategorieen=[k for k in keuzelijst(boom(conn, crypto))
                          if k["niveau"] == 0],
        keuzes=keuzelijst(boom(conn, crypto, alleen_actief=True)),
    )


def _regelrijen(conn, crypto) -> list[dict]:
    platte = laad_alles(conn, crypto)

    def pad(*ids):
        namen = [platte[i].naam for i in ids if i and i in platte]
        return " › ".join(namen) if namen else "—"

    rijen = []
    for r in conn.execute("SELECT * FROM regels ORDER BY prioriteit, id"):
        rijen.append({
            "id": r["id"], "naam": crypto.dec(r["naam_enc"]) or "",
            "prioriteit": r["prioriteit"], "veld": r["veld"], "operator": r["operator"],
            "waarde": crypto.dec(r["waarde_enc"]) or "",
            "bedrag_min": r["bedrag_min"], "bedrag_max": r["bedrag_max"],
            "richting": r["richting"], "actief": bool(r["actief"]),
            "pad": pad(r["categorie_id"], r["subcategorie_id"], r["subsub_id"]),
            "cat_ids": {i for i in (r["categorie_id"], r["subcategorie_id"],
                                    r["subsub_id"]) if i},
            "categorie_id": r["categorie_id"], "subcategorie_id": r["subcategorie_id"],
            "subsub_id": r["subsub_id"],
            "handelaar": crypto.dec(r["handelaar_enc"]) or "",
            "land": crypto.dec(r["land_enc"]) or "",
            "treffers": r["treffers"], "herkomst": r["herkomst"],
        })
    return rijen


@bp.route("/regels/<int:regel_id>")
@login_vereist
def regel_bewerken(regel_id: int):
    conn = get_db()
    crypto = g.crypto
    regel = next((r for r in _regelrijen(conn, crypto) if r["id"] == regel_id), None)
    if regel is None:
        flash("Die regel bestaat niet meer.", "fout")
        return redirect(url_for("instellingen.regels"))
    return render_template(
        "instellingen_regel.html", regel=regel, veldnamen=VELDNAMEN,
        keuzes=keuzelijst(boom(conn, crypto, alleen_actief=True)),
    )


# --------------------------------------------------------------------------
# AI en overige instellingen
# --------------------------------------------------------------------------

@bp.route("/model", methods=["GET", "POST"])
@login_vereist
def model():
    conn = get_db()
    boodschap = None

    if request.method == "POST":
        if request.form.get("actie") == "testen":
            gelukt, boodschap = test_verbinding(conn)
            flash(boodschap, "goed" if gelukt else "fout")
            return redirect(url_for("instellingen.model"))
        for sleutel in ("ai_basis_url", "ai_model", "ai_zoek_url",
                        "fuzzy_auto_drempel", "fuzzy_suggestie_drempel"):
            if sleutel in request.form:
                zet_instelling(conn, sleutel, request.form[sleutel].strip())
        for schakelaar in ("ai_actief", "ai_zoeken_actief", "leer_van_bevestiging"):
            zet_instelling(conn, schakelaar, "1" if request.form.get(schakelaar) else "0")
        conn.commit()
        flash("Instellingen opgeslagen.", "goed")
        return redirect(url_for("instellingen.model"))

    waarden = {
        sleutel: instelling(conn, sleutel)
        for sleutel in ("ai_actief", "ai_basis_url", "ai_model", "ai_zoeken_actief",
                        "ai_zoek_url", "fuzzy_auto_drempel", "fuzzy_suggestie_drempel",
                        "leer_van_bevestiging")
    }
    return render_template("instellingen_model.html", waarden=waarden, boodschap=boodschap)


# --------------------------------------------------------------------------
# Gebruikers
# --------------------------------------------------------------------------

@bp.route("/gebruikers", methods=["GET", "POST"])
@beheerder_vereist
def gebruikers():
    conn = get_db()

    if request.method == "POST":
        actie = request.form.get("actie")
        if actie == "toevoegen":
            naam = request.form.get("gebruikersnaam", "").strip()
            wachtwoord = request.form.get("wachtwoord", "")
            if len(naam) < 3:
                flash("Kies een gebruikersnaam van minstens 3 tekens.", "fout")
            elif len(wachtwoord) < 10:
                flash("Het wachtwoord moet minstens 10 tekens lang zijn.", "fout")
            else:
                try:
                    maak_gebruiker(naam, wachtwoord, g.sessie["dek"],
                                   is_beheerder=request.form.get("beheerder") == "1")
                    flash(f"Gebruiker {naam} toegevoegd.", "goed")
                except Exception:  # noqa: BLE001
                    flash("Die gebruikersnaam bestaat al.", "fout")
        elif actie == "wachtwoord":
            wachtwoord = request.form.get("wachtwoord", "")
            if len(wachtwoord) < 10:
                flash("Het wachtwoord moet minstens 10 tekens lang zijn.", "fout")
            else:
                wijzig_wachtwoord(request.form.get("id", type=int), wachtwoord,
                                  g.sessie["dek"])
                flash("Wachtwoord aangepast.", "goed")
        elif actie == "actief":
            los = connect()
            try:
                los.execute("UPDATE gebruikers SET actief = 1 - actief WHERE id=? AND id<>?",
                            (request.form.get("id", type=int), g.sessie["id"]))
                los.commit()
            finally:
                los.close()
        return redirect(url_for("instellingen.gebruikers"))

    rijen = [
        {"id": r["id"], "naam": r["gebruikersnaam"], "beheerder": bool(r["is_beheerder"]),
         "actief": bool(r["actief"]), "laatste_login": r["laatste_login"]}
        for r in connect().execute(
            "SELECT * FROM gebruikers ORDER BY id").fetchall()
    ]
    return render_template("instellingen_gebruikers.html", rijen=rijen,
                           eigen_id=g.sessie["id"])


@bp.route("/logboek")
@beheerder_vereist
def logboek():
    conn = get_db()
    crypto = g.crypto
    rijen = [
        {"tijdstip": r["tijdstip"], "gebruiker": r["gebruiker"], "actie": r["actie"],
         "detail": crypto.dec(r["detail_enc"]) or ""}
        for r in conn.execute("SELECT * FROM logboek ORDER BY id DESC LIMIT 200")
    ]
    return render_template("instellingen_logboek.html", rijen=rijen)


# --------------------------------------------------------------------------
# Herstel en e-mail
# --------------------------------------------------------------------------

@bp.route("/herstel", methods=["GET", "POST"])
@login_vereist
def herstel():
    conn = get_db()

    if request.method == "POST":
        actie = request.form.get("actie")

        if actie == "mailinstellingen":
            for sleutel in ("smtp_server", "smtp_poort", "smtp_beveiliging",
                            "smtp_gebruiker", "smtp_afzender"):
                lokaal.schrijf(conn, sleutel, request.form.get(sleutel, "").strip())
            # Een leeg wachtwoordveld laat het bestaande wachtwoord staan.
            nieuw = request.form.get("smtp_wachtwoord", "")
            if nieuw:
                lokaal.schrijf(conn, "smtp_wachtwoord", nieuw)
            lokaal.schrijf(conn, "smtp_actief",
                           "1" if request.form.get("smtp_actief") else "0")
            conn.commit()
            flash("Mailinstellingen opgeslagen.", "goed")

        elif actie == "adres":
            adres = request.form.get("email", "").strip()
            zet_herstelmail(g.sessie["id"], adres)
            log(conn, g.crypto, g.gebruiker, "herstelmail_gewijzigd")
            conn.commit()
            flash("E-mailadres voor herstel opgeslagen." if adres
                  else "E-mailadres verwijderd.", "goed")

        elif actie == "test":
            adres = request.form.get("email", "").strip() or herstelstatus(
                g.sessie["id"])["email"]
            if not adres:
                flash("Vul eerst een e-mailadres in.", "fout")
            else:
                try:
                    mail.verstuur_testbericht(conn, adres)
                    flash(f"Testbericht verstuurd naar {adres}. "
                          "Kijk ook in je map met ongewenste post.", "goed")
                except mail.MailFout as exc:
                    flash(str(exc), "fout")

        return redirect(url_for("instellingen.herstel"))

    return render_template(
        "instellingen_herstel.html",
        status=herstelstatus(g.sessie["id"]),
        mailwaarden=mail.instellingen(conn),
        kan_mailen=mail.actief(conn),
    )
