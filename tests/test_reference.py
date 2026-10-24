import csv
from importlib.resources import files

import pytest


@pytest.mark.parametrize("year", [2023, 2024])
def test_reference_list_has_400_unique_keys(year: int) -> None:
    text = files("tableau_extract.data").joinpath(f"kreise_{year}.csv").read_text("utf-8")
    rows = list(csv.DictReader(text.splitlines(), delimiter=";"))
    keys = [r["ags5"] for r in rows]
    assert len(keys) == 400
    assert len(set(keys)) == 400
    assert all(len(k) == 5 and k.isdigit() for k in keys)
    assert {r["typ"] for r in rows} <= {
        "Kreisfreie Stadt",
        "Stadtkreis",
        "Kreis",
        "Landkreis",
        "Regionalverband",
    }
