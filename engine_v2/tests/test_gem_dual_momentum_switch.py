"""
Testy regresyjne PORTFOLIO RISK ENGINE ("gem_dual_momentum_switch") - rekonstrukcja "The One".

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gem_dual_momentum_switch.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY

gem_switch = PORTFOLIO_RISK_ENGINE_REGISTRY["gem_dual_momentum_switch"]

RISK_ON = ["spy", "vea", "vwo"]
RISK_OFF = ["lqd", "ief", "tlt"]
ALL = RISK_ON + RISK_OFF


def _score(row):
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    return pd.DataFrame([row], index=idx, columns=ALL)


def _mom12(row):
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    return pd.DataFrame([row], index=idx, columns=ALL)


def _tw(score):
    return pd.DataFrame(0.0, index=score.index, columns=list(score.columns) + ["_CASH"])


def _params(**overrides):
    base = {"risk_on_assets": RISK_ON, "risk_off_assets": RISK_OFF, "mom_12_key": "mom_12"}
    base.update(overrides)
    return base


def test_requires_all_params():
    score = _score({t: 0.01 for t in ALL})
    tw = _tw(score)
    with pytest.raises(ValueError, match="risk_on_assets"):
        gem_switch(tw, None, {"mom_12": score}, score, {})


def test_unknown_ticker_raises():
    score = _score({t: 0.01 for t in ALL})
    tw = _tw(score)
    with pytest.raises(ValueError, match="brak tickerow"):
        gem_switch(tw, None, {"mom_12": score}, score, _params(risk_on_assets=["zzz"]))


def test_missing_mom12_indicator_raises():
    score = _score({t: 0.01 for t in ALL})
    tw = _tw(score)
    with pytest.raises(ValueError, match="brak wskaznika"):
        gem_switch(tw, None, {}, score, _params())


def test_positive_absolute_and_relative_momentum_goes_risk_on():
    # best_on (vwo=0.06) > 0 i > best_off (tlt=0.02) -> risk-on w vwo
    row = {"spy": 0.03, "vea": 0.01, "vwo": 0.06, "lqd": 0.01, "ief": 0.015, "tlt": 0.02}
    score = _score(row)
    tw = _tw(score)

    out = gem_switch(tw, None, {"mom_12": score}, score, _params())

    date = score.index[0]
    assert out.loc[date, "vwo"] == 1.0
    assert out.drop(columns=["vwo"]).loc[date].sum() == 0.0


def test_best_on_positive_but_worse_than_best_off_goes_risk_off():
    # best_on (spy=0.02) > 0, ale best_off (tlt=0.05) jest lepszy -> risk-off
    row = {"spy": 0.02, "vea": 0.0, "vwo": -0.01, "lqd": 0.03, "ief": 0.04, "tlt": 0.05}
    score = _score(row)
    mom12 = _mom12({"spy": 0.02, "vea": 0.0, "vwo": -0.01, "lqd": 0.03, "ief": 0.04, "tlt": 0.05})
    tw = _tw(score)

    out = gem_switch(tw, None, {"mom_12": mom12}, score, _params())

    date = score.index[0]
    assert out.loc[date, "tlt"] == 1.0  # najlepszy risk-off, dodatni wlasny mom_12 -> nie cash


def test_negative_absolute_momentum_and_negative_bond_momentum_goes_cash():
    # best_on ujemny -> risk-off; best_off (tlt) ma ujemny WLASNY 12m momentum -> cash
    row = {"spy": -0.02, "vea": -0.03, "vwo": -0.05, "lqd": -0.01, "ief": -0.02, "tlt": -0.005}
    score = _score(row)
    mom12 = _mom12(row)  # ten sam ujemny wzorzec
    tw = _tw(score)

    out = gem_switch(tw, None, {"mom_12": mom12}, score, _params())

    date = score.index[0]
    assert out.loc[date, "_CASH"] == 1.0
    assert out.drop(columns=["_CASH"]).loc[date].sum() == 0.0


def test_risk_off_but_bond_positive_avoids_cash():
    row = {"spy": -0.02, "vea": -0.03, "vwo": -0.05, "lqd": 0.01, "ief": 0.02, "tlt": 0.04}
    score = _score(row)
    mom12 = _mom12(row)
    tw = _tw(score)

    out = gem_switch(tw, None, {"mom_12": mom12}, score, _params())

    date = score.index[0]
    assert out.loc[date, "tlt"] == 1.0
    assert out.loc[date, "_CASH"] == 0.0


def test_nan_score_defaults_to_cash():
    row = {t: np.nan for t in ALL}
    score = _score(row)
    mom12 = _mom12(row)
    tw = _tw(score)

    out = gem_switch(tw, None, {"mom_12": mom12}, score, _params())

    date = score.index[0]
    assert out.loc[date, "_CASH"] == 1.0


def test_full_chain_on_real_data(us_data_dir):
    from engine_v2.blocks.asset_scoring import REGISTRY as ASSET_SCORING_REGISTRY
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY

    universe = ["spy.us", "vea.us", "vwo.us", "lqd.us", "ief.us", "tlt.us"]
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

    risk_on = ["spy.us", "vea.us", "vwo.us"]
    risk_off = ["lqd.us", "ief.us", "tlt.us"]
    out = gem_switch(
        tw, md, indicator_set, score,
        {"risk_on_assets": risk_on, "risk_off_assets": risk_off, "mom_12_key": "mom_12"},
    )

    assert (out.sum(axis=1) - 1.0).abs().max() < 1e-9
    assert ((out == 1.0).sum(axis=1) <= 1).all()
    # w historii musialy wystapic wszystkie 3 rezymy (on / off / cash)
    assert out[risk_on].sum(axis=1).gt(0).any()
    assert out[risk_off].sum(axis=1).gt(0).any()
    assert out["_CASH"].gt(0).any()
