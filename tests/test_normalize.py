import pytest

from tableau_extract.errors import InputError
from tableau_extract.models import Column, ParsedView, SheetTable
from tableau_extract.normalize import (
    ROLE_CLASS,
    ROLE_DIMENSION,
    ROLE_GEOMETRY,
    ROLE_KEY,
    ROLE_MEASURE,
    ROLE_NAME,
    choose_sheet,
    column_name,
    describe_fields,
)
from tableau_extract.vizql_parse import parse_bootstrap


def test_bbsr_roles_and_names(bbsr_text: str) -> None:
    view = parse_bootstrap(bbsr_text)
    fields = {f.original: f for f in describe_fields(view.sheets["Karte"])}
    assert fields["krs23"].role == ROLE_KEY
    assert fields["krsname23"].role == ROLE_NAME
    assert fields["slk2023"].role == ROLE_DIMENSION
    assert fields["COLLECT(Geometrie)"].role == ROLE_GEOMETRY
    assert fields["Latitude (generated)"].role == ROLE_GEOMETRY
    klassen = fields["P Wohnungsneubaubedarf 2330 We Pa Je 10000Ew (Round) (Klassen)"]
    assert klassen.role == ROLE_CLASS
    assert klassen.value_kind == "klasse"
    absolute = fields["SUM(P Wohnungsneubaubedarf 2330 We Pa (Round))"]
    assert absolute.role == ROLE_MEASURE
    assert absolute.column == "p_wohnungsneubaubedarf_2330_we_pa"
    assert absolute.rounded is True
    assert absolute.as_dict()["quelle_wert"] == "formatierter_alias"


def test_automatic_sheet_choice(bbsr_text: str) -> None:
    assert choose_sheet(parse_bootstrap(bbsr_text)).name == "Karte"


def test_forced_sheet(synthetic_text: str) -> None:
    assert choose_sheet(parse_bootstrap(synthetic_text), "Legende").name == "Legende"


def test_unknown_sheet_lists_existing(bbsr_text: str) -> None:
    with pytest.raises(InputError, match="Impressum, Karte"):
        choose_sheet(parse_bootstrap(bbsr_text), "Tabelle")


def test_no_region_sheet() -> None:
    view = ParsedView({"A": SheetTable("A", [Column("SUM(x)", "real", [1.0])])})
    with pytest.raises(InputError, match="--sheet"):
        choose_sheet(view)


@pytest.mark.parametrize(
    ("caption", "expected"),
    [
        ("SUM(P Wohnungsneubaubedarf 2330 We Pa (Round))", "p_wohnungsneubaubedarf_2330_we_pa"),
        (
            "P Wohnungsneubaubedarf 2330 We Pa Je 10000Ew (Round) (Klassen)",
            "p_wohnungsneubaubedarf_2330_we_pa_je_10000ew_klassen",
        ),
        ("Bevölkerung Größe", "bevoelkerung_groesse"),
        ("AVG(Quote %)", "quote"),
    ],
)
def test_column_names(caption: str, expected: str) -> None:
    assert column_name(caption) == expected


def test_name_collision_gets_suffix() -> None:
    table = SheetTable(
        "S",
        [
            Column("SUM(Wert)", "real", [1.0]),
            Column("AVG(Wert)", "real", [1.0]),
            Column("Kreis Name", "cstring", ["a"]),
            Column("ags5", "cstring", ["x"]),
        ],
    )
    cols = [f.column for f in describe_fields(table)]
    assert cols == ["wert", "wert_2", "kreis_name_2", "ags5_2"]


def test_class_detected_from_values() -> None:
    col = Column("Stufe", "cstring", ["bis unter 15", "15 bis unter 30", "30 und mehr"] * 10)
    assert describe_fields(SheetTable("S", [col]))[0].role == ROLE_CLASS
