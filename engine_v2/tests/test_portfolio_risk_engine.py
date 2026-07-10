"""
Testy regresyjne PORTFOLIO RISK ENGINE ("none").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_portfolio_risk_engine.py -v
"""

import pandas as pd

from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY

none = PORTFOLIO_RISK_ENGINE_REGISTRY["none"]


def test_none_returns_unchanged_copy():
    idx = pd.date_range("2021-01-01", periods=2, freq="MS")
    target_weights = pd.DataFrame({"a": [0.8, 0.5], "_CASH": [0.2, 0.5]}, index=idx)

    out = none(target_weights, market_data=None, indicator_set=None, score=None, params={})

    pd.testing.assert_frame_equal(out, target_weights)
    assert out is not target_weights  # kopia, nie ten sam obiekt
