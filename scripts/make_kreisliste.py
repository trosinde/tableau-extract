"""Erzeugt eine Kreis-Referenzliste (ags5;name;typ) aus einer Destatis-Tabelle.

Quelle: Destatis, Gemeindeverzeichnis, „Kreisfreie Städte und Landkreise nach Fläche,
Bevölkerung und Bevölkerungsdichte“ (04-kreise.xlsx bzw. Archiv 04_KreiseVorjahr.xlsx).

Aufruf:
    uv run --with openpyxl python scripts/make_kreisliste.py <datei.xlsx> <ziel.csv>
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    ws = wb.worksheets[1]
    stand = None
    rows = []
    for row in ws.iter_rows(values_only=True):
        text = " ".join(str(c) for c in row[:2] if c)
        m = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
        if stand is None and m:
            stand = m.group(1)
        key = str(row[0]).strip() if row[0] is not None else ""
        if re.fullmatch(r"\d{5}", key) and row[2]:
            rows.append((key, str(row[2]).strip(), str(row[1]).strip()))
    keys = [r[0] for r in rows]
    if len(keys) != len(set(keys)):
        raise SystemExit("doppelte Schlüssel in der Quelle")
    with dst.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(["ags5", "name", "typ"])
        w.writerows(rows)
    print(f"{dst}: {len(rows)} Kreise, Gebietsstand {stand}")


if __name__ == "__main__":
    main()
