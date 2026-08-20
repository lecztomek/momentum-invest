"""
Testy QUALITY BACKTEST - silnik v6. Trzy rzeczy, ktorych nie mial zaden poprzedni silnik i ktore
trzeba sprawdzic osobno:

  1. **zmienna liczba pozycji** (`top 20-25%` uniwersum, a nie staly `max_positions`),
  2. **histereza na PERCENTYLU** rankingu, nie na pozycji ("trzymaj, dopoki >= 45 percentyla"),
  3. **equal weight z realnym rebalansem** - dociazanie i odchudzanie pozycji co kwartal.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_quality_backtest.py -v
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport, load_snapshots
from value_engine.fundamentals import FundamentalPanel
from value_engine.quality_backtest import QualityConfig, run_quality_backtest
from value_engine.signals import month_start_decision_dates, quarter_start_decision_dates

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"
PL_DATA_DIR = REPO_ROOT / "data" / "pl"

_PERIODS = [f"{y}/Q{q} (x)" for y in (2018, 2019) for q in (1, 2, 3, 4)]
_DATES = [
    "2018-02-01", "2018-05-01", "2018-08-01", "2018-11-01",
    "2019-02-01", "2019-05-01", "2019-08-01", "2019-11-01",
]


def _prices(**series) -> pd.DataFrame:
    length = max(len(v) for v in series.values())
    index = pd.bdate_range("2019-01-01", periods=length)
    return pd.DataFrame(series, index=index)


def _report(ticker: str, quality: float) -> ParsedReport:
    """Spolka o jednorodnej "jakosci": im wyzszy `quality`, tym lepsze wszystkie szesc skladnikow."""
    return ParsedReport(
        ticker=ticker,
        report_type="mixed",
        periodicity="quarterly",
        periods=list(_PERIODS),
        publication_dates=list(_DATES),
        metrics={
            "IncomeNetProfit": [10.0 * quality] * 8,
            "CashflowOperatingCashflow": [20.0 * quality] * 8,
            "IncomeEBIT": [15.0 * quality] * 8,
            "BalanceCapital": [1000.0] * 8,
            "BalanceTotalAssets": [2000.0] * 8,
            "BalanceCurrentBorrowings": [400.0 / quality] * 8,
            "BalanceNoncurrentBorrowings": [0.0] * 8,
        },
    )


def _panel(**quality_by_ticker) -> FundamentalPanel:
    return FundamentalPanel.from_reports(
        [_report(ticker.upper(), quality) for ticker, quality in quality_by_ticker.items()]
    )


def _run(prices, panel, dates=None, **overrides):
    config = QualityConfig(tickers=list(prices.columns), **overrides)
    return run_quality_backtest(
        prices, panel, dates if dates is not None else month_start_decision_dates(prices), config
    )


# --- ZMIENNA LICZBA POZYCJI ---


def test_position_count_follows_top_fraction_of_universe():
    """top 25% z 8 spolek = 2 pozycje. To rdzen v6: liczba pozycji WYNIKA z rozmiaru uniwersum."""
    names = [f"t{i}" for i in range(8)]
    prices = _prices(**{name: [100.0] * 60 for name in names})
    panel = _panel(**{name: float(8 - i) for i, name in enumerate(names)})

    result = _run(prices, panel, top_fraction=0.25)

    assert result["decisions"][0]["ranked"] == 8
    assert result["decisions"][0]["n_target"] == 2
    assert result["decisions"][0]["n_positions"] == 2
    # kupione najlepsze dwie
    assert result["decisions"][0]["held"] == ["t0", "t1"]


def test_narrow_universe_gives_at_least_one_position():
    """Realny przypadek z GPW 2006-2010: rankowane byly 3-5 spolek, wiec top 25% to 1 pozycja.
    To NIE jest blad silnika, tylko konsekwencja spec - i wlasnie dlatego wczesny okres v6 jest
    portfelem jednoskladnikowym (patrz README, MaxDD -83.5% w 2008)."""
    prices = _prices(a=[100.0] * 40, b=[100.0] * 40, c=[100.0] * 40)
    panel = _panel(a=3.0, b=2.0, c=1.0)

    result = _run(prices, panel, top_fraction=0.25)

    assert result["decisions"][0]["n_target"] == 1
    assert result["decisions"][0]["held"] == ["a"]


def test_max_positions_caps_the_target():
    names = [f"t{i}" for i in range(12)]
    prices = _prices(**{name: [100.0] * 60 for name in names})
    panel = _panel(**{name: float(12 - i) for i, name in enumerate(names)})

    uncapped = _run(prices, panel, top_fraction=0.50)
    capped = _run(prices, panel, top_fraction=0.50, max_positions=3)

    assert uncapped["decisions"][0]["n_target"] == 6
    assert capped["decisions"][0]["n_target"] == 3


def test_shrinking_universe_trims_excess_positions():
    """Gdy uniwersum sie zwezi, `top X%` maleje i nadwyzka MUSI byc sprzedana - inaczej liczba
    pozycji tylko rosla by w czasie (doprecyzowanie nr 3 w silniku)."""
    names = [f"t{i}" for i in range(8)]
    prices = _prices(**{name: [100.0] * 80 for name in names})
    panel = _panel(**{name: float(8 - i) for i, name in enumerate(names)})
    dates = month_start_decision_dates(prices)
    # od trzeciej daty decyzyjnej inwestowalne sa tylko 4 spolki -> top 25% to 1 pozycja
    universe = {
        date: (names if i < 2 else names[:4]) for i, date in enumerate(dates)
    }

    config = QualityConfig(tickers=names, top_fraction=0.25)
    result = run_quality_backtest(prices, panel, dates, config, eligible_universe=universe)

    assert result["decisions"][0]["n_positions"] == 2
    assert result["decisions"][-1]["n_target"] == 1
    assert result["decisions"][-1]["n_positions"] == 1
    assert any(t.exit_reason == "over_target" for t in result["trades"])


# --- HISTEREZA NA PERCENTYLU ---


def test_position_is_kept_while_above_keep_percentile():
    """Spolka nr 2 z 4 (75 percentyl) jest POZA top 25%, ale zostaje w portfelu - to caly sens
    histerezy. Gdyby silnik trzymal tylko top X%, rotowalby przy kazdym drgnieciu rankingu."""
    prices = _prices(a=[100.0] * 80, b=[100.0] * 80, c=[100.0] * 80, d=[100.0] * 80)
    panel_before = _panel(a=4.0, b=3.0, c=2.0, d=1.0)
    dates = month_start_decision_dates(prices)

    result = _run(prices, panel_before, dates, top_fraction=0.25, keep_percentile=45.0)

    # top 25% z 4 = 1 pozycja, wiec kupujemy tylko "a"
    assert result["decisions"][0]["held"] == ["a"]
    # "a" ma 100 percentyl przez caly czas, wiec zostaje i nie ma zadnej wymiany
    assert [d["held"] for d in result["decisions"]] == [["a"]] * len(result["decisions"])
    assert not [t for t in result["trades"] if t.exit_reason == "below_keep_percentile"]


def test_position_is_sold_when_it_falls_below_keep_percentile():
    """Jakosc spolki "a" psuje sie w trakcie: pierwszy raport jest najlepszy, pozniejszy najgorszy.
    Silnik musi ja sprzedac, gdy spadnie ponizej progu percentyla."""
    names = ["a", "b", "c", "d"]
    prices = _prices(**{name: [100.0] * 200 for name in names})
    # "a" startuje jako najlepsza, a od publikacji 2019-08 laduje na dnie rankingu
    degrading = _report("A", 4.0)
    # Degradacja musi byc DRASTYCZNA, bo TTM sumuje 4 kwartaly - dwa slabe kwartaly przy dwoch
    # bardzo dobrych nadal daja przyzwoity TTM (zlapane realnie: przy 0.1 zamiast 40 spolka wciaz
    # byla pierwsza w rankingu, bo 40+40+40+0.1 > 4 x 30 konkurenta).
    degrading.metrics["IncomeNetProfit"] = [40.0] * 6 + [-500.0] * 2
    degrading.metrics["CashflowOperatingCashflow"] = [80.0] * 6 + [-500.0] * 2
    degrading.metrics["IncomeEBIT"] = [60.0] * 6 + [-500.0] * 2
    degrading.metrics["BalanceCurrentBorrowings"] = [100.0] * 6 + [1900.0] * 2
    panel = FundamentalPanel.from_reports(
        [degrading] + [_report(name.upper(), quality) for name, quality in [("b", 3.0), ("c", 2.0), ("d", 1.0)]]
    )

    result = _run(prices, panel, top_fraction=0.25, keep_percentile=45.0)

    assert result["decisions"][0]["held"] == ["a"]
    exits = [t for t in result["trades"] if t.exit_reason == "below_keep_percentile"]
    assert [t.ticker for t in exits] == ["a"]
    assert result["decisions"][-1]["held"] == ["b"]  # slot przejmuje nowy najlepszy


def test_holding_that_cannot_be_scored_is_sold_as_quality_loss():
    """Doprecyzowanie nr 2: spolka JEST w uniwersum, ale przestala miec ocene, wiec sprzedajemy -
    to dokladnie "pogorszenie quality" ze spec (przestalismy wiedziec, czy firma jest dobra).

    Realny mechanizm utraty oceny: kapital wlasny schodzi PONIZEJ ZERA (spolka po duzych stratach).
    ROE i ROIC sa wtedy swiadomie uniewazniane, zostaja 4 skladniki z 6 - przy `min_components=5`
    spolka wypada z rankingu, mimo ze nadal jest w uniwersum."""
    names = ["a", "b", "c", "d"]
    prices = _prices(**{name: [100.0] * 200 for name in names})
    collapsing = _report("A", 4.0)
    collapsing.metrics["BalanceCapital"] = [1000.0] * 6 + [-500.0] * 2  # kapital wlasny na minusie
    panel = FundamentalPanel.from_reports(
        [collapsing]
        + [_report(name.upper(), quality) for name, quality in [("b", 3.0), ("c", 2.0), ("d", 1.0)]]
    )

    config = QualityConfig(
        tickers=names, top_fraction=0.25, keep_percentile=45.0, min_components=5
    )
    result = run_quality_backtest(prices, panel, month_start_decision_dates(prices), config)

    assert result["decisions"][0]["held"] == ["a"]
    exits = [t for t in result["trades"] if t.exit_reason == "quality_unavailable"]
    assert [t.ticker for t in exits] == ["a"]
    assert result["decisions"][-1]["held"] == ["b"]


def test_position_outside_pit_universe_is_not_force_sold():
    """Doprecyzowanie nr 1 (spojne z v2-v5): zanik plynnosci NIE wymusza sprzedazy - wtedy
    najtrudniej wyjsc. Pozycja czeka na powrot do uniwersum."""
    names = ["a", "b", "c", "d"]
    prices = _prices(**{name: [100.0] * 80 for name in names})
    panel = _panel(a=4.0, b=3.0, c=2.0, d=1.0)
    dates = month_start_decision_dates(prices)
    universe = {date: (names if i == 0 else ["b", "c", "d"]) for i, date in enumerate(dates)}

    config = QualityConfig(tickers=names, top_fraction=0.25, keep_percentile=45.0)
    result = run_quality_backtest(prices, panel, dates, config, eligible_universe=universe)

    assert result["decisions"][0]["held"] == ["a"]
    assert "a" in result["decisions"][-1]["held"], "pozycja poza uniwersum nie moze byc sprzedana na sile"


# --- EQUAL WEIGHT ---


def test_rebalance_pulls_weights_back_to_equal():
    """Bez rebalansu zwyciezca rosnie w portfelu bez ograniczen. Z rebalansem wagi wracaja do 1/N -
    to dokladnie ta rozniсa miedzy v6 i v4/v5, ktore kupowaly po 1/N i wiecej nie ruszaly wag."""
    names = [f"t{i}" for i in range(8)]
    values = {name: [100.0] * 400 for name in names}
    values["t0"] = list(100.0 * np.linspace(1.0, 6.0, 400))  # zwyciezca rosnie 6x
    prices = _prices(**values)
    panel = _panel(**{name: float(8 - i) for i, name in enumerate(names)})

    with_rebalance = _run(prices, panel, top_fraction=0.25, rebalance_to_equal_weight=True)
    without = _run(prices, panel, top_fraction=0.25, rebalance_to_equal_weight=False)

    # rebalans MUSI generowac obrot (przycinanie zwyciezcy), brak rebalansu nie generuje go na
    # datach bez wejsc i wyjsc
    assert with_rebalance["decisions"][-1]["turnover"] > 0
    assert without["decisions"][-1]["turnover"] == 0

    weights_with = with_rebalance["decisions"][-1]["weights"]
    weights_without = without["decisions"][-1]["weights"]

    assert weights_with["t0"] == pytest.approx(0.5, abs=0.03), "z rebalansem wagi wracaja do 1/N"
    assert weights_without["t0"] > 0.75, "bez rebalansu zwyciezca zajmuje wiekszosc portfela"
    # a skoro zwyciezca rosnie, to jego przycinanie MUSI obnizyc koncowy kapital
    assert (
        with_rebalance["equity_curve"]["equity"].iloc[-1]
        < without["equity_curve"]["equity"].iloc[-1]
    )


def test_rebalance_tolerance_suppresses_micro_trades():
    """Przy stalych cenach wagi sa juz rowne, wiec rebalans nie moze niczego handlowac - inaczej
    kazdy kwartal placilby 40 bps od szumu numerycznego."""
    names = [f"t{i}" for i in range(8)]
    prices = _prices(**{name: [100.0] * 200 for name in names})
    panel = _panel(**{name: float(8 - i) for i, name in enumerate(names)})

    result = _run(prices, panel, top_fraction=0.25)

    later = [d for d in result["decisions"][2:]]
    assert all(d["turnover"] == 0 for d in later), "rebalans handluje przy zerowej rozbieznosci wag"


def test_costs_reduce_final_equity():
    names = [f"t{i}" for i in range(8)]
    values = {name: [100.0] * 300 for name in names}
    values["t0"] = list(100.0 * np.linspace(1.0, 3.0, 300))
    prices = _prices(**values)
    panel = _panel(**{name: float(8 - i) for i, name in enumerate(names)})

    free = _run(prices, panel, cost_bps=0.0)["equity_curve"]["equity"].iloc[-1]
    costly = _run(prices, panel, cost_bps=100.0)["equity_curve"]["equity"].iloc[-1]

    assert costly < free


# --- WALIDACJA I DATY ---


def test_invalid_config_raises():
    prices = _prices(a=[100.0] * 30)
    panel = _panel(a=1.0)

    with pytest.raises(ValueError, match="top_fraction"):
        _run(prices, panel, top_fraction=0.0)
    with pytest.raises(ValueError, match="keep_percentile"):
        _run(prices, panel, keep_percentile=101.0)


def test_quarter_start_dates_are_calendar_anchored():
    """Daty kwartalne MUSZA byc liczone z kalendarza. "Co trzecia data miesieczna" dawalaby faze
    zalezna od poczatku historii cen, wiec dwa przebiegi na roznych podzbiorach tickerow
    rebalansowalyby w innych miesiacach - i test leave-one-out porownywalby jablka z gruszkami."""
    long_history = _prices(a=[100.0] * 600)
    short_history = _prices(a=[100.0] * 600).iloc[40:]  # start w innym miesiacu

    dates_long = quarter_start_decision_dates(long_history)
    dates_short = quarter_start_decision_dates(short_history)

    assert {d.month for d in dates_long} == {1, 4, 7, 10}
    assert {d.month for d in dates_short} <= {1, 4, 7, 10}
    common = set(dates_long) & set(dates_short)
    assert common, "siatki kwartalne z roznych historii musza sie pokrywac"


def test_equity_curve_covers_every_session_and_starts_at_one():
    prices = _prices(a=[100.0] * 60, b=[100.0] * 60, c=[100.0] * 60, d=[100.0] * 60)
    panel = _panel(a=4.0, b=3.0, c=2.0, d=1.0)

    result = _run(prices, panel)

    assert len(result["equity_curve"]) == len(prices)
    # Pierwszy bar JEST data decyzyjna, wiec kapital jest juz pomniejszony o koszty wejscia
    # (40 bps) - dokladnie 1.0 byloby bledem, bo znaczylo by darmowe transakcje.
    assert result["equity_curve"]["equity"].iloc[0] == pytest.approx(1.0 - 0.004, abs=1e-6)
    assert (result["equity_curve"]["equity"] > 0).all()


def test_no_signals_means_no_first_decision_date():
    prices = _prices(a=[100.0] * 30)
    empty_panel = FundamentalPanel.from_reports([])

    result = _run(prices, empty_panel)

    assert result["first_decision_date"] is None
    assert not result["trades"]


# --- na prawdziwych danych ---


def test_real_data_runs_and_holds_between_min_and_max_positions():
    if not DB_PATH.exists() or not PL_DATA_DIR.exists():
        pytest.skip("Brak danych")
    from value_engine.run_quality import QualityHarness
    from value_engine.run_quality_value import discover_tickers

    harness = QualityHarness(discover_tickers())
    result, metrics = harness.run(top_fraction=0.25, keep_percentile=45.0)

    assert metrics is not None
    decisions = [d for d in result["decisions"] if d["date"] >= metrics["start"]]
    assert len(decisions) > 60, "kwartalnie od 2006 to powinno byc ~80 decyzji"
    assert all(d["n_positions"] >= 1 for d in decisions)
    # Liczba pozycji MUSI wynikac z rozmiaru rankingu, a nie z zaszytego limitu - wczesniej bylo tu
    # `<= 8` (dobre przy 41 spolkach, lamiace sie przy 381). Sprawdzamy WLASNOSC: pozycji nigdy
    # wiecej niz `n_target`, a `n_target` to zaokraglone 25% rankowanego uniwersum.
    for decision in decisions:
        assert decision["n_positions"] <= max(decision["n_target"], 1)
        assert decision["n_target"] == max(1, round(0.25 * decision["ranked"]))

    # HISTEREZA NA PRAWDZIWYCH DANYCH: po zakonczeniu decyzji zadna trzymana spolka nie moze byc
    # ponizej progu percentyla. Wyjatek to pozycje BEZ percentyla (poza uniwersum PIT), ktorych
    # swiadomie nie sprzedajemy na sile - te maja NaN i sa tu odfiltrowane.
    below = [
        (d["date"], ticker, value)
        for d in decisions
        for ticker, value in d["held_percentiles"].items()
        if value == value and value < 45.0
    ]
    assert not below, f"pozycje ponizej progu po decyzji: {below[:3]}"

    # EQUAL WEIGHT: wagi po rebalansie musza byc bliskie 1/N
    spreads = [
        max(d["weights"].values()) - min(d["weights"].values())
        for d in decisions
        if len(d["weights"]) > 1
    ]
    assert max(spreads) < 0.10, f"najwiekszy rozjazd wag {max(spreads):.3f}"
