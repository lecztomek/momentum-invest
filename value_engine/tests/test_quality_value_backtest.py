"""
Testy QUALITY VALUE BACKTEST - mechanika slotow, reguly podmiany i wyjsc.

Na syntetycznych danych, zeby sprawdzac REGULY (a nie akurat panujace warunki rynkowe).

Uruchomienie: .venv/bin/pytest value_engine/tests/test_quality_value_backtest.py -v
"""

from typing import Dict, List, Optional

import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport
from value_engine.fundamentals import FundamentalPanel
from value_engine.quality_value_backtest import QualityValueConfig, run_quality_value_backtest
from value_engine.signals import month_start_decision_dates

_PERIODS = [f"{y}/Q{q} (x)" for y in (2017, 2018) for q in (1, 2, 3, 4)]
_DATES = [
    "2017-05-01", "2017-08-01", "2017-11-01", "2018-01-02",
    "2018-05-01", "2018-08-01", "2018-11-01", "2019-01-01",
]
_HIGH_LOOKBACK = 40
_REL_LOOKBACK = 20


def _panel(specs: Dict[str, str]) -> FundamentalPanel:
    """`specs`: ticker (WIELKIMI) -> "good" (QUALITY 100) albo "bad" (QUALITY 0).

    "good": zysk>0, CFO>=zysk, dlug/aktywa spada. "bad": strata, CFO<0, dlug/aktywa rosnie."""
    reports = []
    for ticker, kind in specs.items():
        good = kind == "good"
        reports.append(
            ParsedReport(
                ticker=ticker,
                report_type="mixed",
                periodicity="quarterly",
                periods=_PERIODS,
                publication_dates=_DATES,
                metrics={
                    "IncomeNetProfit": [10.0 if good else -10.0] * 8,
                    "CashflowOperatingCashflow": [20.0 if good else -5.0] * 8,
                    "BalanceCurrentBorrowings": ([100.0] * 4 + [50.0] * 4) if good else ([50.0] * 4 + [100.0] * 4),
                    "BalanceNoncurrentBorrowings": [0.0] * 8,
                    "BalanceTotalAssets": [1000.0] * 8,
                },
            )
        )
    return FundamentalPanel.from_reports(reports)


def _config(tickers: List[str], **overrides) -> QualityValueConfig:
    defaults = dict(
        tickers=tickers,
        max_positions=overrides.pop("max_positions", 2),
        high_lookback_days=_HIGH_LOOKBACK,
        relative_lookback_days=_REL_LOOKBACK,
        cost_bps=0.0,
    )
    defaults.update(overrides)
    return QualityValueConfig(**defaults)


def _run(prices: pd.DataFrame, config: QualityValueConfig, panel: Optional[FundamentalPanel] = None) -> dict:
    panel = panel or _panel({t.upper(): "good" for t in config.tickers})
    benchmark = pd.Series(100.0, index=prices.index)  # plaski rynek: REL zalezy tylko od spolki
    return run_quality_value_backtest(prices, benchmark, panel, month_start_decision_dates(prices), config)


def _flat_then_drop(n: int, drop_to: float) -> List[float]:
    """40 dni na 100 (napelnia okno 52W high), potem spadek na `drop_to` do konca."""
    return ([100.0] * _HIGH_LOOKBACK + [drop_to] * n)[:n]


# --- BRAMKA WEJSCIA ---


def test_no_entry_below_drawdown_gate():
    index = pd.bdate_range("2019-01-01", periods=120)
    prices = pd.DataFrame({"a": _flat_then_drop(len(index), 90.0)}, index=index)  # tylko -10%

    result = _run(prices, _config(["a"], min_drawdown=0.25))

    assert result["trades"] == []


def test_entry_when_drawdown_gate_met():
    index = pd.bdate_range("2019-01-01", periods=120)
    prices = pd.DataFrame({"a": _flat_then_drop(len(index), 70.0)}, index=index)  # -30%

    result = _run(prices, _config(["a"], min_drawdown=0.25))

    assert result["trades"], "spolka przeszla bramke, a nie zostala kupiona"
    assert result["trades"][0].entry_price == pytest.approx(70.0)


def test_no_entry_when_quality_below_gate():
    index = pd.bdate_range("2019-01-01", periods=120)
    prices = pd.DataFrame({"a": _flat_then_drop(len(index), 50.0)}, index=index)

    result = _run(prices, _config(["a"], min_quality=50.0), panel=_panel({"A": "bad"}))

    assert result["trades"] == []


def test_quality_gate_can_be_disabled():
    """Wariant `min_quality=0` (sprawdzany w sweepie) musi realnie wpuszczac slabe spolki."""
    index = pd.bdate_range("2019-01-01", periods=120)
    prices = pd.DataFrame({"a": _flat_then_drop(len(index), 50.0)}, index=index)

    result = _run(prices, _config(["a"], min_quality=0.0), panel=_panel({"A": "bad"}))

    assert result["trades"], "przy wylaczonej bramce jakosci slaba spolka powinna byc kupiona"


# --- SLOTY I RANKING ---


def test_best_candidate_fills_free_slot_first():
    index = pd.bdate_range("2019-01-01", periods=120)
    prices = pd.DataFrame(
        {"deep": _flat_then_drop(len(index), 40.0), "shallow": _flat_then_drop(len(index), 70.0)}, index=index
    )

    result = _run(prices, _config(["deep", "shallow"], max_positions=1))

    held = [d["held"] for d in result["decisions"] if d["n_positions"] > 0]
    assert held and held[0] == ["deep"]  # mocniej przeceniona ma wyzszy DD percentyl


def test_respects_max_positions_and_never_goes_negative_on_cash():
    index = pd.bdate_range("2019-01-01", periods=150)
    tickers = ["a", "b", "c", "d", "e"]
    prices = pd.DataFrame({t: _flat_then_drop(len(index), 50.0) for t in tickers}, index=index)

    result = _run(prices, _config(tickers, max_positions=3))

    assert max(d["n_positions"] for d in result["decisions"]) == 3
    for decision in result["decisions"]:
        assert decision["n_positions"] <= 3
    # brak dzwigni: equity nigdy nie skacze powyzej sumy wycen (kontrola przez dodatnia equity)
    assert (result["equity_curve"]["equity"] > 0).all()


# --- REGULA PODMIANY ---


def _replacement_prices(index: pd.DatetimeIndex) -> pd.DataFrame:
    """"held" wchodzi pierwsze (spadek -30%), potem "newcomer" leci znacznie glebiej (-70%),
    czyli dostaje wyzszy DD percentyl i moze podmienic."""
    held = ([100.0] * _HIGH_LOOKBACK + [70.0] * len(index))[: len(index)]
    newcomer = ([100.0] * (_HIGH_LOOKBACK + 45) + [30.0] * len(index))[: len(index)]
    return pd.DataFrame({"held": held, "newcomer": newcomer}, index=index)


def test_replacement_happens_when_margin_exceeded():
    index = pd.bdate_range("2019-01-01", periods=200)
    prices = _replacement_prices(index)

    result = _run(prices, _config(["held", "newcomer"], max_positions=1, replace_margin=10.0))

    replaced = [t for t in result["trades"] if t.exit_reason == "replaced"]
    assert replaced, "podmiana nie nastapila, choc przewaga score powinna przekroczyc prog"
    assert replaced[0].ticker == "held"


def test_no_replacement_when_margin_not_exceeded():
    """Ten sam uklad cen, ale prog podmiany podniesiony powyzej realnej roznicy score - portfel
    ma zostac nietkniety. To pilnuje, ze prog dziala, a nie ze podmiana jest bezwarunkowa."""
    index = pd.bdate_range("2019-01-01", periods=200)
    prices = _replacement_prices(index)

    result = _run(prices, _config(["held", "newcomer"], max_positions=1, replace_margin=1000.0))

    assert [t for t in result["trades"] if t.exit_reason == "replaced"] == []


def test_at_most_one_replacement_per_month_by_default():
    index = pd.bdate_range("2019-01-01", periods=200)
    tickers = ["h1", "h2", "n1", "n2"]
    data = {
        "h1": ([100.0] * _HIGH_LOOKBACK + [70.0] * len(index))[: len(index)],
        "h2": ([100.0] * _HIGH_LOOKBACK + [72.0] * len(index))[: len(index)],
        "n1": ([100.0] * (_HIGH_LOOKBACK + 45) + [20.0] * len(index))[: len(index)],
        "n2": ([100.0] * (_HIGH_LOOKBACK + 45) + [22.0] * len(index))[: len(index)],
    }
    prices = pd.DataFrame(data, index=index)

    result = _run(prices, _config(tickers, max_positions=2, replace_margin=0.0))

    assert all(d["replacements"] <= 1 for d in result["decisions"])


# --- WYJSCIA ---


def test_exit_on_fundamental_fail():
    """Spolka kupiona jako "good" traci jakosc w trakcie trzymania (publikacja straty) i MUSI byc
    sprzedana z powodem `fundamental_fail`, niezaleznie od ceny."""
    index = pd.bdate_range("2019-01-01", periods=200)
    prices = pd.DataFrame({"a": _flat_then_drop(len(index), 60.0)}, index=index)

    panel = FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="quarterly",
                periods=_PERIODS + ["2019/Q1 (x)"],
                publication_dates=_DATES + ["2019-04-01"],  # strata staje sie znana 2019-04-01
                metrics={
                    "IncomeNetProfit": [10.0] * 8 + [-1000.0],
                    "CashflowOperatingCashflow": [20.0] * 8 + [-1000.0],
                    "BalanceCurrentBorrowings": [100.0] * 4 + [50.0] * 4 + [500.0],
                    "BalanceNoncurrentBorrowings": [0.0] * 9,
                    "BalanceTotalAssets": [1000.0] * 9,
                },
            )
        ]
    )

    result = _run(prices, _config(["a"], max_positions=1, max_holding_months=99), panel=panel)

    fails = [t for t in result["trades"] if t.exit_reason == "fundamental_fail"]
    assert fails, f"brak wyjscia na fundamentach, powody: {[t.exit_reason for t in result['trades']]}"
    assert fails[0].exit_date >= pd.Timestamp("2019-04-01")


def test_exit_on_timeout():
    index = pd.bdate_range("2019-01-01", periods=400)
    prices = pd.DataFrame({"a": _flat_then_drop(len(index), 60.0)}, index=index)

    result = _run(prices, _config(["a"], max_positions=1, max_holding_months=6))

    timeouts = [t for t in result["trades"] if t.exit_reason == "timeout"]
    assert timeouts
    months = (timeouts[0].exit_date.year - timeouts[0].entry_date.year) * 12 + (
        timeouts[0].exit_date.month - timeouts[0].entry_date.month
    )
    assert months == 6


def test_no_profit_target_exit():
    """Spec: "bez szybkiego profit targetu" - silny wzrost NIE moze sam z siebie zamknac pozycji."""
    index = pd.bdate_range("2019-01-01", periods=200)
    # spadek -50% (wejscie), potem mocne odbicie do 200 (+300% od wejscia)
    values = ([100.0] * _HIGH_LOOKBACK + [50.0] * 25 + [200.0] * len(index))[: len(index)]
    prices = pd.DataFrame({"a": values}, index=index)

    result = _run(prices, _config(["a"], max_positions=1, max_holding_months=99))

    assert all(t.exit_reason != "target" for t in result["trades"])
    # jedyne dopuszczalne zamkniecie w tym ukladzie to koniec danych
    assert all(t.exit_reason in ("end_of_data", "fundamental_fail") for t in result["trades"])


def test_open_positions_are_closed_at_end_of_data():
    index = pd.bdate_range("2019-01-01", periods=120)
    prices = pd.DataFrame({"a": _flat_then_drop(len(index), 60.0)}, index=index)

    result = _run(prices, _config(["a"], max_positions=1, max_holding_months=99))

    assert result["trades"], "pozycja otwarta na koniec nie zostala domknieta do statystyk"
    assert result["trades"][-1].exit_reason == "end_of_data"
    assert result["trades"][-1].exit_date == index[-1]


# --- KSIEGOWANIE ---


def test_equity_curve_is_daily_and_starts_at_one():
    index = pd.bdate_range("2019-01-01", periods=100)
    prices = pd.DataFrame({"a": [100.0] * len(index)}, index=index)

    result = _run(prices, _config(["a"]))
    equity_curve = result["equity_curve"]

    assert len(equity_curve) == len(index)
    assert equity_curve["equity"].iloc[0] == pytest.approx(1.0)


def test_transaction_costs_reduce_equity():
    index = pd.bdate_range("2019-01-01", periods=200)
    prices = _replacement_prices(index)

    free = _run(prices, _config(["held", "newcomer"], max_positions=1, replace_margin=0.0, cost_bps=0.0))
    costly = _run(prices, _config(["held", "newcomer"], max_positions=1, replace_margin=0.0, cost_bps=200.0))

    assert free["trades"], "brak transakcji - test nie sprawdza kosztow"
    assert costly["equity_curve"]["equity"].iloc[-1] < free["equity_curve"]["equity"].iloc[-1]


def test_max_positions_zero_is_rejected():
    index = pd.bdate_range("2019-01-01", periods=60)
    prices = pd.DataFrame({"a": [100.0] * 60}, index=index)
    with pytest.raises(ValueError, match="max_positions"):
        _run(prices, _config(["a"], max_positions=0))


# --- v3: BEZ PODMIANY PO SCORE ---


def test_v3_disables_score_replacement_entirely():
    """v3 (user): "Bez comiesiecznej podmiany na podstawie score." Ten sam uklad cen, ktory w v2
    wywoluje podmiane, przy `allow_score_replacement=False` NIE moze jej wywolac."""
    index = pd.bdate_range("2019-01-01", periods=200)
    prices = _replacement_prices(index)

    v2 = _run(prices, _config(["held", "newcomer"], max_positions=1, replace_margin=10.0))
    v3 = _run(
        prices,
        _config(["held", "newcomer"], max_positions=1, replace_margin=10.0, allow_score_replacement=False),
    )

    assert [t for t in v2["trades"] if t.exit_reason == "replaced"]
    assert [t for t in v3["trades"] if t.exit_reason == "replaced"] == []


def test_v3_still_fills_slot_freed_by_quality_fail():
    """Score ma dalej sluzyc do WYBORU kandydata na wolny slot - tylko nie do przetasowywania.
    Slot zwolniony przez `fundamental_fail` musi zostac wypelniony najlepszym kandydatem."""
    index = pd.bdate_range("2019-01-01", periods=300)
    held = ([100.0] * _HIGH_LOOKBACK + [70.0] * len(index))[: len(index)]
    # NEWCOMER musi zjezdzac CIAGLE (1%/dzien), a nie raz spasc na staly poziom - inaczej jego
    # obsuniecie "zdrowieje" (szczyt wypada z okna 52W high) i przestaje byc kandydatem, zanim
    # zwolni sie slot.
    newcomer = [100.0] * _HIGH_LOOKBACK + [100.0 * (0.99**i) for i in range(len(index))]
    prices = pd.DataFrame({"held": held, "newcomer": newcomer[: len(index)]}, index=index)

    panel = FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="HELD",
                report_type="mixed",
                periodicity="quarterly",
                periods=_PERIODS + ["2019/Q2 (x)"],
                publication_dates=_DATES + ["2019-08-01"],  # HELD traci jakosc 2019-08-01
                metrics={
                    "IncomeNetProfit": [10.0] * 8 + [-1000.0],
                    "CashflowOperatingCashflow": [20.0] * 8 + [-1000.0],
                    "BalanceCurrentBorrowings": [100.0] * 4 + [50.0] * 4 + [500.0],
                    "BalanceNoncurrentBorrowings": [0.0] * 9,
                    "BalanceTotalAssets": [1000.0] * 9,
                },
            ),
            ParsedReport(
                ticker="NEWCOMER",
                report_type="mixed",
                periodicity="quarterly",
                periods=_PERIODS,
                publication_dates=_DATES,
                metrics={
                    "IncomeNetProfit": [10.0] * 8,
                    "CashflowOperatingCashflow": [20.0] * 8,
                    "BalanceCurrentBorrowings": [100.0] * 4 + [50.0] * 4,
                    "BalanceNoncurrentBorrowings": [0.0] * 8,
                    "BalanceTotalAssets": [1000.0] * 8,
                },
            ),
        ]
    )

    result = _run(
        prices,
        _config(["held", "newcomer"], max_positions=1, allow_score_replacement=False, max_holding_months=99),
        panel=panel,
    )

    assert [t for t in result["trades"] if t.exit_reason == "fundamental_fail"]
    assert any(d["held"] == ["newcomer"] for d in result["decisions"]), "wolny slot nie zostal wypelniony"


# --- UNIWERSUM POINT-IN-TIME ---


def test_eligible_universe_blocks_new_entries():
    index = pd.bdate_range("2019-01-01", periods=150)
    prices = pd.DataFrame({"a": _flat_then_drop(len(index), 50.0)}, index=index)
    config = _config(["a"], max_positions=1)
    panel = _panel({"A": "good"})
    benchmark = pd.Series(100.0, index=prices.index)
    dates = month_start_decision_dates(prices)

    from value_engine.quality_value_backtest import run_quality_value_backtest as run_engine

    blocked = run_engine(prices, benchmark, panel, dates, config, eligible_universe={d: [] for d in dates})
    allowed = run_engine(prices, benchmark, panel, dates, config, eligible_universe={d: ["a"] for d in dates})

    assert blocked["trades"] == []
    assert allowed["trades"], "spolka w uniwersum PIT powinna byc kupiona"


def test_position_is_not_force_sold_when_it_leaves_universe():
    """Pozycja, ktora wypadla z uniwersum (np. spadla plynnosc), NIE jest sprzedawana na sile -
    wychodzi normalnymi reguami. Wymuszona sprzedaz przy spadku plynnosci bylaby nierealistyczna."""
    index = pd.bdate_range("2019-01-01", periods=200)
    prices = pd.DataFrame({"a": _flat_then_drop(len(index), 50.0)}, index=index)
    dates = month_start_decision_dates(prices)
    cutoff = dates[4]
    universe = {d: (["a"] if d <= cutoff else []) for d in dates}

    from value_engine.quality_value_backtest import run_quality_value_backtest as run_engine

    result = run_engine(
        prices,
        pd.Series(100.0, index=prices.index),
        _panel({"A": "good"}),
        dates,
        _config(["a"], max_positions=1, max_holding_months=99),
        eligible_universe=universe,
    )

    assert result["trades"], "pozycja powinna byc otwarta przed wypadnieciem z uniwersum"
    assert result["trades"][-1].exit_reason == "end_of_data"  # nie sprzedana przy wypadnieciu
    assert any(d["date"] > cutoff and d["held"] == ["a"] for d in result["decisions"])


# --- TRAILING STOP ---


def test_trailing_stop_sells_after_drop_from_peak_since_entry():
    """Szczyt liczony OD MOMENTU ZAKUPU, nie od 52W high: wejscie po 50, szczyt 80, spadek do 60
    to -25% od szczytu -> stop 20% musi zadzialac."""
    index = pd.bdate_range("2019-01-01", periods=200)
    values = ([100.0] * _HIGH_LOOKBACK + [50.0] * 25 + [80.0] * 25 + [60.0] * len(index))[: len(index)]
    prices = pd.DataFrame({"a": values}, index=index)

    result = _run(prices, _config(["a"], max_positions=1, max_holding_months=99, trailing_stop=0.20))

    stops = [t for t in result["trades"] if t.exit_reason == "trailing_stop"]
    assert stops, f"stop nie zadzialal, powody: {[t.exit_reason for t in result['trades']]}"
    assert stops[0].exit_price == pytest.approx(60.0)
    assert stops[0].gross_return == pytest.approx(60 / 50 - 1)  # nadal na plusie wzgledem wejscia


def test_trailing_stop_does_not_fire_on_shallow_pullback():
    index = pd.bdate_range("2019-01-01", periods=200)
    # wejscie 50, szczyt 80, cofniecie do 70 = -12.5% od szczytu (mniej niz prog 20%)
    values = ([100.0] * _HIGH_LOOKBACK + [50.0] * 25 + [80.0] * 25 + [70.0] * len(index))[: len(index)]
    prices = pd.DataFrame({"a": values}, index=index)

    result = _run(prices, _config(["a"], max_positions=1, max_holding_months=99, trailing_stop=0.20))

    assert [t for t in result["trades"] if t.exit_reason == "trailing_stop"] == []


def test_trailing_stop_is_checked_daily_not_only_on_decision_dates():
    """Stop to zlecenie stojace. Spadek zaczyna sie i konczy WEWNATRZ miesiaca (kurs wraca przed
    kolejnym 1. dniem miesiaca) - kontrola miesieczna by go przegapila, dzienna nie."""
    index = pd.bdate_range("2019-01-01", periods=200)
    values = [100.0] * _HIGH_LOOKBACK + [50.0] * 25
    values += [80.0] * 15 + [55.0] * 3 + [80.0] * (len(index) - len(values) - 18)
    prices = pd.DataFrame({"a": values[: len(index)]}, index=index)

    monthly_only = _run(prices, _config(["a"], max_positions=1, max_holding_months=99))
    with_stop = _run(prices, _config(["a"], max_positions=1, max_holding_months=99, trailing_stop=0.20))

    assert [t for t in monthly_only["trades"] if t.exit_reason == "trailing_stop"] == []
    assert [t for t in with_stop["trades"] if t.exit_reason == "trailing_stop"]


def test_trailing_stop_disabled_by_default():
    index = pd.bdate_range("2019-01-01", periods=200)
    values = ([100.0] * _HIGH_LOOKBACK + [50.0] * 25 + [80.0] * 25 + [10.0] * len(index))[: len(index)]
    prices = pd.DataFrame({"a": values}, index=index)

    result = _run(prices, _config(["a"], max_positions=1, max_holding_months=99))

    assert all(t.exit_reason != "trailing_stop" for t in result["trades"])
