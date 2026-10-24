"""Das gebaute Wheel enthält alle Ressourcen und läuft außerhalb des Repos."""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tests.conftest import FIXTURES

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv nicht installiert")

SCRIPT = """
import json, sys
from tableau_extract import extract
r = extract(
    "https://tableau.bbsr.bund.de/t/bbr/views/WB/DWohnungsneubaubedare_insgesamt",
    out="out", replay=sys.argv[1],
)
v = r.meta["pruefungen"]["vollstaendigkeit"]
print(json.dumps({"status": r.status, "referenz": v["referenz"], "gefunden": v["gefunden"],
                  "zeilen": len(r.df)}))
"""


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dist = tmp_path_factory.mktemp("dist")
    subprocess.run(["uv", "build", "--wheel", "-q", "-o", str(dist)], cwd=ROOT, check=True)
    return next(dist.glob("tableau_extract-*.whl"))


def test_wheel_contains_reference_lists(wheel: Path) -> None:
    names = zipfile.ZipFile(wheel).namelist()
    assert "tableau_extract/data/kreise_2023.csv" in names
    assert "tableau_extract/data/kreise_2024.csv" in names
    assert "tableau_extract/py.typed" in names


def test_installed_wheel_runs_outside_repo(wheel: Path, tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    subprocess.run(["uv", "venv", "-q", "-p", sys.executable, str(venv)], check=True)
    py = venv / "bin" / "python"
    subprocess.run(["uv", "pip", "install", "-q", "-p", str(py), str(wheel)], check=True)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "bootstrapSession.txt").write_bytes((FIXTURES / "bbsr_bootstrap.txt").read_bytes())
    work = tmp_path / "leer"
    work.mkdir()
    out = subprocess.run(
        [str(py), "-c", SCRIPT, str(raw)], cwd=work, check=True, capture_output=True, text=True
    ).stdout
    assert '"referenz": "paket"' in out
    assert '"gefunden": 400' in out
    assert '"status": "neu"' in out
