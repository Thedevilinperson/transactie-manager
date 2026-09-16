"""Bulkinvoer van bankafschriften in drie stappen: uploaden, indeling
nakijken, importeren."""

from __future__ import annotations

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
        fouten: list[str] = []
        aangeraakt: set[int] = set()
        taak.fase = "Transacties verwerken"

        for nummer, rij in enumerate(rijen, start=2):
            if (nummer - 2) % 25 == 0:
                taak.vorder(nummer - 2)

            velden = rij_naar_velden(rij, kop, inst["mapping"], inst["decimaal"])
            if velden["boekdatum"] is None or velden["bedrag"] is None:
                overgeslagen += 1
                if len(fouten) < 15:
                    fouten.append(f"Rij {nummer}: datum of bedrag ontbreekt of is "
                                  "onleesbaar.")
                continue

            rekening_id = inst["rekening_id"]
            if velden["eigen_rekening"]:
                sleutel = crypto.blind(velden["eigen_rekening"], iban=True)
                rekening_id = inst["per_iban"].get(sleutel, rekening_id)

            bedrag = Decimal(velden["bedrag"])
            tegenpartij_rek = (normalize_iban(velden["tegenpartij_rekening"])
                               or velden["tegenpartij_rekening"])

            bestaand = bestaande_id(
                conn, crypto, rekening_id=rekening_id, boekdatum=velden["boekdatum"],
                bedrag=bedrag, referentie=velden["referentie"],
                tegenpartij_rekening=tegenpartij_rek, mededeling=velden["mededeling"],
                tegenpartij_naam=velden["tegenpartij_naam"], gebruikt=aangeraakt,
            )

            if bestaand is not None:
                aangeraakt.add(bestaand)
                if inst["aanvullen"]:
                    velden["tegenpartij_rekening"] = tegenpartij_rek
                    if vul_aan(conn, crypto, bestaand, velden):
                        aangevuld += 1
                    else:
                        ongewijzigd += 1
                else:
                    ongewijzigd += 1
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
                batch_id=batch,
                ruwe_data=json.dumps(velden["ruw"], ensure_ascii=False),
            )
            if tx_id is None:
                ongewijzigd += 1
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
                "totaal": len(rijen), "fouten": fouten}
    finally:
        conn.close()


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
