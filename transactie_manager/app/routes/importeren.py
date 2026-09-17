"""Bulkinvoer van bankafschriften in drie stappen: uploaden, indeling
nakijken, importeren."""

from __future__ import annotations

import collections
import json
import secrets
from decimal import Decimal
from pathlib import Path

from flask import (Blueprint, flash, g, jsonify, redirect, render_template, request,
                   url_for)
from werkzeug.utils import secure_filename

from ..auth import login_vereist
from ..categories import zoek_of_maak
from ..categorizer.engine import Motor, TransactieKenmerken, Voorstel
from .. import taken
from ..config import UPLOAD_DIR
from ..crypto import normalize_iban
from ..database import connect, get_db, log, now_iso
from ..filters import vergeet_keuzes
from ..importers.tabel import (BESTANDSTYPES, INDELINGSVELDEN, PROFIELEN, VELDEN,
                               detecteer_mapping, lees_bestand, rij_naar_velden)
from ..transacties import bestaande_id, bewaar, vul_aan

bp = Blueprint("importeren", __name__, url_prefix="/importeren")

# Waarom een rij niet als nieuwe transactie in de databank belandde.
REDENEN = {
    "aangevuld": "Stond er al; velden aangevuld",
    "dubbel_databank": "Stond al in de databank",
    "dubbel_bestand": "Komt twee keer voor in dit bestand",
    "onleesbaar": "Datum of bedrag ontbreekt of is onleesbaar",
    "toegevoegd": "Alsnog toegevoegd",
}
MAX_BEWAARDE_REGELS = 3000

MAX_VOORBEELD = 12


def _rekeningen(conn, crypto):
    return [
        {"id": r["id"], "naam": crypto.dec(r["naam_enc"]),
         "iban": crypto.dec(r["iban_enc"]) or "", "iban_idx": r["iban_idx"]}
        for r in conn.execute("SELECT * FROM rekeningen WHERE actief=1 ORDER BY volgorde, id")
    ]


@bp.route("/", methods=["GET", "POST"])
@login_vereist
def start():
    conn = get_db()
    rekeningen = _rekeningen(conn, g.crypto)

    if request.method == "POST":
        bestand = request.files.get("bestand")
        if not bestand or not bestand.filename:
            flash("Kies eerst een bestand.", "fout")
            return redirect(url_for("importeren.start"))

        veilige_naam = secure_filename(bestand.filename)
        achtervoegsel = Path(veilige_naam).suffix.lower()
        if achtervoegsel not in BESTANDSTYPES:
            flash(f"Bestandstype {achtervoegsel or 'onbekend'} wordt niet ondersteund. "
                  "Gebruik .xlsx of .csv.", "fout")
            return redirect(url_for("importeren.start"))

        token = secrets.token_urlsafe(16)
        doel = UPLOAD_DIR / f"{token}{achtervoegsel}"
        bestand.save(doel)
        return redirect(url_for("importeren.voorbeeld", token=token,
                                naam=veilige_naam,
                                profiel=request.form.get("profiel", "automatisch")))

    return render_template("importeren.html", rekeningen=rekeningen, profielen=PROFIELEN)


def _bestandspad(token: str) -> Path | None:
    for pad in UPLOAD_DIR.glob(f"{token}.*"):
        return pad
    return None


@bp.route("/voorbeeld/<token>")
@login_vereist
def voorbeeld(token: str):
    pad = _bestandspad(token)
    if pad is None:
        flash("Het geüploade bestand is niet meer beschikbaar. Probeer opnieuw.", "fout")
        return redirect(url_for("importeren.start"))

    conn = get_db()
    profiel = request.args.get("profiel", "automatisch")
    kop, rijen = lees_bestand(pad)
    if not kop:
        flash("Er zijn geen kolommen gevonden in dit bestand.", "fout")
        return redirect(url_for("importeren.start"))

    mapping = detecteer_mapping(kop, profiel)
    voorbeeldrijen = []
    for rij in rijen[:MAX_VOORBEELD]:
        voorbeeldrijen.append(rij_naar_velden(rij, kop, mapping))

    ontbrekend = [
        label for veld, label, verplicht in VELDEN
        if verplicht and veld not in mapping and f"{veld}_debet" not in mapping
    ]
    heeft_indeling = "hoofdcategorie" in mapping

    return render_template(
        "importeren_voorbeeld.html",
        token=token, bestandsnaam=request.args.get("naam", pad.name),
        kop=kop, mapping=mapping, velden=VELDEN, profiel=profiel, profielen=PROFIELEN,
        voorbeeldrijen=voorbeeldrijen, aantal_rijen=len(rijen), ontbrekend=ontbrekend,
        heeft_indeling=heeft_indeling, indelingsvelden=INDELINGSVELDEN,
        rekeningen=_rekeningen(conn, g.crypto),
    )


@bp.route("/uitvoeren", methods=["POST"])
@login_vereist
def uitvoeren():
    pad = _bestandspad(request.form.get("token", ""))
    if pad is None:
        flash("Het geüploade bestand is niet meer beschikbaar.", "fout")
        return redirect(url_for("importeren.start"))

    conn = get_db()
    crypto = g.crypto
    rekeningen = _rekeningen(conn, crypto)
    if not rekeningen:
        flash("Voeg eerst een rekening toe bij Instellingen.", "fout")
        return redirect(url_for("instellingen.rekeningen"))

    mapping = {
        veld: request.form.get(f"map_{veld}", "")
        for veld, _, _ in VELDEN
        if request.form.get(f"map_{veld}")
    }
    for extra in ("bedrag_debet", "bedrag_credit"):
        if request.form.get(f"map_{extra}"):
            mapping[extra] = request.form[f"map_{extra}"]

    instellingen = {
        "mapping": mapping,
        "decimaal": request.form.get("decimaal", "auto"),
        "rekening_id": request.form.get("rekening_id", type=int) or rekeningen[0]["id"],
        "auto_toewijzen": request.form.get("auto_toewijzen", "1") == "1",
        "neem_indeling_over": (request.form.get("neem_indeling_over") == "1"
                               and "hoofdcategorie" in mapping),
        "aanvullen": request.form.get("aanvullen", "1") == "1",
        "bestandsnaam": request.form.get("bestandsnaam", pad.name),
        "profiel": request.form.get("profiel", "automatisch"),
        "per_iban": {r["iban_idx"]: r["id"] for r in rekeningen if r["iban_idx"]},
        "gebruiker": g.gebruiker,
    }

    token = pad.stem
    taken.start(token, f"Invoer van {instellingen['bestandsnaam']}",
                _verwerk, pad, crypto, instellingen)
    return redirect(url_for("importeren.bezig", token=token))


@bp.route("/bezig/<token>")
@login_vereist
def bezig(token: str):
    taak = taken.haal(token)
    if taak is None:
        flash("Die invoer is niet meer bekend.", "fout")
        return redirect(url_for("importeren.start"))
    return render_template("importeren_bezig.html", token=token, taak=taak)


@bp.route("/voortgang/<token>")
@login_vereist
def voortgang(token: str):
    taak = taken.haal(token)
    if taak is None:
        return jsonify({"fout": "onbekend"}), 404
    return jsonify(taak.naar_json())


def _verwerk(taak, pad: Path, crypto, inst: dict) -> dict:
    """Leest het bestand rij per rij in. Draait in een aparte draad, dus met een
    eigen verbinding naar de databank."""
    conn = connect()
    try:
        taak.fase = "Bestand lezen"
        kop, rijen = lees_bestand(pad)
        taak.totaal = len(rijen)

        taak.fase = "Regels en geschiedenis laden"
        motor = Motor(conn, crypto) if inst["auto_toewijzen"] else None
        cat_cache: dict = {}

        batch = conn.execute(
            "INSERT INTO import_batches (bestand_enc, profiel, aantal_rijen, gebruiker,"
            " tijdstip) VALUES (?,?,?,?,?)",
            (crypto.enc(inst["bestandsnaam"]), inst["profiel"], len(rijen),
             inst["gebruiker"], now_iso()),
        ).lastrowid

        nieuw = aangevuld = ongewijzigd = overgeslagen = uit_bestand = 0
        bewaarde_regels = 0
        fouten: list[str] = []
        gezien_referenties: dict = {}

        def noteer(rijnummer: int, reden: str, detail: str, rij_waarden,
                   tx_id: int | None = None):
            """Legt vast waarom een rij niet als nieuwe transactie is bewaard."""
            nonlocal bewaarde_regels
            if bewaarde_regels >= MAX_BEWAARDE_REGELS:
                return
            bewaarde_regels += 1
            conn.execute(
                "INSERT INTO import_regels (batch_id, rijnummer, reden, detail_enc,"
                " rij_enc, bestaande_tx_id) VALUES (?,?,?,?,?,?)",
                (batch, rijnummer, reden, crypto.enc(detail),
                 crypto.enc(json.dumps(rij_waarden, ensure_ascii=False)), tx_id),
            )
        aangeraakt: set[int] = set()
        # Telt hoe vaak dezelfde rij in dit bestand voorkomt. Drie identieke
        # betalingen op één dag zijn drie aankopen, geen drie keer dezelfde.
        herhaling: collections.Counter = collections.Counter()
        taak.fase = "Transacties verwerken"

        for nummer, rij in enumerate(rijen, start=2):
            if (nummer - 2) % 25 == 0:
                taak.vorder(nummer - 2)

            velden = rij_naar_velden(rij, kop, inst["mapping"], inst["decimaal"])
            ruw = velden.get("ruw", {})
            if velden["boekdatum"] is None or velden["bedrag"] is None:
                overgeslagen += 1
                ontbreekt = ("datum" if velden["boekdatum"] is None else "bedrag")
                noteer(nummer, "onleesbaar",
                       f"De {ontbreekt} kon niet gelezen worden.", ruw)
                if len(fouten) < 15:
                    fouten.append(f"Rij {nummer}: {ontbreekt} ontbreekt of is "
                                  "onleesbaar.")
                continue

            rekening_id = inst["rekening_id"]
            if velden["eigen_rekening"]:
                sleutel = crypto.blind(velden["eigen_rekening"], iban=True)
                rekening_id = inst["per_iban"].get(sleutel, rekening_id)

            bedrag = Decimal(velden["bedrag"])
            tegenpartij_rek = (normalize_iban(velden["tegenpartij_rekening"])
                               or velden["tegenpartij_rekening"])

            # Alleen nodig wanneer er geen referentie is; die is al uniek.
            volgnummer = 1
            if not velden["referentie"]:
                sleutel = (rekening_id, str(velden["boekdatum"]), str(bedrag),
                           tegenpartij_rek, velden["mededeling"],
                           velden["tegenpartij_naam"])
                herhaling[sleutel] += 1
                volgnummer = herhaling[sleutel]

            bestaand = bestaande_id(
                conn, crypto, rekening_id=rekening_id, boekdatum=velden["boekdatum"],
                bedrag=bedrag, referentie=velden["referentie"],
                tegenpartij_rekening=tegenpartij_rek, mededeling=velden["mededeling"],
                tegenpartij_naam=velden["tegenpartij_naam"], gebruikt=aangeraakt,
                volgnummer=volgnummer,
            )

            # Dezelfde bankreferentie twee keer in één bestand is geen dubbel
            # van de databank maar een dubbel binnen het bestand zelf.
            in_bestand = velden["referentie"] and velden["referentie"] in gezien_referenties
            if velden["referentie"]:
                gezien_referenties.setdefault(velden["referentie"], nummer)

            if bestaand is not None:
                aangeraakt.add(bestaand)
                if inst["aanvullen"]:
                    velden["tegenpartij_rekening"] = tegenpartij_rek
                    gewijzigd = vul_aan(conn, crypto, bestaand, velden)
                else:
                    gewijzigd = []
                if gewijzigd:
                    aangevuld += 1
                    noteer(nummer, "aangevuld",
                           "Aangevulde velden: " + ", ".join(gewijzigd), ruw, bestaand)
                else:
                    ongewijzigd += 1
                    if in_bestand:
                        noteer(nummer, "dubbel_bestand",
                               "Dezelfde bankreferentie staat ook op rij "
                               f"{gezien_referenties[velden['referentie']]}.",
                               ruw, bestaand)
                    else:
                        noteer(nummer, "dubbel_databank",
                               "Deze verrichting stond al in de databank.",
                               ruw, bestaand)
                continue

            voorstel = None
            if inst["neem_indeling_over"] and velden["hoofdcategorie"]:
                ids = zoek_of_maak(conn, crypto, velden["hoofdcategorie"],
                                   velden["subcategorie"], velden["subsubcategorie"],
                                   cache=cat_cache)
                if ids[0] is not None:
                    voorstel = Voorstel(
                        categorie_id=ids[0], subcategorie_id=ids[1], subsub_id=ids[2],
                        handelaar=velden["winkel"] or None,
                        land=velden["land"] or None,
                        zekerheid=1.0, methode="bestand", status="bevestigd",
                        toelichting="Indeling stond in het ingelezen bestand.",
                    )
                    uit_bestand += 1

            if voorstel is None and motor is not None:
                kenmerken = TransactieKenmerken(
                    beschrijving=velden["beschrijving"],
                    tegenpartij_naam=velden["tegenpartij_naam"],
                    tegenpartij_rekening=velden["tegenpartij_rekening"],
                    mededeling=velden["mededeling"],
                    begunstigde=velden["begunstigde"],
                    bedrag=bedrag,
                    richting="in" if bedrag >= 0 else "uit",
                )
                voorstel = motor.beoordeel(kenmerken)
                motor.onthoud(kenmerken, voorstel)

            tx_id = bewaar(
                conn, crypto, rekening_id=rekening_id, boekdatum=velden["boekdatum"],
                valutadatum=velden["valutadatum"], bedrag=bedrag, munt=velden["munt"],
                tegenpartij_naam=velden["tegenpartij_naam"],
                tegenpartij_rekening=tegenpartij_rek,
                begunstigde=velden["begunstigde"], mededeling=velden["mededeling"],
                beschrijving=velden["beschrijving"], referentie=velden["referentie"],
                verrichtingsdatum=velden["verrichtingsdatum"], voorstel=voorstel,
                batch_id=batch, volgnummer=volgnummer,
                ruwe_data=json.dumps(velden["ruw"], ensure_ascii=False),
            )
            if tx_id is None:
                ongewijzigd += 1
                noteer(nummer, "dubbel_databank",
                       "Een verrichting met dezelfde vingerafdruk stond al in de "
                       "databank.", ruw)
            else:
                nieuw += 1
                aangeraakt.add(tx_id)

        taak.vorder(len(rijen), "Afronden")
        conn.execute(
            "UPDATE import_batches SET aantal_nieuw=?, aantal_dubbel=? WHERE id=?",
            (nieuw, aangevuld + ongewijzigd, batch))
        log(conn, crypto, inst["gebruiker"], "import",
            f"nieuw={nieuw} aangevuld={aangevuld} ongewijzigd={ongewijzigd} "
            f"overgeslagen={overgeslagen}")
        conn.commit()
        vergeet_keuzes()

        try:
            pad.unlink()
        except OSError:
            pass

        return {"nieuw": nieuw, "aangevuld": aangevuld, "ongewijzigd": ongewijzigd,
                "overgeslagen": overgeslagen, "uit_bestand": uit_bestand,
                "totaal": len(rijen), "fouten": fouten, "batch": batch,
                "verklaard": nieuw + aangevuld + ongewijzigd + overgeslagen,
                "bewaarde_regels": bewaarde_regels,
                "afgekapt": bewaarde_regels >= MAX_BEWAARDE_REGELS}
    finally:
        conn.close()


@bp.route("/batch/<int:batch_id>/regels")
@login_vereist
def batchregels(batch_id: int):
    """De rijen die niet als nieuwe transactie zijn ingelezen, met de reden."""
    conn = get_db()
    crypto = g.crypto
    reden = request.args.get("reden", "")
    toon_afgehandeld = request.args.get("afgehandeld") == "1"

    sql = "SELECT * FROM import_regels WHERE batch_id = ?"
    params: list = [batch_id]
    if reden:
        sql += " AND reden = ?"
        params.append(reden)
    if not toon_afgehandeld:
        sql += " AND afgehandeld = 0"
    sql += " ORDER BY rijnummer LIMIT 500"

    rijen = []
    for r in conn.execute(sql, params):
        try:
            waarden = json.loads(crypto.dec(r["rij_enc"]) or "{}")
        except (ValueError, TypeError):
            waarden = {}
        rijen.append({
            "id": r["id"], "rijnummer": r["rijnummer"], "reden": r["reden"],
            "detail": crypto.dec(r["detail_enc"]) or "",
            "waarden": {k: v for k, v in waarden.items() if v},
            "bestaande_tx_id": r["bestaande_tx_id"],
            "afgehandeld": bool(r["afgehandeld"]),
        })

    tellingen = {
        r["reden"]: r["n"] for r in conn.execute(
            "SELECT reden, COUNT(*) n FROM import_regels WHERE batch_id = ?"
            " GROUP BY reden", (batch_id,))
    }
    batch = conn.execute("SELECT * FROM import_batches WHERE id = ?",
                         (batch_id,)).fetchone()
    return render_template(
        "importeren_regels.html", batch_id=batch_id, rijen=rijen,
        tellingen=tellingen, redenen=REDENEN, gekozen_reden=reden,
        toon_afgehandeld=toon_afgehandeld,
        bestandsnaam=crypto.dec(batch["bestand_enc"]) if batch else "—",
        aantal_rijen=batch["aantal_rijen"] if batch else 0,
    )


@bp.route("/regel/<int:regel_id>/toevoegen", methods=["POST"])
@login_vereist
def regel_toevoegen(regel_id: int):
    """Voegt een overgeslagen rij alsnog toe, op uitdrukkelijke vraag."""
    conn = get_db()
    crypto = g.crypto
    regel = conn.execute("SELECT * FROM import_regels WHERE id = ?",
                         (regel_id,)).fetchone()
    if regel is None:
        flash("Die rij is niet meer bekend.", "fout")
        return redirect(url_for("importeren.geschiedenis"))

    waarden = json.loads(crypto.dec(regel["rij_enc"]) or "{}")
    batch = conn.execute("SELECT * FROM import_batches WHERE id = ?",
                         (regel["batch_id"],)).fetchone()
    profiel = batch["profiel"] if batch else "automatisch"
    kop = list(waarden)
    mapping = detecteer_mapping(kop, profiel)
    velden = rij_naar_velden([waarden[k] for k in kop], kop, mapping)

    if velden["boekdatum"] is None or velden["bedrag"] is None:
        flash("Deze rij mist nog altijd een leesbare datum of een bedrag. "
              "Voeg ze met de hand toe via Nieuwe transactie.", "fout")
        return redirect(url_for("importeren.batchregels", batch_id=regel["batch_id"]))

    rekening = conn.execute(
        "SELECT id FROM rekeningen WHERE actief = 1 ORDER BY volgorde, id LIMIT 1"
    ).fetchone()
    bedrag = Decimal(velden["bedrag"])
    kenmerken = TransactieKenmerken(
        beschrijving=velden["beschrijving"], tegenpartij_naam=velden["tegenpartij_naam"],
        tegenpartij_rekening=velden["tegenpartij_rekening"],
        mededeling=velden["mededeling"], begunstigde=velden["begunstigde"],
        bedrag=bedrag, richting="in" if bedrag >= 0 else "uit",
    )
    tx_id = bewaar(
        conn, crypto, rekening_id=rekening["id"], boekdatum=velden["boekdatum"],
        valutadatum=velden["valutadatum"], bedrag=bedrag, munt=velden["munt"],
        tegenpartij_naam=velden["tegenpartij_naam"],
        tegenpartij_rekening=normalize_iban(velden["tegenpartij_rekening"])
        or velden["tegenpartij_rekening"],
        begunstigde=velden["begunstigde"], mededeling=velden["mededeling"],
        beschrijving=velden["beschrijving"], referentie=velden["referentie"],
        verrichtingsdatum=velden["verrichtingsdatum"],
        voorstel=Motor(conn, crypto).beoordeel(kenmerken),
        batch_id=regel["batch_id"],
        ruwe_data=json.dumps(waarden, ensure_ascii=False), forceer=True,
    )
    conn.execute("UPDATE import_regels SET afgehandeld = 1, reden = 'toegevoegd',"
                 " bestaande_tx_id = ? WHERE id = ?", (tx_id, regel_id))
    log(conn, crypto, g.gebruiker, "overgeslagen_rij_toegevoegd", f"regel={regel_id}")
    conn.commit()
    vergeet_keuzes()
    flash("De rij is alsnog toegevoegd.", "goed")
    return redirect(url_for("importeren.batchregels", batch_id=regel["batch_id"]))


@bp.route("/regel/<int:regel_id>/afhandelen", methods=["POST"])
@login_vereist
def regel_afhandelen(regel_id: int):
    conn = get_db()
    regel = conn.execute("SELECT batch_id FROM import_regels WHERE id = ?",
                         (regel_id,)).fetchone()
    conn.execute("UPDATE import_regels SET afgehandeld = 1 WHERE id = ?", (regel_id,))
    conn.commit()
    return redirect(url_for("importeren.batchregels",
                            batch_id=regel["batch_id"] if regel else 0))


@bp.route("/batch/<int:batch_id>/alles-afhandelen", methods=["POST"])
@login_vereist
def batch_afhandelen(batch_id: int):
    conn = get_db()
    reden = request.form.get("reden", "")
    sql = "UPDATE import_regels SET afgehandeld = 1 WHERE batch_id = ?"
    params: list = [batch_id]
    if reden:
        sql += " AND reden = ?"
        params.append(reden)
    aantal = conn.execute(sql, params).rowcount
    conn.commit()
    flash(f"{aantal} rijen als nagekeken gemarkeerd.", "goed")
    return redirect(url_for("importeren.batchregels", batch_id=batch_id))


@bp.route("/geschiedenis")
@login_vereist
def geschiedenis():
    conn = get_db()
    crypto = g.crypto
    rijen = [
        {
            "id": r["id"], "bestand": crypto.dec(r["bestand_enc"]) or "—",
            "profiel": r["profiel"], "aantal_rijen": r["aantal_rijen"],
            "nieuw": r["aantal_nieuw"], "dubbel": r["aantal_dubbel"],
            "gebruiker": r["gebruiker"], "tijdstip": r["tijdstip"],
        }
        for r in conn.execute("SELECT * FROM import_batches ORDER BY id DESC LIMIT 50")
    ]
    return render_template("importeren_geschiedenis.html", rijen=rijen)


@bp.route("/batch/<int:batch_id>/terugdraaien", methods=["POST"])
@login_vereist
def terugdraaien(batch_id: int):
    conn = get_db()
    aantal = conn.execute("DELETE FROM transacties WHERE batch_id = ?", (batch_id,)).rowcount
    conn.execute("DELETE FROM import_batches WHERE id = ?", (batch_id,))
    log(conn, g.crypto, g.gebruiker, "import_teruggedraaid", f"batch={batch_id} n={aantal}")
    conn.commit()
    flash(f"{aantal} transacties uit die invoer verwijderd.", "goed")
    return redirect(url_for("importeren.geschiedenis"))
