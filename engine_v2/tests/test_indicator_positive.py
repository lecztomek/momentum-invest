"""
Testy regresyjne ASSET FILTERS ("indicator_positive").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_indicator_positive.py -v
"""

import pandas as pd
import pytest

from engine_v2.blocks.asset_filters import REGISTRY as ASSET_FILTERS_REGISTRY
from engine_v2.types import MarketData

indicator_positive = ASSET_FILTERS_REGISTRY["indicator_positive"]


def _market_data_and_indicator():
    idx = pd.date_range("2021-01-01", periods=3, freq="MS")
    prices = pd.DataFrame({"a": 1.0, "b": 1.0, "c": 1.0}, index=idx)
    momentum = pd.DataFrame(
        {"a": [0.05, -0.01, 0.02], "b": [-0.02, 0.03, -0.01], "c": [0.0, 0.01, -0.005]}, index=idx
    )
    return MarketData(prices=prices, returns=prices.pct_change()), {"mom_12": momentum}


def test_requires_indicator_key():
    md, indicator_set = _market_data_and_indicator()
    with pytest.raises(ValueError, match="indicator_key"):
        indicator_positive(md, indicator_set, {})


def test_unknown_indicator_key_raises():
    md, indicator_set = _market_data_and_indicator()
    with pytest.raises(ValueError, match="Brak wskaznika"):
        indicator_positive(md, indicator_set, {"indicator_key": "nope"})


def test_default_threshold_zero():
    md, indicator_set = _market_data_and_indicator()
    mask = indicator_positive(md, indicator_set, {"indicator_key": "mom_12"})

    assert mask["a"].tolist() == [True, False, True]
    assert mask["b"].tolist() == [False, True, False]
    assert mask["c"].tolist() == [False, True, False]  # 0.0 nie jest > 0


def test_custom_threshold():
    md, indicator_set = _market_data_and_indicator()
    mask = indicator_positive(md, indicator_set, {"indicator_key": "mom_12", "threshold": 0.02})

    assert mask["a"].tolist() == [True, False, False]


def test_assets_scope_restricts_to_subset():
    md, indicator_set = _market_data_and_indicator()
    mask = indicator_positive(
        md, indicator_set, {"indicator_key": "mom_12", "assets": ["a"]}
    )

    assert mask["a"].tolist() == [True, False, True]
    assert mask["b"].all()  # poza zakresem - zawsze True
    assert mask["c"].all()
