"""Daten-Fingerabdruck für die Änderungserkennung.

SHA-256 über eine kanonische JSON-Darstellung von Blatt, Filterzustand, Feldliste und
Zeilen. Die Zeilen werden nach (ags5, Filterspalten) sortiert und die Werte als Text
genommen, wie sie in `data_raw.csv` stehen. Sitzungskennungen, Zeitstempel und die
Reihenfolge der Zeilen in der Rohantwort haben damit keinen Einfluss.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def raw_text(value: Any) -> str:
    """Textform eines Rohwerts (wie in data_raw.csv)."""
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def fingerprint(
    *,
    sheet: str,
    filter_state: Any,
    fields: list[tuple[str, str, str]],
    rows: list[tuple[str, tuple[str, ...], list[Any]]],
) -> str:
    """rows: (ags5, Filterwerte, Rohwerte in Feldreihenfolge)."""
    canonical = {
        "sheet": sheet,
        "filter_state": filter_state,
        "fields": [list(f) for f in fields],
        "rows": sorted(
            [ags5, list(filters), [raw_text(v) for v in values]] for ags5, filters, values in rows
        ),
    }
    data = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
