-- Immobiliensuche Brasilien — Supabase Schema
-- Ausfuehren im Supabase SQL Editor

CREATE TABLE inserate (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  quelle            TEXT NOT NULL,        -- 'olx', 'zap', 'vivareal'
  externe_id        TEXT,                 -- ID auf der Quellplattform
  titel             TEXT,
  preis_brl         NUMERIC,
  preis_eur         NUMERIC,
  flaeche_m2        NUMERIC,
  zimmer            INTEGER,
  stadt             TEXT,
  region            TEXT,                 -- z.B. 'nordosten', 'sueden', 'rio-kueste'
  url               TEXT,
  lat               NUMERIC,
  lng               NUMERIC,
  distanz_meer_km   NUMERIC,
  eigentumsform     TEXT,                 -- 'escritura', 'posse', 'unbekannt'
  zustand           TEXT,                 -- 'neuwertig', 'gut', 'renovierungsbeduerftig', 'unbekannt'
  nebenkosten_info  TEXT,
  beschreibung      TEXT,
  bilder            JSONB DEFAULT '[]',
  erstmals_gesehen  DATE DEFAULT CURRENT_DATE,
  zuletzt_gesehen   DATE DEFAULT CURRENT_DATE,
  hash              TEXT UNIQUE,          -- Duplikat-Erkennung
  erstellt_am       TIMESTAMPTZ DEFAULT now()
);

-- Indizes fuer Dashboard-Filter
CREATE INDEX ON inserate (stadt);
CREATE INDEX ON inserate (preis_brl);
CREATE INDEX ON inserate (distanz_meer_km);
CREATE INDEX ON inserate (eigentumsform);
CREATE INDEX ON inserate (erstmals_gesehen);

-- View fuer Dashboard (mit EUR-Filter)
CREATE VIEW v_inserate AS
SELECT
  id, quelle, titel, preis_brl, preis_eur,
  flaeche_m2, zimmer, stadt, region,
  lat, lng, distanz_meer_km,
  eigentumsform, zustand,
  url, erstmals_gesehen, zuletzt_gesehen
FROM inserate
ORDER BY erstmals_gesehen DESC, preis_eur ASC;
