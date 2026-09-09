"""De categorisatiemotor.

Volgorde van toewijzing:

1. **Vaste regels** — exacte of bevat-vergelijking op tegenpartij, rekening of
   mededeling, eventueel begrensd door een bedragvork. Resultaat is zeker.
2. **Fuzzy vergelijking** met eerder bevestigde transacties. Boven de
   auto-drempel wordt de categorie toegewezen en als zeker gemarkeerd; tussen
   de suggestie- en auto-drempel komt de transactie in het nazicht terecht.
3. **Lokaal AI-model** (optioneel) — wordt apart aangeroepen en levert altijd
   een voorstel dat de gebruiker moet bevestigen.
4. **Manueel** — de gebruiker kiest zelf.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from ..crypto import normalize, normalize_iban
from ..database import instelling

try:  # snelle implementatie indien beschikbaar
    from rapidfuzz import fuzz as _fuzz, process as _process

    # WRatio en niet token_set_ratio: die laatste geeft 100% zodra de ene naam
    # een deelverzameling van de andere is, waardoor "Brico" evengoed op
    # "Brico Plan-It 4214 Gent" past als op om het even welke andere Brico.
    def _ratio(a: str, b: str) -> float:
        return float(_fuzz.WRatio(a, b))

    def _beste(doel: str, kandidaten: list[str], drempel: float):
        """Zoekt de beste kandidaat in één C-lus in plaats van in Python."""
        treffer = _process.extractOne(
            doel, kandidaten, scorer=_fuzz.WRatio, score_cutoff=drempel
        )
        return (treffer[2], treffer[1]) if treffer else None
except ImportError:  # terugval op de standaardbibliotheek
    _process = None
    from difflib import SequenceMatcher

    def _ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100.0

    def _beste(doel: str, kandidaten: list[str], drempel: float):
        beste = None
        for i, kandidaat in enumerate(kandidaten):
            score = _ratio(doel, kandidaat)
            if score >= drempel and (beste is None or score > beste[1]):
                beste = (i, score)
        return beste


@dataclass
class Voorstel:
    categorie_id: int | None = None
    subcategorie_id: int | None = None
    subsub_id: int | None = None
    handelaar: str | None = None
    land: str | None = None
    zekerheid: float = 0.0
    methode: str = "geen"
    status: str = "niet_toegewezen"
    toelichting: str = ""

    @property
    def gevonden(self) -> bool:
        return self.categorie_id is not None


@dataclass
class TransactieKenmerken:
    """Alles waar de motor naar kijkt, in klare tekst."""
    beschrijving: str = ""
    tegenpartij_naam: str = ""
    tegenpartij_rekening: str = ""
    mededeling: str = ""
    begunstigde: str = ""
    bedrag: Decimal = Decimal("0")
    richting: str = "uit"

    def tekst(self) -> str:
        return normalize(" ".join(
            [self.beschrijving, self.tegenpartij_naam, self.mededeling, self.begunstigde]
        ))

    def sleutel(self) -> str:
        """De referentiesleutel uit het categorieënbestand:
        beschrijving en tegenpartij aan elkaar geplakt."""
        return normalize(f"{self.beschrijving}-{self.tegenpartij_naam}")


# --------------------------------------------------------------------------
# Stap 1: vaste regels
# --------------------------------------------------------------------------

@dataclass
class Regel:
    id: int
    naam: str
    prioriteit: int
    veld: str
    operator: str
    waarde: str
    bedrag_min: float | None
    bedrag_max: float | None
    richting: str | None
    categorie_id: int | None
    subcategorie_id: int | None
    subsub_id: int | None
    handelaar: str | None
    land: str | None
    herkomst: str = "handmatig"


def laad_regels(conn, crypto) -> list[Regel]:
    regels = []
    for row in conn.execute(
        "SELECT * FROM regels WHERE actief = 1 ORDER BY prioriteit, id"
    ):
        regels.append(Regel(
            id=row["id"],
            naam=crypto.dec(row["naam_enc"]) or "",
            prioriteit=row["prioriteit"],
            veld=row["veld"],
            operator=row["operator"],
            waarde=crypto.dec(row["waarde_enc"]) or "",
            bedrag_min=row["bedrag_min"],
            bedrag_max=row["bedrag_max"],
            richting=row["richting"],
            categorie_id=row["categorie_id"],
            subcategorie_id=row["subcategorie_id"],
            subsub_id=row["subsub_id"],
            handelaar=crypto.dec(row["handelaar_enc"]),
            land=crypto.dec(row["land_enc"]),
            herkomst=row["herkomst"] if "herkomst" in row.keys() else "handmatig",
        ))
    return regels


def _veldwaarde(k: TransactieKenmerken, veld: str) -> str:
    if veld == "sleutel":
        return k.sleutel()
    if veld == "beschrijving":
        return normalize(k.beschrijving)
    if veld == "tegenpartij_naam":
        return normalize(k.tegenpartij_naam)
    if veld == "tegenpartij_rekening":
        return normalize_iban(k.tegenpartij_rekening)
    if veld == "mededeling":
        return normalize(k.mededeling)
    return k.tekst() + " " + normalize_iban(k.tegenpartij_rekening)


def regel_past(regel: Regel, k: TransactieKenmerken) -> bool:
    if regel.richting and regel.richting != k.richting:
        return False
    bedrag = abs(k.bedrag)
    if regel.bedrag_min is not None and bedrag < Decimal(str(regel.bedrag_min)):
        return False
    if regel.bedrag_max is not None and bedrag >= Decimal(str(regel.bedrag_max)):
        return False

    doel = _veldwaarde(k, regel.veld)
    if not doel:
        return False
    if regel.veld == "tegenpartij_rekening":
        naald = normalize_iban(regel.waarde)
    else:
        naald = normalize(regel.waarde)
    if not naald:
        return False

    if regel.operator == "gelijk":
        return doel == naald
    if regel.operator == "bevat":
        return bool(naald) and naald in doel
    if regel.operator == "regex":
        try:
            return re.search(regel.waarde, doel, re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def pas_regels_toe(regels: list[Regel], k: TransactieKenmerken) -> Voorstel | None:
    for regel in regels:
        if regel_past(regel, k):
            omschrijving = regel.naam or f"regel #{regel.id}"
            return Voorstel(
                categorie_id=regel.categorie_id,
                subcategorie_id=regel.subcategorie_id,
                subsub_id=regel.subsub_id,
                handelaar=regel.handelaar,
                land=regel.land,
                zekerheid=1.0,
                methode="regel",
                status="bevestigd",
                toelichting=f"Toegewezen door {omschrijving}.",
            )
    return None


# --------------------------------------------------------------------------
# Stap 2: fuzzy vergelijking met de geschiedenis
# --------------------------------------------------------------------------

@dataclass
class Referentie:
    tekst: str
    categorie_id: int
    subcategorie_id: int | None
    subsub_id: int | None
    handelaar: str | None
    land: str | None
    aantal: int = 1
    bedrag_min: Decimal | None = None
    bedrag_max: Decimal | None = None
    onzeker: bool = False


def bouw_geschiedenis(conn, crypto, regels: list["Regel"] | None = None,
                      limiet: int = 8000) -> list[Referentie]:
    """Verzamelt vergelijkingsmateriaal voor de fuzzy stap.

    Twee bronnen: eerder bevestigde transacties, en de regels die uit het
    categorieënbestand zijn ingelezen. Die tweede bron is wat de motor bij een
    allereerste invoer al bruikbaar maakt, wanneer er nog geen geschiedenis is.
    """
    verzameld: dict[tuple, Referentie] = {}

    def voeg_toe(basis, cat, sub, subsub, handelaar, land, bedrag=None, gewicht=1,
                 onzeker=False):
        if not basis:
            return
        sleutel = (basis, cat, sub, subsub)
        ref = verzameld.get(sleutel)
        if ref is None:
            verzameld[sleutel] = Referentie(
                tekst=basis, categorie_id=cat, subcategorie_id=sub, subsub_id=subsub,
                handelaar=handelaar, land=land, aantal=gewicht,
                bedrag_min=bedrag, bedrag_max=bedrag, onzeker=onzeker,
            )
        else:
            ref.aantal += gewicht
            if bedrag is not None:
                ref.bedrag_min = bedrag if ref.bedrag_min is None else min(ref.bedrag_min, bedrag)
                ref.bedrag_max = bedrag if ref.bedrag_max is None else max(ref.bedrag_max, bedrag)

    rows = conn.execute(
        "SELECT tegenpartij_naam_enc, handelaar_enc, land_enc, bedrag_enc,"
        " categorie_id, subcategorie_id, subsub_id"
        " FROM transacties WHERE status='bevestigd' AND categorie_id IS NOT NULL"
        " ORDER BY id DESC LIMIT ?",
        (limiet,),
    ).fetchall()
    for row in rows:
        naam = crypto.dec(row["tegenpartij_naam_enc"]) or ""
        handelaar = crypto.dec(row["handelaar_enc"])
        voeg_toe(normalize(handelaar or naam), row["categorie_id"], row["subcategorie_id"],
                 row["subsub_id"], handelaar or naam, crypto.dec(row["land_enc"]),
                 abs(crypto.dec_amount(row["bedrag_enc"])), gewicht=2)

    for regel in (regels or []):
        if regel.categorie_id is None:
            continue
        if regel.veld == "sleutel":
            # Alleen het tegenpartijdeel is bruikbaar om op te vergelijken.
            basis = normalize(regel.waarde.split("-", 1)[-1])
        elif regel.veld == "tegenpartij_naam":
            basis = normalize(regel.waarde)
        else:
            continue
        voeg_toe(basis, regel.categorie_id, regel.subcategorie_id, regel.subsub_id,
                 regel.handelaar, regel.land,
                 onzeker=regel.herkomst == "referentie_onzeker")

    return sorted(verzameld.values(), key=lambda r: -r.aantal)


def fuzzy_voorstel(geschiedenis: list[Referentie], kandidaten: list[str],
                   k: TransactieKenmerken, auto_drempel: float,
                   suggestie_drempel: float) -> Voorstel | None:
    doel = normalize(k.tegenpartij_naam) or k.tekst()
    if not doel or not kandidaten:
        return None

    treffer = _beste(doel, kandidaten, suggestie_drempel)
    if treffer is None:
        return None

    index, score = treffer
    ref = geschiedenis[index]
    # Herhaalde bevestigingen wegen licht door.
    score = min(100.0, score + min(ref.aantal, 10) * 0.3)
    zeker = score / 100.0
    naam = ref.handelaar or ref.tekst

    if score >= auto_drempel and not ref.onzeker:
        return Voorstel(
            categorie_id=ref.categorie_id, subcategorie_id=ref.subcategorie_id,
            subsub_id=ref.subsub_id, handelaar=ref.handelaar, land=ref.land,
            zekerheid=round(zeker, 3), methode="fuzzy", status="bevestigd",
            toelichting=f"Sterke gelijkenis ({score:.0f}%) met {naam}.",
        )
    if ref.onzeker:
        return Voorstel(
            categorie_id=ref.categorie_id, subcategorie_id=ref.subcategorie_id,
            subsub_id=ref.subsub_id, handelaar=ref.handelaar, land=ref.land,
            zekerheid=round(min(zeker, 0.6), 3), methode="fuzzy", status="nazicht",
            toelichting=f"{naam} staat in de referentielijst onder meer dan één "
                        "categorie. Kies zelf welke hier past.",
        )
    return Voorstel(
        categorie_id=ref.categorie_id, subcategorie_id=ref.subcategorie_id,
        subsub_id=ref.subsub_id, handelaar=ref.handelaar, land=ref.land,
        zekerheid=round(zeker, 3), methode="fuzzy", status="nazicht",
        toelichting=f"Vermoedelijke match ({score:.0f}%) met {naam}. Nakijken voor bevestiging.",
    )


# --------------------------------------------------------------------------
# Samenhangende motor
# --------------------------------------------------------------------------

class Motor:
    """Laadt regels en geschiedenis één keer en beoordeelt daarna elke rij.

    Bij duizenden regels loont het om de exacte vergelijkingen in een
    woordenboek te zetten; alleen de bevat- en regex-regels worden nog
    doorlopen.
    """

    def __init__(self, conn, crypto):
        self.conn = conn
        self.crypto = crypto
        self.regels = laad_regels(conn, crypto)
        self.exact: dict[tuple[str, str], Regel] = {}
        self.los: list[Regel] = []
        for regel in self.regels:
            if regel.operator == "gelijk" and regel.bedrag_min is None \
                    and regel.bedrag_max is None:
                sleutel = (regel.veld, normalize(regel.waarde))
                self.exact.setdefault(sleutel, regel)
            else:
                self.los.append(regel)

        self.geschiedenis = bouw_geschiedenis(conn, crypto, self.regels)
        self.kandidaten = [ref.tekst for ref in self.geschiedenis]
        self.auto_drempel = float(instelling(conn, "fuzzy_auto_drempel", "92"))
        self.suggestie_drempel = float(instelling(conn, "fuzzy_suggestie_drempel", "72"))

    def beoordeel(self, k: TransactieKenmerken) -> Voorstel:
        # Stap 1a: exacte treffer op de gecombineerde sleutel, dan op tegenpartij.
        for veld, waarde in (("sleutel", k.sleutel()),
                             ("beschrijving", normalize(k.beschrijving)),
                             ("tegenpartij_naam", normalize(k.tegenpartij_naam))):
            regel = self.exact.get((veld, waarde))
            if regel is not None and (regel.richting is None or regel.richting == k.richting):
                onzeker = regel.herkomst == "referentie_onzeker"
                return Voorstel(
                    categorie_id=regel.categorie_id,
                    subcategorie_id=regel.subcategorie_id,
                    subsub_id=regel.subsub_id,
                    handelaar=regel.handelaar, land=regel.land,
                    zekerheid=0.6 if onzeker else 1.0,
                    methode="regel",
                    status="nazicht" if onzeker else "bevestigd",
                    toelichting=(
                        f"{regel.naam or veld} komt in de referentielijst onder "
                        "meer dan één categorie voor. Kies zelf welke hier past."
                        if onzeker else
                        f"Exacte treffer in de referentielijst ({regel.naam or veld})."
                    ),
                )

        # Stap 1b: de overige regels, met bedragvork en bevat-vergelijking.
        voorstel = pas_regels_toe(self.los, k)
        if voorstel is not None:
            return voorstel

        # Stap 2: fuzzy vergelijking.
        voorstel = fuzzy_voorstel(self.geschiedenis, self.kandidaten, k,
                                  self.auto_drempel, self.suggestie_drempel)
        if voorstel is not None:
            return voorstel

        return Voorstel(
            methode="geen", status="niet_toegewezen",
            toelichting="Geen regel of gelijkaardige transactie gevonden.",
        )

    def onthoud(self, k: TransactieKenmerken, voorstel: Voorstel) -> None:
        """Voegt een bevestigde toewijzing toe aan het vergelijkingsmateriaal."""
        if not voorstel.gevonden or voorstel.status != "bevestigd":
            return
        basis = normalize(voorstel.handelaar or k.tegenpartij_naam)
        if not basis:
            return
        for ref in self.geschiedenis:
            if (ref.tekst == basis and ref.categorie_id == voorstel.categorie_id
                    and ref.subcategorie_id == voorstel.subcategorie_id):
                ref.aantal += 1
                return
        self.geschiedenis.append(Referentie(
            tekst=basis, categorie_id=voorstel.categorie_id,
            subcategorie_id=voorstel.subcategorie_id, subsub_id=voorstel.subsub_id,
            handelaar=voorstel.handelaar or k.tegenpartij_naam, land=voorstel.land,
        ))
        self.kandidaten.append(basis)
