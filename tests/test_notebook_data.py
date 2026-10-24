from pathlib import Path

from tests.conftest import FIXTURES

NB = Path(__file__).resolve().parents[1] / "notebooks"


def test_example_raw_equals_fixtures() -> None:
    raw = NB / "beispiel_raw"
    assert (raw / "bootstrapSession.txt").read_bytes() == (
        FIXTURES / "bbsr_bootstrap.txt"
    ).read_bytes()
    assert (raw / "startSession.json").read_bytes() == (
        FIXTURES / "bbsr_startsession.json"
    ).read_bytes()


def test_example_raw_has_no_tokens() -> None:
    text = (NB / "beispiel_raw" / "bootstrapSession.txt").read_text(encoding="utf-8")
    assert "pk.eyJ" not in text and "sk.eyJ" not in text


def test_install_cell_is_skipped_in_ci() -> None:
    import nbformat

    nb = nbformat.read(NB / "schnellstart.ipynb", as_version=4)
    install = [c for c in nb.cells if "%pip install" in c.source]
    assert len(install) == 1
    assert "skip-ci" in install[0].metadata.get("tags", [])
