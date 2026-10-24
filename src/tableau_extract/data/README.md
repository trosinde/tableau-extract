# Kreis-Referenzlisten

`kreise_<JJJJ>.csv`: alle Kreise und kreisfreien Städte Deutschlands, Gebietsstand 31.12. des Jahres. Spalten `ags5;name;typ`, UTF-8, Semikolon.

| Datei | Gebietsstand | Kreise | Quelle | SHA-256 der Quelldatei (abgerufen 24.10.2026) |
|---|---|---|---|---|
| `kreise_2023.csv` | 31.12.2023 | 400 | Destatis, Gemeindeverzeichnis, Archiv: [`04_KreiseVorjahr.xlsx`](https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/Gemeindeverzeichnis/Administrativ/Archiv/Standardtabellen/04_KreiseVorjahr.xlsx?__blob=publicationFile) | `f393e3d01f9594773d205d5b8c4be04ed600990f07a74ee8c395d2bdef6bd6a4` |
| `kreise_2024.csv` | 31.12.2024 | 400 | Destatis, Gemeindeverzeichnis: [`04-kreise.xlsx`](https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/Gemeindeverzeichnis/Administrativ/04-kreise.xlsx?__blob=publicationFile) | `acb81f0139b525658bff493064e5b0bfec5bf31975fac4f3fef032d39d485e50` |

Die Kreisschlüssel beider Stände sind identisch. Erzeugt mit:

```bash
uv run --with openpyxl python scripts/make_kreisliste.py <datei.xlsx> src/tableau_extract/data/kreise_<JJJJ>.csv
```

Datenlizenz: Datenlizenz Deutschland – Namensnennung – Version 2.0 (© Statistisches Bundesamt (Destatis)).
