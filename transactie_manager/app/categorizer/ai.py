"""Stap 3: voorstel door een lokaal AI-model.

Er wordt gepraat met een Ollama-server (of een compatibele server met hetzelfde
`/api/chat`-eindpunt). Optioneel wordt eerst via de Brave Search API opgezocht
wat voor zaak de tegenpartij is; die webinformatie is dan de belangrijkste bron
voor het model.

De keuze gebeurt in twee kleine stappen in plaats van één grote:

1. **Hoofdcategorie.** Het model beschrijft wat voor zaak de tegenpartij is en
   wat er vermoedelijk betaald werd, en kiest daarna één hoofdcategorie uit een
   korte lijst (met de subcategorieën erbij als uitleg).
2. **Pad.** Binnen die hoofdcategorie kiest het het volledige pad.

Een klein model (7B) haalt bij één lijst van honderden paden de mist in: het
begrijpt de zaak wel, maar kiest dan op een toevallig woord ("online winkel" →
"Shopping") in plaats van op wat er gekocht werd. Twee korte lijsten houden
het bij de les. Het model kiest altijd een pad; twijfel drukt het uit in de
zekerheid.

Een voorstel uit deze stap komt altijd op status "nazicht": de gebruiker moet
het bevestigen, net zoals bij een fuzzy suggestie. Elke bevraging — per stap de
vraag en het ruwe antwoord, en het resultaat — wordt in het logboek gezet
(versleuteld, net als de rest van dat logboek).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from ..categories import boom, keuzelijst
from ..crypto import normalize
from ..database import instelling, log
from .. import lokaal
from .engine import TransactieKenmerken, Voorstel

TIMEOUT = 60
BRAVE_ZOEK_URL = "https://api.search.brave.com/res/v1/web/search"

# Hoofdcategorieën waarbij een land van bestemming zin heeft. Bij andere
# uitgaven vulde het model soms toch een land in — het land van de winkel —
# en dat hoort niet in het veld "land van bestemming".
LAND_WOORDEN = ("vakantie", "reis")


def _enkel_spatie(tekst: str) -> str:
    """Bankexports vullen namen soms op met spaties ("LedLoket      Denekamp").
    Dat maakt de vraag aan het model en de zoekopdracht er niet beter op."""
    return " ".join((tekst or "").split())


class AIFout(RuntimeError):
    pass


def beschikbaar(conn) -> bool:
    return instelling(conn, "ai_actief", "0") == "1"


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


def _webcontext(conn, zoekterm: str) -> str:
    """Haalt een paar zoekresultaten op over de tegenpartij, via de Brave
    Search API. Faalt stil: geen sleutel ingesteld, geen bereikbare server of
    een andere fout levert gewoon geen context op, en de bevraging van het
    AI-model gaat gewoon door zonder die context."""
    if instelling(conn, "ai_zoeken_actief", "0") != "1" or not zoekterm:
        return ""
    sleutel = lokaal.lees(conn, "brave_api_key")
    if not sleutel:
        return ""
    url = BRAVE_ZOEK_URL + "?" + urllib.parse.urlencode({
        "q": _enkel_spatie(zoekterm) + " winkel bedrijf",
        "count": 5,
    })
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "X-Subscription-Token": sleutel,
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return ""

    resultaten = ((data.get("web") or {}).get("results") or [])[:5]
    stukken = []
    for r in resultaten:
        titel = re.sub(r"<[^>]+>", "", r.get("title") or "").strip()
        beschrijving = re.sub(r"<[^>]+>", "", r.get("description") or "").strip()
        regel = " — ".join(deel for deel in (titel, beschrijving) if deel)
        if regel:
            stukken.append(regel)
    return "\n".join(stukken)[:1200]


# De kopregel van een categorieënbestand ("Hoofdcategorie / Categorie /
# Subcategorie") die als categorie mee is ingelezen. Voor het model is dat
# ruis: het is geen echte keuze.
PLAATSHOUDERS = {"hoofdcategorie"}


def _wortels(conn, crypto, richting: str):
    return [w for w in boom(conn, crypto, soort=richting, alleen_actief=True)
            if normalize(w.naam) not in PLAATSHOUDERS]


def _paden(conn, crypto, richting: str) -> list[tuple[str, tuple]]:
    """Alle toegelaten categoriepaden als (leesbaar pad, id-tupel)."""
    resultaat: list[tuple[str, tuple]] = []
    for hoofd in _wortels(conn, crypto, richting):
        if not hoofd.kinderen:
            resultaat.append((hoofd.naam, (hoofd.id, None, None)))
        for sub in hoofd.kinderen:
            if not sub.kinderen:
                resultaat.append((f"{hoofd.naam} > {sub.naam}", (hoofd.id, sub.id, None)))
            for subsub in sub.kinderen:
                resultaat.append((
                    f"{hoofd.naam} > {sub.naam} > {subsub.naam}",
                    (hoofd.id, sub.id, subsub.id),
                ))
    return resultaat


# Gedeelde spelregels voor beide stappen. Wat hier staat, is telkens een fout
# die het model in de praktijk maakte.
SPELREGELS = (
    "Spelregels:\n"
    "- De informatie van het web is je belangrijkste bron: die zegt wat voor zaak "
    "de tegenpartij is. Vertrouw daarop meer dan op wat de naam doet vermoeden.\n"
    "- Deel in volgens WAT er gekocht of betaald werd (het soort product of de "
    "dienst), niet volgens HOE of WAAR: woorden als online, webshop, winkel, "
    "shopping, eCommerce of betaalkaart zeggen niets over de categorie.\n"
    "- Een categorie voor vakantie of reizen kies je alleen als de transactie zelf "
    "op een reis wijst (hotel, camping, tol of brandstof onderweg, vliegticket, "
    "uitstap tijdens een vakantie). Een aankoop bij een winkel of webshop in een "
    "ander land is géén vakantie-uitgave.\n"
    "- Het bedrag helpt om te kiezen tussen aannemelijke opties, niet om een "
    "categorie te verzinnen.\n"
    "- Je kiest ALTIJD precies één optie uit de lijst, ook als je twijfelt: kies dan "
    "de meest waarschijnlijke en geef een lage zekerheid. Zekerheid: 0.9 of hoger "
    "als het duidelijk past, rond 0.6 als het aannemelijk is, 0.3 of lager als het "
    "een gok is.\n"
    "- Neem het nummer én de tekst van je keuze letterlijk over uit de lijst.\n"
    "- Antwoord uitsluitend met JSON, zonder uitleg errond, met de velden in de "
    "gevraagde volgorde."
)

SYSTEEM_HOOFD = (
    "Je bent een boekhoudkundige assistent voor een Belgisch huishouden. Je krijgt "
    "één banktransactie en een genummerde lijst met hoofdcategorieën; achter elke "
    "hoofdcategorie staat ter uitleg wat eronder valt.\n"
    "Werkwijze: beschrijf eerst in een paar woorden wat voor zaak de tegenpartij is "
    "en wat er vermoedelijk gekocht of betaald werd. Kies pas daarna de "
    "hoofdcategorie waar dat product of die dienst thuishoort.\n"
    + SPELREGELS + "\n"
    'Vorm: {"soort_zaak": "<wat voor zaak>", "product": "<wat er vermoedelijk '
    'gekocht of betaald werd>", "reden": "<één korte zin>", "nummer": <getal uit '
    'de lijst>, "hoofdcategorie": "<de naam, letterlijk>", "zekerheid": <0.0 tot 1.0>}'
)

SYSTEEM_PAD = (
    "Je bent een boekhoudkundige assistent voor een Belgisch huishouden. Je krijgt "
    "één banktransactie, een beschrijving van wat er betaald werd, en een "
    "genummerde lijst met categoriepaden binnen één hoofdcategorie. Kies het pad "
    "dat past bij het product of de dienst.\n"
    + SPELREGELS + "\n"
    "Land: alleen invullen (ISO-landcode, bv. FR) bij een uitgave tijdens een "
    "vakantie of reis; het land waar een winkel gevestigd is, telt niet.\n"
    'Vorm: {"reden": "<één korte zin>", "nummer": <getal uit de lijst>, '
    '"pad": "<de tekst van dat pad, letterlijk>", "handelaar": "<naam van de zaak '
    'of leeg>", "land": "<landcode of leeg>", "zekerheid": <0.0 tot 1.0>}'
)


def _transactietekst(k: TransactieKenmerken, context: str) -> str:
    """De transactie zoals het model ze te zien krijgt, webinformatie voorop."""
    tegenpartij = _enkel_spatie(k.tegenpartij_naam)
    tekst = ""
    if context:
        tekst += ("Wat het web zegt over de tegenpartij (belangrijkste bron):\n"
                  f"{context}\n\n")
    else:
        tekst += ("Er is geen webinformatie over de tegenpartij. Baseer je op de "
                  "naam, de mededeling en het bedrag.\n\n")
    tekst += (
        "Transactie\n"
        f"- Richting: {'inkomst' if k.richting == 'in' else 'uitgave'}\n"
        f"- Bedrag: {abs(k.bedrag)} EUR\n"
        f"- Tegenpartij: {tegenpartij or 'onbekend'}\n"
        f"- Rekening tegenpartij: {k.tegenpartij_rekening or 'onbekend'}\n"
        f"- Mededeling: {_enkel_spatie(k.mededeling) or 'geen'}\n"
    )
    if k.beschrijving:
        tekst += (f"- Soort verrichting: {_enkel_spatie(k.beschrijving)} "
                  "(zegt hoe er betaald werd, niet waarvoor)\n")
    return tekst


def _hoofdlijst(wortels) -> list[str]:
    """Eén regel per hoofdcategorie, met wat eronder valt als uitleg.

    Juist die uitleg doet het werk: "Huis" zegt een model weinig, maar
    "Huis — verbouwingen (…, Elektriciteit & Verlichting, …)" wel.
    """
    regels = []
    for hoofd in wortels:
        delen = []
        # Bewust alles: een weggelaten naam is net het woord dat het model
        # nodig had. Het blijft één regel per hoofdcategorie.
        for sub in hoofd.kinderen:
            if sub.kinderen:
                namen = ", ".join(c.naam for c in sub.kinderen)
                delen.append(f"{sub.naam} ({namen})")
            else:
                delen.append(sub.naam)
        regels.append(hoofd.naam + (" — " + "; ".join(delen) if delen else ""))
    return regels


class _StapFout(AIFout):
    """Een fout binnen één stap, met het ruwe antwoord erbij voor het logboek."""

    def __init__(self, boodschap: str, ruw: str = ""):
        super().__init__(boodschap)
        self.ruw = ruw


def _chat(basis: str, model: str, systeem: str, vraag: str) -> tuple[str, dict]:
    """Eén vraag aan het model. Geeft (ruw antwoord, ontlede JSON) terug."""
    antwoord = _http_json(f"{basis}/api/chat", {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
        "messages": [
            {"role": "system", "content": systeem},
            {"role": "user", "content": vraag},
        ],
    })
    inhoud = (antwoord.get("message") or {}).get("content", "")
    try:
        return inhoud, json.loads(inhoud)
    except json.JSONDecodeError:
        gevonden = re.search(r"\{.*\}", inhoud, re.S)
        if gevonden:
            try:
                return inhoud, json.loads(gevonden.group(0))
            except json.JSONDecodeError:
                pass
    raise _StapFout("Het model gaf geen bruikbaar antwoord.", inhoud)


def _zekerheid(data: dict, standaard: float = 0.6) -> float:
    try:
        return max(0.0, min(1.0, float(data.get("zekerheid", standaard))))
    except (TypeError, ValueError):
        return standaard


def _kies_hoofd(data: dict, wortels) -> int:
    """Welke hoofdcategorie? De naam gaat voor op het nummer, zoals bij _kies_pad."""
    gevraagd = normalize(str(data.get("hoofdcategorie", "") or ""))
    if gevraagd:
        for i, hoofd in enumerate(wortels):
            if normalize(hoofd.naam) == gevraagd:
                return i
    try:
        index = int(data.get("nummer", 0)) - 1
    except (TypeError, ValueError):
        return -1
    return index if 0 <= index < len(wortels) else -1


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


def _log_bevraging(conn, crypto, gebruiker: str | None, model: str,
                    k: TransactieKenmerken, stappen: list[tuple[str, str, str, str]],
                    voorstel: Voorstel | None, fout: str | None = None) -> None:
    """Zet de volledige bevraging in het logboek: per stap wat er verstuurd werd
    en wat er terugkwam, en wat daaruit volgde. Net als de rest van het logboek
    wordt dit versleuteld opgeslagen.

    `stappen` is een lijst van (titel, systeeminstructie, vraag, ruw antwoord).
    """
    if not gebruiker:
        return
    naam = _enkel_spatie(k.tegenpartij_naam) or k.beschrijving or "onbekend"
    stukken = [
        f"Tegenpartij: {naam}",
        f"Bedrag: {abs(k.bedrag)} EUR ({'inkomst' if k.richting == 'in' else 'uitgave'})",
        f"Model: {model}",
    ]
    for titel, systeem, vraag, ruw in stappen:
        stukken += [
            "",
            f"=== {titel} ===",
            "Verzonden vraag (systeeminstructie + gebruikersbericht):",
            systeem,
            "---",
            vraag.strip(),
            "",
            "Ruw antwoord van het model:",
            (ruw or "(geen antwoord ontvangen)").strip(),
        ]
    if voorstel is not None:
        stukken += [
            "",
            f"Resultaat: Voorstel: {voorstel.toelichting} "
            f"({round(voorstel.zekerheid * 100)}% zeker).",
        ]
    if fout:
        stukken += ["", f"Resultaat: geen voorstel — {fout}"]
    log(conn, crypto, gebruiker, "ai_bevraagd", "\n".join(stukken))


def stel_voor(conn, crypto, k: TransactieKenmerken, gebruiker: str | None = None) -> Voorstel:
    """Vraagt het model om een voorstel, in twee stappen (zie bovenaan).

    Met `gebruiker` wordt de volledige bevraging — per stap de vraag en het ruwe
    antwoord, en het resultaat — in het logboek gezet, ook als het model geen
    bruikbaar antwoord geeft. Zonder `gebruiker` gebeurt dat niet.

    Lukt de eerste stap niet (geen bruikbaar antwoord, of een hoofdcategorie die
    niet bestaat), dan valt de tweede stap terug op de volledige lijst met
    paden: liever één grote vraag dan geen voorstel.
    """
    if not beschikbaar(conn):
        raise AIFout("Het AI-model staat uitgeschakeld in de instellingen.")

    wortels = _wortels(conn, crypto, k.richting)
    alle_paden = _paden(conn, crypto, k.richting)
    if not alle_paden:
        raise AIFout("Er zijn nog geen categorieën ingesteld.")

    basis = instelling(conn, "ai_basis_url").rstrip("/")
    model = instelling(conn, "ai_model")
    context = _webcontext(conn, _enkel_spatie(k.tegenpartij_naam))
    transactie = _transactietekst(k, context)
    stappen: list[tuple[str, str, str, str]] = []

    try:
        # ---- stap 1: hoofdcategorie ------------------------------------
        hoofd = None
        data1: dict = {}
        zeker_hoofd = 1.0
        beschrijving = ""
        vraag1 = (transactie + "\nHoofdcategorieën:\n" + "\n".join(
            f"{i + 1}. {regel}" for i, regel in enumerate(_hoofdlijst(wortels))) + "\n")
        try:
            ruw1, data1 = _chat(basis, model, SYSTEEM_HOOFD, vraag1)
            stappen.append(("Stap 1: hoofdcategorie", SYSTEEM_HOOFD, vraag1, ruw1))
            index = _kies_hoofd(data1, wortels)
            if index >= 0:
                hoofd = wortels[index]
                zeker_hoofd = _zekerheid(data1)
                soort = _enkel_spatie(str(data1.get("soort_zaak", "") or ""))
                product = _enkel_spatie(str(data1.get("product", "") or ""))
                beschrijving = "; ".join(d for d in (
                    f"soort zaak: {soort}" if soort else "",
                    f"vermoedelijk betaald voor: {product}" if product else "") if d)
        except _StapFout as exc:
            stappen.append(("Stap 1: hoofdcategorie", SYSTEEM_HOOFD, vraag1, exc.ruw))

        # ---- stap 2: pad binnen de hoofdcategorie -----------------------
        if hoofd is not None:
            paden = [p for p in alle_paden if p[1][0] == hoofd.id]
            titel2 = f"Stap 2: pad binnen {hoofd.naam}"
        else:
            paden = alle_paden
            titel2 = "Stap 2: pad uit de volledige lijst (stap 1 gaf geen hoofdcategorie)"

        if len(paden) == 1:
            # Niets te kiezen: de hoofdcategorie heeft maar één pad.
            index, data2, zeker_pad = 0, {}, 1.0
        else:
            vraag2 = transactie
            if beschrijving:
                vraag2 += f"\nWat er betaald werd (uit de eerste stap): {beschrijving}\n"
            vraag2 += "\nCategoriepaden:\n" + "\n".join(
                f"{i + 1}. {label}" for i, (label, _) in enumerate(paden)) + "\n"
            try:
                ruw2, data2 = _chat(basis, model, SYSTEEM_PAD, vraag2)
            except _StapFout as exc:
                stappen.append((titel2, SYSTEEM_PAD, vraag2, exc.ruw))
                raise
            stappen.append((titel2, SYSTEEM_PAD, vraag2, ruw2))
            index, _ = _kies_pad(data2, paden)
            if index < 0:
                raise AIFout("Het model koos geen categorie uit de lijst.")
            zeker_pad = _zekerheid(data2)

        label, ids = paden[index]
        # Een ketting is zo sterk als haar zwakste schakel.
        zekerheid = min(zeker_hoofd, zeker_pad)

        reden = str(data2.get("reden") or data1.get("reden") or "").strip()
        if beschrijving:
            reden = (beschrijving[:1].upper() + beschrijving[1:] + ". " + reden).strip()
        handelaar = _enkel_spatie(str(data2.get("handelaar", "") or "")) or None
        land = str(data2.get("land", "") or "").strip() or None
        if land and not any(w in label.lower() for w in LAND_WOORDEN):
            land = None
        if zekerheid < 0.5:
            reden = ("Het model twijfelt. " + reden).strip()

        voorstel = Voorstel(
            categorie_id=ids[0],
            subcategorie_id=ids[1],
            subsub_id=ids[2],
            handelaar=handelaar,
            land=land,
            zekerheid=round(zekerheid, 3),
            methode="ai",
            status="nazicht",
            toelichting=f"Voorstel van {model}: {label}." + (f" {reden}" if reden else ""),
        )
    except AIFout as exc:
        _log_bevraging(conn, crypto, gebruiker, model, k, stappen, None, fout=str(exc))
        raise

    _log_bevraging(conn, crypto, gebruiker, model, k, stappen, voorstel)
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
