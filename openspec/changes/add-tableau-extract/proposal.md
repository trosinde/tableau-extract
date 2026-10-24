# Proposal

## Why

Regionaldaten des Bundes, z. B. der BBSR-Wohnungsneubaubedarf 2023–2030 je Kreis, gibt es oft nur als interaktive Tableau-Karte ohne Datei-Download. Für eine reproduzierbare Pipeline (DVC, Parquet) brauchen wir diese Werte maschinenlesbar und exakt so, wie Tableau sie im Datenmodell hält. Abgelesene Farbklassen oder Tooltips sind keine Grundlage.

Die Zugangsprüfung (`docs/zugangsbericht.md`, Einstufung **A-lokal**) zeigt den Rahmen:

- Von einem Privatanschluss liefert die VizQL-`bootstrapSession` alle 400 Kreise mit Schlüssel, Name und Messwerten.
- Der View-CSV-Export (404 `missing-view`) und der Daten-/Kreuztabellen-Download (nicht angeboten) sind gesperrt.
- Aus Rechenzentrumsnetzen antwortet CloudFront mit 403.

## What Changes

- Neues Python-Paket `tableau_extract` mit CLI `tableau-extract "<url>"` und Python-API `extract(url, **opts)`.
- Die Eingabe-URL wird normalisiert. Einbettungsseiten (z. B. bbsr.bund.de mit Zustimmungs-Checkbox) werden mit einem Hinweis auf die Tableau-URL abgelehnt.
- Die Extraktionswege werden in fester Reihenfolge versucht:
  - **A** View-CSV-Export
  - **B** VizQL-Session per HTTP (Hauptweg)
  - **C** Daten-Download im Browser
  - **D** Netzwerkmitschnitt mit Playwright (Rückfallweg)
- Jeder Fehlversuch wird protokolliert. Sperren werden nicht umgangen.
- Laut Zugangsbericht werden **B und D voll umgesetzt**. A und C werden versucht und ihr Scheitern sauber protokolliert, aber nicht weiter ausgebaut.
- Die Ausgabe je Lauf liegt unter `out/<slug>/<UTC>_<sha8>/`:
  - `data_raw.csv`, `kreise.csv`, `kreise.parquet`, `meta.json`
  - `raw/` mit den unveränderten Rohantworten
  - `latest`-Verweis auf den neuesten Lauf
- Normalisierung:
  - `ags5` 5-stellig als Text
  - Zahlen gemäß dem Gebietsschema der Arbeitsmappe (z. B. `en_US`: `23,000` → 23000)
  - Klassenfelder mit `<feld>_typ = klasse`
  - Sonderwerte bleiben leer
- Vollständigkeitsprüfung gegen eine eingecheckte Kreis-Referenzliste (400 Kreise, Gebietsstand passend zum Datenjahr).
- **Änderungserkennung:** Die Ergebnisse werden nur dann neu geschrieben, wenn sich die Daten wirklich geändert haben.
  - Verglichen wird ein Fingerabdruck der ausgelesenen Daten: Felder, Werte, Blatt, Filterzustand.
  - Rohbytes taugen dafür nicht, denn sie enthalten bei jedem Abruf neue Sitzungs-IDs.
  - Ist der Fingerabdruck gleich, wird nichts geschrieben, `latest` bleibt, und der Lauf meldet „unverändert“ mit Exit 0. Nachgelagerte DVC-Stufen laufen dann nicht neu.
- Weitere Optionen:
  - `--list` zeigt Blätter, Felder und Filter
  - `--sheet` erzwingt ein Blatt
  - `--all-filters` zieht einen Abzug je Filterwert
  - `--method` erzwingt einen Weg
  - `--check-sum` gleicht eine Feldsumme gegen einen Sollwert ab
- Exit-Codes:

  | Code | Bedeutung |
  |---|---|
  | 0 | Erfolg oder „unverändert“ |
  | 1 | unerwarteter Fehler |
  | 2 | alle Wege gesperrt, keine Datentabelle |
  | 3 | Kreise nicht eindeutig zuordenbar, keine Datentabelle |

- Dazu kommen Tests mit Fixtures (ohne Netzwerk), ein Live-Test (`@pytest.mark.live`, standardmäßig aus), `ruff` und `mypy`, eine CI für Lint und Tests, README mit DVC-Beispiel, LICENSE (MIT) und CHANGELOG.

## Capabilities

### New Capabilities

- `tableau-extract`: Extraktion der Daten einer Tableau-Kartenansicht je Landkreis. Umfasst Eingabe, Extraktionswege, Exaktheit, Kreiszuordnung, Ausgabeformat, Nachvollziehbarkeit, Änderungserkennung und Fehlerverhalten.

### Modified Capabilities

(keine)

## Impact

- **Neuer Code:** `src/tableau_extract/` mit CLI und API, `tests/` mit Fixtures, `src/tableau_extract/data/` mit der Kreis-Referenzliste.
- **Abhängigkeiten:** `requests`, `pandas`, `pyarrow`; `playwright` als optionales Extra `browser` für Weg D.
- **Betrieb:** nur von Nicht-Rechenzentrums-IPs (lokal, Homelab). GitHub Actions fährt nur Lint und Offline-Tests.
- `probe/` bleibt als Werkzeug der Zugangsprüfung bestehen.
