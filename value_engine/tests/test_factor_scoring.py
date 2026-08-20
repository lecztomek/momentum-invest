"""
Testy FACTOR SCORING - Value (rentownosci), Quality (5 kryteriow), Momentum 12-1, skladanie score.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_factor_scoring.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport, load_snapshots
from value_engine.factor_scoring import (
    MOMENTUM_WEIGHT,
    QUALITY_WEIGHT,
    VALUE_WEIGHT,
    QualityInputs,
    ValueInputs,
    compute_quality,
    compute_value_inputs,
    momentum_12_1,
    score_universe,
)
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator, load_shares_outstanding

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"

_PERIODS = [f"{y}/Q{q} (x)" for y in (2017, 2018) for q in (1, 2, 3, 4)]
_DATES = [
    "2017-05-01", "2017-08-01", "2017-11-01", "2018-01-02",
    "2018-05-01", "2018-08-01", "2018-11-01", "2019-01-01",
]
_AS_OF = pd.Timestamp("2019-06-01")


def _panel(**metrics) -> FundamentalPanel:
    expanded = {}
    for name, value in metrics.items():
        expanded[name] = value if isinstance(value, list) else [value] * 8
    return FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="quarterly",
                periods=_PERIODS,
                publication_dates=_DATES,
                metrics=expanded,
            )
        ]
    )


def _full_panel(net_income=10.0, cashflow=40.0, capex=10.0, assets=1000.0, debt=None, share_capital=1000.0):
    return _panel(
        IncomeNetProfit=net_income,
        CashflowOperatingCashflow=cashflow,
        CashflowCapex=capex,
        BalanceTotalAssets=assets,
        BalanceCapital=500.0,
        BalanceCurrentBorrowings=debt if debt is not None else ([100.0] * 4 + [50.0] * 4),
        BalanceNoncurrentBorrowings=0.0,
        BalanceShareCapital=share_capital,
    )


# --- VALUE ---


def test_value_inputs_are_yields_not_multiples():
    """Rentownosci, nie mnozniki: 4 kwartaly x 10 tys. = 40 tys. zysku TTM, kapitalizacja 1 mln ->
    earnings_yield 4%. Ta postac (odwrotnosc P/E) obsluguje straty poprawnie, patrz nastepny test."""
    panel = _full_panel()
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})  # nominal 1 PLN

    inputs = compute_value_inputs(panel, estimator, "A", price=1.0, as_of=_AS_OF)

    assert inputs.market_cap == pytest.approx(1_000_000.0)
    assert inputs.earnings_yield == pytest.approx(40 * 1000 / 1_000_000)  # 4%
    assert inputs.book_to_price == pytest.approx(500 * 1000 / 1_000_000)  # 200%
    # FCF = CFO 160 tys. - CAPEX 40 tys. = 120 tys.
    assert inputs.fcf_yield == pytest.approx(120 * 1000 / 1_000_000)


def test_earnings_yield_is_negative_for_loss_making_company():
    """Kluczowa zaleta rentownosci nad P/E: przy stracie P/E jest nieokreslone, a earnings_yield
    jest ujemny i poprawnie trafia na koniec rankingu "taniosci"."""
    panel = _full_panel(net_income=-10.0)
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    inputs = compute_value_inputs(panel, estimator, "A", price=1.0, as_of=_AS_OF)

    assert inputs.earnings_yield < 0


def test_capex_sign_convention_does_not_change_fcf():
    """CAPEX bywa raportowany ze znakiem ujemnym (wyplyw) albo dodatnim (kwota nakladow) - FCF musi
    wyjsc tak samo, inaczej czesc spolek mialaby FCF zawyzony o 2x naklady."""
    estimator_kwargs = {"A": 1_000_000.0}
    positive = compute_value_inputs(
        _full_panel(capex=10.0), SharesEstimator(_full_panel(capex=10.0), estimator_kwargs), "A", 1.0, _AS_OF
    )
    negative = compute_value_inputs(
        _full_panel(capex=-10.0), SharesEstimator(_full_panel(capex=-10.0), estimator_kwargs), "A", 1.0, _AS_OF
    )

    assert positive.fcf_yield == pytest.approx(negative.fcf_yield)


def test_value_inputs_empty_without_market_cap():
    panel = _full_panel(share_capital=1000.0)
    estimator = SharesEstimator(panel, {})  # brak kotwicy liczby akcji

    inputs = compute_value_inputs(panel, estimator, "A", price=1.0, as_of=_AS_OF)

    assert inputs.available() == 0
    assert inputs.market_cap is None


# --- QUALITY ---


def test_quality_100_when_all_five_criteria_pass():
    quality = compute_quality(_full_panel(), "A", _AS_OF)

    assert quality.score == 100.0
    assert all(quality.passed.values())


def test_quality_steps_are_20_points():
    quality = compute_quality(_full_panel(net_income=-10.0, cashflow=-20.0), "A", _AS_OF)

    assert quality.score in (0.0, 20.0, 40.0, 60.0, 80.0, 100.0)


def test_roa_criterion_is_redundant_with_positive_profit():
    """UDOKUMENTOWANA REDUNDANCJA SPEC: `ROA > 0` to przy dodatnich aktywach dokladnie to samo co
    `zysk TTM > 0`, wiec te dwa kryteria ZAWSZE zapalaja sie razem i "dodatni zysk" wazy w praktyce
    40, a nie 20 pkt. Zaimplementowane doslownie jak w spec - ten test pilnuje, zeby fakt byl
    widoczny, a nie ukryty."""
    good = compute_quality(_full_panel(net_income=10.0), "A", _AS_OF)
    bad = compute_quality(_full_panel(net_income=-10.0), "A", _AS_OF)

    assert good.passed["net_income_positive"] == good.passed["roa_positive"] is True
    assert bad.passed["net_income_positive"] == bad.passed["roa_positive"] is False


def test_quality_missing_data_fails_criteria():
    panel = _full_panel()

    quality = compute_quality(panel, "A", pd.Timestamp("2017-01-01"))  # przed publikacja

    assert quality.score == 0.0


# --- MOMENTUM ---


def test_momentum_12_1_skips_last_month():
    index = pd.bdate_range("2019-01-01", periods=300)
    # rosnie do dnia 279, potem zapada sie w ostatnim miesiacu - 12-1 NIE moze tego widziec
    values = list(range(100, 100 + 279)) + [1.0] * 21
    prices = pd.DataFrame({"a": values[: len(index)]}, index=index)

    result = momentum_12_1(prices, index[299], lookback=252, skip=21)

    assert result["a"] > 0, "krach z ostatniego miesiaca nie powinien wplywac na momentum 12-1"


def test_momentum_12_1_measures_expected_window():
    index = pd.bdate_range("2019-01-01", periods=300)
    prices = pd.DataFrame({"a": [float(i) for i in range(1, 301)]}, index=index)

    result = momentum_12_1(prices, index[299], lookback=252, skip=21)

    expected = prices["a"].iloc[299 - 21] / prices["a"].iloc[299 - 252] - 1
    assert result["a"] == pytest.approx(expected)


def test_momentum_is_none_without_enough_history():
    index = pd.bdate_range("2019-01-01", periods=100)
    prices = pd.DataFrame({"a": [1.0] * 100}, index=index)

    assert momentum_12_1(prices, index[99], lookback=252, skip=21)["a"] is None


# --- SKLADANIE SCORE ---


def _value(earnings, book, fcf) -> ValueInputs:
    return ValueInputs(earnings_yield=earnings, book_to_price=book, fcf_yield=fcf, market_cap=1.0)


def test_final_score_uses_spec_weights():
    assert VALUE_WEIGHT, QUALITY_WEIGHT
    scored = score_universe(
        ["a", "b"],
        value_inputs={"a": _value(0.10, 1.0, 0.10), "b": _value(0.01, 0.1, 0.01)},
        quality_inputs={"a": QualityInputs(score=100.0), "b": QualityInputs(score=0.0)},
        momentum={"a": 0.50, "b": -0.10},
    )
    best = scored[0]

    # "a" jest najtansza, najlepszej jakosci i z najlepszym momentum -> wszystkie percentyle 100
    assert best.ticker == "a"
    assert best.final == pytest.approx(100 * (VALUE_WEIGHT + QUALITY_WEIGHT + MOMENTUM_WEIGHT))
    assert VALUE_WEIGHT + QUALITY_WEIGHT + MOMENTUM_WEIGHT == pytest.approx(1.0)


def test_cheaper_company_gets_higher_value_score():
    scored = score_universe(
        ["tania", "droga"],
        value_inputs={"tania": _value(0.20, 2.0, 0.15), "droga": _value(0.02, 0.2, 0.01)},
        quality_inputs={"tania": QualityInputs(score=50.0), "droga": QualityInputs(score=50.0)},
        momentum={"tania": 0.0, "droga": 0.0},
    )
    by_ticker = {s.ticker: s for s in scored}

    assert by_ticker["tania"].value > by_ticker["droga"].value


def test_company_without_enough_value_metrics_is_excluded():
    """Spolka z jedna metryka Value dostalaby VALUE liczony z innej podstawy niz reszta - lepiej ja
    pominac, niz porownywac nieporownywalne."""
    scored = score_universe(
        ["pelna", "kaleka"],
        value_inputs={"pelna": _value(0.1, 1.0, 0.1), "kaleka": _value(0.1, None, None)},
        quality_inputs={"pelna": QualityInputs(score=50.0), "kaleka": QualityInputs(score=50.0)},
        momentum={"pelna": 0.0, "kaleka": 0.0},
        min_value_metrics=2,
    )

    assert [s.ticker for s in scored] == ["pelna"]


def test_missing_momentum_excludes_company():
    scored = score_universe(
        ["a", "b"],
        value_inputs={"a": _value(0.1, 1.0, 0.1), "b": _value(0.1, 1.0, 0.1)},
        quality_inputs={"a": QualityInputs(score=50.0), "b": QualityInputs(score=50.0)},
        momentum={"a": 0.1, "b": None},
    )

    assert [s.ticker for s in scored] == ["a"]


def test_scored_list_is_sorted_descending():
    scored = score_universe(
        ["a", "b", "c"],
        value_inputs={t: _value(v, v * 10, v) for t, v in [("a", 0.30), ("b", 0.10), ("c", 0.20)]},
        quality_inputs={t: QualityInputs(score=50.0) for t in "abc"},
        momentum={"a": 0.1, "b": 0.2, "c": 0.3},
    )

    assert [s.final for s in scored] == sorted([s.final for s in scored], reverse=True)


# --- na prawdziwych danych ---


def test_real_data_value_metrics_are_in_plausible_ranges():
    """Kontrola zdrowia rozsadku na 22 realnych spolkach: odwrotnosci rentownosci (czyli P/E i P/BV)
    musza wychodzic w realistycznych zakresach. Gdyby liczba akcji byla odtworzona blednie, P/BV
    wychodzilby np. w setkach."""
    if not DB_PATH.exists():
        pytest.skip("Brak bazy")
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY

    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
    shares = load_shares_outstanding(DB_PATH)
    estimator = SharesEstimator(panel, shares)
    prices = LOADER_REGISTRY["stooq_csv"](
        [t.lower() for t in shares], {"data_dir": str(REPO_ROOT / "data" / "pl"), "frequency": "daily"}
    ).prices
    as_of = pd.Timestamp("2026-08-01")

    book_to_price_values = []
    for ticker in shares:
        series = prices[ticker.lower()][prices.index <= as_of].dropna()
        if series.empty:
            continue
        inputs = compute_value_inputs(panel, estimator, ticker, float(series.iloc[-1]), as_of)
        if inputs.book_to_price is not None:
            book_to_price_values.append(inputs.book_to_price)

    assert len(book_to_price_values) >= 15

    # MEDIANA, nie kazda wartosc. Blad jednostek (tysiace vs zlote) albo pomylony mianownik przesuwa
    # CALY rozklad o rzedy wielkosci, wiec to mediana lapie realny blad. Prog na kazdej spolce
    # osobno nie dziala przy 400 nazwach: sa realne przypadki P/BV rzedu 30 000 (spolka po odpisach,
    # z kapitalem wlasnym praktycznie zerowym przy niezerowej kapitalizacji) - to nie blad danych,
    # to spolka, ktorej ta miara nie opisuje. Percentylowy ranking jest na to odporny.
    series = pd.Series(book_to_price_values)
    assert 0.1 < float(series.median()) < 5.0, f"mediana book_to_price = {series.median():.3f}"
    # luzny bezpiecznik: x1000 dalby wartosci rzedu tysiecy dla POLOWY spolek
    assert float((series > 100).mean()) < 0.05, "ponad 5% spolek z P/BV < 0.01 - sprawdz jednostki"
