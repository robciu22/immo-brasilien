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
    client = get_client()
    result = (
        client.table("inserate")
        .upsert(inserate, on_conflict="hash")
        .execute()
    )
    return result


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
