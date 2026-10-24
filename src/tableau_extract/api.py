"""Python-API: extract(url, **optionen) und list_view(url)."""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from . import __version__
from .acquire import Acquisition, acquire
from .errors import FormatError, InputError
from .fingerprint import fingerprint
from .http import PoliteClient
from .models import ParsedView, RawCapture, SheetTable
from .normalize import (
    ROLE_GEOMETRY,
    ROLE_KEY,
    ROLE_MEASURE,
    ROLE_NAME,
    FieldInfo,
    choose_sheet,
    describe_fields,
    normalize_column,
    snake,
)
from .output import (
    TableData,
    dataframe,
    latest_dir,
    latest_meta,
    load_state,
    save_state,
    stamp_is_fresh,
    write_run,
)
from .regions import assign_regions
from .url import ViewUrl, parse_view_url

DEFAULT_FULL_CHECK_DAYS = 30.0


# --- Ergebnisobjekte -----------------------------------------------------------------


def _html_table(rows: list[tuple[str, Any]], title: str) -> str:
    body = "".join(
        f"<tr><th style='text-align:left'>{html.escape(k)}</th>"
        f"<td style='text-align:left'>{html.escape(str(v))}</td></tr>"
        for k, v in rows
    )
    caption = f"<caption style='text-align:left'><b>{html.escape(title)}</b></caption>"
    return f"<table>{caption}{body}</table>"


def _text_table(rows: list[tuple[str, Any]], title: str) -> str:
    width = max(len(k) for k, _ in rows)
    return "\n".join([title] + [f"  {k.ljust(width)}  {v}" for k, v in rows])


@dataclass
class ExtractResult:
    """Ergebnis von `extract`. Im Notebook erscheint eine kurze Zusammenfassung."""

    status: str  # "neu" | "unverändert"
    df: pd.DataFrame
    meta: dict[str, Any]
    path: Path | None
    reason: str = ""  # bei „unverändert“: "veroeffentlichungsstand" | "daten"
    messages: list[str] = field(default_factory=list)

    @property
    def method(self) -> str:
        return str(self.meta.get("weg", ""))

    @property
    def sheet(self) -> str:
        return str(self.meta.get("blatt", ""))

    def summary(self) -> list[tuple[str, Any]]:
        checks = self.meta.get("pruefungen", {})
        voll = checks.get("vollstaendigkeit", {})
        rows: list[tuple[str, Any]] = [
            ("Status", self.status + (f" ({self.reason})" if self.reason else "")),
            ("Weg", self.method),
            ("Blatt", self.sheet),
            ("Zeilen", len(self.df)),
        ]
        if voll:
            rows.append(
                (
                    "Vollständigkeit",
                    f"{voll.get('gefunden')}/{voll.get('erwartet')} Kreise, "
                    f"Gebietsstand {voll.get('gebietsstand')}"
                    + ("" if voll.get("vollstaendig") else " – Abweichungen, siehe meta"),
                )
            )
        if "gegenprobe" in checks:
            g = checks["gegenprobe"]
            rows.append(
                (
                    "Gegenprobe",
                    f"{g['feld']}: {g['ist']} statt {g['soll']} ({g['abweichung_prozent']:+} %)",
                )
            )
        stand = self.meta.get("veroeffentlichungsstand") or {}
        if stand.get("workbookLastPublishedAt"):
            rows.append(("Veröffentlicht", stand["workbookLastPublishedAt"]))
        rows.append(("Pfad", str(self.path) if self.path else "–"))
        for m in self.messages:
            rows.append(("Hinweis", m))
        return rows

    def _repr_html_(self) -> str:
        return _html_table(self.summary(), "tableau-extract")

    def __repr__(self) -> str:
        return _text_table(self.summary(), "ExtractResult")


@dataclass
class ViewListing:
    """Ergebnis von `list_view`: Blätter, Felder mit Rollen, Filter."""

    url: str
    method: str
    chosen_sheet: str | None
    sheets: dict[str, list[FieldInfo]]
    rows: dict[str, int]
    filters: list[dict[str, Any]]
    stamp: dict[str, Any] | None
    attempts: list[dict[str, Any]]

    def lines(self) -> list[str]:
        out = []
        for name, fields in self.sheets.items():
            mark = "  (gewählt)" if name == self.chosen_sheet else ""
            out.append(f"Blatt: {name}  [{self.rows[name]} Zeilen]{mark}")
            for f in fields:
                extra = " · gerundet" if f.rounded else ""
                extra += " · formatierter Text" if f.source == "alias" else ""
                out.append(f"  {f.original:<60} {f.role:<10} {f.dtype}{extra}  → {f.column}")
        if self.filters:
            out.append("Filter/Parameter:")
            for flt in self.filters:
                out.append(
                    f"  {flt['name']} ({flt['kind']}): {flt['values']}, gewählt {flt['selected']}"
                )
        else:
            out.append("Filter/Parameter: keine")
        if self.stamp:
            out.append(f"Veröffentlicht: {self.stamp.get('workbookLastPublishedAt')}")
        out.append(f"Weg: {self.method}")
        return out

    def __repr__(self) -> str:
        return "\n".join(self.lines())

    def _repr_html_(self) -> str:
        parts = []
        for name, fields in self.sheets.items():
            mark = " (gewählt)" if name == self.chosen_sheet else ""
            rows = "".join(
                f"<tr><td>{html.escape(f.original)}</td><td>{f.role}</td><td>{f.dtype}</td>"
                f"<td>{html.escape(f.column)}</td>"
                f"<td>{'ja' if f.rounded else ''}</td></tr>"
                for f in fields
            )
            parts.append(
                f"<p><b>Blatt {html.escape(name)}</b> – {self.rows[name]} Zeilen{mark}</p>"
                "<table><tr><th>Feld</th><th>Rolle</th><th>Typ</th><th>Spalte</th>"
                f"<th>gerundet</th></tr>{rows}</table>"
            )
        filt = ", ".join(f"{f['name']}: {f['values']}" for f in self.filters) or "keine"
        parts.append(f"<p>Filter/Parameter: {html.escape(filt)}<br>Weg: {self.method}</p>")
        return "".join(parts)


# --- Hilfsfunktionen --------------------------------------------------------------------


def _out_base(view: ViewUrl, out: str | Path | None) -> Path:
    root = Path(out or os.environ.get("TABLEAU_EXTRACT_OUT") or "out")
    return root / view.slug


def _replay(replay: str | Path | None) -> str | None:
    value = replay or os.environ.get("TABLEAU_EXTRACT_REPLAY")
    return str(value) if value else None


def _views(capture: RawCapture) -> list[tuple[dict[str, str], ParsedView]]:
    return capture.filter_views or [({}, capture.view)]


_ABSOLUTE_HINT = re.compile(r"je_|anteil|quote|prozent|rate|_pro_", re.IGNORECASE)


def _check_sum(
    df: pd.DataFrame, fields: list[FieldInfo], target: float, column: str | None
) -> dict[str, Any]:
    measures = [f.column for f in fields if f.role == ROLE_MEASURE]
    if column is None:
        absolute = [c for c in measures if not _ABSOLUTE_HINT.search(c)]
        if not absolute:
            raise InputError(
                "--check-sum: kein Messfeld mit absoluten Werten; --check-field angeben"
            )
        column = absolute[0]
    if column not in measures:
        raise InputError(f"--check-field {column!r} ist kein Messfeld. Messfelder: {measures}")
    ist = sum((v for v in df[column] if v is not None), Decimal(0))
    soll = Decimal(str(target))
    deviation = float(round((ist - soll) / soll * 100, 2)) if soll else 0.0
    return {"feld": column, "soll": float(soll), "ist": float(ist), "abweichung_prozent": deviation}


# --- Hauptablauf -------------------------------------------------------------------------


def _build(
    capture: RawCapture,
    *,
    sheet: str | None,
    year: int | None,
    reference: str | Path | None,
    cwd: Path,
) -> tuple[SheetTable, list[FieldInfo], TableData, dict[str, Any], list[str], Any, str]:
    views = _views(capture)
    first_table = choose_sheet(capture.view, sheet)
    sheet_name = first_table.name
    fields = describe_fields(first_table)
    out_fields = [f for f in fields if f.role not in (ROLE_KEY, ROLE_NAME, ROLE_GEOMETRY)]
    raw_fields = [f for f in fields if f.dtype != "spatial"]
    filter_names = list(views[0][0])
    filter_cols = [snake(n) for n in filter_names]

    columns = ["ags5", "kreis_name", *filter_cols]
    for f in out_fields:
        columns += [f.column, f"{f.column}_typ"]
    raw_header = [*filter_names, *[f.original for f in raw_fields]]
    rows: list[list[Any]] = []
    raw_rows: list[list[Any]] = []
    fp_rows: list[tuple[str, tuple[str, ...], list[Any]]] = []
    warnings: list[str] = []
    completeness: list[dict[str, Any]] = []
    region_info: dict[str, Any] = {}
    locale = capture.view.locale

    for selection, pview in views:
        if sheet_name not in pview.sheets:
            raise FormatError(f"Blatt {sheet_name!r} fehlt im Abzug für {selection}")
        table = pview.sheets[sheet_name]
        if [c.name for c in table.columns] != [f.original for f in fields]:
            raise FormatError(f"Felder des Blatts weichen im Abzug für {selection} ab")
        regions = assign_regions(table, fields, year=year, reference_path=reference, cwd=cwd)
        warnings += [w + (f" [{selection}]" if selection else "") for w in regions.warnings]
        completeness.append(
            {**regions.completeness, **({"filter": selection} if selection else {})}
        )
        region_info = {
            "methode": regions.method,
            "schluesselfeld": regions.key_field,
            "namensfeld": regions.name_field,
        }
        norm = {
            f.original: normalize_column(table.column(f.original), f, pview.locale or locale)
            for f in out_fields
        }
        fvals = tuple(selection[n] for n in filter_names)
        for i in range(table.n_rows):
            row: list[Any] = [regions.ags5[i], regions.names[i], *fvals]
            for f in out_fields:
                row += [norm[f.original][i], f.value_kind]
            rows.append(row)
            raw_vals = [table.column(f.original).values[i] for f in raw_fields]
            raw_rows.append([*fvals, *raw_vals])
            fp_rows.append((regions.ags5[i], fvals, raw_vals))
        warnings += [w for w in pview.warnings if w not in warnings]

    filter_state: Any = (
        {"modus": "alle_werte", "kombinationen": [s for s, _ in views]}
        if capture.filter_views
        else {f.name: f.selected for f in capture.view.filters}
    )
    fp = fingerprint(
        sheet=sheet_name,
        filter_state=filter_state,
        fields=[(f.original, f.column, f.dtype) for f in raw_fields],
        rows=fp_rows,
    )
    table_data = TableData(
        raw_header=raw_header,
        raw_rows=raw_rows,
        columns=columns,
        rows=rows,
        decimal_columns={f.column for f in out_fields if f.role == ROLE_MEASURE},
    )
    extra = {
        "vollstaendigkeit": completeness[0] if len(completeness) == 1 else completeness,
        "kreiszuordnung": region_info,
        "filterzustand": filter_state,
    }
    return first_table, fields, table_data, extra, warnings, filter_state, fp


def extract(
    url: str,
    *,
    out: str | Path | None = None,
    sheet: str | None = None,
    all_filters: bool = False,
    method: str | None = None,
    replay: str | Path | None = None,
    force: bool = False,
    full_check_days: float = DEFAULT_FULL_CHECK_DAYS,
    check_sum: float | None = None,
    check_field: str | None = None,
    gebietsstand: int | None = None,
    referenz: str | Path | None = None,
    timeout: float = 60.0,
    client: PoliteClient | None = None,
    now: datetime | None = None,
    cwd: str | Path | None = None,
) -> ExtractResult:
    """Extrahiert die Daten einer Tableau-Ansicht je Kreis.

    Wirft `ExtractError` (mit `exit_code`) bei ungültiger Eingabe (1), gesperrter
    Quelle (2) oder nicht eindeutiger Kreiszuordnung (3).
    """
    view = parse_view_url(url)
    base = _out_base(view, out)
    now = now or datetime.now(UTC)
    cwd_path = Path(cwd) if cwd else Path.cwd()
    replay_dir = _replay(replay)
    state = load_state(base)
    has_latest = latest_dir(base) is not None

    def skip(stamp: dict[str, Any]) -> bool:
        return has_latest and stamp_is_fresh(state, stamp, now, full_check_days)

    acq: Acquisition = acquire(
        view,
        client=client,
        method=method,
        all_filters=all_filters,
        replay=replay_dir,
        skip_if_stamp=None if (force or replay_dir) else skip,
        timeout=timeout,
    )
    if acq.unchanged_by_stamp:
        return _unchanged(
            base,
            "veroeffentlichungsstand",
            f"unverändert (Veröffentlichungsstand "
            f"{(acq.stamp or {}).get('workbookLastPublishedAt')}), nichts geladen",
        )
    capture = acq.capture
    assert capture is not None

    table, fields, data, extra, warnings, filter_state, fp = _build(
        capture, sheet=sheet, year=gebietsstand, reference=referenz, cwd=cwd_path
    )
    df = dataframe(data)
    checks: dict[str, Any] = {"vollstaendigkeit": extra["vollstaendigkeit"]}
    messages = list(warnings)
    if check_sum is not None:
        checks["gegenprobe"] = _check_sum(df, fields, check_sum, check_field)
        g = checks["gegenprobe"]
        messages.append(
            f"Gegenprobe {g['feld']}: Summe {g['ist']:g}, Soll {g['soll']:g}, "
            f"Abweichung {g['abweichung_prozent']:+} %"
        )

    meta: dict[str, Any] = {
        "tableau_extract_version": __version__,
        "eingabe_url": url,
        "url": view.normalized,
        "slug": view.slug,
        "weg": capture.method,
        "blatt": table.name,
        "blaetter": sorted(capture.view.sheets),
        "filter": [f.as_dict() for f in capture.view.filters],
        "filterzustand": filter_state,
        "felder": [f.as_dict() for f in fields],
        "spalten": data.columns,
        "abrufzeit_utc": now.astimezone(UTC).isoformat(timespec="seconds"),
        "gebietsschema": capture.view.locale,
        "veroeffentlichungsstand": acq.stamp,
        "server": capture.info,
        "rohdaten": [
            {"datei": f"raw/{f.name}", "sha256": f.sha256, "bytes": len(f.content)}
            for f in capture.files
        ],
        "daten_fingerabdruck": fp,
        "fehlversuche": [a.as_dict() for a in acq.attempts if not a.ok],
        "versuche": [a.as_dict() for a in acq.attempts],
        "kreiszuordnung": extra["kreiszuordnung"],
        "pruefungen": checks,
        "warnungen": warnings,
    }

    previous = latest_meta(base)
    new_state = {
        "veroeffentlichungsstand": acq.stamp,
        "letzte_vollpruefung_utc": now.astimezone(UTC).isoformat(timespec="seconds"),
        "daten_fingerabdruck": fp,
    }
    if previous is not None and previous.get("daten_fingerabdruck") == fp:
        if not replay_dir:
            save_state(base, {**new_state, "letzter_lauf": previous.get("lauf")})
        result = _unchanged(
            base, "daten", f"unverändert (Fingerabdruck {fp[:8]}), nichts geschrieben"
        )
        result.messages = messages + result.messages
        if "gegenprobe" in checks:
            result.meta = {
                **result.meta,
                "pruefungen": {
                    **result.meta.get("pruefungen", {}),
                    "gegenprobe": checks["gegenprobe"],
                },
            }
        return result

    meta["lauf"] = f"{now.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}_{fp[:8]}"
    path = write_run(base, fingerprint=fp, now=now, table=data, meta=meta, raw_files=capture.files)
    if not replay_dir:
        save_state(base, {**new_state, "letzter_lauf": meta["lauf"]})
    return ExtractResult("neu", df, meta, path, messages=messages)


def _unchanged(base: Path, reason: str, message: str) -> ExtractResult:
    d = latest_dir(base)
    assert d is not None
    meta = latest_meta(base) or {}
    df = pd.read_parquet(d / "kreise.parquet")
    for c in df.columns:
        if not any(isinstance(v, Decimal) for v in df[c].dropna()):
            df[c] = df[c].astype("string")
    return ExtractResult("unverändert", df, meta, base / "latest", reason, [message])


def list_view(
    url: str,
    *,
    method: str | None = None,
    replay: str | Path | None = None,
    timeout: float = 60.0,
    client: PoliteClient | None = None,
) -> ViewListing:
    """Blätter, Felder mit Rollen sowie Filter einer Ansicht; schreibt nichts."""
    view = parse_view_url(url)
    acq = acquire(view, client=client, method=method, replay=_replay(replay), timeout=timeout)
    capture = acq.capture
    assert capture is not None
    try:
        chosen: str | None = choose_sheet(capture.view).name
    except InputError:
        chosen = None
    return ViewListing(
        url=view.normalized,
        method=capture.method,
        chosen_sheet=chosen,
        sheets={n: describe_fields(t) for n, t in sorted(capture.view.sheets.items())},
        rows={n: t.n_rows for n, t in capture.view.sheets.items()},
        filters=[f.as_dict() for f in capture.view.filters],
        stamp=acq.stamp,
        attempts=[a.as_dict() for a in acq.attempts],
    )
