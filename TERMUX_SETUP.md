# ZAP Spider — Einrichtung auf Android (Termux)

## Warum Termux?

ZAP Imóveis (zapimoveis.com.br) blockiert Datacenter-IPs (GitHub Actions, VPS) via
Cloudflare. Eine Mobilfunk-IP wird nicht geblockt. Termux auf dem Android-Smartphone
ermöglicht einen täglichen automatischen Run direkt von der Mobilfunk-IP.

---

## 1. Termux installieren

### Empfohlene Apps (in dieser Reihenfolge installieren)

| App | Zweck | Pflicht? |
|---|---|---|
| **Termux** | Terminal + Python-Umgebung | Ja |
| **Termux:Boot** | Startet crond automatisch nach Neustart | Empfohlen |
| **Termux:Widget** | Skripte per Homescreen-Widget starten | Optional |

### Installationsquelle

**Option A — F-Droid** (aktuell empfohlen):
- F-Droid installieren (f-droid.org → „Download F-Droid")
- In F-Droid nach **„Termux"** suchen — Entwickler: **„Termux Dev Team"**
- Paket-ID zur Kontrolle: `com.termux`
- Ebenso **„Termux:Boot"** (com.termux.boot) installieren

> **Hinweis:** Google plant ab September 2026 Einschränkungen für APK-Sideloading,
> die F-Droid betreffen könnten. Falls F-Droid nicht mehr funktioniert:

**Option B — Direkt von GitHub** (funktioniert auch ohne F-Droid):
- Termux APK-Releases: github.com/termux/termux-app/releases
- Neueste `termux-app_v*.apk` (arm64-v8a für moderne Android-Geräte) herunterladen
- Manuell installieren (ADB oder direkt auf dem Telefon)

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

### Automatischer Start nach Neustart (Termux:Boot)

Damit crond nach jedem Telefonstart automatisch läuft:

```bash
mkdir -p ~/.termux/boot
echo "crond" > ~/.termux/boot/start-crond.sh
chmod +x ~/.termux/boot/start-crond.sh
```

> Termux:Boot muss einmalig geöffnet worden sein, damit es sich als Boot-Handler
> registriert. Danach reicht die obige Datei.

### Cronjob anlegen

```bash
# Cronjob anlegen (täglich 10:00 Uhr)
crontab -e
```

Im Editor folgenden Eintrag hinzufügen:

```
0 10 * * * cd /data/data/com.termux/files/home/immo-brasilien && python -m scrapers.zap_local >> ~/zap_scrape.log 2>&1
```

Speichern: `Strg+X` → `Y` → `Enter`

crond manuell starten (einmalig nach Einrichtung):
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
