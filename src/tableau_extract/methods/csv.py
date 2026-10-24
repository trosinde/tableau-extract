"""Weg A: View-Data-Export (GET <view>.csv)."""

from __future__ import annotations

import csv
import io

from ..http import HttpError, PoliteClient
from ..models import Attempt, Column, MethodFailed, ParsedView, RawCapture, RawFile, SheetTable
from ..url import ViewUrl

NAME = "csv"


def parse_view_csv(content: bytes, sheet: str) -> ParsedView:
    """Liest den View-Data-Export. Alle Werte bleiben Text, genau wie geliefert."""
    text = content.decode("utf-8-sig")
    first = text.splitlines()[0] if text else ""
    try:
        delimiter = csv.Sniffer().sniff(first, delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows or not rows[0]:
        raise ValueError("leere CSV")
    header, body = rows[0], rows[1:]
    columns = []
    for i, name in enumerate(header):
        values: list[str | int | float | None] = [r[i] if i < len(r) else None for r in body]
        columns.append(Column(name, "cstring", values, "alias"))
    return ParsedView(sheets={sheet: SheetTable(sheet, columns)}, locale=None)


def fetch(view: ViewUrl, client: PoliteClient) -> RawCapture:
    try:
        resp = client.get(view.csv_url, label=NAME)
    except HttpError as exc:
        raise MethodFailed(exc.attempt) from exc
    ctype = resp.headers.get("Content-Type", "")
    if "csv" not in ctype and "text/plain" not in ctype:
        raise MethodFailed(
            Attempt(NAME, False, view.csv_url, resp.status_code, f"keine CSV ({ctype or '?'})")
        )
    try:
        parsed = parse_view_csv(resp.content, view.sheet)
    except (ValueError, UnicodeDecodeError) as exc:
        raise MethodFailed(
            Attempt(NAME, False, view.csv_url, resp.status_code, f"CSV nicht lesbar: {exc}")
        ) from exc
    return RawCapture(NAME, [RawFile("view.csv", resp.content)], parsed)
