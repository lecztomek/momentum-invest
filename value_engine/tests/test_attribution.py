"""
Testy ATTRIBUTION - badanie "co lacza spolki, ktore rosly".

Cztery rzeczy, ktore musza byc dokladnie takie:
  1. **korelacja rangowa** liczona bez scipy (Pearson na rangach) - blad tutaj przewraca kazdy IC,
  2. **point-in-time cech ex-ante** - to jedyna czesc badania, ktora ma znaczenie dla strategii,
     wiec nie moze widziec raportu przed publikacja,
  3. **TOZSAMOSC DEKOMPOZYCJI**: `(1+zwrot) = (1+wzrost EPS) * (1+zmiana mnoznika)` - to nie
     przyblizenie, to definicja (cena = EPS * P/E), wiec musi sie zgadzac do zera numerycznego,
  4. **`_growth` przy niedodatniej bazie zwraca None** - "poprawa" ze -100 na -50 nie jest ani
     -50%, ani +50%, a wrzucona do rankingu przesuwa cala cechę.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_attribution.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.attribution import (
    EX_ANTE_FEATURES,
    _growth,
    _spearman,
    company_features,
    decompose_returns,
    forward_return,
    information_coefficients,
)
from value_engine.br_parser import ParsedReport
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"

_PERIODS = [f"{y}/Q{q} (x)" for y in (2018, 2019, 2020) for q in (1, 2, 3, 4)]
_DATES = [
    "2018-05-01", "2018-08-01", "2018-11-01", "2019-02-01",
    "2019-05-01", "2019-08-01", "2019-11-01", "2020-02-01",
    "2020-05-01", "2020-08-01", "2020-11-01", "2021-02-01",
]


def _panel(ticker: str = "A", **metrics) -> FundamentalPanel:
    expanded = {
        name: (value if isinstance(value, list) else [value] * len(_PERIODS))
        for name, value in metrics.items()
    }
    return FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker=ticker,
                report_type="mixed",
                periodicity="quarterly",
                periods=list(_PERIODS),
                publication_dates=list(_DATES),
                metrics=expanded,
            )
        ]
    )


def _full(**overrides):
    base = dict(
        IncomeRevenues=1000.0,
        IncomeEBIT=200.0,
        IncomeNetProfit=100.0,
        CashflowOperatingCashflow=150.0,
        CashflowCapex=-50.0,
        BalanceTotalAssets=5000.0,
        BalanceCapital=2000.0,
        BalanceCurrentAssets=1500.0,
        BalanceCurrentLiabilities=750.0,
        BalanceShareCapital=1000.0,
        BalanceCurrentBorrowings=500.0,
        BalanceNoncurrentBorrowings=0.0,
    )
    base.update(overrides)
    return base


# --- KORELACJA RANGOWA ---


def test_spearman_on_monotone_and_antimonotone_series():
    left = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    assert _spearman(left, pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])) == pytest.approx(1.0)
    assert _spearman(left, pd.Series([50.0, 40.0, 30.0, 20.0, 10.0])) == pytest.approx(-1.0)


def test_spearman_is_immune_to_a_single_outlier():
    """Cala pointa uzycia rangowej, a nie liniowej: jeden ekstremalny outlier (np. E/P przy zysku
    bliskim zera) nie moze zdominowac wyniku."""
    left = pd.Series([1.0, 2.0, 3.0, 4.0, 1_000_000.0])
    right = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    assert _spearman(left, right) == pytest.approx(1.0)
    assert left.corr(right) < 0.9, "Pearson MUSI byc tu zepsuty - inaczej test nic nie pokazuje"


def test_spearman_returns_nan_for_constant_input():
    assert pd.isna(_spearman(pd.Series([2.0, 2.0, 2.0]), pd.Series([1.0, 2.0, 3.0])))


def test_growth_rejects_non_positive_base():
    assert _growth(50.0, 100.0) == pytest.approx(-0.5)
    assert _growth(150.0, 100.0) == pytest.approx(0.5)
    assert _growth(-50.0, -100.0) is None, "wzrost z ujemnej bazy nie ma interpretacji"
    assert _growth(100.0, 0.0) is None
    assert _growth(None, 100.0) is None


# --- CECHY EX-ANTE ---


def test_features_are_computed_in_the_right_units():
    """Sprawozdania sa w TYSIACACH, kapitalizacja w zlotych. Przy cenie 1.0 i 1 mln akcji
    kapitalizacja to 1 mln zl = 1000 tys., wiec E/P = zysk TTM 400 tys. / 1000 tys. = 0.4."""
    panel = _panel(**_full())
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    features = company_features(
        panel, panel, estimator, "A", pd.Timestamp("2021-06-01"), price=1.0
    ).values

    assert features["earnings_yield"] == pytest.approx(400.0 / 1000.0)
    assert features["book_to_price"] == pytest.approx(2000.0 / 1000.0)
    assert features["sales_to_price"] == pytest.approx(4000.0 / 1000.0)
    # FCF = CFO + capex (capex jest ujemny): 600 - 200 = 400
    assert features["fcf_yield"] == pytest.approx(400.0 / 1000.0)
    assert features["roe"] == pytest.approx(400.0 / 2000.0)
    assert features["roa"] == pytest.approx(400.0 / 5000.0)
    assert features["ebit_margin"] == pytest.approx(800.0 / 4000.0)
    assert features["cfo_to_assets"] == pytest.approx(600.0 / 5000.0)
    assert features["current_ratio"] == pytest.approx(2.0)
    assert features["debt_to_assets"] == pytest.approx(500.0 / 5000.0)
    assert features["accruals"] == pytest.approx((400.0 - 600.0) / 5000.0)


def test_features_are_point_in_time():
    """Rdzen poprawnosci czesci (A): na dzien przed pierwsza publikacja nie wiemy NIC."""
    panel = _panel(**_full())
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    before = company_features(panel, panel, estimator, "A", pd.Timestamp("2018-04-30"), 1.0).values

    assert all(value is None for value in before.values())


def test_every_declared_feature_is_actually_produced():
    """Straznik spojnosci: `EX_ANTE_FEATURES` jest uzywane do naglowkow raportu, wiec kazdy klucz
    musi istniec w wyniku - inaczej raport cicho gubi cecha."""
    panel = _panel(**_full())
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    features = company_features(panel, panel, estimator, "A", pd.Timestamp("2021-06-01"), 1.0).values

    assert set(features) == set(EX_ANTE_FEATURES)


def test_negative_equity_invalidates_roe():
    panel = _panel(**_full(BalanceCapital=-500.0, IncomeNetProfit=-100.0))
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    features = company_features(panel, panel, estimator, "A", pd.Timestamp("2021-06-01"), 1.0).values

    assert features["roe"] is None
    assert features["roa"] is not None


# --- ZWROTY FORWARD ---


def _prices(**series) -> pd.DataFrame:
    length = max(len(v) for v in series.values())
    return pd.DataFrame(series, index=pd.bdate_range("2019-01-01", periods=length))


def test_forward_return_uses_last_price_at_or_before_each_date():
    prices = _prices(a=[100.0] * 10 + [150.0] * 10)

    value = forward_return(prices, "a", prices.index[5], prices.index[15])

    assert value == pytest.approx(0.5)


def test_forward_return_is_none_when_the_series_ends_early():
    """Spolka bez ceny na koncu okresu (delisting, zawieszenie) NIE moze byc liczona jako 0%."""
    prices = _prices(a=[100.0] * 10 + [float("nan")] * 10)

    assert forward_return(prices, "a", prices.index[15], prices.index[19]) is None
    assert forward_return(prices, "brak", prices.index[0], prices.index[5]) is None


# --- DEKOMPOZYCJA ---


def test_decomposition_identity_holds_exactly():
    """(1 + zwrot ceny) = (1 + wzrost EPS) * (1 + zmiana mnoznika). To definicja, nie przyblizenie:
    cena = EPS * P/E. Gdyby sie nie zgadzalo, cala czesc (B) badania bylaby bledna."""
    index = pd.bdate_range("2019-01-01", periods=700)
    prices = pd.DataFrame({"a": [10.0] * 350 + [30.0] * 350}, index=index)
    # zysk podwaja sie od publikacji 2020-05 (kwartaly 9-12), liczba akcji stala
    panel = _panel(**_full(IncomeNetProfit=[100.0] * 8 + [200.0] * 4))
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})
    start = index[300]
    universe = {start: ["a"]}

    frame = decompose_returns(panel, estimator, prices, universe, horizon_months=12)

    assert len(frame) == 1
    row = frame.iloc[0]
    assert (1.0 + row["price_return"]) == pytest.approx(
        (1.0 + row["eps_growth"]) * (1.0 + row["multiple_change"])
    )
    assert row["dilution"] == pytest.approx(0.0)
    assert row["eps_growth"] == pytest.approx(1.0)  # zysk TTM 400 -> 800


def test_decomposition_buckets_are_computed_within_each_date():
    """Kwantyle MUSZA byc liczone w obrebie daty - inaczej porownywalibysmy zwroty z roznych
    rezimow rynkowych (2008 z 2021) i "kwintyl 1" znaczyloby "byl rok 2008"."""
    index = pd.bdate_range("2019-01-01", periods=1200)
    names = [f"t{i}" for i in range(10)]
    # w pierwszym okresie wszystkie rosna, w drugim wszystkie spadaja
    data = {}
    for i, name in enumerate(names):
        data[name] = [100.0] * 300 + [100.0 + i * 10] * 300 + [50.0 - i] * 600
    prices = pd.DataFrame(data, index=index)
    panel = FundamentalPanel.from_reports([])
    estimator = SharesEstimator(panel, {})
    universe = {index[290]: names, index[610]: names}

    frame = decompose_returns(panel, estimator, prices, universe, horizon_months=12, quantiles=5)

    for date, group in frame.groupby("date"):
        assert group["bucket"].nunique() == 5, f"{date}: kwantyle musza istniec w kazdej dacie"


# --- IC END-TO-END ---


def test_information_coefficient_detects_a_planted_relationship():
    """Kontrola end-to-end na danych, w ktorych ZNAMY odpowiedz: spolka o wyzszym E/P rosnie
    mocniej, wiec IC dla `earnings_yield` musi byc +1.0."""
    index = pd.bdate_range("2019-01-01", periods=700)
    names = [f"t{i}" for i in range(12)]
    prices = pd.DataFrame(
        # cena startowa rosnie z i (wiec E/P MALEJE z i), a zwrot forward maleje z i
        {name: [100.0 + 10 * i] * 350 + [(100.0 + 10 * i) * (2.0 - 0.1 * i)] * 350
         for i, name in enumerate(names)},
        index=index,
    )
    reports = []
    for name in names:
        reports.append(
            ParsedReport(
                ticker=name.upper(),
                report_type="mixed",
                periodicity="quarterly",
                periods=list(_PERIODS),
                publication_dates=list(_DATES),
                metrics={key: [value] * len(_PERIODS) for key, value in _full().items()},
            )
        )
    panel = FundamentalPanel.from_reports(reports)
    estimator = SharesEstimator(panel, {name.upper(): 1_000_000.0 for name in names})
    universe = {index[340]: names}

    ic, summary = information_coefficients(
        (panel, panel), estimator, prices, universe, horizon_months=12, min_companies=5
    )

    assert len(ic) == 1
    # zysk identyczny, cena startowa rosnaca -> E/P malejace; zwrot forward tez malejacy -> IC = +1
    assert summary.loc["earnings_yield", "sredni_IC"] == pytest.approx(1.0)
    assert summary.loc["log_market_cap", "sredni_IC"] == pytest.approx(-1.0)


def test_information_coefficient_skips_thin_cross_sections():
    index = pd.bdate_range("2019-01-01", periods=700)
    prices = pd.DataFrame({"a": [100.0] * 700, "b": [100.0] * 700}, index=index)
    panel = FundamentalPanel.from_reports([])
    estimator = SharesEstimator(panel, {})

    ic, summary = information_coefficients(
        (panel, panel), estimator, prices, {index[340]: ["a", "b"]}, horizon_months=12
    )

    assert ic.empty and summary.empty, "przekroj z 2 spolek nie moze dawac IC"
