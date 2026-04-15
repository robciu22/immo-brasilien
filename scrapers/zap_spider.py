"""
ZAP Imóveis Spider — Immobiliensuche Brasilien
Scrapet Kaufinserate in den 20 Zielstädten (Küstenorte) bis 2.200.000 BRL (~375.000 €).
Nutzt Playwright (headless=False) um Bot-Erkennung zu umgehen.
Daten werden über window.__NEXT_DATA__ ausgelesen (Next.js globale Variable nach Hydration).
"""

import time
import hashlib
import logging
from datetime import date
from playwright.sync_api import sync_playwright

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


def _tiefe_suche(obj, key: str):
    """Durchsucht rekursiv ein JSON-Objekt nach einem Schlüssel, gibt erste Fundstelle zurück."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            result = _tiefe_suche(v, key)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _tiefe_suche(item, key)
            if result is not None:
                return result
    return None


def parse_listings_aus_next_data(data: dict) -> list[dict]:
    """Extrahiert Inserate aus dem window.__NEXT_DATA__ JSON-Objekt."""
    listings_raw = None
    page_props = data.get("props", {}).get("pageProps", {})

    for pfad in [
        lambda pp: pp.get("initialState", {}).get("search", {}).get("result", {}).get("listings"),
        lambda pp: pp.get("initialData", {}).get("search", {}).get("result", {}).get("listings"),
        lambda pp: pp.get("serverData", {}).get("search", {}).get("result", {}).get("listings"),
        lambda pp: pp.get("initialState", {}).get("results", {}).get("listings"),
        lambda pp: pp.get("listings"),
    ]:
        try:
            candidate = pfad(page_props)
            if candidate:
                listings_raw = candidate
                break
        except Exception:
            continue

    # Fallback: rekursive Suche nach "listings"-Schlüssel
    if listings_raw is None:
        listings_raw = _tiefe_suche(data, "listings")

    if listings_raw is None:
        top_keys = list(page_props.keys()) if page_props else list(data.keys())
        log.warning(f"ZAP __NEXT_DATA__ — Listings-Key nicht gefunden. pageProps-Keys: {top_keys}")
        if page_props:
            for k, v in page_props.items():
                sub = list(v.keys()) if isinstance(v, dict) else type(v).__name__
                log.warning(f"  pageProps.{k}: {sub}")
        return []

    log.info(f"ZAP __NEXT_DATA__ — {len(listings_raw)} Roheinträge")

    listings = []
    for eintrag in listings_raw:
        try:
            # ZAP verschachtelt Inserat-Daten in .listing, manchmal direkt im Objekt
            l = eintrag.get("listing") or eintrag

            ext_id = str(l.get("id", ""))
            preise = l.get("pricingInfos") or []
            preis_brl = None
            iptu_brl  = None
            condo_brl = None
            for p in preise if isinstance(preise, list) else [preise]:
                if p.get("businessType") == "SALE":
                    preis_brl = int(p.get("price", 0)) or None
                    iptu_brl  = int(p.get("yearlyIptu", 0)) or None
                    condo_brl = int(p.get("monthlyCondoFee", 0)) or None
                    break

            if preis_brl is None or preis_brl > PREIS_MAX_BRL:
                continue

            zimmer_raw = l.get("bedrooms")
            zimmer = int(zimmer_raw[0]) if isinstance(zimmer_raw, list) and zimmer_raw else (int(zimmer_raw) if zimmer_raw else None)

            flaeche_raw = l.get("usableAreas") or l.get("totalAreas")
            flaeche = int(flaeche_raw[0]) if isinstance(flaeche_raw, list) and flaeche_raw else (int(flaeche_raw) if flaeche_raw else None)

            addr = l.get("address") or {}
            point = addr.get("point") or {}
            lat = float(point["lat"]) if "lat" in point else None
            lng = float(point["lon"]) if "lon" in point else None

            link_obj = eintrag.get("link") or {}
            url = link_obj.get("href", "") if isinstance(link_obj, dict) else ""
            if not url:
                url = l.get("href", "")

            if not flaeche and url:
                flaeche = extrahiere_flaeche_aus_url(url)

            listings.append({
                "externe_id":  ext_id or None,
                "preis_brl":   preis_brl,
                "zimmer":      zimmer,
                "flaeche_m2":  flaeche,
                "url":         url,
                "lat":         lat,
                "lng":         lng,
                "iptu_brl":    iptu_brl,
                "condo_brl":   condo_brl,
            })
        except Exception as e:
            log.debug(f"ZAP Eintrag übersprungen: {e}")
            continue

    return listings


def _parse_kandidaten(body: str, ct: str) -> list[dict]:
    """
    Gibt eine Liste von JSON-Objekten zurück die aus dem Response-Body extrahiert wurden.
    Unterstützt normales JSON und Next.js RSC-Streams (text/x-component).
    """
    import json, re
    kandidaten = []

    # Normales JSON-Objekt
    try:
        obj = json.loads(body)
        if isinstance(obj, dict):
            kandidaten.append(obj)
            return kandidaten
    except Exception:
        pass

    # RSC-Stream: Zeilen im Format  "<hex_id>:<json_fragment>"
    # Wir extrahieren alle Zeilen die mit einem JSON-Objekt oder -Array beginnen
    for line in body.splitlines():
        m = re.match(r'^[0-9a-f]+:([\[{].+)', line)
        if m:
            try:
                obj = json.loads(m.group(1))
                if isinstance(obj, (dict, list)):
                    kandidaten.append(obj)
            except Exception:
                pass

    return kandidaten


def _extrahiere_listings_aus_kandidat(data) -> list[dict]:
    """
    Extrahiert Roheinträge aus einem JSON-Objekt oder -Array.
    Priorität: Suchergebnisse > Tiefensuche > Empfehlungen (letzter Fallback).
    """
    if isinstance(data, list):
        # RSC-Array-Chunk: Tiefensuche nach "listings"
        gefunden = _tiefe_suche(data, "listings")
        if gefunden and isinstance(gefunden, list):
            return gefunden
        return []

    if not isinstance(data, dict):
        return []

    # 1) Bekannte Search-Ergebnis-Pfade (höchste Priorität)
    for pfad in [
        lambda d: d.get("search", {}).get("result", {}).get("listings"),
        lambda d: d.get("result", {}).get("listings"),
        lambda d: d.get("listings"),
    ]:
        try:
            c = pfad(data)
            if c and isinstance(c, list) and len(c) > 0:
                return c
        except Exception:
            continue

    # 2) Rekursive Tiefensuche nach "listings"
    gefunden = _tiefe_suche(data, "listings")
    if gefunden and isinstance(gefunden, list) and len(gefunden) > 0:
        return gefunden

    # 3) Fallback: glue-api /v2/recommendations (personalisiert, nicht stadtbezogen)
    recos = data.get("recommendations")
    if recos and isinstance(recos, list):
        eintraege = []
        for reco in recos:
            for score in (reco.get("scores") or []):
                entry = score.get("listing")
                if entry and isinstance(entry, dict):
                    eintraege.append(entry)
        if eintraege:
            return eintraege

    return []


def _extrahiere_listings_aus_api_responses(api_responses: list[dict]) -> list[dict]:
    """
    Durchsucht abgefangene API-Antworten (JSON + RSC) nach Inseraten.
    Unterstützt glue-api recommendations, Search-Ergebnisse und RSC-Streams.
    """
    alle = []
    gesehen_ids: set[str] = set()

    for resp in api_responses:
        body = resp.get("body", "")
        ct   = resp.get("ct", "")
        if not body:
            continue

        kandidaten = _parse_kandidaten(body, ct)

        listings_raw = []
        for kandidat in kandidaten:
            gefunden = _extrahiere_listings_aus_kandidat(kandidat)
            if gefunden:
                listings_raw = gefunden
                log.debug(f"  Kandidat in {resp['url'][:80]} → {len(listings_raw)} Roheinträge")
                break

        if not listings_raw:
            continue

        log.debug(f"  API-Response {resp['url'][:80]} → {len(listings_raw)} Roheinträge")

        for eintrag in listings_raw:
            try:
                l = eintrag.get("listing") or eintrag

                ext_id = str(l.get("id", ""))
                if ext_id and ext_id in gesehen_ids:
                    continue
                if ext_id:
                    gesehen_ids.add(ext_id)

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
                    continue

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

                alle.append({
                    "externe_id": ext_id or None,
                    "preis_brl":  preis_brl,
                    "zimmer":     zimmer,
                    "flaeche_m2": flaeche,
                    "url":        url,
                    "lat":        lat,
                    "lng":        lng,
                    "iptu_brl":   iptu_brl,
                    "condo_brl":  condo_brl,
                })
            except Exception as e:
                log.debug(f"ZAP API-Eintrag übersprungen: {e}")
                continue

    return alle


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

                # Fange JSON-API-Antworten während des Seitenladens ab
                api_responses: list[dict] = []

                def _on_response(response, _store=api_responses):
                    if response.status != 200:
                        return
                    r_url = response.url
                    is_glue = "glue-api" in r_url
                    is_zap  = "zapimoveis" in r_url or "olx" in r_url
                    if not (is_glue or is_zap):
                        return
                    ct = response.headers.get("content-type", "")
                    # glue-api: immer erfassen (kann auch text/plain o.ä. sein)
                    # zapimoveis.com.br: JSON + RSC-Stream (text/x-component)
                    if not is_glue and "json" not in ct and "x-component" not in ct:
                        return
                    try:
                        body = response.body().decode("utf-8", errors="ignore")
                        if body:
                            _store.append({"url": r_url, "body": body, "ct": ct})
                    except Exception:
                        pass

                page.on("response", _on_response)
                try:
                    page.goto(url, timeout=30000)
                    page.wait_for_timeout(4000 + seite * 500)
                except Exception as e:
                    log.warning(f"Fehler bei {stadt_key} Seite {seite}: {e}")
                    page.remove_listener("response", _on_response)
                    break
                finally:
                    page.remove_listener("response", _on_response)

                listings = _extrahiere_listings_aus_api_responses(api_responses)

                if not listings:
                    if seite == 1:
                        if api_responses:
                            for r in api_responses[:5]:
                                log.warning(
                                    f"  ZAP API ohne Listings [{r.get('ct','?')[:30]}]: "
                                    f"{r['url'][:100]} | {r['body'][:150]}"
                                )
                        else:
                            log.warning(f"  ZAP keine Antworten für {stadt_key}")
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
