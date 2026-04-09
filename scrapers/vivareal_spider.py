"""
VivaReal Spider — Immobiliensuche Brasilien
Scrapet Kaufinserate in den 10 Zielstädten (Küstenorte) bis 1.000.000 BRL.
Nutzt Playwright (headless=False) um Cloudflare zu umgehen.
Daten werden aus eingebettetem Next.js JSON extrahiert.
"""

import re
import time
import hashlib
import logging
from datetime import date
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from scrapers.utils import aktueller_kurs_brl_eur

log = logging.getLogger(__name__)

PREIS_MAX_BRL = 1_000_000

# Stadt → (region, bundesstaat-kuerzel, vivareal-slug)
ZIELSTAEDTE = {
    "fortaleza":          ("nordosten",  "ceara",              "fortaleza"),
    "natal":              ("nordosten",  "rio-grande-do-norte", "natal"),
    "recife":             ("nordosten",  "pernambuco",         "recife"),
    "salvador":           ("nordosten",  "bahia",              "salvador"),
    "maceio":             ("nordosten",  "alagoas",            "maceio"),
    "florianopolis":      ("sueden",     "santa-catarina",     "florianopolis"),
    "balneario-camboriu": ("sueden",     "santa-catarina",     "balneario-camboriu"),
    "buzios":             ("rio-kueste", "rio-de-janeiro",     "armacao-dos-buzios"),
    "angra-dos-reis":     ("rio-kueste", "rio-de-janeiro",     "angra-dos-reis"),
    "paraty":             ("rio-kueste", "rio-de-janeiro",     "paraty"),
}

# Küstenpunkte für Distanzberechnung (lat, lng)
KUESTENPUNKTE = [
    (-3.7172,  -38.5433),
    (-5.7945,  -35.2110),
    (-8.0476,  -34.8770),
    (-12.9714, -38.5014),
    (-9.6658,  -35.7350),
    (-27.5954, -48.5480),
    (-26.9908, -48.6348),
    (-22.7469, -41.8819),
    (-23.0064, -44.3178),
    (-23.2237, -44.7130),
]


def heute() -> str:
    return date.today().isoformat()


def erstelle_hash(inserat_id: str, quelle: str = "vivareal") -> str:
    return hashlib.md5(f"{quelle}-{inserat_id}".encode()).hexdigest()


def extrahiere_flaeche_aus_url(url: str) -> float | None:
    """'...120m2-venda...' → 120.0"""
    match = re.search(r"(\d+)m2", url)
    return float(match.group(1)) if match else None


def parse_listings_aus_html(html: str) -> list[dict]:
    """Extrahiert Inserate aus dem eingebetteten Next.js JSON."""
    soup = BeautifulSoup(html, "html.parser")

    for s in soup.find_all("script"):
        text = s.string or ""
        if "mainValue" not in text:
            continue

        unescaped = text.replace('\\"', '"')

        ids     = re.findall(r'"id":"(\d{8,12})"', unescaped)
        preise  = re.findall(r'"mainValue":(\d+)', unescaped)
        zimmer  = re.findall(r'"bedrooms":\[(\d+)\]', unescaped)
        urls    = re.findall(r'"href":"(https://www\.vivareal[^"]+/imovel/[^"]+)"', unescaped)
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
                "externe_id":    ids[i] if i < len(ids) else None,
                "preis_brl":     preis_brl,
                "zimmer":        int(zimmer[i]) if i < len(zimmer) else None,
                "flaeche_m2":    flaeche,
                "url":           url,
                "lat":           lat,
                "lng":           lng,
                "iptu_brl":      int(iptu[i]) if i < len(iptu) else None,
                "condo_brl":     int(condo[i]) if i < len(condo) else None,
            })

        return listings

    return []


def distanz_zum_meer(lat: float, lng: float) -> float | None:
    if lat is None or lng is None:
        return None
    from geopy.distance import geodesic
    return round(min(geodesic((lat, lng), p).km for p in KUESTENPUNKTE), 2)


def scrape_alle_staedte(max_seiten: int = 3) -> list[dict]:
    """
    Scrapet alle 10 Zielstädte, bis zu max_seiten pro Stadt.
    Gibt eine Liste von Inseraten zurück.
    """
    kurs = aktueller_kurs_brl_eur()
    log.info(f"Wechselkurs BRL→EUR: {kurs:.4f}")

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

        for stadt_key, (region, bundesstaat, slug) in ZIELSTAEDTE.items():
            log.info(f"Scrape Stadt: {stadt_key}")

            for seite in range(1, max_seiten + 1):
                url = (
                    f"https://www.vivareal.com.br/venda/{bundesstaat}/{slug}/"
                    f"?tipos=casa_residencial,apartamento"
                    f"&preco_maximo={PREIS_MAX_BRL}"
                    f"&pagina={seite}"
                )

                try:
                    page.goto(url, timeout=30000)
                    page.wait_for_timeout(4000 + seite * 500)  # etwas länger bei späteren Seiten
                    html = page.content()
                except Exception as e:
                    log.warning(f"Fehler bei {stadt_key} Seite {seite}: {e}")
                    break

                listings = parse_listings_aus_html(html)
                if not listings:
                    log.info(f"  Keine Inserate mehr auf Seite {seite} — stoppe für {stadt_key}")
                    break

                log.info(f"  Seite {seite}: {len(listings)} Inserate")

                for l in listings:
                    inserat = {
                        "quelle":           "vivareal",
                        "externe_id":       l["externe_id"],
                        "titel":            None,   # wird aus URL-Slug extrahierbar
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
                        "eigentumsform":    "unbekannt",
                        "zustand":          "unbekannt",
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

                time.sleep(2)  # Höfliche Pause zwischen Seiten

        browser.close()

    log.info(f"Gesamt: {len(alle_inserate)} Inserate aus {len(ZIELSTAEDTE)} Städten")
    return alle_inserate


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    inserate = scrape_alle_staedte(max_seiten=2)
    print(f"\n=== Ergebnis: {len(inserate)} Inserate ===")
    for ins in inserate[:5]:
        print(
            f"  {ins['stadt']:20} | R$ {ins['preis_brl']:>9,}"
            f" | ~{ins['preis_eur']:>7,.0f} EUR"
            f" | {ins['zimmer'] or '?'} Zi"
            f" | {ins['flaeche_m2'] or '?'} m²"
            f" | {ins['distanz_meer_km'] or '?'} km Meer"
        )
