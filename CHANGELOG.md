# Changelog

Zapis istotnych zmian w projekcie, najnowsze na górze. Każdy wpis krótko: co się zmieniło i po co.

## 2026-07-10

- **BUGFIX `engine_v2/pipeline.py::_run_phase_a`**: `usable_dates = score.dropna(how="all").index`
  miał wycinać tylko rozgrzewkę na starcie historii, ale w praktyce kasował KAŻDY miesiąc w
  środku historii, gdzie score wyszedł w całości NaN (regularnie przy `canary_regime_gate` -
  cały regime niezdatny). Poprawnie policzony `target_weights` (np. `rebound_starter` wchodzący
  w VT) był liczony, a potem wyrzucany - ten miesiąc znikał z FINAL PORTFOLIO, backtest jechał
  dalej na starych wagach zamiast wykonać zaplanowaną zmianę. Dotyczyło 79 z ~201 miesięcy
  (~40% historii) w `best17_a` (jedyna strategia z `canary_regime_gate`/all-ineligible
  scenariuszem w tym repo). Naprawa: obcinamy TYLKO ciągłą rozgrzewkę na starcie (do pierwszej
  daty z choć jednym policzonym score), nie każdą pojedynczą datę z NaN w środku. Zaktualizowano
  `test_pipeline.py::test_pipeline_matches_manual_wiring` i
  `test_final_portfolio.py::test_full_engine_chain_on_real_data` (ręcznie duplikowały starą
  logikę). Pełny pakiet testów: 157/158 (1 fail niepowiązany - brakujące tickery efa/agg/shy dla
  `vaa_g4`, nie mam ich w `data/us/nyse`).

  **Konsekwencje - `best17_a` solo, PRZED vs PO poprawce (cała historia)**:
  | | PRZED (buggy) | PO (poprawione) |
  |---|---|---|
  | CAGR | ~19% | **~7.7%** |
  | MaxDD | -26% | -28% |
  | Sharpe | ~1.03 | **~0.58** |
  | Roczny turnover | ~0.45 | **~7.0** |

  `best17_a` NIE jest już najlepszym wynikiem w repo - jego prawdziwy turnover/Sharpe jest teraz
  w tej samej okolicy co `the_one` (~6.8 turnover, Sharpe ~0.66, niezmieniony przez tę poprawkę -
  `the_one` nie ma mechanizmu "cała grupa niezdatna", więc bug go nie dotyczył). `combined_best2`
  (patrz niżej) prawie się nie zmienił - COMBINER przypadkiem już wymuszał podobne zachowanie
  (wypełniał brakujące daty `best17_a` jako cash), więc błąd solo nie przekładał się 1:1 na
  wynik połączony. `validation`(OOS)/sweep `min_score_gap` dla `best17_a` w README - NIE
  przeliczone po poprawce, oznaczone tam jako nieaktualne do czasu ponownego uruchomienia.

- `strategies_v2/combined_best2/combined_spec.json`: **wynik po poprawce bugfixa powyżej**: CAGR
  ~8.1%, MaxDD -17.4%, Sharpe ~0.68, Calmar ~0.47, roczny turnover ~6.8 (poprzednio, na buggy
  pipeline: CAGR ~7.4%, MaxDD -15.5%, Sharpe ~0.66, turnover ~6.6 - patrz niżej, wynik pierwotny
  z komentarzem o przyczynach). nowy `CombinedSpec` łączący dwie
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
