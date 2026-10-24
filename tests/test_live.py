"""Live-Test gegen die BBSR-Karte. Nur lokal: uv run pytest -m live"""

import csv
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tableau_extract import extract

pytestmark = pytest.mark.live
ROOT = Path(__file__).resolve().parents[1]
URL = (
    "https://tableau.bbsr.bund.de/t/bbr/views/"
    "Wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_FINAL/DWohnungsneubaubedare_insgesamt"
)


def test_bbsr_live(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    r = extract(URL, out=tmp_path, check_sum=320_000, now=now, cwd=tmp_path)
    assert r.status == "neu"
    assert r.method == "vizql"
    rows = list(csv.DictReader((r.path / "kreise.csv").open(encoding="utf-8"), delimiter=";"))
    assert len(rows) == 400
    assert all(len(x["ags5"]) == 5 and x["ags5"].isdigit() for x in rows)
    assert len({x["ags5"] for x in rows}) == 400
    assert abs(r.meta["pruefungen"]["gegenprobe"]["abweichung_prozent"]) < 5
    assert r.meta["pruefungen"]["vollstaendigkeit"]["vollstaendig"] is True

    r2 = extract(URL, out=tmp_path, now=now + timedelta(minutes=1), cwd=tmp_path)
    assert r2.status == "unverändert"


def test_notebook_live(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "TABLEAU_EXTRACT_REPLAY"}
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_notebook.py"),
            str(ROOT / "notebooks" / "schnellstart.ipynb"),
            str(tmp_path),
        ],
        check=True,
        env=env,
    )
