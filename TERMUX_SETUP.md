# ZAP Spider — Einrichtung auf Android (Termux)

## Warum Termux?

ZAP Imóveis (zapimoveis.com.br) blockiert Datacenter-IPs (GitHub Actions, VPS) via
Cloudflare. Eine Mobilfunk-IP wird nicht geblockt. Termux auf dem Android-Smartphone
ermöglicht einen täglichen automatischen Run direkt von der Mobilfunk-IP.

---

## 1. Termux installieren

**Wichtig:** Termux über **F-Droid** installieren, nicht über den Google Play Store
(die Play-Store-Version wird nicht mehr gepflegt).

- F-Droid App: https://f-droid.org
- Termux in F-Droid suchen und installieren

---

## 2. Grundpakete installieren

Terminal in Termux öffnen und folgende Befehle ausführen:

```bash
pkg update && pkg upgrade -y
pkg install python git openssh cronie -y
```

---

## 3. Projekt klonen

```bash
cd ~
git clone git@github.com:robciu22/immo-brasilien.git
cd immo-brasilien
```

SSH-Key für GitHub einrichten (einmalig):

```bash
ssh-keygen -t ed25519 -C "termux-android"
cat ~/.ssh/id_ed25519.pub
# Den angezeigten Key unter github.com → Settings → SSH Keys hinzufügen
```

---

## 4. Python-Abhängigkeiten installieren

```bash
cd ~/immo-brasilien
pip install requests supabase python-dotenv
```

> Playwright wird **nicht** benötigt — das lokale Skript verwendet nur `requests`.

---

## 5. Umgebungsvariablen einrichten

```bash
nano ~/immo-brasilien/.env
```

Inhalt (eigene Werte eintragen):

```
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJ...
```

Datei speichern: `Strg+X` → `Y` → `Enter`

---

## 6. Testlauf

```bash
cd ~/immo-brasilien
python -m scrapers.zap_local --test
```

Erwartete Ausgabe (Beispiel für Fortaleza):
```
INFO: ZAP lokal — Stadt: fortaleza
INFO:   Seite 1: 24 Inserate
INFO:   fortaleza gesamt: 24 Inserate
INFO: ZAP lokal Gesamt: 24 Inserate aus 1 Städten
INFO: Supabase: 24 Datensätze geschrieben
```

Wenn `HTTP 403` erscheint: Telefon ist mit einem WLAN verbunden das eine
Datacenter-IP-Range hat (selten, aber möglich). In dem Fall auf Mobilfunk wechseln.

---

## 7. Täglichen Cronjob einrichten

```bash
# crond-Daemon beim Termux-Start automatisch starten
echo "crond" >> ~/.bashrc

# Cronjob anlegen (täglich 10:00 Uhr)
crontab -e
```

Im Editor folgenden Eintrag hinzufügen:

```
0 10 * * * cd /data/data/com.termux/files/home/immo-brasilien && python -m scrapers.zap_local >> ~/zap_scrape.log 2>&1
```

Speichern: `Strg+X` → `Y` → `Enter`

crond starten:
```bash
crond
```

---

## 8. Termux im Hintergrund laufen lassen

Damit Android Termux nicht beendet:

1. **Termux-Benachrichtigung** aktiv lassen:  
   Termux → Seitenmenü → „Acquire Wakelock" aktivieren

2. **Akku-Optimierung deaktivieren**:  
   Android-Einstellungen → Apps → Termux → Akku → „Nicht optimieren"

---

## 9. Logs prüfen

```bash
tail -50 ~/zap_scrape.log
```

---

## Projekt aktuell halten

Vor dem Run holt Termux automatisch die neueste Version — dazu den Cronjob erweitern:

```
0 10 * * * cd /data/data/com.termux/files/home/immo-brasilien && git pull --quiet && python -m scrapers.zap_local >> ~/zap_scrape.log 2>&1
```
