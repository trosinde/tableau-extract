"""Fehlerklassen mit zugehörigen Exit-Codes."""

from __future__ import annotations

from typing import Any


class ExtractError(Exception):
    """Basisklasse; `exit_code` bestimmt den Exit-Code der CLI."""

    exit_code = 1

    def __init__(self, message: str, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = report or {}


class InputError(ExtractError):
    """Ungültige Eingabe (keine Tableau-URL, unbekanntes Blatt, ...)."""

    exit_code = 1


class FormatError(ExtractError):
    """Antwort hat nicht das erwartete Format; es werden keine Teildaten geliefert."""

    exit_code = 1


class BlockedError(ExtractError):
    """Kein Extraktionsweg lieferte Daten."""

    exit_code = 2


class AmbiguousRegionError(ExtractError):
    """Mindestens eine Zeile lässt sich keinem Kreis eindeutig zuordnen."""

    exit_code = 3
