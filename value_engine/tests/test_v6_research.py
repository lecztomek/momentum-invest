"""
Test JEDNEJ rzeczy, na ktorej stoi cala waznosc leave-one-out na 381 spolkach:

`V6Research.restricted_universe([X])` musi dawac DOKLADNIE to samo, co przeliczenie uniwersum
point-in-time od zera na zbiorze bez X. Skrot jest dozwolony tylko dlatego, ze kryteria uniwersum
(historia cen, mediana obrotu) sa niezalezne miedzy spolkami. Gdyby ktos dodal kryterium
przekrojowe - np. `top_n` najplynniejszych albo limit na branze - skrot przestalby byc poprawny, a
381 przebiegow leave-one-out cicho liczyloby cos innego niz deklaruje.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_v6_research.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.universe import point_in_time_universe

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"
PL_DATA_DIR = REPO_ROOT / "data" / "pl"


def _synthetic(n_tickers: int = 6, n_days: int = 900):
    index = pd.bdate_range("2015-01-01", periods=n_days)
    names = [f"t{i}" for i in range(n_tickers)]
    prices = pd.DataFrame({name: [100.0 + i] * n_days for i, name in enumerate(names)}, index=index)
    # rozne poziomy obrotu, czesc ponizej progu; jedna spolka z dziurami w szeregu
    turnover = pd.DataFrame(
        {name: [(i + 1) * 1_000_000.0] * n_days for i, name in enumerate(names)}, index=index
    )
    turnover.loc[turnover.index[::7], "t3"] = float("nan")
    return prices, turnover, names, list(index[::63])


def test_dropping_a_ticker_equals_recomputing_the_universe():
    """RDZEN POPRAWNOSCI SKROTU uzytego w leave-one-out."""
    prices, turnover, names, dates = _synthetic()

    full = point_in_time_universe(prices, turnover, dates, min_median_turnover=2_000_000.0)

    for dropped in names:
        shortcut = {date: [t for t in members if t != dropped] for date, members in full.items()}
        kept = [t for t in names if t != dropped]
        recomputed = point_in_time_universe(
            prices[kept], turnover[kept], dates, min_median_turnover=2_000_000.0
        )
        assert shortcut == recomputed, f"skrot rozni sie od przeliczenia po usunieciu {dropped}"


def test_shortcut_breaks_with_top_n_and_the_test_proves_it():
    """Kontrola negatywna: gdy wlaczymy kryterium PRZEKROJOWE (`top_n` najplynniejszych), skrot
    przestaje byc poprawny. Ten test istnieje, zeby bylo jasne, DLACZEGO `run_v6_research` nie moze
    uzywac `top_n` - a nie zeby chronic jakies zachowanie."""
    prices, turnover, names, dates = _synthetic()

    full = point_in_time_universe(prices, turnover, dates, min_median_turnover=0.0, top_n=3)
    dropped = names[-1]  # najplynniejsza spolka
    shortcut = {date: [t for t in members if t != dropped] for date, members in full.items()}
    kept = [t for t in names if t != dropped]
    recomputed = point_in_time_universe(
        prices[kept], turnover[kept], dates, min_median_turnover=0.0, top_n=3
    )

    assert shortcut != recomputed, "przy `top_n` skrot MUSI sie rozjechac - inaczej test nic nie mowi"


def test_real_data_shortcut_matches_recomputation():
    if not DB_PATH.exists() or not PL_DATA_DIR.exists():
        pytest.skip("Brak danych")
    from value_engine.run_quality_value import discover_tickers, load_prices
    from value_engine.signals import quarter_start_decision_dates
    from value_engine.universe import load_industries, load_turnover, non_financial_tickers

    tickers = non_financial_tickers(discover_tickers(), load_industries(DB_PATH))[:60]
    prices = load_prices(tickers)
    turnover = load_turnover(tickers, PL_DATA_DIR)
    dates = quarter_start_decision_dates(prices)
    full = point_in_time_universe(prices[tickers], turnover, dates, min_median_turnover=2_000_000.0)

    # kilka spolek, w tym takie, ktore realnie sa w uniwersum
    present = sorted({t for members in full.values() for t in members})[:3]
    for dropped in present or tickers[:3]:
        shortcut = {date: [t for t in members if t != dropped] for date, members in full.items()}
        kept = [t for t in tickers if t != dropped]
        recomputed = point_in_time_universe(
            prices[kept], turnover[kept], dates, min_median_turnover=2_000_000.0
        )
        assert shortcut == recomputed, dropped
