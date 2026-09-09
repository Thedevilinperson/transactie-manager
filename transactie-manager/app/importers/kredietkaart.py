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
from datetime import date, datetime
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
    totaal = re.search(
        r"(?:totaal te betalen|te betalen|nieuw saldo|totaal|total|montant)"
        r"\D{0,40}?" + BEDRAG,
        "\n".join(regels), re.IGNORECASE)
    if totaal:
        gegevens["totaal"] = _parse_bedrag(totaal.group("bedrag"), None)
    return gegevens


def ontleed(regels: list[str], patroon: str = "automatisch") -> Uittreksel:
    """Ontleedt de tekstregels tot een uittreksel met aankopen."""
    kop = _kop(regels)
    uittreksel = Uittreksel(
        kaart=kop["kaart"], periode=kop["periode"], totaal=kop["totaal"],
        alle_regels=regels,
    )

    namen = [patroon] if patroon in PATRONEN else list(PATRONEN)
    beste_naam, beste_resultaat, beste_score = "", [], -1

    for naam in namen:
        samengesteld = re.compile(PATRONEN[naam])
        resultaat: list[PdfRegel] = []
        score = 0
        for nummer, tekst in enumerate(regels, start=1):
            item = PdfRegel(nummer=nummer, tekst=tekst)
            if not OVERSLAAN.match(tekst.strip()):
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

AFREKENING = re.compile(
    r"\b(bcc|mastercard|master card|visa|kredietkaart|creditcard|amex|"
    r"american express)\b", re.IGNORECASE)


def is_afrekeningsregel(beschrijving: str, tegenpartij: str) -> bool:
    """Herkent de maandelijkse kaartafrekening op het bankafschrift."""
    return bool(AFREKENING.search(f"{beschrijving} {tegenpartij}"))


def zoek_afrekeningen(conn, crypto, van: date | None = None, tot: date | None = None,
                      limiet: int = 60) -> list[dict]:
    """Kandidaat-afrekeningen om een PDF aan te hangen."""
    from ..transacties import rij_naar_object

    sql = ("SELECT * FROM transacties WHERE richting='uit' AND ouder_tx_id IS NULL"
           " ORDER BY boekdatum DESC LIMIT 600")
    kandidaten = []
    for row in conn.execute(sql):
        tx = rij_naar_object(row, crypto)
        if not is_afrekeningsregel(tx.beschrijving, tx.tegenpartij_naam):
            continue
        if van and tx.boekdatum < van.isoformat():
            continue
        if tot and tx.boekdatum > tot.isoformat():
            continue
        aantal = conn.execute(
            "SELECT COUNT(*) n FROM transacties WHERE ouder_tx_id = ?", (tx.id,)
        ).fetchone()["n"]
        kandidaten.append({
            "id": tx.id, "boekdatum": tx.boekdatum, "bedrag": tx.bedrag,
            "omschrijving": f"{tx.beschrijving} — {tx.tegenpartij_naam}".strip(" —"),
            "aantal_kinderen": aantal, "is_afrekening": tx.is_afrekening,
        })
        if len(kandidaten) >= limiet:
            break
    return kandidaten
