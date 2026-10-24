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

- **Installation und Nutzung im Jupyter-Notebook** (wie bei `demografie-fetch`):
  - Installation per `%pip install "git+https://github.com/trosinde/tableau-extract.git@v0.1.0"` aus dem öffentlichen Repo, Version über Git-Tag festgelegt; Browser-Rückfallweg über das Extra `[browser]`.
  - Die Kreis-Referenzliste liegt im Paket, damit alles auch außerhalb des Repos funktioniert. Eine Datei im Projekt (`./config/`) hat Vorrang.
  - `ExtractResult` zeigt im Notebook eine kurze Zusammenfassung (Status, Weg, Blatt, Zeilen, Vollständigkeit, Pfad) statt des ganzen DataFrames. `list_view(url)` ist Teil der öffentlichen API.
  - **Offline-Wiederholung:** `--replay <raw-ordner>` bzw. `TABLEAU_EXTRACT_REPLAY` verarbeitet gespeicherte Rohantworten statt abzurufen. Das macht ältere Läufe neu auswertbar und erlaubt es, das Beispiel-Notebook in CI auszuführen, obwohl der BBSR-Server Rechenzentren sperrt.
  - Beispiel-Notebook `notebooks/schnellstart.ipynb`, in CI bei jeder Änderung vollständig ausgeführt (aus dem gebauten Wheel, mit Offline-Wiederholung).
  - README-Abschnitt „Im Jupyter-Notebook“, Release 0.1.0 mit Git-Tag und CHANGELOG.
- **Veröffentlichung des Repos** erst nach Bereinigung persönlicher Daten und ausdrücklicher Freigabe (Entscheidungspunkt, siehe design.md).
- Dazu kommen Tests mit Fixtures (ohne Netzwerk), ein Live-Test (`@pytest.mark.live`, standardmäßig aus), `ruff` und `mypy`, eine CI für Lint und Tests, README mit DVC-Beispiel, LICENSE (MIT) und CHANGELOG.

## Capabilities

### New Capabilities

- `tableau-extract`: Extraktion der Daten einer Tableau-Kartenansicht je Landkreis. Umfasst Eingabe, Extraktionswege, Exaktheit, Kreiszuordnung, Ausgabeformat, Nachvollziehbarkeit, Änderungserkennung und Fehlerverhalten.
- `notebook-usage`: Installation aus dem Repo, Lauffähigkeit außerhalb des Repos, Darstellung im Notebook und Offline-Wiederholung, abgesichert durch ein in CI ausgeführtes Beispiel-Notebook.

### Modified Capabilities

(keine)

## Impact

- **Neuer Code:** `src/tableau_extract/` mit CLI und API, `tests/` mit Fixtures, `src/tableau_extract/data/` mit der Kreis-Referenzliste.
- **Abhängigkeiten:** `requests`, `pandas`, `pyarrow`; `playwright` als optionales Extra `browser` für Weg D.
- **Neue Dateien:** `notebooks/schnellstart.ipynb`, Workflow `notebook.yml`, eine kleine aufgezeichnete Rohantwort unter `notebooks/beispiel_raw/` für das Notebook in CI.
- **Entwicklungsabhängigkeiten:** `nbclient`, `ipykernel` (nur CI und Tests).
- **GitHub:** Sichtbarkeit öffentlich (nach Freigabe), Tag `v0.1.0`.
- **Betrieb:** nur von Nicht-Rechenzentrums-IPs (lokal, Homelab). GitHub Actions fährt nur Lint, Offline-Tests und das Notebook mit Offline-Wiederholung.
- `probe/` bleibt als Werkzeug der Zugangsprüfung bestehen.
