"""
Telegram Alerts — sendet Zusammenfassung neuer Inserate nach dem täglichen Scrape.
Benötigt: TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID als Umgebungsvariablen.
"""

import os
import logging
import requests

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _token() -> str | None:
    return os.getenv("TELEGRAM_BOT_TOKEN")


def _chat_id() -> str | None:
    return os.getenv("TELEGRAM_CHAT_ID")


def sende_nachricht(text: str) -> bool:
    """Sendet eine Nachricht via Telegram Bot API. Gibt True zurück bei Erfolg."""
    token = _token()
    chat_id = _chat_id()

    if not token or not chat_id:
        log.warning("Telegram nicht konfiguriert (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID fehlen)")
        return False

    try:
        response = requests.post(
            TELEGRAM_API.format(token=token),
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        response.raise_for_status()
        log.info("Telegram Alert gesendet")
        return True
    except Exception as e:
        log.error(f"Telegram Fehler: {e}")
        return False


def sende_scrape_zusammenfassung(neue_inserate: list[dict], gesamt_inserate: int) -> bool:
    """
    Sendet eine kompakte Zusammenfassung nach dem täglichen Scrape.
    Schickt bis zu 5 Einzel-Listings der günstigsten neuen Inserate.
    """
    if not neue_inserate:
        text = (
            "🏠 <b>Immo Brasilien — Täglicher Run</b>\n\n"
            f"Keine neuen Inserate heute.\n"
            f"Gesamt in Datenbank: {gesamt_inserate}"
        )
        return sende_nachricht(text)

    anzahl = len(neue_inserate)
    # Günstigste zuerst
    top = sorted(neue_inserate, key=lambda x: x.get("preis_eur", 999999))[:5]

    zeilen = []
    for ins in top:
        stadt = ins.get("stadt", "?").replace("-", " ").title()
        preis_eur = ins.get("preis_eur", 0)
        preis_brl = ins.get("preis_brl", 0)
        zimmer = ins.get("zimmer")
        flaeche = ins.get("flaeche_m2")
        distanz = ins.get("distanz_meer_km")
        url = ins.get("url", "")

        details = []
        if zimmer:
            details.append(f"{zimmer} Zi")
        if flaeche:
            details.append(f"{flaeche:.0f} m²")
        if distanz:
            details.append(f"{distanz:.1f} km Meer")

        detail_str = " · ".join(details)
        zeile = (
            f"• <b>{stadt}</b> — {preis_eur:,.0f} € (R$ {preis_brl:,.0f})\n"
            f"  {detail_str}\n"
            f"  <a href=\"{url}\">→ VivaReal</a>"
        )
        zeilen.append(zeile)

    listings_text = "\n\n".join(zeilen)

    text = (
        f"🏠 <b>Immo Brasilien — {anzahl} neue Inserate!</b>\n\n"
        f"{listings_text}\n\n"
        f"<i>Gesamt in DB: {gesamt_inserate}</i>"
    )

    return sende_nachricht(text)
