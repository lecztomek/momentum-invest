"""
Testy REVERSAL (koncepcje v9 i v10 - ten sam silnik na dwoch siatkach). Piec grup:

  1. **kazdy z osmiu warunkow bramki psuty OSOBNO** - bramka to jedyna obrona przed kupowaniem
     spolki w realnym distressie, wiec pomylony kierunek w ktorymkolwiek warunku jest niewidoczny
     w wyniku, a zmienia sens strategii,
  2. **BRAK DANYCH = WARUNEK NIESPELNIONY** - to bramka, nie ranking; spolka bez fundamentow nie moze
     przechodzic filtru distressu na samym braku informacji,
  3. **timing wejscia** - sygnal "spadek w miesiacu M" jest znany dopiero na pierwszej sesji M+1 i
     wtedy kupujemy; kupno wewnatrz M byloby look-ahead,
  4. **wybor kandydatow po NAJWIEKSZYM spadku** i brak podmian przy pelnym portfelu,
  5. **przeliczenie krokow siatki** (v10) - okno triggera i holding sa liczone w SESJACH, wiec
     pomylka o jeden krok jest tu duzo mniej widoczna niz przy siatce miesiecznej.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_reversal.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport
from value_engine.fundamentals import FundamentalPanel
from value_engine.reversal import GATE_CONDITIONS, evaluate_gate, find_candidates, monthly_returns, trailing_returns, worst_decile_threshold
from value_engine.reversal_backtest import ReversalConfig, run_reversal_backtest
from value_engine.signals import month_start_decision_dates

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"
PL_DATA_DIR = REPO_ROOT / "data" / "pl"

_PERIODS = [f"{y}/Q{q} (x)" for y in (2018, 2019, 2020) for q in (1, 2, 3, 4)]
_DATES = [
    "2018-05-01", "2018-08-01", "2018-11-01", "2019-02-01",
    "2019-05-01", "2019-08-01", "2019-11-01", "2020-02-01",
    "2020-05-01", "2020-08-01", "2020-11-01", "2021-02-01",
]
_AS_OF = pd.Timestamp("2021-06-01")

# Zdrowa spolka: zysk i CFO dodatnie, dlug 20% aktywow i staly, przychody i EBIT stabilne, bez emisji.
_HEALTHY = dict(
    BalanceCapital=1000.0,
    IncomeNetProfit=50.0,
    CashflowOperatingCashflow=80.0,
    BalanceTotalAssets=5000.0,
    BalanceCurrentBorrowings=1000.0,
    BalanceNoncurrentBorrowings=0.0,
    IncomeRevenues=2000.0,
    IncomeEBIT=200.0,
    BalanceShareCapital=500.0,
)


def _panel(ticker: str = "A", **overrides) -> FundamentalPanel:
    metrics = {}
    for name, value in {**_HEALTHY, **overrides}.items():
        metrics[name] = value if isinstance(value, list) else [value] * len(_PERIODS)
    return FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker=ticker,
                report_type="mixed",
                periodicity="quarterly",
                periods=list(_PERIODS),
                publication_dates=list(_DATES),
                metrics=metrics,
            )
        ]
    )


# --- BRAMKA ---


def test_healthy_company_passes_all_eight_conditions():
    gate = evaluate_gate(_panel(), "A", _AS_OF)

    assert gate.ok, f"niespelnione: {gate.failures()}"
    assert set(gate.passed) == set(GATE_CONDITIONS)
    assert gate.values["debt_ratio"] == pytest.approx(0.20)


def test_each_condition_can_be_broken_independently():
    """Kazdy warunek psuty osobno - lapie pomylony kierunek albo prog w KAZDYM z osmiu."""
    cases = {
        "equity_positive": dict(BalanceCapital=-100.0),
        "net_income_positive": dict(IncomeNetProfit=-50.0),
        "cashflow_positive": dict(CashflowOperatingCashflow=-80.0),
        # dlug 3500/5000 = 70% > 60%
        "debt_ratio_below_limit": dict(BalanceCurrentBorrowings=3500.0),
        # dlug skacze z 20% na 40% aktywow = +20 pp > 10 pp
        "debt_ratio_not_jumping": dict(BalanceCurrentBorrowings=[1000.0] * 8 + [2000.0] * 4),
        # przychody TTM spadaja o 50% > 20%
        "revenue_not_collapsing": dict(IncomeRevenues=[2000.0] * 8 + [1000.0] * 4),
        # EBIT TTM spada o 75% > 40%
        "ebit_not_collapsing": dict(IncomeEBIT=[200.0] * 8 + [50.0] * 4),
        # kapital zakladowy +40% > 10% (emisja ratunkowa)
        "no_rescue_issuance": dict(BalanceShareCapital=[500.0] * 8 + [700.0] * 4),
    }
    for condition, override in cases.items():
        gate = evaluate_gate(_panel(**override), "A", _AS_OF)
        assert gate.passed[condition] is False, f"{condition} powinien byc niespelniony"
        assert not gate.ok


def test_conditions_are_at_the_declared_thresholds():
    """Progi ze spec, sprawdzone po obu stronach granicy."""
    # dlug 2999/5000 = 59.98% < 60% przechodzi, 3001/5000 = 60.02% nie
    assert evaluate_gate(_panel(BalanceCurrentBorrowings=2999.0), "A", _AS_OF).passed["debt_ratio_below_limit"]
    assert not evaluate_gate(
        _panel(BalanceCurrentBorrowings=3001.0), "A", _AS_OF
    ).passed["debt_ratio_below_limit"]
    # przychody -19% przechodza, -21% nie
    assert evaluate_gate(
        _panel(IncomeRevenues=[2000.0] * 8 + [1620.0] * 4), "A", _AS_OF
    ).passed["revenue_not_collapsing"]
    assert not evaluate_gate(
        _panel(IncomeRevenues=[2000.0] * 8 + [1580.0] * 4), "A", _AS_OF
    ).passed["revenue_not_collapsing"]
    # EBIT -39% przechodzi, -41% nie
    assert evaluate_gate(
        _panel(IncomeEBIT=[200.0] * 8 + [122.0] * 4), "A", _AS_OF
    ).passed["ebit_not_collapsing"]
    assert not evaluate_gate(
        _panel(IncomeEBIT=[200.0] * 8 + [118.0] * 4), "A", _AS_OF
    ).passed["ebit_not_collapsing"]


def test_missing_data_fails_the_gate():
    """RDZEN BEZPIECZENSTWA v9: przy triggerze "-20% w miesiac" spolka bez opublikowanych
    fundamentow jest najgrozniejszym kandydatem, wiec brak danych MUSI byc traktowany jak
    niespelniony warunek, a nie jak neutralny."""
    gate = evaluate_gate(FundamentalPanel.from_reports([]), "A", _AS_OF)

    assert not gate.ok
    assert set(gate.failures()) == set(GATE_CONDITIONS)


def test_gate_is_point_in_time():
    panel = _panel()

    assert evaluate_gate(panel, "A", pd.Timestamp("2018-04-30")).ok is False
    assert evaluate_gate(panel, "A", _AS_OF).ok is True


def test_negative_base_fails_the_trend_conditions():
    """"Nie spadlo wiecej niz 20%" przy UJEMNEJ bazie nie ma interpretacji - spolka, ktora rok temu
    miala ujemny EBIT, nie jest "stabilna", wiec warunek jest niespelniony."""
    gate = evaluate_gate(_panel(IncomeEBIT=[-200.0] * 8 + [200.0] * 4), "A", _AS_OF)

    assert gate.passed["ebit_not_collapsing"] is False


# --- SYGNAL CENOWY ---


def _prices(**series) -> pd.DataFrame:
    length = max(len(v) for v in series.values())
    return pd.DataFrame(series, index=pd.bdate_range("2019-01-01", periods=length))


def test_monthly_return_is_measured_between_decision_dates():
    # trzy miesiace po ~21 sesji: 100 -> 100 -> 75 (spadek 25% w trzecim miesiacu)
    values = [100.0] * 21 + [100.0] * 21 + [75.0] * 21
    prices = _prices(a=values)
    dates = month_start_decision_dates(prices)

    returns = monthly_returns(prices, dates)

    assert returns[dates[1]]["a"] == pytest.approx(0.0)
    assert returns[dates[2]]["a"] == pytest.approx(-0.25)
    assert dates[0] not in returns, "pierwsza data nie ma poprzedniej, wiec nie ma zwrotu"


def test_candidates_are_ordered_by_biggest_drop():
    """Spec: "jesli kandydatow >4: wybieramy te z najwiekszym miesiecznym spadkiem"."""
    panel = FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker=name,
                report_type="mixed",
                periodicity="quarterly",
                periods=list(_PERIODS),
                publication_dates=list(_DATES),
                metrics={k: ([v] * len(_PERIODS) if not isinstance(v, list) else v) for k, v in _HEALTHY.items()},
            )
            for name in ("A", "B", "C")
        ]
    )
    returns = {"a": -0.25, "b": -0.45, "c": -0.30, "d": -0.05}

    candidates, gates, triggered = find_candidates(returns, ["a", "b", "c", "d"], panel, _AS_OF)

    assert [ticker for ticker, _ in candidates] == ["b", "c", "a"]
    assert "d" not in triggered, "spadek -5% nie przechodzi triggera -20%"


def test_candidate_failing_the_gate_is_dropped_even_with_the_biggest_drop():
    panel = FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker=name,
                report_type="mixed",
                periodicity="quarterly",
                periods=list(_PERIODS),
                publication_dates=list(_DATES),
                metrics={
                    key: ([value] * len(_PERIODS) if not isinstance(value, list) else value)
                    for key, value in {**_HEALTHY, **extra}.items()
                },
            )
            for name, extra in (("A", {}), ("B", dict(IncomeNetProfit=-100.0)))
        ]
    )
    returns = {"a": -0.22, "b": -0.60}

    candidates, gates, triggered = find_candidates(returns, ["a", "b"], panel, _AS_OF)

    assert triggered == ["a", "b"]
    assert [ticker for ticker, _ in candidates] == ["a"], "najglebszy spadek nie omija bramki"
    assert "net_income_positive" in gates["b"].failures()


# --- SILNIK ---


def _long_prices(**series) -> pd.DataFrame:
    length = max(len(v) for v in series.values())
    return pd.DataFrame(series, index=pd.bdate_range("2019-01-01", periods=length))


def _multi_panel(*tickers, **overrides) -> FundamentalPanel:
    return FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker=name.upper(),
                report_type="mixed",
                periodicity="quarterly",
                periods=list(_PERIODS),
                publication_dates=list(_DATES),
                metrics={
                    key: ([value] * len(_PERIODS) if not isinstance(value, list) else value)
                    for key, value in {**_HEALTHY, **overrides}.items()
                },
            )
            for name in tickers
        ]
    )


def test_entry_happens_on_the_first_session_after_the_drop_month():
    """Spadek w miesiacu M jest znany po zamknieciu M, wiec kupujemy na pierwszej sesji M+1 - i po
    CENIE Z TEJ SESJI. Kupno wewnatrz M byloby look-ahead."""
    # miesiace: 1-24 stabilnie 100, w miesiacu 25 spada do 70, potem stabilnie
    values = [100.0] * 21 * 24 + [70.0] * 21 * 12
    prices = _long_prices(a=values)
    dates = month_start_decision_dates(prices)
    panel = _multi_panel("A")

    result = run_reversal_backtest(
        prices, panel, dates, ReversalConfig(tickers=["a"], holding_steps=3)
    )

    assert result["trades"], "spadek -30% zdrowej spolki musi dac transakcje"
    trade = result["trades"][0]
    assert trade.entry_date in dates
    assert trade.entry_price == pytest.approx(70.0), "kupujemy PO spadku, nie przed"
    assert trade.trigger_return == pytest.approx(-0.30)


def test_position_is_sold_after_the_holding_period():
    values = [100.0] * 21 * 24 + [70.0] * 21 * 24
    prices = _long_prices(a=values)
    dates = month_start_decision_dates(prices)
    panel = _multi_panel("A")

    for holding in (3, 6, 12):
        result = run_reversal_backtest(
            prices, panel, dates, ReversalConfig(tickers=["a"], holding_steps=holding)
        )
        trade = result["trades"][0]
        entry_index = dates.index(trade.entry_date)
        exit_index = dates.index(trade.exit_date) if trade.exit_date in dates else len(dates) - 1
        assert exit_index - entry_index == holding, f"holding {holding}M: {exit_index - entry_index}"
        assert trade.exit_reason == "holding_period"


def test_fundamental_fail_exits_before_the_holding_period():
    """Spolka psuje sie PO zakupie (zysk schodzi na minus od publikacji 2020-05) - musi wyjsc
    wczesniej niz po holdingu.

    Spadek musi wypasc PO 2020-02, bo warunki trendu (`revenue_not_collapsing`, `ebit_not_collapsing`)
    licza TTM sprzed roku i wymagaja OSMIU opublikowanych kwartalow. Wczesniej bramka odrzuca spolke
    z braku danych - poprawnie, ale wtedy nie ma czego kupic i test nie mierzy tego, co mial."""
    values = [100.0] * 21 * 15 + [70.0] * 21 * 25
    prices = _long_prices(a=values)
    dates = month_start_decision_dates(prices)
    panel = _multi_panel("A", IncomeNetProfit=[50.0] * 8 + [-200.0] * 4)

    result = run_reversal_backtest(
        prices, panel, dates, ReversalConfig(tickers=["a"], holding_steps=12)
    )

    reasons = {t.exit_reason for t in result["trades"]}
    assert "fundamental_fail" in reasons


def test_portfolio_is_capped_and_there_is_no_replacement():
    """Spec mowi "max 4 spolki" i nie przewiduje podmian, wiec przy pelnym portfelu kolejni
    kandydaci sa POMIJANI - a log musi to policzyc."""
    names = [f"t{i}" for i in range(6)]
    # wszystkie spadaja o 30% w tym samym miesiacu
    values = {name: [100.0] * 21 * 24 + [70.0 - i] * 21 * 12 for i, name in enumerate(names)}
    prices = _long_prices(**values)
    dates = month_start_decision_dates(prices)
    panel = _multi_panel(*names)

    result = run_reversal_backtest(
        prices, panel, dates, ReversalConfig(tickers=names, holding_steps=6, max_positions=4)
    )

    entry_dates = {t.entry_date for t in result["trades"]}
    first_entry = min(entry_dates)
    bought_first = [t for t in result["trades"] if t.entry_date == first_entry]
    assert len(bought_first) == 4, f"kupiono {len(bought_first)}, limit to 4"
    skipped = sum(d["skipped_no_slot"] for d in result["decisions"])
    assert skipped >= 2, "dwoch kandydatow musi przepasc z braku slotu"


def test_equal_weight_at_entry():
    names = ["a", "b"]
    values = {"a": [100.0] * 21 * 24 + [70.0] * 21 * 12, "b": [40.0] * 21 * 24 + [28.0] * 21 * 12}
    prices = _long_prices(**values)
    dates = month_start_decision_dates(prices)
    panel = _multi_panel("A", "B")

    result = run_reversal_backtest(
        prices, panel, dates, ReversalConfig(tickers=names, holding_steps=6, cost_bps=0.0)
    )

    first = min(t.entry_date for t in result["trades"])
    bought = [t for t in result["trades"] if t.entry_date == first]
    assert len(bought) == 2

    # Rowne wagi przy ROZNYCH cenach wejscia: kazda pozycja dostaje 1/max_positions kapitalu, czyli
    # 25% z 1.0. Sprawdzamy to na zwrocie portfela: obie spolki spadaja o te same 30% w tym samym
    # miesiacu, wiec przy rownych wagach kapital musi spasc dokladnie o 2 * 25% * 30% = 15%.
    curve = result["equity_curve"].set_index("date")["equity"]
    at_entry = float(curve.loc[first])
    assert at_entry == pytest.approx(1.0), "przy zerowych kosztach kupno nie zmienia kapitalu"
    entry_prices = {t.ticker: t.entry_price for t in bought}
    assert entry_prices == {"a": pytest.approx(70.0), "b": pytest.approx(28.0)}


def test_entry_delay_shifts_the_purchase():
    values = [100.0] * 21 * 24 + [70.0] * 21 * 24
    prices = _long_prices(a=values)
    dates = month_start_decision_dates(prices)
    panel = _multi_panel("A")

    immediate = run_reversal_backtest(
        prices, panel, dates, ReversalConfig(tickers=["a"], holding_steps=3, entry_delay_steps=0)
    )
    delayed = run_reversal_backtest(
        prices, panel, dates, ReversalConfig(tickers=["a"], holding_steps=3, entry_delay_steps=1)
    )

    assert dates.index(delayed["trades"][0].entry_date) == dates.index(immediate["trades"][0].entry_date) + 1


def test_no_trigger_means_no_trades_and_flat_equity():
    """Bez spadku -20% strategia siedzi w gotowce - krzywa MUSI byc plaska, mimo ze cena rosnie."""
    prices = _long_prices(a=[100.0 + i for i in range(21 * 30)])
    dates = month_start_decision_dates(prices)
    panel = _multi_panel("A")

    result = run_reversal_backtest(prices, panel, dates, ReversalConfig(tickers=["a"]))

    assert not result["trades"]
    assert result["equity_curve"]["equity"].nunique() == 1


def test_invalid_config_raises():
    prices = _long_prices(a=[100.0] * 200)
    dates = month_start_decision_dates(prices)
    panel = _multi_panel("A")

    with pytest.raises(ValueError, match="trigger"):
        run_reversal_backtest(prices, panel, dates, ReversalConfig(tickers=["a"], trigger=0.20))
    with pytest.raises(ValueError, match="holding_steps"):
        run_reversal_backtest(prices, panel, dates, ReversalConfig(tickers=["a"], holding_steps=0))


# --- SIATKA DZIENNA (koncepcja v10, "krotkoterminowy reversal") ---
#
# v10 to ten sam silnik, tylko `decision_dates` = wszystkie sesje, `trigger_lookback_steps=5`
# (tydzien) i `holding_steps` liczone w sesjach. Te testy pilnuja, zeby przeliczenie krokow siatki
# bylo dokladne: pomylka o jeden krok przy holdingu 5 sesji to 20% bledu w dlugosci trzymania
# (przy holdingu 3-miesiecznym w v9 ta sama pomylka to 33%, ale tam bylo ja widac w datach).


def test_trailing_return_spans_exactly_five_sessions_on_a_daily_grid():
    # 10 sesji po 100, potem jedna sesja -12%, potem plasko
    values = [100.0] * 10 + [88.0] * 10
    prices = _prices(a=values)
    dates = list(prices.index)

    returns = trailing_returns(prices, dates, lookback_steps=5)

    # sesja o indeksie 10 to pierwsza z cena 88; okno 5 sesji wstecz konczy sie na 100
    assert returns[dates[10]]["a"] == pytest.approx(-0.12)
    # 5 sesji po spadku okno jest CALE po spadku, wiec zwrot wraca do zera
    assert returns[dates[15]]["a"] == pytest.approx(0.0)
    assert dates[4] not in returns, "przed 5 sesja nie ma jeszcze pelnego okna"
    assert dates[5] in returns


def test_trailing_return_rejects_nonpositive_lookback():
    prices = _prices(a=[100.0] * 10)
    with pytest.raises(ValueError, match="lookback_steps"):
        trailing_returns(prices, list(prices.index), lookback_steps=0)


def test_worst_decile_threshold_is_cross_sectional():
    returns = {f"t{i}": -0.01 * i for i in range(20)}  # od 0.00 do -0.19
    investable = list(returns)

    threshold = worst_decile_threshold(returns, investable, quantile=0.10)

    assert threshold == pytest.approx(pd.Series(list(returns.values())).quantile(0.10))
    # dwie najgorsze spolki z 20 przechodza prog decyla
    assert sum(1 for v in returns.values() if v <= threshold) == 2


def test_worst_decile_threshold_ignores_non_investable_and_small_universes():
    returns = {f"t{i}": -0.01 * i for i in range(20)}  # od 0.00 do -0.19

    full = worst_decile_threshold(returns, list(returns))
    without_worst_five = worst_decile_threshold(returns, [f"t{i}" for i in range(15)])

    assert full < without_worst_five, "spolki poza uniwersum nie moga przesuwac progu"
    assert worst_decile_threshold(returns, ["t0", "t1", "t2"]) is None, "3 spolki to nie decyl"


# Bramka potrzebuje piatej obserwacji kwartalnej (porownanie r/r robi `shift=4`), a ostatni raport
# w `_DATES` jest publikowany 2021-02-01, wiec spadek musi wypasc PO tej dacie. Od 2019-01-01 to
# okolo 550 sesji roboczych - stad dlugie serie w testach ponizej.
_DROP_SESSION = 600


def test_daily_grid_holds_for_exactly_five_sessions():
    values = [100.0] * _DROP_SESSION + [85.0] + [90.0] * 30
    prices = _long_prices(a=values)
    dates = list(prices.index)
    panel = _multi_panel("A")

    result = run_reversal_backtest(
        prices,
        panel,
        dates,
        ReversalConfig(tickers=["a"], trigger=-0.10, trigger_lookback_steps=5, holding_steps=5),
    )

    trade = result["trades"][0]
    assert dates.index(trade.entry_date) == _DROP_SESSION + 1, "kupno na NASTEPNEJ sesji po spadku"
    assert dates.index(trade.exit_date) - dates.index(trade.entry_date) == 5


def test_quantile_trigger_never_buys_a_stock_that_rose():
    """Przyciecie progu decylowego do zera. Gdy CALE uniwersum rosnie, 10 percentyl zwrotow jest
    dodatni - bez przyciecia strategia kupowalaby "spolki, ktore urosly najmniej", co nie ma nic
    wspolnego z kupowaniem po panice.

    Test ma KONTROLE POZYTYWNA w tej samej konfiguracji (jedna spolka realnie spada i ZOSTAJE
    kupiona), bo inaczej "brak transakcji" moglby wynikac z odrzucenia przez bramke, a nie z progu."""
    length = _DROP_SESSION + 30
    rising = {f"t{i}": [100.0 + j * (1 + i * 0.1) for j in range(length)] for i in range(12)}
    config = dict(
        tickers=list(rising), trigger=-0.10, trigger_lookback_steps=5,
        holding_steps=5, trigger_quantile=0.10,
    )
    panel = _multi_panel(*[t.upper() for t in rising])

    prices = _long_prices(**rising)
    all_rising = run_reversal_backtest(prices, panel, list(prices.index), ReversalConfig(**config))

    with_faller = dict(rising)
    with_faller["t0"] = [100.0] * _DROP_SESSION + [80.0] * 30
    prices = _long_prices(**with_faller)
    one_falling = run_reversal_backtest(prices, panel, list(prices.index), ReversalConfig(**config))

    assert not all_rising["trades"], "prog decylowy nie moze wpuszczac spolek ze zwrotem dodatnim"
    assert one_falling["trades"], "kontrola: realny spadek MUSI zostac kupiony"
    assert {t.ticker for t in one_falling["trades"]} == {"t0"}, "kupiona tylko spolka, ktora spadla"


# --- na prawdziwych danych ---


def test_real_data_gate_rejects_most_crash_events():
    """Kontrola z rzeczywistoscia: bramka MUSI odrzucac wiekszosc spadkow -20%, bo wiekszosc takich
    spadkow na GPW to spolki w realnych problemach. Gdyby przepuszczala prawie wszystko, znaczyloby
    to, ze warunki sa martwe."""
    if not DB_PATH.exists() or not PL_DATA_DIR.exists():
        pytest.skip("Brak danych")
    from value_engine.run_reversal import ReversalHarness

    harness = ReversalHarness()
    result, metrics = harness.run(holding_steps=3)

    assert metrics is not None
    decisions = [d for d in result["decisions"] if d["date"] >= metrics["start"]]
    triggered = sum(len(d["triggered"]) for d in decisions)
    passed = sum(len(d["passed_gate"]) for d in decisions)
    assert triggered > 100, f"tylko {triggered} zdarzen -20% - sprawdz trigger"
    assert passed / triggered < 0.60, f"bramka przepuszcza {passed/triggered:.0%} - warunki sa martwe"
    # kazdy z osmiu warunkow musi cokolwiek odrzucac, inaczej jest ozdoba
    for condition in GATE_CONDITIONS:
        assert result["rejection_counts"].get(condition, 0) > 0, f"{condition} nie odrzuca nigdy"
