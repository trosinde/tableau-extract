import tableau_extract
from tableau_extract.cli import main


def test_version() -> None:
    assert tableau_extract.__version__


def test_cli_help_exits_cleanly() -> None:
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
