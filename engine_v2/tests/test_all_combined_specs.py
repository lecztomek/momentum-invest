"""
Testy regresyjne OGOLNE dla WSZYSTKICH strategies_v2/*/combined_spec.json - dotad kazdy portfel
laczony mial (najwyzej) dedykowany test dla siebie (albo zaden - patrz README "Uwaga o pokryciu
testami per-strategia"). Ten plik automatycznie odkrywa KAZDY zapisany combined_spec.json w repo i
sprawdza go end-to-end na realnych danych - nowy portfel dodany do strategies_v2/ automatycznie
dostaje to samo minimum regresji, bez potrzeby pisania nowego pliku testowego.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_all_combined_specs.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.combined_pipeline import run_combined_pipeline
from engine_v2.combined_spec import CombinedSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
STRATEGIES_DIR = REPO_ROOT / "strategies_v2"

COMBINED_SPEC_PATHS = sorted(STRATEGIES_DIR.glob("*/combined_spec.json"))


def _ids(path: Path) -> str:
    return path.parent.name


@pytest.mark.parametrize("combined_spec_path", COMBINED_SPEC_PATHS, ids=_ids)
def test_combined_spec_is_valid(combined_spec_path):
    combined_spec = CombinedSpec.load(combined_spec_path)
    assert combined_spec.validate() == []


@pytest.mark.parametrize("combined_spec_path", COMBINED_SPEC_PATHS, ids=_ids)
def test_combined_spec_runs_end_to_end_on_real_data(combined_spec_path, us_data_dir):
    combined_spec = CombinedSpec.load(combined_spec_path)

    final_portfolio = run_combined_pipeline(combined_spec, combined_spec_path.parent)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 0
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)


def test_at_least_all_known_combined_specs_discovered():
    """Sanity check - lapie przypadek gdyby glob z jakiegos powodu przestal cokolwiek znajdowac
    (np. zmiana struktury folderow) zamiast po cichu przepuscic 0 testow."""
    discovered_names = {p.parent.name for p in COMBINED_SPEC_PATHS}
    assert len(discovered_names) >= 20
