"""Erzeugt synthetische VizQL-Antworten für Fälle, die die BBSR-Karte nicht abdeckt.

- `synthetic_bootstrap_de.txt`: Gebietsschema de_DE, Filter „Zeitraum“ (zwei Werte),
  Parameter „Komponente“, Sonderwerte (`*`, `%null%`), Klassenfeld, 4-stellige
  Kreisschlüssel, formatierte Zahlen (`1.234,5`), ein zweites Blatt „Legende“.
- `synthetic_filter_response.json`: Antwort auf „Zeitraum = 2031-2040“, die das
  Datenwörterbuch um ein Segment ergänzt.

Aufbau wie echte Antworten (siehe vizql_parse.py). Aufruf ohne Argumente schreibt
beide Dateien neben dieses Skript.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent

KEYS = [8111, 9162, 7131, 1001]
NAMES = [
    "Stuttgart, Stadtkreis",
    "München, Kreisfreie Stadt",
    "Ahrweiler, Landkreis",
    "Flensburg, Stadt",
]
KLASSEN = ["15 bis unter 30", "30 bis unter 45", "bis unter 15", "45 und mehr"]


class DictBuilder:
    """Baut Datenwörterbuch-Segmente und Indizes wie Tableau."""

    def __init__(self, offset: dict[str, int] | None = None) -> None:
        self.lists: dict[str, list[Any]] = {}
        self.offset = offset or {}

    def index(self, dtype: str, value: Any) -> int:
        lst = self.lists.setdefault(dtype, [])
        lst.append(value)
        return self.offset.get(dtype, 0) + len(lst) - 1

    def alias(self, text: str) -> int:
        return -self.index("cstring", text) - 1

    def segment(self) -> dict[str, Any]:
        return {"dataColumns": [{"dataType": t, "dataValues": v} for t, v in self.lists.items()]}


def pane_columns(fields: list[tuple[str, str, list[int], str]]) -> dict[str, Any]:
    """fields: (caption, dataType, indices, art "value"|"alias")."""
    viz_cols = []
    pane_cols = []
    for i, (caption, dtype, idx, art) in enumerate(fields):
        viz_cols.append(
            {
                "fieldCaption": caption,
                "dataType": dtype,
                "paneIndices": [0],
                "columnIndices": [i],
                "fn": f"[ds].[{caption}]",
            }
        )
        pane_cols.append(
            {
                "valueIndices": idx if art == "value" else [],
                "aliasIndices": idx if art == "alias" else [],
            }
        )
    viz_cols.insert(0, {"paneIndices": [0], "columnIndices": [len(fields)]})  # ohne Caption
    pane_cols.append({"valueIndices": [], "aliasIndices": []})
    return {"vizDataColumns": viz_cols, "paneColumnsList": [{"vizPaneColumns": pane_cols}]}


def karte(b: DictBuilder, bedarf: list[str], quote: list[float]) -> dict[str, Any]:
    return pane_columns(
        [
            ("Kreisschlüssel", "integer", [b.index("integer", k) for k in KEYS], "value"),
            ("Kreis", "cstring", [b.index("cstring", n) for n in NAMES], "value"),
            ("SUM(Bedarf (Round))", "real", [b.alias(x) for x in bedarf], "alias"),
            ("SUM(Quote)", "real", [b.index("real", q) for q in quote], "value"),
            (
                "Bedarf je EW (Klassen)",
                "cstring",
                [b.index("cstring", k) for k in KLASSEN],
                "value",
            ),
            (
                "COLLECT(Geometrie)",
                "spatial",
                [b.index("spatial", "GEOGRAPHY('POINT(0 0)')") for _ in KEYS],
                "value",
            ),
        ]
    )


def filters_json(selected: str) -> str:
    tuples = [{"t": [{"v": v}], "s": v == selected} for v in ("2023-2030", "2031-2040")]
    return json.dumps(
        [
            {
                "worksheet": "Karte",
                "table": {
                    "schema": [
                        {"caption": "Zeitraum", "name": ["ds", "none:Zeitraum:nk"], "ordinal": 0}
                    ],
                    "tuples": tuples,
                },
                "all": False,
            }
        ]
    )


def zones(selected: str, karte_pcd: dict[str, Any] | None = None) -> dict[str, Any]:
    visual: dict[str, Any] = {"filtersJson": filters_json(selected)}
    if karte_pcd is not None:
        visual["vizData"] = {"paneColumnsData": karte_pcd}
    return {
        "1": {"worksheet": "Karte", "presModelHolder": {"visual": visual}},
        "2": {"worksheet": "Legende", "presModelHolder": {"visual": {}}},
        "3": {
            "presModelHolder": {
                "parameterControl": {
                    "fieldCaption": "Komponente",
                    "parameterName": "[Parameters].[Parameter 1]",
                    "formattedValues": ["insgesamt", "Ersatzbedarf"],
                    "formattedValue": "insgesamt",
                }
            }
        },
        "4": {"presModelHolder": {"dashboardText": {}}},
    }


def bootstrap() -> tuple[str, dict[str, int]]:
    b = DictBuilder()
    karte_pcd = karte(b, ["1.234,5", "*", "%null%", "12.000"], [1.5, 2.25, 0.1, 3.0])
    legende_pcd = pane_columns(
        [
            (
                "Klasse",
                "cstring",
                [b.index("cstring", k) for k in ("bis unter 15", "45 und mehr")],
                "value",
            ),
        ]
    )
    info = {
        "workbookLocale": "de_DE",
        "worldUpdate": {
            "applicationPresModel": {
                "workbookPresModel": {"dashboardPresModel": {"zones": zones("2023-2030")}}
            }
        },
    }
    data = {
        "secondaryInfo": {
            "presModelMap": {
                "dataDictionary": {
                    "presModelHolder": {
                        "genDataDictionaryPresModel": {"dataSegments": {"0": b.segment()}}
                    }
                },
                "vizData": {
                    "presModelHolder": {
                        "genPresModelMapPresModel": {
                            "presModelMap": {
                                "Karte": {
                                    "presModelHolder": {
                                        "genVizDataPresModel": {"paneColumnsData": karte_pcd}
                                    }
                                },
                                "Legende": {
                                    "presModelHolder": {
                                        "genVizDataPresModel": {"paneColumnsData": legende_pcd}
                                    }
                                },
                            }
                        }
                    }
                },
            }
        }
    }
    out = []
    for part in (info, data):
        body = json.dumps(part, ensure_ascii=False, separators=(",", ":"))
        out.append(f"{len(body)};{body}")
    lengths = {t: len(v) for t, v in b.lists.items()}
    return "".join(out), lengths


def filter_response(offset: dict[str, int]) -> dict[str, Any]:
    b = DictBuilder(offset)
    karte_pcd = karte(b, ["2.000", "1.500,25", "*", "900"], [0.5, 1.0, 0.2, 0.3])
    return {
        "vqlCmdResponse": {
            "layoutStatus": {
                "applicationPresModel": {
                    "dataDictionary": {"dataSegments": {"1": b.segment()}},
                    "workbookPresModel": {
                        "dashboardPresModel": {"zones": zones("2031-2040", karte_pcd)}
                    },
                }
            }
        }
    }


def main() -> None:
    text, lengths = bootstrap()
    (HERE / "synthetic_bootstrap_de.txt").write_text(text, encoding="utf-8")
    (HERE / "synthetic_filter_response.json").write_text(
        json.dumps(filter_response(lengths), ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
