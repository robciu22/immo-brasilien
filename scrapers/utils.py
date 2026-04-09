import hashlib
import re
import requests
from datetime import date
from dotenv import load_dotenv

load_dotenv()

ZIELSTAEDTE = {
    "fortaleza":            ("nordosten", "CE"),
    "natal":                ("nordosten", "RN"),
    "recife":               ("nordosten", "PE"),
    "salvador":             ("nordosten", "BA"),
    "maceio":               ("nordosten", "AL"),
    "florianopolis":        ("sueden",    "SC"),
    "balneario-camboriu":   ("sueden",    "SC"),
    "buzios":               ("rio-kueste","RJ"),
    "angra-dos-reis":       ("rio-kueste","RJ"),
    "paraty":               ("rio-kueste","RJ"),
}

# Referenzpunkte Kueste (lat, lng) fuer Distanzberechnung
KUESTENPUNKTE = [
    (-3.7172,  -38.5433),   # Fortaleza
    (-5.7945,  -35.2110),   # Natal
    (-8.0476,  -34.8770),   # Recife
    (-12.9714, -38.5014),   # Salvador
    (-9.6658,  -35.7350),   # Maceió
    (-27.5954, -48.5480),   # Florianópolis
    (-26.9908, -48.6348),   # Balneário Camboriú
    (-22.7469, -41.8819),   # Búzios
    (-23.0064, -44.3178),   # Angra dos Reis
    (-23.2237, -44.7130),   # Paraty
]


def erstelle_hash(preis_brl, flaeche_m2, url: str) -> str:
    """Eindeutiger Hash pro Inserat — verhindert Duplikate."""
    rohtext = f"{preis_brl}-{flaeche_m2}-{url}"
    return hashlib.md5(rohtext.encode()).hexdigest()


def bereinige_preis(text: str) -> float | None:
    """'R$ 850.000' → 850000.0"""
    if not text:
        return None
    zahlen = re.sub(r"[^\d]", "", text)
    return float(zahlen) if zahlen else None


def bereinige_flaeche(text: str) -> float | None:
    """'85 m²' → 85.0"""
    if not text:
        return None
    match = re.search(r"(\d+[\.,]?\d*)", text)
    return float(match.group(1).replace(",", ".")) if match else None


def aktueller_kurs_brl_eur() -> float:
    """Tagesaktueller BRL→EUR Kurs."""
    try:
        r = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "BRL", "symbols": "EUR"},
            timeout=5
        )
        return r.json()["rates"]["EUR"]
    except Exception:
        return 0.18  # Fallback-Kurs


def heute() -> str:
    return date.today().isoformat()
