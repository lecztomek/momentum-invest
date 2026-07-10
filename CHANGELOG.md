# Changelog

Zapis istotnych zmian w projekcie, najnowsze na górze. Każdy wpis krótko: co się zmieniło i po co.

## 2026-07-10

- **PRZEBUDOWA `engine_v2/combined_pipeline.py`**: każda strategia liczy teraz WŁASNY
  EXECUTION/HYSTERESIS (pełny solo `run_strategy_pipeline`, z prawdziwym `PortfolioState`) PRZED
  połączeniem, zamiast JEDNEJ, wspólnej histerezy WAGOWEJ na surowych targetach po combinerze.
  Powód: histereza wagowa na poziomie połączonego portfela nie potrafi odtworzyć histerezy
  SCORE'OWEJ liczonej wewnątrz jednej strategii (np. `best17_a`'s `score_gap_hysteresis`) - widzi
  tylko WYNIK przełączenia (pełny skok wagi), nie to jak blisko była decyzja. `CombinedSpec` już
  nie niesie własnego `execution`/`execution_params` - usunięte z dataclass i z
  `strategies_v2/combined_example/combined_spec.json` i `.../combined_best2/combined_spec.json`.
  COMBINER (`fixed_capital_weights`) BEZ ZMIAN - działa identycznie na dowolnej tabeli kształtu
  `TargetWeights`, teraz dostaje JUŻ WYKONANE wagi zamiast surowego targetu. Nowa pomocnicza
  `_weights_used_to_wide()` odbudowuje tabelę ticker-waga z `weights_used_json`. Metryki okresu
  (`turnover`/`trade_cost`/`gross_return`/`net_return`) łączone wg `capital_weights` wprost w
  `combined_pipeline.py`; `operations` (liczba transakcji) sumowane BEZ ważenia. Usunięto martwy
  kod `pipeline._run_overlays_only` (był używany wyłącznie przez starą wersję combined_pipeline).
  Zaktualizowano `test_combined_pipeline.py` (test capital-split teraz porównuje JUŻ WYKONANE
  wagi, dodano silniejszą asercję: `run_combined_pipeline()` musi dać DOKŁADNIE te same wagi co
  manualne połączenie, bo żaden dodatkowy execution już się nie dzieje na poziomie połączonego
  portfela). Pełny pakiet: 157/158 (1 fail niepowiązany, jak niżej).

  **`combined_best2` - wynik po przebudowie vs poprzednie wersje**:
  | | Stara archit. (buggy pipeline) | Stara archit. (po bugfixie NaN) | **Nowa archit. (własny execution)** |
  |---|---|---|---|
  | CAGR | ~7.4% | ~8.1% | **~8.9%** |
  | MaxDD | -15.5% | -17.4% | -20.2% |
  | Sharpe | ~0.66 | ~0.68 | **~0.74** |
  | Roczny turnover | ~6.6 | ~6.8 | ~6.7 |

  Poprawa jest realna (Sharpe +~9%), ale turnover ledwo drgnął - `the_one` ma wbudowane
  `execution.hysteresis_pct: 0.0` (dosłownie zero wygładzania) w swoim `strategy_spec.json`,
  niezależnie od tego, na jakim poziomie liczy się histereza. Żeby faktycznie obniżyć turnover
  połączonego portfela, trzeba by dostroić WŁASNĄ histerezę `the_one` (ma już zdefiniowany
  sweep `allowed_param_families.execution.hysteresis_pct` - nieużyty jeszcze).

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

- `strategies_v2/combined_best2/combined_spec.json`: pierwsza wersja - nowy `CombinedSpec`
  łączący dwie ówcześnie najlepsze strategie (`best17_a` - final CAGR ~19%, Sharpe ~1.03, brak
  rozjazdu train/OOS; `the_one` - jedyna strategia z lepszym OOS niż train), 50/50 kapitału,
  wspólna histereza 0.02 + koszt 40bps (ta wspólna histereza została później usunięta - patrz
  przebudowa architektury wyżej). Uruchomione realnie (dane z `main`, poza gitem w
  `data/us/nyse`) - pipeline działał poprawnie mechanicznie (wagi sumują się do 1.0, daty
  rosnące), ale WYNIK rozczarował: CAGR ~7.4%, MaxDD -15.5%, Sharpe ~0.66, Calmar ~0.48, roczny
  turnover ~6.6 (bardzo wysoki - histereza po WADZE nie radziła sobie z dwiema skoncentrowanymi
  strategiami top_n=1/2, gdzie pojedynczy switch to skok wagi o 50 p.p.; sweep progu 0.02-0.4
  praktycznie nie zmieniał turnoveru, dopiero >=0.55 go ciął, ale kosztem MaxDD -34% i Sharpe
  ~0.5). Gorzej niż `best17_a` i `the_one` osobno w tamtym momencie - stąd późniejsza przebudowa
  na własny execution per strategia (patrz wyżej) i bugfix NaN (patrz niżej).
- `engine_v2/grid_sweep.py`: `allowed_param_families` wspiera teraz sweepowanie parametrów
  bloków wielo-instancyjnych (`indicators`, `asset_filters`) przez notację `"instancja.param"`
  (np. `{"indicators": {"sma_200.window": [100, 150, 200]}}`), zamiast rzucać błąd
  "nie wspierane". Bloki jedno-implementacyjne bez zmian.
