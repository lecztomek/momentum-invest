"""
Testy regresyjne PORTFOLIO RISK ENGINE ("gfm_risk_switch") - rekonstrukcja "Global Factor Model"
(GFM, inwestujdlugoterminowo.pl/global-factor-model-gfm/).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gfm_risk_switch.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY

gfm_switch = PORTFOLIO_RISK_ENGINE_REGISTRY["gfm_risk_switch"]

RISK_ON = ["a", "b", "c", "d"]
RISK_OFF = ["ief", "tlt"]
ALL = RISK_ON + RISK_OFF


def _df(row):
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    return pd.DataFrame([row], index=idx, columns=ALL)


def _tw(df):
    return pd.DataFrame(0.0, index=df.index, columns=list(df.columns) + ["_CASH"])


def _params(**overrides):
    base = {
        "risk_on_assets": RISK_ON,
        "risk_off_assets": RISK_OFF,
        "top_n": 2,
        "risk_on_mom_keys": ["mom_3", "mom_6", "mom_12"],
        "risk_off_mom_keys": ["mom_1", "mom_3", "mom_6", "mom_12"],
        "regime_indicator_key": "mom_12",
        "regime_ticker": "a",
        "regime_threshold": 0.0,
    }
    base.update(overrides)
    return base


def _flat_indicators(value=0.01):
    row = {t: value for t in ALL}
    return {
        "mom_1": _df(row),
        "mom_3": _df(row),
        "mom_6": _df(row),
        "mom_12": _df(row),
    }


def test_requires_all_params():
    tw = _tw(_df({t: 0.0 for t in ALL}))
    with pytest.raises(ValueError, match="risk_on_assets"):
        gfm_switch(tw, None, _flat_indicators(), None, {})


def test_requires_regime_params():
    tw = _tw(_df({t: 0.0 for t in ALL}))
    params = _params()
    del params["regime_indicator_key"]
    with pytest.raises(ValueError, match="regime_indicator_key"):
        gfm_switch(tw, None, _flat_indicators(), None, params)


def test_unknown_ticker_raises():
    tw = _tw(_df({t: 0.0 for t in ALL}))
    with pytest.raises(ValueError, match="brak tickerow"):
        gfm_switch(tw, None, _flat_indicators(), None, _params(risk_on_assets=["zzz"]))


def test_missing_indicator_raises():
    tw = _tw(_df({t: 0.0 for t in ALL}))
    indicators = _flat_indicators()
    del indicators["mom_6"]
    with pytest.raises(ValueError, match="brak wskaznikow"):
        gfm_switch(tw, None, indicators, None, _params())


def test_risk_on_selects_top_n_equal_weight():
    # regime (mom_12 na "a") dodatni -> risk-on; wybieramy top_n=2 wg (mom_3+mom_6+mom_12)/3
    indicators = {
        "mom_1": _df({"a": 0.05, "b": 0.05, "c": 0.05, "d": 0.05, "ief": 0.0, "tlt": 0.0}),
        "mom_3": _df({"a": 0.10, "b": 0.02, "c": 0.20, "d": 0.01, "ief": 0.0, "tlt": 0.0}),
        "mom_6": _df({"a": 0.10, "b": 0.02, "c": 0.20, "d": 0.01, "ief": 0.0, "tlt": 0.0}),
        "mom_12": _df({"a": 0.10, "b": 0.02, "c": 0.20, "d": 0.01, "ief": 0.0, "tlt": 0.0}),
    }
    tw = _tw(indicators["mom_1"])

    out = gfm_switch(tw, None, indicators, None, _params(top_n=2))

    date = indicators["mom_1"].index[0]
    # najlepsze 2 wg score_on: c (0.20) i a (0.10)
    assert out.loc[date, "c"] == pytest.approx(0.5)
    assert out.loc[date, "a"] == pytest.approx(0.5)
    assert out.loc[date, "b"] == 0.0
    assert out.loc[date, "d"] == 0.0
    assert out.loc[date, "ief"] == 0.0
    assert out.loc[date, "tlt"] == 0.0
    assert out.loc[date].sum() == pytest.approx(1.0)


def test_risk_off_goes_all_in_best_bond():
    # regime ujemny -> risk-off; ief bije tlt na (mom_1+mom_3+mom_6+mom_12)/4
    indicators = {
        "mom_1": _df({"a": -0.05, "b": 0.0, "c": 0.0, "d": 0.0, "ief": 0.03, "tlt": 0.01}),
        "mom_3": _df({"a": -0.05, "b": 0.0, "c": 0.0, "d": 0.0, "ief": 0.02, "tlt": 0.01}),
        "mom_6": _df({"a": -0.05, "b": 0.0, "c": 0.0, "d": 0.0, "ief": 0.02, "tlt": 0.01}),
        "mom_12": _df({"a": -0.05, "b": 0.0, "c": 0.0, "d": 0.0, "ief": 0.02, "tlt": 0.01}),
    }
    tw = _tw(indicators["mom_1"])

    out = gfm_switch(tw, None, indicators, None, _params())

    date = indicators["mom_1"].index[0]
    assert out.loc[date, "ief"] == pytest.approx(1.0)
    assert out.loc[date, "tlt"] == 0.0
    assert out.drop(columns=["ief"]).loc[date].sum() == pytest.approx(0.0)


def test_regime_threshold_boundary_is_risk_off():
    # regime dokladnie na progu (nie > prog) -> risk-off, nie risk-on
    indicators = _flat_indicators(value=0.0)
    indicators["mom_12"] = _df({"a": 0.0, "b": 0.0, "c": 0.0, "d": 0.0, "ief": 0.01, "tlt": 0.0})
    tw = _tw(indicators["mom_1"])

    out = gfm_switch(tw, None, indicators, None, _params(regime_threshold=0.0))

    date = indicators["mom_1"].index[0]
    assert out.loc[date, "ief"] == pytest.approx(1.0)


def test_nan_regime_defaults_to_risk_off():
    indicators = _flat_indicators()
    indicators["mom_12"] = _df({"a": np.nan, "b": 0.0, "c": 0.0, "d": 0.0, "ief": 0.02, "tlt": 0.01})
    tw = _tw(indicators["mom_1"])

    out = gfm_switch(tw, None, indicators, None, _params())

    date = indicators["mom_1"].index[0]
    assert out.loc[date, "ief"] == pytest.approx(1.0)


def test_all_nan_scores_default_to_cash():
    indicators = {k: _df({t: np.nan for t in ALL}) for k in ["mom_1", "mom_3", "mom_6", "mom_12"]}
    tw = _tw(indicators["mom_1"])

    out = gfm_switch(tw, None, indicators, None, _params())

    date = indicators["mom_1"].index[0]
    assert out.loc[date, "_CASH"] == pytest.approx(1.0)


def test_top_n_variants_gfm_3_4_5():
    row_common = {"ief": 0.0, "tlt": 0.0}
    on_scores = {"a": 0.05, "b": 0.04, "c": 0.03, "d": 0.02}
    indicators = {
        "mom_1": _df({**on_scores, **row_common}),
        "mom_3": _df({**on_scores, **row_common}),
        "mom_6": _df({**on_scores, **row_common}),
        "mom_12": _df({**on_scores, **row_common}),
    }
    tw = _tw(indicators["mom_1"])
    date = indicators["mom_1"].index[0]

    for top_n, expected_held in [(2, {"a", "b"}), (3, {"a", "b", "c"})]:
        out = gfm_switch(tw, None, indicators, None, _params(top_n=top_n))
        held = set(out.loc[date][out.loc[date] > 0].index) - {"_CASH"}
        assert held == expected_held
        assert out.loc[date].sum() == pytest.approx(1.0)
