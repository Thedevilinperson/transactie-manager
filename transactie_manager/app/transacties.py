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


def _bedragsleutel(bedrag: Decimal) -> str:
    """Het bedrag als tekst voor een vingerafdruk, met het teken erin.

    De normalisatie achter `fingerprint` gooit leestekens weg, en daarmee ook
    het minteken. Een afschrijving van 5 646,24 en de tegenboeking van
    +5 646,24 kregen zo dezelfde vingerafdruk, waarna de tweede voor een dubbel
    werd aangezien en verdween. Het teken staat nu als woord in de sleutel.

    Negatieve bedragen houden bewust hun oude vorm. Anders zou de vingerafdruk
    van elke bestaande uitgave veranderen en zou een eerder ingelezen bestand
    bij een volgende invoer helemaal opnieuw toegevoegd worden.
    """
    return f"{bedrag:.2f}" if bedrag < 0 else f"plus {bedrag:.2f}"


def vingerafdruk(crypto, rekening_id: int, boekdatum, bedrag: Decimal,
                 tegenpartij_rekening: str, mededeling: str, tegenpartij_naam: str) -> str:
    return crypto.fingerprint(
        str(rekening_id), str(boekdatum), _bedragsleutel(Decimal(str(bedrag))),
        tegenpartij_rekening, mededeling, tegenpartij_naam,
    )


def _oude_vingerafdruk(crypto, rekening_id: int, boekdatum, bedrag: Decimal,
                       tegenpartij_rekening: str, mededeling: str,
                       tegenpartij_naam: str) -> str:
    """De vorm van vóór de tekencorrectie, om bestaande rijen terug te vinden."""
    return crypto.fingerprint(
        str(rekening_id), str(boekdatum), f"{bedrag:.2f}",
        tegenpartij_rekening, mededeling, tegenpartij_naam,
    )


def referentieafdruk(crypto, rekening_id: int, referentie: str, bedrag: Decimal) -> str:
    """Vingerafdruk op de bankreferentie.

    Sommige banken geven een boeking en haar tegenboeking dezelfde referentie.
    Daarom telt het teken van het bedrag mee. Ook hier houden negatieve bedragen
    hun oude vorm.
    """
    if Decimal(str(bedrag)) < 0:
        return crypto.fingerprint("ref", str(rekening_id), referentie)
    return crypto.fingerprint("ref", str(rekening_id), referentie, "plus")


def _zoek_op_afdruk(conn, crypto, afdruk: str, bedrag: Decimal | None = None):
    """Zoekt een rij op vingerafdruk. Met `bedrag` wordt ook nagegaan of het
    bedrag overeenkomt; dat is nodig bij de oude, tekenloze afdrukken, die voor
    een boeking en haar tegenboeking gelijk waren."""
    rij = conn.execute(
        "SELECT id, bedrag_enc FROM transacties WHERE vingerafdruk = ?", (afdruk,)
    ).fetchone()
    if rij is None:
        return None
    if bedrag is not None and crypto.dec_amount(rij["bedrag_enc"]) != Decimal(str(bedrag)):
        return None
    return rij["id"]


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
        afdruk = referentieafdruk(crypto, rekening_id, referentie, bedrag)
        oud = crypto.fingerprint("ref", str(rekening_id), referentie)
    else:
        afdruk = vingerafdruk(crypto, rekening_id, datum, bedrag,
                              tegenpartij_rekening, mededeling, tegenpartij_naam)
        oud = _oude_vingerafdruk(crypto, rekening_id, datum, bedrag,
                                 tegenpartij_rekening, mededeling, tegenpartij_naam)

    if _zoek_op_afdruk(conn, crypto, afdruk) is not None:
        return None
    # Rijen van vóór de tekencorrectie dragen nog de oude afdruk. Het bedrag moet
    # dan wel kloppen, anders zou een tegenboeking alsnog verdwijnen.
    if oud != afdruk and _zoek_op_afdruk(conn, crypto, oud, bedrag) is not None:
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


def bestaande_id(conn, crypto, *, rekening_id: int, boekdatum, bedrag: Decimal,
                 referentie: str = "", tegenpartij_rekening: str = "",
                 mededeling: str = "", tegenpartij_naam: str = "",
                 gebruikt: set | None = None) -> int | None:
    """Zoekt of deze verrichting al in de databank staat.

    Drie manieren, van betrouwbaar naar minder betrouwbaar:

    1. de referentie van de bank, die uniek is per verrichting;
    2. een vingerafdruk over de hele rij;
    3. rekening, datum, bedrag en rekening van de tegenpartij samen.

    Die derde is nodig wanneer je hetzelfde bestand opnieuw aanbiedt met een
    kolom erbij: de mededeling verandert dan, en daarmee ook de vingerafdruk.
    Ze wordt alleen gebruikt wanneer er precies één kandidaat overblijft die in
    deze invoer nog niet gebruikt is, zodat twee identieke verrichtingen op
    dezelfde dag niet op elkaar worden geplakt.
    """
    bedrag = Decimal(str(bedrag))
    datum = boekdatum.isoformat() if isinstance(boekdatum, date) else str(boekdatum)
    gebruikt = gebruikt if gebruikt is not None else set()

    if referentie:
        gevonden = _zoek_op_afdruk(
            conn, crypto, referentieafdruk(crypto, rekening_id, referentie, bedrag))
        if gevonden is None:
            gevonden = _zoek_op_afdruk(
                conn, crypto, crypto.fingerprint("ref", str(rekening_id), referentie),
                bedrag)
        if gevonden is not None:
            return gevonden

    gevonden = _zoek_op_afdruk(conn, crypto, vingerafdruk(
        crypto, rekening_id, datum, bedrag, tegenpartij_rekening, mededeling,
        tegenpartij_naam))
    if gevonden is None:
        gevonden = _zoek_op_afdruk(conn, crypto, _oude_vingerafdruk(
            crypto, rekening_id, datum, bedrag, tegenpartij_rekening, mededeling,
            tegenpartij_naam), bedrag)
    if gevonden is not None:
        return gevonden

    kandidaten = [
        r["id"] for r in conn.execute(
            "SELECT id, bedrag_enc, tegenpartij_rek_idx FROM transacties"
            " WHERE rekening_id = ? AND boekdatum = ?", (rekening_id, datum))
        if r["id"] not in gebruikt
        and crypto.dec_amount(r["bedrag_enc"]) == bedrag
        and r["tegenpartij_rek_idx"] == (
            crypto.blind(tegenpartij_rekening, iban=True) if tegenpartij_rekening else None)
    ]
    return kandidaten[0] if len(kandidaten) == 1 else None


# Velden die bij een tweede aanbieding van hetzelfde bestand aangevuld mogen
# worden. Alleen wat leeg is wordt ingevuld; wat je zelf hebt aangepast blijft.
AANVULBAAR = ["referentie", "beschrijving", "tegenpartij_naam", "tegenpartij_rekening",
              "begunstigde", "mededeling", "handelaar", "land", "valutadatum"]


def vul_aan(conn, crypto, tx_id: int, velden: dict) -> list[str]:
    """Vult lege velden aan met wat er in het bestand staat.

    De mededeling is het geval waarvoor dit bestaat: staat er nu "A | B" en komt
    er "A | B | C" binnen, dan is het nieuwe een uitbreiding van het oude en mag
    het vervangen. Is het iets anders, dan blijft staan wat er stond.
    """
    rij = conn.execute("SELECT * FROM transacties WHERE id = ?", (tx_id,)).fetchone()
    if rij is None:
        return []

    huidig = rij_naar_object(rij, crypto)
    aanpassingen: dict = {}

    for veld in AANVULBAAR:
        nieuw = velden.get(veld)
        nieuw = str(nieuw).strip() if nieuw not in (None, "") else ""
        if not nieuw:
            continue
        oud = (getattr(huidig, veld, "") or "") if veld != "valutadatum" else (
            rij["valutadatum"] or "")
        oud = str(oud).strip()
        if not oud:
            aanpassingen[veld] = nieuw
        elif veld == "mededeling" and oud != nieuw and oud in nieuw:
            aanpassingen[veld] = nieuw

    if not aanpassingen:
        return []
    werk_bij(conn, crypto, tx_id, **aanpassingen)
    return sorted(aanpassingen)


def werk_bij(conn, crypto, tx_id: int, **velden) -> None:
    """Past velden aan. Onbekende sleutels worden genegeerd."""
    kolommen = {
        "categorie_id": ("categorie_id", None),
        "subcategorie_id": ("subcategorie_id", None),
        "subsub_id": ("subsub_id", None),
        "zekerheid": ("zekerheid", None),
        "methode": ("methode", None),
        "status": ("status", None),
        "beschrijving": ("beschrijving_enc", "enc"),
        "referentie": ("referentie_enc", "enc"),
        "tegenpartij_rekening": ("tegenpartij_rek_enc", "enc"),
        "valutadatum": ("valutadatum", None),
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
        if sleutel == "beschrijving":
            stukken.append("beschrijving_idx = ?")
            waarden.append(crypto.blind(waarde) if waarde else None)
        if sleutel == "tegenpartij_rekening":
            stukken.append("tegenpartij_rek_idx = ?")
            waarden.append(crypto.blind(waarde, iban=True) if waarde else None)

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

    # De gecombineerde sleutel hangt van twee velden af; die berekenen we na
    # afloop opnieuw uit wat er nu werkelijk staat.
    if "beschrijving" in velden or "tegenpartij_naam" in velden:
        rij = conn.execute(
            "SELECT beschrijving_enc, tegenpartij_naam_enc FROM transacties WHERE id = ?",
            (tx_id,)).fetchone()
        if rij is not None:
            beschrijving = crypto.dec(rij["beschrijving_enc"]) or ""
            tegenpartij = crypto.dec(rij["tegenpartij_naam_enc"]) or ""
            conn.execute(
                "UPDATE transacties SET sleutel_idx = ? WHERE id = ?",
                (crypto.blind(f"{beschrijving}-{tegenpartij}") if beschrijving else None,
                 tx_id),
            )


def haal(conn, crypto, tx_id: int) -> Transactie | None:
    row = conn.execute("SELECT * FROM transacties WHERE id = ?", (tx_id,)).fetchone()
    return rij_naar_object(row, crypto) if row else None


def zoek(conn, crypto, *, filters=None, categorie_ids=None, cat_namen=None,
         sorteer="datum", aflopend=True, limiet=200, offset=0):
    """Haalt transacties op volgens de filters.

    Zoeken op tekst en sorteren op een versleuteld veld kunnen niet in SQL, dus
    die gebeuren na het ontsleutelen. Bij een zoekterm of een sortering op naam
    wordt de selectie eerst volledig opgehaald en dan pas afgesneden.
    """
    from .filters import Filters
    from .crypto import normalize

    filters = filters or Filters()
    waar, params = filters.sql()
    if categorie_ids:
        plaatsen = ",".join("?" * len(categorie_ids))
        waar += (f" AND (categorie_id IN ({plaatsen}) OR subcategorie_id IN ({plaatsen})"
                 f" OR subsub_id IN ({plaatsen}))")
        params = params + list(categorie_ids) * 3

    sql = f"SELECT * FROM transacties WHERE {waar}"

    # Sorteringen die rechtstreeks in SQL kunnen.
    in_sql = {"datum": "boekdatum", "status": "status", "bron": "methode",
              "zekerheid": "zekerheid"}
    in_geheugen = sorteer in ("tegenpartij", "mededeling", "categorie", "bedrag")
    naar_geheugen = bool(filters.zoekterm) or in_geheugen or filters.vraagt_tekst

    if not naar_geheugen:
        richting_sql = "DESC" if aflopend else "ASC"
        sql += f" ORDER BY {in_sql.get(sorteer, 'boekdatum')} {richting_sql}, id {richting_sql}"
        sql += " LIMIT ? OFFSET ?"
        return ([rij_naar_object(r, crypto)
                 for r in conn.execute(sql, params + [limiet, offset])], None)

    naald = normalize(filters.zoekterm) if filters.zoekterm else ""
    cat_namen = cat_namen or {}
    gevonden = []
    for row in conn.execute(sql, params):
        tx = rij_naar_object(row, crypto)
        if filters.vraagt_tekst and not filters.past_tekst(land=tx.land,
                                                           winkel=tx.handelaar):
            continue
        if naald:
            pad = " ".join(cat_namen.get(i, "") for i in
                           (tx.categorie_id, tx.subcategorie_id, tx.subsub_id) if i)
            hooiberg = normalize(" ".join([
                tx.tegenpartij_naam, tx.mededeling, tx.begunstigde, tx.handelaar,
                tx.land, tx.beschrijving, tx.tegenpartij_rekening, pad,
            ]))
            if naald not in hooiberg:
                continue
        gevonden.append(tx)

    sleutels = {
        "datum": lambda t: (t.boekdatum, t.id),
        "tegenpartij": lambda t: (t.tegenpartij_naam or t.handelaar or "").lower(),
        "mededeling": lambda t: (t.mededeling or "").lower(),
        "categorie": lambda t: " ".join(
            cat_namen.get(i, "") for i in
            (t.categorie_id, t.subcategorie_id, t.subsub_id) if i).lower(),
        # Op de grootte van het bedrag, niet op het teken: bij een lijst vol
        # uitgaven wil je de zwaarste bovenaan, niet de kleinste.
        "bedrag": lambda t: abs(t.bedrag),
        "bron": lambda t: t.methode,
        "status": lambda t: t.status,
        "zekerheid": lambda t: t.zekerheid,
    }
    gevonden.sort(key=sleutels.get(sorteer, sleutels["datum"]), reverse=aflopend)
    return gevonden[offset:offset + limiet], len(gevonden)


def tel(conn, status: str | None = None) -> int:
    sql = "SELECT COUNT(*) AS n FROM transacties"
    params: list = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    return conn.execute(sql, params).fetchone()["n"]
