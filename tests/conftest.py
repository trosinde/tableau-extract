from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def bbsr_text() -> str:
    return (FIXTURES / "bbsr_bootstrap.txt").read_text(encoding="utf-8")


@pytest.fixture
def synthetic_text() -> str:
    return (FIXTURES / "synthetic_bootstrap_de.txt").read_text(encoding="utf-8")
