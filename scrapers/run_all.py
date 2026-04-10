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
    from scrapers.vivareal_spider import scrape_alle_staedte, heute
    from db.supabase_client import upsert_inserate, lade_neue_inserate_von_heute, zaehle_alle_inserate
    from notifications.telegram_bot import sende_scrape_zusammenfassung

    log.info("=== Immobiliensuche Brasilien — Täglicher Run ===")

    inserate = scrape_alle_staedte(max_seiten=3)
    log.info(f"Spider fertig: {len(inserate)} Inserate gesammelt")

    if not inserate:
        log.warning("Keine Inserate gefunden — Abbruch")
        sys.exit(1)

    result = upsert_inserate(inserate)
    log.info(f"Supabase: {len(result.data)} Datensätze geschrieben (Duplikate übersprungen)")

    # Telegram Alert
    heute_datum = heute()
    neue = lade_neue_inserate_von_heute(heute_datum)
    gesamt = zaehle_alle_inserate()
    log.info(f"Neue Inserate heute: {len(neue)} — Gesamt: {gesamt}")
    sende_scrape_zusammenfassung(neue, gesamt)

    log.info("=== Run erfolgreich ===")


if __name__ == "__main__":
    main()
