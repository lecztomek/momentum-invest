"""
Testy regresyjne ALPHA WEIGHTING ("rounded_score_weights").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_rounded_score_weights.py -v
"""

import pandas as pd
import pytest

from engine_v2.blocks.alpha_weighting import REGISTRY as ALPHA_WEIGHTING_REGISTRY

rounded_score_weights = ALPHA_WEIGHTING_REGISTRY["rounded_score_weights"]


def _score_and_selection(scores_row, columns):
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    score = pd.DataFrame([scores_row], index=idx, columns=columns)
    selection = pd.DataFrame([[True] * len(columns)], index=idx, columns=columns)
    return score, selection


def test_no_selection_is_full_cash():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    score = pd.DataFrame({"a": [1.0]}, index=idx)
    selection = pd.DataFrame({"a": [False]}, index=idx)

    out = rounded_score_weights(selection, score, {}, {})
    assert out.loc[idx[0], "_CASH"] == pytest.approx(1.0)
    assert out.loc[idx[0], "a"] == 0.0


def test_equal_scores_split_as_evenly_as_10pct_blocks_allow():
    # 4 tickery remisuja (identyczny score), 10 blokow / 4 nie dzieli sie rowno (2.5 kazdy) -
    # largest remainder daje najblizszy mozliwy podzial: dwa po 20%, dwa po 30% (roznica 1 blok)
    score, selection = _score_and_selection([1.0, 1.0, 1.0, 1.0], ["stocks", "bonds", "gold", "commo"])
    out = rounded_score_weights(selection, score, {}, {})

    row = out.loc["2021-01-01"]
    assert row.sum() == pytest.approx(1.0)
    assert sorted(row[["stocks", "bonds", "gold", "commo"]].tolist()) == pytest.approx([0.2, 0.2, 0.3, 0.3])


def test_always_sums_to_one_and_respects_minimum_floor():
    # jedna klasa aktywow ma OGROMNA przewage score - reszta i tak dostaje minimum (1 blok = 10%)
    score, selection = _score_and_selection([100.0, 0.0, 0.0, 0.0], ["stocks", "bonds", "gold", "commo"])
    out = rounded_score_weights(selection, score, {}, {"round_to": 0.10, "min_weight_blocks": 1})

    row = out.loc["2021-01-01"]
    assert row["bonds"] == pytest.approx(0.10)
    assert row["gold"] == pytest.approx(0.10)
    assert row["commo"] == pytest.approx(0.10)
    assert row["stocks"] == pytest.approx(0.70)  # reszta (7 blokow z 10) idzie do najsilniejszego
    assert row.sum() == pytest.approx(1.0)


def test_proportional_tilt_uses_largest_remainder_to_hit_exact_sum():
    # 3 wybrane, min_weight_blocks=0 - czysto proporcjonalnie do score, ale suma MUSI dac 10 blokow
    score, selection = _score_and_selection([3.0, 2.0, 1.0], ["a", "b", "c"])
    out = rounded_score_weights(selection, score, {}, {"round_to": 0.10, "min_weight_blocks": 0})

    row = out.loc["2021-01-01"]
    # a-min=2, b-min=1, c-min=0 -> sily 2:1:0, ale wszystkie ujemne przesuniete do min=0 dla c
    # (strength: a=2, b=1, c=0) -> idealne bloki (z 10): a=6.67, b=3.33, c=0 -> largest remainder
    total_blocks = round(row["a"] / 0.10) + round(row["b"] / 0.10) + round(row["c"] / 0.10)
    assert total_blocks == 10
    assert row.sum() == pytest.approx(1.0)
    assert row["a"] > row["b"] > row["c"]


def test_raises_when_minimum_floor_exceeds_total_blocks():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    columns = [f"t{i}" for i in range(12)]  # 12 tickerow
    score = pd.DataFrame([[1.0] * 12], index=idx, columns=columns)
    selection = pd.DataFrame([[True] * 12], index=idx, columns=columns)

    with pytest.raises(ValueError, match="min_weight_blocks"):
        rounded_score_weights(selection, score, {}, {"round_to": 0.10, "min_weight_blocks": 1})


def test_invalid_round_to_raises():
    score, selection = _score_and_selection([1.0], ["a"])
    with pytest.raises(ValueError, match="round_to"):
        rounded_score_weights(selection, score, {}, {"round_to": 0.0})

    with pytest.raises(ValueError, match="round_to"):
        rounded_score_weights(selection, score, {}, {"round_to": 0.03})


def test_deterministic_tie_break_alphabetical():
    # b i c maja identyczny score (remis) - z 1 dodatkowym blokiem do rozdania powinien dostac
    # go ten alfabetycznie pierwszy z remisujacych ("b" przed "c")
    score, selection = _score_and_selection([5.0, 1.0, 1.0], ["a", "b", "c"])
    out = rounded_score_weights(selection, score, {}, {"round_to": 0.10, "min_weight_blocks": 0})

    row = out.loc["2021-01-01"]
    assert row["b"] >= row["c"]
    assert row.sum() == pytest.approx(1.0)


def test_full_chain_on_real_data(us_data_dir, us_universe):
    from engine_v2.blocks.asset_scoring import REGISTRY as ASSET_SCORING_REGISTRY
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
    from engine_v2.blocks.selector import REGISTRY as SELECTOR_REGISTRY

    stooq_csv = LOADER_REGISTRY["stooq_csv"]
    momentum_monthly = INDICATORS_REGISTRY["momentum_monthly"]
    weighted_sum = ASSET_SCORING_REGISTRY["weighted_sum"]
    top_n = SELECTOR_REGISTRY["top_n"]

    md = stooq_csv(us_universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    indicator_set = {"mom_6": momentum_monthly(md, {"window": 6})}
    eligibility = pd.DataFrame(True, index=md.prices.index, columns=md.prices.columns)
    score = weighted_sum(md, indicator_set, eligibility, {"weights": {"mom_6": 1.0}})
    selection = top_n(score, {"top_n": len(us_universe)})

    out = rounded_score_weights(selection, score, indicator_set, {"round_to": 0.10, "min_weight_blocks": 1})

    assert (out.sum(axis=1) - 1.0).abs().max() < 1e-9
    # kazda waga jest wielokrotnoscia 10%
    non_cash = out.drop(columns="_CASH")
    assert ((non_cash * 10).round(6) % 1 == 0).all().all()
