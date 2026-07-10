"""
Testy regresyjne OVERLAYS ("none").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_overlays.py -v
"""

import pandas as pd

from engine_v2.blocks.overlays import REGISTRY as OVERLAYS_REGISTRY
from engine_v2.types import MarketData, OverlayContext, PortfolioState

none = OVERLAYS_REGISTRY["none"]


def test_none_returns_unchanged_copy():
    row = pd.Series({"a": 0.8, "_CASH": 0.2})
    context = OverlayContext(
        date=pd.Timestamp("2021-01-01"),
        state=PortfolioState(),
        market_data=MarketData(prices=pd.DataFrame(), returns=pd.DataFrame()),
    )

    out = none(row, context, {})

    pd.testing.assert_series_equal(out, row)
    assert out is not row  # kopia, nie ten sam obiekt
