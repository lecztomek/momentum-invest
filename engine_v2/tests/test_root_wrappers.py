"""
Testy dla cienkich wrapperow w korzeniu repo (`run_one.py`, `monthly_report.py`) - user: "Czemu
nie ma tego run one w glownym katalogu jak run pipeline dla starego engine". Cala logika juz jest
przetestowana w `test_run_one.py`/`test_monthly_report.py` - tu sprawdzamy TYLKO, ze wrapper w
korzeniu faktycznie odpala te sama logike (delegacja dziala, nie duplikuje kodu).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_root_wrappers.py -v
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_root_run_one_wrapper_works():
    result = subprocess.run(
        [sys.executable, "run_one.py", "gpm_mid_10"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    assert "gpm_mid_10" in result.stdout
    assert "CAGR" in result.stdout


def test_root_monthly_report_wrapper_works(tmp_path):
    out_path = tmp_path / "gpm_mid_10.csv"
    result = subprocess.run(
        [sys.executable, "monthly_report.py", "gpm_mid_10", "--out", str(out_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    assert out_path.exists()
