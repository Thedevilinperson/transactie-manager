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
from dataclasses import dataclass, field
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

    def _besten(doel: str, kandidaten: list[str], drempel: float, aantal: int = 8):
        """De beste kandidaten, in één C-lus in plaats van in Python."""
        return [(t[2], t[1]) for t in _process.extract(
            doel, kandidaten, scorer=_fuzz.WRatio, score_cutoff=drempel, limit=aantal)]
except ImportError:  # terugval op de standaardbibliotheek
    _process = None
    from difflib import SequenceMatcher

    def _ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100.0

    def _besten(doel: str, kandidaten: list[str], drempel: float, aantal: int = 8):
        scores = [(i, _ratio(doel, k)) for i, k in enumerate(kandidaten)]
        return sorted((p for p in scores if p[1] >= drempel), key=lambda p: -p[1])[:aantal]


# Regels die wel indelen maar altijd om bevestiging vragen.
ONZEKERE_HERKOMSTEN = {"referentie_onzeker", "historiek_onzeker"}


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
    regel_id: int | None = None

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
class Voorwaarde:
    """Eén vergelijking op één veld."""
    veld: str
    operator: str
    waarde: str


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
    # Bijkomende voorwaarden, met EN bovenop de eerste. Leeg bij een gewone
    # regel op één veld.
    extra: list[Voorwaarde] = field(default_factory=list)

    @property
    def voorwaarden(self) -> list[Voorwaarde]:
        """Alle voorwaarden samen, de eerste voorop."""
        return [Voorwaarde(self.veld, self.operator, self.waarde)] + self.extra

    @property
    def gecombineerd(self) -> bool:
        return bool(self.extra)


def laad_regels(conn, crypto, alleen_actief: bool = True) -> list[Regel]:
    """De regels op prioriteit. Met `alleen_actief=False` komen de
    uitgeschakelde er ook bij — nodig om te weten wat een regel deed voordat
    hij uitgezet werd."""
    extra: dict[int, list[Voorwaarde]] = {}
    for rij in conn.execute("SELECT * FROM regel_voorwaarden"
                            " ORDER BY regel_id, volgorde, id"):
        extra.setdefault(rij["regel_id"], []).append(Voorwaarde(
            veld=rij["veld"], operator=rij["operator"],
            waarde=crypto.dec(rij["waarde_enc"]) or "",
        ))

    regels = []
    sql = "SELECT * FROM regels"
    if alleen_actief:
        sql += " WHERE actief = 1"
    for row in conn.execute(sql + " ORDER BY prioriteit, id"):
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
            extra=extra.get(row["id"], []),
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


def _voorwaarde_past(vw: Voorwaarde, k: TransactieKenmerken) -> bool:
    """Eén vergelijking op één veld.

    `bevat_niet` is er omdat een combinatie pas nuttig wordt als je ook iets kan
    uitsluiten: "alles van Total, behalve wanneer er CARWASH in de mededeling
    staat". Een leeg veld telt daarbij als "bevat het niet", want dan staat het
    er inderdaad niet.
    """
    doel = _veldwaarde(k, vw.veld)
    naald = (normalize_iban(vw.waarde) if vw.veld == "tegenpartij_rekening"
             else normalize(vw.waarde))

    if vw.operator == "regex":
        try:
            return re.search(vw.waarde, doel, re.IGNORECASE) is not None
        except re.error:
            return False
    if not naald:
        return False
    if vw.operator == "bevat_niet":
        return naald not in doel
    if not doel:
        return False
    if vw.operator == "gelijk":
        return doel == naald
    if vw.operator == "bevat":
        return naald in doel
    return False


def regel_past(regel: Regel, k: TransactieKenmerken) -> bool:
    """Past de regel op deze transactie?

    Alle voorwaarden moeten kloppen, en de bedragvork en de richting erbovenop.
    """
    if regel.richting and regel.richting != k.richting:
        return False
    bedrag = abs(k.bedrag)
    if regel.bedrag_min is not None and bedrag < Decimal(str(regel.bedrag_min)):
        return False
    if regel.bedrag_max is not None and bedrag >= Decimal(str(regel.bedrag_max)):
        return False

    return all(_voorwaarde_past(vw, k) for vw in regel.voorwaarden)


def eerste_passende(regels: list[Regel], k: TransactieKenmerken) -> Regel | None:
    """Geeft de eerste regel die past. De lijst staat op prioriteit gesorteerd."""
    for regel in regels:
        if regel_past(regel, k):
            return regel
    return None


def naar_voorstel(regel: Regel) -> Voorstel:
    omschrijving = regel.naam or f"regel #{regel.id}"
    onzeker = regel.herkomst in ONZEKERE_HERKOMSTEN
    return Voorstel(
        categorie_id=regel.categorie_id,
        subcategorie_id=regel.subcategorie_id,
        subsub_id=regel.subsub_id,
        handelaar=regel.handelaar,
        land=regel.land,
        zekerheid=0.6 if onzeker else 1.0,
        methode="regel",
        status="nazicht" if onzeker else "bevestigd",
        toelichting=(f"{omschrijving} wijst naar meer dan één categorie. "
                     "Kies zelf welke hier past."
                     if onzeker else f"Toegewezen door {omschrijving}."),
        regel_id=regel.id,
    )


def pas_regels_toe(regels: list[Regel], k: TransactieKenmerken) -> Voorstel | None:
    for regel in regels:
        if regel_past(regel, k):
            omschrijving = regel.naam or f"regel #{regel.id}"
            onzeker = regel.herkomst in ONZEKERE_HERKOMSTEN
            return Voorstel(
                categorie_id=regel.categorie_id,
                subcategorie_id=regel.subcategorie_id,
                subsub_id=regel.subsub_id,
                handelaar=regel.handelaar,
                land=regel.land,
                zekerheid=0.6 if onzeker else 1.0,
                methode="regel",
                status="nazicht" if onzeker else "bevestigd",
                toelichting=(f"{omschrijving} wijst in de historiek naar meer dan "
                             "één categorie. Kies zelf welke hier past."
                             if onzeker else f"Toegewezen door {omschrijving}."),
                regel_id=regel.id,
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
    # "in", "uit" of None (een regel zonder richting geldt voor beide).
    richting: str | None = None
    # Waarom deze referentie om nazicht vraagt: "referentie" (de regel wees
    # in het categorieënbestand naar meer dan één categorie) of "meerdere"
    # (deze tegenpartij komt in je geschiedenis onder meer dan één categorie
    # voor).
    onzeker_reden: str = ""


# Alleen wat een mens heeft ingedeeld, telt als geschiedenis voor de fuzzy stap:
# met de hand (manueel), uit een ingelezen historiek (bestand), of een
# AI-voorstel dat je bevestigd hebt. Wat een regel of de fuzzy stap zelf
# indeelde, telt niet mee. Dat werd vroeger wel gedaan, op de naam alleen, en
# dan veralgemeende de motor zijn eigen werk: een regel "Axelle Huyge én
# drinkgeld in de mededeling" deelde transacties in, die transacties werden
# geschiedenis voor "Axelle Huyge", en daarna ging élke transactie van Axelle
# automatisch naar drinkgeld — elke automatische bevestiging maakte de volgende
# nog zekerder.
MENSELIJKE_METHODEN = ("manueel", "bestand", "ai")

# Een fuzzy treffer wordt alleen automatisch bevestigd als beide namen ongeveer
# even lang zijn. Is de ene veel korter, dan past ze gewoon binnen de andere en
# moet je het zelf nakijken. En dan alleen als het eerste woord gelijk is:
# "Delhaize" in "Delhaize Gent" is dezelfde zaak, "Huyge" in "Daniel Huyge" is
# alleen dezelfde familienaam.
MIN_LENGTEVERHOUDING = 0.67


def bouw_geschiedenis(conn, crypto, regels: list["Regel"] | None = None,
                      limiet: int = 8000) -> list[Referentie]:
    """Verzamelt vergelijkingsmateriaal voor de fuzzy stap.

    Twee bronnen:

    * transacties die een mens heeft ingedeeld (zie MENSELIJKE_METHODEN) of
      waarvan hij het voorstel met *Klopt* goedkeurde (`nagekeken`);
    * regels die enkel op de naam van de tegenpartij (of de gecombineerde
      sleutel) werken. Een regel met bijkomende voorwaarden of een bedragvork
      doet niet mee: de fuzzy stap vergelijkt alleen namen, en zou zo'n regel
      dus ruimer toepassen dan hij bedoeld is. Die regel doet zijn werk in de
      regelstap, precies zoals hij geschreven is.

    Komt een tegenpartij in dezelfde richting onder meer dan één categorie
    voor, dan wordt ze als onzeker gemarkeerd: de fuzzy stap stelt dan wel iets
    voor, maar bevestigt niet zelf.
    """
    verzameld: dict[tuple, Referentie] = {}

    def voeg_toe(basis, cat, sub, subsub, handelaar, land, richting, bedrag=None,
                 gewicht=1, onzeker=False):
        if not basis:
            return
        sleutel = (basis, cat, sub, subsub, richting)
        ref = verzameld.get(sleutel)
        if ref is None:
            verzameld[sleutel] = Referentie(
                tekst=basis, categorie_id=cat, subcategorie_id=sub, subsub_id=subsub,
                handelaar=handelaar, land=land, aantal=gewicht,
                bedrag_min=bedrag, bedrag_max=bedrag, onzeker=onzeker,
                richting=richting, onzeker_reden="referentie" if onzeker else "",
            )
        else:
            ref.aantal += gewicht
            if bedrag is not None:
                ref.bedrag_min = bedrag if ref.bedrag_min is None else min(ref.bedrag_min, bedrag)
                ref.bedrag_max = bedrag if ref.bedrag_max is None else max(ref.bedrag_max, bedrag)

    plaatsen = ",".join("?" * len(MENSELIJKE_METHODEN))
    rows = conn.execute(
        "SELECT tegenpartij_naam_enc, handelaar_enc, land_enc, bedrag_enc, richting,"
        " categorie_id, subcategorie_id, subsub_id"
        " FROM transacties WHERE status='bevestigd' AND categorie_id IS NOT NULL"
        f" AND (methode IN ({plaatsen}) OR nagekeken = 1)"
        " ORDER BY id DESC LIMIT ?",
        (*MENSELIJKE_METHODEN, limiet),
    ).fetchall()
    for row in rows:
        naam = crypto.dec(row["tegenpartij_naam_enc"]) or ""
        handelaar = crypto.dec(row["handelaar_enc"])
        voeg_toe(normalize(handelaar or naam), row["categorie_id"], row["subcategorie_id"],
                 row["subsub_id"], handelaar or naam, crypto.dec(row["land_enc"]),
                 row["richting"], abs(crypto.dec_amount(row["bedrag_enc"])), gewicht=2)

    for regel in (regels or []):
        if regel.categorie_id is None:
            continue
        if regel.extra or regel.bedrag_min is not None or regel.bedrag_max is not None:
            continue
        if regel.veld == "sleutel":
            # Alleen het tegenpartijdeel is bruikbaar om op te vergelijken.
            basis = normalize(regel.waarde.split("-", 1)[-1])
        elif regel.veld == "tegenpartij_naam":
            basis = normalize(regel.waarde)
        else:
            continue
        voeg_toe(basis, regel.categorie_id, regel.subcategorie_id, regel.subsub_id,
                 regel.handelaar, regel.land, regel.richting,
                 onzeker=regel.herkomst in ONZEKERE_HERKOMSTEN)

    # Tegenpartijen die in dezelfde richting onder meer dan één categorie staan.
    # Een referentie zonder richting (van een regel) telt in beide mee.
    per_naam: dict[str, list[Referentie]] = {}
    for ref in verzameld.values():
        per_naam.setdefault(ref.tekst, []).append(ref)
    for refs in per_naam.values():
        if len(refs) < 2:
            continue
        for richting in ("in", "uit"):
            hier = [r for r in refs if r.richting in (richting, None)]
            paden = {(r.categorie_id, r.subcategorie_id, r.subsub_id) for r in hier}
            if len(paden) > 1:
                for r in hier:
                    if not r.onzeker:
                        r.onzeker = True
                        r.onzeker_reden = "meerdere"

    return sorted(verzameld.values(), key=lambda r: -r.aantal)


def fuzzy_voorstel(geschiedenis: list[Referentie], kandidaten: list[str],
                   k: TransactieKenmerken, auto_drempel: float,
                   suggestie_drempel: float) -> Voorstel | None:
    doel = normalize(k.tegenpartij_naam) or k.tekst()
    if not doel or not kandidaten:
        return None

    treffer = None
    for index, score in _besten(doel, kandidaten, suggestie_drempel):
        ref = geschiedenis[index]
        lengtes = sorted((len(doel), len(ref.tekst)))
        gedeeltelijk = bool(lengtes[1]) and lengtes[0] / lengtes[1] < MIN_LENGTEVERHOUDING
        if gedeeltelijk and doel.split()[:1] != ref.tekst.split()[:1]:
            # De kortere naam past in de langere, maar niet vooraan: dan is het
            # gedeelde stuk meestal een familienaam ("Huyge" in "Axelle Huyge"),
            # en dat zegt niets. Bij een winkel is het gedeelde stuk net het
            # eerste woord ("Delhaize" in "Delhaize Gent 1234").
            continue
        treffer = (index, score, gedeeltelijk)
        break
    if treffer is None:
        return None

    index, score, gedeeltelijk = treffer
    ref = geschiedenis[index]
    # Herhaalde bevestigingen wegen licht door.
    score = min(100.0, score + min(ref.aantal, 10) * 0.3)
    zeker = score / 100.0
    naam = ref.handelaar or ref.tekst

    if score >= auto_drempel and not ref.onzeker and not gedeeltelijk:
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
            toelichting=(f"{naam} komt in je geschiedenis onder meer dan één "
                         "categorie voor. Kies zelf welke hier past."
                         if ref.onzeker_reden == "meerdere" else
                         f"{naam} staat in de referentielijst onder meer dan één "
                         "categorie. Kies zelf welke hier past."),
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

class Regelboek:
    """De regelstap van de motor, los van de fuzzy stap.

    Bij duizenden regels loont het om de exacte vergelijkingen in een
    woordenboek te zetten; alleen de bevat- en regex-regels worden nog
    doorlopen.

    De klasse staat apart omdat het regelonderhoud dezelfde keuze moet kunnen
    maken als de motor: welke regel zou déze transactie nu toewijzen? Zou dat
    met een eigen kopie van die logica gebeuren, dan gaan beide op den duur uit
    elkaar lopen.
    """

    def __init__(self, regels: list[Regel]):
        self.regels = sorted(regels, key=lambda r: (r.prioriteit, r.id))
        self.exact: dict[tuple[str, str], Regel] = {}
        self.los: list[Regel] = []
        for regel in self.regels:
            if regel.operator == "gelijk" and not regel.extra \
                    and regel.bedrag_min is None and regel.bedrag_max is None:
                sleutel = (regel.veld,
                           normalize_iban(regel.waarde)
                           if regel.veld == "tegenpartij_rekening"
                           else normalize(regel.waarde))
                self.exact.setdefault(sleutel, regel)
            else:
                self.los.append(regel)

    def beste(self, k: TransactieKenmerken) -> Regel | None:
        """De regel die deze transactie toewijst, of None.

        Exacte treffers en regels met een bedragvork worden samen beoordeeld en
        niet na elkaar: anders zou een brede regel op de tegenpartij altijd
        voorgaan op een nauwkeurigere regel die het bedrag meeneemt.
        """
        kandidaten: list[Regel] = []
        for veld, waarde in (("sleutel", k.sleutel()),
                             ("beschrijving", normalize(k.beschrijving)),
                             ("tegenpartij_naam", normalize(k.tegenpartij_naam)),
                             ("tegenpartij_rekening",
                              normalize_iban(k.tegenpartij_rekening))):
            if not waarde:
                continue
            regel = self.exact.get((veld, waarde))
            if regel is not None and (regel.richting is None
                                      or regel.richting == k.richting):
                kandidaten.append(regel)

        los = eerste_passende(self.los, k)
        if los is not None:
            kandidaten.append(los)

        if not kandidaten:
            return None
        return min(kandidaten, key=lambda r: (r.prioriteit, r.id))


class Motor:
    """Laadt regels en geschiedenis één keer en beoordeelt daarna elke rij."""

    def __init__(self, conn, crypto):
        self.conn = conn
        self.crypto = crypto
        self.regels = laad_regels(conn, crypto)
        self.regelboek = Regelboek(self.regels)

        self.geschiedenis = bouw_geschiedenis(conn, crypto, self.regels)
        self._verdeel()
        self.auto_drempel = float(instelling(conn, "fuzzy_auto_drempel", "92"))
        self.suggestie_drempel = float(instelling(conn, "fuzzy_suggestie_drempel", "72"))

    def beoordeel(self, k: TransactieKenmerken) -> Voorstel:
        """Zoekt de best passende regel en valt anders terug op de fuzzy stap."""
        beste = self.regelboek.beste(k)
        if beste is not None:
            return naar_voorstel(beste)

        refs, teksten = self.per_richting.get(k.richting, ([], []))
        voorstel = fuzzy_voorstel(refs, teksten, k,
                                  self.auto_drempel, self.suggestie_drempel)
        if voorstel is not None:
            return voorstel

        return Voorstel(
            methode="geen", status="niet_toegewezen",
            toelichting="Geen regel of gelijkaardige transactie gevonden.",
        )

    def _verdeel(self) -> None:
        """Per richting de referenties die er gelden: een uitgave vergelijken
        met een inkomst van dezelfde tegenpartij heeft geen zin. Referenties
        zonder richting (van regels) gelden in beide."""
        self.per_richting = {}
        for richting in ("in", "uit"):
            refs = [r for r in self.geschiedenis if r.richting in (richting, None)]
            self.per_richting[richting] = (refs, [r.tekst for r in refs])

    def onthoud(self, k: TransactieKenmerken, voorstel: Voorstel) -> None:
        """Voegt een indeling tijdens een invoer toe aan het vergelijkingsmateriaal.

        Alleen als ze van een mens komt (een ingelezen historiek met categorie).
        Wat de motor zelf net indeelde, mag de volgende rij van dezelfde invoer
        niet sturen — anders versterkt één gok zichzelf over het hele bestand.
        """
        if (not voorstel.gevonden or voorstel.status != "bevestigd"
                or voorstel.methode not in MENSELIJKE_METHODEN):
            return
        basis = normalize(voorstel.handelaar or k.tegenpartij_naam)
        if not basis:
            return
        for ref in self.geschiedenis:
            if (ref.tekst == basis and ref.categorie_id == voorstel.categorie_id
                    and ref.subcategorie_id == voorstel.subcategorie_id
                    and ref.richting == k.richting):
                ref.aantal += 1
                return
        andere = [r for r in self.geschiedenis if r.tekst == basis
                  and r.richting in (k.richting, None)]
        nieuw = Referentie(
            tekst=basis, categorie_id=voorstel.categorie_id,
            subcategorie_id=voorstel.subcategorie_id, subsub_id=voorstel.subsub_id,
            handelaar=voorstel.handelaar or k.tegenpartij_naam, land=voorstel.land,
            richting=k.richting,
        )
        if andere:
            # Nu staat deze tegenpartij onder meer dan één categorie.
            for r in andere + [nieuw]:
                if not r.onzeker:
                    r.onzeker, r.onzeker_reden = True, "meerdere"
        self.geschiedenis.append(nieuw)
        self._verdeel()
