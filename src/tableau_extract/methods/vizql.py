"""Weg B: VizQL-Session per HTTP (startSession + bootstrapSession).

Ablauf wie im Browser, ohne JavaScript:
1. `GET <view>?:embed=y` (Cookies des Load-Balancers)
2. `POST /vizql/.../startSession/viewing`: JSON mit `sessionid`, `sheetId`, `vizql_root`,
   Rechten und Veröffentlichungsstand
3. `POST <vizql_root>/bootstrapSession/sessions/<id>`: Datenwörterbuch und Blätter

Optional (`--all-filters`): Befehle `categorical-filter-by-index` bzw.
`set-parameter-value` je Filterwert; jede Antwort ergänzt das Datenwörterbuch.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable
from typing import Any

from ..errors import FormatError, InputError
from ..http import HttpError, PoliteClient
from ..models import Attempt, Filter, MethodFailed, ParsedView, RawCapture, RawFile
from ..url import ViewUrl
from ..vizql_parse import VizState

NAME = "vizql"
MAX_COMBINATIONS = 200
CLIENT_DIMENSION = json.dumps({"w": 1920, "h": 1080})

#: Felder aus startSession, die in die Metadaten übernommen werden
INFO_KEYS = (
    "workbookName",
    "repositoryUrl",
    "current_view_luid",
    "current_workbook_luid",
    "current_sheet_type",
    "visible_sheets",
    "locale",
    "language",
    "allow_export_data",
    "allow_export_image",
    "allow_view_underlying",
    "allow_summary",
    "workbookLastPublishedAt",
    "workbookContentVersion",
)

PostCommand = Callable[[str, list[tuple[str, tuple[None, str]]]], dict[str, Any]]


def stamp_from_start(start: dict[str, Any]) -> dict[str, Any] | None:
    """Veröffentlichungsstand aus der startSession-Antwort (None, wenn nicht enthalten)."""
    published = start.get("workbookLastPublishedAt")
    if not published:
        return None
    return {
        "workbookLastPublishedAt": published,
        "workbookContentVersion": start.get("workbookContentVersion"),
        "view_luid": start.get("current_view_luid"),
    }


class VizqlSession:
    """Eine VizQL-Sitzung per HTTP. `open()` liefert den Veröffentlichungsstand."""

    def __init__(self, view: ViewUrl, client: PoliteClient) -> None:
        self.view = view
        self.client = client
        self.start: dict[str, Any] | None = None
        self.start_raw: bytes = b""
        self.failure: Attempt | None = None

    def open(self) -> dict[str, Any]:
        if self.start is not None:
            return self.start
        if self.failure is not None:
            raise MethodFailed(self.failure)
        try:
            self.client.get(self.view.embed_url, label=NAME)
            url = f"{self.view.vizql_prefix}/startSession/viewing"
            resp = self.client.post(
                url, label=NAME, params={":embed": "y"}, headers={"Accept": "application/json"}
            )
        except HttpError as exc:
            self.failure = exc.attempt
            raise MethodFailed(exc.attempt) from exc
        try:
            start: dict[str, Any] = dict(resp.json())
            start["sessionid"], start["vizql_root"]
        except (ValueError, KeyError, TypeError) as exc:
            self.failure = Attempt(
                NAME,
                False,
                url,
                resp.status_code,
                "startSession: unerwartete Antwort (kein JSON mit sessionid)",
            )
            raise MethodFailed(self.failure) from exc
        self.start, self.start_raw = start, resp.content
        return start

    @property
    def stamp(self) -> dict[str, Any] | None:
        return stamp_from_start(self.start) if self.start else None

    def _root(self) -> str:
        assert self.start is not None
        return f"{self.view.base}{self.start['vizql_root']}"

    def bootstrap(self) -> bytes:
        start = self.open()
        url = f"{self._root()}/bootstrapSession/sessions/{start['sessionid']}"
        data = {
            "sheet_id": start.get("sheetId", ""),
            "clientDimension": CLIENT_DIMENSION,
            "renderMapsClientSide": "true",
            "isBrowserRendering": "true",
            "browserRenderingThreshold": "100",
            "formatDataValueLocally": "false",
            "language": start.get("language") or "en",
            "locale": start.get("locale") or "en_US",
        }
        try:
            return self.client.post(url, label=NAME, data=data).content
        except HttpError as exc:
            raise MethodFailed(exc.attempt) from exc

    def post_command(
        self, command: str, files: list[tuple[str, tuple[None, str]]]
    ) -> dict[str, Any]:
        start = self.open()
        url = f"{self._root()}/sessions/{start['sessionid']}/commands/tabdoc/{command}"
        try:
            resp = self.client.post(url, label=NAME, files=files)
            result: dict[str, Any] = resp.json()
            return result
        except HttpError as exc:
            raise MethodFailed(exc.attempt) from exc
        except ValueError as exc:
            raise FormatError(f"Befehl {command}: Antwort ist kein JSON") from exc


def capture_from_bootstrap(
    method: str,
    boot: bytes,
    *,
    start: dict[str, Any] | None,
    start_raw: bytes = b"",
    all_filters: bool = False,
    post_command: PostCommand | None = None,
) -> RawCapture:
    """Gemeinsamer Teil von Weg B und D: parsen und ggf. alle Filterwerte abziehen."""
    text = boot.decode("utf-8")
    state = VizState.from_bootstrap(text)
    if state.locale is None and start:
        state.locale = start.get("locale")
    files = [RawFile("bootstrapSession.txt", boot)]
    if start_raw:
        files.insert(0, RawFile("startSession.json", start_raw))
    view = state.to_view()
    capture = RawCapture(
        method,
        files,
        view,
        stamp=stamp_from_start(start) if start else None,
        info={k: start[k] for k in INFO_KEYS if start and k in start},
    )
    if all_filters and view.filters:
        if post_command is None:
            raise MethodFailed(
                Attempt(
                    method, False, None, None, "--all-filters wird auf diesem Weg nicht unterstützt"
                )
            )
        capture.filter_views, cmd_files = run_all_filters(state, view.filters, post_command)
        capture.files.extend(cmd_files)
    return capture


def _filter_sheet(f: Filter, state: VizState) -> str:
    return f.worksheet or next(iter(state.sheets), "")


def run_all_filters(
    state: VizState, filters: list[Filter], post_command: PostCommand
) -> tuple[list[tuple[dict[str, str], ParsedView]], list[RawFile]]:
    """Zieht je Kombination der Filter-/Parameterwerte einen Abzug."""
    combos = list(itertools.product(*[f.values for f in filters]))
    if len(combos) > MAX_COMBINATIONS:
        raise InputError(
            f"--all-filters ergäbe {len(combos)} Abzüge (höchstens {MAX_COMBINATIONS}); "
            "bitte Ansicht mit weniger Filtern verwenden"
        )
    results: list[tuple[dict[str, str], ParsedView]] = []
    files: list[RawFile] = []
    index: list[dict[str, Any]] = []
    for n, combo in enumerate(combos):
        for f, value in zip(filters, combo, strict=True):
            if f.kind == "parameter":
                resp = post_command(
                    "set-parameter-value",
                    [
                        ("globalFieldName", (None, f.field)),
                        ("valueString", (None, value)),
                        ("useUsLocale", (None, "false")),
                    ],
                )
            else:
                resp = post_command(
                    "categorical-filter-by-index",
                    [
                        (
                            "visualIdPresModel",
                            (
                                None,
                                json.dumps({"worksheet": _filter_sheet(f, state), "dashboard": ""}),
                            ),
                        ),
                        ("globalFieldName", (None, f.field)),
                        ("membershipTarget", (None, "filter")),
                        ("filterIndices", (None, json.dumps([f.values.index(value)]))),
                        ("filterUpdateType", (None, "filter-replace")),
                    ],
                )
            state.apply_command_response(resp)
            name = f"command_{n:03d}_{len(files):03d}.json"
            files.append(RawFile(name, json.dumps(resp, ensure_ascii=False).encode("utf-8")))
        selection = {f.name: v for f, v in zip(filters, combo, strict=True)}
        index.append({"filter": selection, "datei": files[-1].name})
        results.append((selection, state.to_view()))
    files.append(
        RawFile(
            "filter_index.json", json.dumps(index, ensure_ascii=False, indent=1).encode("utf-8")
        )
    )
    return results, files


def fetch(session: VizqlSession, *, all_filters: bool = False) -> RawCapture:
    boot = session.bootstrap()
    try:
        return capture_from_bootstrap(
            NAME,
            boot,
            start=session.start,
            start_raw=session.start_raw,
            all_filters=all_filters,
            post_command=session.post_command,
        )
    except FormatError as exc:
        raise MethodFailed(Attempt(NAME, False, None, None, str(exc))) from exc
