from tableau_extract.fingerprint import fingerprint

FIELDS = [("krs23", "krs23", "integer"), ("SUM(x)", "x", "real")]


def fp(rows: list, sheet: str = "Karte", state: object = None) -> str:  # type: ignore[type-arg]
    return fingerprint(sheet=sheet, filter_state=state, fields=FIELDS, rows=rows)


ROWS = [("08111", (), [8111, 1.5]), ("09162", (), [9162, "23,000"])]


def test_order_does_not_matter() -> None:
    assert fp(ROWS) == fp(list(reversed(ROWS)))


def test_changed_value_changes_hash() -> None:
    changed = [ROWS[0], ("09162", (), [9162, "23,050"])]
    assert fp(ROWS) != fp(changed)


def test_sheet_and_filter_state_count() -> None:
    assert fp(ROWS) != fp(ROWS, sheet="Andere")
    assert fp(ROWS) != fp(ROWS, state={"Zeitraum": "2031-2040"})


def test_float_text_is_exact() -> None:
    a = [("08111", (), [8111, 0.1])]
    b = [("08111", (), [8111, 0.10000000000000002])]
    assert fp(a) != fp(b)


def test_hash_is_hex_sha256() -> None:
    h = fp(ROWS)
    assert len(h) == 64
    int(h, 16)
