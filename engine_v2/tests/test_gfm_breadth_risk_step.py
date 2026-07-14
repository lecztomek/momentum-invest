"""
Testy regresyjne PORTFOLIO RISK ENGINE ("gfm_breadth_risk_step") - user: "Zmieniamy w GFM tylko
mechanizm risk-off: zamiast prostego SPY 12M > 0, liczymy szerokosc rynku... ryzyko zmniejszamy
stopniowo, np. 100% / 75% / 50% / 25% / 0%... czesc defensywna wybiera najlepszy z SHY, IEF, TLT".

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gfm_breadth_risk_step.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY

breadth_step = PORTFOLIO_RISK_ENGINE_REGISTRY["gfm_breadth_risk_step"]

# 8 aktywow ryzykownych (latwe do liczenia szerokosci w 4 progach: 2/4/6, kroki co 2)
RISKY = ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"]
PROTECTIVE = ["shy", "ief", "tlt"]
ALL = RISKY + PROTECTIVE


def _df(row):
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    return pd.DataFrame([row], index=idx, columns=ALL)


def _tw(df):
    return pd.DataFrame(0.0, index=df.index, columns=list(df.columns) + ["_CASH"])


def _params(**overrides):
    base = {
        "risky_assets": RISKY,
        "protective_assets": PROTECTIVE,
        "top_n_risky": 3,
        "risky_mom_keys": ["mom_3", "mom_6", "mom_12"],
        "protective_mom_keys": ["mom_1", "mom_3", "mom_6", "mom_12"],
        "breadth_thresholds": [2, 4, 6, 8],
        "risky_shares": [0.0, 0.25, 0.5, 0.75, 1.0],
    }
    base.update(overrides)
    return base


def _row_with_n_positive(n, positive_value=0.05, negative_value=-0.05):
    return {t: (positive_value if i < n else negative_value) for i, t in enumerate(RISKY)}


def _indicators_from_risky_row(risky_row, protective_row=None):
    protective_row = protective_row or {t: 0.0 for t in PROTECTIVE}
    row = {**risky_row, **protective_row}
    return {k: _df(row) for k in ["mom_1", "mom_3", "mom_6", "mom_12"]}


def test_requires_all_params():
    tw = _tw(_df({t: 0.0 for t in ALL}))
    with pytest.raises(ValueError, match="risky_assets"):
        breadth_step(tw, None, _indicators_from_risky_row(_row_with_n_positive(8)), None, {})


def test_requires_breadth_params():
    tw = _tw(_df({t: 0.0 for t in ALL}))
    params = _params()
    del params["breadth_thresholds"]
    with pytest.raises(ValueError, match="breadth_thresholds"):
        breadth_step(tw, None, _indicators_from_risky_row(_row_with_n_positive(8)), None, params)


def test_risky_shares_length_must_match_thresholds_plus_one():
    tw = _tw(_df({t: 0.0 for t in ALL}))
    with pytest.raises(ValueError, match="len\\(risky_shares\\)"):
        breadth_step(
            tw, None, _indicators_from_risky_row(_row_with_n_positive(8)), None,
            _params(risky_shares=[0.0, 1.0]),
        )


def test_unknown_ticker_raises():
    tw = _tw(_df({t: 0.0 for t in ALL}))
    with pytest.raises(ValueError, match="brak tickerow"):
        breadth_step(tw, None, _indicators_from_risky_row(_row_with_n_positive(8)), None, _params(risky_assets=["zzz"]))


def test_missing_indicator_raises():
    tw = _tw(_df({t: 0.0 for t in ALL}))
    indicators = _indicators_from_risky_row(_row_with_n_positive(8))
    del indicators["mom_6"]
    with pytest.raises(ValueError, match="brak wskaznikow"):
        breadth_step(tw, None, indicators, None, _params())


@pytest.mark.parametrize(
    "n_positive, expected_risky_share",
    [(0, 0.0), (1, 0.0), (2, 0.25), (3, 0.25), (4, 0.5), (5, 0.5), (6, 0.75), (7, 0.75), (8, 1.0)],
)
def test_breadth_buckets_give_expected_stepped_risky_share(n_positive, expected_risky_share):
    risky_row = _row_with_n_positive(n_positive)
    indicators = _indicators_from_risky_row(risky_row, {"shy": 0.01, "ief": 0.03, "tlt": 0.02})
    tw = _tw(indicators["mom_1"])
    date = indicators["mom_1"].index[0]

    out = breadth_step(tw, None, indicators, None, _params())

    risky_total = out.loc[date, RISKY].sum()
    assert risky_total == pytest.approx(expected_risky_share)
    assert out.loc[date].sum() == pytest.approx(1.0)


def test_protective_share_goes_entirely_to_best_of_three_candidates():
    # szerokosc n=0 -> risky_share=0.0, cala reszta w najlepszego z shy/ief/tlt (ief tu najlepszy)
    risky_row = _row_with_n_positive(0)
    indicators = _indicators_from_risky_row(risky_row, {"shy": 0.01, "ief": 0.03, "tlt": 0.02})
    tw = _tw(indicators["mom_1"])
    date = indicators["mom_1"].index[0]

    out = breadth_step(tw, None, indicators, None, _params())

    assert out.loc[date, "ief"] == pytest.approx(1.0)
    assert out.loc[date, "shy"] == 0.0
    assert out.loc[date, "tlt"] == 0.0


def test_risky_share_split_equally_among_top_n_risky():
    # szerokosc n=8 -> risky_share=1.0, top_n_risky=3 najlepsze wg score
    risky_row = {"r1": 0.05, "r2": 0.04, "r3": 0.03, "r4": 0.02, "r5": 0.01, "r6": 0.01, "r7": 0.01, "r8": 0.01}
    indicators = _indicators_from_risky_row(risky_row)
    tw = _tw(indicators["mom_1"])
    date = indicators["mom_1"].index[0]

    out = breadth_step(tw, None, indicators, None, _params())

    held = set(out.loc[date][out.loc[date] > 1e-9].index)
    assert held == {"r1", "r2", "r3"}
    for t in held:
        assert out.loc[date, t] == pytest.approx(1.0 / 3.0)


def test_nan_risky_scores_do_not_count_toward_breadth_or_selection():
    risky_row = {"r1": 0.05, "r2": np.nan, "r3": 0.03, "r4": np.nan, "r5": -0.1, "r6": -0.1, "r7": -0.1, "r8": -0.1}
    indicators = _indicators_from_risky_row(risky_row, {"shy": 0.01, "ief": 0.02, "tlt": 0.03})
    tw = _tw(indicators["mom_1"])
    date = indicators["mom_1"].index[0]

    # tylko r1, r3 dodatnie -> n=2 -> risky_share=0.25
    out = breadth_step(tw, None, indicators, None, _params())
    assert out.loc[date, RISKY].sum() == pytest.approx(0.25)
    assert out.loc[date, "r2"] == 0.0
    assert out.loc[date, "r4"] == 0.0


def test_no_eligible_protective_candidate_goes_to_cash():
    risky_row = _row_with_n_positive(0)
    indicators = _indicators_from_risky_row(risky_row, {"shy": np.nan, "ief": np.nan, "tlt": np.nan})
    tw = _tw(indicators["mom_1"])
    date = indicators["mom_1"].index[0]

    out = breadth_step(tw, None, indicators, None, _params())

    assert out.loc[date, "_CASH"] == pytest.approx(1.0)


def test_no_eligible_risky_candidate_goes_to_cash():
    risky_row = {t: np.nan for t in RISKY}
    indicators = _indicators_from_risky_row(risky_row, {"shy": 0.01, "ief": 0.02, "tlt": 0.03})
    tw = _tw(indicators["mom_1"])
    date = indicators["mom_1"].index[0]

    # n=0 (brak dodatnich, NaN nie liczy sie) -> risky_share=0.0 -> caly kapital w protective, brak CASH
    out = breadth_step(tw, None, indicators, None, _params())
    assert out.loc[date, "_CASH"] == 0.0
    assert out.loc[date, "tlt"] == pytest.approx(1.0)  # tlt=0.03 najlepszy z shy/ief/tlt
