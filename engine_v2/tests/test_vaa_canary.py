"""
Testy regresyjne PORTFOLIO RISK ENGINE ("vaa_canary").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_vaa_canary.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY

vaa_canary = PORTFOLIO_RISK_ENGINE_REGISTRY["vaa_canary"]

OFFENSIVE = ["spy", "efa", "vwo", "agg"]
DEFENSIVE = ["shy", "ief", "lqd"]


def _score(rows):
    idx = pd.date_range("2021-01-01", periods=len(rows), freq="MS")
    return pd.DataFrame(rows, index=idx, columns=OFFENSIVE + DEFENSIVE)


def _dummy_target_weights(score):
    return pd.DataFrame(0.0, index=score.index, columns=list(score.columns) + ["_CASH"])


def test_requires_asset_lists():
    score = _score([[0.1] * 7])
    tw = _dummy_target_weights(score)
    with pytest.raises(ValueError, match="offensive_assets"):
        vaa_canary(tw, None, {}, score, {})


def test_unknown_ticker_in_params_raises():
    score = _score([[0.1] * 7])
    tw = _dummy_target_weights(score)
    with pytest.raises(ValueError, match="brak tickerow"):
        vaa_canary(
            tw, None, {}, score,
            {"offensive_assets": ["zzz"], "defensive_assets": DEFENSIVE},
        )


def test_all_canaries_positive_picks_best_offensive():
    # wszystkie 4 ofensywne dodatnie -> risk-on, wybierz najlepszy z ofensywnych (nie defensywny)
    row = {"spy": 0.05, "efa": 0.02, "vwo": 0.01, "agg": 0.03, "shy": 0.10, "ief": 0.10, "lqd": 0.10}
    score = _score([row])
    tw = _dummy_target_weights(score)

    out = vaa_canary(tw, None, {}, score, {"offensive_assets": OFFENSIVE, "defensive_assets": DEFENSIVE})

    date = score.index[0]
    assert out.loc[date, "spy"] == 1.0  # najwyzszy score wsrod OFENSYWNYCH
    assert out.drop(columns=["spy"]).loc[date].sum() == 0.0


def test_one_canary_negative_picks_best_defensive():
    # jeden ofensywny (vwo) ujemny -> risk-off, wybierz najlepszy z DEFENSYWNYCH
    row = {"spy": 0.05, "efa": 0.02, "vwo": -0.01, "agg": 0.03, "shy": 0.01, "ief": 0.04, "lqd": 0.02}
    score = _score([row])
    tw = _dummy_target_weights(score)

    out = vaa_canary(tw, None, {}, score, {"offensive_assets": OFFENSIVE, "defensive_assets": DEFENSIVE})

    date = score.index[0]
    assert out.loc[date, "ief"] == 1.0  # najwyzszy score wsrod DEFENSYWNYCH
    assert out.drop(columns=["ief"]).loc[date].sum() == 0.0


def test_zero_score_counts_as_bad_breadth():
    # score dokladnie 0 (nie > 0) -> traktowane jako "zly kanarek"
    row = {"spy": 0.05, "efa": 0.0, "vwo": 0.02, "agg": 0.03, "shy": 0.01, "ief": 0.01, "lqd": 0.05}
    score = _score([row])
    tw = _dummy_target_weights(score)

    out = vaa_canary(tw, None, {}, score, {"offensive_assets": OFFENSIVE, "defensive_assets": DEFENSIVE})

    date = score.index[0]
    assert out.loc[date, "lqd"] == 1.0  # risk-off mimo ze wiekszosc ofensywnych dodatnia


def test_nan_score_defaults_to_full_cash():
    row_nan = {t: np.nan for t in OFFENSIVE + DEFENSIVE}
    score = _score([row_nan])
    tw = _dummy_target_weights(score)

    out = vaa_canary(tw, None, {}, score, {"offensive_assets": OFFENSIVE, "defensive_assets": DEFENSIVE})

    date = score.index[0]
    assert out.loc[date, "_CASH"] == 1.0
    assert out.drop(columns=["_CASH"]).loc[date].sum() == 0.0


def test_switches_regime_across_periods():
    rows = [
        {"spy": 0.05, "efa": 0.02, "vwo": 0.01, "agg": 0.03, "shy": 0.01, "ief": 0.04, "lqd": 0.02},  # risk-on
        {"spy": -0.02, "efa": 0.02, "vwo": 0.01, "agg": 0.03, "shy": 0.01, "ief": 0.04, "lqd": 0.02},  # risk-off
    ]
    score = _score(rows)
    tw = _dummy_target_weights(score)

    out = vaa_canary(tw, None, {}, score, {"offensive_assets": OFFENSIVE, "defensive_assets": DEFENSIVE})

    assert out.loc[score.index[0], "spy"] == 1.0
    assert out.loc[score.index[1], "ief"] == 1.0


def test_full_chain_on_real_data(us_data_dir):
    from engine_v2.blocks.asset_scoring import REGISTRY as ASSET_SCORING_REGISTRY
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY

    universe = ["spy.us", "efa.us", "vwo.us", "agg.us", "shy.us", "ief.us", "lqd.us"]
    stooq_csv = LOADER_REGISTRY["stooq_csv"]
    momentum_monthly = INDICATORS_REGISTRY["momentum_monthly"]
    weighted_sum = ASSET_SCORING_REGISTRY["weighted_sum"]

    md = stooq_csv(universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    indicator_set = {
        "mom_1": momentum_monthly(md, {"window": 1}),
        "mom_3": momentum_monthly(md, {"window": 3}),
        "mom_6": momentum_monthly(md, {"window": 6}),
        "mom_12": momentum_monthly(md, {"window": 12}),
    }
    eligibility = pd.DataFrame(True, index=md.prices.index, columns=md.prices.columns)
    score = weighted_sum(
        md, indicator_set, eligibility,
        {"weights": {"mom_1": 12 / 19, "mom_3": 4 / 19, "mom_6": 2 / 19, "mom_12": 1 / 19}},
    )
    tw = pd.DataFrame(0.0, index=score.index, columns=list(score.columns) + ["_CASH"])

    offensive = ["spy.us", "efa.us", "vwo.us", "agg.us"]
    defensive = ["shy.us", "ief.us", "lqd.us"]
    out = vaa_canary(tw, md, indicator_set, score, {"offensive_assets": offensive, "defensive_assets": defensive})

    assert (out.sum(axis=1) - 1.0).abs().max() < 1e-9
    # kazdy wiersz ma dokladnie jedno aktywo (albo cash) z waga 1.0
    assert ((out == 1.0).sum(axis=1) <= 1).all()
    # w historii musialy wystapic oba rezymy (risk-on i risk-off) - inaczej test nic nie sprawdza
    assert out[offensive].sum(axis=1).gt(0).any()
    assert out[defensive].sum(axis=1).gt(0).any()
