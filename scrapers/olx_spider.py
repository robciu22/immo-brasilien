"""
OLX Brasil Spider — Immobiliensuche Brasilien
Scrapet Kaufinserate in den Zielstädten (Küstenorte) bis 1.000.000 BRL.
"""

import scrapy
import json
import time
import random
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from scrapers.utils import (
    ZIELSTAEDTE,
    KUESTENPUNKTE,
    erstelle_hash,
    bereinige_preis,
    bereinige_flaeche,
    aktueller_kurs_brl_eur,
    heute,
)

PREIS_MAX_BRL = 1_000_000

geolocator = Nominatim(user_agent="immo-brasilien-suche-v1", timeout=10)


def distanz_zum_meer(lat: float, lng: float) -> float:
    """Minimale Distanz zur nächstgelegenen Küste in km."""
    return round(
        min(geodesic((lat, lng), punkt).km for punkt in KUESTENPUNKTE), 2
    )


def geocode(adresse: str, stadt: str) -> tuple[float, float] | tuple[None, None]:
    """Adresse → (lat, lng). Rate-Limit: 1 Request/Sek."""
    try:
        time.sleep(1.1)  # Nominatim-Limit
        loc = geolocator.geocode(f"{adresse}, {stadt}, Brasil")
        if loc:
            return loc.latitude, loc.longitude
    except Exception:
        pass
    return None, None


class OLXSpider(scrapy.Spider):
    name = "olx"
    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS": 1,
        "USER_AGENT": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "ROBOTSTXT_OBEY": True,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kurs = aktueller_kurs_brl_eur()
        self.logger.info(f"Wechselkurs BRL→EUR: {self.kurs:.4f}")

    def start_requests(self):
        for stadt, (region, estado) in ZIELSTAEDTE.items():
            # OLX-URL mit Preis- und Kategoriefilter
            url = (
                f"https://www.olx.com.br/imoveis/venda/casas-residencias-comercios"
                f"/{stadt}?pe={PREIS_MAX_BRL}&o=1"
            )
            yield scrapy.Request(
                url,
                callback=self.parse_liste,
                meta={"stadt": stadt, "region": region},
                dont_filter=False,
            )

    def parse_liste(self, response):
        """Listenansicht — Links zu Detailseiten extrahieren."""
        stadt = response.meta["stadt"]
        region = response.meta["region"]

        # OLX rendert Inserate als JSON im HTML-Script-Tag
        # Alternativ: CSS-Selektoren falls kein JSON
        inserat_links = response.css("a.olx-ad-card__link::attr(href)").getall()

        if not inserat_links:
            self.logger.warning(f"Keine Inserate gefunden für {stadt} — ggf. Selektor anpassen")

        for link in inserat_links:
            yield scrapy.Request(
                link,
                callback=self.parse_detail,
                meta={"stadt": stadt, "region": region},
            )

        # Nächste Seite
        naechste = response.css("a[data-testid='pagination-next']::attr(href)").get()
        if naechste:
            yield scrapy.Request(
                naechste,
                callback=self.parse_liste,
                meta={"stadt": stadt, "region": region},
            )

    def parse_detail(self, response):
        """Detailseite — vollständiges Inserat extrahieren."""
        stadt = response.meta["stadt"]
        region = response.meta["region"]

        titel = response.css("h1.olx-text--title-large::text").get("").strip()
        preis_text = response.css("h2.olx-text--title-large::text").get("")
        preis_brl = bereinige_preis(preis_text)

        if not preis_brl or preis_brl > PREIS_MAX_BRL:
            return  # Ausserhalb Budget

        beschreibung = " ".join(
            response.css("div.olx-description p::text").getall()
        ).strip()

        # Kennzahlen aus den Detail-Chips
        chips = {
            chip.css("span:first-child::text").get("").lower(): chip.css("span:last-child::text").get("")
            for chip in response.css("li.olx-ad-properties__item")
        }

        flaeche_m2 = bereinige_flaeche(chips.get("área total", chips.get("área útil", "")))
        zimmer_text = chips.get("quartos", chips.get("dormitórios", ""))
        zimmer = int(zimmer_text) if zimmer_text.isdigit() else None

        # Adresse
        adresse = response.css("span.olx-location-tag__text::text").get("").strip()

        # Geocoding
        lat, lng = geocode(adresse, stadt)
        distanz = distanz_zum_meer(lat, lng) if lat else None

        # Bilder
        bilder = response.css("img.olx-carousel__image::attr(src)").getall()[:5]

        # externe ID aus URL
        externe_id = response.url.split("-")[-1].rstrip("/")

        inserat = {
            "quelle": "olx",
            "externe_id": externe_id,
            "titel": titel,
            "preis_brl": preis_brl,
            "preis_eur": round(preis_brl * self.kurs, 2) if preis_brl else None,
            "flaeche_m2": flaeche_m2,
            "zimmer": zimmer,
            "stadt": stadt,
            "region": region,
            "url": response.url,
            "lat": lat,
            "lng": lng,
            "distanz_meer_km": distanz,
            "eigentumsform": "unbekannt",   # wird durch Claude Enrichment befüllt
            "zustand": "unbekannt",
            "nebenkosten_info": None,
            "beschreibung": beschreibung[:2000],  # Limit für DB
            "bilder": json.dumps(bilder),
            "erstmals_gesehen": heute(),
            "zuletzt_gesehen": heute(),
            "hash": erstelle_hash(preis_brl, flaeche_m2, response.url),
        }

        yield inserat
