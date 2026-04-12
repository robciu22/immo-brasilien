import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def upsert_inserate(inserate: list[dict]) -> dict:
    """Inserate in Supabase schreiben. Duplikate werden per hash-Konflikt übersprungen."""
    # Deduplizieren innerhalb des Batches (gleicher Hash darf nur einmal vorkommen)
    seen = set()
    unique = []
    for ins in inserate:
        h = ins.get("hash")
        if h not in seen:
            seen.add(h)
            unique.append(ins)

    client = get_client()
    result = (
        client.table("inserate")
        .upsert(unique, on_conflict="hash")
        .execute()
    )
    return result


def lade_neue_inserate_von_heute(datum: str) -> list[dict]:
    """Gibt alle Inserate zurück, die heute erstmals gesehen wurden."""
    client = get_client()
    result = (
        client.table("inserate")
        .select("*")
        .eq("erstmals_gesehen", datum)
        .execute()
    )
    return result.data


def zaehle_alle_inserate() -> int:
    """Gibt die Gesamtanzahl aller Inserate in der Datenbank zurück."""
    client = get_client()
    result = client.table("inserate").select("id", count="exact").execute()
    return result.count or 0


def markiere_inaktive_inserate(tage: int = 14) -> int:
    """
    Markiert Inserate als inaktiv, die seit mehr als `tage` Tagen nicht mehr gescraped wurden.
    Gibt die Anzahl deaktivierter Inserate zurück.
    """
    from datetime import date, timedelta
    client = get_client()
    grenze = (date.today() - timedelta(days=tage)).isoformat()
    result = (
        client.table("inserate")
        .update({"aktiv": False})
        .lt("zuletzt_gesehen", grenze)
        .eq("aktiv", True)
        .execute()
    )
    return len(result.data)


def lade_alle_inserate(max_preis_eur: float = 150000, max_distanz_meer: float = 50) -> list[dict]:
    """Inserate für Dashboard laden."""
    client = get_client()
    result = (
        client.table("v_inserate")
        .select("*")
        .lte("preis_eur", max_preis_eur)
        .lte("distanz_meer_km", max_distanz_meer)
        .execute()
    )
    return result.data
