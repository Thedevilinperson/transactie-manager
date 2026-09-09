"""Bewaren en opvragen van transacties, met versleuteling van de velden."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .categorizer.engine import TransactieKenmerken, Voorstel
from .database import now_iso


@dataclass
class Transactie:
    id: int
    rekening_id: int
    boekdatum: str
    valutadatum: str | None
    beschrijving: str
    referentie: str
    richting: str
    bedrag: Decimal
    munt: str
    tegenpartij_naam: str
    tegenpartij_rekening: str
    begunstigde: str
    mededeling: str
    handelaar: str
    land: str
    categorie_id: int | None
    subcategorie_id: int | None
    subsub_id: int | None
    zekerheid: float
    methode: str
    status: str
    toelichting: str
    is_afrekening: bool = False
    ouder_tx_id: int | None = None
    bron: str = "bank"

    @property
    def kenmerken(self) -> TransactieKenmerken:
        return TransactieKenmerken(
            beschrijving=self.beschrijving,
            tegenpartij_naam=self.tegenpartij_naam,
            tegenpartij_rekening=self.tegenpartij_rekening,
            mededeling=self.mededeling,
            begunstigde=self.begunstigde,
            bedrag=self.bedrag,
            richting=self.richting,
        )


def rij_naar_object(row, crypto) -> Transactie:
    return Transactie(
        id=row["id"],
        rekening_id=row["rekening_id"],
        boekdatum=row["boekdatum"],
        valutadatum=row["valutadatum"],
        beschrijving=crypto.dec(row["beschrijving_enc"]) or "",
        referentie=crypto.dec(row["referentie_enc"]) or "",
        richting=row["richting"],
        bedrag=crypto.dec_amount(row["bedrag_enc"]),
        munt=row["munt"],
        tegenpartij_naam=crypto.dec(row["tegenpartij_naam_enc"]) or "",
        tegenpartij_rekening=crypto.dec(row["tegenpartij_rek_enc"]) or "",
        begunstigde=crypto.dec(row["begunstigde_enc"]) or "",
        mededeling=crypto.dec(row["mededeling_enc"]) or "",
        handelaar=crypto.dec(row["handelaar_enc"]) or "",
        land=crypto.dec(row["land_enc"]) or "",
        categorie_id=row["categorie_id"],
        subcategorie_id=row["subcategorie_id"],
        subsub_id=row["subsub_id"],
        zekerheid=row["zekerheid"],
        methode=row["methode"],
        status=row["status"],
        toelichting=crypto.dec(row["toelichting_enc"]) or "",
        is_afrekening=bool(row["is_afrekening"]),
        ouder_tx_id=row["ouder_tx_id"],
        bron=row["bron"],
    )


def vingerafdruk(crypto, rekening_id: int, boekdatum, bedrag: Decimal,
                 tegenpartij_rekening: str, mededeling: str, tegenpartij_naam: str) -> str:
    return crypto.fingerprint(
        str(rekening_id), str(boekdatum), f"{bedrag:.2f}",
        tegenpartij_rekening, mededeling, tegenpartij_naam,
    )


def bewaar(conn, crypto, *, rekening_id: int, boekdatum: date | str, bedrag: Decimal,
           valutadatum=None, munt: str = "EUR", tegenpartij_naam: str = "",
           tegenpartij_rekening: str = "", begunstigde: str = "", mededeling: str = "",
           voorstel: Voorstel | None = None, batch_id: int | None = None,
           ruwe_data: str | None = None, handelaar: str = "", land: str = "",
           beschrijving: str = "", referentie: str = "", verrichtingsdatum=None,
           is_afrekening: bool = False, ouder_tx_id: int | None = None,
           bron: str = "bank") -> int | None:
    """Voegt een transactie toe. Geeft None terug als ze al bestaat."""
    bedrag = Decimal(str(bedrag))
    richting = "in" if bedrag >= 0 else "uit"
    datum = boekdatum.isoformat() if isinstance(boekdatum, date) else str(boekdatum)
    vd = valutadatum.isoformat() if isinstance(valutadatum, date) else (valutadatum or None)

    vrd = (verrichtingsdatum.isoformat() if isinstance(verrichtingsdatum, date)
           else (verrichtingsdatum or None))

    # De bankreferentie is uniek per verrichting; die krijgt voorrang bij het
    # ontdubbelen. Ontbreekt ze, dan vallen we terug op de inhoud van de rij.
    if referentie:
        afdruk = crypto.fingerprint("ref", str(rekening_id), referentie)
    else:
        afdruk = vingerafdruk(crypto, rekening_id, datum, bedrag,
                              tegenpartij_rekening, mededeling, tegenpartij_naam)
    if conn.execute("SELECT 1 FROM transacties WHERE vingerafdruk = ?", (afdruk,)).fetchone():
        return None

    voorstel = voorstel or Voorstel()
    handelaar = handelaar or (voorstel.handelaar or "")
    land = land or (voorstel.land or "")
    tijdstip = now_iso()

    cur = conn.execute(
        "INSERT INTO transacties (rekening_id, boekdatum, valutadatum, verrichtingsdatum,"
        " referentie_enc, beschrijving_enc, beschrijving_idx, sleutel_idx, richting,"
        " bedrag_enc, munt, tegenpartij_naam_enc, tegenpartij_naam_idx, tegenpartij_rek_enc,"
        " tegenpartij_rek_idx, begunstigde_enc, mededeling_enc, handelaar_enc, handelaar_idx,"
        " land_enc, categorie_id, subcategorie_id, subsub_id, zekerheid, methode, status,"
        " toelichting_enc, vingerafdruk, batch_id, ruwe_data_enc, is_afrekening, ouder_tx_id,"
        " bron, aangemaakt_op, gewijzigd_op)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            rekening_id, datum, vd, vrd,
            crypto.enc(referentie) if referentie else None,
            crypto.enc(beschrijving) if beschrijving else None,
            crypto.blind(beschrijving) if beschrijving else None,
            crypto.blind(f"{beschrijving}-{tegenpartij_naam}") if beschrijving else None,
            richting, crypto.enc_amount(bedrag), munt,
            crypto.enc(tegenpartij_naam) if tegenpartij_naam else None,
            crypto.blind(tegenpartij_naam),
            crypto.enc(tegenpartij_rekening) if tegenpartij_rekening else None,
            crypto.blind(tegenpartij_rekening, iban=True),
            crypto.enc(begunstigde) if begunstigde else None,
            crypto.enc(mededeling) if mededeling else None,
            crypto.enc(handelaar) if handelaar else None,
            crypto.blind(handelaar) if handelaar else None,
            crypto.enc(land) if land else None,
            voorstel.categorie_id, voorstel.subcategorie_id, voorstel.subsub_id,
            voorstel.zekerheid, voorstel.methode,
            voorstel.status if voorstel.gevonden else "niet_toegewezen",
            crypto.enc(voorstel.toelichting) if voorstel.toelichting else None,
            afdruk, batch_id,
            crypto.enc(ruwe_data) if ruwe_data else None,
            1 if is_afrekening else 0, ouder_tx_id, bron,
            tijdstip, tijdstip,
        ),
    )
    return cur.lastrowid


def werk_bij(conn, crypto, tx_id: int, **velden) -> None:
    """Past velden aan. Onbekende sleutels worden genegeerd."""
    kolommen = {
        "categorie_id": ("categorie_id", None),
        "subcategorie_id": ("subcategorie_id", None),
        "subsub_id": ("subsub_id", None),
        "zekerheid": ("zekerheid", None),
        "methode": ("methode", None),
        "status": ("status", None),
        "handelaar": ("handelaar_enc", "enc"),
        "land": ("land_enc", "enc"),
        "mededeling": ("mededeling_enc", "enc"),
        "tegenpartij_naam": ("tegenpartij_naam_enc", "enc"),
        "begunstigde": ("begunstigde_enc", "enc"),
        "toelichting": ("toelichting_enc", "enc"),
        "boekdatum": ("boekdatum", None),
        "rekening_id": ("rekening_id", None),
    }
    stukken, waarden = [], []
    for sleutel, waarde in velden.items():
        if sleutel not in kolommen:
            continue
        kolom, behandeling = kolommen[sleutel]
        stukken.append(f"{kolom} = ?")
        waarden.append(crypto.enc(waarde) if behandeling == "enc" and waarde else
                       (None if behandeling == "enc" else waarde))
        if sleutel == "handelaar":
            stukken.append("handelaar_idx = ?")
            waarden.append(crypto.blind(waarde) if waarde else None)
        if sleutel == "tegenpartij_naam":
            stukken.append("tegenpartij_naam_idx = ?")
            waarden.append(crypto.blind(waarde) if waarde else None)

    if "bedrag" in velden and velden["bedrag"] is not None:
        bedrag = Decimal(str(velden["bedrag"]))
        stukken += ["bedrag_enc = ?", "richting = ?"]
        waarden += [crypto.enc_amount(bedrag), "in" if bedrag >= 0 else "uit"]

    if not stukken:
        return
    stukken.append("gewijzigd_op = ?")
    waarden.append(now_iso())
    waarden.append(tx_id)
    conn.execute(f"UPDATE transacties SET {', '.join(stukken)} WHERE id = ?", waarden)


def haal(conn, crypto, tx_id: int) -> Transactie | None:
    row = conn.execute("SELECT * FROM transacties WHERE id = ?", (tx_id,)).fetchone()
    return rij_naar_object(row, crypto) if row else None


def zoek(conn, crypto, *, status=None, rekening_id=None, categorie_ids=None,
         van=None, tot=None, richting=None, zoekterm="", limiet=200, offset=0):
    """Haalt transacties op. Zoeken op tekst gebeurt na ontsleuteling."""
    sql = "SELECT * FROM transacties WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if rekening_id:
        sql += " AND rekening_id = ?"
        params.append(rekening_id)
    if richting in ("in", "uit"):
        sql += " AND richting = ?"
        params.append(richting)
    if van:
        sql += " AND boekdatum >= ?"
        params.append(van)
    if tot:
        sql += " AND boekdatum <= ?"
        params.append(tot)
    if categorie_ids:
        plaatsen = ",".join("?" * len(categorie_ids))
        sql += (f" AND (categorie_id IN ({plaatsen}) OR subcategorie_id IN ({plaatsen})"
                f" OR subsub_id IN ({plaatsen}))")
        params += list(categorie_ids) * 3
    sql += " ORDER BY boekdatum DESC, id DESC"

    if zoekterm:
        # Tekst staat versleuteld: alles ophalen en in het geheugen filteren.
        from .crypto import normalize
        naald = normalize(zoekterm)
        gevonden = []
        for row in conn.execute(sql, params):
            tx = rij_naar_object(row, crypto)
            hooiberg = normalize(" ".join([
                tx.tegenpartij_naam, tx.mededeling, tx.begunstigde,
                tx.handelaar, tx.tegenpartij_rekening,
            ]))
            if naald in hooiberg:
                gevonden.append(tx)
            if len(gevonden) >= offset + limiet:
                break
        return gevonden[offset:offset + limiet]

    sql += " LIMIT ? OFFSET ?"
    params += [limiet, offset]
    return [rij_naar_object(r, crypto) for r in conn.execute(sql, params)]


def tel(conn, status: str | None = None) -> int:
    sql = "SELECT COUNT(*) AS n FROM transacties"
    params: list = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    return conn.execute(sql, params).fetchone()["n"]
