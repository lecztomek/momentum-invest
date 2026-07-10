"""
Testy regresyjne ACCEPTANCE CHECK ("check_criteria").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_acceptance_check.py -v
"""

from engine_v2.acceptance_check import check_criteria
from engine_v2.acceptance_spec import Criteria


def test_only_set_criteria_are_checked():
    criteria = Criteria(min_cagr=0.05)
    metrics = {"cagr": 0.10, "max_drawdown": -0.5, "sharpe": -10, "calmar": -10, "annual_turnover": 999}

    result = check_criteria(metrics, criteria)

    assert result == {"min_cagr": True}


def test_min_criteria_pass_and_fail():
    criteria = Criteria(min_cagr=0.05, min_sharpe=0.5, min_calmar=0.4)
    metrics = {"cagr": 0.03, "sharpe": 0.6, "calmar": 0.4}

    result = check_criteria(metrics, criteria)

    assert result == {"min_cagr": False, "min_sharpe": True, "min_calmar": True}


def test_max_criteria_pass_and_fail():
    criteria = Criteria(
        max_drawdown=-0.25,
        max_annual_turnover=6.0,
        max_consecutive_negative_months=6,
        max_time_underwater_months=24,
    )
    metrics = {
        "max_drawdown": -0.30,  # gorszy niz -0.25 -> fail
        "annual_turnover": 5.0,  # <= 6.0 -> pass
        "max_consecutive_negative_months": 6,  # == prog -> pass (<=)
        "max_time_underwater_months": 30,  # > 24 -> fail
    }

    result = check_criteria(metrics, criteria)

    assert result == {
        "max_drawdown": False,
        "max_annual_turnover": True,
        "max_consecutive_negative_months": True,
        "max_time_underwater_months": False,
    }


def test_all_none_returns_empty():
    assert check_criteria({"cagr": 0.1}, Criteria()) == {}
