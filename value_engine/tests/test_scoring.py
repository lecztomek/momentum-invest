"""
Testy SCORING - QUALITY (4 kryteria x 25 pkt), percentyle DD/REL i skladanie SCORE.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_scoring.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport, load_snapshots
from value_engine.fundamentals import FundamentalPanel
from value_engine.scoring import (
    composite_score,
    compute_quality,
    drawdown_from_high,
    percentile_scores,
    score_universe,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"

_PERIODS = [f"{y}/Q{q} (x)" for y in (2017, 2018) for q in (1, 2, 3, 4)]
_DATES = [
    "2017-05-01", "2017-08-01", "2017-11-01", "2018-01-02",
    "2018-05-01", "2018-08-01", "2018-11-01", "2019-01-01",
]
_AS_OF = pd.Timestamp("2019-06-01")


def _panel(net_income, cashflow, debt, assets) -> FundamentalPanel:
    """Kazdy argument to lista 8 wartosci (albo skalar powtorzony 8x)."""

    def expand(value):
        return value if isinstance(value, list) else [value] * 8

    return FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="quarterly",
                periods=_PERIODS,
                publication_dates=_DATES,
                metrics={
                    "IncomeNetProfit": expand(net_income),
                    "CashflowOperatingCashflow": expand(cashflow),
                    "BalanceCurrentBorrowings": expand(debt),
                    "BalanceNoncurrentBorrowings": [0.0] * 8,
                    "BalanceTotalAssets": expand(assets),
                },
            )
        ]
    )


# --- QUALITY ---


def test_quality_100_when_all_four_criteria_pass():
    # zysk > 0, CFO > 0, CFO >= zysk, dlug/aktywa spada (100/1000 -> 50/1000)
    panel = _panel(
        net_income=10.0,
        cashflow=20.0,
        debt=[100.0, 100.0, 100.0, 100.0, 50.0, 50.0, 50.0, 50.0],
        assets=1000.0,
    )
    quality = compute_quality(panel, "A", _AS_OF)

    assert quality.score == 100.0
    assert quality.points == 4
    assert all(quality.passed.values())


def test_quality_scores_in_25_point_steps():
    """QUALITY moze byc TYLKO 0/25/50/75/100 - po 25 pkt za kryterium."""
    cases = {
        # nic niespelnione: strata, CFO<0 I gorszy od straty, dlug/aktywa rosnie
        0.0: dict(net_income=-5.0, cashflow=-10.0, debt=[50.0] * 4 + [100.0] * 4, assets=1000.0),
        # tylko zysk > 0 (CFO<0 i CFO<zysk, dlug rosnie)
        25.0: dict(net_income=10.0, cashflow=-5.0, debt=[50.0] * 4 + [100.0] * 4, assets=1000.0),
        # zysk > 0, CFO > 0, ale CFO < zysk i dlug rosnie
        50.0: dict(net_income=100.0, cashflow=10.0, debt=[50.0] * 4 + [100.0] * 4, assets=1000.0),
        # zysk > 0, CFO > 0, CFO >= zysk, ale dlug rosnie
        75.0: dict(net_income=10.0, cashflow=20.0, debt=[50.0] * 4 + [100.0] * 4, assets=1000.0),
    }
    for expected, kwargs in cases.items():
        assert compute_quality(_panel(**kwargs), "A", _AS_OF).score == expected


def test_cashflow_ge_net_income_passes_when_both_negative():
    """UDOKUMENTOWANY NIUANS SPEC (nie blad): kryterium `CFO TTM >= Net Income TTM` jest
    porownaniem doslownym, wiec przechodzi takze gdy OBA sa ujemne, a CFO jest po prostu MNIEJ
    ujemny (np. CFO -20 >= zysk -40). Jako miernik "jakosci zysku" nie ma to wtedy sensu
    ekonomicznego, ale NIE psuje strategii: spolka ze strata i ujemnym CFO moze zebrac najwyzej
    25 pkt, wiec i tak nie przejdzie bramki QUALITY >= 50. Zaimplementowane doslownie, zeby nie
    zmieniac cicho reguly podanej przez usera."""
    quality = compute_quality(
        _panel(net_income=-10.0, cashflow=-5.0, debt=[50.0] * 4 + [100.0] * 4, assets=1000.0), "A", _AS_OF
    )

    assert quality.passed["cashflow_ge_net_income"]
    assert not quality.passed["net_income_positive"]
    assert not quality.passed["cashflow_positive"]
    assert quality.score == 25.0  # ponizej bramki 50, wiec nieszkodliwe


def test_quality_criterion_cashflow_ge_net_income():
    """CFO >= zysk netto - kryterium "jakosci zysku" (czy zysk jest gotowkowy)."""
    good = compute_quality(_panel(net_income=10.0, cashflow=10.0, debt=50.0, assets=1000.0), "A", _AS_OF)
    bad = compute_quality(_panel(net_income=10.0, cashflow=9.0, debt=50.0, assets=1000.0), "A", _AS_OF)

    assert good.passed["cashflow_ge_net_income"]
    assert not bad.passed["cashflow_ge_net_income"]


def test_quality_debt_ratio_uses_ratio_not_absolute_debt():
    """Kryterium to dlug/AKTYWA, nie sam dlug - spolka moze zwiekszyc dlug nominalnie i wciaz
    przejsc, jesli aktywa rosly szybciej."""
    panel = _panel(
        net_income=10.0,
        cashflow=20.0,
        debt=[100.0] * 4 + [150.0] * 4,  # dlug ROSNIE nominalnie o 50%
        assets=[1000.0] * 4 + [2000.0] * 4,  # ale aktywa rosna 2x -> wskaznik spada 0.10 -> 0.075
    )
    quality = compute_quality(panel, "A", _AS_OF)

    assert quality.passed["debt_ratio_not_rising"]
    assert quality.values["debt_ratio_now"] == pytest.approx(0.075)
    assert quality.values["debt_ratio_year_ago"] == pytest.approx(0.10)


def test_quality_missing_data_fails_criteria_not_passes_them():
    """Brak danych = kryterium NIESPELNIONE. Inaczej spolka bez fundamentow przechodzilaby bramke
    QUALITY >= 50 na samym braku informacji."""
    panel = _panel(net_income=10.0, cashflow=20.0, debt=50.0, assets=1000.0)

    # przed pierwsza publikacja nie wiadomo nic
    quality = compute_quality(panel, "A", pd.Timestamp("2017-01-01"))
    assert quality.score == 0.0
    assert not any(quality.passed.values())

    # nieznany ticker
    assert compute_quality(panel, "NIEZNANA", _AS_OF).score == 0.0


def test_quality_is_point_in_time():
    """Spolka ze strata staje sie "niezdrowa" tylko OD DATY PUBLIKACJI tej straty."""
    panel = FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="quarterly",
                periods=_PERIODS,
                publication_dates=_DATES,
                metrics={
                    # ostatni kwartal to duza strata, opublikowana 2019-01-01
                    "IncomeNetProfit": [10.0] * 7 + [-1000.0],
                    "CashflowOperatingCashflow": [20.0] * 8,
                    "BalanceCurrentBorrowings": [50.0] * 8,
                    "BalanceNoncurrentBorrowings": [0.0] * 8,
                    "BalanceTotalAssets": [1000.0] * 8,
                },
            )
        ]
    )

    before = compute_quality(panel, "A", pd.Timestamp("2018-12-31"))
    after = compute_quality(panel, "A", pd.Timestamp("2019-01-01"))

    assert before.passed["net_income_positive"]
    assert not after.passed["net_income_positive"]


# --- PERCENTYLE I SKLADANIE SCORE ---


def test_percentile_scores_rank_highest_input_as_100():
    scores = percentile_scores({"a": 0.10, "b": 0.50, "c": 0.30})

    assert scores["b"] == 100.0  # najwieksze obsuniecie -> 100
    assert scores["c"] == pytest.approx(200 / 3)
    assert scores["a"] == pytest.approx(100 / 3)


def test_percentile_scores_single_element_gets_100():
    """Zbior jednoelementowy: element jest trywialnie najlepszy w swoim zbiorze. Udokumentowana
    konsekwencja `rank(pct=True)` - przy 1-3 kandydatach percentyle sa zgrubne."""
    assert percentile_scores({"a": 0.42}) == {"a": 100.0}


def test_percentile_scores_ties_are_averaged():
    scores = percentile_scores({"a": 0.30, "b": 0.30})
    assert scores["a"] == scores["b"] == 75.0  # srednia rang 1 i 2 z 2 -> 1.5/2


def test_composite_score_matches_spec_example():
    """Przyklad ze spec: DD=90, REL=80, QUALITY=75 -> 0.50*90 + 0.25*80 + 0.25*75 = 83.75."""
    assert composite_score(90.0, 80.0, 75.0) == pytest.approx(83.75)


def test_drawdown_from_high_is_positive_fraction():
    assert drawdown_from_high(75.0, 100.0) == pytest.approx(0.25)
    assert drawdown_from_high(100.0, 100.0) == pytest.approx(0.0)
    assert drawdown_from_high(50.0, None) is None


def test_score_universe_applies_entry_gate_but_still_scores_everyone():
    """Bramka (dd >= 25% I QUALITY >= 50) decyduje o MOZLIWOSCI KUPNA, ale score liczymy dla
    calego przekazanego zbioru - bo pozycje juz trzymane musza byc porownywalne z kandydatami
    (inaczej prog 10 pkt przy podmianie nie ma sensu)."""
    healthy = compute_quality(_panel(net_income=10.0, cashflow=20.0, debt=[100.0] * 4 + [50.0] * 4, assets=1000.0), "A", _AS_OF)
    weak = compute_quality(_panel(net_income=-10.0, cashflow=-5.0, debt=[50.0] * 4 + [100.0] * 4, assets=1000.0), "A", _AS_OF)

    scored = score_universe(
        ["deep_good", "shallow_good", "deep_bad"],
        drawdowns={"deep_good": 0.40, "shallow_good": 0.10, "deep_bad": 0.50},
        relative_weakness={"deep_good": 0.20, "shallow_good": 0.05, "deep_bad": 0.30},
        qualities={"deep_good": healthy, "shallow_good": healthy, "deep_bad": weak},
    )
    by_ticker = {s.ticker: s for s in scored}

    assert len(scored) == 3  # wszyscy dostali score
    assert by_ticker["deep_good"].passes_entry_gate  # dd 40% + QUALITY 100
    assert not by_ticker["shallow_good"].passes_entry_gate  # dd tylko 10%
    assert not by_ticker["deep_bad"].passes_entry_gate  # QUALITY 0
    assert scored[0].score >= scored[-1].score  # posortowane malejaco


# --- na prawdziwych danych ---


def test_real_data_quality_discriminates_across_universe():
    """Na 22 realnych spolkach QUALITY musi faktycznie roznicowac - gdyby wszystkie mialy to samo,
    komponent bylby bezuzyteczny (i sygnalizowalby blad w liczeniu)."""
    if not DB_PATH.exists():
        pytest.skip(f"Brak bazy {DB_PATH}")
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
    as_of = pd.Timestamp("2026-08-01")

    scores = {t: compute_quality(panel, t, as_of).score for t in panel.tickers}

    assert len(scores) >= 20, "oczekiwane uniwersum ~20-25 spolek"
    assert all(s in (0.0, 25.0, 50.0, 75.0, 100.0) for s in scores.values()), scores
    assert len(set(scores.values())) >= 3, f"QUALITY nie roznicuje: {scores}"
