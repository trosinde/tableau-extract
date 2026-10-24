import json

import pytest

from tableau_extract.errors import FormatError
from tableau_extract.vizql_parse import VizState, parse_bootstrap, split_segments
from tests.conftest import FIXTURES


def test_fixtures_are_small() -> None:
    for name in ("bbsr_bootstrap.txt", "synthetic_bootstrap_de.txt"):
        assert (FIXTURES / name).stat().st_size < 1_000_000


def test_bbsr_sheets_and_locale(bbsr_text: str) -> None:
    view = parse_bootstrap(bbsr_text)
    assert set(view.sheets) == {"Karte", "Impressum"}
    assert view.locale == "en_US"
    assert view.filters == []
    assert view.sheets["Karte"].n_rows == 400


def test_bbsr_berlin_row(bbsr_text: str) -> None:
    karte = parse_bootstrap(bbsr_text).sheets["Karte"]
    keys = karte.column("krs23").values
    i = keys.index(11000000)
    assert karte.column("krsname23").values[i] == "Berlin, Stadt"
    absolute = karte.column("SUM(P Wohnungsneubaubedarf 2330 We Pa (Round))")
    assert absolute.values[i] == "23,000"
    assert absolute.source == "alias"
    per10k = karte.column("SUM(P Wohnungsneubaubedarf 2330 We Pa Je 10000Ew (Round))")
    assert per10k.values[i] == 61.3
    assert per10k.source == "value"
    assert len(set(keys)) == 400


def test_synthetic_filters_and_parameter(synthetic_text: str) -> None:
    view = parse_bootstrap(synthetic_text)
    assert view.locale == "de_DE"
    zeitraum, komponente = view.filters
    assert zeitraum.name == "Zeitraum"
    assert zeitraum.values == ["2023-2030", "2031-2040"]
    assert zeitraum.selected == ["2023-2030"]
    assert zeitraum.field == "[ds].[none:Zeitraum:nk]"
    assert komponente.kind == "parameter"
    assert komponente.selected == ["insgesamt"]


def test_synthetic_values(synthetic_text: str) -> None:
    karte = parse_bootstrap(synthetic_text).sheets["Karte"]
    assert karte.column("Kreisschlüssel").values == [8111, 9162, 7131, 1001]
    assert karte.column("SUM(Bedarf (Round))").values == ["1.234,5", "*", "%null%", "12.000"]


def test_command_response_extends_dictionary(synthetic_text: str) -> None:
    state = VizState.from_bootstrap(synthetic_text)
    state.apply_command_response(
        json.loads((FIXTURES / "synthetic_filter_response.json").read_text(encoding="utf-8"))
    )
    karte = state.sheet_table("Karte")
    assert karte.column("SUM(Bedarf (Round))").values == ["2.000", "1.500,25", "*", "900"]
    assert karte.column("Kreis").values[0] == "Stuttgart, Stadtkreis"
    assert state.filters()[0].selected == ["2031-2040"]


def test_unequal_column_is_dropped_with_warning(synthetic_text: str) -> None:
    parts = split_segments(synthetic_text)
    pcd = parts[1]["secondaryInfo"]["presModelMap"]["vizData"]["presModelHolder"][
        "genPresModelMapPresModel"
    ]["presModelMap"]["Karte"]["presModelHolder"]["genVizDataPresModel"]["paneColumnsData"]
    pcd["paneColumnsList"][0]["vizPaneColumns"][3]["valueIndices"] = [0]
    body = json.dumps(parts[1])
    text = synthetic_text.split(";", 1)[0]
    first = synthetic_text[: len(text) + 1 + int(text)]
    view = parse_bootstrap(first + f"{len(body)};{body}")
    assert "SUM(Quote)" not in [c.name for c in view.sheets["Karte"].columns]
    assert any("SUM(Quote)" in w for w in view.warnings)


@pytest.mark.parametrize(
    "text",
    ["", "abc", "10;{}", "2;{}", '9;{"a": 1}xx', "2;{}2;{}"],
)
def test_broken_input_raises_instead_of_partial_data(text: str) -> None:
    with pytest.raises(FormatError):
        parse_bootstrap(text)


def test_bbsr_truncated_raises(bbsr_text: str) -> None:
    with pytest.raises(FormatError):
        parse_bootstrap(bbsr_text[: len(bbsr_text) // 2])
