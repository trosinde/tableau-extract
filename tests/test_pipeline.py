import csv
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import responses

from tableau_extract import BlockedError, extract, list_view
from tableau_extract.http import PoliteClient
from tableau_extract.methods import browser
from tableau_extract.models import Attempt
from tests.conftest import FIXTURES
from tests.fixtures.make_fixture import join_segments, split_segments
from tests.test_methods import ROOT, URL, mock_csv_404, start_json

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
SLUG = (
    "bbr-wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_final-dwohnungsneubaubedare_insgesamt"
)


def client() -> PoliteClient:
    return PoliteClient(sleep=lambda s: None)


def changed_bootstrap() -> bytes:
    parts = split_segments((FIXTURES / "bbsr_bootstrap.txt").read_text(encoding="utf-8"))
    segs = parts[1]["secondaryInfo"]["presModelMap"]["dataDictionary"]["presModelHolder"][
        "genDataDictionaryPresModel"
    ]["dataSegments"]
    for seg in segs.values():
        for col in seg["dataColumns"]:
            if col["dataType"] == "cstring":
                col["dataValues"] = ["23,050" if v == "23,000" else v for v in col["dataValues"]]
    return join_segments(parts).encode("utf-8")


def mock_server(boot: bytes | None = None, start: dict | None = None) -> None:  # type: ignore[type-arg]
    mock_csv_404()
    responses.get(re.compile(re.escape(URL) + r"\?.*"), body="<html></html>")
    responses.post(
        re.compile(re.escape(ROOT) + r"/startSession/viewing.*"), json=start or start_json()
    )
    responses.post(
        ROOT + "/bootstrapSession/sessions/TESTSESSION-1:1",
        body=boot or (FIXTURES / "bbsr_bootstrap.txt").read_bytes(),
    )


def boot_calls() -> int:
    return sum("bootstrapSession" in c.request.url for c in responses.calls)


def run(tmp_path: Path, now: datetime = NOW, **kw):  # type: ignore[no-untyped-def]
    return extract(URL, out=tmp_path, client=client(), now=now, cwd=tmp_path, **kw)


@responses.activate
def test_first_run_writes_everything(tmp_path: Path) -> None:
    mock_server()
    r = run(tmp_path, check_sum=320000)
    assert r.status == "neu"
    base = tmp_path / SLUG
    folder = base / "latest"
    assert folder.is_symlink()
    assert r.path is not None and r.path.name.startswith("20261024T120000Z_")
    for name in (
        "data_raw.csv",
        "kreise.csv",
        "kreise.parquet",
        "meta.json",
        "raw/bootstrapSession.txt",
        "raw/startSession.json",
    ):
        assert (folder / name).exists(), name

    rows = list(csv.DictReader((folder / "kreise.csv").open(encoding="utf-8"), delimiter=";"))
    assert len(rows) == 400
    assert len({row["ags5"] for row in rows}) == 400
    berlin = next(row for row in rows if row["ags5"] == "11000")
    assert berlin["kreis_name"] == "Berlin, Stadt"
    assert berlin["p_wohnungsneubaubedarf_2330_we_pa"] == "23000"
    assert berlin["p_wohnungsneubaubedarf_2330_we_pa_je_10000ew"] == "61.3"
    assert berlin["p_wohnungsneubaubedarf_2330_we_pa_je_10000ew_klassen"] == "60 bis unter 75"
    assert berlin["p_wohnungsneubaubedarf_2330_we_pa_je_10000ew_klassen_typ"] == "klasse"
    assert berlin["p_wohnungsneubaubedarf_2330_we_pa_typ"] == "wert"

    raw = (folder / "data_raw.csv").read_text(encoding="utf-8")
    assert "23,000" in raw and "11000000" in raw

    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["weg"] == "vizql"
    assert meta["blatt"] == "Karte"
    assert meta["gebietsschema"] == "en_US"
    assert meta["veroeffentlichungsstand"]["workbookLastPublishedAt"] == "2025-03-05T15:16:42.359Z"
    assert [f["method"] for f in meta["fehlversuche"]] == ["csv"]
    assert {d["datei"] for d in meta["rohdaten"]} == {
        "raw/startSession.json",
        "raw/bootstrapSession.txt",
    }
    assert meta["pruefungen"]["vollstaendigkeit"]["vollstaendig"] is True
    assert meta["pruefungen"]["vollstaendigkeit"]["referenz"] == "paket"
    assert meta["pruefungen"]["gegenprobe"]["abweichung_prozent"] == -1.1
    feld = next(f for f in meta["felder"] if f["spalte"] == "p_wohnungsneubaubedarf_2330_we_pa")
    assert feld["original"] == "SUM(P Wohnungsneubaubedarf 2330 We Pa (Round))"
    assert feld["im_datenmodell_gerundet"] is True

    table = pq.read_table(folder / "kreise.parquet")
    assert b"tableau_extract" in table.schema.metadata
    assert str(table.schema.field("p_wohnungsneubaubedarf_2330_we_pa_je_10000ew").type).startswith(
        "decimal128"
    )
    assert r.df["p_wohnungsneubaubedarf_2330_we_pa"].sum() == Decimal(316490)

    state = json.loads((base / "state.json").read_text(encoding="utf-8"))
    assert state["daten_fingerabdruck"] == meta["daten_fingerabdruck"]


@responses.activate
def test_second_run_unchanged_by_stamp(tmp_path: Path) -> None:
    mock_server()
    first = run(tmp_path)
    r = run(tmp_path, now=NOW + timedelta(days=3))
    assert r.status == "unverändert" and r.reason == "veroeffentlichungsstand"
    assert boot_calls() == 1
    assert len([p for p in (tmp_path / SLUG).iterdir() if p.name.startswith("2026")]) == 1
    assert (tmp_path / SLUG / "latest").resolve() == first.path
    assert len(r.df) == 400
    assert "nichts geladen" in r.messages[0]


@responses.activate
def test_force_loads_fully_same_data(tmp_path: Path) -> None:
    mock_server()
    run(tmp_path)
    r = run(tmp_path, now=NOW + timedelta(hours=1), force=True)
    assert boot_calls() == 2
    assert r.status == "unverändert" and r.reason == "daten"
    state = json.loads((tmp_path / SLUG / "state.json").read_text(encoding="utf-8"))
    assert state["letzte_vollpruefung_utc"] == "2026-10-24T13:00:00+00:00"


@responses.activate
def test_safety_net_after_31_days(tmp_path: Path) -> None:
    mock_server()
    run(tmp_path)
    r = run(tmp_path, now=NOW + timedelta(days=31))
    assert boot_calls() == 2
    assert r.status == "unverändert" and r.reason == "daten"
    folders = [p for p in (tmp_path / SLUG).iterdir() if p.name.startswith("2026")]
    assert len(folders) == 1


@responses.activate
def test_new_publication_loads_fully(tmp_path: Path) -> None:
    mock_server()
    run(tmp_path)
    responses.reset()
    mock_server(start=dict(start_json(), workbookLastPublishedAt="2026-11-01T00:00:00Z"))
    r = run(tmp_path, now=NOW + timedelta(days=1))
    assert boot_calls() == 1
    assert r.status == "unverändert" and r.reason == "daten"


@responses.activate
def test_missing_stamp_loads_fully(tmp_path: Path) -> None:
    start = {k: v for k, v in start_json().items() if k != "workbookLastPublishedAt"}
    mock_server(start=start)
    run(tmp_path)
    run(tmp_path, now=NOW + timedelta(hours=1))
    assert boot_calls() == 2


@responses.activate
def test_changed_value_new_folder(tmp_path: Path) -> None:
    mock_server()
    first = run(tmp_path)
    responses.reset()
    mock_server(
        boot=changed_bootstrap(),
        start=dict(start_json(), workbookLastPublishedAt="2026-11-01T00:00:00Z"),
    )
    r = run(tmp_path, now=NOW + timedelta(days=8))
    assert r.status == "neu"
    assert r.path != first.path
    assert (tmp_path / SLUG / "latest").resolve() == r.path
    berlin = r.df[r.df["ags5"] == "11000"].iloc[0]
    assert berlin["p_wohnungsneubaubedarf_2330_we_pa"] == Decimal(23050)


@responses.activate
def test_new_session_same_data_is_unchanged(tmp_path: Path) -> None:
    mock_server()
    run(tmp_path)
    responses.reset()
    mock_server(
        start=dict(
            start_json(),
            sessionid="TESTSESSION-1:1",
            workbookLastPublishedAt="2026-01-01T00:00:00Z",
        )
    )
    r = run(tmp_path, now=NOW + timedelta(hours=2))
    assert r.status == "unverändert" and r.reason == "daten"


@responses.activate
def test_blocked_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_server()
    first = run(tmp_path)
    responses.reset()
    cf = {"status": 403, "headers": {"Server": "CloudFront"}}
    responses.get(URL + ".csv", **cf)  # type: ignore[arg-type]
    responses.get(re.compile(re.escape(URL) + r"\?.*"), **cf)  # type: ignore[arg-type]

    def blocked(self: browser.BrowserSession) -> None:
        self.loaded = True
        self.failure = Attempt("network", False, URL, 403, "HTTP 403")

    monkeypatch.setattr(browser.BrowserSession, "load", blocked)
    with pytest.raises(BlockedError):
        run(tmp_path, now=NOW + timedelta(days=40))
    assert (tmp_path / SLUG / "latest").resolve() == first.path


@responses.activate
def test_blocked_first_run_no_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cf = {"status": 403}
    responses.get(URL + ".csv", **cf)  # type: ignore[arg-type]
    responses.get(re.compile(re.escape(URL) + r"\?.*"), **cf)  # type: ignore[arg-type]
    monkeypatch.setattr(
        browser.BrowserSession,
        "load",
        lambda self: setattr(self, "failure", Attempt("network", False, URL, 403, "x")),
    )
    with pytest.raises(BlockedError):
        run(tmp_path)
    assert not list(tmp_path.rglob("kreise.csv"))


@responses.activate
def test_notebook_repr(tmp_path: Path) -> None:
    mock_server()
    r = run(tmp_path, check_sum=320000)
    html = r._repr_html_()
    for text in ("Status", "neu", "vizql", "Karte", "400", "Gegenprobe", "-1.1"):
        assert text in html
    assert "Berlin" not in html
    assert "ExtractResult" in repr(r)


@responses.activate
def test_list_view_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    mock_server()
    listing = list_view(URL, client=client())
    assert listing.chosen_sheet == "Karte"
    assert listing.rows["Karte"] == 400
    assert listing.filters == []
    assert "krs23" in repr(listing)
    assert "<table>" in listing._repr_html_()
    assert list(tmp_path.iterdir()) == []


def test_replay_from_run_folder(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "bootstrapSession.txt").write_bytes((FIXTURES / "bbsr_bootstrap.txt").read_bytes())
    (raw / "startSession.json").write_text(json.dumps(start_json()), encoding="utf-8")
    r = extract(URL, out=tmp_path / "out", replay=raw, now=NOW, cwd=tmp_path)
    assert r.status == "neu" and r.method == "replay"
    assert not (tmp_path / "out" / SLUG / "state.json").exists()
    r2 = extract(URL, out=tmp_path / "out", replay=raw, now=NOW + timedelta(hours=1), cwd=tmp_path)
    assert r2.status == "unverändert"
