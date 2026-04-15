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
import re
import sys
import time
import requests
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from scrapers.utils import aktueller_kurs_brl_eur

# Küstenpunkte für Distanzberechnung — kopiert aus vivareal_spider.py
# (direkter Import vermieden, da vivareal_spider Playwright lädt)
KUESTENPUNKTE = [
    (-3.740, -38.740), (-3.739, -38.720), (-3.738, -38.700), (-3.736, -38.680),
    (-3.734, -38.660), (-3.732, -38.640), (-3.730, -38.620), (-3.728, -38.600),
    (-3.726, -38.580), (-3.724, -38.560), (-3.722, -38.540), (-3.720, -38.520),
    (-3.718, -38.500), (-3.716, -38.480), (-3.714, -38.460), (-3.712, -38.440),
    (-3.711, -38.420), (-3.710, -38.400), (-3.700, -38.380), (-3.690, -38.360),
    (-5.882, -35.177), (-5.870, -35.178), (-5.858, -35.180), (-5.846, -35.182),
    (-5.834, -35.184), (-5.822, -35.187), (-5.810, -35.190), (-5.798, -35.193),
    (-5.786, -35.196), (-5.774, -35.199), (-5.762, -35.202), (-5.750, -35.204),
    (-5.738, -35.205), (-5.726, -35.205), (-5.714, -35.204), (-5.702, -35.202),
    (-5.690, -35.200), (-5.678, -35.197), (-5.666, -35.193), (-5.654, -35.188),
    (-5.642, -35.183), (-5.630, -35.177),
    (-7.960, -34.840), (-7.975, -34.845), (-7.990, -34.852), (-8.005, -34.860),
    (-8.020, -34.868), (-8.035, -34.874), (-8.050, -34.878), (-8.065, -34.882),
    (-8.080, -34.885), (-8.095, -34.888), (-8.110, -34.892), (-8.125, -34.898),
    (-8.140, -34.905), (-8.155, -34.912), (-8.170, -34.920), (-8.185, -34.928),
    (-8.200, -34.936), (-8.215, -34.944),
    (-13.010, -38.532), (-13.008, -38.524), (-13.005, -38.516), (-13.003, -38.508),
    (-13.001, -38.500), (-12.999, -38.492), (-12.997, -38.484), (-12.994, -38.476),
    (-12.992, -38.468), (-12.990, -38.460), (-12.988, -38.452), (-12.986, -38.444),
    (-12.984, -38.436), (-12.982, -38.428), (-12.980, -38.420), (-12.978, -38.412),
    (-12.976, -38.404), (-12.974, -38.396), (-12.972, -38.388), (-12.970, -38.380),
    (-12.968, -38.372), (-12.966, -38.364), (-12.964, -38.356), (-12.962, -38.348),
    (-12.960, -38.340), (-12.958, -38.332), (-12.956, -38.324), (-12.954, -38.316),
    (-12.952, -38.308), (-12.950, -38.300),
    (-12.946, -38.378), (-12.940, -38.366), (-12.934, -38.354), (-12.928, -38.342),
    (-12.922, -38.332), (-12.916, -38.322), (-12.910, -38.313), (-12.904, -38.305),
    (-12.898, -38.297), (-12.892, -38.290),
    (-9.550, -35.678), (-9.568, -35.688), (-9.586, -35.698), (-9.604, -35.708),
    (-9.620, -35.716), (-9.636, -35.722), (-9.652, -35.728), (-9.668, -35.732),
    (-9.684, -35.736), (-9.700, -35.740), (-9.716, -35.743), (-9.732, -35.746),
    (-9.748, -35.749), (-9.764, -35.751), (-9.780, -35.753), (-9.796, -35.754),
    (-9.812, -35.755), (-9.828, -35.754),
    (-27.390, -48.355), (-27.408, -48.357), (-27.426, -48.360), (-27.444, -48.363),
    (-27.462, -48.367), (-27.480, -48.372), (-27.498, -48.378), (-27.516, -48.385),
    (-27.534, -48.393), (-27.552, -48.403), (-27.570, -48.415), (-27.588, -48.428),
    (-27.606, -48.440), (-27.624, -48.451), (-27.642, -48.461), (-27.660, -48.471),
    (-27.678, -48.482), (-27.696, -48.494), (-27.714, -48.508), (-27.732, -48.522),
    (-27.470, -48.542), (-27.488, -48.558), (-27.506, -48.572), (-27.524, -48.584),
    (-27.542, -48.594), (-27.560, -48.602),
    (-26.960, -48.608), (-26.968, -48.612), (-26.976, -48.616), (-26.984, -48.620),
    (-26.992, -48.624), (-27.000, -48.628), (-27.008, -48.631), (-27.016, -48.634),
    (-27.024, -48.636), (-27.032, -48.637),
    (-22.710, -41.848), (-22.718, -41.862), (-22.726, -41.876), (-22.734, -41.890),
    (-22.742, -41.904), (-22.750, -41.918), (-22.758, -41.930), (-22.764, -41.942),
    (-22.768, -41.952), (-22.763, -41.938), (-22.754, -41.922), (-22.745, -41.906),
    (-22.736, -41.890), (-22.727, -41.874), (-22.718, -41.858),
    (-22.975, -44.272), (-22.983, -44.284), (-22.991, -44.296), (-22.999, -44.308),
    (-23.007, -44.318), (-23.015, -44.326), (-23.023, -44.332), (-23.031, -44.336),
    (-23.025, -44.320), (-23.015, -44.308), (-23.005, -44.298), (-22.995, -44.286),
    (-23.198, -44.674), (-23.206, -44.688), (-23.214, -44.702), (-23.222, -44.715),
    (-23.230, -44.727), (-23.238, -44.737), (-23.244, -44.745), (-23.236, -44.730),
    (-23.226, -44.717), (-23.216, -44.704),
    (-9.008, -35.224), (-9.014, -35.218), (-9.020, -35.212), (-9.026, -35.207),
    (-9.032, -35.202), (-9.038, -35.197), (-9.044, -35.193), (-9.050, -35.189),
    (-6.226, -35.046), (-6.230, -35.040), (-6.234, -35.034), (-6.238, -35.028),
    (-6.242, -35.022), (-6.246, -35.016), (-6.250, -35.010), (-6.254, -35.004),
    (-2.796, -40.512), (-2.798, -40.506), (-2.800, -40.500), (-2.802, -40.494),
    (-2.804, -40.488), (-2.806, -40.482), (-2.808, -40.476), (-2.810, -40.470),
    (-16.420, -39.065), (-16.430, -39.062), (-16.440, -39.059), (-16.450, -39.057),
    (-16.460, -39.055), (-16.470, -39.054), (-16.480, -39.053), (-16.490, -39.052),
    (-16.500, -39.052), (-16.510, -39.053),
    (-14.270, -38.992), (-14.278, -38.987), (-14.286, -38.982), (-14.294, -38.978),
    (-14.302, -38.974), (-14.310, -38.971), (-14.318, -38.968), (-14.326, -38.966),
    (-23.432, -45.066), (-23.436, -45.072), (-23.440, -45.078), (-23.444, -45.084),
    (-23.448, -45.090), (-23.452, -45.096), (-23.456, -45.102), (-23.460, -45.108),
    (-23.464, -45.114), (-23.468, -45.120),
    (-23.970, -46.256), (-23.976, -46.248), (-23.982, -46.240), (-23.988, -46.232),
    (-23.994, -46.224), (-24.000, -46.218), (-24.006, -46.212), (-24.012, -46.207),
    (-24.018, -46.203), (-24.024, -46.200),
    (-23.958, -46.334), (-23.960, -46.322), (-23.962, -46.310), (-23.964, -46.298),
    (-23.966, -46.286), (-23.968, -46.274), (-23.970, -46.262), (-23.972, -46.250),
    (-23.974, -46.238), (-23.976, -46.226),
    (-22.988, -43.365), (-22.990, -43.350), (-22.992, -43.335), (-22.994, -43.320),
    (-22.996, -43.305), (-22.998, -43.290), (-23.000, -43.275), (-23.002, -43.260),
    (-23.004, -43.245), (-23.006, -43.230), (-23.008, -43.215), (-23.010, -43.200),
    (-22.986, -43.195), (-22.984, -43.185), (-22.982, -43.175),
    (-22.956, -42.026), (-22.962, -42.020), (-22.968, -42.014), (-22.974, -42.008),
    (-22.980, -42.002), (-22.986, -41.996), (-22.992, -41.991), (-22.998, -41.987),
]


def extrahiere_flaeche_aus_url(url: str) -> float | None:
    """'...120m2-venda...' → 120.0"""
    match = re.search(r"(\d+)m2", url)
    return float(match.group(1)) if match else None


def distanz_zum_meer(lat: float, lng: float) -> float | None:
    if lat is None or lng is None:
        return None
    from geopy.distance import geodesic
    return round(min(geodesic((lat, lng), p).km for p in KUESTENPUNKTE), 2)

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
    # unitTypes als Liste → erzeugt ?unitTypes=APARTMENT&unitTypes=HOME
    params = [
        ("unitTypes",    "APARTMENT"),
        ("unitTypes",    "HOME"),
        ("businessType", "SALE"),
        ("stateSlug",    bundesstaat),
        ("citySlug",     slug),
        ("size",         "24"),
        ("from",         str(offset)),
        ("portal",       "ZAP"),
    ]
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
            log.warning(f"  {bundesstaat}/{slug} S{seite}: HTTP {resp.status_code} | {resp.text[:300]!r}")
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
