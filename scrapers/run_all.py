"""
Einstiegspunkt für GitHub Actions:
1. VivaReal Spider ausführen
2. ZAP Imóveis Spider ausführen
3. Inserate in Supabase schreiben
4. Ergebnis loggen
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
    from scrapers.vivareal_spider import scrape_alle_staedte as vivareal_scrape, heute
    from scrapers.zap_spider import scrape_alle_staedte as zap_scrape
    from db.supabase_client import upsert_inserate, lade_neue_inserate_von_heute, zaehle_alle_inserate, markiere_inaktive_inserate
    from notifications.telegram_bot import sende_scrape_zusammenfassung

    log.info("=== Immobiliensuche Brasilien — Täglicher Run ===")

    inserate_vivareal = vivareal_scrape(max_seiten=3)
    log.info(f"VivaReal Spider fertig: {len(inserate_vivareal)} Inserate")

    inserate_zap = zap_scrape(max_seiten=3)
    log.info(f"ZAP Spider fertig: {len(inserate_zap)} Inserate")

    inserate = inserate_vivareal + inserate_zap
    log.info(f"Gesamt gesammelt: {len(inserate)} Inserate (beide Portale)")

    if not inserate:
        log.warning("Keine Inserate gefunden — Abbruch")
        sys.exit(1)

    # Hashes die bereits heute in der DB sind (vor diesem Run)
    heute_datum = heute()
    bereits_heute_hashes = {ins["hash"] for ins in lade_neue_inserate_von_heute(heute_datum)}

    result = upsert_inserate(inserate)
    log.info(f"Supabase: {len(result.data)} Datensätze geschrieben (Duplikate übersprungen)")

    # Bereinigung: Inserate die seit 14 Tagen nicht mehr gesehen → inaktiv
    deaktiviert = markiere_inaktive_inserate(tage=14)
    if deaktiviert > 0:
        log.info(f"Bereinigung: {deaktiviert} Inserate als inaktiv markiert")

    # Telegram Alert: nur Inserate die in DIESEM Run neu dazugekommen sind
    scraped_hashes = {ins.get("hash") for ins in inserate}
    alle_heute = lade_neue_inserate_von_heute(heute_datum)
    neue = [ins for ins in alle_heute if ins["hash"] in scraped_hashes and ins["hash"] not in bereits_heute_hashes]
    gesamt = zaehle_alle_inserate()
    log.info(f"Neue Inserate in diesem Run: {len(neue)} — Gesamt: {gesamt}")
    sende_scrape_zusammenfassung(neue, gesamt, deaktiviert)

    log.info("=== Run erfolgreich ===")


if __name__ == "__main__":
    main()
