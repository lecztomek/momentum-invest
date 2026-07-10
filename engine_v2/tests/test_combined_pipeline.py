"""
Testy regresyjne COMBINED PIPELINE - end-to-end na prawdziwych danych: laczy example_v0 (60%)
i example_v0_b (40%) przez COMBINER, kazda strategia z WLASNYM execution/histereza (patrz
combined_pipeline.py - COMBINER laczy juz WYKONANE wagi, nie surowy target).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_combined_pipeline.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.combined_pipeline import run_combined_pipeline
from engine_v2.combined_spec import CombinedSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
COMBINED_SPEC_PATH = REPO_ROOT / "strategies_v2" / "combined_example" / "combined_spec.json"


def _load_combined_spec_with_real_data(us_data_dir, us_universe):
    combined_spec = CombinedSpec.load(COMBINED_SPEC_PATH)

    # podmieniamy universe/data_dir na te z fixture'ow (te same wartosci co w plikach, ale
    # przez fixture zeby test byl niezalezny od tego czy dane akurat sa w repo)
    from engine_v2.spec import StrategySpec

    base_dir = COMBINED_SPEC_PATH.parent
    for rel_path in combined_spec.strategy_spec_paths:
        strategy_spec = StrategySpec.load(base_dir / rel_path)
        assert strategy_spec.universe == us_universe
        assert strategy_spec.base_params["data_loader"]["data_dir"] == "data/us"

    return combined_spec, base_dir


def test_invalid_combined_spec_raises():
    spec = CombinedSpec(name="x", hypothesis="y", strategy_spec_paths=["only_one.json"], combiner="c")
    with pytest.raises(ValueError, match="niepoprawny"):
        run_combined_pipeline(spec, Path("."))


def test_combined_pipeline_end_to_end_on_real_data(us_data_dir, us_universe):
    combined_spec, base_dir = _load_combined_spec_with_real_data(us_data_dir, us_universe)

    final_portfolio = run_combined_pipeline(combined_spec, base_dir)

    assert final_portfolio["date"].is_monotonic_increasing
    assert (final_portfolio["strategy"] == "combined_v0").all()
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
    assert final_portfolio["signal_changed"].any()


def test_combined_pipeline_matches_manual_capital_split(us_data_dir, us_universe):
    """Manualnie odpalamy PELNY solo pipeline kazdej strategii (WLACZNIE z jej WLASNYM
    execution/histereza), lacznie wazymy ich JUZ WYKONANE wagi 60/40 i porownujemy z tym co dal
    run_combined_pipeline - dowod ze COMBINER faktycznie miesza JUZ WYKONANE wagi (nie surowy
    target sprzed wlasnej histerezy kazdej strategii) wg zadeklarowanych capital_weights."""
    from engine_v2.combined_pipeline import _weights_used_to_wide
    from engine_v2.combiner import REGISTRY as COMBINER_REGISTRY
    from engine_v2.pipeline import run_strategy_pipeline
    from engine_v2.spec import StrategySpec

    combined_spec, base_dir = _load_combined_spec_with_real_data(us_data_dir, us_universe)

    strategy_weights_used = {}
    for rel_path in combined_spec.strategy_spec_paths:
        strategy_spec = StrategySpec.load(base_dir / rel_path)
        strategy_weights_used[strategy_spec.name] = _weights_used_to_wide(run_strategy_pipeline(strategy_spec))

    manual_combined, _effective_weights = COMBINER_REGISTRY["fixed_capital_weights"](
        strategy_weights_used, combined_spec.combiner_params
    )

    # spojnosc wewnetrzna: kazdy wiersz manualnego combined sumuje sie do 1
    assert (manual_combined.sum(axis=1) - 1.0).abs().max() < 1e-6

    # run_combined_pipeline() musi dac DOKLADNIE te same wagi co manualne polaczenie (zaden
    # dodatkowy execution juz sie nie dzieje na poziomie polaczonego portfela)
    final_portfolio = run_combined_pipeline(combined_spec, base_dir)
    for _, row in final_portfolio.iterrows():
        weights = json.loads(row["weights_used_json"])
        for ticker, weight in weights.items():
            assert weight == pytest.approx(manual_combined.loc[row["date"], ticker], abs=1e-9)
