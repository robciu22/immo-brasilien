"""
VivaReal Spider — Immobiliensuche Brasilien
Scrapet Kaufinserate in den 17 Zielstädten (Küstenorte) bis 1.400.000 BRL (~250.000 €).
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

PREIS_MAX_BRL = 2_200_000

# Stadt → (region, bundesstaat-kuerzel, vivareal-slug)
ZIELSTAEDTE = {
    # Nordosten
    "fortaleza":          ("nordosten",  "ceara",               "fortaleza"),
    "natal":              ("nordosten",  "rio-grande-do-norte",  "natal"),
    "recife":             ("nordosten",  "pernambuco",           "recife"),
    "salvador":           ("nordosten",  "bahia",                "salvador"),
    "maceio":             ("nordosten",  "alagoas",              "maceio"),
    "maragogi":           ("nordosten",  "alagoas",              "maragogi"),
    "porto-seguro":       ("nordosten",  "bahia",                "porto-seguro"),
    "itacare":            ("nordosten",  "bahia",                "itacare"),
    # Süden
    "florianopolis":      ("sueden",     "santa-catarina",       "florianopolis"),
    "balneario-camboriu": ("sueden",     "santa-catarina",       "balneario-camboriu"),
    "guaruja":            ("sueden",     "sao-paulo",            "guaruja"),
    "santos":             ("sueden",     "sao-paulo",            "santos"),
    # Rio-Küste
    "rio-de-janeiro":     ("rio-kueste", "rio-de-janeiro",       "rio-de-janeiro"),
    "arraial-do-cabo":    ("rio-kueste", "rio-de-janeiro",       "arraial-do-cabo"),
    "buzios":             ("rio-kueste", "rio-de-janeiro",       "armacao-dos-buzios"),
    "angra-dos-reis":     ("rio-kueste", "rio-de-janeiro",       "angra-dos-reis"),
    "paraty":             ("rio-kueste", "rio-de-janeiro",       "paraty"),
}

# Küstenpunkte für Distanzberechnung (lat, lng)
# Dichtes Raster ~alle 500m entlang der tatsächlichen Küstenlinie
KUESTENPUNKTE = [
    # Fortaleza (CE) — Barra do Ceará bis Praia do Futuro (~20 Punkte)
    (-3.740, -38.740), (-3.739, -38.720), (-3.738, -38.700), (-3.736, -38.680),
    (-3.734, -38.660), (-3.732, -38.640), (-3.730, -38.620), (-3.728, -38.600),
    (-3.726, -38.580), (-3.724, -38.560), (-3.722, -38.540), (-3.720, -38.520),
    (-3.718, -38.500), (-3.716, -38.480), (-3.714, -38.460), (-3.712, -38.440),
    (-3.711, -38.420), (-3.710, -38.400), (-3.700, -38.380), (-3.690, -38.360),

    # Natal (RN) — Ponta Negra bis Praia do Forte (~22 Punkte)
    # Ponta Negra (südlich, Küste läuft nord-süd)
    (-5.882, -35.177), (-5.870, -35.178), (-5.858, -35.180), (-5.846, -35.182),
    (-5.834, -35.184), (-5.822, -35.187), (-5.810, -35.190), (-5.798, -35.193),
    (-5.786, -35.196), (-5.774, -35.199), (-5.762, -35.202), (-5.750, -35.204),
    (-5.738, -35.205), (-5.726, -35.205), (-5.714, -35.204), (-5.702, -35.202),
    (-5.690, -35.200), (-5.678, -35.197), (-5.666, -35.193), (-5.654, -35.188),
    (-5.642, -35.183), (-5.630, -35.177),

    # Recife (PE) — Boa Viagem bis Olinda (~18 Punkte)
    (-7.960, -34.840), (-7.975, -34.845), (-7.990, -34.852), (-8.005, -34.860),
    (-8.020, -34.868), (-8.035, -34.874), (-8.050, -34.878), (-8.065, -34.882),
    (-8.080, -34.885), (-8.095, -34.888), (-8.110, -34.892), (-8.125, -34.898),
    (-8.140, -34.905), (-8.155, -34.912), (-8.170, -34.920), (-8.185, -34.928),
    (-8.200, -34.936), (-8.215, -34.944),

    # Salvador (BA) — Barra bis Itapuã (~40 Punkte, tatsächliche Orla-Linie)
    (-13.010, -38.532), (-13.008, -38.524), (-13.005, -38.516), (-13.003, -38.508),
    (-13.001, -38.500), (-12.999, -38.492), (-12.997, -38.484), (-12.994, -38.476),
    (-12.992, -38.468), (-12.990, -38.460), (-12.988, -38.452), (-12.986, -38.444),
    (-12.984, -38.436), (-12.982, -38.428), (-12.980, -38.420), (-12.978, -38.412),
    (-12.976, -38.404), (-12.974, -38.396), (-12.972, -38.388), (-12.970, -38.380),
    (-12.968, -38.372), (-12.966, -38.364), (-12.964, -38.356), (-12.962, -38.348),
    (-12.960, -38.340), (-12.958, -38.332), (-12.956, -38.324), (-12.954, -38.316),
    (-12.952, -38.308), (-12.950, -38.300),
    # Stella Maris bis Itapuã (Küste biegt Richtung Nordost)
    (-12.946, -38.378), (-12.940, -38.366), (-12.934, -38.354), (-12.928, -38.342),
    (-12.922, -38.332), (-12.916, -38.322), (-12.910, -38.313), (-12.904, -38.305),
    (-12.898, -38.297), (-12.892, -38.290),

    # Maceio (AL) — Pajuçara bis Praia do Frances (~18 Punkte)
    (-9.550, -35.678), (-9.568, -35.688), (-9.586, -35.698), (-9.604, -35.708),
    (-9.620, -35.716), (-9.636, -35.722), (-9.652, -35.728), (-9.668, -35.732),
    (-9.684, -35.736), (-9.700, -35.740), (-9.716, -35.743), (-9.732, -35.746),
    (-9.748, -35.749), (-9.764, -35.751), (-9.780, -35.753), (-9.796, -35.754),
    (-9.812, -35.755), (-9.828, -35.754),

    # Florianopolis (SC) — Atlantikküste Ost (~20 Punkte)
    (-27.390, -48.355), (-27.408, -48.357), (-27.426, -48.360), (-27.444, -48.363),
    (-27.462, -48.367), (-27.480, -48.372), (-27.498, -48.378), (-27.516, -48.385),
    (-27.534, -48.393), (-27.552, -48.403), (-27.570, -48.415), (-27.588, -48.428),
    (-27.606, -48.440), (-27.624, -48.451), (-27.642, -48.461), (-27.660, -48.471),
    (-27.678, -48.482), (-27.696, -48.494), (-27.714, -48.508), (-27.732, -48.522),
    # Nordküste / Lagoa-Seite
    (-27.470, -48.542), (-27.488, -48.558), (-27.506, -48.572), (-27.524, -48.584),
    (-27.542, -48.594), (-27.560, -48.602),

    # Balneario Camboriu (SC) — Hauptstrand (~10 Punkte)
    (-26.960, -48.608), (-26.968, -48.612), (-26.976, -48.616), (-26.984, -48.620),
    (-26.992, -48.624), (-27.000, -48.628), (-27.008, -48.631), (-27.016, -48.634),
    (-27.024, -48.636), (-27.032, -48.637),

    # Buzios (RJ) — Halbinsel mit mehreren Stränden (~15 Punkte)
    (-22.710, -41.848), (-22.718, -41.862), (-22.726, -41.876), (-22.734, -41.890),
    (-22.742, -41.904), (-22.750, -41.918), (-22.758, -41.930), (-22.764, -41.942),
    (-22.768, -41.952), (-22.763, -41.938), (-22.754, -41.922), (-22.745, -41.906),
    (-22.736, -41.890), (-22.727, -41.874), (-22.718, -41.858),

    # Angra dos Reis (RJ) — Baía da Ilha Grande (~12 Punkte)
    (-22.975, -44.272), (-22.983, -44.284), (-22.991, -44.296), (-22.999, -44.308),
    (-23.007, -44.318), (-23.015, -44.326), (-23.023, -44.332), (-23.031, -44.336),
    (-23.025, -44.320), (-23.015, -44.308), (-23.005, -44.298), (-22.995, -44.286),

    # Paraty (RJ) — Baía de Paraty (~10 Punkte)
    (-23.198, -44.674), (-23.206, -44.688), (-23.214, -44.702), (-23.222, -44.715),
    (-23.230, -44.727), (-23.238, -44.737), (-23.244, -44.745), (-23.236, -44.730),
    (-23.226, -44.717), (-23.216, -44.704),

    # Maragogi (AL) — Praia de Maragogi (~8 Punkte)
    (-9.008, -35.224), (-9.014, -35.218), (-9.020, -35.212), (-9.026, -35.207),
    (-9.032, -35.202), (-9.038, -35.197), (-9.044, -35.193), (-9.050, -35.189),

    # Porto Seguro (BA) — Orla Norte bis Sul (~10 Punkte)
    (-16.420, -39.065), (-16.430, -39.062), (-16.440, -39.059), (-16.450, -39.057),
    (-16.460, -39.055), (-16.470, -39.054), (-16.480, -39.053), (-16.490, -39.052),
    (-16.500, -39.052), (-16.510, -39.053),

    # Itacaré (BA) — Praias do sul (~8 Punkte)
    (-14.270, -38.992), (-14.278, -38.987), (-14.286, -38.982), (-14.294, -38.978),
    (-14.302, -38.974), (-14.310, -38.971), (-14.318, -38.968), (-14.326, -38.966),

    # Guarujá (SP) — Praia da Enseada bis Pitangueiras (~10 Punkte)
    (-23.970, -46.256), (-23.976, -46.248), (-23.982, -46.240), (-23.988, -46.232),
    (-23.994, -46.224), (-24.000, -46.218), (-24.006, -46.212), (-24.012, -46.207),
    (-24.018, -46.203), (-24.024, -46.200),

    # Santos (SP) — Orla da Praia (~10 Punkte)
    (-23.958, -46.334), (-23.960, -46.322), (-23.962, -46.310), (-23.964, -46.298),
    (-23.966, -46.286), (-23.968, -46.274), (-23.970, -46.262), (-23.972, -46.250),
    (-23.974, -46.238), (-23.976, -46.226),

    # Rio de Janeiro (RJ) — Barra da Tijuca bis Recreio (~15 Punkte)
    (-22.988, -43.365), (-22.990, -43.350), (-22.992, -43.335), (-22.994, -43.320),
    (-22.996, -43.305), (-22.998, -43.290), (-23.000, -43.275), (-23.002, -43.260),
    (-23.004, -43.245), (-23.006, -43.230), (-23.008, -43.215), (-23.010, -43.200),
    # Ipanema / Copacabana
    (-22.986, -43.195), (-22.984, -43.185), (-22.982, -43.175),

    # Arraial do Cabo (RJ) — Praia Grande / Praia dos Anjos (~8 Punkte)
    (-22.956, -42.026), (-22.962, -42.020), (-22.968, -42.014), (-22.974, -42.008),
    (-22.980, -42.002), (-22.986, -41.996), (-22.992, -41.991), (-22.998, -41.987),
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
