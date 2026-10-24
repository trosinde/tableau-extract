from decimal import Decimal

import pytest

from tableau_extract.errors import FormatError
from tableau_extract.normalize import is_special, parse_number, text_value


@pytest.mark.parametrize(
    ("value", "locale", "expected"),
    [
        ("1.234,5", "de_DE", Decimal("1234.5")),
        ("12.000", "de_DE", Decimal("12000")),
        ("1,600", "en_US", Decimal("1600")),
        ("23,000", "en_US", Decimal("23000")),
        ("1,234.56", "en_US", Decimal("1234.56")),
        ("350", "en_US", Decimal("350")),
        (75.4, "en_US", Decimal("75.4")),
        (0.1, None, Decimal("0.1")),
        (9764000, None, Decimal("9764000")),
        ("12,5%", "de_DE", Decimal("0.125")),
        ("-3,25", "de_DE", Decimal("-3.25")),
    ],
)
def test_parse_number(value: object, locale: str | None, expected: Decimal) -> None:
    assert parse_number(value, locale) == expected  # type: ignore[arg-type]


def test_float_is_exact_not_binary() -> None:
    assert str(parse_number(75.4, "en_US")) == "75.4"


@pytest.mark.parametrize("value", [None, "", "*", "null", "%null%", "-", " "])
def test_special_values_become_empty(value: object) -> None:
    assert is_special(value)  # type: ignore[arg-type]
    assert parse_number(value, "de_DE") is None  # type: ignore[arg-type]
    assert text_value(value) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "locale"),
    [("1,234.5", "de_DE"), ("1.234,5", "en_US"), ("12a", "de_DE"), ("1,60", "en_US")],
)
def test_ambiguous_or_wrong_format_raises(value: str, locale: str) -> None:
    with pytest.raises(FormatError):
        parse_number(value, locale)


def test_class_text_kept() -> None:
    assert text_value("60 bis unter 75") == "60 bis unter 75"


def test_normalize_column_measure_and_class(synthetic_text: str) -> None:
    from tableau_extract.normalize import describe_fields, normalize_column
    from tableau_extract.vizql_parse import parse_bootstrap

    view = parse_bootstrap(synthetic_text)
    karte = view.sheets["Karte"]
    fields = {f.original: f for f in describe_fields(karte)}
    bedarf = normalize_column(
        karte.column("SUM(Bedarf (Round))"), fields["SUM(Bedarf (Round))"], view.locale
    )
    assert bedarf == [Decimal("1234.5"), None, None, Decimal("12000")]
    klasse = fields["Bedarf je EW (Klassen)"]
    assert klasse.value_kind == "klasse"
    assert (
        normalize_column(karte.column(klasse.original), klasse, view.locale)[0] == "15 bis unter 30"
    )
    assert fields["SUM(Quote)"].value_kind == "wert"
