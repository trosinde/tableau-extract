import json
from pathlib import Path

import pytest

from tableau_extract.cli import main
from tableau_extract.errors import AmbiguousRegionError, BlockedError
from tests.conftest import FIXTURES
from tests.test_methods import URL, start_json

SLUG = (
    "bbr-wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_final-dwohnungsneubaubedare_insgesamt"
)


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "bootstrapSession.txt").write_bytes((FIXTURES / "bbsr_bootstrap.txt").read_bytes())
    (raw / "startSession.json").write_text(json.dumps(start_json()), encoding="utf-8")
    return raw


def test_list_writes_nothing(
    raw_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main([URL, "--list", "--replay", str(raw_dir)]) == 0
    out = capsys.readouterr().out
    assert "Blatt: Karte" in out and "(gewählt)" in out and "krs23" in out
    assert not (tmp_path / "out").exists()


def test_extract_and_unchanged(
    raw_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    assert main([URL, "--replay", str(raw_dir), "--out", str(out), "--check-sum", "320000"]) == 0
    text = capsys.readouterr().out
    assert "neu:" in text and "400 Zeilen" in text and "400/400" in text
    assert "Abweichung -1.1 %" in text
    assert (out / SLUG / "latest" / "kreise.csv").is_file()
    assert main([URL, "--replay", str(raw_dir), "--out", str(out)]) == 0
    assert "unverändert" in capsys.readouterr().out


def test_env_out(raw_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TABLEAU_EXTRACT_OUT", str(tmp_path / "envout"))
    monkeypatch.setenv("TABLEAU_EXTRACT_REPLAY", str(raw_dir))
    assert main([URL, "--quiet"]) == 0
    assert (tmp_path / "envout" / SLUG / "latest" / "meta.json").is_file()


def test_invalid_url_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["https://www.bbsr.bund.de/seite.html"]) == 1
    assert "iframe" in capsys.readouterr().err


def test_unknown_sheet_exit_1(raw_dir: Path, tmp_path: Path) -> None:
    assert main([URL, "--replay", str(raw_dir), "--out", str(tmp_path), "--sheet", "X"]) == 1


def test_blocked_exit_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def blocked(*a: object, **k: object) -> None:
        raise BlockedError(
            "Kein Weg lieferte Daten.",
            {"fehlversuche": [{"method": "csv", "status": 403, "message": "HTTP 403, CloudFront"}]},
        )

    monkeypatch.setattr("tableau_extract.cli.extract", blocked)
    assert main([URL]) == 2
    err = capsys.readouterr().err
    assert "Weg csv: HTTP 403" in err


def test_ambiguous_exit_3(monkeypatch: pytest.MonkeyPatch) -> None:
    def ambiguous(*a: object, **k: object) -> None:
        raise AmbiguousRegionError("Landshut: mehrdeutiger Name")

    monkeypatch.setattr("tableau_extract.cli.extract", ambiguous)
    assert main([URL]) == 3


def test_check_field_not_measure(raw_dir: Path, tmp_path: Path) -> None:
    assert (
        main(
            [
                URL,
                "--replay",
                str(raw_dir),
                "--out",
                str(tmp_path),
                "--check-sum",
                "1",
                "--check-field",
                "slk2023",
            ]
        )
        == 1
    )
