"""
Testy dla `engine_v2/uk_mapping.py` - user: "bardzo prosto - usa decyduje o wszystkim na uk
zwykly mapping". Wszystkie testy na SYNTETYCZNYCH danych (bez prawdziwych cen UK, ktore jeszcze
nie sa w repo) - sprawdzaja czysta logike remapowania wag i porownania metryk.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_uk_mapping.py -v
"""

import json

import pandas as pd
import pytest

from engine_v2.acceptance_spec import UkMappingAcceptance
from engine_v2.uk_mapping import (
    check_uk_mapping_criteria,
    compare_us_vs_uk,
    load_ticker_mapping,
    remap_final_portfolio,
)


def _final_portfolio(rows):
    """rows: list of (date_str, weights_dict, trade_cost)."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime([r[0] for r in rows]),
            "weights_used_json": [json.dumps(r[1]) for r in rows],
            "trade_cost": [r[2] for r in rows],
            "turnover": [0.0 for _ in rows],
        }
    )


def _equity_curve(rows):
    """rows: list of (date_str, equity)."""
    return pd.DataFrame({"date": pd.to_datetime([r[0] for r in rows]), "equity": [r[1] for r in rows]})


# ---------------------------------------------------------------- load_ticker_mapping

def test_load_ticker_mapping_lowercases_keys_and_values(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps({"XLK.US": "IUIT.UK", "IVV.us": "CSPX.uk"}), encoding="utf-8")

    mapping = load_ticker_mapping(path)

    assert mapping == {"xlk.us": "iuit.uk", "ivv.us": "cspx.uk"}


# ---------------------------------------------------------------- remap_final_portfolio

def test_remap_replaces_tickers_1to1_keeping_weights():
    fp = _final_portfolio([("2021-01-01", {"xlk.us": 0.8, "ivv.us": 0.2}, 0.001)])
    mapping = {"xlk.us": "iuit.uk", "ivv.us": "cspx.uk"}

    uk_fp, diag = remap_final_portfolio(fp, mapping)

    weights = json.loads(uk_fp.iloc[0]["weights_used_json"])
    assert weights == {"iuit.uk": 0.8, "cspx.uk": 0.2}
    assert diag["mismatch_periods"] == 0
    assert diag["unmapped_tickers_used"] == []


def test_remap_unmapped_ticker_falls_back_to_cash_and_flags_mismatch():
    """Rdzen wymagania - VT ('signal only') nie ma mapowania UK - jesli kiedykolwiek dostanie
    niezerowa wage (np. rebound_starter w best17_a), musi trafic w _CASH i byc jawnie zliczone
    jako mismatch, NIE zniknac po cichu."""
    fp = _final_portfolio([("2021-01-01", {"vt.us": 1.0}, 0.001)])
    mapping = {"xlk.us": "iuit.uk"}  # brak vt.us celowo

    uk_fp, diag = remap_final_portfolio(fp, mapping)

    weights = json.loads(uk_fp.iloc[0]["weights_used_json"])
    assert weights == {"_CASH": 1.0}
    assert diag["mismatch_periods"] == 1
    assert diag["mismatch_pct"] == pytest.approx(1.0)
    assert diag["unmapped_tickers_used"] == ["vt.us"]
    assert diag["mismatch_dates"] == [pd.Timestamp("2021-01-01")]


def test_remap_partial_mismatch_only_unmapped_portion_goes_to_cash():
    fp = _final_portfolio([("2021-01-01", {"xlk.us": 0.8, "vt.us": 0.2}, 0.0)])
    mapping = {"xlk.us": "iuit.uk"}

    uk_fp, diag = remap_final_portfolio(fp, mapping)

    weights = json.loads(uk_fp.iloc[0]["weights_used_json"])
    assert weights == {"iuit.uk": 0.8, "_CASH": 0.2}
    assert diag["mismatch_periods"] == 1


def test_remap_cash_rows_pass_through_unchanged():
    fp = _final_portfolio([("2021-01-01", {"_CASH": 1.0}, 0.0)])

    uk_fp, diag = remap_final_portfolio(fp, {"xlk.us": "iuit.uk"})

    weights = json.loads(uk_fp.iloc[0]["weights_used_json"])
    assert weights == {"_CASH": 1.0}
    assert diag["mismatch_periods"] == 0


def test_remap_zero_weight_unmapped_ticker_does_not_count_as_mismatch():
    fp = _final_portfolio([("2021-01-01", {"xlk.us": 1.0, "vt.us": 0.0}, 0.0)])
    mapping = {"xlk.us": "iuit.uk"}  # vt.us bez mapowania, ale waga=0 - nie powinno miec znaczenia

    uk_fp, diag = remap_final_portfolio(fp, mapping)

    weights = json.loads(uk_fp.iloc[0]["weights_used_json"])
    assert weights == {"iuit.uk": 1.0}
    assert diag["mismatch_periods"] == 0


def test_remap_diagnostics_counts_across_multiple_periods():
    fp = _final_portfolio(
        [
            ("2021-01-01", {"xlk.us": 1.0}, 0.0),
            ("2021-02-01", {"vt.us": 1.0}, 0.0),
            ("2021-03-01", {"xlk.us": 0.5, "ivv.us": 0.5}, 0.0),
        ]
    )
    mapping = {"xlk.us": "iuit.uk", "ivv.us": "cspx.uk"}

    uk_fp, diag = remap_final_portfolio(fp, mapping)

    assert diag["total_periods"] == 3
    assert diag["mismatch_periods"] == 1
    assert diag["mismatch_pct"] == pytest.approx(1 / 3)
    assert diag["unmapped_tickers_used"] == ["vt.us"]


def test_remap_empty_final_portfolio_raises():
    with pytest.raises(ValueError, match="pusty final_portfolio"):
        remap_final_portfolio(pd.DataFrame(columns=["date", "weights_used_json", "trade_cost"]), {})


# ---------------------------------------------------------------- compare_us_vs_uk

def test_compare_identical_curves_gives_perfect_correlation_and_zero_gaps():
    fp = _final_portfolio([("2021-01-01", {"x": 1.0}, 0.0), ("2021-02-01", {"x": 1.0}, 0.0)])
    ec = _equity_curve(
        [("2021-01-01", 1.00), ("2021-01-15", 1.02), ("2021-02-01", 1.05), ("2021-02-15", 1.03), ("2021-03-01", 1.08)]
    )

    result = compare_us_vs_uk(fp, ec, fp, ec)

    assert result["monthly_return_correlation"] == pytest.approx(1.0)
    assert result["max_single_month_return_diff"] == pytest.approx(0.0)
    assert result["cagr_gap"] == pytest.approx(0.0)
    assert result["max_drawdown_gap"] == pytest.approx(0.0)


def test_compare_divergent_curves_gives_nonzero_gaps():
    fp = _final_portfolio([("2021-01-01", {"x": 1.0}, 0.0)])
    us_ec = _equity_curve([("2021-01-01", 1.00), ("2021-02-01", 1.10), ("2021-03-01", 1.21)])
    uk_ec = _equity_curve([("2021-01-01", 1.00), ("2021-02-01", 1.05), ("2021-03-01", 1.05)])

    result = compare_us_vs_uk(fp, us_ec, fp, uk_ec)

    assert result["uk_metrics"]["cagr"] < result["us_metrics"]["cagr"]
    assert result["cagr_gap"] < 0.0
    assert result["max_single_month_return_diff"] > 0.0
    assert result["n_common_months"] >= 1


# ---------------------------------------------------------------- check_uk_mapping_criteria

def test_check_uk_mapping_criteria_only_checks_set_thresholds():
    comparison = {
        "monthly_return_correlation": 0.95,
        "max_single_month_return_diff": 0.01,
        "cagr_gap": -0.02,
        "max_drawdown_gap": 0.03,
    }
    criteria = UkMappingAcceptance(min_monthly_return_correlation=0.9)

    results = check_uk_mapping_criteria(comparison, mismatch_pct=0.05, criteria=criteria)

    assert results == {"min_monthly_return_correlation": True}


def test_check_uk_mapping_criteria_all_thresholds_pass():
    comparison = {
        "monthly_return_correlation": 0.95,
        "max_single_month_return_diff": 0.01,
        "cagr_gap": -0.02,
        "max_drawdown_gap": 0.03,
    }
    criteria = UkMappingAcceptance(
        max_weights_mismatch_months_pct=0.10,
        min_monthly_return_correlation=0.9,
        max_single_month_return_diff=0.02,
        max_cagr_gap_vs_us=0.05,
        max_drawdown_gap_vs_us=0.05,
    )

    results = check_uk_mapping_criteria(comparison, mismatch_pct=0.05, criteria=criteria)

    assert all(results.values())


def test_check_uk_mapping_criteria_gap_checks_use_absolute_value():
    """cagr_gap ujemny (UK gorszy niz US) MUSI byc rownie 'wart odnotowania' jak dodatni -
    sprawdzane na abs(), nie na surowej wartosci."""
    comparison = {
        "monthly_return_correlation": 0.99,
        "max_single_month_return_diff": 0.0,
        "cagr_gap": -0.10,
        "max_drawdown_gap": 0.0,
    }
    criteria = UkMappingAcceptance(max_cagr_gap_vs_us=0.05)

    results = check_uk_mapping_criteria(comparison, mismatch_pct=0.0, criteria=criteria)

    assert results["max_cagr_gap_vs_us"] is False


def test_check_uk_mapping_criteria_mismatch_pct_fails_above_threshold():
    criteria = UkMappingAcceptance(max_weights_mismatch_months_pct=0.03)

    results = check_uk_mapping_criteria({}, mismatch_pct=0.10, criteria=criteria)

    assert results["max_weights_mismatch_months_pct"] is False
