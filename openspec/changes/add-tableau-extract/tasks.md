# Tasks

## 1. Projektgerüst

- [x] 1.1 Branch `feat/tableau-extract` anlegen; `pyproject.toml` um `pandas`, `pyarrow`, das Extra `browser` (playwright), die Dev-Gruppe (`pytest`, `responses`, `ruff`, `mypy`, `pandas-stubs`), den Entry-Point `tableau-extract` und pytest-Marker `live` (standardmäßig abgewählt) ergänzen; prüfen mit `uv sync --all-groups && uv run tableau-extract --help`
- [x] 1.2 Modulstruktur nach design.md D1 anlegen (leere Module mit Docstrings, `py.typed`); prüfen mit `uv run ruff check && uv run mypy src`
- [x] 1.3 CI-Workflow `.github/workflows/ci.yml` (Push und PR: `ruff check`, `ruff format --check`, `mypy`, `pytest -m "not live"`) anlegen; prüfen mit grünem Lauf auf GitHub

## 2. URL und HTTP-Client

- [x] 2.1 `url.py`: Tableau-View-URL parsen (Basis, Site, Arbeitsmappe, Blatt), `:`-Parameter entfernen, Slug bilden, Nicht-Tableau- und Einbettungs-URLs mit verständlicher Meldung ablehnen (inkl. Hinweis auf `iframe`); prüfen mit `tests/test_url.py` (BBSR-URL mit/ohne `:embed`, URL ohne `/views/`, bbsr.bund.de-Seite)
- [ ] 2.2 `http.py`: höflicher Client nach D8 (User-Agent, ≥1 s Abstand, Backoff 2/4/8 s bei 429/5xx/Timeout, kein Retry bei 401/403/404, Login-Weiterleitung erkennen), Versuchsprotokoll-Eintrag je Anfrage; prüfen mit `tests/test_http.py` (gemockte 503→200, 403, 302 auf `/signin`, Drossel per gemockter Uhr)

## 3. VizQL-Parser und Fixtures

- [ ] 3.1 `tests/fixtures/make_fixture.py` schreiben und daraus `bbsr_bootstrap.txt` (Geometrie gekürzt, sonst unverändert) aus `probe/results/lokal/t5_bootstrapSession.txt` erzeugen; dazu synthetische Fixture `synthetic_bootstrap_de.txt` (de_DE, ein Filter, Sonderwerte `*`/`%null%`, Klassenfeld, 4-stellige Schlüssel); prüfen, dass beide Dateien < 1 MB sind und vom Parser gelesen werden
- [ ] 3.2 `vizql_parse.py`: Längenpräfix-Segmente zerlegen, Datenwörterbuch nach Typ, Blätter und Felder je Blatt, `aliasIndices`/`valueIndices` inkl. negativer Indizes auflösen, `workbookLocale`, Filter/Parameter auslesen; klare Fehlermeldung bei unerwartetem Format; prüfen mit `tests/test_vizql_parse.py` (BBSR: Blätter `Karte`/`Impressum`, 400 Zeilen, Berlin `11000000`/`"23,000"`/`61.3`, Locale `en_US`; synthetisch: Filter erkannt; kaputte Eingabe → Fehler statt Teildaten)
- [ ] 3.3 Blattauswahl (Geometrie/Schlüssel), `--sheet`, Rollenerkennung und Spaltennamen nach D5 inkl. Hinweis `(Round)`; prüfen mit Tests (automatische Wahl `Karte`, unbekanntes Blatt → Fehler mit Liste, `SUM(P Wohnungsneubaubedarf 2330 We Pa (Round))` → `p_wohnungsneubaubedarf_2330_we_pa`, Kollision → `_2`)

## 4. Normalisierung und Kreiszuordnung

- [ ] 4.1 `normalize.py`: Zahlen nach Locale mit `Decimal` (en/de, nicht eindeutig → Fehler), Sonderwerte leer, Klassenfelder mit `<feld>_typ`; prüfen mit `tests/test_numbers.py` (`1.234,5`→1234.5 de, `1,600`→1600 en, `75.4` exakt, `*`/`null`/leer → leer, Klasse → `klasse`)
- [ ] 4.2 Destatis-Kreisliste Gebietsstand 31.12.2023 beschaffen, als `src/tableau_extract/data/kreise_2023.csv` (`ags5;name;typ`, 400 Zeilen) einchecken, Herkunft/URL/SHA-256 in `src/tableau_extract/data/README.md`; prüfen mit Test „400 eindeutige ags5“
- [ ] 4.3 `regions.py`: Schlüssel normalisieren (D6), Gebietsstand ableiten, Namensabgleich (Umlaute, Zusätze), Mehrdeutigkeit → Fehler mit Kandidaten, Vollständigkeit (fehlend/überzählig/doppelt); prüfen mit `tests/test_regions.py` (`8111`→`08111`, `9764000`→`09764`, „Ahrweiler, Landkreis“, „Muenchen, Landkreis“, mehrdeutiger Name → Exit-3-Fehler, 398 Kreise → Warnung mit Liste)

## 5. Extraktionswege

- [ ] 5.1 Weg A `methods/csv.py`: `GET <view>.csv`, Erfolg nur bei 200 und CSV-Inhalt, sonst Protokolleintrag; prüfen mit Tests (gemocktes CSV → Tabelle; 404 `missing-view` → Fehlversuch mit Status)
- [ ] 5.2 Weg B `methods/vizql.py`: Ladeseite → `startSession/viewing` → `bootstrapSession` per HTTP nach D2, Rohantworten als `RawCapture`; prüfen mit gemocktem Ablauf (`responses`) und Fixture → 400 Zeilen; danach einmal live lokal ausführen und Ergebnis (Erfolg oder Fehlergrund) im PR notieren
- [ ] 5.3 Wege C/D `methods/browser.py`: eine Playwright-Sitzung, `bootstrapSession` mitschneiden (D), Download-Menü auf „Daten“/„Kreuztabelle“ prüfen und protokollieren (C), ohne Playwright sauberer Fehlversuch; prüfen mit Test „Playwright fehlt → Protokolleintrag“ und Parser-Test auf mitgeschnittener Fixture
- [ ] 5.4 Orchestrierung: Reihenfolge A→B→C→D, `--method`, Abbruch beim ersten Erfolg, alle gescheitert → `BlockedError` mit Bericht; prüfen mit Tests (A 404 + B ok → `vizql` mit Protokoll A; alle 403 → Exit 2, kein `kreise.csv`, `latest` unverändert)
- [ ] 5.5 `--all-filters`: je Filterwert Abzug ziehen (Weg B/D), Filterspalten ergänzen; prüfen mit synthetischer Fixture (2 Filterwerte → doppelte Zeilenzahl + Spalte)

## 6. Ausgabe, Fingerabdruck, Änderungserkennung

- [ ] 6.1 `fingerprint.py` nach D7 (kanonisch, sortiert, unabhängig von Sitzung/Reihenfolge); prüfen mit Tests (gleiche Daten in anderer Reihenfolge/anderer Session-ID → gleicher Hash; ein Wert geändert → anderer Hash)
- [ ] 6.2 `output.py`: temporärer Ordner, `data_raw.csv`, `kreise.csv` (`;`, Punkt, UTF-8), `kreise.parquet` (Decimal, Metadaten im Schema), `meta.json` (alle Felder laut Spec), `raw/`, atomarer Umzug und `latest`-Symlink; Vergleich mit `latest` → „unverändert“ ohne Schreiben; prüfen mit Tests (erster Lauf legt alles an; zweiter Lauf gleich → kein neuer Ordner, Meldung „unverändert“, Exit 0; geänderter Wert → neuer Ordner, `latest` umgehängt; Parquet-Metadaten lesbar)

## 7. CLI, API, Gegenprobe

- [ ] 7.1 `api.py`: `extract(url, **opts) -> ExtractResult` (DataFrame, Metadaten, Pfade, Status `neu`/`unverändert`); prüfen mit Test gegen gemockten Weg B
- [ ] 7.2 `cli.py`: alle Optionen (`--sheet`, `--all-filters`, `--out`, `--list`, `--method`, `--check-sum`, `--check-field`, `--gebietsstand`, `--timeout`, `--quiet`), Umgebungsvariablen, Exit-Codes 0/1/2/3; prüfen mit `tests/test_cli.py` (`--list` schreibt nichts; ungültige URL → 1; gesperrt → 2; mehrdeutig → 3; `TABLEAU_EXTRACT_OUT`)
- [ ] 7.3 Gegenprobe `--check-sum`/`--check-field`: Summe, Abweichung in %, Eintrag in `meta.json`; prüfen mit Test (BBSR-Fixture, Soll 320000 → −1,1 %)

## 8. Dokumentation und Abschluss

- [ ] 8.1 README an das tatsächliche Verhalten anpassen (Status-Hinweis „in Planung“ und `[geplant]`-Marken entfernen, Beispielausgaben durch echte ersetzen, Diagramme aktuell halten), `LICENSE` (MIT), `CHANGELOG.md` anlegen; prüfen, dass die README-Befehle so laufen und die Mermaid-Diagramme fehlerfrei rendern
- [ ] 8.2 Live-Test `tests/test_live.py` (`@pytest.mark.live`): BBSR-URL → 400 Zeilen, gültige `ags5`, Summe innerhalb ±5 % von 320 000, zweiter Lauf „unverändert“; lokal ausführen mit `uv run pytest -m live`
- [ ] 8.3 Integrationsprüfung: `uv run ruff check && uv run ruff format --check && uv run mypy src && uv run pytest`, `openspec validate add-tableau-extract --strict` grün, CI grün
- [ ] 8.4 Akzeptanz: echter Lauf `tableau-extract "<BBSR-URL>"` lokal, 5 Kreise mit den Tooltip-Werten der Karte abgleichen (z. B. Berlin, Bonn, Rhein-Sieg-Kreis, Ahrweiler, Erzgebirgskreis) und als Tabelle in die PR-Beschreibung; zweiter Lauf meldet „unverändert“

## Workflow follow-up

- PR `feat/tableau-extract` → `main` mit Verweis auf `openspec/changes/add-tableau-extract/`
- Nach dem Merge `/opsx:archive`, damit die Spec unter `openspec/specs/tableau-extract/` gilt
