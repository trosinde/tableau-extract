from pathlib import Path

import pytest

from tableau_extract.errors import AmbiguousRegionError
from tableau_extract.models import Column, SheetTable
from tableau_extract.normalize import describe_fields
from tableau_extract.regions import (
    assign_regions,
    load_reference,
    match_name,
    normalize_key,
    split_name,
    year_from_fields,
)
from tableau_extract.vizql_parse import parse_bootstrap


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (8111, "08111"),
        ("8111", "08111"),
        (9764000, "09764"),
        ("09764000", "09764"),
        (11000, "11000"),
        (11000000, "11000"),
        (9764000.0, "09764"),
        (123, None),
        ("abc", None),
        (None, None),
        ("*", None),
        (123456, None),
    ],
)
def test_normalize_key(value: object, expected: str | None) -> None:
    assert normalize_key(value) == expected  # type: ignore[arg-type]


def test_year_from_fields() -> None:
    assert year_from_fields(["krs23", "krsname23"]) == 2023
    assert year_from_fields(["Kreis_2024"]) == 2024
    assert year_from_fields(["Kreisschlüssel"]) is None


@pytest.fixture
def ref2023():  # type: ignore[no-untyped-def]
    return load_reference(2023, cwd=Path("/nonexistent"))[0]


def test_split_name() -> None:
    assert split_name("Ahrweiler, Landkreis") == ("ahrweiler", "kreis")
    assert split_name("München, Landeshauptstadt") == ("muenchen", "stadt")
    assert split_name("Landkreis Rostock") == ("rostock", "kreis")
    assert split_name("Stuttgart, Stadtkreis") == ("stuttgart", "stadt")


def test_match_name_with_suffix(ref2023) -> None:  # type: ignore[no-untyped-def]
    assert match_name("Ahrweiler, Landkreis", ref2023) == ("07131", [])
    assert match_name("Ahrweiler", ref2023) == ("07131", [])


def test_match_name_umlaut_spelling(ref2023) -> None:  # type: ignore[no-untyped-def]
    assert match_name("Muenchen, Landkreis", ref2023) == ("09184", [])
    assert match_name("München, Stadt", ref2023) == ("09162", [])


def test_match_name_ambiguous(ref2023) -> None:  # type: ignore[no-untyped-def]
    key, cands = match_name("Landshut", ref2023)
    assert key is None
    assert len(cands) == 2
    assert match_name("Landshut, Stadt", ref2023)[0] == "09261"
    assert match_name("Landshut, Landkreis", ref2023)[0] == "09274"


def test_bbsr_complete(bbsr_text: str) -> None:
    karte = parse_bootstrap(bbsr_text).sheets["Karte"]
    res = assign_regions(karte, describe_fields(karte), cwd=Path("/nonexistent"))
    assert res.method == "schluessel"
    assert res.reference.year == 2023
    assert res.reference.origin == "paket"
    assert res.completeness["vollstaendig"] is True
    assert res.completeness["gefunden"] == 400
    assert res.warnings == []
    assert res.ags5[res.names.index("Berlin, Stadt")] == "11000"


def _table(keys: list[object] | None, names: list[str]) -> SheetTable:
    cols = [Column("Kreis", "cstring", list(names))]
    if keys is not None:
        cols.insert(0, Column("krs23", "integer", list(keys)))
    cols.append(Column("SUM(Wert)", "real", [1.0] * len(names)))
    return SheetTable("Karte", cols)


def test_missing_regions_warn(bbsr_text: str) -> None:
    karte = parse_bootstrap(bbsr_text).sheets["Karte"]
    for col in karte.columns:
        col.values = col.values[:398]
    res = assign_regions(karte, describe_fields(karte), cwd=Path("/nonexistent"))
    assert len(res.completeness["fehlend"]) == 2
    assert all("name" in m for m in res.completeness["fehlend"])
    assert res.warnings and "398/400" in res.warnings[0]


def test_double_region_warns() -> None:
    t = _table([8111, 8111], ["Stuttgart", "Stuttgart"])
    res = assign_regions(t, describe_fields(t), cwd=Path("/nonexistent"))
    assert res.completeness["doppelt"] == ["08111"]


def test_name_matching_without_key() -> None:
    t = _table(None, ["Ahrweiler, Landkreis", "Muenchen, Landkreis"])
    res = assign_regions(t, describe_fields(t), year=2023, cwd=Path("/nonexistent"))
    assert res.method == "name"
    assert res.ags5 == ["07131", "09184"]


def test_ambiguous_name_raises_exit_3() -> None:
    t = _table(None, ["Landshut"])
    with pytest.raises(AmbiguousRegionError) as ei:
        assign_regions(t, describe_fields(t), year=2023, cwd=Path("/nonexistent"))
    assert ei.value.exit_code == 3
    assert "09261" in str(ei.value) and "09274" in str(ei.value)


def test_invalid_key_raises() -> None:
    t = _table(["*", 8111], ["Irgendwo", "Stuttgart"])
    with pytest.raises(AmbiguousRegionError, match="ungültiger Kreisschlüssel"):
        assign_regions(t, describe_fields(t), cwd=Path("/nonexistent"))


def test_project_reference_has_priority(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "kreise_2023.csv").write_text(
        "ags5;name;typ\n08111;Stuttgart;Stadtkreis\n", encoding="utf-8"
    )
    ref, _ = load_reference(2023, cwd=tmp_path)
    assert ref.origin == "projekt"
    assert len(ref.rows) == 1


def test_package_reference_without_config(tmp_path: Path) -> None:
    ref, warnings = load_reference(2023, cwd=tmp_path)
    assert ref.origin == "paket"
    assert warnings == []


def test_explicit_reference_path(tmp_path: Path) -> None:
    p = tmp_path / "meine.csv"
    p.write_text("ags5;name\n8111;Stuttgart\n", encoding="utf-8")
    ref, _ = load_reference(None, path=p)
    assert ref.origin == "pfad"
    assert ref.rows[0]["ags5"] == "08111"


def test_unknown_year_falls_back_with_warning(tmp_path: Path) -> None:
    ref, warnings = load_reference(2030, cwd=tmp_path)
    assert ref.year == 2024
    assert "2030" in warnings[0]
