"""Normalisierung: Feldrollen, Spaltennamen, Blattwahl, Zahlen, Sonderwerte, Klassen."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import FormatError, InputError
from .models import Column, ParsedView, SheetTable, Value

ROLE_KEY = "schluessel"
ROLE_NAME = "name"
ROLE_MEASURE = "messwert"
ROLE_DIMENSION = "dimension"
ROLE_CLASS = "klasse"
ROLE_GEOMETRY = "geometrie"

_AGG = re.compile(r"^(SUM|AVG|MIN|MAX|MEDIAN|CNT|CNTD|ATTR|AGG|STDEV|VAR|COLLECT)\((.*)\)$")
_KEY_NAME = re.compile(
    r"(^|[^a-z])(krs|ags|ars|rs|kreis_?schl|schl(ue|ü)ssel|kreiskennziffer)", re.IGNORECASE
)
_NAME_NAME = re.compile(r"name|kreis|bezeichnung", re.IGNORECASE)
_CLASS_NAME = re.compile(r"\((klassen|klasse|bins|gruppen)\)\s*$", re.IGNORECASE)
_CLASS_VALUE = re.compile(
    r"bis unter|und mehr|unter \d|über \d|ab \d|\d\s*[-–]\s*\d|^[<>≤≥]|\d\s*bis\s*\d",
    re.IGNORECASE,
)
_GENERATED = re.compile(r"^(Latitude|Longitude) \(generated\)$|^(Breitengrad|Längengrad)")
_ROUND = re.compile(r"\s*\(Round\)", re.IGNORECASE)

#: Sonderwerte, die in kreise.csv leer werden
SPECIAL_VALUES = {"", "null", "%null%", "*", "-", "–", "%missing%", ".", "x", "..."}


@dataclass
class FieldInfo:
    """Ein Feld der Ansicht mit abgeleiteter Rolle und Spaltenname."""

    original: str
    column: str
    dtype: str
    role: str
    source: str  # "value" | "alias" (formatierter Text)
    rounded: bool = False

    @property
    def value_kind(self) -> str:
        return "klasse" if self.role == ROLE_CLASS else "wert"

    def as_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "spalte": self.column,
            "datentyp": self.dtype,
            "rolle": self.role,
            "werttyp": self.value_kind,
            "quelle_wert": "formatierter_alias" if self.source == "alias" else "rohwert",
            "im_datenmodell_gerundet": self.rounded,
        }


# --- Rollen und Namen ------------------------------------------------------


def _inner(caption: str) -> tuple[str | None, str]:
    m = _AGG.match(caption.strip())
    return (m.group(1), m.group(2)) if m else (None, caption.strip())


def _is_keylike(values: list[Value]) -> bool:
    present = [v for v in values if v is not None and str(v).strip() != ""]
    if not present:
        return False
    for v in present:
        if isinstance(v, float) and not v.is_integer():
            return False
        digits = str(int(v)) if isinstance(v, (int, float)) else str(v).strip()
        if not digits.isdigit() or not 4 <= len(digits) <= 8:
            return False
    return True


def classify(col: Column) -> str:
    agg, inner = _inner(col.name)
    if col.dtype == "spatial" or agg == "COLLECT" or _GENERATED.match(col.name):
        return ROLE_GEOMETRY
    if agg is None and _KEY_NAME.search(inner) and _is_keylike(col.values):
        return ROLE_KEY
    texts = [v for v in col.values if isinstance(v, str) and v.strip()]
    if _CLASS_NAME.search(inner):
        return ROLE_CLASS
    if col.dtype == "cstring" and texts and agg is None:
        share = sum(bool(_CLASS_VALUE.search(t)) for t in texts) / len(texts)
        if share >= 0.9 and len(set(texts)) <= max(12, len(texts) // 10):
            return ROLE_CLASS
        if _NAME_NAME.search(inner):
            return ROLE_NAME
    if agg is not None or col.dtype in ("real", "integer"):
        return ROLE_MEASURE
    return ROLE_DIMENSION


def snake(text: str) -> str:
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    text = text.replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "feld"


def column_name(caption: str) -> str:
    _, inner = _inner(caption)
    return snake(_ROUND.sub("", inner))


RESERVED = {"ags5", "kreis_name"}


def describe_fields(table: SheetTable) -> list[FieldInfo]:
    """Rollen und eindeutige Spaltennamen für alle Felder eines Blatts."""
    used = set(RESERVED)
    fields = []
    for col in table.columns:
        role = classify(col)
        base = column_name(col.name)
        name = base
        n = 2
        while name in used or name.endswith("_typ"):
            name = f"{base}_{n}"
            n += 1
        used.add(name)
        fields.append(
            FieldInfo(
                original=col.name,
                column=name,
                dtype=col.dtype,
                role=role,
                source=col.source,
                rounded=bool(_ROUND.search(col.name)),
            )
        )
    return fields


# --- Blattwahl -------------------------------------------------------------


def choose_sheet(view: ParsedView, forced: str | None = None) -> SheetTable:
    names = sorted(view.sheets)
    if forced is not None:
        if forced not in view.sheets:
            raise InputError(
                f"Blatt {forced!r} gibt es nicht. Vorhandene Blätter: {', '.join(names)}"
            )
        return view.sheets[forced]
    scored = []
    for name in names:
        roles = {f.role for f in describe_fields(view.sheets[name])}
        score = (ROLE_KEY in roles) * 2 + (ROLE_GEOMETRY in roles)
        if score:
            scored.append((score, view.sheets[name].n_rows, name))
    if not scored:
        raise InputError(
            "Kein Blatt mit Kreisschlüssel oder Geometrie gefunden. "
            f"Bitte mit --sheet wählen. Vorhandene Blätter: {', '.join(names)}"
        )
    scored.sort(reverse=True)
    return view.sheets[scored[0][2]]


# --- Werte -------------------------------------------------------------------


def is_special(value: Value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:  # NaN
        return True
    return isinstance(value, str) and value.strip().lower() in SPECIAL_VALUES


_EN = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")
_DE = re.compile(r"^[+-]?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$")


def parse_number(value: Value, locale: str | None) -> Decimal | None:
    """Zahl exakt als Decimal; formatierte Texte gemäß Gebietsschema der Arbeitsmappe.

    Sonderwerte ergeben None. Nicht eindeutig lesbare Texte führen zu FormatError.
    """
    if is_special(value):
        return None
    if isinstance(value, bool):
        raise FormatError(f"Wahrheitswert statt Zahl: {value!r}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    text = str(value).strip().replace(" ", "").replace(" ", "").replace(" ", "")
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    lang = (locale or "").split("_")[0].split("-")[0].lower()
    if lang in ("de", "fr", "it", "es", "nl", "pt", "da", "pl", "cs"):
        if not _DE.match(text):
            raise FormatError(f"Zahl {value!r} passt nicht zum Gebietsschema {locale}")
        text = text.replace(".", "").replace(",", ".")
    elif lang in ("en", ""):
        if not _EN.match(text):
            raise FormatError(f"Zahl {value!r} passt nicht zum Gebietsschema {locale or 'en'}")
        text = text.replace(",", "")
    else:
        raise FormatError(f"Gebietsschema {locale!r} wird für formatierte Zahlen nicht unterstützt")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - durch Regex ausgeschlossen
        raise FormatError(f"Zahl {value!r} nicht lesbar") from exc
    return number / 100 if percent else number


def text_value(value: Value) -> str | None:
    if is_special(value):
        return None
    return str(value)


def normalize_column(col: Column, field: FieldInfo, locale: str | None) -> list[Any]:
    """Werte einer Spalte für kreise.csv: Messwerte als Decimal, sonst Text; Sonderwerte None."""
    if field.role == ROLE_MEASURE:
        out: list[Any] = []
        for v in col.values:
            try:
                out.append(parse_number(v, locale))
            except FormatError as exc:
                raise FormatError(f"Feld {col.name!r}: {exc}") from exc
        return out
    return [text_value(v) for v in col.values]
