"""Kredietkaartuittreksels in PDF omzetten naar transacties.

Waarom deze aanpak
------------------
Uittreksels van Mastercard en Visa (bij ons via BCC) zijn PDF's met een echte
tekstlaag; het zijn geen scans. Tekst uitlezen is dus voldoende en veel
betrouwbaarder dan tekenherkenning. We gebruiken `pdfplumber`, omdat dat de
woorden per regel teruggeeft met hun plaats op de bladzijde. Daardoor blijven
kolommen die met spaties uitgelijnd zijn overeind, wat met platte
tekstextractie vaak misloopt. Valt `pdfplumber` weg, dan is er een terugval op
`pypdf`.

Tekenherkenning zit er bewust niet in: dat vraagt zware pakketten die op een
Raspberry Pi nauwelijks te installeren zijn, en het zou de nauwkeurigheid van
bedragen verlagen. Levert een PDF geen tekst op, dan meldt de module dat het om
een scan gaat in plaats van er een gok van te maken.

Hoe het aansluit op de bankafschriften
--------------------------------------
Op het bankafschrift staat de maandelijkse afrekening als één regel, meestal
"Debet ten voordele van BCC" met de kaartreferentie erbij. Die regel wordt
gemarkeerd als afrekening en telt niet mee in de overzichten. De aankopen uit
de PDF komen eronder te hangen als losse transacties, elk met hun eigen
categorie. Zo verschijnt het bedrag maar één keer in de cijfers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path


class PdfFout(RuntimeError):
    pass


@dataclass
class PdfRegel:
    """Eén tekstregel uit de PDF, met wat de ontleding erin herkend heeft."""
    nummer: int
    tekst: str
    datum: date | None = None
    omschrijving: str = ""
    bedrag: Decimal | None = None
    munt: str = "EUR"
    origineel_bedrag: str = ""
    herkend: bool = False


@dataclass
class Uittreksel:
    kaart: str = ""
    kaarthouder: str = ""
    periode: str = ""
    totaal: Decimal | None = None
    totaal_regel: str = ""
    vervaldag: date | None = None
    regels: list[PdfRegel] = field(default_factory=list)
    alle_regels: list[str] = field(default_factory=list)
    patroon: str = ""

    @property
    def herkende(self) -> list[PdfRegel]:
        return [r for r in self.regels if r.herkend]

    @property
    def som(self) -> Decimal:
        return sum((r.bedrag for r in self.herkende if r.bedrag), Decimal("0"))


# --------------------------------------------------------------------------
# Tekst uit de PDF halen
# --------------------------------------------------------------------------

def haal_regels(pad: Path) -> list[str]:
    """Geeft de tekstregels van alle bladzijden terug."""
    regels: list[str] = []
    try:
        import pdfplumber

        with pdfplumber.open(pad) as pdf:
            for bladzijde in pdf.pages:
                tekst = bladzijde.extract_text(x_tolerance=1.5, y_tolerance=3) or ""
                regels.extend(tekst.splitlines())
    except ImportError:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise PdfFout(
                "Er is geen PDF-bibliotheek beschikbaar. Installeer pdfplumber."
            ) from exc
        lezer = PdfReader(str(pad))
        for bladzijde in lezer.pages:
            regels.extend((bladzijde.extract_text() or "").splitlines())
    except Exception as exc:  # noqa: BLE001
        raise PdfFout(f"De PDF kon niet gelezen worden: {exc}") from exc

    opgekuist = [r.rstrip() for r in regels if r and r.strip()]
    if not opgekuist:
        raise PdfFout(
            "Deze PDF bevat geen tekst. Waarschijnlijk is het een scan of een "
            "afbeelding. Vraag bij je kaartuitgever een uittreksel met tekst op, "
            "of voer de aankopen met de hand in."
        )
    return opgekuist


# --------------------------------------------------------------------------
# Regels ontleden
# --------------------------------------------------------------------------

# Bedragen zoals 1.234,56 of 1234,56 of -12,50, eventueel met CR/- erachter.
BEDRAG = r"(?P<bedrag>-?\d{1,3}(?:[.\s]\d{3})*,\d{2}|-?\d+,\d{2}|-?\d+\.\d{2})"
TEKEN = r"(?P<teken>\s*(?:CR|C|\-|\+))?"

# Verschillende opmaken die bij kaartuittreksels voorkomen. Ze worden op
# volgorde geprobeerd; het patroon dat de meeste regels verklaart, wint.
PATRONEN: dict[str, str] = {
    "datum_datum_tekst_bedrag":
        r"^(?P<datum>\d{2}[/.-]\d{2}(?:[/.-]\d{2,4})?)\s+"
        r"\d{2}[/.-]\d{2}(?:[/.-]\d{2,4})?\s+"
        r"(?P<omschrijving>.+?)\s+" + BEDRAG + TEKEN + r"\s*$",
    "datum_tekst_bedrag":
        r"^(?P<datum>\d{2}[/.-]\d{2}(?:[/.-]\d{2,4})?)\s+"
        r"(?P<omschrijving>.+?)\s+" + BEDRAG + TEKEN + r"\s*$",
    "tekst_datum_bedrag":
        r"^(?P<omschrijving>.+?)\s+(?P<datum>\d{2}[/.-]\d{2}[/.-]\d{2,4})\s+"
        + BEDRAG + TEKEN + r"\s*$",
    "datum_iso_tekst_bedrag":
        r"^(?P<datum>\d{4}-\d{2}-\d{2})\s+(?P<omschrijving>.+?)\s+"
        + BEDRAG + TEKEN + r"\s*$",
}

# Regels die nooit een aankoop zijn.
OVERSLAAN = re.compile(
    r"^(totaal|total|te betalen|saldo|vorig saldo|overdracht|subtotaal|"
    r"betaling ontvangen|domiciliëring|domiciliering|bladzijde|pagina|"
    r"kaartnummer|card number|iban|bic|btw|tva)\b",
    re.IGNORECASE,
)

# Bedrag in vreemde munt, bijvoorbeeld "USD 45,00" of "45,00 GBP".
VREEMDE_MUNT = re.compile(r"\b([A-Z]{3})\s*\d[\d.,\s]*|\b\d[\d.,\s]*\s*([A-Z]{3})\b")


def _parse_bedrag(tekst: str, teken: str | None) -> Decimal | None:
    schoon = tekst.replace(" ", "")
    if "," in schoon:
        schoon = schoon.replace(".", "").replace(",", ".")
    try:
        bedrag = Decimal(schoon)
    except InvalidOperation:
        return None
    # Op een kaartuittreksel is alles een uitgave, behalve wat als krediet
    # gemarkeerd staat.
    if teken and teken.strip().upper() in ("CR", "C", "+"):
        return abs(bedrag)
    return -abs(bedrag)


def _parse_datum(tekst: str, jaar: int | None) -> date | None:
    tekst = tekst.strip()
    for opmaak in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y",
                   "%Y-%m-%d"):
        try:
            return datetime.strptime(tekst, opmaak).date()
        except ValueError:
            continue
    # Dag en maand zonder jaartal: het jaar uit de kop van het uittreksel.
    for opmaak in ("%d/%m", "%d-%m", "%d.%m"):
        try:
            gedeeltelijk = datetime.strptime(tekst, opmaak)
            return date(jaar or date.today().year, gedeeltelijk.month, gedeeltelijk.day)
        except ValueError:
            continue
    return None


def _kop(regels: list[str]) -> dict:
    """Haalt kaart, houder, periode en totaal uit de eerste bladzijde."""
    gegevens: dict = {"kaart": "", "kaarthouder": "", "periode": "",
                      "totaal": None, "jaar": None}
    kop = "\n".join(regels[:40])

    kaart = re.search(r"\b((?:\d{4}[\s*Xx.-]{1,4}){3}\d{3,4}|[X*]{4,}\s*\d{3,4})", kop)
    if kaart:
        gegevens["kaart"] = kaart.group(1).strip()
    soort = re.search(r"\b(mastercard|visa|american express|amex)\b", kop, re.IGNORECASE)
    if soort:
        gegevens["kaart"] = (soort.group(1).title() + " " + gegevens["kaart"]).strip()

    periode = re.search(
        r"(\d{2}[/.-]\d{2}[/.-]\d{2,4})\s*(?:tot|t/m|-|tot en met|au)\s*"
        r"(\d{2}[/.-]\d{2}[/.-]\d{2,4})", kop, re.IGNORECASE)
    if periode:
        gegevens["periode"] = f"{periode.group(1)} tot {periode.group(2)}"

    jaar = re.search(r"\b(20\d{2})\b", kop)
    if jaar:
        gegevens["jaar"] = int(jaar.group(1))

    # Het totaal staat soms bovenaan, soms onderaan het uittreksel.
    gegevens.update(_totaal(regels))
    return gegevens


# Het saldo van vorige maand staat op elke afrekening naast dat van deze maand.
# Alles wat naar de vorige periode verwijst, mag dus nooit als totaal gelden.
VORIGE_PERIODE = re.compile(
    r"\b(vorig|vorige|voorgaand|previous|ancien|overdracht|overgedragen|"
    r"reeds betaald|betaling ontvangen|betalingen ontvangen|terugbetaling)\b",
    re.IGNORECASE)

# Van sterk naar zwak: het label dat het duidelijkst "dit is wat je nu betaalt"
# zegt, wint.
TOTAALLABELS = [
    (r"totaal te betalen", 100),
    (r"nieuw saldo", 95),
    (r"saldo nieuw", 95),
    (r"nieuw te betalen", 95),
    (r"te betalen bedrag", 90),
    (r"montant (?:total )?(?:à|a) payer", 90),
    (r"\bte betalen\b", 80),
    (r"totaal van de verrichtingen", 60),
    (r"\btotaal\b", 50),
    (r"\btotal\b", 50),
]


def _totaal(regels: list[str]) -> dict:
    """Zoekt het bedrag dat deze maand betaald moet worden.

    Op een kaartafrekening staan meerdere totalen door elkaar: het saldo van
    vorige maand, wat je intussen betaald hebt, en het nieuwe te betalen bedrag.
    Het eerste bedrag dat op een totaal lijkt, is dus vaak het verkeerde. We
    bekijken alle regels, gooien weg wat naar de vorige periode verwijst, en
    houden het sterkste label over.
    """
    bedrag_zoeker = re.compile(BEDRAG + TEKEN)
    beste = None

    for regel in regels:
        tekst = regel.strip()
        if not tekst or VORIGE_PERIODE.search(tekst):
            continue
        treffer = bedrag_zoeker.search(tekst)
        if treffer is None:
            continue
        for patroon, gewicht in TOTAALLABELS:
            if re.search(patroon, tekst, re.IGNORECASE):
                if beste is None or gewicht > beste[0]:
                    bedrag = _parse_bedrag(treffer.group("bedrag"),
                                           treffer.groupdict().get("teken"))
                    if bedrag is not None:
                        beste = (gewicht, abs(bedrag), tekst)
                break

    if beste is None:
        return {"totaal": None, "totaal_regel": ""}
    return {"totaal": beste[1], "totaal_regel": beste[2][:120]}


def ontleed(regels: list[str], patroon: str = "automatisch") -> Uittreksel:
    """Ontleedt de tekstregels tot een uittreksel met aankopen."""
    kop = _kop(regels)
    uittreksel = Uittreksel(
        kaart=kop["kaart"], periode=kop["periode"], totaal=kop["totaal"],
        totaal_regel=kop.get("totaal_regel", ""), alle_regels=regels,
    )

    namen = [patroon] if patroon in PATRONEN else list(PATRONEN)
    beste_naam, beste_resultaat, beste_score = "", [], -1

    for naam in namen:
        samengesteld = re.compile(PATRONEN[naam])
        resultaat: list[PdfRegel] = []
        score = 0
        for nummer, tekst in enumerate(regels, start=1):
            item = PdfRegel(nummer=nummer, tekst=tekst)
            if not OVERSLAAN.match(tekst.strip()) and not VORIGE_PERIODE.search(tekst):
                treffer = samengesteld.match(tekst.strip())
                if treffer:
                    bedrag = _parse_bedrag(treffer.group("bedrag"),
                                           treffer.groupdict().get("teken"))
                    datum = _parse_datum(treffer.group("datum"), kop["jaar"])
                    omschrijving = re.sub(r"\s{2,}", "  ",
                                          treffer.group("omschrijving").strip())
                    if bedrag is not None and datum is not None and omschrijving:
                        item.datum = datum
                        item.bedrag = bedrag
                        item.omschrijving = omschrijving
                        item.herkend = True
                        score += 1
                        vreemde = VREEMDE_MUNT.search(omschrijving)
                        if vreemde:
                            item.origineel_bedrag = vreemde.group(0).strip()
                            item.munt = (vreemde.group(1) or vreemde.group(2) or "EUR")
            resultaat.append(item)
        if score > beste_score:
            beste_naam, beste_resultaat, beste_score = naam, resultaat, score

    uittreksel.regels = beste_resultaat
    uittreksel.patroon = beste_naam
    return uittreksel


def lees_pdf(pad: Path, patroon: str = "automatisch") -> Uittreksel:
    return ontleed(haal_regels(pad), patroon)


# --------------------------------------------------------------------------
# Koppelen aan de afrekening op het bankafschrift
# --------------------------------------------------------------------------

# De maandafrekening ziet er bij Argenta uit als "Debet ten voordele van BCC"
# met de kaartreferentie erachter. Het is die ene regel waarmee de bank de hele
# maand in één keer verrekent.
AFREKENING = re.compile(
    r"(debet ten voordele van\s+(bcc|mastercard|visa)"
    r"|afrekening\s+(kredietkaart|creditcard|mastercard|visa)"
    r"|betaling\s+kredietkaart"
    r"|\b(bcc|kredietkaart|creditcard)\b)",
    re.IGNORECASE)

# Een betaling met een debetkaart is geen kredietkaartverrichting: het bedrag
# gaat meteen van de rekening en staat dus al als gewone uitgave op het
# afschrift. "Mastercard Debit" en "Maestro" horen hier bij, ondanks de naam van
# het kaartmerk in de omschrijving.
DEBETKAART = re.compile(
    r"\b(debit|debet ?kaart|debetkaart|maestro|bancontact|vpay|v ?pay)\b",
    re.IGNORECASE)


def is_afrekeningsregel(beschrijving: str, tegenpartij: str) -> bool:
    """Herkent de maandelijkse kaartafrekening op het bankafschrift.

    Betalingen met een debetkaart worden uitgesloten, ook wanneer er
    "Mastercard" of "Visa" in de omschrijving staat. Die staan al als gewone
    uitgave op het afschrift en mogen niet nog eens uitgesplitst worden.
    """
    tekst = f"{beschrijving} {tegenpartij}"
    if DEBETKAART.search(tekst):
        return False
    return bool(AFREKENING.search(tekst))


def afrekeningsjaren(afrekeningen: list[dict]) -> list[int]:
    """De jaren waarin er kaartafrekeningen staan.

    Neemt de lijst die je toch al hebt. Vroeger deed deze functie er een eigen
    zoekopdracht voor, waardoor het scherm alles twee keer doorliep.
    """
    return sorted({int(a["boekdatum"][:4]) for a in afrekeningen}, reverse=True)


def zoek_afrekeningen(conn, crypto, jaar: int | None = None,
                      limiet: int = 2000) -> list[dict]:
    """Kandidaat-afrekeningen om een PDF aan te hangen.

    Of een regel een afrekening is, blijkt uit de beschrijving en de naam van de
    tegenpartij, en die staan versleuteld. Daar valt niet met SQL op voor te
    selecteren. Vroeger werd daarom bij elk bezoek élke uitgave ontsleuteld; op
    tienduizenden rijen liep dat op tot seconden, en het scherm deed dat twee
    keer per keer.

    Het oordeel wordt nu bewaard in de kolom `kaartafrekening`: NULL is "nog
    niet bekeken", 0 en 1 zijn het antwoord. Alleen wat nog op NULL staat wordt
    ontsleuteld, dus de eerste keer duurt het één keer zo lang als vroeger en
    daarna niet meer. Nieuwe transacties komen als NULL binnen en worden bij het
    volgende bezoek meegenomen.
    """
    sql = ("SELECT id, boekdatum, bedrag_enc, beschrijving_enc,"
           " tegenpartij_naam_enc, is_afrekening, tegenboeking_tx_id,"
           " kaartafrekening FROM transacties"
           " WHERE richting = 'uit' AND ouder_tx_id IS NULL"
           " AND (kaartafrekening IS NULL OR kaartafrekening = 1)")
    params: list = []
    if jaar:
        sql += " AND substr(boekdatum, 1, 4) = ?"
        params.append(str(jaar))
    sql += " ORDER BY boekdatum DESC"

    kinderen = {
        rij["ouder_tx_id"]: rij["n"] for rij in conn.execute(
            "SELECT ouder_tx_id, COUNT(*) n FROM transacties"
            " WHERE ouder_tx_id IS NOT NULL GROUP BY ouder_tx_id")
    }

    kandidaten: list[dict] = []
    geoordeeld: list[tuple] = []
    for row in conn.execute(sql, params):
        beschrijving = crypto.dec(row["beschrijving_enc"]) or ""
        tegenpartij = crypto.dec(row["tegenpartij_naam_enc"]) or ""
        afrekening = is_afrekeningsregel(beschrijving, tegenpartij)
        if row["kaartafrekening"] is None:
            geoordeeld.append((1 if afrekening else 0, row["id"]))
        if not afrekening:
            continue
        kandidaten.append({
            "id": row["id"],
            "boekdatum": row["boekdatum"],
            "bedrag": crypto.dec_amount(row["bedrag_enc"]),
            "omschrijving": f"{beschrijving} — {tegenpartij}".strip(" —"),
            "aantal_kinderen": kinderen.get(row["id"], 0),
            "is_afrekening": bool(row["is_afrekening"]),
            "tegenboeking_tx_id": row["tegenboeking_tx_id"],
        })
        if len(kandidaten) >= limiet:
            break

    if geoordeeld:
        conn.executemany("UPDATE transacties SET kaartafrekening = ? WHERE id = ?",
                         geoordeeld)
        conn.commit()
    return kandidaten


# --------------------------------------------------------------------------
# Tegenboekingen
# --------------------------------------------------------------------------

# Hoeveel dagen een tegenboeking van haar afrekening mag afliggen. Een
# terugstorting of een correctie komt doorgaans binnen enkele dagen; ruimer
# maken vergroot de kans dat een toevallig gelijk bedrag wordt aangezien voor
# een tegenboeking.
VENSTER_DAGEN = 10


def _datum(tekst: str) -> date | None:
    try:
        return date.fromisoformat(tekst[:10])
    except (TypeError, ValueError):
        return None


def zoek_tegenboekingen(conn, crypto, afrekening_id: int,
                        venster: int = VENSTER_DAGEN) -> list[dict]:
    """Boekingen die deze afrekening kunnen tegenboeken.

    Een tegenboeking staat op dezelfde rekening, heeft hetzelfde bedrag met het
    tegengestelde teken, ligt dicht in de tijd, en hangt nog nergens aan. Het
    bedrag staat versleuteld, dus de vergelijking gebeurt na het ontsleutelen —
    daarom wordt eerst op rekening en datum voorgeselecteerd.
    """
    afrekening = conn.execute(
        "SELECT id, rekening_id, boekdatum, bedrag_enc FROM transacties WHERE id = ?",
        (afrekening_id,)).fetchone()
    if afrekening is None:
        return []
    dag = _datum(afrekening["boekdatum"])
    if dag is None:
        return []
    doelbedrag = -crypto.dec_amount(afrekening["bedrag_enc"])

    al_gebruikt = {
        rij["tegenboeking_tx_id"] for rij in conn.execute(
            "SELECT tegenboeking_tx_id FROM transacties"
            " WHERE tegenboeking_tx_id IS NOT NULL")
    }

    gevonden = []
    for row in conn.execute(
        "SELECT id, boekdatum, bedrag_enc, beschrijving_enc, tegenpartij_naam_enc"
        " FROM transacties WHERE rekening_id = ? AND id <> ?"
        " AND is_afrekening = 0 AND ouder_tx_id IS NULL"
        " AND boekdatum BETWEEN ? AND ? ORDER BY boekdatum",
        (afrekening["rekening_id"], afrekening_id,
         (dag - timedelta(days=venster)).isoformat(),
         (dag + timedelta(days=venster)).isoformat()),
    ):
        if row["id"] in al_gebruikt:
            continue
        if crypto.dec_amount(row["bedrag_enc"]) != doelbedrag:
            continue
        beschrijving = crypto.dec(row["beschrijving_enc"]) or ""
        tegenpartij = crypto.dec(row["tegenpartij_naam_enc"]) or ""
        gevonden.append({
            "id": row["id"],
            "boekdatum": row["boekdatum"],
            "bedrag": crypto.dec_amount(row["bedrag_enc"]),
            "omschrijving": (f"{beschrijving} — {tegenpartij}".strip(" —")
                             or "(geen omschrijving)"),
        })
    return gevonden


def koppel_tegenboekingen(conn, crypto, venster: int = VENSTER_DAGEN) -> int:
    """Hangt elke open afrekening aan haar tegenboeking, als die eenduidig is.

    Alleen wanneer er précies één kandidaat is. Zijn er meerdere, dan is het een
    keuze en geen vaststelling; die laat de toepassing aan jou.
    """
    gekoppeld = 0
    for kandidaat in zoek_afrekeningen(conn, crypto):
        if kandidaat["is_afrekening"] or kandidaat.get("tegenboeking_tx_id"):
            continue
        mogelijk = zoek_tegenboekingen(conn, crypto, kandidaat["id"], venster)
        if len(mogelijk) != 1:
            continue
        conn.execute("UPDATE transacties SET tegenboeking_tx_id = ? WHERE id = ?",
                     (mogelijk[0]["id"], kandidaat["id"]))
        gekoppeld += 1
    return gekoppeld
