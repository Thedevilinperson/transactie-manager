"""Instellingen: rekeningen, categorieën, regels, AI-model en gebruikers."""

from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..auth import beheerder_vereist, login_vereist, maak_gebruiker, wijzig_wachtwoord
from ..categories import boom, keuzelijst, laad_alles
from ..categorizer.ai import test_verbinding
from ..crypto import normalize, normalize_iban
from ..database import connect, get_db, instelling, log, now_iso, zet_instelling

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
# --------------------------------------------------------------------------

@bp.route("/regels", methods=["GET", "POST"])
@login_vereist
def regels():
    conn = get_db()
    crypto = g.crypto

    if request.method == "POST":
        actie = request.form.get("actie")
        if actie == "toevoegen":
            waarde = request.form.get("waarde", "").strip()
            if not waarde:
                flash("Geef aan waarop de regel moet passen.", "fout")
            else:
                conn.execute(
                    "INSERT INTO regels (naam_enc, prioriteit, veld, operator, waarde_enc,"
                    " waarde_idx, bedrag_min, bedrag_max, richting, categorie_id,"
                    " subcategorie_id, subsub_id, handelaar_enc, land_enc, aangemaakt_op)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        crypto.enc(request.form.get("naam", "").strip() or waarde),
                        request.form.get("prioriteit", 100, type=int),
                        request.form.get("veld", "tegenpartij_naam"),
                        request.form.get("operator", "bevat"),
                        crypto.enc(waarde), crypto.blind(normalize(waarde)),
                        request.form.get("bedrag_min", type=float),
                        request.form.get("bedrag_max", type=float),
                        request.form.get("richting") or None,
                        request.form.get("categorie_id", type=int),
                        request.form.get("subcategorie_id", type=int),
                        request.form.get("subsub_id", type=int),
                        crypto.enc(request.form.get("handelaar", "").strip()) or None,
                        crypto.enc(request.form.get("land", "").strip()) or None,
                        now_iso(),
                    ),
                )
                conn.commit()
                flash("Regel toegevoegd.", "goed")
        elif actie == "verwijderen":
            conn.execute("DELETE FROM regels WHERE id=?", (request.form.get("id", type=int),))
            conn.commit()
            flash("Regel verwijderd.", "goed")
        elif actie == "actief":
            conn.execute("UPDATE regels SET actief = 1 - actief WHERE id=?",
                         (request.form.get("id", type=int),))
            conn.commit()
        return redirect(url_for("instellingen.regels"))

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
            "handelaar": crypto.dec(r["handelaar_enc"]) or "",
        })
    return render_template(
        "instellingen_regels.html", rijen=rijen,
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
