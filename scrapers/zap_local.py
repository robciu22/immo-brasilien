"""
ZAP Imóveis — Lokaler Spider für Android/Termux oder Heimrechner.

Kein Playwright, kein Browser. Funktioniert nur von Wohngebiets-/Mobilfunk-IPs
(Cloudflare blockiert Datacenter-IPs wie GitHub Actions mit HTTP 403).

Ausführung:
    python -m scrapers.zap_local              # Einzel-Run
    python -m scrapers.zap_local --test       # Nur 1 Stadt, 1 Seite

Cronjob (Termux / Linux):
    0 10 * * * cd ~/immo-brasilien && python -m scrapers.zap_local >> ~/zap_scrape.log 2>&1
"""

import hashlib
import logging
import sys
import time
import requests
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from scrapers.vivareal_spider import distanz_zum_meer, extrahiere_flaeche_aus_url
from scrapers.utils import aktueller_kurs_brl_eur

log = logging.getLogger(__name__)

PREIS_MAX_BRL = 2_200_000

ZIELSTAEDTE = {
    # Nordosten
    "fortaleza":          ("nordosten",  "ceara",                "fortaleza"),
    "jericoacoara":       ("nordosten",  "ceara",                "jijoca-de-jericoacoara"),
    "natal":              ("nordosten",  "rio-grande-do-norte",  "natal"),
    "pipa":               ("nordosten",  "rio-grande-do-norte",  "tibau-do-sul"),
    "recife":             ("nordosten",  "pernambuco",           "recife"),
    "salvador":           ("nordosten",  "bahia",                "salvador"),
    "maceio":             ("nordosten",  "alagoas",              "maceio"),
    "maragogi":           ("nordosten",  "alagoas",              "maragogi"),
    "porto-seguro":       ("nordosten",  "bahia",                "porto-seguro"),
    "itacare":            ("nordosten",  "bahia",                "itacare"),
    # Süden
    "florianopolis":      ("sueden",     "santa-catarina",       "florianopolis"),
    "balneario-camboriu": ("sueden",     "santa-catarina",       "balneario-camboriu"),
    "ubatuba":            ("sueden",     "sao-paulo",            "ubatuba"),
    "guaruja":            ("sueden",     "sao-paulo",            "guaruja"),
    "santos":             ("sueden",     "sao-paulo",            "santos"),
    # Rio-Küste
    "rio-de-janeiro":     ("rio-kueste", "rio-de-janeiro",       "rio-de-janeiro"),
    "arraial-do-cabo":    ("rio-kueste", "rio-de-janeiro",       "arraial-do-cabo"),
    "buzios":             ("rio-kueste", "rio-de-janeiro",       "armacao-dos-buzios"),
    "angra-dos-reis":     ("rio-kueste", "rio-de-janeiro",       "angra-dos-reis"),
    "paraty":             ("rio-kueste", "rio-de-janeiro",       "paraty"),
}


def heute() -> str:
    return date.today().isoformat()


def erstelle_hash(inserat_id: str) -> str:
    return hashlib.md5(f"zap-{inserat_id}".encode()).hexdigest()


def _scrape_seite(
    bundesstaat: str,
    slug: str,
    seite: int,
    session: requests.Session,
) -> list[dict]:
    """
    Ruft eine Seite Suchergebnisse von der glue-api ab.
    Gibt Roheinträge (listing-Objekte) zurück.
    """
    offset = (seite - 1) * 24
    params = {
        "unitTypes":    "APARTMENT,HOME",
        "listingType":  "USED",
        "businessType": "SALE",
        "stateSlug":    bundesstaat,
        "citySlug":     slug,
        "categoryPage": "1",
        "size":         "24",
        "from":         str(offset),
        "portal":       "ZAP",
        "priceMax":     str(PREIS_MAX_BRL),
    }
    headers = {
        "Accept":   "application/json",
        "X-Domain": "www.zapimoveis.com.br",
        "Origin":   "https://www.zapimoveis.com.br",
        "Referer":  f"https://www.zapimoveis.com.br/venda/{bundesstaat}/{slug}/",
    }
    try:
        resp = session.get(
            "https://glue-api.zapimoveis.com.br/v2/listings",
            params=params,
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 403:
            log.error(
                "HTTP 403 — Cloudflare blockt diese IP. "
                "Dieses Skript funktioniert nur von Wohngebiets-/Mobilfunk-IPs, "
                "nicht von Datacenter-IPs (GitHub Actions, VPS etc.)."
            )
            return []
        if resp.status_code != 200:
            log.warning(f"  {bundesstaat}/{slug} S{seite}: HTTP {resp.status_code}")
            return []

        data = resp.json()
        listings_raw = (
            data.get("search", {})
                .get("result", {})
                .get("listings") or []
        )
        return listings_raw

    except Exception as e:
        log.warning(f"  Fehler {bundesstaat}/{slug} S{seite}: {e}")
        return []


def _parse_roheintrag(eintrag: dict, stadt_key: str, region: str, kurs: float) -> dict | None:
    """Wandelt einen Roh-API-Eintrag in ein Supabase-kompatibles Inserat um."""
    try:
        l = eintrag.get("listing") or eintrag

        ext_id = str(l.get("id", ""))

        preise = l.get("pricingInfos") or []
        preis_brl = None
        iptu_brl  = None
        condo_brl = None
        for p in (preise if isinstance(preise, list) else [preise]):
            if p.get("businessType") == "SALE":
                preis_brl = int(p.get("price", 0)) or None
                iptu_brl  = int(p.get("yearlyIptu", 0)) or None
                condo_brl = int(p.get("monthlyCondoFee", 0)) or None
                break

        if preis_brl is None or preis_brl > PREIS_MAX_BRL:
            return None

        zimmer_raw = l.get("bedrooms")
        zimmer = (
            int(zimmer_raw[0]) if isinstance(zimmer_raw, list) and zimmer_raw
            else (int(zimmer_raw) if zimmer_raw else None)
        )

        flaeche_raw = l.get("usableAreas") or l.get("totalAreas")
        flaeche = (
            int(flaeche_raw[0]) if isinstance(flaeche_raw, list) and flaeche_raw
            else (int(flaeche_raw) if flaeche_raw else None)
        )

        addr  = l.get("address") or {}
        point = addr.get("point") or {}
        lat = float(point["lat"]) if "lat" in point else None
        lng = float(point["lon"]) if "lon" in point else None

        link_obj = eintrag.get("link") or {}
        url = link_obj.get("href", "") if isinstance(link_obj, dict) else ""
        if not url:
            url = l.get("href", "")

        if not flaeche and url:
            flaeche = extrahiere_flaeche_aus_url(url)

        return {
            "quelle":           "zap",
            "externe_id":       ext_id or None,
            "titel":            None,
            "preis_brl":        preis_brl,
            "preis_eur":        round(preis_brl * kurs, 2),
            "flaeche_m2":       flaeche,
            "zimmer":           zimmer,
            "stadt":            stadt_key,
            "region":           region,
            "url":              url,
            "lat":              lat,
            "lng":              lng,
            "distanz_meer_km":  distanz_zum_meer(lat, lng),
            "eigentumsform":    (
                "casa" if "/casa-" in url
                else "apartamento" if "/apartamento-" in url
                else "unbekannt"
            ),
            "zustand":          "unbekannt",
            "ist_condominio":   bool(condo_brl and condo_brl > 0),
            "nebenkosten_info": (
                f"IPTU: R${iptu_brl}, Condo: R${condo_brl}"
                if iptu_brl else None
            ),
            "beschreibung":     None,
            "bilder":           "[]",
            "erstmals_gesehen": heute(),
            "zuletzt_gesehen":  heute(),
            "hash":             erstelle_hash(ext_id or url),
        }
    except Exception as e:
        log.debug(f"Eintrag übersprungen: {e}")
        return None


def scrape_alle_staedte(max_seiten: int = 3) -> list[dict]:
    """
    Scrapet alle 20 Zielstädte via direktem glue-api-Aufruf (kein Browser).
    Nur von Wohngebiets-/Mobilfunk-IPs nutzbar.
    """
    kurs = aktueller_kurs_brl_eur()
    log.info(f"ZAP lokal — Wechselkurs BRL→EUR: {kurs:.4f}")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.6367.82 Mobile Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9",
    })

    alle_inserate: list[dict] = []
    gesehen_ids:   set[str]   = set()

    for stadt_key, (region, bundesstaat, slug) in ZIELSTAEDTE.items():
        log.info(f"ZAP lokal — Stadt: {stadt_key}")
        stadt_inserate = 0

        for seite in range(1, max_seiten + 1):
            roheintraege = _scrape_seite(bundesstaat, slug, seite, session)

            if not roheintraege:
                if seite == 1:
                    log.warning(f"  Keine Ergebnisse für {stadt_key}")
                break

            neu = 0
            for roheintrag in roheintraege:
                inserat = _parse_roheintrag(roheintrag, stadt_key, region, kurs)
                if inserat is None:
                    continue
                ext_id = inserat.get("externe_id") or inserat["url"]
                if ext_id in gesehen_ids:
                    continue
                gesehen_ids.add(ext_id)
                alle_inserate.append(inserat)
                neu += 1

            log.info(f"  Seite {seite}: {neu} Inserate")
            stadt_inserate += neu
            time.sleep(1)

        log.info(f"  {stadt_key} gesamt: {stadt_inserate} Inserate")
        time.sleep(2)

    log.info(f"ZAP lokal Gesamt: {len(alle_inserate)} Inserate aus {len(ZIELSTAEDTE)} Städten")
    return alle_inserate


def main():
    """Einstiegspunkt: Scrapen + direkt in Supabase schreiben."""
    test_modus = "--test" in sys.argv

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if test_modus:
        log.info("=== ZAP Lokal — Testmodus (1 Stadt, 1 Seite) ===")
        # Nur fortaleza testen
        global ZIELSTAEDTE
        ZIELSTAEDTE = {
            "fortaleza": ("nordosten", "ceara", "fortaleza"),
        }
        inserate = scrape_alle_staedte(max_seiten=1)
    else:
        log.info("=== ZAP Lokal — Täglicher Run ===")
        inserate = scrape_alle_staedte(max_seiten=3)

    if not inserate:
        log.warning("Keine Inserate gefunden — Abbruch")
        sys.exit(1)

    from db.supabase_client import upsert_inserate, zaehle_alle_inserate
    result = upsert_inserate(inserate)
    log.info(f"Supabase: {len(result.data)} Datensätze geschrieben")

    gesamt = zaehle_alle_inserate()
    log.info(f"Gesamt in DB: {gesamt} Inserate")
    log.info("=== ZAP Lokal Run erfolgreich ===")


if __name__ == "__main__":
    main()
