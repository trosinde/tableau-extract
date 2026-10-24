import json
import re
import sys
from pathlib import Path

import pytest
import responses

from tableau_extract.acquire import acquire
from tableau_extract.errors import BlockedError, InputError
from tableau_extract.http import PoliteClient
from tableau_extract.methods import browser, csv, replay, vizql
from tableau_extract.models import Attempt, MethodFailed
from tableau_extract.url import parse_view_url
from tests.conftest import FIXTURES

URL = (
    "https://tableau.bbsr.bund.de/t/bbr/views/"
    "Wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_FINAL/DWohnungsneubaubedare_insgesamt"
)
VIEW = parse_view_url(URL)
ROOT = "https://tableau.bbsr.bund.de/vizql/t/bbr/w/Wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_FINAL/v/DWohnungsneubaubedare_insgesamt"


def client() -> PoliteClient:
    return PoliteClient(sleep=lambda s: None)


def start_json() -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / "bbsr_startsession.json").read_text(encoding="utf-8"))


def mock_vizql(boot: str = "bbsr_bootstrap.txt", start: dict | None = None) -> None:  # type: ignore[type-arg]
    responses.get(
        re.compile(re.escape(URL) + r"\?.*"),
        body=(FIXTURES / "bbsr_view.html").read_text(encoding="utf-8"),
    )
    responses.post(
        re.compile(re.escape(ROOT) + r"/startSession/viewing.*"), json=start or start_json()
    )
    responses.post(
        ROOT + "/bootstrapSession/sessions/TESTSESSION-1:1", body=(FIXTURES / boot).read_bytes()
    )


def mock_csv_404() -> None:
    responses.get(URL + ".csv", status=404, json={"type": "missing-view"})


# --- Weg A -------------------------------------------------------------------------


@responses.activate
def test_csv_success() -> None:
    responses.get(URL + ".csv", body="krs;Wert\n08111;1.5\n", content_type="text/csv")
    cap = csv.fetch(VIEW, client())
    table = cap.view.sheets[VIEW.sheet]
    assert table.column("krs").values == ["08111"]
    assert cap.files[0].name == "view.csv"


@responses.activate
def test_csv_missing_view() -> None:
    mock_csv_404()
    with pytest.raises(MethodFailed) as ei:
        csv.fetch(VIEW, client())
    assert ei.value.attempt.status == 404
    assert "missing-view" in ei.value.attempt.message


# --- Weg B -------------------------------------------------------------------------


@responses.activate
def test_vizql_flow() -> None:
    mock_vizql()
    session = vizql.VizqlSession(VIEW, client())
    cap = vizql.fetch(session)
    assert cap.view.sheets["Karte"].n_rows == 400
    assert cap.stamp == {
        "workbookLastPublishedAt": "2025-03-05T15:16:42.359Z",
        "workbookContentVersion": 1,
        "view_luid": "2df355e6-93da-4e8e-958c-d10b82a500fb",
    }
    assert cap.info["allow_export_data"] is False
    assert [f.name for f in cap.files] == ["startSession.json", "bootstrapSession.txt"]
    boot_call = responses.calls[2].request
    assert "sheet_id=D%253A%2520Wohnungsneubaubedare_insgesamt" in str(boot_call.body)


@responses.activate
def test_vizql_start_without_session_fails() -> None:
    responses.get(re.compile(re.escape(URL) + r"\?.*"), body="x")
    responses.post(re.compile(re.escape(ROOT) + r"/startSession/viewing.*"), json={"x": 1})
    with pytest.raises(MethodFailed, match="startSession"):
        vizql.fetch(vizql.VizqlSession(VIEW, client()))


# --- Wege C/D ------------------------------------------------------------------------


def test_browser_without_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    session = browser.BrowserSession(VIEW, "ua")
    with pytest.raises(MethodFailed, match="Playwright nicht installiert"):
        browser.fetch_network(session)
    with pytest.raises(MethodFailed, match="Playwright nicht installiert"):
        browser.fetch_download(session)


def _loaded_session(menu: dict[str, str]) -> browser.BrowserSession:
    s = browser.BrowserSession(VIEW, "ua")
    s.loaded = True
    s.bootstrap = (FIXTURES / "bbsr_bootstrap.txt").read_bytes()
    s.start = start_json()
    s.start_raw = json.dumps(s.start).encode()
    s.menu = menu
    return s


def test_network_parses_captured_bootstrap() -> None:
    cap = browser.fetch_network(_loaded_session({}))
    assert cap.method == "network"
    assert cap.view.sheets["Karte"].n_rows == 400
    assert cap.stamp is not None


def test_download_menu_logged() -> None:
    s = _loaded_session({"Daten": "nicht angeboten", "Kreuztabelle": "nicht angeboten"})
    with pytest.raises(MethodFailed, match="Daten: nicht angeboten"):
        browser.fetch_download(s)


# --- Orchestrierung ------------------------------------------------------------------


@responses.activate
def test_first_blocked_second_ok() -> None:
    mock_csv_404()
    mock_vizql()
    acq = acquire(VIEW, client=client())
    assert acq.capture is not None and acq.capture.method == "vizql"
    assert [(a.method, a.ok, a.status) for a in acq.attempts] == [
        ("csv", False, 404),
        ("vizql", True, 200),
    ]


@responses.activate
def test_forced_method_only() -> None:
    mock_vizql()
    acq = acquire(VIEW, client=client(), method="vizql")
    assert [a.method for a in acq.attempts] == ["vizql"]


def test_unknown_method() -> None:
    with pytest.raises(InputError):
        acquire(VIEW, method="ftp")


@responses.activate
def test_all_blocked_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    cf = {"status": 403, "body": "<TITLE>ERROR</TITLE>", "headers": {"Server": "CloudFront"}}
    responses.get(URL + ".csv", **cf)  # type: ignore[arg-type]
    responses.get(re.compile(re.escape(URL) + r"\?.*"), **cf)  # type: ignore[arg-type]

    def blocked(self: browser.BrowserSession) -> None:
        self.loaded = True
        self.failure = Attempt("network", False, URL, 403, "HTTP 403 beim Laden der Ansicht")

    monkeypatch.setattr(browser.BrowserSession, "load", blocked)
    with pytest.raises(BlockedError) as ei:
        acquire(VIEW, client=client())
    assert ei.value.exit_code == 2
    statuses = [(f["method"], f["status"]) for f in ei.value.report["fehlversuche"]]
    assert statuses == [("csv", 403), ("vizql", 403), ("download", 403), ("network", 403)]


@responses.activate
def test_precheck_skips_bootstrap() -> None:
    mock_vizql()
    acq = acquire(VIEW, client=client(), skip_if_stamp=lambda s: True)
    assert acq.unchanged_by_stamp is True
    assert acq.capture is None
    assert not any("bootstrapSession" in c.request.url for c in responses.calls)
    assert not any(c.request.url.endswith(".csv") for c in responses.calls)


@responses.activate
def test_precheck_changed_loads_fully() -> None:
    mock_csv_404()
    mock_vizql()
    acq = acquire(VIEW, client=client(), skip_if_stamp=lambda s: False)
    assert acq.capture is not None
    starts = [c for c in responses.calls if "startSession" in c.request.url]
    assert len(starts) == 1  # Sitzung der Vorabprüfung wird weiterverwendet


# --- --all-filters ---------------------------------------------------------------------


@responses.activate
def test_all_filters_synthetic() -> None:
    start = dict(start_json(), locale="de_DE")
    mock_vizql("synthetic_bootstrap_de.txt", start)
    cmd = json.loads((FIXTURES / "synthetic_filter_response.json").read_text(encoding="utf-8"))
    responses.post(re.compile(re.escape(ROOT) + r"/sessions/TESTSESSION-1:1/commands/.*"), json=cmd)
    cap = vizql.fetch(vizql.VizqlSession(VIEW, client()), all_filters=True)
    assert len(cap.filter_views) == 4  # Zeitraum (2) × Komponente (2)
    assert cap.filter_views[0][0] == {"Zeitraum": "2023-2030", "Komponente": "insgesamt"}
    sent = [c.request for c in responses.calls if "/commands/" in c.request.url]
    assert len(sent) == 8
    assert any("categorical-filter-by-index" in r.url for r in sent)
    assert any("set-parameter-value" in r.url for r in sent)
    assert any(f.name == "filter_index.json" for f in cap.files)


# --- Offline-Wiederholung --------------------------------------------------------------


@responses.activate
def test_replay_same_table_without_network(tmp_path: Path) -> None:
    mock_vizql()
    cap = vizql.fetch(vizql.VizqlSession(VIEW, client()))
    for f in cap.files:
        (tmp_path / f.name).write_bytes(f.content)
    n_calls = len(responses.calls)
    acq = acquire(VIEW, replay=str(tmp_path))
    assert len(responses.calls) == n_calls
    assert acq.capture is not None and acq.capture.method == "replay"
    a, b = cap.view.sheets["Karte"], acq.capture.view.sheets["Karte"]
    assert [c.values for c in a.columns] == [c.values for c in b.columns]
    assert acq.capture.stamp == cap.stamp


def test_replay_all_filters(tmp_path: Path) -> None:
    (tmp_path / "bootstrapSession.txt").write_bytes(
        (FIXTURES / "synthetic_bootstrap_de.txt").read_bytes()
    )
    cmd = (FIXTURES / "synthetic_filter_response.json").read_bytes()
    (tmp_path / "command_000_000.json").write_bytes(cmd)
    (tmp_path / "command_001_001.json").write_bytes(cmd)
    (tmp_path / "filter_index.json").write_text(
        json.dumps(
            [
                {"filter": {"Zeitraum": "2023-2030"}, "datei": "command_000_000.json"},
                {"filter": {"Zeitraum": "2031-2040"}, "datei": "command_001_001.json"},
            ]
        )
    )
    cap = replay.fetch(tmp_path, "Karte")
    assert [sel for sel, _ in cap.filter_views] == [
        {"Zeitraum": "2023-2030"},
        {"Zeitraum": "2031-2040"},
    ]


def test_replay_empty_folder(tmp_path: Path) -> None:
    with pytest.raises(InputError, match=r"bootstrapSession\.txt"):
        replay.fetch(tmp_path, "Karte")


def test_replay_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(InputError):
        replay.fetch(tmp_path / "nichts", "Karte")
