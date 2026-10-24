# Changelog

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [SemVer](https://semver.org/lang/de/).

## [0.1.0] – 2026-10-24

Erste Version (OpenSpec-Change `add-tableau-extract`).

### Neu

- CLI `tableau-extract` und Python-API `extract()` / `list_view()`: Daten einer Tableau-Kartenansicht je Landkreis exakt aus dem Datenmodell.
- Extraktionswege A (View-CSV), B (VizQL per HTTP, Hauptweg), C (Download-Menü prüfen), D (Netzwerkmitschnitt mit Playwright, Extra `[browser]`); jeder Fehlversuch wird protokolliert, Sperren werden nicht umgangen.
- Ausgabe `kreise.csv`, `kreise.parquet` (decimal128), `data_raw.csv`, `meta.json`, `raw/`, `latest`.
- Zahlen nach Gebietsschema der Arbeitsmappe als `Decimal`, Klassenfelder mit `<feld>_typ`, Sonderwerte leer.
- Kreiszuordnung über Schlüssel oder Namen, Vollständigkeitsprüfung gegen Destatis-Referenzlisten (31.12.2023, 31.12.2024; mitinstalliert).
- Änderungserkennung: Vorabprüfung des Veröffentlichungsstands (kein Download, wenn unverändert), Sicherheitsnetz nach 30 Tagen bzw. `--force`, Daten-Fingerabdruck; `state.json`.
- `--all-filters`, `--sheet`, `--list`, `--method`, `--check-sum`, `--replay`, `--referenz`, `--gebietsstand`.
- Offline-Wiederholung aus gespeicherten Rohantworten.
- Notebook-Darstellung von `ExtractResult` und `ViewListing`; Beispiel-Notebook `notebooks/schnellstart.ipynb`, in CI ausgeführt.
- Zugangsprüfung `probe/access_probe.py` und Bericht `docs/zugangsbericht.md`.
