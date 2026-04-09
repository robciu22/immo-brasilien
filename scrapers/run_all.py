"""
Einstiegspunkt für GitHub Actions:
1. VivaReal Spider ausführen
2. Inserate in Supabase schreiben
3. Ergebnis loggen
"""

import logging
import sys
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def main():
    from scrapers.vivareal_spider import scrape_alle_staedte
    from db.supabase_client import upsert_inserate

    log.info("=== Immobiliensuche Brasilien — Täglicher Run ===")

    inserate = scrape_alle_staedte(max_seiten=3)
    log.info(f"Spider fertig: {len(inserate)} Inserate gesammelt")

    if not inserate:
        log.warning("Keine Inserate gefunden — Abbruch")
        sys.exit(1)

    result = upsert_inserate(inserate)
    log.info(f"Supabase: {len(result.data)} Datensätze geschrieben (Duplikate übersprungen)")
    log.info("=== Run erfolgreich ===")


if __name__ == "__main__":
    main()
