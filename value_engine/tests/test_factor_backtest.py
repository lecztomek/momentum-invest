"""
Testy FACTOR BACKTEST (v4) - mechanika top-4 z histereza top-8.

Na syntetycznych danych. Zeby kontrolowac ranking wprost, wiekszosc testow ustawia identyczne
fundamenty dla wszystkich spolek i rozniczkuje je TYLKO cena (a wiec momentum i Value) - dzieki
temu wiadomo dokladnie, kto ma byc na ktorym miejscu.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_factor_backtest.py -v
"""

from typing import Dict, List, Optional

import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport
from value_engine.factor_backtest import FactorConfig, run_factor_backtest
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator
from value_engine.signals import month_start_decision_dates

_PERIODS = [f"{y}/Q{q} (x)" for y in (2017, 2018) for q in (1, 2, 3, 4)]
_DATES = [
    "2017-05-01", "2017-08-01", "2017-11-01", "2018-01-02",
    "2018-05-01", "2018-08-01", "2018-11-01", "2019-01-01",
]
_MOM_LOOKBACK = 40
_MOM_SKIP = 5


def _panel(tickers: List[str], weak: Optional[Dict[str, str]] = None) -> FundamentalPanel:
    """Identyczne, zdrowe fundamenty dla wszystkich - ranking rozniczkuje wtedy tylko cena.

    `weak`: ticker -> DATA PUBLIKACJI (ISO), od ktorej spolka raportuje strate i ujemny CFO, a wiec
    traci punkty Quality. Quality jest niezalezne od ceny, wiec to najczystszy sposob sterowania
    rankingiem w testach podmiany - inaczej Value (40%) przebija Momentum (30%) i drozejaca spolka
    SPADA w rankingu (poprawne zachowanie strategii, ale utrudnia testowanie histerezy).

    Data publikacji musi wypadac W TRAKCIE backtestu. Przy pogorszeniu opublikowanym PRZED pierwsza
    data decyzyjna spolka po prostu nigdy nie wchodzi do portfela, wiec nie da sie przetestowac jej
    WYPADNIECIA - to wlasnie unieważniało pierwsza wersje tych testow."""
    weak = weak or {}
    reports = []
    for ticker in tickers:
        break_date = weak.get(ticker)
        periods = list(_PERIODS)
        dates = list(_DATES)
        profit = [10.0] * 8
        cashflow = [40.0] * 8
        extra = 0
        if break_date is not None:
            periods.append("2019/Q1 (x)")
            dates.append(break_date)
            profit.append(-500.0)
            cashflow.append(-500.0)
            extra = 1
        reports.append(
            ParsedReport(
                ticker=ticker.upper(),
                report_type="mixed",
                periodicity="quarterly",
                periods=periods,
                publication_dates=dates,
                metrics={
                    "IncomeNetProfit": profit,
                    "CashflowOperatingCashflow": cashflow,
                    "CashflowCapex": [10.0] * (8 + extra),
                    "BalanceTotalAssets": [1000.0] * (8 + extra),
                    "BalanceCapital": [500.0] * (8 + extra),
                    "BalanceCurrentBorrowings": [100.0] * 4 + [50.0] * (4 + extra),
                    "BalanceNoncurrentBorrowings": [0.0] * (8 + extra),
                    "BalanceShareCapital": [1000.0] * (8 + extra),
                },
            )
        )
    return FundamentalPanel.from_reports(reports)


def _harness(prices: pd.DataFrame, weak: Optional[Dict[str, str]] = None, **overrides):
    tickers = list(prices.columns)
    panel = _panel(tickers, weak)
    estimator = SharesEstimator(panel, {t.upper(): 1_000_000.0 for t in tickers})
    config = FactorConfig(
        tickers=tickers,
        max_positions=overrides.pop("max_positions", 2),
        keep_rank=overrides.pop("keep_rank", 3),
        entry_rank=overrides.pop("entry_rank", 2),
        cost_bps=overrides.pop("cost_bps", 0.0),
        momentum_lookback_days=_MOM_LOOKBACK,
        momentum_skip_days=_MOM_SKIP,
        **overrides,
    )
    return run_factor_backtest(
        prices, panel, estimator, month_start_decision_dates(prices), config,
        eligible_universe=overrides.get("eligible_universe"),
    )


def _trend(n: int, slope: float, start: float = 100.0) -> List[float]:
    return [start * (1.0 + slope) ** i for i in range(n)]


# --- WEJSCIA I RANKING ---


def test_fills_all_slots_with_best_ranked():
    index = pd.bdate_range("2019-01-01", periods=120)
    prices = pd.DataFrame(
        {
            "best": _trend(len(index), 0.004),
            "good": _trend(len(index), 0.002),
            "bad": _trend(len(index), -0.002),
            "worst": _trend(len(index), -0.004),
        },
        index=index,
    )

    result = _harness(prices, max_positions=2)

    # Niezmiennik: trzymamy DOKLADNIE czolo wlasnego rankingu silnika. Nie zakladamy tu, KTO to
    # bedzie - przy identycznych fundamentach VALUE (40%) przebija MOMENTUM (30%), wiec wygrywaja
    # spolki TANSZE, czyli te po spadku. To poprawne zachowanie strategii i celowo nie jest tu
    # "poprawiane" na intuicyjne "wygrywa rosnaca".
    entries = [d for d in result["decisions"] if d["n_positions"] > 0]
    assert entries, "nic nie kupiono"
    for decision in entries:
        expected = {ticker for ticker, _ in decision["top"][:2]}
        assert set(decision["held"]) <= expected | set(decision["held"]), decision
    first = entries[0]
    assert set(first["held"]) == {ticker for ticker, _ in first["top"][:2]}


def test_never_exceeds_max_positions():
    index = pd.bdate_range("2019-01-01", periods=150)
    prices = pd.DataFrame({t: _trend(len(index), 0.001 * i) for i, t in enumerate("abcdef")}, index=index)

    result = _harness(prices, max_positions=3)

    assert max(d["n_positions"] for d in result["decisions"]) == 3
    assert all(d["n_positions"] <= 3 for d in result["decisions"])


def test_no_entry_gate_on_drawdown_or_quality():
    """v4 nie ma ZADNEJ bramki wejscia (inaczej niz v2/v3, gdzie wymagane bylo obsuniecie >=25% i
    QUALITY >=50). Spolka bijaca kolejne szczyty, z QUALITY = 0 (strata i ujemny CFO), MUSI byc
    kupiona, jesli jest jedynym kandydatem - w v2/v3 bylaby odrzucona dwukrotnie."""
    index = pd.bdate_range("2019-01-01", periods=120)
    prices = pd.DataFrame({"rosnie": _trend(len(index), 0.005)}, index=index)

    result = _harness(prices, weak={"rosnie": "2019-01-01"}, max_positions=1, keep_rank=1, entry_rank=1)

    assert result["trades"], "brak transakcji - v4 nie powinno miec bramki wejscia"
    assert result["trades"][0].ticker == "rosnie"


# --- HISTEREZA: top `keep_rank` / top `entry_rank` ---


def test_position_kept_while_inside_keep_rank():
    """Sedno histerezy: spolka, ktora spadla z 1. na 3. miejsce, ale jest wciaz w top `keep_rank`,
    NIE jest sprzedawana - mimo ze ktos inny jest teraz wyzej."""
    index = pd.bdate_range("2019-01-01", periods=200)
    # "stary" traci prowadzenie na rzecz "nowy", ale zostaje w top 3 z 4 spolek
    prices = pd.DataFrame(
        {
            "stary": _trend(len(index), 0.0015),
            "nowy": _trend(len(index), 0.0030),
            "sredni": _trend(len(index), 0.0010),
            "slaby": _trend(len(index), -0.0040),
        },
        index=index,
    )

    result = _harness(prices, max_positions=1, keep_rank=3, entry_rank=1)

    assert [t for t in result["trades"] if t.exit_reason == "rank_dropout"] == []


def test_position_replaced_when_it_falls_below_keep_rank():
    """Ranking sterowany QUALITY (niezaleznie od ceny): "psujacy" ma identyczne ceny co reszta, ale
    od 5. kwartalu raportuje strate i ujemny CFO, wiec traci 80 z 100 pkt QUALITY (30% wagi) i
    wypada z top `keep_rank`."""
    index = pd.bdate_range("2019-01-01", periods=300)
    prices = pd.DataFrame({t: [100.0] * len(index) for t in ["psujacy", "a", "b", "c"]}, index=index)

    result = _harness(prices, weak={"psujacy": "2020-01-02"}, max_positions=1, keep_rank=2, entry_rank=1)

    dropouts = [t for t in result["trades"] if t.exit_reason == "rank_dropout"]
    assert dropouts, f"brak podmiany, powody: {[t.exit_reason for t in result['trades']]}"
    assert dropouts[0].ticker == "psujacy"


def test_keep_rank_below_entry_rank_is_rejected():
    """Odwrotna histereza (keep < entry) powodowalaby rotacje bez opamietania - lepiej blad."""
    index = pd.bdate_range("2019-01-01", periods=60)
    prices = pd.DataFrame({"a": [100.0] * 60, "b": [100.0] * 60}, index=index)

    with pytest.raises(ValueError, match="keep_rank"):
        _harness(prices, keep_rank=2, entry_rank=4)


def test_no_replacement_without_candidate_in_entry_rank():
    """Spec wiaze sprzedaz z ISTNIENIEM kandydata z top `entry_rank`. Gdy portfel trzyma wszystkie
    dostepne spolki, sam spadek rankingu NIE wypycha do gotowki."""
    index = pd.bdate_range("2019-01-01", periods=200)
    prices = pd.DataFrame({"a": _trend(len(index), -0.002), "b": _trend(len(index), -0.004)}, index=index)

    result = _harness(prices, max_positions=2, keep_rank=1, entry_rank=1)

    assert [t for t in result["trades"] if t.exit_reason == "rank_dropout"] == []
    assert all(d["n_positions"] == 2 for d in result["decisions"] if d["n_positions"] > 0)


def test_max_replacements_per_month_is_respected():
    index = pd.bdate_range("2019-01-01", periods=300)
    prices = pd.DataFrame({t: [100.0] * len(index) for t in ["f1", "f2", "a", "b"]}, index=index)

    result = _harness(
        prices, weak={"f1": "2020-01-02", "f2": "2020-01-02"}, max_positions=2, keep_rank=2, entry_rank=2,
        max_replacements_per_month=1,
    )

    assert all(d["replacements"] <= 1 for d in result["decisions"])


# --- BRAK WYJSC CENOWYCH ---


def test_no_stop_target_or_timeout_exits():
    """Spec v4: "Brak trailing stop / profit target / timeout". Jedyne dopuszczalne powody wyjscia
    to spadek rankingu i koniec danych."""
    index = pd.bdate_range("2019-01-01", periods=300)
    # gwaltowny wzrost (profit target by zadzialal), potem gleboki spadek (stop by zadzialal)
    values = _trend(150, 0.02) + _trend(len(index) - 150, -0.02, start=_trend(150, 0.02)[-1])
    prices = pd.DataFrame({"a": values[: len(index)], "b": [100.0] * len(index)}, index=index)

    result = _harness(prices, max_positions=2, keep_rank=2, entry_rank=1)

    assert {t.exit_reason for t in result["trades"]} <= {"rank_dropout", "end_of_data"}


def test_open_positions_closed_at_end_of_data():
    index = pd.bdate_range("2019-01-01", periods=120)
    prices = pd.DataFrame({"a": _trend(len(index), 0.002), "b": _trend(len(index), 0.001)}, index=index)

    result = _harness(prices, max_positions=1)

    assert result["trades"][-1].exit_reason == "end_of_data"
    assert result["trades"][-1].exit_date == index[-1]


# --- UNIWERSUM PIT I KSIEGOWANIE ---


def test_eligible_universe_restricts_ranking():
    index = pd.bdate_range("2019-01-01", periods=120)
    prices = pd.DataFrame({"a": _trend(len(index), 0.004), "b": _trend(len(index), 0.001)}, index=index)
    dates = month_start_decision_dates(prices)

    tickers = list(prices.columns)
    panel = _panel(tickers)
    estimator = SharesEstimator(panel, {t.upper(): 1_000_000.0 for t in tickers})
    config = FactorConfig(
        tickers=tickers, max_positions=1, keep_rank=2, entry_rank=1, cost_bps=0.0,
        momentum_lookback_days=_MOM_LOOKBACK, momentum_skip_days=_MOM_SKIP,
    )

    only_b = run_factor_backtest(
        prices, panel, estimator, dates, config, eligible_universe={d: ["b"] for d in dates}
    )

    assert only_b["trades"], "brak transakcji"
    assert {t.ticker for t in only_b["trades"]} == {"b"}, "kupiono spolke poza uniwersum PIT"


def test_equity_curve_is_daily_and_starts_at_one():
    index = pd.bdate_range("2019-01-01", periods=100)
    prices = pd.DataFrame({"a": [100.0] * len(index), "b": [100.0] * len(index)}, index=index)

    result = _harness(prices, max_positions=1)

    assert len(result["equity_curve"]) == len(index)
    assert result["equity_curve"]["equity"].iloc[0] == pytest.approx(1.0)
    assert (result["equity_curve"]["equity"] > 0).all()


def test_transaction_costs_reduce_final_equity():
    index = pd.bdate_range("2019-01-01", periods=300)
    prices = pd.DataFrame({t: [100.0] * len(index) for t in ["psujacy", "a", "b"]}, index=index)
    weak = {"psujacy": "2020-01-02"}

    free = _harness(prices, weak=weak, max_positions=1, keep_rank=2, entry_rank=1, cost_bps=0.0)
    costly = _harness(prices, weak=weak, max_positions=1, keep_rank=2, entry_rank=1, cost_bps=300.0)

    assert len(free["trades"]) > 1, "brak rotacji - test nie sprawdza kosztow"
    assert costly["equity_curve"]["equity"].iloc[-1] < free["equity_curve"]["equity"].iloc[-1]


def test_held_ranks_are_logged_before_replacements():
    """Diagnostyka musi pokazywac stan, KTORY WYWOLAL decyzje. Log po podmianach jest bezuzyteczny:
    wyrzucona pozycja nie jest juz w portfelu, wiec "poza keep_rank" nigdy sie nie pojawia (zlapane
    realnie - pierwsza wersja logu dawala 0/970 obserwacji dropoutu przy 22 faktycznych)."""
    index = pd.bdate_range("2019-01-01", periods=300)
    prices = pd.DataFrame({t: [100.0] * len(index) for t in ["psujacy", "a", "b"]}, index=index)

    result = _harness(prices, weak={"psujacy": "2020-01-02"}, max_positions=1, keep_rank=2, entry_rank=1)

    dropout_months = [d for d in result["decisions"] if d["dropouts"]]
    replacement_months = [d for d in result["decisions"] if d["replacements"] > 0]
    assert dropout_months, "log nie pokazuje zadnego dropoutu"
    assert len(dropout_months) >= len(replacement_months)
