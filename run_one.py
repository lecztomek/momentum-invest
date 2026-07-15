"""
Cienki wrapper w korzeniu repo dla `engine_v2/run_one.py` - user: "Czemu nie ma tego run one w
glownym katalogu jak run pipeline dla starego engine" (por. `run_global_pipeline.py`, glowny
punkt wejscia starego `engine/`). Cala logika zyje w `engine_v2/run_one.py` (engine_v2 to
samodzielny pakiet), ten plik tylko pozwala odpalic z korzenia bez `-m`:

  .venv/bin/python3 run_one.py gpm_mid_10
  .venv/bin/python3 run_one.py --list
"""

from engine_v2.run_one import main

if __name__ == "__main__":
    main()
