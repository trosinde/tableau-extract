# Zugangsbericht (Schritt 0)

**Einstufung: A-lokal.** Von einem Privatanschluss liefert die Ansicht ihre Daten vollständig über die VizQL-Session (Weg B, ersatzweise D). Aus der Cloud (GitHub Actions) ist der Server komplett gesperrt.

## Geprüfte Ansicht

- Einbettende Seite: <https://www.bbsr.bund.de/BBSR/DE/forschung/fachbeitraege/wohnen-immobilien/wohnungsmarktprognose/prognose/01-prognose.html>. Die Karte liegt dort hinter einer Zustimmungs-Checkbox (Datenschutz).
- Die Tableau-URL steht im `iframe` des Fragments `k-prognose.html?view=getEmbedded`:
  `https://tableau.bbsr.bund.de/t/bbr/views/Wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_FINAL/DWohnungsneubaubedare_insgesamt?:embed=y&:isGuestRedirectFromVizportal=y`
- Server: Tableau Server (VizQL `v_202512510031138`), Gastzugang, Site `bbr`, davor AWS CloudFront.

## Ergebnisse

Skript: `probe/access_probe.py`, Rohergebnisse unter `probe/results/<env>/result.json`. Je Test gab es höchstens eine Anfrage, Weiterleitungen wurden nicht verfolgt.

| # | Test | lokal (Privatanschluss, 24.10.2026) | Cloud (GitHub Actions, Azure-IP) |
|---|---|---|---|
| T1 | `GET /robots.txt` | 404 (Tableau „Page Not Found“), Server erreichbar, keine robots.txt | **403 CloudFront** |
| T2 | View-URL, Standard-UA von `requests` | 200, Viz-HTML (5 KB). Ohne `:embed` kommt 302 auf `/#/site/bbr/views/...` (Vizportal), aber keine Anmeldung | **403 CloudFront** |
| T3 | wie T2, Browser-UA + `Referer: bbsr.bund.de` | 200, identisch zu T2, kein Filter nach Kennung oder Herkunft | **403 CloudFront** |
| T4 | `GET <view>.csv` | **404** `{"type":"missing-view"}`: Der View-Data-Export ist für Gäste nicht freigegeben | **403 CloudFront** |
| T5 | Playwright öffnet die View | 200, `bootstrapSession` 200 (3–4,6 MB) mit `dataDictionary` und `presModel`. Das Download-Menü bietet nur **Bild, PDF, PowerPoint**; „Daten“ und „Kreuztabelle“ fehlen | **403** („The request could not be satisfied“), keine VizQL-Antwort |

Die Cloud-Sperre greift für jeden Pfad, jede Kennung und auch für einen echten Browser. Es handelt sich also um eine IP- bzw. WAF-Regel für Rechenzentrumsnetze, nicht um einen Robots- oder User-Agent-Filter. Sie wird nicht umgangen (kein Proxy, kein Residential-IP-Dienst).

## Inhalt der `bootstrapSession` (lokal)

| Blatt | Felder |
|---|---|
| `Karte` | `krs23`, `krsname23`, `slk2023`, `SUM(P Wohnungsneubaubedarf 2330 We Pa (Round))`, `SUM(P Wohnungsneubaubedarf 2330 We Pa Je 10000Ew (Round))`, `P Wohnungsneubaubedarf 2330 We Pa Je 10000Ew (Round) (Klassen)`, `COLLECT(Geometrie)`, Latitude/Longitude (generated) |
| `Impressum` | `SUM(Krs2022)` |

Datenwörterbuch: 401 Ganzzahlen, 1085 Dezimalwerte, 1301 Texte und 400 Polygone (genau 400 Kreise). Kreisschlüssel und Kreisname werden direkt geliefert, ein Namensabgleich ist voraussichtlich unnötig.

**Hinweis zur Exaktheit:** Die Messfelder heissen in der Arbeitsmappe selbst `(Round)`. Das BBSR rundet also schon im Datenmodell. Geliefert werden die Werte „wie Tableau sie hält“, d. h. die gerundeten Werte. Unrundierte Werte gibt diese Ansicht nicht her. Das kommt so in `meta.json` und in die README.

## Folgen für den OpenSpec-Change

| Weg | Status | Umsetzen? |
|---|---|---|
| A View-Data-Export (`.csv`) | gesperrt (404 `missing-view`) | nur als Versuch mit protokolliertem Fehlschlag |
| B VizQL-Session per HTTP | funktioniert, nachgeprüft am 24.10.2026 (startSession → bootstrapSession per `requests`, 3,4 MB). `startSession` bestätigt die Rechte: `allow_export_data=false`, `allow_view_underlying=false`, `allow_summary=false` | **ja, Hauptweg** |
| C Crosstab-/Daten-Download | nicht angeboten | nein, nur protokolliert |
| D Netzwerkmitschnitt (Playwright) | funktioniert (T5) | **ja, Rückfallweg** |

- **Betrieb:** nur lokal bzw. auf einer Maschine mit Nicht-Rechenzentrums-IP (z. B. Homelab).
- **GitHub Actions** fährt nur Lint und die Offline-Tests mit Fixtures. Der Live-Test bleibt `@pytest.mark.live` und lokal.
- In der Cloud endet ein Lauf mit Exit 2 und dem Bericht „403 CloudFront“.
