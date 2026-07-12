"""
Wspolne fixture'y dla testow engine_v2. Testy DATA LOADER dzialaja na prawdziwych danych z
`data/us` (to jest de facto integration test - loader ma za zadanie czytac te konkretne pliki).
Testy pozostalych blokow (np. DATA CLEANER) uzywaja w pelni syntetycznych danych, zeby byc
szybkie, deterministyczne i niezalezne od tego co akurat jest w `data/`.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def us_data_dir() -> Path:
    path = REPO_ROOT / "data" / "us"
    if not path.exists():
        pytest.skip(f"Brak folderu z danymi: {path} (dane nie sa w repo).")
    return path


@pytest.fixture
def us_universe():
    return ["ivv.us", "xlk.us", "iau.us", "dbc.us", "tlt.us"]


@pytest.fixture
def uk_data_dir() -> Path:
    path = REPO_ROOT / "data" / "uk"
    if not path.exists():
        pytest.skip(f"Brak folderu z danymi UK: {path} (dane nie sa w repo).")
    return path
