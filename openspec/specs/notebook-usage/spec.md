# notebook-usage Specification

## Purpose

Macht tableau-extract in einem lokalen Jupyter-Notebook installier- und nutzbar: Installation aus dem öffentlichen Repo per Git-Tag, Lauffähigkeit außerhalb des Repos, kompakte Darstellung der Ergebnisse und ein Beispiel-Notebook, das in CI ausgeführt wird.

## Requirements

### Requirement: Installation im Notebook
Das Paket SHALL sich in einem Jupyter-Kernel mit Python ≥ 3.11 per `%pip install "git+https://github.com/trosinde/tableau-extract.git@<tag>"` ohne Zugangsdaten installieren lassen. Mit `tableau-extract[browser] @ git+…@<tag>` SHALL zusätzlich der Browser-Rückfallweg installiert werden.

#### Scenario: Installation per Git-Tag
- **WHEN** im Notebook `%pip install "git+https://github.com/trosinde/tableau-extract.git@v0.1.0"` ausgeführt wird
- **THEN** ist danach `from tableau_extract import extract, list_view` ohne Neustart des Kernels möglich

#### Scenario: Zu altes Python
- **WHEN** der Kernel Python 3.10 verwendet
- **THEN** bricht die Installation mit dem Hinweis auf `requires-python >= 3.11` ab

### Requirement: Lauffähig außerhalb des Repos
Das installierte Paket SHALL alle Ressourcen mitbringen, die für Extraktion und Vollständigkeitsprüfung nötig sind (insbesondere die Kreis-Referenzlisten), sodass ein Aufruf aus einem beliebigen Arbeitsverzeichnis dasselbe Ergebnis liefert wie im Repo.

#### Scenario: Aufruf aus fremdem Ordner
- **WHEN** das gebaute Wheel in eine frische Umgebung installiert und `extract(..., replay=<beispiel>)` in einem leeren Ordner aufgerufen wird
- **THEN** enthält das Ergebnis eine Vollständigkeitsprüfung gegen die mitgelieferte Referenzliste, ohne Meldung „Referenzliste fehlt“

### Requirement: Darstellung im Notebook
`ExtractResult` SHALL im Notebook als kompakte Zusammenfassung erscheinen (Status, Weg, Blatt, Zeilenzahl, Vollständigkeit, Gegenprobe, Ausgabepfad), sowohl als HTML als auch als Text. Der DataFrame SHALL über ein Attribut erreichbar sein und nicht vollständig ausgegeben werden.

#### Scenario: Ergebnis als letzte Zelle
- **WHEN** eine Notebook-Zelle mit `extract(url)` endet
- **THEN** zeigt das Notebook eine Tabelle mit Status, Weg, Blatt, Zeilen und Pfad, aber nicht die 400 Datenzeilen

#### Scenario: Unverändert im Notebook
- **WHEN** die Daten seit dem letzten Lauf unverändert sind
- **THEN** zeigt die Zusammenfassung den Status `unverändert` und den Pfad des bestehenden Laufs

### Requirement: Beispiel-Notebook in CI
Das Repo SHALL ein Beispiel-Notebook `notebooks/schnellstart.ipynb` enthalten (Installation, Ansicht auflisten, Abruf, Wiederholung „unverändert“, Weiterverarbeitung mit pandas). CI SHALL es bei jeder Änderung an Code, Notebook oder Paketkonfiguration aus dem gebauten Wheel in einer frischen Umgebung vollständig ausführen; ein Fehler in einer Zelle SHALL den Workflow scheitern lassen.

#### Scenario: Notebook in CI ohne Zugriff auf die Quelle
- **WHEN** der Notebook-Workflow in GitHub Actions läuft, wo die Quelle mit 403 sperrt
- **THEN** wird das Notebook mit Offline-Wiederholung aus `notebooks/beispiel_raw/` ausgeführt, die Installationszelle übersprungen und das ausgeführte Notebook als Artefakt abgelegt

#### Scenario: Fehler im Notebook
- **WHEN** eine Zelle eine Ausnahme wirft
- **THEN** ist der Workflow rot
