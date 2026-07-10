# Changelog

Zapis istotnych zmian w projekcie, najnowsze na górze. Każdy wpis krótko: co się zmieniło i po co.

## 2026-07-10

- `strategies_v2/combined_best2/combined_spec.json`: nowy `CombinedSpec` łączący dwie
  dotychczas najlepsze strategie (`best17_a` - final CAGR ~19%, Sharpe ~1.03, brak rozjazdu
  train/OOS; `the_one` - jedyna strategia z lepszym OOS niż train), 50/50 kapitału, wspólna
  histereza 0.02. NIE uruchomione w tej sesji - brak `data/us` (gitignored, dane nie są w
  repo), więc brak realnego wyniku liczbowego na razie.
- `engine_v2/grid_sweep.py`: `allowed_param_families` wspiera teraz sweepowanie parametrów
  bloków wielo-instancyjnych (`indicators`, `asset_filters`) przez notację `"instancja.param"`
  (np. `{"indicators": {"sma_200.window": [100, 150, 200]}}`), zamiast rzucać błąd
  "nie wspierane". Bloki jedno-implementacyjne bez zmian.
