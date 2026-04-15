"""
ZAP Imóveis Spider — Immobiliensuche Brasilien
Scrapet Kaufinserate in den 20 Zielstädten (Küstenorte) bis 2.200.000 BRL (~375.000 €).
Nutzt Playwright (headless=False) um Bot-Erkennung zu umgehen.
Daten werden aus eingebettetem Next.js JSON extrahiert (gleiches OLX-Backend wie VivaReal).
"""

import re
import time
import hashlib
import logging
from datetime import date
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from scrapers.utils import aktueller_kurs_brl_eur
from scrapers.vivareal_spider import (
    KUESTENPUNKTE,
    distanz_zum_meer,
    extrahiere_flaeche_aus_url,
)

log = logging.getLogger(__name__)

PREIS_MAX_BRL = 2_200_000

# Stadt → (region, bundesstaat-slug, zap-city-slug)
# ZAP verwendet Vollnamen für alle Bundesstaaten (kein sp/rj)
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


def parse_listings_aus_html(html: str) -> list[dict]:
    """Extrahiert Inserate aus dem eingebetteten Next.js JSON (gleiches Format wie VivaReal)."""
    soup = BeautifulSoup(html, "html.parser")

    for s in soup.find_all("script"):
        text = s.string or ""
        if "mainValue" not in text:
            continue

        unescaped = text.replace('\\"', '"')

        ids     = re.findall(r'"id":"(\d{8,12})"', unescaped)
        preise  = re.findall(r'"mainValue":(\d+)', unescaped)
        zimmer  = re.findall(r'"bedrooms":\[(\d+)\]', unescaped)
        urls    = re.findall(r'"href":"(https://www\.zapimoveis[^"]+/imovel/[^"]+)"', unescaped)
        iptu    = re.findall(r'"iptu":(\d+)', unescaped)
        condo   = re.findall(r'"condominium":(\d+)', unescaped)
        lats    = re.findall(r'"lat":([-\d.]+)', unescaped)
        lngs    = re.findall(r'"lon":([-\d.]+)', unescaped)

        listings = []
        for i in range(len(preise)):
            preis_brl = int(preise[i])
            if preis_brl > PREIS_MAX_BRL:
                continue

            url = urls[i] if i < len(urls) else ""
            flaeche = extrahiere_flaeche_aus_url(url)

            lat = float(lats[i]) if i < len(lats) else None
            lng = float(lngs[i]) if i < len(lngs) else None

            listings.append({
                "externe_id":  ids[i] if i < len(ids) else None,
                "preis_brl":   preis_brl,
                "zimmer":      int(zimmer[i]) if i < len(zimmer) else None,
                "flaeche_m2":  flaeche,
                "url":         url,
                "lat":         lat,
                "lng":         lng,
                "iptu_brl":    int(iptu[i]) if i < len(iptu) else None,
                "condo_brl":   int(condo[i]) if i < len(condo) else None,
            })

        return listings

    return []


def scrape_alle_staedte(max_seiten: int = 3) -> list[dict]:
    """
    Scrapet alle 20 Zielstädte auf ZAP Imóveis, bis zu max_seiten pro Stadt.
    Gibt eine Liste von Inseraten zurück.
    """
    kurs = aktueller_kurs_brl_eur()
    log.info(f"ZAP — Wechselkurs BRL→EUR: {kurs:.4f}")

    alle_inserate = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
        )
        page = ctx.new_page()

        # Warm-up: ZAP-Startseite besuchen damit Bot-Erkennung die Session akzeptiert
        try:
            page.goto("https://www.zapimoveis.com.br/", timeout=15000)
            page.wait_for_timeout(3000)
            log.info("ZAP Warm-up OK")
        except Exception:
            pass

        for stadt_key, (region, bundesstaat, slug) in ZIELSTAEDTE.items():
            log.info(f"ZAP Scrape Stadt: {stadt_key}")

            for seite in range(1, max_seiten + 1):
                url = (
                    f"https://www.zapimoveis.com.br/venda/{bundesstaat}/{slug}/"
                    f"?tipo=residencial_apartamento,residencial_casa"
                    f"&preco__lte={PREIS_MAX_BRL}"
                    f"&pagina={seite}"
                )

                try:
                    page.goto(url, timeout=30000)
                    page.wait_for_timeout(4000 + seite * 500)
                    html = page.content()
                except Exception as e:
                    log.warning(f"Fehler bei {stadt_key} Seite {seite}: {e}")
                    break

                listings = parse_listings_aus_html(html)
                if not listings:
                    break

                log.info(f"  Seite {seite}: {len(listings)} Inserate")

                for l in listings:
                    inserat = {
                        "quelle":           "zap",
                        "externe_id":       l["externe_id"],
                        "titel":            None,
                        "preis_brl":        l["preis_brl"],
                        "preis_eur":        round(l["preis_brl"] * kurs, 2),
                        "flaeche_m2":       l["flaeche_m2"],
                        "zimmer":           l["zimmer"],
                        "stadt":            stadt_key,
                        "region":           region,
                        "url":              l["url"],
                        "lat":              l["lat"],
                        "lng":              l["lng"],
                        "distanz_meer_km":  distanz_zum_meer(l["lat"], l["lng"]),
                        "eigentumsform":    "casa" if "/casa-" in l["url"] else "apartamento" if "/apartamento-" in l["url"] else "unbekannt",
                        "zustand":          "unbekannt",
                        "ist_condominio":   bool(l.get("condo_brl") and l["condo_brl"] > 0),
                        "nebenkosten_info": (
                            f"IPTU: R${l['iptu_brl']}, Condo: R${l['condo_brl']}"
                            if l["iptu_brl"] else None
                        ),
                        "beschreibung":     None,
                        "bilder":           "[]",
                        "erstmals_gesehen": heute(),
                        "zuletzt_gesehen":  heute(),
                        "hash":             erstelle_hash(l["externe_id"] or l["url"]),
                    }
                    alle_inserate.append(inserat)

                time.sleep(2)

        browser.close()

    log.info(f"ZAP Gesamt: {len(alle_inserate)} Inserate aus {len(ZIELSTAEDTE)} Städten")
    return alle_inserate


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    inserate = scrape_alle_staedte(max_seiten=2)
    print(f"\n=== ZAP Ergebnis: {len(inserate)} Inserate ===")
    for ins in inserate[:5]:
        print(
            f"  {ins['stadt']:20} | R$ {ins['preis_brl']:>9,}"
            f" | ~{ins['preis_eur']:>7,.0f} EUR"
            f" | {ins['zimmer'] or '?'} Zi"
            f" | {ins['flaeche_m2'] or '?'} m²"
            f" | {ins['distanz_meer_km'] or '?'} km Meer"
        )
