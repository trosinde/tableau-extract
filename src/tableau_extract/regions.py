"""Kreiszuordnung: Schlüssel normalisieren, Namensabgleich, Vollständigkeit."""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

from .errors import AmbiguousRegionError, InputError
from .models import SheetTable, Value
from .normalize import ROLE_KEY, ROLE_NAME, FieldInfo, is_special


def normalize_key(value: Value) -> str | None:
    """Kreisschlüssel als 5-stelliger Text.

    4–5 Stellen: Kreisform, auf 5 aufgefüllt (`8111` → `08111`).
    7–8 Stellen: Gemeindeform, auf 8 aufgefüllt, erste 5 (`9764000` → `09764`).
    Alles andere ist ungültig (None).
    """
    if is_special(value):
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    digits = str(value).strip()
    if not digits.isdigit():
        return None
    if len(digits) in (4, 5):
        return digits.zfill(5)
    if len(digits) in (7, 8):
        return digits.zfill(8)[:5]
    return None


# --- Referenzliste -----------------------------------------------------------


@dataclass
class Reference:
    year: int
    origin: str  # "pfad" | "projekt" | "paket"
    path: str
    rows: list[dict[str, str]]

    @property
    def by_key(self) -> dict[str, dict[str, str]]:
        return {r["ags5"]: r for r in self.rows}


def available_years() -> list[int]:
    years = []
    for entry in files("tableau_extract.data").iterdir():
        m = re.fullmatch(r"kreise_(\d{4})\.csv", entry.name)
        if m:
            years.append(int(m.group(1)))
    return sorted(years)


def year_from_fields(names: list[str]) -> int | None:
    """Gebietsstand aus Feldnamen wie `krs23` oder `kreise_2023` ableiten."""
    for name in names:
        m = re.search(r"(?<!\d)(20\d{2}|\d{2})(?!\d)", name)
        if m:
            y = int(m.group(1))
            return y if y > 1000 else 2000 + y
    return None


def load_reference(
    year: int | None,
    *,
    path: str | Path | None = None,
    cwd: Path | None = None,
) -> tuple[Reference, list[str]]:
    """Referenzliste nach Suchreihenfolge: Pfad → ./config/kreise_<JJJJ>.csv → Paket."""
    warnings: list[str] = []
    if path is not None:
        p = Path(path)
        if not p.is_file():
            raise InputError(f"Referenzliste {p} nicht gefunden")
        y = year or year_from_fields([p.name]) or 0
        return Reference(y, "pfad", str(p), _read(p.read_text("utf-8"))), warnings

    years = available_years()
    if year is None:
        year = years[-1]
    chosen = year
    project = (cwd or Path.cwd()) / "config" / f"kreise_{year}.csv"
    if project.is_file():
        return Reference(year, "projekt", str(project), _read(project.read_text("utf-8"))), []
    if year not in years:
        earlier = [y for y in years if y <= year]
        chosen = earlier[-1] if earlier else years[0]
        warnings.append(f"Keine Referenzliste für Gebietsstand {year}; verwendet wird {chosen}")
    res = files("tableau_extract.data").joinpath(f"kreise_{chosen}.csv")
    return (
        Reference(
            chosen,
            "paket",
            f"tableau_extract/data/kreise_{chosen}.csv",
            _read(res.read_text("utf-8")),
        ),
        warnings,
    )


def _read(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(text.splitlines(), delimiter=";"))
    if not rows or not {"ags5", "name"} <= set(rows[0]):
        raise InputError("Referenzliste braucht die Spalten ags5;name[;typ]")
    for r in rows:
        r["ags5"] = r["ags5"].zfill(5)
    return rows


# --- Namensabgleich ------------------------------------------------------------

_STADT_TYPES = {"kreisfreie stadt", "stadtkreis"}
_SUFFIXES = [
    (r",\s*kreisfreie stadt$", "stadt"),
    (r"\(kreisfreie stadt\)$", "stadt"),
    (r",\s*landkreis$", "kreis"),
    (r",\s*kreis$", "kreis"),
    (r"^landkreis\s+", "kreis"),
    (r"^lk\s+", "kreis"),
    (r"^kreis\s+", "kreis"),
    (r"^stadtkreis\s+", "stadt"),
    (r",\s*stadtkreis$", "stadt"),
    (r"^sk\s+", "stadt"),
    (r"^kreisfreie stadt\s+", "stadt"),
    (r",\s*[a-z-]*stadt$", "stadt"),  # , Stadt / , Landeshauptstadt / , Hansestadt …
]


def _fold(text: str) -> str:
    text = text.lower().strip()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text)


def split_name(name: str) -> tuple[str, str | None]:
    """(Grundname, Typ-Hinweis 'stadt'|'kreis'|None)."""
    text = _fold(name)
    hint = None
    for pattern, h in _SUFFIXES:
        new = re.sub(pattern, "", text).strip()
        if new != text:
            text, hint = new, hint or h
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text, hint


def _ref_type(row: dict[str, str]) -> str:
    return "stadt" if row.get("typ", "").strip().lower() in _STADT_TYPES else "kreis"


def match_name(name: str, ref: Reference) -> tuple[str | None, list[str]]:
    """Schlüssel zu einem Namen; (None, Kandidaten) bei keinem oder mehreren Treffern."""
    base, hint = split_name(name)
    candidates = []
    for row in ref.rows:
        rbase, rhint = split_name(row["name"])
        if rbase != base:
            continue
        rtype = rhint or _ref_type(row)
        if hint is not None and rtype != hint:
            continue
        candidates.append(row)
    if len(candidates) == 1:
        return candidates[0]["ags5"], []
    return None, [f"{r['ags5']} {r['name']} ({r.get('typ', '?')})" for r in candidates]


# --- Zuordnung und Vollständigkeit ------------------------------------------------


@dataclass
class RegionResult:
    ags5: list[str]
    names: list[str | None]
    reference: Reference
    key_field: str | None
    name_field: str | None
    method: str  # "schluessel" | "name"
    completeness: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def assign_regions(
    table: SheetTable,
    fields: list[FieldInfo],
    *,
    year: int | None = None,
    reference_path: str | Path | None = None,
    cwd: Path | None = None,
    rows_per_region: int = 1,
) -> RegionResult:
    """Ordnet jeder Zeile einen Kreis zu; wirft AmbiguousRegionError bei Unklarheit."""
    key_f = next((f for f in fields if f.role == ROLE_KEY), None)
    name_f = next((f for f in fields if f.role == ROLE_NAME), None)
    if key_f is None and name_f is None:
        raise AmbiguousRegionError(
            f"Blatt {table.name!r} hat weder Kreisschlüssel noch Kreisnamen",
            {"felder": [f.original for f in fields]},
        )
    if year is None:
        year = year_from_fields([f.original for f in (key_f, name_f) if f is not None])
    ref, warnings = load_reference(year, path=reference_path, cwd=cwd)
    names: list[str | None] = (
        [None if is_special(v) else str(v) for v in table.column(name_f.original).values]
        if name_f
        else [None] * table.n_rows
    )

    problems: list[dict[str, Any]] = []
    ags5: list[str] = []
    if key_f is not None:
        method = "schluessel"
        for i, v in enumerate(table.column(key_f.original).values):
            k = normalize_key(v)
            if k is None:
                problems.append(
                    {"zeile": i, "wert": v, "name": names[i], "grund": "ungültiger Kreisschlüssel"}
                )
                ags5.append("")
            else:
                ags5.append(k)
    else:
        assert name_f is not None
        method = "name"
        for i, n in enumerate(names):
            k, cands = match_name(n, ref) if n else (None, [])
            if k is None:
                grund = "mehrdeutiger Name" if cands else "Name nicht in Referenzliste"
                problems.append({"zeile": i, "name": n, "grund": grund, "kandidaten": cands})
                ags5.append("")
            else:
                ags5.append(k)
    if problems:
        lines = "; ".join(
            f"{p.get('name') or p.get('wert')}: {p['grund']}"
            + (f" ({', '.join(p['kandidaten'])})" if p.get("kandidaten") else "")
            for p in problems[:10]
        )
        raise AmbiguousRegionError(
            f"{len(problems)} Zeile(n) nicht eindeutig einem Kreis zuzuordnen: {lines}",
            {"nicht_zugeordnet": problems},
        )

    completeness = check_completeness(ags5, ref, rows_per_region=rows_per_region)
    if completeness["fehlend"] or completeness["ueberzaehlig"] or completeness["doppelt"]:
        warnings.append(
            f"Vollständigkeit: {completeness['gefunden']}/{completeness['erwartet']} Kreise, "
            f"fehlend {[m['ags5'] for m in completeness['fehlend']]}, "
            f"überzählig {completeness['ueberzaehlig']}, doppelt {completeness['doppelt']}"
        )
    return RegionResult(
        ags5=ags5,
        names=names,
        reference=ref,
        key_field=key_f.original if key_f else None,
        name_field=name_f.original if name_f else None,
        method=method,
        completeness=completeness,
        warnings=warnings,
    )


def check_completeness(
    ags5: list[str], ref: Reference, *, rows_per_region: int = 1
) -> dict[str, Any]:
    by_key = ref.by_key
    counts: dict[str, int] = {}
    for k in ags5:
        counts[k] = counts.get(k, 0) + 1
    missing = [{"ags5": k, "name": by_key[k]["name"]} for k in sorted(by_key) if k not in counts]
    extra = sorted(k for k in counts if k not in by_key)
    double = sorted(k for k, c in counts.items() if c > rows_per_region)
    return {
        "gebietsstand": f"31.12.{ref.year}",
        "referenz": ref.origin,
        "referenz_datei": ref.path,
        "erwartet": len(by_key),
        "gefunden": len(set(counts) & set(by_key)),
        "fehlend": missing,
        "ueberzaehlig": extra,
        "doppelt": double,
        "vollstaendig": not missing and not extra and not double,
    }
