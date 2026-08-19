"""
Testy UNIVERSE - uniwersum point-in-time (plynnosc + historia liczone bez look-ahead).

Uruchomienie: .venv/bin/pytest value_engine/tests/test_universe.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.universe import load_turnover, point_in_time_universe, universe_size_report

REPO_ROOT = Path(__file__).resolve().parents[2]
PL_DATA_DIR = REPO_ROOT / "data" / "pl"


def _frames(n_days: int = 300):
    index = pd.bdate_range("2019-01-01", periods=n_days)
    prices = pd.DataFrame({"liquid": 100.0, "illiquid": 10.0}, index=index)
    turnover = pd.DataFrame({"liquid": 50_000_000.0, "illiquid": 100_000.0}, index=index)
    return prices, turnover, index


def test_liquidity_threshold_excludes_illiquid_ticker():
    prices, turnover, index = _frames()
    dates = [index[260]]

    universe = point_in_time_universe(
        prices, turnover, dates, min_history_days=252, min_median_turnover=2_000_000.0, turnover_lookback_days=126
    )

    assert universe[dates[0]] == ["liquid"]


def test_zero_threshold_keeps_everyone_with_enough_history():
    prices, turnover, index = _frames()
    dates = [index[260]]

    universe = point_in_time_universe(prices, turnover, dates, min_median_turnover=0.0)

    assert universe[dates[0]] == ["illiquid", "liquid"]


def test_min_history_gate_excludes_recently_listed():
    """Bez tego swiezo notowana spolka wchodzilaby do uniwersum, mimo ze nie da sie dla niej
    policzyc 52W high."""
    prices, turnover, index = _frames()
    dates = [index[100], index[260]]

    universe = point_in_time_universe(prices, turnover, dates, min_history_days=252, min_median_turnover=0.0)

    assert universe[dates[0]] == []  # 100 sesji < 252
    assert set(universe[dates[1]]) == {"liquid", "illiquid"}


def test_liquidity_is_computed_only_from_the_past():
    """KRYTYCZNE: obrot musi byc liczony z okna KROCZACEGO WSTECZ. Spolka, ktora stanie sie plynna
    dopiero w przyszlosci, NIE moze byc w uniwersum dzisiaj."""
    index = pd.bdate_range("2019-01-01", periods=600)
    prices = pd.DataFrame({"a": 100.0}, index=index)
    # nieplynna przez pierwsze 400 sesji, potem bardzo plynna
    turnover = pd.DataFrame({"a": [100_000.0] * 400 + [50_000_000.0] * 200}, index=index)

    early, late = index[300], index[560]
    universe = point_in_time_universe(
        prices, turnover, [early, late], min_history_days=252, min_median_turnover=2_000_000.0,
        turnover_lookback_days=126,
    )

    assert universe[early] == [], "spolka byla wtedy nieplynna - nie moze byc w uniwersum"
    assert universe[late] == ["a"], "po realnym wzroscie plynnosci powinna wejsc"


def test_top_n_keeps_only_most_liquid():
    index = pd.bdate_range("2019-01-01", periods=300)
    prices = pd.DataFrame({"a": 100.0, "b": 100.0, "c": 100.0}, index=index)
    turnover = pd.DataFrame({"a": 10e6, "b": 30e6, "c": 20e6}, index=index)
    dates = [index[260]]

    universe = point_in_time_universe(prices, turnover, dates, min_median_turnover=0.0, top_n=2)

    assert set(universe[dates[0]]) == {"b", "c"}  # dwie najplynniejsze, nie "a"


def test_median_not_mean_so_one_spike_does_not_qualify():
    """Mediana, nie srednia: jeden dzien z ogromnym obrotem nie moze kwalifikowac spolki na
    kolejne pol roku."""
    index = pd.bdate_range("2019-01-01", periods=300)
    prices = pd.DataFrame({"a": 100.0}, index=index)
    spike = [100_000.0] * 299
    spike[250] = 10_000_000_000.0  # jednodniowy wystrzal
    turnover = pd.DataFrame({"a": spike + [100_000.0]}, index=index)
    dates = [index[260]]

    universe = point_in_time_universe(
        prices, turnover, dates, min_median_turnover=2_000_000.0, turnover_lookback_days=126
    )

    assert universe[dates[0]] == []


def test_universe_size_report():
    prices, turnover, index = _frames()
    dates = [index[260], index[270]]
    universe = point_in_time_universe(prices, turnover, dates, min_median_turnover=0.0)

    sizes = universe_size_report(universe)

    assert list(sizes.values) == [2, 2]
    assert list(sizes.index) == dates


# --- na prawdziwych danych ---


def test_real_turnover_loads_and_has_no_zero_volume_gaps():
    if not PL_DATA_DIR.exists():
        pytest.skip("Brak data/pl")
    turnover = load_turnover(["cdr", "kgh", "dnp"], PL_DATA_DIR)

    assert set(turnover.columns) == {"cdr", "kgh", "dnp"}
    for ticker in turnover.columns:
        series = turnover[ticker].dropna()
        assert len(series) > 500
        assert (series > 0).mean() > 0.99, f"{ticker}: podejrzanie duzo dni z zerowym obrotem"


def test_real_data_cdr_excluded_during_microcap_years():
    """Sedno poprawki uniwersum PIT: CD Projekt w 2008 mial obrot ~0.4 mln PLN/dzien (mikrospolka,
    ~170x mniej niz KGH) i NIE nalezal do "duzych i plynnych" spolek. Przy stalej liscie byl tam
    przez cala historie - i to WLASNIE on odwracal wnioski w tescie leave-one-out. Uniwersum PIT
    musi go wykluczyc w tamtych latach i wpuscic dopiero, gdy realnie urosl."""
    if not PL_DATA_DIR.exists():
        pytest.skip("Brak data/pl")
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY

    tickers = ["cdr", "kgh"]
    prices = LOADER_REGISTRY["stooq_csv"](tickers, {"data_dir": str(PL_DATA_DIR), "frequency": "daily"}).prices
    turnover = load_turnover(tickers, PL_DATA_DIR)
    dates = [pd.Timestamp("2008-01-02"), pd.Timestamp("2026-06-01")]
    dates = [d for d in dates if d in prices.index]

    universe = point_in_time_universe(prices, turnover, dates, min_median_turnover=2_000_000.0)

    early, late = dates[0], dates[-1]
    assert "cdr" not in universe[early], "CDR byl wtedy mikrospolka - nie powinien byc w uniwersum"
    assert "kgh" in universe[early], "KGH byl wtedy duzy i plynny - powinien byc"
    assert "cdr" in universe[late], "dzis CDR jest plynny - powinien byc"
