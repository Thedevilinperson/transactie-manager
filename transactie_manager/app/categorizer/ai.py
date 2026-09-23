"""Stap 3: voorstel door een lokaal AI-model.

Er wordt gepraat met een Ollama-server (of een compatibele server met hetzelfde
`/api/chat`-eindpunt). Een klein lokaal model (7B) kent jouw indeling niet en
heeft weinig kennis van Vlaamse begrippen; wat het wél goed kan, is vergelijken
met voorbeelden. De vraag is daarom zo opgebouwd:

* **De indeling zoals jij ze gebruikt.** Niet alle uiteinden van de boom, maar
  de paden waarin je in deze richting (inkomst of uitgave) al transacties hebt
  bevestigd — ook tussenniveaus zoals *Hobby › restaurant* — plus de paden
  waarvoor je een omschrijving schreef. Bij elk pad: jouw omschrijving en een
  paar tegenpartijen die je er eerder in zette. Die lijst staat in de
  systeeminstructie en is voor elke vraag in dezelfde richting gelijk; Ollama
  kan dat stuk dan hergebruiken in plaats van telkens opnieuw te verwerken.
* **De transactie**, met de mededeling voorop: die schreef een mens, en ze zegt
  meestal letterlijk waarvoor betaald werd.
* **Eerdere transacties die erop lijken**, uit je historiek (zie historiek.py).
* **Webinformatie**, alleen bij betalingen aan een zaak (kaart, Bancontact,
  eCommerce, domiciliëring). Bij een overschrijving tussen personen vond Brave
  vooral naamgenoten, merken en LinkedIn-profielen, en dat stuurde het model
  de verkeerde kant op.

Het model kiest altijd één pad. Zijn eigen "zekerheid" wordt niet meer
gevraagd: een 7B-model gaf 90% bij drie foute antwoorden op drie. De zekerheid
van een voorstel komt nu uit de historiek — klopt de keuze met de gelijkaardige
eerdere transacties, of wijkt ze ervan af.

Het contextvenster (`num_ctx`) wordt expliciet meegegeven. Ollama gebruikt
anders een klein standaardvenster en kort een te lange vraag stil in. Blijkt de
vraag te groot, dan worden eerst de voorbeeldnamen per pad ingekort.

Een voorstel uit deze stap komt altijd op status "nazicht". Elke bevraging —
de vraag, het ruwe antwoord, het aantal tokens en het resultaat — wordt in het
logboek gezet (versleuteld, net als de rest van dat logboek).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from ..categories import boom, laad_alles
from ..crypto import normalize
from ..database import instelling, log
from .. import lokaal
from . import historiek as hist
from .engine import TransactieKenmerken, Voorstel

# Ruim: op een processor zonder grafische kaart kost het verwerken van een
# vraag van een paar duizend tokens al snel een of twee minuten.
TIMEOUT = 300
BRAVE_ZOEK_URL = "https://api.search.brave.com/res/v1/web/search"
STANDAARD_CONTEXT = 8192
# Wat er in het venster vrij moet blijven voor het antwoord en als marge.
ANTWOORDRUIMTE = 700

# Hoofdcategorieën waarbij een land van bestemming zin heeft.
LAND_WOORDEN = ("vakantie", "reis")

# De kopregel van een categorieënbestand ("Hoofdcategorie / Categorie /
# Subcategorie") die als categorie mee is ingelezen. Voor het model is dat ruis.
PLAATSHOUDERS = {"hoofdcategorie"}

# Soorten verrichting waarbij de tegenpartij een persoon kan zijn. Daar geeft
# een webopzoeking op de naam vooral naamgenoten.
GEEN_WEB = ("overschrijving", "opdracht", "storting", "overdracht")

# Zekerheid van een AI-voorstel, bepaald door de historiek en niet door het
# model zelf.
ZEKER_STANDAARD = 0.5
ZEKER_BEVESTIGD = 0.7   # zelfde pad als de best gelijkende eerdere transactie
ZEKER_AFWIJKEND = 0.35  # gelijkaardige transacties wijzen elders naartoe
STERKE_GELIJKENIS = 0.5


def _enkel_spatie(tekst: str) -> str:
    """Bankexports vullen namen soms op met spaties ("LedLoket      Denekamp")."""
    return " ".join((tekst or "").split())


class AIFout(RuntimeError):
    pass


def beschikbaar(conn) -> bool:
    return instelling(conn, "ai_actief", "0") == "1"


def contextvenster(conn) -> int:
    try:
        return max(2048, min(131072, int(instelling(conn, "ai_contextvenster",
                                                     str(STANDAARD_CONTEXT)))))
    except (TypeError, ValueError):
        return STANDAARD_CONTEXT


def _http_json(url: str, payload: dict, timeout: int = TIMEOUT) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise AIFout(f"Kon het AI-model niet bereiken: {exc}") from exc


def test_verbinding(conn) -> tuple[bool, str]:
    basis = instelling(conn, "ai_basis_url").rstrip("/")
    try:
        with urllib.request.urlopen(f"{basis}/api/tags", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        modellen = [m.get("name", "") for m in data.get("models", [])]
        if not modellen:
            return True, "Verbinding gelukt, maar er staan nog geen modellen klaar."
        return True, "Verbinding gelukt. Beschikbaar: " + ", ".join(modellen[:8])
    except Exception as exc:  # noqa: BLE001
        return False, f"Geen verbinding: {exc}"


def zoekvraag(naam: str) -> str:
    """De zoekvraag die naar Brave gaat. Op één plaats, zodat de knop in het
    bewerkscherm gegarandeerd hetzelfde opzoekt als het AI-model."""
    return _enkel_spatie(naam) + " winkel bedrijf"


def _zonder_html(tekst: str) -> str:
    return re.sub(r"<[^>]+>", "", tekst or "").strip()


def _brave(sleutel: str, zoekterm: str) -> list[dict]:
    """Eén opzoeking bij de Brave Search API. Geeft de eerste vijf resultaten
    als {titel, beschrijving, url, bron}; gooit AIFout als het misloopt."""
    url = BRAVE_ZOEK_URL + "?" + urllib.parse.urlencode({
        "q": zoekvraag(zoekterm),
        "count": 5,
    })
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "X-Subscription-Token": sleutel,
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AIFout(f"Brave Search gaf geen antwoord: {exc}") from exc

    uit = []
    for r in ((data.get("web") or {}).get("results") or [])[:5]:
        uit.append({
            "titel": _zonder_html(r.get("title")),
            "beschrijving": _zonder_html(r.get("description")),
            "url": str(r.get("url") or ""),
            "bron": str((r.get("meta_url") or {}).get("hostname") or ""),
        })
    return uit


def _als_context(resultaten: list[dict]) -> str:
    """De resultaten zoals het model ze te zien krijgt: titel — beschrijving,
    één per regel, samen hoogstens 1200 tekens."""
    stukken = []
    for r in resultaten:
        regel = " — ".join(deel for deel in (r["titel"], r["beschrijving"]) if deel)
        if regel:
            stukken.append(regel)
    return "\n".join(stukken)[:1200]


def _webcontext(conn, zoekterm: str) -> str:
    """Haalt een paar zoekresultaten op over de tegenpartij, via de Brave
    Search API. Faalt stil: geen sleutel ingesteld, geen bereikbare server of
    een andere fout levert gewoon geen context op, en de bevraging van het
    AI-model gaat gewoon door zonder die context."""
    if not zoekterm:
        return ""
    sleutel = lokaal.lees(conn, "brave_api_key")
    if not sleutel:
        return ""
    try:
        return _als_context(_brave(sleutel, zoekterm))
    except AIFout:
        return ""


def webopzoeking_klaar(conn) -> bool:
    """Staat de webopzoeking aan, en is er een Brave-sleutel?"""
    return (instelling(conn, "ai_zoeken_actief", "0") == "1"
            and bool(lokaal.lees(conn, "brave_api_key")))


def webopzoeking(conn, k: TransactieKenmerken) -> dict:
    """Dezelfde opzoeking als bij een AI-bevraging, maar om te tonen.

    Er wordt ook gezocht als het model het bij deze transactie niet zou doen
    (een overschrijving): je vraagt er zelf om, en het scherm zegt erbij dat
    het model deze resultaten dan niet meekrijgt.
    """
    if not webopzoeking_klaar(conn):
        raise AIFout("De webopzoeking staat uit of er is geen Brave API-sleutel "
                     "ingevuld (Instellingen › Automatisch indelen).")
    naam = _enkel_spatie(k.tegenpartij_naam)
    if not naam:
        raise AIFout("Er is geen naam van de tegenpartij om op te zoeken.")

    resultaten = _brave(lokaal.lees(conn, "brave_api_key"), naam)
    zinvol, reden = webopzoeking_zinvol(k)
    if zinvol:
        gebruik = ("Dit is wat het AI-model bij deze transactie over de "
                   "tegenpartij meekrijgt.")
    else:
        gebruik = (f"Bij deze transactie zoekt het AI-model niet op het internet "
                   f"({reden}); deze resultaten krijgt het dus niet te zien.")
    return {
        "zoekvraag": zoekvraag(naam),
        "resultaten": resultaten,
        "context": _als_context(resultaten) if zinvol else "",
        "model_gebruikt": zinvol,
        "gebruik": gebruik,
    }


def webopzoeking_zinvol(k: TransactieKenmerken) -> tuple[bool, str]:
    """Heeft een opzoeking op de naam van de tegenpartij zin?

    Alleen bij een betaling aan een zaak. Bij een overschrijving kan de
    tegenpartij een persoon zijn, en dan vindt een zoekmachine naamgenoten.
    """
    if not _enkel_spatie(k.tegenpartij_naam):
        return False, "geen naam van de tegenpartij"
    soort = normalize(k.beschrijving)
    for woord in GEEN_WEB:
        if woord in soort:
            return False, f"{_enkel_spatie(k.beschrijving)} — de tegenpartij kan een persoon zijn"
    return True, ""


# --------------------------------------------------------------------------
# De indeling zoals de gebruiker ze gebruikt
# --------------------------------------------------------------------------

@dataclass
class Pad:
    label: str
    ids: tuple
    aantal: int
    omschrijving: str
    namen: list[str]


def _alle_uiteinden(wortels) -> list[tuple[str, tuple]]:
    """Alle uiteinden van de boom, voor wie nog (bijna) geen historiek heeft."""
    uit = []
    for hoofd in wortels:
        if not hoofd.kinderen:
            uit.append((hoofd.naam, (hoofd.id, None, None)))
        for sub in hoofd.kinderen:
            if not sub.kinderen:
                uit.append((f"{hoofd.naam} > {sub.naam}", (hoofd.id, sub.id, None)))
            for subsub in sub.kinderen:
                uit.append((f"{hoofd.naam} > {sub.naam} > {subsub.naam}",
                            (hoofd.id, sub.id, subsub.id)))
    return uit


def indeling(conn, crypto, richting: str, geheugen: hist.Historiek) -> list[Pad]:
    """De paden die het model te zien krijgt, alfabetisch.

    Wat je in deze richting al gebruikt hebt, plus alles onder een categorie
    met een omschrijving. Heb je in deze richting nog nauwelijks iets
    bevestigd, dan de volledige boom: anders valt er niets te kiezen.
    """
    platte = laad_alles(conn, crypto, alleen_actief=True)
    wortels = [w for w in boom(conn, crypto, soort=richting, alleen_actief=True)
               if normalize(w.naam) not in PLAATSHOUDERS]
    toegelaten_wortels = {w.id for w in wortels}
    r = geheugen.richting(richting)

    def label(ids) -> str | None:
        namen = []
        for i in ids:
            if i is None:
                continue
            if i not in platte:
                return None  # uitgezet of verwijderd
            namen.append(platte[i].naam)
        return " > ".join(namen) if namen else None

    def omschrijving(ids) -> str:
        return "; ".join(platte[i].omschrijving for i in ids
                         if i in platte and platte[i].omschrijving)

    paden: dict[tuple, Pad] = {}

    def voeg_toe(ids, aantal=0):
        if ids in paden or ids[0] not in toegelaten_wortels:
            return
        tekst = label(ids)
        if not tekst:
            return
        namen = [n for n, _ in r.namen.get(ids, {}).most_common(4)] if ids in r.namen else []
        paden[ids] = Pad(tekst, ids, aantal, omschrijving(ids), namen)

    for ids, aantal in r.telling.items():
        voeg_toe(ids, aantal)

    beschreven = {c.id for c in platte.values() if c.omschrijving}
    weinig = len(paden) < 5
    for tekst, ids in _alle_uiteinden(wortels):
        if weinig or beschreven.intersection(i for i in ids if i):
            voeg_toe(ids)

    return sorted(paden.values(), key=lambda p: p.label.lower())


# --------------------------------------------------------------------------
# De vraag
# --------------------------------------------------------------------------

SYSTEEM = (
    "Je bent een boekhoudkundige assistent voor een Vlaams huishouden. Je deelt "
    "één banktransactie in volgens de EIGEN indeling van deze gebruiker. Die staat "
    "hieronder: elk pad met, waar bekend, een omschrijving van de gebruiker "
    "(\"omschrijving:\") en tegenpartijen die de gebruiker er eerder in zette "
    "(\"o.a.\"). Die omschrijvingen en voorbeelden bepalen wat een categorie "
    "betekent, meer dan de naam.\n"
    "\n"
    "Bronnen, van sterk naar zwak:\n"
    "1. De mededeling. Die schreef een mens; ze zegt meestal letterlijk waarvoor "
    "betaald werd.\n"
    "2. Eerdere transacties van deze gebruiker die op deze lijken: zo deelt de "
    "gebruiker in. Staat daar dezelfde tegenpartij of hetzelfde soort aankoop, "
    "kies dan in principe hetzelfde pad.\n"
    "3. Webinformatie over de tegenpartij (alleen bij betalingen aan een zaak). "
    "Die zegt wat voor zaak het is, maar kan over een naamgenoot of een ander "
    "bedrijf gaan: negeer ze als ze niet klopt met de naam of de mededeling.\n"
    "4. De naam van de tegenpartij.\n"
    "\n"
    "Spelregels:\n"
    "- Deel in volgens WAT er gekocht of betaald werd, niet HOE of WAAR: online, "
    "webshop, winkel, eCommerce, Bancontact, betaalkaart of overschrijving zeggen "
    "niets over de categorie.\n"
    "- Vlaamse begrippen: Chiro, KSA, KLJ, scouts en gidsen zijn jeugdbewegingen; "
    "een frituur is een snackbar; Delhaize, Colruyt, Aldi en Lidl zijn "
    "supermarkten.\n"
    "- Bij een inkomst betaalt iemand de gebruiker: denk aan een terugbetaling, een "
    "verkoop, loon, een cadeau.\n"
    "- Een categorie voor vakantie of reizen alleen als de transactie zelf op een "
    "reis wijst (hotel, camping, tol onderweg, vliegticket). Een winkel of webshop "
    "in een ander land is geen vakantie.\n"
    "- Kies ALTIJD precies één pad uit de lijst, ook als je twijfelt. Neem het "
    "nummer én de tekst van het pad letterlijk over.\n"
    "- Land: alleen invullen (ISO-code, bv. FR) bij een uitgave tijdens een reis.\n"
    "- Antwoord uitsluitend met JSON, zonder uitleg errond, velden in deze "
    "volgorde: "
    '{"reden": "<één korte zin: wat werd er betaald en waarom dit pad>", '
    '"nummer": <getal uit de lijst>, "pad": "<de tekst van dat pad, letterlijk>", '
    '"handelaar": "<naam van de zaak of leeg>", "land": "<landcode of leeg>"}\n'
)


def _padregel(nummer: int, pad: Pad, namen: int) -> str:
    regel = f"{nummer}. {pad.label}"
    extra = []
    if pad.omschrijving:
        extra.append(f"omschrijving: {pad.omschrijving}")
    if namen and pad.namen:
        extra.append("o.a. " + ", ".join(pad.namen[:namen]))
    return regel + (" — " + "; ".join(extra) if extra else "")


def _systeem(richting: str, paden: list[Pad], namen: int) -> str:
    kop = "Indeling voor " + ("INKOMSTEN" if richting == "in" else "UITGAVEN")
    return (SYSTEEM + "\n" + kop + ":\n"
            + "\n".join(_padregel(i + 1, p, namen) for i, p in enumerate(paden)))


def _gebruikersbericht(k: TransactieKenmerken, voorbeelden, labels: dict,
                       context: str, web_reden: str) -> str:
    tekst = (
        "Transactie\n"
        f"- Mededeling: {_enkel_spatie(k.mededeling) or 'geen'}\n"
        f"- Richting: {'inkomst (iemand betaalt de gebruiker)' if k.richting == 'in' else 'uitgave'}\n"
        f"- Bedrag: {abs(k.bedrag)} EUR\n"
        f"- Tegenpartij: {_enkel_spatie(k.tegenpartij_naam) or 'onbekend'}\n"
    )
    if k.begunstigde and normalize(k.begunstigde) != normalize(k.tegenpartij_naam):
        tekst += f"- Begunstigde: {_enkel_spatie(k.begunstigde)}\n"
    if k.beschrijving:
        tekst += (f"- Soort verrichting: {_enkel_spatie(k.beschrijving)} "
                  "(zegt hoe er betaald werd, niet waarvoor)\n")

    tekst += "\nEerdere transacties van deze gebruiker die hierop lijken:\n"
    if voorbeelden:
        for v in voorbeelden:
            mededeling = f" — \"{v.mededeling}\"" if v.mededeling else ""
            soort = "" if v.richting == k.richting else (
                " (een inkomst)" if v.richting == "in" else " (een uitgave)")
            tekst += f"- {v.tegenpartij or 'onbekend'}{mededeling}{soort} → {labels[v.ids]}\n"
    else:
        tekst += "(geen gevonden)\n"

    if context:
        tekst += ("\nWebinformatie over de tegenpartij (automatisch opgezocht op de "
                  "naam; kan over een naamgenoot of een ander bedrijf gaan):\n"
                  f"{context}\n")
    elif web_reden:
        tekst += f"\nGeen webinformatie opgezocht: {web_reden}.\n"
    return tekst


def _schatting(tekst: str) -> int:
    """Ruwe schatting van het aantal tokens. Nederlandse tekst telt bij de
    gangbare modellen ongeveer drie tekens per token; liever te ruim."""
    return len(tekst) // 3 + 1


def _chat(basis: str, model: str, systeem: str, vraag: str, num_ctx: int) -> tuple[str, dict, dict]:
    """Eén vraag aan het model. Geeft (ruw antwoord, ontlede JSON, statistiek)."""
    antwoord = _http_json(f"{basis}/api/chat", {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_ctx": num_ctx},
        "messages": [
            {"role": "system", "content": systeem},
            {"role": "user", "content": vraag},
        ],
    })
    inhoud = (antwoord.get("message") or {}).get("content", "")
    statistiek = {
        "vraag_tokens": antwoord.get("prompt_eval_count"),
        "antwoord_tokens": antwoord.get("eval_count"),
        "seconden": round((antwoord.get("total_duration") or 0) / 1e9, 1),
    }
    try:
        return inhoud, json.loads(inhoud), statistiek
    except json.JSONDecodeError:
        gevonden = re.search(r"\{.*\}", inhoud, re.S)
        if gevonden:
            try:
                return inhoud, json.loads(gevonden.group(0)), statistiek
            except json.JSONDecodeError:
                pass
    raise _StapFout("Het model gaf geen bruikbaar antwoord.", inhoud, statistiek)


class _StapFout(AIFout):
    def __init__(self, boodschap: str, ruw: str = "", statistiek: dict | None = None):
        super().__init__(boodschap)
        self.ruw = ruw
        self.statistiek = statistiek or {}


def _kies_pad(data: dict, paden: list[tuple[str, tuple]]) -> tuple[int, str]:
    """Welk pad heeft het model gekozen?

    Het model geeft zowel een nummer als de tekst van het pad. Bij een lange
    lijst verspringt een klein model al eens een nummer, terwijl de tekst wel
    klopt; de tekst gaat daarom voor als ze letterlijk (op hoofdletters en
    spaties na) in de lijst staat. Geeft (index, hoe gevonden) terug, of
    (-1, "") als geen van beide bruikbaar is.
    """
    def plat(tekst: str) -> str:
        return normalize(re.sub(r"\s*[>›]\s*", " > ", str(tekst or "")))

    gevraagd = plat(data.get("pad", ""))
    if gevraagd:
        for i, (label, _) in enumerate(paden):
            if plat(label) == gevraagd:
                return i, "pad"
    try:
        index = int(data.get("nummer", 0)) - 1
    except (TypeError, ValueError):
        index = -1
    if 0 <= index < len(paden):
        return index, "nummer"
    return -1, ""


def _tokennotities(notities: list[str], stat: dict, num_ctx: int) -> None:
    """Hoe groot de vraag was volgens Ollama zelf. Vult ze het venster, dan is
    ze vermoedelijk ingekort — en dat gebeurt stil."""
    if not stat.get("vraag_tokens"):
        return
    notities.append(f"Tokens: vraag {stat['vraag_tokens']}, antwoord "
                    f"{stat.get('antwoord_tokens')}, venster {num_ctx}; "
                    f"{stat.get('seconden')} s")
    if stat["vraag_tokens"] >= num_ctx - 50:
        notities.append("LET OP: de vraag vulde het hele venster en is vermoedelijk "
                        "ingekort. Vergroot het venster bij Instellingen › "
                        "Automatisch indelen.")


def _log_bevraging(conn, crypto, gebruiker: str | None, model: str,
                    k: TransactieKenmerken, systeem: str, vraag: str, ruw: str,
                    notities: list[str], voorstel: Voorstel | None,
                    fout: str | None = None) -> None:
    """Zet de volledige bevraging in het logboek, versleuteld zoals de rest."""
    if not gebruiker:
        return
    naam = _enkel_spatie(k.tegenpartij_naam) or k.beschrijving or "onbekend"
    stukken = [
        f"Tegenpartij: {naam}",
        f"Bedrag: {abs(k.bedrag)} EUR ({'inkomst' if k.richting == 'in' else 'uitgave'})",
        f"Model: {model}",
    ]
    stukken += notities
    stukken += [
        "",
        "Verzonden vraag (systeeminstructie met indeling + gebruikersbericht):",
        systeem,
        "---",
        vraag.strip(),
        "",
        "Ruw antwoord van het model:",
        (ruw or "(geen antwoord ontvangen)").strip(),
    ]
    if voorstel is not None:
        stukken += ["", f"Resultaat: Voorstel: {voorstel.toelichting}"]
    if fout:
        stukken += ["", f"Resultaat: geen voorstel — {fout}"]
    log(conn, crypto, gebruiker, "ai_bevraagd", "\n".join(stukken))


def stel_voor(conn, crypto, k: TransactieKenmerken, gebruiker: str | None = None) -> Voorstel:
    """Vraagt het model om een voorstel (zie bovenaan voor de opbouw).

    Met `gebruiker` wordt de volledige bevraging in het logboek gezet, ook als
    het model geen bruikbaar antwoord geeft.
    """
    if not beschikbaar(conn):
        raise AIFout("Het AI-model staat uitgeschakeld in de instellingen.")

    geheugen = hist.laad(conn, crypto)
    paden = indeling(conn, crypto, k.richting, geheugen)
    if not paden:
        raise AIFout("Er zijn nog geen categorieën ingesteld.")
    labels = {p.ids: p.label for p in paden}

    basis = instelling(conn, "ai_basis_url").rstrip("/")
    model = instelling(conn, "ai_model")
    num_ctx = contextvenster(conn)
    notities: list[str] = []

    # Eerdere transacties die erop lijken, in beide richtingen: een uitgave
    # "lidgeld chiro" zegt ook iets over een inkomst "chiro rokje". Alleen naar
    # paden die in de lijst staan, anders zou het model een pad zien dat het
    # niet mag kiezen. De eigen richting gaat voor bij gelijke score.
    naam = _enkel_spatie(k.tegenpartij_naam) + " " + _enkel_spatie(k.begunstigde)
    andere = "in" if k.richting == "uit" else "uit"
    kandidaten = (geheugen.lijkt_op(k.richting, naam, _enkel_spatie(k.mededeling))
                  + geheugen.lijkt_op(andere, naam, _enkel_spatie(k.mededeling), aantal=3))
    voorbeelden = sorted((v for v in kandidaten if v.ids in labels),
                         key=lambda v: (-v.score, v.richting != k.richting))[:6]

    zinvol, web_reden = webopzoeking_zinvol(k)
    context = ""
    if instelling(conn, "ai_zoeken_actief", "0") == "1":
        if zinvol:
            context = _webcontext(conn, _enkel_spatie(k.tegenpartij_naam))
            notities.append("Webopzoeking: " + ("uitgevoerd" if context
                                                 else "niets gevonden of niet bereikbaar"))
        else:
            notities.append(f"Webopzoeking: overgeslagen ({web_reden})")
    else:
        web_reden = ""

    vraag = _gebruikersbericht(k, voorbeelden, labels, context, web_reden)

    # Past het in het venster? Zo niet: eerst minder voorbeeldnamen per pad,
    # dan de minst gebruikte paden weglaten.
    budget = num_ctx - ANTWOORDRUIMTE
    namen = 3
    systeem = _systeem(k.richting, paden, namen)
    while _schatting(systeem + vraag) > budget and namen > 0:
        namen -= 1
        systeem = _systeem(k.richting, paden, namen)
    if _schatting(systeem + vraag) > budget:
        houden = {v.ids for v in voorbeelden}
        rangorde = sorted(paden, key=lambda p: (p.ids not in houden, -p.aantal))
        while len(rangorde) > 10 and _schatting(_systeem(k.richting, rangorde, 0) + vraag) > budget:
            rangorde.pop()
        paden = sorted(rangorde, key=lambda p: p.label.lower())
        labels = {p.ids: p.label for p in paden}
        systeem = _systeem(k.richting, paden, 0)
        notities.append(f"LET OP: de indeling paste niet in het contextvenster van "
                        f"{num_ctx} tokens; alleen de {len(paden)} meest gebruikte "
                        "paden zijn meegegeven. Vergroot het venster bij "
                        "Instellingen › Automatisch indelen.")
    notities.append(f"Indeling: {len(paden)} paden, {namen} voorbeeldnamen per pad; "
                    f"{len(voorbeelden)} gelijkaardige eerdere transacties")

    ruw = ""
    try:
        try:
            ruw, data, stat = _chat(basis, model, systeem, vraag, num_ctx)
        except _StapFout as exc:
            ruw = exc.ruw
            _tokennotities(notities, exc.statistiek, num_ctx)
            raise
        _tokennotities(notities, stat, num_ctx)

        paden_tuples = [(p.label, p.ids) for p in paden]
        index, _ = _kies_pad(data, paden_tuples)
        if index < 0:
            raise AIFout("Het model koos geen categorie uit de lijst.")
        label, ids = paden_tuples[index]

        # Zekerheid uit de historiek, niet uit het model.
        sterk = [v for v in voorbeelden if v.score >= STERKE_GELIJKENIS]
        reden = str(data.get("reden") or "").strip()
        if sterk and sterk[0].ids == ids:
            zekerheid = ZEKER_BEVESTIGD
            steun = f" Zelfde indeling als een eerdere transactie bij {sterk[0].tegenpartij}."
        elif sterk and ids not in {v.ids for v in sterk}:
            zekerheid = ZEKER_AFWIJKEND
            steun = (f" Let op: een gelijkaardige eerdere transactie bij "
                     f"{sterk[0].tegenpartij} staat onder {labels[sterk[0].ids]}.")
        else:
            zekerheid = ZEKER_STANDAARD
            steun = ""

        handelaar = _enkel_spatie(str(data.get("handelaar", "") or "")) or None
        land = str(data.get("land", "") or "").strip() or None
        if land and not any(w in label.lower() for w in LAND_WOORDEN):
            land = None

        voorstel = Voorstel(
            categorie_id=ids[0],
            subcategorie_id=ids[1],
            subsub_id=ids[2],
            handelaar=handelaar,
            land=land,
            zekerheid=zekerheid,
            methode="ai",
            status="nazicht",
            toelichting=(f"Voorstel van {model}: {label}."
                         + (f" {reden}" if reden else "") + steun),
        )
    except AIFout as exc:
        _log_bevraging(conn, crypto, gebruiker, model, k, systeem, vraag, ruw,
                       notities, None, fout=str(exc))
        raise

    _log_bevraging(conn, crypto, gebruiker, model, k, systeem, vraag, ruw,
                   notities, voorstel)
    return voorstel


def maak_regel_van_voorstel(conn, crypto, k: TransactieKenmerken, voorstel: Voorstel) -> None:
    """Legt een bevestigd AI- of fuzzy-voorstel vast als vaste regel."""
    from ..database import now_iso

    waarde = (voorstel.handelaar or k.tegenpartij_naam or "").strip()
    if not waarde:
        return
    bestaand = conn.execute(
        "SELECT id FROM regels WHERE waarde_idx = ? AND veld='tegenpartij_naam'"
        " AND IFNULL(categorie_id,0)=IFNULL(?,0) AND IFNULL(subcategorie_id,0)=IFNULL(?,0)",
        (crypto.blind(waarde), voorstel.categorie_id, voorstel.subcategorie_id),
    ).fetchone()
    if bestaand:
        return
    conn.execute(
        "INSERT INTO regels (naam_enc, prioriteit, veld, operator, waarde_enc, waarde_idx,"
        " richting, categorie_id, subcategorie_id, subsub_id, handelaar_enc, land_enc,"
        " aangemaakt_op) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            crypto.enc(f"Geleerd van {waarde}"), 50, "tegenpartij_naam", "bevat",
            crypto.enc(normalize(waarde)), crypto.blind(normalize(waarde)),
            k.richting, voorstel.categorie_id, voorstel.subcategorie_id, voorstel.subsub_id,
            crypto.enc(voorstel.handelaar) if voorstel.handelaar else None,
            crypto.enc(voorstel.land) if voorstel.land else None,
            now_iso(),
        ),
    )
