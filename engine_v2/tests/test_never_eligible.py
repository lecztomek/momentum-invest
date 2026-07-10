"""
Testy regresyjne ASSET FILTERS ("never_eligible").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_never_eligible.py -v
"""

import pandas as pd
import pytest

from engine_v2.blocks.asset_filters import REGISTRY as ASSET_FILTERS_REGISTRY
from engine_v2.types import MarketData

never_eligible = ASSET_FILTERS_REGISTRY["never_eligible"]


def _md():
    idx = pd.date_range("2021-01-01", periods=3, freq="D")
    return MarketData(prices=pd.DataFrame({"a": 1.0, "b": 1.0, "c": 1.0}, index=idx), returns=pd.DataFrame())


def test_requires_assets():
    with pytest.raises(ValueError, match="assets"):
        never_eligible(_md(), {}, {})


def test_unknown_ticker_raises():
    with pytest.raises(ValueError, match="nieznany ticker"):
        never_eligible(_md(), {}, {"assets": ["zzz"]})


def test_marks_given_assets_always_false():
    mask = never_eligible(_md(), {}, {"assets": ["b"]})
    assert not mask["b"].any()
    assert mask["a"].all()
    assert mask["c"].all()
