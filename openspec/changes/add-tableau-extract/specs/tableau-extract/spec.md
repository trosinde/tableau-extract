# Spec Delta

## Purpose

Liest aus der URL einer Tableau-Kartenansicht die zugrunde liegenden Daten je deutschem Landkreis exakt aus dem Tableau-Datenmodell und legt sie nachvollziehbar als Tabelle (CSV, Parquet) mit Metadaten für eine reproduzierbare Pipeline ab.

## ADDED Requirements

### Requirement: Eingabe einer Tableau-View-URL
Das System SHALL genau eine URL als Eingabe akzeptieren, die auf eine Tableau-Ansicht (`/views/<Arbeitsmappe>/<Blatt>`, optional mit Site `/t/<site>`) zeigt. Andere URLs SHALL mit einer verständlichen Meldung und Exit-Code 1 abgelehnt werden, ohne dass Daten abgerufen werden.

#### Scenario: Gültige Tableau-URL
- **WHEN** `tableau-extract "https://tableau.bbsr.bund.de/t/bbr/views/Wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_FINAL/DWohnungsneubaubedare_insgesamt?:embed=y"` aufgerufen wird
- **THEN** erkennt das System Basis-URL, Site `bbr`, Arbeitsmappe und Blatt und beginnt mit der Extraktion

#### Scenario: Keine Tableau-URL
- **WHEN** eine URL ohne `/views/<Arbeitsmappe>/<Blatt>` übergeben wird
- **THEN** endet das System mit Exit-Code 1 und einer Meldung, dass eine Tableau-View-URL erwartet wird

#### Scenario: Einbettungsseite statt Tableau
- **WHEN** die URL auf eine HTML-Seite zeigt, die die Ansicht nur einbettet (z. B. eine bbsr.bund.de-Seite mit Zustimmungs-Checkbox)
- **THEN** bricht das System mit Exit-Code 1 ab, und die Meldung erklärt, dass die Tableau-URL aus dem `iframe` der Seite zu verwenden ist

### Requirement: URL-Normalisierung
Das System SHALL Anzeige- und Einbettungsparameter (Parameter, die mit `:` beginnen, z. B. `:embed`, `:showVizHome`, `:toolbar`) aus der URL entfernen, bevor Slug und Metadaten gebildet werden, damit dieselbe Ansicht unabhängig von diesen Parametern denselben Ausgabeordner erhält.

#### Scenario: Gleiche Ansicht mit unterschiedlichen Anzeigeparametern
- **WHEN** dieselbe Ansicht einmal mit `?:embed=y&:toolbar=no` und einmal ohne Parameter aufgerufen wird
- **THEN** verwenden beide Läufe denselben Slug und dieselbe normalisierte URL in `meta.json`

### Requirement: Extraktionswege in fester Reihenfolge
Das System SHALL die Wege in dieser Reihenfolge versuchen: A View-Data-Export, B VizQL-Session per HTTP, C Daten-Download im Browser, D Netzwerkmitschnitt im Browser. Der erste Weg, der Daten liefert, SHALL gewinnen. Mit `--method csv|vizql|download|network` SHALL nur der genannte Weg versucht werden.

#### Scenario: Erster Weg gesperrt, zweiter erfolgreich
- **WHEN** Weg A mit HTTP 404 scheitert und Weg B Daten liefert
- **THEN** stammen die Daten aus Weg B, und `meta.json` nennt `method = vizql` sowie den Fehlversuch von A mit HTTP-Status und Meldung

#### Scenario: Weg erzwungen
- **WHEN** `--method network` angegeben ist
- **THEN** versucht das System ausschließlich Weg D

### Requirement: Keine Umgehung von Zugangsschranken
Das System SHALL NOT Anmeldungen, Zugriffssperren, CAPTCHAs, Zustimmungsdialoge, Robots-Sperren oder Rate-Limits umgehen. Ein Weg, der auf eine solche Schranke trifft, SHALL als gescheitert protokolliert werden.

#### Scenario: Weiterleitung auf Anmeldung
- **WHEN** ein Weg mit einer Weiterleitung auf eine Anmeldeseite antwortet
- **THEN** wird der Weg als gescheitert mit Grund „Anmeldung erforderlich“ protokolliert, und es werden keine Zugangsdaten eingegeben

### Requirement: Höflicher Abruf
Das System SHALL einen eigenen User-Agent mit Projektnamen senden, höchstens eine Anfrage pro Sekunde an denselben Host stellen und vorübergehende Fehler (HTTP 429, 5xx, Zeitüberschreitung) mit exponentiellem Backoff höchstens dreimal wiederholen.

#### Scenario: Vorübergehender Serverfehler
- **WHEN** eine Anfrage mit HTTP 503 beantwortet wird
- **THEN** wiederholt das System sie mit wachsender Wartezeit höchstens dreimal, bevor der Weg als gescheitert gilt

#### Scenario: Dauerhafte Sperre
- **WHEN** eine Anfrage mit HTTP 403 beantwortet wird
- **THEN** wiederholt das System sie nicht und protokolliert den Weg als gescheitert

### Requirement: Exaktheit der Werte
Das System SHALL Werte ausschließlich aus einem Tableau-Datenexport oder dem VizQL-Datenwörterbuch übernehmen. Das System SHALL NOT Werte aus Farben, Bildern, Screenshots, Tooltip-Texten oder per OCR ableiten und SHALL NOT Werte schätzen, runden oder ergänzen.

#### Scenario: Wert mit voller Genauigkeit
- **WHEN** das Datenwörterbuch für einen Kreis den Wert `75.4` enthält
- **THEN** steht in `kreise.csv` genau `75.4`

#### Scenario: Wert nur als formatierter Text im Datenmodell
- **WHEN** ein Messwert im Datenmodell nur als formatierter Alias vorliegt (z. B. `23,000`)
- **THEN** wird der Text unverändert in `data_raw.csv` übernommen und in `kreise.csv` als Zahl 23000 abgelegt, ohne weitere Rundung

### Requirement: Kennzeichnung von Klassenfeldern
Das System SHALL Felder, die nur Klassen statt Einzelwerten enthalten, als Klassen übernehmen und je solchem Feld eine Spalte `<feld>_typ` mit dem Wert `klasse` ausgeben. Bei Feldern mit Einzelwerten SHALL `<feld>_typ` den Wert `wert` haben.

#### Scenario: Ansicht enthält nur Klassen
- **WHEN** ein Feld je Kreis Werte wie `60 bis unter 75` enthält
- **THEN** steht der Klassentext in der Tabelle, und `<feld>_typ = klasse`

### Requirement: Blattauswahl
Das System SHALL alle Blätter der Ansicht ermitteln und automatisch das Blatt mit geografischer Rolle oder Kreisschlüssel wählen. Mit `--sheet <name>` SHALL das genannte Blatt verwendet werden. Ein unbekannter Blattname SHALL mit Exit-Code 1 und der Liste der vorhandenen Blätter abgelehnt werden.

#### Scenario: Automatische Wahl
- **WHEN** die Ansicht die Blätter `Impressum` und `Karte` enthält und nur `Karte` ein Geometrie- bzw. Kreisschlüsselfeld hat
- **THEN** wird `Karte` gewählt und in `meta.json` als Blatt vermerkt

#### Scenario: Unbekanntes Blatt erzwungen
- **WHEN** `--sheet "Tabelle"` angegeben ist und kein solches Blatt existiert
- **THEN** endet das System mit Exit-Code 1 und nennt die vorhandenen Blätter

### Requirement: Auflisten ohne Extraktion
Mit `--list` SHALL das System Blätter, Felder je Blatt sowie Filter und Parameter mit ihren Werten ausgeben, ohne Ausgabedateien zu schreiben.

#### Scenario: Liste anzeigen
- **WHEN** `tableau-extract "<url>" --list` aufgerufen wird
- **THEN** werden Blätter, Felder und Filter angezeigt, und unter `out/` wird nichts angelegt

### Requirement: Filter und Parameter
Das System SHALL alle Filter und Parameter der Ansicht mit ihren möglichen Werten und dem Standardzustand in `meta.json` auflisten. Ohne `--all-filters` SHALL der Standardzustand gelten. Mit `--all-filters` SHALL je Filterwert ein Abzug gezogen und die Tabelle um eine Spalte je Filter ergänzt werden.

#### Scenario: Standardzustand
- **WHEN** die Ansicht einen Filter `Zeitraum` mit Standardwert `2023-2030` hat und `--all-filters` fehlt
- **THEN** enthält die Tabelle nur die Daten für `2023-2030`, und `meta.json` nennt den Filter, seine Werte und den verwendeten Zustand

#### Scenario: Alle Filterwerte
- **WHEN** `--all-filters` angegeben ist und der Filter `Zeitraum` zwei Werte hat
- **THEN** enthält die Tabelle je Kreis und Filterwert eine Zeile sowie eine Spalte `zeitraum`

#### Scenario: Ansicht ohne Filter
- **WHEN** die Ansicht keine Filter oder Parameter hat
- **THEN** ist die Filterliste in `meta.json` leer, und `--all-filters` ändert das Ergebnis nicht

### Requirement: Normalisierung des Kreisschlüssels
Das System SHALL je Zeile einen Kreisschlüssel `ags5` als 5-stelligen Text mit führender Null ausgeben. Gelieferte Schlüssel SHALL aus 4–5-stelliger Kreisform oder aus 7–8-stelliger Gemeindeform (`…000`) auf die ersten fünf Stellen des 8-stelligen Schlüssels zurückgeführt werden.

#### Scenario: Fehlende führende Null
- **WHEN** der gelieferte Schlüssel `8111` lautet
- **THEN** ist `ags5 = 08111`

#### Scenario: Gemeindeform des Schlüssels
- **WHEN** der gelieferte Schlüssel `9764000` lautet
- **THEN** ist `ags5 = 09764`

### Requirement: Zuordnung über den Kreisnamen
Fehlt ein Kreisschlüssel, SHALL das System den Kreis über eine eingecheckte Referenzliste (Destatis, Gebietsstand 31.12. des Datenjahres) per Name zuordnen. Dabei werden Groß-/Kleinschreibung, Umlautschreibweisen und Zusätze wie „, Landkreis“, „Stadtkreis“ oder „, Stadt“ ausgeglichen. Unklare Zuordnungen SHALL NOT geraten werden.

#### Scenario: Name mit Zusatz
- **WHEN** der gelieferte Name `Ahrweiler, Landkreis` lautet und die Referenzliste `Ahrweiler` mit Schlüssel `07131` enthält
- **THEN** ist `ags5 = 07131`

#### Scenario: Umlaut-Schreibweise
- **WHEN** der gelieferte Name `Muenchen, Landkreis` lautet
- **THEN** wird er `München, Landkreis` aus der Referenzliste zugeordnet

#### Scenario: Mehrdeutiger Name
- **WHEN** ein Name wie `Landshut` ohne Zusatz sowohl zur kreisfreien Stadt als auch zum Landkreis passt
- **THEN** wird kein Schlüssel geraten, der Lauf endet mit Exit-Code 3, es wird keine Datentabelle geschrieben, und der Bericht nennt die betroffenen Namen und Kandidaten

### Requirement: Vollständigkeit der Kreise
WHEN die Ansicht deutsche Kreise zeigt, SHALL `kreise.csv` jeden Kreis genau einmal enthalten (je Filterkombination). Das System SHALL die Schlüssel gegen die Referenzliste des passenden Gebietsstands prüfen und Abweichungen als Warnung mit der Liste fehlender und überzähliger Kreise ausgeben.

#### Scenario: Vollständige Ansicht
- **WHEN** die Ansicht 400 Kreise mit Gebietsstand 2023 liefert
- **THEN** enthält `kreise.csv` 400 Zeilen mit eindeutigen, gültigen `ags5`, und es gibt keine Warnung

#### Scenario: Fehlende Kreise
- **WHEN** die Ansicht 398 Kreise liefert
- **THEN** gibt das System eine Warnung aus und vermerkt die zwei fehlenden Schlüssel samt Namen in `meta.json`

#### Scenario: Doppelter Kreis
- **WHEN** ein `ags5` (ohne Filterspalten) zweimal vorkommt
- **THEN** wird dies als Warnung mit dem betroffenen Schlüssel gemeldet

### Requirement: Zahlenformate
Das System SHALL Zahlen als Dezimalwerte mit voller gelieferter Genauigkeit übernehmen. Formatierte Zahlentexte SHALL gemäß dem Gebietsschema der Arbeitsmappe in Tausender- und Dezimalzeichen zerlegt werden. `kreise.csv` SHALL Semikolon als Trennzeichen, Punkt als Dezimalzeichen und UTF-8 verwenden.

#### Scenario: Deutsches Format
- **WHEN** das Gebietsschema `de_DE` ist und der Wert `1.234,5` lautet
- **THEN** wird 1234.5 ausgegeben

#### Scenario: Englisches Format
- **WHEN** das Gebietsschema `en_US` ist und der Wert `1,600` lautet
- **THEN** wird 1600 ausgegeben

### Requirement: Sonderwerte
Das System SHALL Sonderwerte wie `null`, `*`, `%null%`, `-` und leere Felder in `kreise.csv` als leeren Wert ausgeben. In `data_raw.csv` SHALL das Originalzeichen erhalten bleiben.

#### Scenario: Geheimhaltungszeichen
- **WHEN** ein Kreis den Wert `*` hat
- **THEN** ist die Zelle in `kreise.csv` leer und in `data_raw.csv` steht `*`

### Requirement: Ausgabeordner und Dateien
Je erfolgreichem Lauf mit geänderten Daten SHALL das System den Ordner `out/<slug>/<UTC-Zeitstempel>_<sha8>/` anlegen, mit `data_raw.csv`, `kreise.csv`, `kreise.parquet` (Metadaten im Schema), `meta.json` und `raw/` (unveränderte Rohantworten). `out/<slug>/latest` SHALL auf diesen Ordner zeigen. `--out` SHALL das Basisverzeichnis festlegen.

#### Scenario: Erster Lauf
- **WHEN** für eine Ansicht noch kein Lauf existiert und die Extraktion gelingt
- **THEN** existieren alle genannten Dateien, und `latest` zeigt auf den neuen Ordner

#### Scenario: Spaltennamen
- **WHEN** ein Feld `SUM(P Wohnungsneubaubedarf 2330 We Pa (Round))` heißt
- **THEN** erhält es in `kreise.csv` einen eindeutigen snake_case-Namen, und `meta.json` ordnet ihm den Originalnamen zu

### Requirement: Nachvollziehbarkeit
Das System SHALL je Lauf in `meta.json` festhalten: Eingabe- und normalisierte URL, Weg, Blatt, Filterzustand und alle Filter mit Werten, Feldliste (Original- und Spaltenname, Datentyp, Werttyp), Abrufzeit (UTC), Gebietsschema, Veröffentlichungsstand (sofern verfügbar), SHA-256 je Rohantwort, Daten-Fingerabdruck, Fehlversuche (Weg, HTTP-Status, Meldung) und Prüfergebnisse.

#### Scenario: Metadaten eines Laufs
- **WHEN** ein Lauf über Weg B Daten liefert
- **THEN** enthält `meta.json` `method = vizql`, das Blatt, die Abrufzeit, die Prüfsummen jeder Datei in `raw/`, den Daten-Fingerabdruck und das Protokoll der vorher gescheiterten Wege

### Requirement: Änderungserkennung
Das System SHALL nach jedem Abruf einen Daten-Fingerabdruck (SHA-256) aus dem Inhalt der normalisierten Tabelle, der Feldliste, dem Blatt und dem Filterzustand bilden. Er SHALL unabhängig von Sitzungskennungen, Zeitstempeln und der Zeilenreihenfolge der Rohantworten sein. Gleicht er dem des Ordners hinter `latest`, SHALL nichts geschrieben werden.

#### Scenario: Unveränderte Quelle
- **WHEN** ein zweiter Lauf dieselben Daten liefert wie der Lauf hinter `latest`
- **THEN** wird kein neuer Ordner angelegt, `latest` bleibt unverändert, und das System meldet „unverändert“ mit Exit-Code 0

#### Scenario: Neue Sitzung, gleiche Daten
- **WHEN** sich die Rohantworten nur in Sitzungskennung oder Reihenfolge der Kreise unterscheiden
- **THEN** gilt die Quelle als unverändert

#### Scenario: Geänderter Wert
- **WHEN** sich mindestens ein Wert eines Kreises gegenüber dem Lauf hinter `latest` geändert hat
- **THEN** wird ein neuer Ordner geschrieben, und `latest` zeigt darauf

### Requirement: Vorabprüfung des Veröffentlichungsstands
Vor dem vollständigen Abruf SHALL das System mit einer kleinen Anfrage den Veröffentlichungsstand der Arbeitsmappe lesen (Zeitpunkt der letzten Veröffentlichung und Inhaltsversion). Ist er gleich dem gespeicherten Stand und liegt die letzte Vollprüfung weniger als `--full-check-days` Tage (Standard 30) zurück, SHALL das System die Daten nicht laden und nichts schreiben.

#### Scenario: Unveränderter Veröffentlichungsstand
- **WHEN** der Veröffentlichungsstand gleich dem gespeicherten ist und die letzte Vollprüfung 3 Tage zurückliegt
- **THEN** lädt das System die Daten nicht, meldet „unverändert (Veröffentlichungsstand)“ mit Exit-Code 0, und `latest` bleibt unverändert

#### Scenario: Neue Veröffentlichung
- **WHEN** sich der Zeitpunkt der letzten Veröffentlichung oder die Inhaltsversion geändert hat
- **THEN** lädt das System die Daten vollständig und entscheidet über den Daten-Fingerabdruck, ob ein neuer Ordner entsteht

#### Scenario: Sicherheitsnetz nach Ablauf der Frist
- **WHEN** der Veröffentlichungsstand gleich ist, die letzte Vollprüfung aber 31 Tage zurückliegt
- **THEN** lädt das System die Daten vollständig, vergleicht den Fingerabdruck und vermerkt die neue Vollprüfung

#### Scenario: Vollabruf erzwungen
- **WHEN** `--force` angegeben ist
- **THEN** lädt das System die Daten vollständig, unabhängig vom Veröffentlichungsstand

#### Scenario: Stand nicht verfügbar
- **WHEN** die Antwort keinen Veröffentlichungsstand enthält oder der Weg ihn nicht liefern kann
- **THEN** lädt das System die Daten vollständig

### Requirement: Zustand der Änderungserkennung
Das System SHALL je Ansicht `out/<slug>/state.json` mit Veröffentlichungsstand, Zeitpunkt der letzten Vollprüfung und Daten-Fingerabdruck führen. Eine Aktualisierung dieser Datei SHALL NOT einen neuen Lauf-Ordner anlegen oder `latest` verändern.

#### Scenario: Vollprüfung ohne Datenänderung
- **WHEN** eine Vollprüfung denselben Fingerabdruck wie `latest` ergibt
- **THEN** wird nur der Zeitpunkt der letzten Vollprüfung in `state.json` aktualisiert, ohne neuen Ordner

### Requirement: Gesperrte Quelle
WHEN kein Weg Daten liefert, SHALL das System mit Exit-Code 2 enden, einen Bericht der Fehlversuche (Weg, HTTP-Status, Meldung) ausgeben und SHALL NOT eine Datentabelle, Teil- oder Schätzdaten schreiben.

#### Scenario: Alle Wege gesperrt
- **WHEN** alle Wege mit HTTP 403 scheitern
- **THEN** endet das System mit Exit-Code 2, der Bericht nennt je Weg den Status 403, und es entstehen weder `kreise.csv` noch `kreise.parquet`, noch ändert sich `latest`

### Requirement: Gegenprobe über eine Summe
Mit `--check-sum <wert>` SHALL das System die Summe eines Messfeldes über alle Kreise mit dem Sollwert vergleichen und die Abweichung in Prozent melden. Das Feld SHALL mit `--check-field <spalte>` wählbar sein. Ohne diese Angabe SHALL das erste Messfeld mit absoluten Werten gelten. Das Ergebnis SHALL in `meta.json` stehen.

#### Scenario: Summe nahe am Bundeswert
- **WHEN** `--check-sum 320000 --check-field p_wohnungsneubaubedarf_2330_we_pa` angegeben ist und die Summe 316490 beträgt
- **THEN** meldet das System eine Abweichung von −1,1 % und vermerkt Soll, Ist und Abweichung in `meta.json`

### Requirement: Python-API
Das System SHALL `extract(url, **optionen)` und `list_view(url)` als öffentliche API bereitstellen; sie akzeptieren dieselben Optionen wie die CLI. `extract` SHALL ein `ExtractResult` liefern mit Status `neu` bzw. `unverändert`, normalisierter Tabelle als DataFrame, Metadaten und Ausgabepfad. Fehler SHALL als Ausnahmen mit dem Exit-Code der CLI gemeldet werden.

#### Scenario: Aufruf aus Python
- **WHEN** `extract(url, out="out/")` erfolgreich ausgeführt wird
- **THEN** enthält das Ergebnis den DataFrame mit denselben Daten wie `kreise.csv`, die Metadaten aus `meta.json` und den Ausgabepfad

#### Scenario: Ansicht auflisten aus Python
- **WHEN** `list_view(url)` aufgerufen wird
- **THEN** liefert das System Blätter, Felder mit Rollen sowie Filter, ohne Dateien zu schreiben

#### Scenario: Gesperrte Quelle aus Python
- **WHEN** `extract(url)` aufgerufen wird und kein Weg Daten liefert
- **THEN** wird eine Ausnahme mit `exit_code = 2` und dem Versuchsprotokoll ausgelöst

### Requirement: Herkunft der Referenzliste
Das System SHALL die Kreis-Referenzliste in dieser Reihenfolge suchen: explizit angegebener Pfad (`--referenz`), `./config/kreise_<JJJJ>.csv` im Arbeitsverzeichnis, mitgelieferte Fassung im Paket. Die verwendete Herkunft (`pfad`, `projekt` oder `paket`) SHALL in `meta.json` stehen.

#### Scenario: Ohne Projektdatei
- **WHEN** das Paket installiert ist und im Arbeitsverzeichnis kein `config/` existiert
- **THEN** verwendet das System die mitgelieferte Liste und vermerkt `referenz = paket`

#### Scenario: Projektdatei hat Vorrang
- **WHEN** `./config/kreise_2023.csv` existiert
- **THEN** verwendet das System diese Datei und vermerkt `referenz = projekt`

### Requirement: Offline-Wiederholung aus Rohdaten
Mit `--replay <ordner>` oder der Umgebungsvariable `TABLEAU_EXTRACT_REPLAY` SHALL das System statt eines Abrufs die dort gespeicherten Rohantworten eines früheren Laufs (Inhalt von `raw/`) verarbeiten. Es SHALL dabei keine Netzwerkanfrage stellen und in `meta.json` `method = replay` samt Quellordner vermerken.

#### Scenario: Früheren Lauf neu auswerten
- **WHEN** `tableau-extract "<url>" --replay out/<slug>/latest/raw` aufgerufen wird
- **THEN** entsteht dieselbe Tabelle wie im ursprünglichen Lauf, ohne Netzwerkzugriff, und `meta.json` nennt `method = replay`

#### Scenario: Replay-Ordner ohne verwertbare Antwort
- **WHEN** der Replay-Ordner keine `bootstrapSession`- oder CSV-Antwort enthält
- **THEN** endet das System mit Exit-Code 1 und einer Meldung, welche Dateien erwartet werden

### Requirement: Konfiguration ohne Zugangsdaten
Das System SHALL ausschließlich über CLI-Argumente und Umgebungsvariablen konfigurierbar sein und SHALL NOT Zugangsdaten im Code oder in Ausgabedateien enthalten.

#### Scenario: Ausgabeverzeichnis per Umgebungsvariable
- **WHEN** `TABLEAU_EXTRACT_OUT=/data/out` gesetzt ist und `--out` fehlt
- **THEN** schreibt das System nach `/data/out`
