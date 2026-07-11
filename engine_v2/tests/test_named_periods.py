"""
Testy jednostkowe `named_periods.compute_named_period_metrics`.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_named_periods.py -v
"""

import pandas as pd
import pytest

from engine_v2.acceptance_spec import Criteria
from engine_v2.named_periods import KNOWN_PERIODS, compute_named_period_metrics


def _flat_growth_equity_curve(start: str, end: str, daily_return: float = 0.0003) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    equity = (1.0 + daily_return) ** pd.Series(range(len(dates)), index=dates)
    return pd.DataFrame({"date": dates, "equity": equity.values})


def test_known_periods_are_documented_and_non_overlapping_order():
    # gfc_crash powinien konczyc sie PRZED startem post_gfc_recovery (nastepstwo bez dziury/nakladania)
    gfc_end = pd.Timestamp(KNOWN_PERIODS["gfc_crash"]["end"])
    recovery_start = pd.Timestamp(KNOWN_PERIODS["post_gfc_recovery"]["start"])
    assert recovery_start > gfc_end


def test_unknown_period_name_raises():
    ec = _flat_growth_equity_curve("2020-01-01", "2020-12-31")
    fp = pd.DataFrame({"date": ec["date"], "turnover": 0.0})
    with pytest.raises(ValueError, match="nieznany okres"):
        compute_named_period_metrics(ec, fp, {"not_a_real_period": Criteria()})


def test_computes_metrics_and_checks_for_covered_period():
    ec = _flat_growth_equity_curve("2019-06-01", "2021-06-30")
    fp = pd.DataFrame({"date": ec["date"], "turnover": 0.0})

    result = compute_named_period_metrics(
        ec, fp, {"covid_crash_rebound": Criteria(min_cagr=0.0, max_drawdown=-0.99)}
    )

    assert result["covid_crash_rebound"]["covered"] is True
    assert result["covid_crash_rebound"]["metrics"]["cagr"] > 0.0
    assert result["covid_crash_rebound"]["checks"] == {"min_cagr": True, "max_drawdown": True}


def test_period_outside_equity_curve_range_marked_not_covered():
    ec = _flat_growth_equity_curve("2015-01-01", "2015-12-31")
    fp = pd.DataFrame({"date": ec["date"], "turnover": 0.0})

    result = compute_named_period_metrics(ec, fp, {"inflation_bear": Criteria(min_cagr=0.0)})

    assert result["inflation_bear"] == {"covered": False, "metrics": None, "checks": {}}


def test_empty_named_periods_returns_empty_dict():
    ec = _flat_growth_equity_curve("2020-01-01", "2020-12-31")
    fp = pd.DataFrame({"date": ec["date"], "turnover": 0.0})
    assert compute_named_period_metrics(ec, fp, {}) == {}
