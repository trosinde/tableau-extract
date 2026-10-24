# Tasks

## 1. Projektgerüst

- [x] 1.1 Branch `feat/tableau-extract` anlegen; `pyproject.toml` um `pandas`, `pyarrow`, das Extra `browser` (playwright), die Dev-Gruppe (`pytest`, `responses`, `ruff`, `mypy`, `pandas-stubs`), den Entry-Point `tableau-extract` und pytest-Marker `live` (standardmäßig abgewählt) ergänzen; prüfen mit `uv sync --all-groups && uv run tableau-extract --help`
- [x] 1.2 Modulstruktur nach design.md D1 anlegen (leere Module mit Docstrings, `py.typed`); prüfen mit `uv run ruff check && uv run mypy src`
- [x] 1.3 CI-Workflow `.github/workflows/ci.yml` (Push und PR: `ruff check`, `ruff format --check`, `mypy`, `pytest -m "not live"`) anlegen; prüfen mit grünem Lauf auf GitHub

## 2. URL und HTTP-Client

- [x] 2.1 `url.py`: Tableau-View-URL parsen (Basis, Site, Arbeitsmappe, Blatt), `:`-Parameter entfernen, Slug bilden, Nicht-Tableau- und Einbettungs-URLs mit verständlicher Meldung ablehnen (inkl. Hinweis auf `iframe`); prüfen mit `tests/test_url.py` (BBSR-URL mit/ohne `:embed`, URL ohne `/views/`, bbsr.bund.de-Seite)
- [x] 2.2 `http.py`: höflicher Client nach D8 (User-Agent, ≥1 s Abstand, Backoff 2/4/8 s bei 429/5xx/Timeout, kein Retry bei 401/403/404, Login-Weiterleitung erkennen), Versuchsprotokoll-Eintrag je Anfrage; prüfen mit `tests/test_http.py` (gemockte 503→200, 403, 302 auf `/signin`, Drossel per gemockter Uhr)

## 3. VizQL-Parser und Fixtures

- [x] 3.1 `tests/fixtures/make_fixture.py` schreiben und daraus `bbsr_bootstrap.txt` (Geometrie gekürzt, sonst unverändert) aus `probe/results/lokal/t5_bootstrapSession.txt` erzeugen; dazu synthetische Fixture `synthetic_bootstrap_de.txt` (de_DE, ein Filter, Sonderwerte `*`/`%null%`, Klassenfeld, 4-stellige Schlüssel); prüfen, dass beide Dateien < 1 MB sind und vom Parser gelesen werden
- [x] 3.2 `vizql_parse.py`: Längenpräfix-Segmente zerlegen, Datenwörterbuch nach Typ, Blätter und Felder je Blatt, `aliasIndices`/`valueIndices` inkl. negativer Indizes auflösen, `workbookLocale`, Filter/Parameter auslesen; klare Fehlermeldung bei unerwartetem Format; prüfen mit `tests/test_vizql_parse.py` (BBSR: Blätter `Karte`/`Impressum`, 400 Zeilen, Berlin `11000000`/`"23,000"`/`61.3`, Locale `en_US`; synthetisch: Filter erkannt; kaputte Eingabe → Fehler statt Teildaten)
- [x] 3.3 Blattauswahl (Geometrie/Schlüssel), `--sheet`, Rollenerkennung und Spaltennamen nach D5 inkl. Hinweis `(Round)`; prüfen mit Tests (automatische Wahl `Karte`, unbekanntes Blatt → Fehler mit Liste, `SUM(P Wohnungsneubaubedarf 2330 We Pa (Round))` → `p_wohnungsneubaubedarf_2330_we_pa`, Kollision → `_2`)

## 4. Normalisierung und Kreiszuordnung

- [x] 4.1 `normalize.py`: Zahlen nach Locale mit `Decimal` (en/de, nicht eindeutig → Fehler), Sonderwerte leer, Klassenfelder mit `<feld>_typ`; prüfen mit `tests/test_numbers.py` (`1.234,5`→1234.5 de, `1,600`→1600 en, `75.4` exakt, `*`/`null`/leer → leer, Klasse → `klasse`)
- [x] 4.2 Destatis-Kreisliste Gebietsstand 31.12.2023 beschaffen, als `src/tableau_extract/data/kreise_2023.csv` (`ags5;name;typ`, 400 Zeilen) einchecken, Herkunft/URL/SHA-256 in `src/tableau_extract/data/README.md`; prüfen mit Test „400 eindeutige ags5“
- [x] 4.3 `regions.py`: Schlüssel normalisieren (D6), Gebietsstand ableiten, Namensabgleich (Umlaute, Zusätze), Mehrdeutigkeit → Fehler mit Kandidaten, Vollständigkeit (fehlend/überzählig/doppelt), Referenz-Suchreihenfolge `--referenz` → `./config/` → Paket mit Herkunft in den Metadaten (`importlib.resources`); prüfen mit `tests/test_regions.py` (`8111`→`08111`, `9764000`→`09764`, „Ahrweiler, Landkreis“, „Muenchen, Landkreis“, mehrdeutiger Name → Exit-3-Fehler, 398 Kreise → Warnung mit Liste, Projektdatei hat Vorrang vor Paket, ohne `config/` → `referenz = paket`)

## 5. Extraktionswege

- [x] 5.1 Weg A `methods/csv.py`: `GET <view>.csv`, Erfolg nur bei 200 und CSV-Inhalt, sonst Protokolleintrag; prüfen mit Tests (gemocktes CSV → Tabelle; 404 `missing-view` → Fehlversuch mit Status)
- [x] 5.2 Weg B `methods/vizql.py`: Ladeseite → `startSession/viewing` → `bootstrapSession` per HTTP nach D2, Rohantworten als `RawCapture`; prüfen mit gemocktem Ablauf (`responses`) und Fixture → 400 Zeilen; danach einmal live lokal ausführen und Ergebnis (Erfolg oder Fehlergrund) im PR notieren
- [x] 5.3 Wege C/D `methods/browser.py`: eine Playwright-Sitzung, `bootstrapSession` mitschneiden (D), Download-Menü auf „Daten“/„Kreuztabelle“ prüfen und protokollieren (C), ohne Playwright sauberer Fehlversuch; prüfen mit Test „Playwright fehlt → Protokolleintrag“ und Parser-Test auf mitgeschnittener Fixture
- [x] 5.4 Orchestrierung: Reihenfolge A→B→C→D, `--method`, Abbruch beim ersten Erfolg, alle gescheitert → `BlockedError` mit Bericht; prüfen mit Tests (A 404 + B ok → `vizql` mit Protokoll A; alle 403 → Exit 2, kein `kreise.csv`, `latest` unverändert)
- [x] 5.5 `--all-filters`: je Filterwert Abzug ziehen (Weg B; Weg D meldet Fehlversuch), Filterspalten ergänzen; prüfen mit synthetischer Fixture (2 Filterwerte → doppelte Zeilenzahl + Spalte)
- [x] 5.6 Offline-Wiederholung `--replay`/`TABLEAU_EXTRACT_REPLAY`: Rohdateien aus `raw/` laden, gleicher Parser, `method = replay`, keine Netzwerkanfrage, fehlende Dateien → Exit 1; prüfen mit Tests (Replay der Fixture ergibt dieselbe Tabelle wie Weg B; `responses` meldet null Aufrufe; leerer Ordner → Fehler mit erwarteten Dateinamen)

## 6. Ausgabe, Fingerabdruck, Änderungserkennung

- [x] 6.1 `fingerprint.py` nach D7 (kanonisch, sortiert, unabhängig von Sitzung/Reihenfolge); prüfen mit Tests (gleiche Daten in anderer Reihenfolge/anderer Session-ID → gleicher Hash; ein Wert geändert → anderer Hash)
- [x] 6.2 `output.py`: temporärer Ordner, `data_raw.csv`, `kreise.csv` (`;`, Punkt, UTF-8), `kreise.parquet` (Decimal, Metadaten im Schema), `meta.json` (alle Felder laut Spec), `raw/`, atomarer Umzug und `latest`-Symlink; Vergleich mit `latest` → „unverändert“ ohne Schreiben; prüfen mit Tests (erster Lauf legt alles an; zweiter Lauf gleich → kein neuer Ordner, Meldung „unverändert“, Exit 0; geänderter Wert → neuer Ordner, `latest` umgehängt; Parquet-Metadaten lesbar)
- [x] 6.3 Vorabprüfung und `state.json` nach D7a: Veröffentlichungsstand aus `startSession` (Weg B), Vergleich mit `out/<slug>/state.json`, Frist `--full-check-days` (Standard 30), `--force`, Replay überspringt; prüfen mit Tests (gleicher Stand + 3 Tage → kein `bootstrapSession`-Aufruf laut `responses`, Exit 0 „unverändert (Veröffentlichungsstand)“; neuer Stand → Vollabruf; 31 Tage → Vollabruf, gleicher Fingerabdruck → nur `state.json` aktualisiert; `--force`; Stand fehlt → Vollabruf)

## 7. CLI, API, Gegenprobe

- [x] 7.1 `api.py`: `extract(url, **opts) -> ExtractResult` (DataFrame, Metadaten, Pfade, Status `neu`/`unverändert`) und `list_view(url) -> ViewListing`, beide mit `_repr_html_`/`__repr__` als kompakte Zusammenfassung (ohne Datenzeilen), Ausnahmen mit `exit_code`; Export in `__init__`; prüfen mit Tests gegen gemockten Weg B (HTML enthält Status/Weg/Blatt/Zeilen/Pfad, keine 400 Zeilen; gesperrt → Ausnahme mit `exit_code = 2`)
- [x] 7.2 `cli.py`: alle Optionen (`--sheet`, `--all-filters`, `--out`, `--list`, `--method`, `--check-sum`, `--check-field`, `--gebietsstand`, `--referenz`, `--replay`, `--force`, `--full-check-days`, `--timeout`, `--quiet`), Umgebungsvariablen, Exit-Codes 0/1/2/3; prüfen mit `tests/test_cli.py` (`--list` schreibt nichts; ungültige URL → 1; gesperrt → 2; mehrdeutig → 3; `TABLEAU_EXTRACT_OUT`)
- [x] 7.3 Gegenprobe `--check-sum`/`--check-field`: Summe, Abweichung in %, Eintrag in `meta.json`; prüfen mit Test (BBSR-Fixture, Soll 320000 → −1,1 %)

## 8. Nutzung im Jupyter-Notebook

- [x] 8.1 Wheel-Inhalt absichern: Test baut das Wheel (`uv build`), installiert es in eine frische venv und ruft dort in einem leeren Ordner `extract(..., replay=<fixture>)` auf; prüfen, dass `kreise_2023.csv` im Wheel liegt und die Vollständigkeitsprüfung `referenz = paket` meldet
- [x] 8.2 `notebooks/beispiel_raw/` mit der gekürzten BBSR-Antwort (identisch zur Test-Fixture, Gleichheitstest) und `notebooks/schnellstart.ipynb` (Installationszelle mit Tag `skip-ci`, `list_view`, `extract`, zweiter Lauf „unverändert“, pandas-Auswertung, Gegenprobe); prüfen durch lokale Ausführung mit `nbclient` mit und ohne `TABLEAU_EXTRACT_REPLAY`
- [x] 8.3 Workflow `.github/workflows/notebook.yml` (Pfade `src/`, `notebooks/`, `pyproject.toml`; Wheel bauen, frische venv mit `ipykernel` + `nbclient`, Notebook mit Replay ausführen, `skip-ci`-Zellen überspringen, ausgeführtes Notebook als Artefakt); `nbclient`/`ipykernel` in die Dev-Gruppe; prüfen mit grünem Lauf und absichtlich kaputter Zelle → rot (lokal mit `act` oder per Test-Branch)
- [x] 8.4 README-Abschnitt „Im Jupyter-Notebook“ (Installationszelle per Tag, `[browser]`-Extra mit `playwright install chromium`, Beispielzellen, Hinweis „nur von Privatanschluss/Homelab, nicht Colab“, Replay); prüfen, dass die Zellen dem Beispiel-Notebook entsprechen

## 9. Veröffentlichung (nach Freigabe, siehe design.md D13)

- [x] 9.1 Probe-Skript speichert keine IP-Adresse und keinen Rechnernamen mehr, nur die Einstufung „Privatanschluss“/„Rechenzentrum“; `probe/results/*/result.json` entsprechend bereinigen; prüfen mit `git grep` auf IP-Muster und Rechnernamen (keine Treffer)
- [x] 9.2 Je nach Entscheidung (b) oder (c): bei (c) Historie aller Branches bereinigen (`git filter-repo`), Force-Push auf `main` und `feat/tableau-extract`; prüfen mit `git log --all -p | grep` auf IP und Rechnernamen (keine Treffer)
- [x] 9.3 Repo nach ausdrücklicher Freigabe öffentlich stellen; prüfen mit `%pip install "git+https://github.com/trosinde/tableau-extract.git@feat/tableau-extract"` in einer frischen venv ohne Zugangsdaten

## 10. Dokumentation und Abschluss

- [x] 10.1 README an das tatsächliche Verhalten anpassen (Status-Hinweis „in Planung“ und `[geplant]`-Marken entfernen, Beispielausgaben durch echte ersetzen, Diagramme aktuell halten), `LICENSE` (MIT), `CHANGELOG.md` anlegen; prüfen, dass die README-Befehle so laufen und die Mermaid-Diagramme fehlerfrei rendern
- [x] 10.2 Live-Test `tests/test_live.py` (`@pytest.mark.live`): BBSR-URL → 400 Zeilen, gültige `ags5`, Summe innerhalb ±5 % von 320 000, zweiter Lauf „unverändert“, Beispiel-Notebook live ohne Replay; lokal ausführen mit `uv run pytest -m live`
- [ ] 10.3 Integrationsprüfung: `uv run ruff check && uv run ruff format --check && uv run mypy src && uv run pytest`, `openspec validate add-tableau-extract --strict` grün, CI und Notebook-Workflow grün
- [ ] 10.4 Akzeptanz: echter Lauf `tableau-extract "<BBSR-URL>"` lokal, 5 Kreise mit den Tooltip-Werten der Karte abgleichen (z. B. Berlin, Bonn, Rhein-Sieg-Kreis, Ahrweiler, Erzgebirgskreis) und als Tabelle in die PR-Beschreibung; zweiter Lauf meldet „unverändert“
- [ ] 10.5 Release 0.1.0: Version in `pyproject.toml`/`__init__`, CHANGELOG-Eintrag, nach dem Merge Tag `v0.1.0` auf `main`; prüfen mit `%pip install "git+https://github.com/trosinde/tableau-extract.git@v0.1.0"` in einem frischen Kernel und Ausführen des Beispiel-Notebooks

## Workflow follow-up

- PR `feat/tableau-extract` → `main` mit Verweis auf `openspec/changes/add-tableau-extract/`
- Nach dem Merge `/opsx:archive`, damit die Spec unter `openspec/specs/tableau-extract/` gilt
