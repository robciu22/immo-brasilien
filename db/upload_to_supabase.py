"""
Liest die neueste JSONL-Datei aus output/ und schreibt Inserate in Supabase.
Duplikate werden per hash-Konflikt übersprungen.
"""

import json
import glob
import os
from supabase_client import upsert_inserate


def lade_neueste_jsonl() -> list[dict]:
    dateien = sorted(glob.glob("output/inserate_*.jsonl"))
    if not dateien:
        print("Keine JSONL-Datei gefunden.")
        return []
    datei = dateien[-1]
    print(f"Lade: {datei}")
    inserate = []
    with open(datei, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if zeile:
                inserate.append(json.loads(zeile))
    return inserate


def main():
    inserate = lade_neueste_jsonl()
    if not inserate:
        return

    print(f"{len(inserate)} Inserate geladen — schreibe in Supabase...")
    result = upsert_inserate(inserate)
    print(f"Fertig. {len(result.data)} Datensätze verarbeitet.")


if __name__ == "__main__":
    main()
