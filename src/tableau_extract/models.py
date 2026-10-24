"""Gemeinsame Datentypen: Versuchsprotokoll, Rohdaten, Blatt-Tabellen."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

Value = str | int | float | None


@dataclass
class Attempt:
    """Ein Eintrag im Versuchsprotokoll (je Weg bzw. Anfrage)."""

    method: str
    ok: bool
    url: str | None = None
    status: int | None = None
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "ok": self.ok,
            "url": self.url,
            "status": self.status,
            "message": self.message,
        }


@dataclass
class RawFile:
    """Eine unveränderte Rohantwort, wie sie unter `raw/` abgelegt wird."""

    name: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass
class Column:
    """Eine Spalte eines Blatts mit den Werten genau wie von Tableau geliefert."""

    name: str
    dtype: str
    values: list[Value]
    #: "alias" = formatierter Text aus dem Datenwörterbuch, "value" = Rohwert
    source: str = "value"


@dataclass
class Filter:
    name: str
    values: list[str]
    selected: list[str]
    kind: str = "filter"  # "filter" | "parameter"
    #: interner Feldname für Befehle (`[ds].[feld]` bzw. Parametername)
    field: str = ""
    worksheet: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "field": self.field,
            "worksheet": self.worksheet,
            "values": self.values,
            "selected": self.selected,
        }


@dataclass
class SheetTable:
    """Ein Blatt der Ansicht als Tabelle (Spalten gleicher Länge)."""

    name: str
    columns: list[Column]

    @property
    def n_rows(self) -> int:
        return len(self.columns[0].values) if self.columns else 0

    def column(self, name: str) -> Column:
        for col in self.columns:
            if col.name == name:
                return col
        raise KeyError(name)


@dataclass
class ParsedView:
    """Ergebnis des Parsers: alle Blätter, Filter und das Gebietsschema."""

    sheets: dict[str, SheetTable]
    filters: list[Filter] = field(default_factory=list)
    locale: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class RawCapture:
    """Was ein Extraktionsweg liefert: Rohdateien plus geparste Ansicht."""

    method: str
    files: list[RawFile]
    view: ParsedView
    #: je Filterwert-Kombination eine Ansicht (nur mit --all-filters)
    filter_views: list[tuple[dict[str, str], ParsedView]] = field(default_factory=list)
    #: Veröffentlichungsstand der Arbeitsmappe (sofern der Weg ihn kennt)
    stamp: dict[str, Any] | None = None
    #: weitere Angaben des Servers, z. B. Rechte (allow_export_data)
    info: dict[str, Any] = field(default_factory=dict)


class MethodFailed(Exception):
    """Ein Extraktionsweg hat keine Daten geliefert; `attempt` nennt den Grund."""

    def __init__(self, attempt: Attempt) -> None:
        super().__init__(attempt.message)
        self.attempt = attempt
