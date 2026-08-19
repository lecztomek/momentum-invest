"""
Testy SIGNALS + BACKTEST (silnik pojedynczych transakcji).

Wszystkie na w pelni syntetycznych, recznie policzonych danych - zeby sprawdzac MECHANIKE
(warunki wyjscia, kolejnosc wyjscia-przed-wejsciem, limit pozycji, konserwatywny filtr
fundamentalny), a nie akurat panujace warunki rynkowe.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_backtest.py -v
"""

import pandas as pd
import pytest

from value_engine.backtest import StrategyConfig, check_health, run_backtest
from value_engine.br_parser import ParsedReport
from value_engine.fundamentals import FundamentalPanel
from value_engine.signals import drawdown_from_rolling_high, month_start_decision_dates


def _healthy_panel(tickers, value=100.0, cashflow=50.0, debt=10.0) -> FundamentalPanel:
    """Panel, w ktorym kazda spolka jest "zdrowa" i w pelni znana od 2019-01-01.

    OSIEM kwartalow, nie cztery: kontrola trendu zadluzenia porownuje poziom biezacy z poziomem
    sprzed 4 kwartalow, wiec potrzebuje co najmniej 5 obserwacji - przy 4 zwracalaby None, czyli
    "brak danych" -> "nie zdrowa", i wszystkie testy wejsc bylyby fałszywie negatywne."""
    periods = [f"2017/Q{q} (x)" for q in (1, 2, 3, 4)] + [f"2018/Q{q} (x)" for q in (1, 2, 3, 4)]
    dates = [
        "2017-05-01", "2017-08-01", "2017-11-01", "2018-01-02",
        "2018-05-01", "2018-08-01", "2018-11-01", "2019-01-01",
    ]
    reports = []
    for ticker in tickers:
        reports.append(
            ParsedReport(
                ticker=ticker,
                report_type="mixed",
                periodicity="quarterly",
                periods=periods,
                publication_dates=dates,
                metrics={
                    "IncomeNetProfit": [value] * 8,
                    "CashflowOperatingCashflow": [cashflow] * 8,
                    "BalanceNoncurrentLiabilities": [debt] * 8,
                },
            )
        )
    return FundamentalPanel.from_reports(reports)


# --- SIGNALS ---


def test_drawdown_is_zero_at_new_high_and_negative_below():
    index = pd.bdate_range("2020-01-01", periods=10)
    prices = pd.DataFrame({"a": [10, 11, 12, 12, 9, 6, 6, 6, 6, 6]}, index=index, dtype=float)

    drawdown = drawdown_from_rolling_high(prices, lookback_trading_days=3)

    assert pd.isna(drawdown["a"].iloc[0])  # niepelne okno -> NaN, nie liczymy z 1 dnia
    assert drawdown["a"].iloc[2] == pytest.approx(0.0)  # nowy szczyt
    assert drawdown["a"].iloc[4] == pytest.approx(9 / 12 - 1)  # 25% ponizej szczytu z okna


def test_drawdown_requires_full_lookback_window():
    """Bez tego swiezo notowana spolka miala by sztucznie male obsuniecie (szczyt z kilku dni)."""
    index = pd.bdate_range("2020-01-01", periods=5)
    prices = pd.DataFrame({"a": [10, 9, 8, 7, 6]}, index=index, dtype=float)

    drawdown = drawdown_from_rolling_high(prices, lookback_trading_days=4)

    assert drawdown["a"].iloc[:3].isna().all()
    assert not pd.isna(drawdown["a"].iloc[3])


def test_month_start_decision_dates_picks_first_trading_day():
    index = pd.bdate_range("2020-01-01", "2020-03-31")
    dates = month_start_decision_dates(pd.DataFrame(index=index))

    assert dates[0] == pd.Timestamp("2020-01-01")
    assert dates[1] == pd.Timestamp("2020-02-03")  # 1 i 2 lutego 2020 to weekend
    assert dates[2] == pd.Timestamp("2020-03-02")


# --- FILTR FUNDAMENTALNY ---


def test_health_requires_positive_profit_and_cashflow():
    config = StrategyConfig(tickers=["a"])
    as_of = pd.Timestamp("2019-06-01")

    assert check_health(_healthy_panel(["A"]), "A", as_of, config).healthy
    assert not check_health(_healthy_panel(["A"], value=-1.0), "A", as_of, config).healthy
    assert not check_health(_healthy_panel(["A"], cashflow=-1.0), "A", as_of, config).healthy


def test_health_is_false_when_fundamentals_unknown():
    """Konserwatywnie: brak danych = nie kupujemy. Traktowanie braku jako "OK" wpuszczaloby
    spolki w okresie, w ktorym strategia nie miala o nich zadnej informacji."""
    config = StrategyConfig(tickers=["a"])
    panel = _healthy_panel(["A"])

    # przed PIERWSZA publikacja (najstarsza w fixture: 2017-05-01) nie wiadomo nic
    assert not check_health(panel, "A", pd.Timestamp("2017-01-01"), config).healthy
    # w trakcie: sa juz 3 kwartaly, ale TTM wymaga 4 -> wciaz "nie wiemy"
    assert not check_health(panel, "A", pd.Timestamp("2017-12-01"), config).healthy
    assert not check_health(panel, "NIEZNANA", pd.Timestamp("2019-06-01"), config).healthy


def test_health_rejects_fast_growing_debt():
    periods = [f"2018/Q{q} (x)" for q in (1, 2, 3, 4)] + ["2019/Q1 (x)"]
    dates = ["2018-05-01", "2018-08-01", "2018-11-01", "2019-01-01", "2019-05-01"]
    panel = FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="quarterly",
                periods=periods,
                publication_dates=dates,
                metrics={
                    "IncomeNetProfit": [100.0] * 5,
                    "CashflowOperatingCashflow": [50.0] * 5,
                    "BalanceNoncurrentLiabilities": [100.0, 100.0, 100.0, 100.0, 200.0],  # +100% r/r
                },
            )
        ]
    )
    config = StrategyConfig(tickers=["a"], max_debt_growth=0.30)
    health = check_health(panel, "A", pd.Timestamp("2019-05-01"), config)

    assert not health.healthy
    assert health.reasons["debt_growth"] == pytest.approx(1.0)


# --- SILNIK TRANSAKCYJNY ---


_LOOKBACK = 40  # musi byc DLUZSZE niz odstep miedzy datami decyzyjnymi (~21 dni handlowych),
# inaczej szczyt wypada z okna przed najblizsza data decyzyjna i obsuniecie "zdrowieje" do 0
# (poprawne zachowanie wskaznika, ale wtedy dane testowe nigdy nie wyzwalaja wejscia).


def _run(prices: pd.DataFrame, config: StrategyConfig, panel=None, lookback: int = _LOOKBACK):
    drawdown = drawdown_from_rolling_high(prices, lookback_trading_days=lookback)
    panel = panel or _healthy_panel([t.upper() for t in config.tickers])
    return run_backtest(prices, drawdown, panel, month_start_decision_dates(prices), config)


def _crash_then_rebound(n: int) -> list:
    """30 dni na 100 (napelnia okno), potem spadek do 50, potem odbicie do 70 (+40% od wejscia)."""
    return ([100.0] * 30 + [50.0] * 21 + [70.0] * n)[:n]


def _crash_and_stay(n: int) -> list:
    return ([100.0] * 30 + [50.0] * n)[:n]


def test_exit_on_target_gain():
    index = pd.bdate_range("2019-01-01", periods=90)
    prices = pd.DataFrame({"a": _crash_then_rebound(len(index))}, index=index)

    result = _run(prices, StrategyConfig(tickers=["a"], min_drawdown=-0.25, exit_gain=0.20, max_holding_months=99))
    trades = result["trades"]

    assert len(trades) == 1
    assert trades[0].exit_reason == "target"
    assert trades[0].entry_price == pytest.approx(50.0)
    assert trades[0].gross_return == pytest.approx(70 / 50 - 1)


def test_exit_on_timeout_when_no_rebound():
    index = pd.bdate_range("2019-01-01", periods=200)
    prices = pd.DataFrame({"a": _crash_and_stay(len(index))}, index=index)

    result = _run(prices, StrategyConfig(tickers=["a"], min_drawdown=-0.25, exit_gain=0.99, max_holding_months=3))
    trades = result["trades"]

    assert trades, "brak transakcji - strategia nie weszla"
    assert trades[0].exit_reason == "timeout"
    months_held = (trades[0].exit_date.year - trades[0].entry_date.year) * 12 + (
        trades[0].exit_date.month - trades[0].entry_date.month
    )
    assert months_held == 3


def test_respects_max_positions():
    index = pd.bdate_range("2019-01-01", periods=120)
    tickers = ["a", "b", "c", "d"]
    prices = pd.DataFrame({t: _crash_and_stay(len(index)) for t in tickers}, index=index)

    result = _run(
        prices,
        StrategyConfig(tickers=tickers, max_positions=2, min_drawdown=-0.25, exit_gain=0.99, max_holding_months=99),
    )

    assert max(d["n_positions"] for d in result["decisions"]) == 2  # limit osiagniety
    for decision in result["decisions"]:
        assert decision["n_positions"] <= 2  # i nigdy nie przekroczony


def test_most_oversold_candidate_is_picked_first():
    """Ranking: "sposrod zdrowych i przecenionych wybieramy najbardziej przecenione"."""
    index = pd.bdate_range("2019-01-01", periods=90)
    deep = ([100.0] * 30 + [30.0] * 60)[: len(index)]  # -70%
    shallow = ([100.0] * 30 + [70.0] * 60)[: len(index)]  # -30%
    prices = pd.DataFrame({"deep": deep, "shallow": shallow}, index=index)

    result = _run(
        prices,
        StrategyConfig(
            tickers=["deep", "shallow"], max_positions=1, min_drawdown=-0.25, exit_gain=0.99, max_holding_months=99
        ),
    )

    held = [d["held"] for d in result["decisions"] if d["n_positions"] > 0]
    assert held and all(h == ["deep"] for h in held)


def test_exits_run_before_entries_so_freed_slot_is_reusable():
    """Kolejnosc w dniu decyzyjnym: najpierw wyjscia, potem wejscia. Gdyby bylo odwrotnie,
    zwolniony slot czekalby bezczynnie caly miesiac."""
    index = pd.bdate_range("2019-01-01", periods=90)
    # "a": spadek i odbicie -> wyjdzie na target. "b": ciagly zjazd 1%/dzien, wiec jej obsuniecie
    # NIE zdrowieje (szczyt sprzed 40 dni zawsze wyzej) - czeka na zwolniony slot.
    a = _crash_then_rebound(len(index))
    b = [100.0 * (0.99**i) for i in range(len(index))]
    prices = pd.DataFrame({"a": a, "b": b}, index=index)

    result = _run(
        prices,
        StrategyConfig(tickers=["a", "b"], max_positions=1, min_drawdown=-0.25, exit_gain=0.20, max_holding_months=99),
    )

    exit_dates = {t.exit_date for t in result["trades"]}
    assert exit_dates, "brak wyjscia - test nie sprawdza tego, co powinien"
    reused = [d for d in result["decisions"] if d["date"] in exit_dates and d["held"] == ["b"]]
    assert reused, "zwolniony slot nie zostal uzyty w tym samym dniu decyzyjnym"


def test_no_entry_when_fundamentals_unhealthy():
    index = pd.bdate_range("2019-01-01", periods=90)
    prices = pd.DataFrame({"a": _crash_and_stay(len(index))}, index=index)

    result = _run(
        prices,
        StrategyConfig(tickers=["a"], min_drawdown=-0.25),
        panel=_healthy_panel(["A"], value=-5.0),  # strata netto
    )

    assert result["trades"] == []
    assert all(d["n_positions"] == 0 for d in result["decisions"])


def test_equity_curve_is_daily_and_starts_at_one():
    index = pd.bdate_range("2019-01-01", periods=60)
    prices = pd.DataFrame({"a": [100.0] * len(index)}, index=index)

    result = _run(prices, StrategyConfig(tickers=["a"], min_drawdown=-0.25))
    equity_curve = result["equity_curve"]

    assert len(equity_curve) == len(index)  # dzienna, nie miesieczna
    assert equity_curve["equity"].iloc[0] == pytest.approx(1.0)
    assert list(equity_curve.columns) == ["date", "equity"]


def test_transaction_cost_reduces_equity_on_round_trip():
    index = pd.bdate_range("2019-01-01", periods=90)
    prices = pd.DataFrame({"a": _crash_then_rebound(len(index))}, index=index)

    cheap = _run(prices, StrategyConfig(tickers=["a"], min_drawdown=-0.25, exit_gain=0.20, cost_bps=0.0))
    pricey = _run(prices, StrategyConfig(tickers=["a"], min_drawdown=-0.25, exit_gain=0.20, cost_bps=100.0))

    assert cheap["trades"], "brak transakcji - test nie sprawdza kosztow"
    assert pricey["equity_curve"]["equity"].iloc[-1] < cheap["equity_curve"]["equity"].iloc[-1]


def test_max_positions_zero_is_rejected():
    index = pd.bdate_range("2019-01-01", periods=10)
    prices = pd.DataFrame({"a": [100.0] * 10}, index=index)
    with pytest.raises(ValueError, match="max_positions"):
        _run(prices, StrategyConfig(tickers=["a"], max_positions=0))
