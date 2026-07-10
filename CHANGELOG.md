# Changelog

Zapis istotnych zmian w projekcie, najnowsze na górze. Każdy wpis krótko: co się zmieniło i po co.

## 2026-07-10

- `strategies_v2/combined_best2/combined_spec.json`: nowy `CombinedSpec` łączący dwie
  dotychczas najlepsze strategie (`best17_a` - final CAGR ~19%, Sharpe ~1.03, brak rozjazdu
  train/OOS; `the_one` - jedyna strategia z lepszym OOS niż train), 50/50 kapitału, wspólna
  histereza 0.02 + koszt 40bps. Uruchomione realnie (dane z `main`, poza gitem w `data/us/nyse`) -
  pipeline działa poprawnie mechanicznie (wagi sumują się do 1.0, daty rosnące), ale WYNIK
  rozczarowuje: CAGR ~7.4%, MaxDD -15.5%, Sharpe ~0.66, Calmar ~0.48, roczny turnover ~6.6
  (bardzo wysoki - histereza po WADZE nie radzi sobie z dwiema skoncentrowanymi strategiami
  top_n=1/2, gdzie pojedynczy switch to skok wagi o 50 p.p.; sweep progu 0.02-0.4 praktycznie
  nie zmienia turnoveru, dopiero >=0.55 go tnie, ale kosztem MaxDD -34% i Sharpe ~0.5). Gorzej niż
  `best17_a` i `the_one` osobno - 50/50 + zwykła histereza wagowa to zła kombinacja dla tej pary;
  potrzebny inny execution/combiner, jeśli ma to mieć sens.
- `engine_v2/grid_sweep.py`: `allowed_param_families` wspiera teraz sweepowanie parametrów
  bloków wielo-instancyjnych (`indicators`, `asset_filters`) przez notację `"instancja.param"`
  (np. `{"indicators": {"sma_200.window": [100, 150, 200]}}`), zamiast rzucać błąd
  "nie wspierane". Bloki jedno-implementacyjne bez zmian.
