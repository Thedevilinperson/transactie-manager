"""De categorisatiemotor.

Volgorde van toewijzing:

1. **Vaste regels** — exacte of bevat-vergelijking op tegenpartij, rekening,
   beschrijving of mededeling, eventueel gecombineerd met EN en OF en begrensd
   door een bedragvork. Een bevestigde regel deelt zeker in; een onbevestigde
   stuurt de transactie naar het nazicht.
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


# Herkomsten van regels die bij het ontstaan naar meer dan één categorie
# wezen. Ze zeggen alleen nog waar een regel vandaan komt; of ze zeker
# indeelt, hangt sinds schemaversie 12 af van `Regel.bevestigd`.
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
    """Eén vergelijking op één veld.

    `koppeling` zegt hoe ze aan de voorwaarde ervoor hangt: "en" of "of". Bij de
    eerste voorwaarde van een regel speelt ze geen rol.
    """
    veld: str
    operator: str
    waarde: str
    koppeling: str = "en"


# Vergelijkingen die iets insluiten. Een groep voorwaarden die alleen uit
# "bevat niet" bestaat, zou op zowat elke transactie passen.
INSLUITEND = ("bevat", "gelijk", "regex")


def groepen(voorwaarden: list[Voorwaarde]) -> list[list[Voorwaarde]]:
    """Deelt de voorwaarden op in groepen die met OF aan elkaar hangen.

    EN gaat voor OF, zoals in de meeste zoekmachines en in SQL: "A en B of C"
    betekent "(A en B) of C". Een regel past zodra één groep volledig klopt.
    """
    uit: list[list[Voorwaarde]] = []
    for i, vw in enumerate(voorwaarden):
        if i == 0 or vw.koppeling != "of":
            if not uit:
                uit.append([])
            uit[-1].append(vw)
        else:
            uit.append([vw])
    return uit


def fout_in_voorwaarden(voorwaarden: list[Voorwaarde]) -> str | None:
    """Geeft een reden terug als deze voorwaarden geen zinnige regel vormen."""
    if not voorwaarden:
        return "Geef minstens één voorwaarde op."
    for groep in groepen(voorwaarden):
        if not any(vw.operator in INSLUITEND for vw in groep):
            return ("Elke groep voorwaarden (wat met OF gescheiden is) heeft minstens "
                    "één voorwaarde nodig die iets insluit: bevat, is gelijk aan of "
                    "een reguliere expressie. Met alleen \"bevat niet\" past de "
                    "regel op zowat alles.")
    return None


def ordenen(voorwaarden: list[Voorwaarde]) -> list[Voorwaarde]:
    """Zet in de eerste groep een insluitende voorwaarde vooraan.

    De eerste voorwaarde van een regel staat in de regeltabel zelf, en die mag
    geen "bevat niet" zijn. Binnen één EN-groep maakt de volgorde niets uit,
    dus daar mag er geschoven worden; over OF heen niet.
    """
    if not voorwaarden or voorwaarden[0].operator in INSLUITEND:
        return list(voorwaarden)
    eerste = groepen(voorwaarden)[0]
    i = next((j for j, vw in enumerate(eerste) if vw.operator in INSLUITEND), None)
    if i is None:
        return list(voorwaarden)
    uit = list(voorwaarden)
    uit[0], uit[i] = uit[i], uit[0]
    uit[0] = Voorwaarde(uit[0].veld, uit[0].operator, uit[0].waarde, "en")
    uit[i] = Voorwaarde(uit[i].veld, uit[i].operator, uit[i].waarde, "en")
    return uit


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
    # Bijkomende voorwaarden, elk met EN of OF aan de vorige. Leeg bij een
    # gewone regel op één veld.
    extra: list[Voorwaarde] = field(default_factory=list)
    # Een bevestigde regel deelt zeker in; een onbevestigde stuurt wat ze
    # indeelt naar het nazicht.
    bevestigd: bool = True

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
            koppeling=(rij["koppeling"] if "koppeling" in rij.keys()
                       and rij["koppeling"] == "of" else "en"),
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
            bevestigd=row["bevestigd_op"] is not None,
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


def bevat(doel: str, naald: str) -> bool:
    """Staan alle woorden van de naald in het doel, in welke volgorde ook?

    "ober merelbeke" past op "ober 78 merelbeker", op "merelbeke ober" en op
    "obermerelbeke": elk woord moet ergens voorkomen, ook midden in een ander
    woord. Beide kanten zijn al genormaliseerd (kleine letters, zonder
    leestekens, één spatie tussen de woorden).
    """
    woorden = naald.split()
    return bool(woorden) and all(w in doel for w in woorden)


def _voorwaarde_past(vw: Voorwaarde, k: TransactieKenmerken) -> bool:
    """Eén vergelijking op één veld.

    `bevat` kijkt per woord: alle woorden van de waarde moeten in het veld
    staan, maar de volgorde en wat ertussen staat doen er niet toe (zie
    `bevat`). Een rekeningnummer wordt als één geheel vergeleken.

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
        return not bevat(doel, naald)
    if not doel:
        return False
    if vw.operator == "gelijk":
        return doel == naald
    if vw.operator == "bevat":
        return bevat(doel, naald)
    return False


def regel_past(regel: Regel, k: TransactieKenmerken) -> bool:
    """Past de regel op deze transactie?

    De voorwaarden vormen groepen die met OF aan elkaar hangen (zie
    `groepen`); binnen een groep moet alles kloppen. De bedragvork en de
    richting gelden voor de hele regel.
    """
    if regel.richting and regel.richting != k.richting:
        return False
    bedrag = abs(k.bedrag)
    if regel.bedrag_min is not None and bedrag < Decimal(str(regel.bedrag_min)):
        return False
    if regel.bedrag_max is not None and bedrag >= Decimal(str(regel.bedrag_max)):
        return False

    return any(all(_voorwaarde_past(vw, k) for vw in groep)
               for groep in groepen(regel.voorwaarden))


def eerste_passende(regels: list[Regel], k: TransactieKenmerken) -> Regel | None:
    """Geeft de eerste regel die past. De lijst staat op prioriteit gesorteerd."""
    for regel in regels:
        if regel_past(regel, k):
            return regel
    return None


def naar_voorstel(regel: Regel) -> Voorstel:
    omschrijving = regel.naam or f"regel #{regel.id}"
    onzeker = not regel.bevestigd
    if onzeker and regel.herkomst in ONZEKERE_HERKOMSTEN:
        uitleg = (f"{omschrijving} wees bij het afleiden naar meer dan één categorie. "
                  "Kies zelf welke hier past, of bevestig de regel.")
    elif onzeker:
        uitleg = (f"Voorgesteld door {omschrijving}. Die regel is nog niet "
                  "bevestigd; kijk de indeling na of bevestig de regel.")
    else:
        uitleg = f"Toegewezen door {omschrijving}."
    return Voorstel(
        categorie_id=regel.categorie_id,
        subcategorie_id=regel.subcategorie_id,
        subsub_id=regel.subsub_id,
        handelaar=regel.handelaar,
        land=regel.land,
        zekerheid=0.6 if onzeker else 1.0,
        methode="regel",
        status="nazicht" if onzeker else "bevestigd",
        toelichting=uitleg,
        regel_id=regel.id,
    )


# --------------------------------------------------------------------------
# Stap 2: fuzzy vergelijking met de geschiedenis
# --------------------------------------------------------------------------
#
# De gelijkenisstap vergelijkt de naam van de tegenpartij met de namen die je
# al eens zelf hebt ingedeeld. Tot versie 0.33.0 liep dat op een paar plaatsen
# mis:
#
# * de geschiedenis werd opgebouwd op de *winkel* van een transactie en niet op
#   haar tegenpartij, terwijl een nieuwe transactie op haar tegenpartij werd
#   vergeleken. Een betaling aan "ELAINE HUYGE" met winkel "Flying tiger" werd
#   zo onder "flying tiger" bewaard, en een volgende betaling aan dezelfde
#   persoon vond ze niet terug;
# * zonder naam werd de hele tekst (beschrijving, mededeling, …) vergeleken met
#   namen, wat willekeurige treffers gaf;
# * filiaal- en kaartnummers, datums en rechtsvormen ("DELHAIZE 1234 GENT",
#   "MAES NV") telden mee in de vergelijking;
# * alleen de beste treffer telde. Lagen twee verschillende namen even dicht
#   ("MAES OLSENE" en "MAES EERNEGEM") en hoorden ze bij een andere categorie,
#   dan won blind de eerste;
# * één enkele eerdere transactie volstond om automatisch te bevestigen, ook
#   als het bedrag er ver naast lag.
#
# Nu vergelijkt de stap naam met naam, zonder die ruis, weegt ze het
# rekeningnummer van de tegenpartij mee, en bevestigt ze pas zelf wanneer de
# treffer eenduidig is, op meer dan één waarneming steunt (of de naam precies
# gelijk is) en het bedrag in de lijn ligt.

@dataclass
class Referentie:
    """Eén naam uit de geschiedenis, met alles wat erover bekend is."""
    tekst: str
    richting: str | None                   # "in", "uit" of None (van een regel)
    weergave: str = ""                     # de naam zoals hij er stond, voor de uitleg
    paden: dict = field(default_factory=dict)       # pad -> aantal waarnemingen
    handelaars: dict = field(default_factory=dict)  # winkel -> aantal
    landen: dict = field(default_factory=dict)      # land -> aantal
    transacties: int = 0                   # hoeveel transacties erachter staan
    bedrag_min: Decimal | None = None
    bedrag_max: Decimal | None = None
    # Een regel die zelf nog niet bevestigd is, levert een referentie die
    # alleen mag voorstellen.
    van_onbevestigde_regel: bool = False
    van_regel: bool = False

    def voeg_toe(self, pad: tuple, handelaar: str | None, land: str | None,
                 bedrag: Decimal | None = None, gewicht: int = 1) -> None:
        self.paden[pad] = self.paden.get(pad, 0) + gewicht
        if handelaar:
            self.handelaars[handelaar] = self.handelaars.get(handelaar, 0) + 1
        if land:
            self.landen[land] = self.landen.get(land, 0) + 1
        if bedrag is not None:
            self.transacties += 1
            self.bedrag_min = bedrag if self.bedrag_min is None else min(self.bedrag_min, bedrag)
            self.bedrag_max = bedrag if self.bedrag_max is None else max(self.bedrag_max, bedrag)

    @property
    def pad(self) -> tuple:
        """Het pad dat het vaakst voorkomt."""
        return max(self.paden.items(), key=lambda p: p[1])[0]

    @property
    def eenduidig(self) -> bool:
        return len(self.paden) == 1

    @staticmethod
    def _enige(teller: dict) -> str | None:
        return next(iter(teller)) if len(teller) == 1 else None

    @property
    def handelaar(self) -> str | None:
        """De winkel, alleen als die bij deze naam altijd dezelfde was."""
        return self._enige(self.handelaars)

    @property
    def land(self) -> str | None:
        return self._enige(self.landen)


# Alleen wat een mens heeft ingedeeld, telt als geschiedenis voor de fuzzy stap:
# met de hand (manueel), uit een ingelezen historiek (bestand), of een
# voorstel dat je met *Klopt* bevestigde (nagekeken). Wat een regel of de fuzzy
# stap zelf indeelde, telt niet mee — anders veralgemeent de motor zijn eigen
# werk: een regel "Axelle Huyge én drinkgeld in de mededeling" deelde
# transacties in, die werden geschiedenis voor "Axelle Huyge", en daarna ging
# élke transactie van Axelle automatisch naar drinkgeld.
MENSELIJKE_METHODEN = ("manueel", "bestand", "ai")

# Een fuzzy treffer wordt alleen automatisch bevestigd als beide namen ongeveer
# even lang zijn. Is de ene veel korter, dan past ze gewoon binnen de andere en
# moet je het zelf nakijken. En dan alleen als het eerste woord gelijk is:
# "Delhaize" in "Delhaize Gent" is dezelfde zaak, "Huyge" in "Daniel Huyge" is
# alleen dezelfde familienaam.
MIN_LENGTEVERHOUDING = 0.67

# Liggen twee namen die bij een andere categorie horen minder dan zoveel
# punten uit elkaar, dan is de treffer niet eenduidig.
MARGE_ANDERE_CATEGORIE = 5.0

# Ligt het bedrag meer dan zoveel keer buiten wat je bij deze naam al zag, dan
# bevestigt de gelijkenisstap niet zelf.
BEDRAGFACTOR = 3

# Woorden die niets over de zaak zeggen.
RECHTSVORMEN = {"bv", "bvba", "nv", "sa", "srl", "sprl", "vzw", "asbl", "cvba", "cv",
                "scrl", "comm", "va", "gmbh", "ltd", "inc", "llc", "sas", "sarl",
                "bvbaa", "ebvba"}


def naamtekst(naam: str | None) -> str:
    """De naam zoals de gelijkenisstap hem vergelijkt.

    Genormaliseerd, en zonder woorden die vooral uit cijfers bestaan
    (filiaalnummers, kaartnummers, datums), zonder losse letters en zonder
    rechtsvormen. "DELHAIZE 1234 GENT 12/03" wordt "delhaize gent", "MAES NV"
    wordt "maes". Een naam als "2dehands" blijft staan: daar zijn de cijfers
    niet de meerderheid. Blijft er niets over, dan geldt de gewone
    genormaliseerde naam.
    """
    basis = normalize(naam)
    woorden = [w for w in basis.split()
               if len(w) > 1 and w not in RECHTSVORMEN
               and sum(c.isdigit() for c in w) * 2 <= len(w)]
    return " ".join(woorden) or basis


def _eerste_woord_gelijk(a: str, b: str) -> bool:
    """Is het eerste woord van beide namen (bijna) hetzelfde?

    Een kleine tikfout mag ("colruijt" en "colruyt"), een andere voornaam niet
    ("axelle" en "elaine").
    """
    ea, eb = a.split()[:1], b.split()[:1]
    if not ea or not eb:
        return False
    if ea[0] == eb[0] or ea[0].startswith(eb[0]) or eb[0].startswith(ea[0]):
        return True
    return _ratio(ea[0], eb[0]) >= 80


def _naam_van(k: TransactieKenmerken) -> str:
    """De naam waarop een transactie vergeleken wordt: de tegenpartij, of als
    die ontbreekt de begunstigde."""
    return naamtekst(k.tegenpartij_naam) or naamtekst(k.begunstigde)


def bouw_geschiedenis(conn, crypto, regels: list["Regel"] | None = None,
                      limiet: int = 8000) -> tuple[list[Referentie], dict]:
    """Verzamelt vergelijkingsmateriaal voor de fuzzy stap.

    Geeft de referenties terug, en per (rekeningnummer, richting) welke
    categorieën je bij dat rekeningnummer al gebruikte.

    Twee bronnen:

    * transacties die een mens heeft ingedeeld (zie MENSELIJKE_METHODEN) of
      waarvan hij het voorstel met *Klopt* goedkeurde (`nagekeken`), op de
      naam van hun tegenpartij;
    * regels die enkel op de naam van de tegenpartij (of de gecombineerde
      sleutel) werken. Een regel met bijkomende voorwaarden of een bedragvork
      doet niet mee: de fuzzy stap vergelijkt alleen namen, en zou zo'n regel
      dus ruimer toepassen dan hij bedoeld is.
    """
    verzameld: dict[tuple, Referentie] = {}
    per_iban: dict[tuple, dict] = {}

    def referentie(tekst: str, richting: str | None, weergave: str = "") -> Referentie:
        sleutel = (tekst, richting)
        ref = verzameld.get(sleutel)
        if ref is None:
            ref = verzameld[sleutel] = Referentie(
                tekst=tekst, richting=richting, weergave=" ".join(weergave.split()))
        return ref

    plaatsen = ",".join("?" * len(MENSELIJKE_METHODEN))
    rows = conn.execute(
        "SELECT tegenpartij_naam_enc, begunstigde_enc, tegenpartij_rek_enc,"
        " handelaar_enc, land_enc, bedrag_enc, richting,"
        " categorie_id, subcategorie_id, subsub_id"
        " FROM transacties WHERE status='bevestigd' AND categorie_id IS NOT NULL"
        " AND is_afrekening = 0"
        f" AND (methode IN ({plaatsen}) OR nagekeken = 1)"
        " ORDER BY id DESC LIMIT ?",
        (*MENSELIJKE_METHODEN, limiet),
    ).fetchall()
    for row in rows:
        pad = (row["categorie_id"], row["subcategorie_id"], row["subsub_id"])
        ruw = (crypto.dec(row["tegenpartij_naam_enc"]) or ""
               or crypto.dec(row["begunstigde_enc"]) or "")
        tekst = naamtekst(ruw)
        if tekst:
            referentie(tekst, row["richting"], ruw).voeg_toe(
                pad, crypto.dec(row["handelaar_enc"]), crypto.dec(row["land_enc"]),
                abs(crypto.dec_amount(row["bedrag_enc"])), gewicht=2)
        iban = normalize_iban(crypto.dec(row["tegenpartij_rek_enc"]))
        if len(iban) >= 8:
            teller = per_iban.setdefault((iban, row["richting"]), {})
            teller[pad] = teller.get(pad, 0) + 1

    for regel in (regels or []):
        if regel.categorie_id is None:
            continue
        if regel.extra or regel.bedrag_min is not None or regel.bedrag_max is not None:
            continue
        if regel.veld == "sleutel":
            # Alleen het tegenpartijdeel is bruikbaar om op te vergelijken.
            tekst = naamtekst(regel.waarde.split("-", 1)[-1])
        elif regel.veld == "tegenpartij_naam":
            tekst = naamtekst(regel.waarde)
        else:
            continue
        if not tekst:
            continue
        ref = referentie(tekst, regel.richting, regel.waarde)
        ref.voeg_toe((regel.categorie_id, regel.subcategorie_id, regel.subsub_id),
                     regel.handelaar, regel.land)
        ref.van_regel = True
        if not regel.bevestigd:
            ref.van_onbevestigde_regel = True

    return sorted(verzameld.values(), key=lambda r: -sum(r.paden.values())), per_iban


def fuzzy_voorstel(referenties: list[Referentie], teksten: list[str],
                   k: TransactieKenmerken, auto_drempel: float,
                   suggestie_drempel: float,
                   per_iban: dict | None = None) -> Voorstel | None:
    """Zoekt de meest gelijkende naam en bepaalt hoe zeker dat is."""
    doel = _naam_van(k)
    iban = normalize_iban(k.tegenpartij_rekening)
    iban_paden = (per_iban or {}).get((iban, k.richting)) if len(iban) >= 8 else None
    iban_pad = next(iter(iban_paden)) if iban_paden and len(iban_paden) == 1 else None

    geldig: list[tuple[Referentie, float, bool]] = []
    if doel and teksten:
        for index, score in _besten(doel, teksten, suggestie_drempel, aantal=12):
            ref = referenties[index]
            lengtes = sorted((len(doel), len(ref.tekst)))
            gedeeltelijk = bool(lengtes[1]) and lengtes[0] / lengtes[1] < MIN_LENGTEVERHOUDING
            if not _eerste_woord_gelijk(doel, ref.tekst):
                # Het eerste woord verschilt: dan is het gedeelde stuk meestal
                # een familienaam ("Huyge" in "Axelle Huyge" en "Elaine
                # Huyge"), en dat zegt niets. Bij een winkel is het gedeelde
                # stuk net het eerste woord ("Delhaize" in "Delhaize Gent").
                continue
            geldig.append((ref, score, gedeeltelijk))

    if not geldig:
        if iban_pad is None:
            return None
        # Geen gelijkende naam, maar wel een rekeningnummer dat je altijd
        # onder dezelfde categorie indeelde. Een voorstel, geen bevestiging:
        # één rekeningnummer kan ook bij een betaalverwerker horen.
        return Voorstel(
            categorie_id=iban_pad[0], subcategorie_id=iban_pad[1], subsub_id=iban_pad[2],
            zekerheid=0.75, methode="fuzzy", status="nazicht",
            toelichting=("Zelfde rekeningnummer van de tegenpartij als eerdere "
                         "transacties die je zo indeelde. Nakijken voor bevestiging."),
        )

    ref, score, gedeeltelijk = max(geldig, key=lambda t: t[1])
    pad = ref.pad
    naam = ref.weergave or ref.tekst
    twijfel: list[str] = []

    if not ref.eenduidig:
        twijfel.append(f"{naam} komt in je geschiedenis onder meer dan één categorie voor")
    if ref.van_onbevestigde_regel:
        twijfel.append(f"{naam} komt uit een regel die nog niet bevestigd is")
    # Een andere naam die bijna even goed lijkt, maar elders thuishoort.
    for ander, ander_score, _ in geldig:
        if ander is ref or ander.pad == pad:
            continue
        if ander_score >= score - MARGE_ANDERE_CATEGORIE:
            twijfel.append(f"{ander.weergave or ander.tekst} lijkt even goed en "
                           "hoort bij een andere categorie")
            break
    if iban_paden and pad not in iban_paden:
        twijfel.append("het rekeningnummer van de tegenpartij hoorde eerder bij een "
                       "andere categorie")

    bedrag = abs(k.bedrag)
    bedrag_wijkt_af = (ref.transacties >= 2 and ref.bedrag_min is not None and bedrag > 0
                       and (bedrag > ref.bedrag_max * BEDRAGFACTOR
                            or bedrag * BEDRAGFACTOR < ref.bedrag_min))

    # Herhaalde waarnemingen en een passend rekeningnummer wegen licht door.
    score = min(100.0, score + min(sum(ref.paden.values()), 10) * 0.3
                + (3.0 if iban_pad == pad else 0.0))
    zeker = score / 100.0
    genoeg_bewijs = ref.transacties >= 2 or ref.van_regel or score >= 99 or iban_pad == pad

    if twijfel:
        return Voorstel(
            categorie_id=pad[0], subcategorie_id=pad[1], subsub_id=pad[2],
            handelaar=ref.handelaar, land=ref.land,
            zekerheid=round(min(zeker, 0.6), 3), methode="fuzzy", status="nazicht",
            toelichting=(f"Gelijkenis ({score:.0f}%) met {naam}, maar "
                         + "; ".join(twijfel) + ". Kies zelf welke categorie hier past."),
        )
    if (score >= auto_drempel and not gedeeltelijk and not bedrag_wijkt_af
            and genoeg_bewijs):
        return Voorstel(
            categorie_id=pad[0], subcategorie_id=pad[1], subsub_id=pad[2],
            handelaar=ref.handelaar, land=ref.land,
            zekerheid=round(zeker, 3), methode="fuzzy", status="bevestigd",
            toelichting=f"Sterke gelijkenis ({score:.0f}%) met {naam}.",
        )
    reden = ""
    if bedrag_wijkt_af:
        reden = (f" Het bedrag wijkt sterk af van wat je bij {naam} gewoonlijk "
                 f"betaalt ({ref.bedrag_min:.2f} tot {ref.bedrag_max:.2f}).")
    elif score >= auto_drempel and not genoeg_bewijs:
        reden = " Er is maar één eerdere transactie om op te steunen."
    return Voorstel(
        categorie_id=pad[0], subcategorie_id=pad[1], subsub_id=pad[2],
        handelaar=ref.handelaar, land=ref.land,
        zekerheid=round(zeker, 3), methode="fuzzy", status="nazicht",
        toelichting=(f"Vermoedelijke match ({score:.0f}%) met {naam}."
                     + reden + " Nakijken voor bevestiging."),
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
        # Per (veld, waarde) alle exacte regels, op prioriteit. Een lijst en
        # geen enkele regel: dezelfde waarde kan een regel voor uitgaven en een
        # voor inkomsten hebben, en die tweede viel vroeger weg.
        self.exact: dict[tuple[str, str], list[Regel]] = {}
        self.los: list[Regel] = []
        for regel in self.regels:
            if regel.operator == "gelijk" and not regel.extra \
                    and regel.bedrag_min is None and regel.bedrag_max is None \
                    and regel.veld in ("sleutel", "beschrijving", "tegenpartij_naam",
                                       "tegenpartij_rekening", "mededeling"):
                sleutel = (regel.veld,
                           normalize_iban(regel.waarde)
                           if regel.veld == "tegenpartij_rekening"
                           else normalize(regel.waarde))
                self.exact.setdefault(sleutel, []).append(regel)
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
                              normalize_iban(k.tegenpartij_rekening)),
                             ("mededeling", normalize(k.mededeling))):
            if not waarde:
                continue
            regel = next((r for r in self.exact.get((veld, waarde), ())
                          if r.richting is None or r.richting == k.richting), None)
            if regel is not None:
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

        self.geschiedenis, self.per_iban = bouw_geschiedenis(conn, crypto, self.regels)
        self._verdeel()
        self.auto_drempel = float(instelling(conn, "fuzzy_auto_drempel", "92"))
        self.suggestie_drempel = float(instelling(conn, "fuzzy_suggestie_drempel", "72"))

    def beoordeel(self, k: TransactieKenmerken) -> Voorstel:
        """Zoekt de best passende regel en valt anders terug op de fuzzy stap."""
        beste = self.regelboek.beste(k)
        if beste is not None:
            return naar_voorstel(beste)

        refs, teksten = self.per_richting.get(k.richting, ([], []))
        voorstel = fuzzy_voorstel(refs, teksten, k, self.auto_drempel,
                                  self.suggestie_drempel, self.per_iban)
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
        self.index = {(r.tekst, r.richting): r for r in self.geschiedenis}
        self.per_richting = {}
        for richting in ("in", "uit"):
            refs = [r for r in self.geschiedenis if r.richting in (richting, None)]
            self.per_richting[richting] = (refs, [r.tekst for r in refs])

    def onthoud(self, k: TransactieKenmerken, voorstel: Voorstel) -> None:
        """Voegt een indeling tijdens een invoer toe aan het vergelijkingsmateriaal.

        Alleen als ze van een mens komt (een ingelezen historiek met categorie).
        Wat de motor zelf net indeelde, mag de volgende rij van dezelfde invoer
        niet sturen — anders versterkt één gok zichzelf over het hele bestand.

        Bijwerken gebeurt ter plaatse: bij een historiek van duizenden rijen
        werd vroeger na elke rij de hele lijst opnieuw opgebouwd.
        """
        if (not voorstel.gevonden or voorstel.status != "bevestigd"
                or voorstel.methode not in MENSELIJKE_METHODEN):
            return
        pad = (voorstel.categorie_id, voorstel.subcategorie_id, voorstel.subsub_id)
        iban = normalize_iban(k.tegenpartij_rekening)
        if len(iban) >= 8:
            teller = self.per_iban.setdefault((iban, k.richting), {})
            teller[pad] = teller.get(pad, 0) + 1
        tekst = _naam_van(k)
        if not tekst:
            return
        ref = self.index.get((tekst, k.richting))
        if ref is None:
            ref = Referentie(tekst=tekst, richting=k.richting,
                             weergave=" ".join((k.tegenpartij_naam or k.begunstigde).split()))
            self.index[(tekst, k.richting)] = ref
            self.geschiedenis.append(ref)
            refs, teksten = self.per_richting[k.richting]
            refs.append(ref)
            teksten.append(tekst)
        ref.voeg_toe(pad, voorstel.handelaar, voorstel.land, abs(k.bedrag), gewicht=2)
