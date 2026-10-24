"""Ausgabeordner schreiben, latest pflegen, Zustand der Änderungserkennung führen.

Aufbau:
    out/<slug>/<UTC>_<sha8>/{data_raw.csv, kreise.csv, kreise.parquet, meta.json, raw/}
    out/<slug>/latest -> <UTC>_<sha8>
    out/<slug>/state.json
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .fingerprint import raw_text
from .models import RawFile


@dataclass
class TableData:
    """Fertige Tabellen für einen Lauf."""

    raw_header: list[str]
    raw_rows: list[list[Any]]
    columns: list[str]  # Spalten von kreise.csv
    rows: list[list[Any]]  # Werte (str, Decimal oder None)
    decimal_columns: set[str]


# --- Zustand -----------------------------------------------------------------------


def load_state(base: Path) -> dict[str, Any]:
    p = base / "state.json"
    if not p.is_file():
        return {}
    try:
        data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
        return data
    except (OSError, ValueError):
        return {}


def save_state(base: Path, state: dict[str, Any]) -> None:
    base.mkdir(parents=True, exist_ok=True)
    tmp = base / f".state-{uuid.uuid4().hex}.json"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, base / "state.json")


def latest_dir(base: Path) -> Path | None:
    link = base / "latest"
    if link.is_symlink() or link.is_dir():
        target = link.resolve()
        if (target / "meta.json").is_file():
            return target
    return None


def latest_meta(base: Path) -> dict[str, Any] | None:
    d = latest_dir(base)
    if d is None:
        return None
    data: dict[str, Any] = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    return data


def stamp_is_fresh(
    state: dict[str, Any], stamp: dict[str, Any], now: datetime, full_check_days: float
) -> bool:
    """True, wenn der Vollabruf laut Vorabprüfung entfallen kann."""
    if not state or state.get("veroeffentlichungsstand") != stamp:
        return False
    last = state.get("letzte_vollpruefung_utc")
    if not last:
        return False
    try:
        when = datetime.fromisoformat(last)
    except ValueError:
        return False
    return now - when < timedelta(days=full_check_days)


# --- Schreiben ---------------------------------------------------------------------------


def _csv_bytes(header: list[str], rows: list[list[Any]], fmt: Any) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(header)
    for row in rows:
        w.writerow([fmt(v) for v in row])
    return buf.getvalue().encode("utf-8")


def _fmt_norm(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return format(v, "f")
    return str(v)


def dataframe(table: TableData) -> pd.DataFrame:
    df = pd.DataFrame(table.rows, columns=table.columns, dtype=object)
    for c in table.columns:
        if c not in table.decimal_columns:
            df[c] = df[c].astype("string")
    return df


def _arrow_table(table: TableData, meta: dict[str, Any]) -> pa.Table:
    arrays = []
    fields = []
    for i, name in enumerate(table.columns):
        values = [row[i] for row in table.rows]
        if name in table.decimal_columns:
            present = [v for v in values if v is not None]
            scale = max((max(0, -v.as_tuple().exponent) for v in present), default=0)
            q = Decimal(1).scaleb(-scale)
            quantized = [None if v is None else v.quantize(q) for v in values]
            digits = max((len(v.as_tuple().digits) for v in quantized if v is not None), default=1)
            precision = min(38, max(digits, scale + 1))
            typ: pa.DataType = pa.decimal128(precision, scale)
            arrays.append(pa.array(quantized, type=typ))
        else:
            typ = pa.string()
            arrays.append(pa.array([None if v is None else str(v) for v in values], type=typ))
        fields.append(pa.field(name, typ))
    schema = pa.schema(
        fields,
        metadata={
            b"tableau_extract": json.dumps(meta, ensure_ascii=False).encode("utf-8"),
        },
    )
    return pa.Table.from_arrays(arrays, schema=schema)


def write_run(
    base: Path,
    *,
    fingerprint: str,
    now: datetime,
    table: TableData,
    meta: dict[str, Any],
    raw_files: list[RawFile],
) -> Path:
    """Schreibt einen Lauf atomar und hängt `latest` um. Gibt den Ordner zurück."""
    base.mkdir(parents=True, exist_ok=True)
    name = f"{now.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}_{fingerprint[:8]}"
    final = base / name
    tmp = base / f".tmp-{uuid.uuid4().hex}"
    tmp.mkdir()
    try:
        (tmp / "raw").mkdir()
        for f in raw_files:
            (tmp / "raw" / f.name).write_bytes(f.content)
        (tmp / "data_raw.csv").write_bytes(_csv_bytes(table.raw_header, table.raw_rows, raw_text))
        (tmp / "kreise.csv").write_bytes(_csv_bytes(table.columns, table.rows, _fmt_norm))
        pq.write_table(_arrow_table(table, meta), tmp / "kreise.parquet")
        (tmp / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if final.exists():
            shutil.rmtree(final)
        os.replace(tmp, final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    link_tmp = base / f".latest-{uuid.uuid4().hex}"
    os.symlink(name, link_tmp)
    os.replace(link_tmp, base / "latest")
    return final
