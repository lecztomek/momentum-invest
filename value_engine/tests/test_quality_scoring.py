"""
Testy QUALITY SCORING - koncepcja v6 (czysta jakosc, bez Value i bez Momentum).

Punkty, ktore trzeba pilnowac:
  - `debt_to_assets` ma ODWROTNY kierunek rankingu (nizej = lepiej),
  - kryteria binarne wchodza jako 0/100, wiec sa w tej samej skali co percentyle,
  - brak danych POMIJA skladnik, a nie zeruje go (inaczej karzemy za brak informacji, nie za jakosc),
  - `percentile` musi opisywac pozycje w RANKINGU, bo na niej stoi cala histereza v6.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_quality_scoring.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport, load_snapshots
from value_engine.fundamentals import FundamentalPanel
from value_engine.quality_scoring import (
    BINARY_CRITERIA,
    COMPONENTS,
    CONTINUOUS_METRICS,
    QualityInputs,
    compute_quality_inputs,
    score_universe,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"

_PERIODS = [f"{y}/Q{q} (x)" for y in (2016, 2017, 2018) for q in (1, 2, 3, 4)]
_DATES = [
    "2016-05-01", "2016-08-01", "2016-11-01", "2017-01-02",
    "2017-05-01", "2017-08-01", "2017-11-01", "2018-01-02",
    "2018-05-01", "2018-08-01", "2018-11-01", "2019-01-02",
]
_AS_OF = pd.Timestamp("2019-06-01")


def _panel(**metrics) -> FundamentalPanel:
    expanded = {
        name: (value if isinstance(value, list) else [value] * len(_PERIODS))
        for name, value in metrics.items()
    }
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


def _full_panel(
    net_income=25.0, cashflow=30.0, ebit=40.0, equity=1000.0, assets=2000.0, debt=200.0
):
    return _panel(
        IncomeNetProfit=net_income,
        CashflowOperatingCashflow=cashflow,
        IncomeEBIT=ebit,
        BalanceCapital=equity,
        BalanceTotalAssets=assets,
        BalanceCurrentBorrowings=debt,
        BalanceNoncurrentBorrowings=0.0,
    )


# --- WSKAZNIKI ---


def test_all_six_components_are_computed_from_ttm_where_applicable():
    """ROE = zysk TTM / kapital wlasny (4 x 25 = 100 / 1000 = 10%), CFO/aktywa = 120/2000 = 6%,
    ROIC = 160 * 0.81 / (1000 + 200) = 10.8%, dlug/aktywa = 200/2000 = 10%."""
    inputs = compute_quality_inputs(_full_panel(), "A", _AS_OF)

    assert inputs.roe == pytest.approx(0.10)
    assert inputs.cfo_to_assets == pytest.approx(120.0 / 2000.0)
    assert inputs.roic == pytest.approx(160.0 * 0.81 / 1200.0)
    assert inputs.debt_to_assets == pytest.approx(0.10)
    assert inputs.cfo_ge_net_income is True  # 120 >= 100
    assert inputs.debt_not_rising is True  # taki sam dlug i te same aktywa rok wczesniej
    assert inputs.available() == len(COMPONENTS) == 6


def test_cfo_below_net_income_fails_that_criterion():
    inputs = compute_quality_inputs(_full_panel(net_income=50.0, cashflow=10.0), "A", _AS_OF)

    assert inputs.cfo_ge_net_income is False
    assert inputs.roe is not None  # pozostale skladniki nadal policzone


def test_rising_debt_ratio_fails_that_criterion():
    """Dlug rosnie w ostatnich 4 kwartalach: 100 -> 400 przy stalych aktywach."""
    panel = _panel(
        IncomeNetProfit=25.0,
        CashflowOperatingCashflow=30.0,
        IncomeEBIT=40.0,
        BalanceCapital=1000.0,
        BalanceTotalAssets=2000.0,
        BalanceCurrentBorrowings=[100.0] * 8 + [400.0] * 4,
        BalanceNoncurrentBorrowings=0.0,
    )
    inputs = compute_quality_inputs(panel, "A", _AS_OF)

    assert inputs.debt_not_rising is False
    assert inputs.debt_to_assets == pytest.approx(0.20)


def test_debt_trend_uses_RATIO_not_absolute_debt():
    """Spolka, ktorej dlug wzrosl 2x, ale aktywa 3x, ma NIZSZE zadluzenie relatywne - kryterium
    musi byc spelnione. Porownywanie samych kwot dawaloby tu falszywy alarm."""
    panel = _panel(
        IncomeNetProfit=25.0,
        CashflowOperatingCashflow=30.0,
        IncomeEBIT=40.0,
        BalanceCapital=1000.0,
        BalanceTotalAssets=[1000.0] * 8 + [3000.0] * 4,
        BalanceCurrentBorrowings=[100.0] * 8 + [200.0] * 4,
        BalanceNoncurrentBorrowings=0.0,
    )
    inputs = compute_quality_inputs(panel, "A", _AS_OF)

    assert inputs.debt_not_rising is True  # 200/3000 = 6.7% < 100/1000 = 10%


def test_negative_equity_invalidates_roe_and_roic_but_not_cashflow_metrics():
    """Przy ujemnym mianowniku spolka ZE STRATA wygladalaby na najrentowniejsza - lepiej brak
    wskaznika. Metryki oparte na aktywach nie sa tym dotkniete."""
    inputs = compute_quality_inputs(
        _full_panel(net_income=-50.0, equity=-500.0), "A", _AS_OF
    )

    assert inputs.roe is None
    assert inputs.roic is None
    assert inputs.cfo_to_assets is not None
    assert inputs.debt_to_assets is not None


def test_unpublished_fundamentals_give_nothing():
    inputs = compute_quality_inputs(_full_panel(), "A", pd.Timestamp("2016-01-01"))

    assert inputs.available() == 0


def test_v6_does_not_need_price_or_market_cap():
    """Kontrola zakresu koncepcji: v6 nie ma czynnika Value, wiec scoring musi dzialac bez ceny i
    bez kapitalizacji - inaczej niesmiertelnie wciagalibysmy z powrotem `SharesEstimator`."""
    inputs = compute_quality_inputs(_full_panel(), "A", _AS_OF)

    assert inputs.available() == 6  # policzone wylacznie z panelu fundamentow


# --- SKLADANIE SCORE ---


def _inputs(roe=0.10, roic=0.10, cfo=0.08, debt=0.20, cfo_ge=True, not_rising=True) -> QualityInputs:
    return QualityInputs(
        roe=roe,
        roic=roic,
        cfo_to_assets=cfo,
        debt_to_assets=debt,
        cfo_ge_net_income=cfo_ge,
        debt_not_rising=not_rising,
    )


def test_lower_debt_to_assets_scores_higher():
    """ODWROTNY KIERUNEK. Gdyby percentyl liczyl sie "wiecej = lepiej", najbardziej zadluzona
    spolka wygrywalaby ranking jakosci."""
    scored = score_universe(
        ["male_dlugi", "duze_dlugi"],
        {"male_dlugi": _inputs(debt=0.05), "duze_dlugi": _inputs(debt=0.60)},
    )
    by_ticker = {s.ticker: s for s in scored}

    assert by_ticker["male_dlugi"].components["debt_to_assets"] == 100.0
    assert by_ticker["duze_dlugi"].components["debt_to_assets"] == 50.0
    assert scored[0].ticker == "male_dlugi"


def test_higher_roe_roic_and_cashflow_score_higher():
    scored = score_universe(
        ["dobra", "slaba"],
        {"dobra": _inputs(0.30, 0.30, 0.20), "slaba": _inputs(0.01, 0.01, 0.01)},
    )

    assert [s.ticker for s in scored] == ["dobra", "slaba"]
    for metric in ("roe", "roic", "cfo_to_assets"):
        assert scored[0].components[metric] > scored[1].components[metric]


def test_binary_criteria_are_scored_as_zero_or_hundred():
    scored = score_universe(
        ["czysta", "brudna"],
        {
            "czysta": _inputs(cfo_ge=True, not_rising=True),
            "brudna": _inputs(cfo_ge=False, not_rising=False),
        },
    )
    by_ticker = {s.ticker: s for s in scored}

    for criterion in BINARY_CRITERIA:
        assert by_ticker["czysta"].components[criterion] == 100.0
        assert by_ticker["brudna"].components[criterion] == 0.0
    # przy identycznych metrykach ciaglych rozstrzygaja wlasnie kryteria binarne
    assert scored[0].ticker == "czysta"


def test_final_is_mean_of_available_components():
    scored = score_universe(["a", "b"], {"a": _inputs(), "b": _inputs(0.2, 0.2, 0.2, 0.1)})

    for score in scored:
        assert len(score.components) == 6
        assert score.final == pytest.approx(sum(score.components.values()) / 6)


def test_missing_component_is_skipped_not_zeroed():
    """Spolka bez przeplywow nie moze byc karana ZEREM za brak informacji - to nie to samo co
    zerowe przeplywy. Liczymy srednia z tego, co jest."""
    partial = QualityInputs(roe=0.5, roic=0.5, debt_to_assets=0.05, debt_not_rising=True)
    scored = score_universe(["pelna", "bez_cfo"], {"pelna": _inputs(), "bez_cfo": partial})
    by_ticker = {s.ticker: s for s in scored}

    assert "cfo_to_assets" not in by_ticker["bez_cfo"].components
    assert "cfo_ge_net_income" not in by_ticker["bez_cfo"].components
    assert len(by_ticker["bez_cfo"].components) == 4
    assert by_ticker["bez_cfo"].final == pytest.approx(
        sum(by_ticker["bez_cfo"].components.values()) / 4
    )
    # ma najwyzsze ROE/ROIC i najnizszy dlug w zbiorze, wiec brak CFO nie moze jej zepchnac na dno
    assert by_ticker["bez_cfo"].final > 50.0


def test_company_below_min_components_is_excluded_from_ranking():
    """Score z dwoch skladnikow nie jest porownywalny ze score z szesciu - taka spolka wypada."""
    scored = score_universe(
        ["pelna", "kaleka"],
        {"pelna": _inputs(), "kaleka": QualityInputs(roe=0.9, roic=0.9)},
        min_components=4,
    )

    assert [s.ticker for s in scored] == ["pelna"]


def test_percentile_describes_position_in_ranking():
    """Na `percentile` stoi histereza v6 ("trzymamy, dopoki nie spadnie ponizej 45 percentyla"),
    wiec musi byc liczony na CALYM rankingu i rosnac wraz z jakoscia."""
    scored = score_universe(
        ["a", "b", "c", "d"],
        {
            "a": _inputs(0.40, 0.40, 0.30, 0.01),
            "b": _inputs(0.30, 0.30, 0.20, 0.05),
            "c": _inputs(0.10, 0.10, 0.10, 0.20),
            "d": _inputs(0.01, 0.01, 0.01, 0.50),
        },
    )

    assert [s.ticker for s in scored] == ["a", "b", "c", "d"]
    assert [s.percentile for s in scored] == [100.0, 75.0, 50.0, 25.0]
    # prog 45 percentyla odsiewa dokladnie najslabsza spolke z czterech
    assert [s.ticker for s in scored if s.percentile >= 45.0] == ["a", "b", "c"]


def test_ranking_is_sorted_and_empty_input_is_safe():
    scored = score_universe(["a", "b", "c"], {t: _inputs(roe=v) for t, v in [("a", 0.1), ("b", 0.3), ("c", 0.2)]})

    assert [s.final for s in scored] == sorted([s.final for s in scored], reverse=True)
    assert score_universe([], {}) == []
    assert score_universe(["x"], {}) == []


def test_all_metrics_declared_in_components():
    """Straznik spojnosci: kazda metryka ciagla i kazde kryterium binarne musi byc polem
    `QualityInputs`, inaczej `available()` liczylby cos innego niz `score_universe`."""
    for name in CONTINUOUS_METRICS + BINARY_CRITERIA:
        assert hasattr(QualityInputs(), name), name
    assert set(COMPONENTS) == set(CONTINUOUS_METRICS) | set(BINARY_CRITERIA)


# --- na prawdziwych danych ---


def test_real_data_ranking_is_plausible_and_populated():
    if not DB_PATH.exists():
        pytest.skip("Brak bazy")
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
    tickers = sorted({report.ticker for report in load_snapshots(DB_PATH)})
    as_of = pd.Timestamp("2026-08-01")

    inputs = {t: compute_quality_inputs(panel, t, as_of) for t in tickers}
    scored = score_universe(tickers, inputs)

    assert len(scored) >= 30, f"rankowanych tylko {len(scored)} z {len(tickers)}"
    assert all(0.0 <= s.final <= 100.0 for s in scored)
    assert scored[0].percentile == pytest.approx(100.0)
    # mediana dlug/aktywa duzych spolek GPW: kilka-kilkadziesiat procent
    debt = pd.Series([s.inputs.debt_to_assets for s in scored if s.inputs.debt_to_assets is not None])
    assert 0.0 < float(debt.median()) < 0.50, f"mediana dlug/aktywa {debt.median():.2f}"


def test_real_data_jsw_looked_like_top_quality_at_the_2017_coal_peak():
    """KONTROLA Z RZECZYWISTOSCIA I JEDNOCZESNIE DOWOD NA GLOWNA SLABOSC v6. JSW w polowie 2017
    (szczyt cen wegla koksowego) mial ROE ~20%, ROIC ~23%, CFO/aktywa ~13% i dlug/aktywa 0.6% -
    czyli wygladal na NAJLEPSZA jakosciowo spolke w uniwersum. Przez kolejne ~3 lata stracil ~83%.

    Ten test nie sprawdza bledu w kodzie, tylko pilnuje, ze wskazniki licza sie tak, jak opisano w
    README - bo na tym stoi caly wniosek o v6 (jakosc z danych kroczacych szczytuje na szczycie
    cyklu)."""
    if not DB_PATH.exists():
        pytest.skip("Brak bazy")
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
    as_of = pd.Timestamp("2017-07-03")

    jsw = compute_quality_inputs(panel, "JSW", as_of)

    assert jsw.roe is not None and jsw.roe > 0.15
    assert jsw.roic is not None and jsw.roic > 0.20
    assert jsw.cfo_to_assets is not None and jsw.cfo_to_assets > 0.10
    assert jsw.debt_to_assets is not None and jsw.debt_to_assets < 0.02
    assert jsw.cfo_ge_net_income is True
    assert jsw.debt_not_rising is True
