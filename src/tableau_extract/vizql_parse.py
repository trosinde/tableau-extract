"""Parser für VizQL-Antworten (bootstrapSession): Datenwörterbuch und Blätter.

Format der `bootstrapSession`-Antwort: mehrere JSON-Segmente, jeweils mit
Längenpräfix in Zeichen, also `<länge>;{json}<länge>;{json}`.

- Segment 0 („info“): Arbeitsmappe, Dashboard-Zonen (Filter, Parameter), `workbookLocale`.
- Segment 1 („data“): `secondaryInfo.presModelMap` mit
  - `dataDictionary`: alle Werte, nach Datentyp in Listen (`integer`, `real`, `cstring`, …),
  - `vizData`: je Blatt `paneColumnsData` mit Indizes in diese Listen.

Ein Index ≥ 0 zeigt in die Liste des Feld-Datentyps, ein Index < 0 auf einen
formatierten Text in `cstring` (Position `-i-1`). Antworten auf Befehle (z. B.
Filter setzen) ergänzen das Datenwörterbuch um neue Segmente; die Indizes
beziehen sich dann auf die Verkettung aller Segmente.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .errors import FormatError
from .models import Column, Filter, ParsedView, SheetTable, Value

_PREFIX = re.compile(r"(\d+);")


def split_segments(text: str) -> list[Any]:
    """Zerlegt eine Antwort im Längenpräfix-Format in ihre JSON-Segmente."""
    parts: list[Any] = []
    i = 0
    text = text.lstrip("﻿")
    while i < len(text):
        m = _PREFIX.match(text, i)
        if m is None:
            raise FormatError(f"bootstrapSession: kein Längenpräfix an Position {i}")
        start = m.end()
        end = start + int(m.group(1))
        if end > len(text):
            raise FormatError("bootstrapSession: Antwort ist abgeschnitten")
        try:
            parts.append(json.loads(text[start:end]))
        except json.JSONDecodeError as exc:
            raise FormatError(f"bootstrapSession: Segment {len(parts)} ist kein JSON") from exc
        i = end
    if not parts:
        raise FormatError("bootstrapSession: leere Antwort")
    return parts


def _get(d: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(d, dict) or key not in d:
            return None
        d = d[key]
    return d


class VizState:
    """Zustand einer Sitzung: Datenwörterbuch (kumulativ), Blätter, Zonen, Gebietsschema."""

    def __init__(self) -> None:
        self.segments: dict[str, dict[str, Any]] = {}
        self.sheets: dict[str, dict[str, Any]] = {}  # Blattname -> paneColumnsData
        self.zones: dict[str, Any] = {}
        self.locale: str | None = None
        self.warnings: list[str] = []

    # --- Einlesen -------------------------------------------------------

    @classmethod
    def from_bootstrap(cls, text: str) -> VizState:
        parts = split_segments(text)
        state = cls()
        info = parts[0]
        state.locale = info.get("workbookLocale") if isinstance(info, dict) else None
        state.zones = (
            _get(
                info,
                "worldUpdate",
                "applicationPresModel",
                "workbookPresModel",
                "dashboardPresModel",
                "zones",
            )
            or {}
        )
        if len(parts) < 2:
            raise FormatError(
                "bootstrapSession enthält kein Datensegment (secondaryInfo); "
                "die Ansicht liefert keine Daten an den Client"
            )
        pmm = _get(parts[1], "secondaryInfo", "presModelMap")
        if not isinstance(pmm, dict):
            raise FormatError("bootstrapSession: secondaryInfo.presModelMap fehlt")
        segs = _get(
            pmm, "dataDictionary", "presModelHolder", "genDataDictionaryPresModel", "dataSegments"
        )
        if not isinstance(segs, dict):
            raise FormatError("bootstrapSession: Datenwörterbuch (dataSegments) fehlt")
        state._add_segments(segs)
        sheets = _get(pmm, "vizData", "presModelHolder", "genPresModelMapPresModel", "presModelMap")
        if not isinstance(sheets, dict):
            raise FormatError("bootstrapSession: vizData fehlt")
        for name, holder in sheets.items():
            pcd = _get(holder, "presModelHolder", "genVizDataPresModel", "paneColumnsData")
            if isinstance(pcd, dict):
                state.sheets[name] = pcd
        return state

    def apply_command_response(self, response: dict[str, Any]) -> None:
        """Übernimmt die Antwort eines Befehls (Filter/Parameter setzen)."""
        apm = _get(response, "vqlCmdResponse", "layoutStatus", "applicationPresModel")
        if not isinstance(apm, dict):
            raise FormatError("Befehlsantwort ohne applicationPresModel")
        segs = _get(apm, "dataDictionary", "dataSegments")
        if isinstance(segs, dict):
            self._add_segments(segs)
        zones = _get(apm, "workbookPresModel", "dashboardPresModel", "zones")
        if isinstance(zones, dict):
            for zid, zone in zones.items():
                if zone is None:
                    continue
                self.zones[zid] = zone
                pcd = _get(zone, "presModelHolder", "visual", "vizData", "paneColumnsData")
                if isinstance(pcd, dict) and zone.get("worksheet"):
                    self.sheets[zone["worksheet"]] = pcd

    def _add_segments(self, segs: dict[str, Any]) -> None:
        for key, seg in segs.items():
            if seg is not None and key not in self.segments:
                self.segments[key] = seg

    # --- Auswerten ------------------------------------------------------

    def data_lists(self) -> dict[str, list[Any]]:
        """Verkettet die Werte aller Segmente je Datentyp (Segmentreihenfolge wie geliefert)."""
        full: dict[str, list[Any]] = {}
        for seg in self.segments.values():
            for col in seg.get("dataColumns", []):
                full.setdefault(col["dataType"], []).extend(col["dataValues"])
        return full

    def sheet_table(self, name: str) -> SheetTable:
        pcd = self.sheets[name]
        data = self.data_lists()
        cstring = data.get("cstring", [])
        columns: list[Column] = []
        seen: dict[str, int] = {}
        for vdc in pcd.get("vizDataColumns", []):
            caption = vdc.get("fieldCaption")
            if not caption:
                continue
            dtype = vdc.get("dataType") or "cstring"
            values: list[Value] = []
            formatted = False
            for pane_i, col_i in zip(
                vdc.get("paneIndices", []), vdc.get("columnIndices", []), strict=False
            ):
                pane = pcd["paneColumnsList"][pane_i]["vizPaneColumns"][col_i]
                idx = pane.get("valueIndices") or pane.get("aliasIndices") or []
                source = data.get(dtype, cstring)
                for j in idx:
                    if j < 0:
                        formatted = True
                        values.append(_at(cstring, -j - 1, caption))
                    else:
                        values.append(_at(source, j, caption))
            if caption in seen:
                seen[caption] += 1
                caption = f"{caption} ({vdc.get('fn') or seen[caption]})"
            else:
                seen[caption] = 1
            columns.append(Column(caption, dtype, values, "alias" if formatted else "value"))

        if not columns:
            return SheetTable(name, [])
        n = max(len(c.values) for c in columns)
        kept = [c for c in columns if len(c.values) == n]
        for c in columns:
            if len(c.values) != n:
                self.warnings.append(
                    f"Blatt {name!r}: Feld {c.name!r} hat {len(c.values)} statt {n} Werte "
                    "und wird nicht übernommen"
                )
        return SheetTable(name, kept)

    def filters(self) -> list[Filter]:
        """Filter (aus `filtersJson` bzw. Schnellfiltern) und Parameter der Ansicht."""
        found: dict[str, Filter] = {}
        for zone in self.zones.values():
            holder = (zone or {}).get("presModelHolder") or {}
            fj = _get(holder, "visual", "filtersJson")
            if isinstance(fj, str) and fj:
                for f in _filters_from_json(fj):
                    found.setdefault(f.name, f)
            qf = _get(holder, "quickFilterDisplay", "quickFilter", "categoricalFilter")
            if isinstance(qf, dict) and qf.get("fn") and qf["fn"] not in found:
                found[qf["fn"]] = _filter_from_quickfilter(qf)
            pc = holder.get("parameterControl")
            if isinstance(pc, dict) and pc.get("parameterName"):
                values = [str(v) for v in pc.get("formattedValues") or []]
                current = pc.get("formattedValue") or pc.get("valueAlias")
                found[pc["parameterName"]] = Filter(
                    name=pc.get("fieldCaption") or pc["parameterName"],
                    values=values,
                    selected=[str(current)] if current is not None else [],
                    kind="parameter",
                    field=pc["parameterName"],
                )
        return list(found.values())

    def to_view(self) -> ParsedView:
        sheets = {name: self.sheet_table(name) for name in self.sheets}
        return ParsedView(
            sheets=sheets,
            filters=self.filters(),
            locale=self.locale,
            warnings=list(self.warnings),
        )


def _at(values: list[Any], i: int, caption: str) -> Value:
    if i >= len(values):
        raise FormatError(f"Feld {caption!r}: Index {i} außerhalb des Datenwörterbuchs")
    v = values[i]
    return v if v is None or isinstance(v, (str, int, float)) else json.dumps(v)


def _filters_from_json(text: str) -> list[Filter]:
    try:
        tables = json.loads(text)
    except json.JSONDecodeError:
        return []
    out: list[Filter] = []
    for t in tables if isinstance(tables, list) else []:
        table = t.get("table") if isinstance(t, dict) else None
        if not isinstance(table, dict) or "schema" not in table or "tuples" not in table:
            continue
        tuples = [tp for tp in table["tuples"] if tp.get("t")]
        values = [str(tp["t"][0]["v"]) for tp in tuples]
        selected = [str(tp["t"][0]["v"]) for tp in tuples if tp.get("s")]
        if t.get("all") or t.get("allChecked"):
            selected = list(values)
        for col in table["schema"]:
            name = col.get("caption") or str(col.get("name"))
            ds_field = col.get("name") or ["", name]
            out.append(
                Filter(
                    name=name,
                    values=values,
                    selected=selected,
                    kind="filter",
                    field=f"[{ds_field[0]}].[{ds_field[1]}]",
                    worksheet=t.get("worksheet"),
                )
            )
    return out


def _filter_from_quickfilter(qf: dict[str, Any]) -> Filter:
    values: list[str] = []
    selected: list[str] = []
    for table in qf.get("domainTables") or []:
        for item in table.get("domain") or []:
            label = str(item.get("label", item.get("value", "")))
            values.append(label)
            if item.get("isSelected"):
                selected.append(label)
    caption = qf.get("fieldCaption") or qf["fn"]
    return Filter(name=caption, values=values, selected=selected, kind="filter", field=qf["fn"])


def parse_bootstrap(text: str, locale: str | None = None) -> ParsedView:
    """Liest eine `bootstrapSession`-Antwort in eine `ParsedView`."""
    state = VizState.from_bootstrap(text)
    if state.locale is None:
        state.locale = locale
    return state.to_view()
