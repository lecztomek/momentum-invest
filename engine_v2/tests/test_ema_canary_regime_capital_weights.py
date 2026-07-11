"""
Testy COMBINER ("ema_canary_regime_capital_weights") - user: dokladny opis 3-poziomowego rezimu
(risk-on/neutralny/risk-off) na bazie ema7_16 (momentum) + kanarek ema5_12, z histereza
"maksymalnie jeden poziom na rebalans".

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_ema_canary_regime_capital_weights.py -v
"""

import pandas as pd
import pytest

from engine_v2.combiner import REGISTRY as COMBINER_REGISTRY
from engine_v2.combiner.ema_canary_regime_capital_weights import (
    apply_level_hysteresis,
    raw_regime_level,
)

ema_canary_regime_capital_weights = COMBINER_REGISTRY["ema_canary_regime_capital_weights"]


# ---------------------------------------------------------------- raw_regime_level (logika czysta)

def test_both_positive_is_risk_on_level_2():
    idx = pd.RangeIndex(1)
    level = raw_regime_level(pd.Series([True], index=idx), pd.Series([True], index=idx))
    assert level.iloc[0] == 2


def test_both_negative_is_risk_off_level_0():
    idx = pd.RangeIndex(1)
    level = raw_regime_level(pd.Series([False], index=idx), pd.Series([False], index=idx))
    assert level.iloc[0] == 0


def test_only_momentum_positive_is_neutral_level_1():
    idx = pd.RangeIndex(1)
    level = raw_regime_level(pd.Series([True], index=idx), pd.Series([False], index=idx))
    assert level.iloc[0] == 1


def test_only_canary_positive_is_neutral_level_1():
    idx = pd.RangeIndex(1)
    level = raw_regime_level(pd.Series([False], index=idx), pd.Series([True], index=idx))
    assert level.iloc[0] == 1


# ---------------------------------------------------------------- apply_level_hysteresis (logika czysta)

def test_no_jump_when_within_max_change():
    raw = pd.Series([1, 2, 1, 0], index=range(4))
    realized = apply_level_hysteresis(raw, max_change=1, start_level=1)
    assert list(realized) == [1, 2, 1, 0]


def test_caps_direct_jump_from_risk_on_to_risk_off():
    """Rdzen wymagania usera - "bez przejscia bezposrednio z 65/35 do 25/75"."""
    raw = pd.Series([2, 0], index=range(2))  # risk-on -> od razu risk-off
    realized = apply_level_hysteresis(raw, max_change=1, start_level=2)
    assert list(realized) == [2, 1]  # zatrzymuje sie na neutralnym, NIE skacze do 0


def test_multi_step_transition_takes_multiple_periods():
    raw = pd.Series([0, 0, 0], index=range(3))
    realized = apply_level_hysteresis(raw, max_change=1, start_level=2)
    assert list(realized) == [1, 0, 0]  # potrzebuje 2 okresow, zeby dojsc z 2 do 0


def test_start_level_used_for_first_decision():
    raw = pd.Series([2], index=range(1))
    realized = apply_level_hysteresis(raw, max_change=1, start_level=0)
    assert list(realized) == [1]  # z 0 do 2 tez ograniczone do +1


def test_max_change_of_two_allows_direct_jump():
    raw = pd.Series([2, 0], index=range(2))
    realized = apply_level_hysteresis(raw, max_change=2, start_level=2)
    assert list(realized) == [2, 0]


# ---------------------------------------------------------------- combiner - walidacja/bledy

def _target_weights(values, columns, index):
    return pd.DataFrame(values, index=index, columns=columns)


def _base_params(**overrides):
    params = {
        "strategy_risk_on": "best17_a_v0",
        "strategy_other": "gpm_v0",
        "data_dir": "data/us",
        "momentum_assets": ["xlk.us", "ivv.us", "dbc.us", "iau.us"],
        "momentum_ema_fast": 7,
        "momentum_ema_slow": 16,
        "canary_assets": ["vt.us", "xlk.us"],
        "canary_ema_fast": 5,
        "canary_ema_slow": 12,
        "canary_bad_threshold": -0.02,
        "canary_max_bad_count": 0,
        "risk_on_weight": 0.65,
        "neutral_weight": 0.45,
        "risk_off_weight": 0.25,
    }
    params.update(overrides)
    return params


def test_requires_all_params():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {"best17_a_v0": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx)}
    with pytest.raises(ValueError, match="wymaga params"):
        ema_canary_regime_capital_weights(tw, {"strategy_risk_on": "best17_a_v0"})


def test_requires_exactly_two_named_strategies():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    tw = {
        "best17_a_v0": _target_weights([[1.0, 0.0]] * 2, ["x", "_CASH"], idx),
        "unrelated": _target_weights([[1.0, 0.0]] * 2, ["y", "_CASH"], idx),
    }
    with pytest.raises(ValueError, match="DOKLADNIE dwie strategie"):
        ema_canary_regime_capital_weights(tw, _base_params())


# ---------------------------------------------------------------- combiner - integracja na realnych danych

def test_real_data_weights_sum_to_one_and_only_three_levels(us_data_dir):
    idx = pd.date_range("2008-07-01", "2026-06-01", freq="MS")
    tw_best = _target_weights([[1.0, 0.0]] * len(idx), ["xlk.us", "_CASH"], idx)
    tw_gpm = _target_weights([[1.0, 0.0]] * len(idx), ["spy.us", "_CASH"], idx)

    combined, effective_weights = ema_canary_regime_capital_weights(
        {"best17_a_v0": tw_best, "gpm_v0": tw_gpm},
        _base_params(data_dir=str(us_data_dir)),
    )

    for date in idx:
        assert combined.loc[date].sum() == pytest.approx(1.0)
        assert effective_weights.loc[date].sum() == pytest.approx(1.0)

    observed_weights = set(effective_weights["best17_a_v0"].round(2))
    assert observed_weights <= {0.25, 0.45, 0.65}
    # w realnej historii 2008-2026 musial wystapic co najmniej risk-on (ema7_16+kanarek oba
    # dodatnie przez wiekszosc historii) i neutralny (dokladnie jeden dodatni, np. kanarek zly
    # ale momentum jeszcze trzyma). Prawdziwy RAW risk-off (oba ujemne naraz) wystapil
    # empirycznie TYLKO w 2005 (przed poczatkiem tego okna) - patrz CHANGELOG (33) - wiec
    # risk_off_weight w praktyce nigdy nie zadziala w tym konkretnym oknie backtestu, co jest
    # oczekiwanym, udokumentowanym wynikiem, nie usterka.
    assert 0.65 in observed_weights
    assert 0.45 in observed_weights


def test_real_data_never_jumps_more_than_one_level_per_month(us_data_dir):
    idx = pd.date_range("2008-07-01", "2026-06-01", freq="MS")
    tw_best = _target_weights([[1.0, 0.0]] * len(idx), ["xlk.us", "_CASH"], idx)
    tw_gpm = _target_weights([[1.0, 0.0]] * len(idx), ["spy.us", "_CASH"], idx)

    combined, effective_weights = ema_canary_regime_capital_weights(
        {"best17_a_v0": tw_best, "gpm_v0": tw_gpm},
        _base_params(data_dir=str(us_data_dir)),
    )

    level_by_weight = {0.25: 0, 0.45: 1, 0.65: 2}
    levels = effective_weights["best17_a_v0"].round(2).map(level_by_weight)
    level_diffs = levels.diff().dropna()
    assert level_diffs.abs().max() <= 1
