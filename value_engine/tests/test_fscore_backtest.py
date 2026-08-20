"""
Testy FSCORE BACKTEST (silnik v7). Sprawdzamy to, co odroznia go od v4-v6:

  - cykl zycia pozycji to DOKLADNIE jeden rok (sprzedaj wszystko 1 lipca, zloz portfel od zera),
  - bramka DWUSTOPNIOWA: najpierw top X% po B/M, POTEM prog F-Score na tym podzbiorze,
  - brak kandydatow = GOTOWKA (a nie "kup cokolwiek"),
  - equal weight przy wejsciu.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_fscore_backtest.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport
from value_engine.fscore import annual_decision_dates
from value_engine.fscore_backtest import FScoreConfig, run_fscore_backtest
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"
PL_DATA_DIR = REPO_ROOT / "data" / "pl"

_PERIODS = ["2018 (gru 18)", "2019 (gru 19)", "2020 (gru 20)", "2021 (gru 21)"]
_PUBLISHED = ["2019-03-15", "2020-03-15", "2021-03-15", "2022-03-15"]


def _perfect(book: float) -> dict:
    """Spolka z F-Score 9 i podanym kapitalem wlasnym (steruje B/M)."""
    return {
        "IncomeNetProfit": [100.0, 150.0, 250.0, 400.0],
        "CashflowOperatingCashflow": [200.0, 300.0, 500.0, 800.0],
        "BalanceTotalAssets": [1000.0, 1000.0, 1000.0, 1000.0],
        "BalanceNoncurrentLiabilities": [500.0, 400.0, 300.0, 200.0],
        "BalanceCurrentAssets": [300.0, 400.0, 500.0, 600.0],
        "BalanceCurrentLiabilities": [200.0, 200.0, 200.0, 200.0],
        "BalanceShareCapital": [50.0, 50.0, 50.0, 50.0],
        "IncomeGrossProfit": [300.0, 450.0, 700.0, 1000.0],
        "IncomeRevenues": [1000.0, 1200.0, 1500.0, 1800.0],
        "BalanceCapital": [book, book, book, book],
    }


def _weak(book: float) -> dict:
    """Spolka z niskim F-Score: strata, ujemny CFO, rosnaca dzwignia, emisja akcji."""
    data = _perfect(book)
    data.update(
        {
            "IncomeNetProfit": [100.0, 150.0, -250.0, -400.0],
            "CashflowOperatingCashflow": [200.0, 300.0, -500.0, -800.0],
            "BalanceNoncurrentLiabilities": [200.0, 300.0, 400.0, 500.0],
            "BalanceCurrentAssets": [600.0, 500.0, 400.0, 300.0],
            "BalanceShareCapital": [50.0, 60.0, 70.0, 80.0],
            "IncomeGrossProfit": [1000.0, 700.0, 450.0, 300.0],
            "IncomeRevenues": [1800.0, 1500.0, 1200.0, 1000.0],
        }
    )
    return data


def _panel(**by_ticker) -> FundamentalPanel:
    return FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker=ticker.upper(),
                report_type="mixed",
                periodicity="annual",
                periods=list(_PERIODS),
                publication_dates=list(_PUBLISHED),
                metrics=metrics,
            )
            for ticker, metrics in by_ticker.items()
        ],
        periodicity="annual",
    )


def _estimator(panel: FundamentalPanel, tickers, shares: float = 1_000_000.0) -> SharesEstimator:
    """`SharesEstimator` potrzebuje kapitalu zakladowego i dzisiejszej liczby akcji. Kapital
    zakladowy jest staly (50), wiec liczba akcji tez - kapitalizacja = cena * 1 mln akcji."""
    return SharesEstimator(panel, {t.upper(): shares for t in tickers})


def _prices(**series) -> pd.DataFrame:
    length = max(len(v) for v in series.values())
    index = pd.bdate_range("2019-01-01", periods=length)
    return pd.DataFrame(series, index=index)


def _run(prices, panel, tickers=None, **overrides):
    tickers = tickers or list(prices.columns)
    config = FScoreConfig(tickers=tickers, **overrides)
    return run_fscore_backtest(
        prices,
        panel,
        _estimator(panel, tickers),
        annual_decision_dates(prices.index),
        config,
    )


# --- DWUSTOPNIOWA BRAMKA ---


def test_only_high_book_to_market_companies_are_candidates():
    """Spolka z F-Score 9, ale NISKIM B/M (droga ksiegowo) nie moze byc kandydatem - najpierw
    filtr B/M, potem F-Score. To kolejnosc ze spec, nie odwrotna."""
    # tanie: kapital wlasny 900 tys -> B/M = 900*1000 / (100 * 1e6) = 9.0
    # drogie: kapital wlasny 1 tys  -> B/M = 0.01
    panel = _panel(tania=_perfect(900.0), droga=_perfect(1.0))
    prices = _prices(tania=[100.0] * 800, droga=[100.0] * 800)

    result = _run(prices, panel, book_to_market_fraction=0.50, min_fscore=8)

    decision = next(d for d in result["decisions"] if d.selected)
    assert decision.candidates == ["tania"]
    assert decision.selected == ["tania"]


def test_high_book_to_market_but_low_fscore_is_rejected():
    panel = _panel(tania_slaba=_weak(900.0), droga_dobra=_perfect(1.0))
    prices = _prices(tania_slaba=[100.0] * 800, droga_dobra=[100.0] * 800)

    result = _run(prices, panel, book_to_market_fraction=0.50, min_fscore=8)

    for decision in result["decisions"]:
        assert decision.selected == [], f"{decision.date}: kupiono {decision.selected}"
    assert not result["trades"]


def test_no_candidates_means_cash_not_a_fallback_purchase():
    """DOPRECYZOWANIE 1: brak spolek z F-Score 8-9 = gotowka. Krzywa kapitalu MUSI byc plaska,
    mimo ze ceny rosna - inaczej silnik po cichu kupowalby cokolwiek."""
    panel = _panel(a=_weak(900.0), b=_weak(800.0))
    prices = _prices(a=list(range(100, 900)), b=list(range(100, 900)))

    result = _run(prices, panel, min_fscore=8)
    equity = result["equity_curve"]["equity"]

    assert equity.iloc[-1] == pytest.approx(1.0)
    assert equity.nunique() == 1, "portfel w gotowce nie moze zmieniac wartosci"
    assert all(not d.in_market for d in result["decisions"])


def test_incomplete_fscore_is_rejected_when_all_signals_required():
    """Bramka wymaga 9/9 DOSTEPNYCH sygnalow (decyzja 4 w `fscore.py`).

    Konstrukcja testu: ceny koncza sie przed lipcem 2021, wiec ostatnia data decyzyjna to
    2020-07-01, a wtedy - po regule "+6 miesiecy" - dostepne sa tylko DWA raporty roczne (2018 i
    2019). Cztery sygnaly potrzebuja aktywow z poczatku roku POPRZEDNIEGO, czyli trzeciego raportu,
    wiec `available` = 6. Spolka jest doskonala (6/6 spelnionych), a mimo to bramka `9/9` ja
    odrzuca - i to jest zamierzone."""
    prices = _prices(a=[100.0] * 500)
    panel = _panel(a=_perfect(900.0))

    strict = _run(prices, panel, min_fscore=5, require_all_signals=True)
    loose = _run(prices, panel, min_fscore=5, require_all_signals=False)

    assert not strict["trades"]
    assert loose["trades"], "z `require_all_signals=False` niepelny F-Score moze wejsc"
    assert loose["trades"][0].fscore == 6


# --- CYKL ROCZNY ---


def test_position_is_held_exactly_until_the_next_annual_date():
    panel = _panel(a=_perfect(900.0))
    prices = _prices(a=[100.0] * 800)

    result = _run(prices, panel, min_fscore=8)
    dates = annual_decision_dates(prices.index)

    assert result["trades"], "spolka z F-Score 9 i wysokim B/M musi byc kupiona"
    for trade in result["trades"]:
        assert trade.entry_date in dates
        # wyjscie to nastepna data roczna albo koniec danych
        assert trade.exit_date in dates or trade.exit_date == prices.index[-1]
        assert 250 <= trade.holding_days <= 400 or trade.exit_date == prices.index[-1]


def test_portfolio_is_rebuilt_from_scratch_every_year():
    """Ta sama spolka kupiona w dwoch kolejnych latach daje DWIE transakcje, nie jedna trzymana
    dwa lata - portfel jest skladany od zera (koszty sa placone co roku).

    Ceny musza siegac az za lipiec 2022, bo pelne 9/9 sygnalow wymaga TRZECH dostepnych raportow
    rocznych, a przy regule "+6 miesiecy" pierwsza taka data to 2021-07-01."""
    panel = _panel(a=_perfect(900.0))
    prices = _prices(a=[100.0] * 950)

    result = _run(prices, panel, min_fscore=8)

    entries = [t.entry_date for t in result["trades"]]
    assert len(entries) == len(set(entries)) >= 2, f"transakcje: {entries}"


def test_equal_weight_at_entry():
    panel = _panel(a=_perfect(900.0), b=_perfect(800.0), c=_perfect(700.0))
    prices = _prices(a=[100.0] * 800, b=[50.0] * 800, c=[25.0] * 800)

    result = _run(prices, panel, book_to_market_fraction=1.00, min_fscore=8)

    first = min(t.entry_date for t in result["trades"])
    bought = [t for t in result["trades"] if t.entry_date == first]
    assert len(bought) == 3
    # rowne wagi przy roznych cenach -> wartosc pozycji ta sama, liczba akcji rozna
    values = {t.ticker: t.entry_price for t in bought}
    assert values == {"a": 100.0, "b": 50.0, "c": 25.0}


def test_costs_are_charged_on_both_legs():
    panel = _panel(a=_perfect(900.0))
    prices = _prices(a=[100.0] * 800)

    free = _run(prices, panel, min_fscore=8, cost_bps=0.0)["equity_curve"]["equity"].iloc[-1]
    costly = _run(prices, panel, min_fscore=8, cost_bps=100.0)["equity_curve"]["equity"].iloc[-1]

    assert free == pytest.approx(1.0, abs=1e-9), "przy stalej cenie i zerowych kosztach kapital stoi"
    assert costly < free


def test_max_positions_caps_the_portfolio():
    panel = _panel(**{f"t{i}": _perfect(900.0 - i) for i in range(6)})
    prices = _prices(**{f"t{i}": [100.0] * 800 for i in range(6)})

    capped = _run(prices, panel, book_to_market_fraction=1.00, min_fscore=8, max_positions=2)

    first = min(t.entry_date for t in capped["trades"])
    assert len([t for t in capped["trades"] if t.entry_date == first]) == 2


def test_universe_filter_limits_candidates():
    panel = _panel(a=_perfect(900.0), b=_perfect(800.0))
    prices = _prices(a=[100.0] * 800, b=[100.0] * 800)
    dates = annual_decision_dates(prices.index)
    config = FScoreConfig(tickers=["a", "b"], book_to_market_fraction=1.00, min_fscore=8)

    result = run_fscore_backtest(
        prices,
        panel,
        _estimator(panel, ["a", "b"]),
        dates,
        config,
        eligible_universe={date: ["a"] for date in dates},
    )

    assert {t.ticker for t in result["trades"]} == {"a"}


def test_invalid_config_raises():
    panel = _panel(a=_perfect(900.0))
    prices = _prices(a=[100.0] * 500)

    with pytest.raises(ValueError, match="book_to_market_fraction"):
        _run(prices, panel, book_to_market_fraction=0.0)
    with pytest.raises(ValueError, match="min_fscore"):
        _run(prices, panel, min_fscore=10)


# --- na prawdziwych danych ---


def test_real_data_spec_variant_is_barely_investable():
    """KLUCZOWY WYNIK v7 zapisany jako test: regula ze spec (top 20% B/M + F-Score 8-9) na 40
    spolkach przepuszcza tak malo, ze strategia siedzi w gotowce wiekszosc czasu. Gdyby ten test
    zaczal padac "w gore", znaczylo by to, ze uniwersum urroslo na tyle, ze v7 da sie wreszcie
    zmierzyc - i wtedy trzeba wrocic do tej koncepcji."""
    if not DB_PATH.exists() or not PL_DATA_DIR.exists():
        pytest.skip("Brak danych")
    from value_engine.run_fscore import FScoreHarness
    from value_engine.run_quality_value import discover_tickers
    from value_engine.universe import load_industries, non_financial_tickers

    tickers = non_financial_tickers(discover_tickers(), load_industries(DB_PATH))
    harness = FScoreHarness(tickers)
    result, metrics = harness.run()

    assert metrics is not None
    assert metrics["time_in_market"] < 0.35, f"w rynku {metrics['time_in_market']:.0%}"
    assert metrics["names_per_year"] < 1.0, f"spolek/rok {metrics['names_per_year']:.2f}"
    assert len(result["trades"]) < 15


def test_real_data_loosened_variant_is_investable():
    """Wariant BEZ filtra B/M i z progiem F >= 7 jest juz mierzalny (ok. 5 spolek/rok, prawie
    zawsze w rynku) - to on jest podstawa wnioskow o samym F-Score."""
    if not DB_PATH.exists() or not PL_DATA_DIR.exists():
        pytest.skip("Brak danych")
    from value_engine.run_fscore import FScoreHarness
    from value_engine.run_quality_value import discover_tickers
    from value_engine.universe import load_industries, non_financial_tickers

    tickers = non_financial_tickers(discover_tickers(), load_industries(DB_PATH))
    harness = FScoreHarness(tickers)
    _, metrics = harness.run(book_to_market_fraction=1.00, min_fscore=7)

    assert metrics is not None
    assert metrics["time_in_market"] > 0.85
    assert metrics["names_per_year"] > 3.0
