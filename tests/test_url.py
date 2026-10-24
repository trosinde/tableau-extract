import pytest

from tableau_extract.errors import InputError
from tableau_extract.url import parse_view_url

BBSR = (
    "https://tableau.bbsr.bund.de/t/bbr/views/"
    "Wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_FINAL/DWohnungsneubaubedare_insgesamt"
)


def test_bbsr_url_parts() -> None:
    v = parse_view_url(BBSR + "?%3Aembed=y&%3AisGuestRedirectFromVizportal=y")
    assert v.base == "https://tableau.bbsr.bund.de"
    assert v.site == "bbr"
    assert v.workbook == "Wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_FINAL"
    assert v.sheet == "DWohnungsneubaubedare_insgesamt"
    assert v.normalized == BBSR
    assert v.csv_url == BBSR + ".csv"
    assert v.embed_url == BBSR + "?:embed=y"
    assert v.vizql_prefix == (
        "https://tableau.bbsr.bund.de/vizql/t/bbr/w/"
        "Wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_FINAL/v/DWohnungsneubaubedare_insgesamt"
    )


def test_display_params_do_not_change_slug_or_url() -> None:
    a = parse_view_url(BBSR + "?:embed=y&:toolbar=no&:showVizHome=no")
    b = parse_view_url(BBSR)
    assert a == b
    assert a.slug == (
        "bbr-wohnungsneubaubedarfe_insgesamt_2023_bis_2030pa_krs_final-dwohnungsneubaubedare_insgesamt"
    )


def test_non_display_params_are_kept_sorted() -> None:
    v = parse_view_url(BBSR + "?Zeitraum=2023&:embed=y&Art=x")
    assert v.query == "Art=x&Zeitraum=2023"
    assert v.normalized == BBSR + "?Art=x&Zeitraum=2023"


def test_url_without_site() -> None:
    v = parse_view_url("https://public.tableau.com/views/WB/Sheet1?:embed=y")
    assert v.site is None
    assert v.normalized == "https://public.tableau.com/views/WB/Sheet1"
    assert v.slug == "default-wb-sheet1"


def test_vizportal_fragment_url() -> None:
    v = parse_view_url("https://tableau.bbsr.bund.de/#/site/bbr/views/WB/Sheet?:iid=1")
    assert (v.site, v.workbook, v.sheet) == ("bbr", "WB", "Sheet")


def test_url_without_views_is_rejected() -> None:
    with pytest.raises(InputError, match="Keine Tableau-View-URL"):
        parse_view_url("https://tableau.bbsr.bund.de/t/bbr/projects/12")


def test_embedding_page_points_to_iframe() -> None:
    page = (
        "https://www.bbsr.bund.de/BBSR/DE/forschung/fachbeitraege/wohnen-immobilien/"
        "wohnungsmarktprognose/prognose/01-prognose.html"
    )
    with pytest.raises(InputError, match="iframe"):
        parse_view_url(page)


def test_not_a_url() -> None:
    with pytest.raises(InputError):
        parse_view_url("Wohnungsneubaubedarf")
