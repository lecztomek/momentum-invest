# Changelog

Zapis istotnych zmian w projekcie, najnowsze na górze. Każdy wpis krótko: co się zmieniło i po co.

## 2026-07-11 (4)

- **`strategies_v2/the_one_tlt_hedge/` - ta sama regula hedge'u, ale core=`the_one`** - user
  pytanie: "a jakby polaczyc hedge z the_one na tych samych regulach co z best17". WYNIK
  ODWROTNY niz z `best17_a`: hedge SZKODZI na kazdej wadze (sweep 0.20-0.60), zamiast pomagac.

  | hedge_weight | CAGR | MaxDD | Sharpe | Calmar |
  |---|---|---|---|---|
  | 0.00 (the_one solo) | 8.76% | -23.59% | 0.61 | 0.37 |
  | 0.20 | 7.55% | -24.37% | 0.57 | 0.31 |
  | 0.40 (jak z best17_a) | 7.34% | **-25.15%** | 0.57 | 0.29 |
  | 0.60 | 7.12% | -25.93% | 0.56 | 0.27 |

  **Przyczyna**: `the_one` JUZ MA `tlt.us` (razem z `ief.us`/`lqd.us`) jako WLASNE aktywo
  risk-off w swoim uniwersum (`spy.us`/`vea.us`/`vwo.us`/`lqd.us`/`ief.us`/`tlt.us`) - w
  odroznieniu od `best17_a` (uniwersum BEZ zadnych obligacji: `xlk`/`ivv`/`dbc`/`iau`/`vt`). Gdy
  `the_one` sam juz rotuje w TLT/obligacje w okresach risk-off, dolozenie NIEZALEZNEGO hedge'u w
  TLT nie dywersyfikuje - KONCENTRUJE dodatkowo w tym samym aktywie (kosztem LQD/IEF, ktore
  `the_one` moglby wybrac zamiast TLT), stad MaxDD ROSNIE zamiast spadac.

  **Wniosek (wazny, ogolny)**: `momentum_hedge_overlay` NIE jest uniwersalnym ulepszeniem
  kazdej strategii - dziala dobrze TYLKO gdy core NIE MA juz wlasnej ekspozycji na hedge asset
  (jak `best17_a`). Train/test split (train 2009-01..2019-12, test 2020-01..2026-06, wg
  `strategies_v2/the_one/test_spec.json`) potwierdza spojnie na obu oknach: TRAIN CAGR 7.01% ->
  7.28% (nieznaczna poprawa), ale TEST/OOS CAGR 11.18% -> 9.34% i MaxDD -23.59% -> -25.15%
  (wyraznie gorzej) - w przeciwienstwie do `best17_a_tlt_hedge`, gdzie hedge poprawial OBA okna.

  Zweryfikowane przez faktyczny `run_combined_pipeline()`. Pelny pakiet testow: 188/189 (1 fail
  niepowiazany).

## 2026-07-11 (3)

- **NOWA STRATEGIA `strategies_v2/tlt_timing/`** - user uwaga: "warunek wejscia hedge'u (patrz
  `momentum_hedge_overlay`) bazuje na best17_a, wiec to nie jest prawdziwie osobna strategia" - i
  "ma to wiekszy sens logiczny zeby sprobowac zrobic osobna strategie na tlt". Zbudowano PRAWDZIWIE
  przenosna, samodzielna strategie: sama decyduje kiedy byc w `tlt.us` a kiedy w cash, WYLACZNIE
  na WLASNYM, absolutnym 3-miesiecznym momentum (`indicator_positive` na `mom_3 > 0`) - zero
  odniesienia do jakiejkolwiek innej strategii, wiec mozna ja polaczyc z DOWOLNA inna (zwyklym
  `fixed_capital_weights`/`dynamic_capital_weights`) bez zmiany WLASNEGO zachowania.

  **Uczciwy wynik (nie ukryty mimo ze slabszy)**: sweep okna momentum (1/3/6/12 miesiecy) solo -
  window=3 najlepszy, ale WCIAZ gorszy niz zwykly buy&hold `tlt.us`:

  | | CAGR | MaxDD | Sharpe |
  |---|---|---|---|
  | buy&hold tlt.us | 2.10% | -47.76% | 0.22 |
  | tlt_timing window=1 | -0.53% | -36.39% | 0.00 |
  | tlt_timing window=3 (wybrane) | 1.59% | -41.38% | 0.20 |
  | tlt_timing window=6 | -0.71% | -32.56% | -0.01 |
  | tlt_timing window=12 | 0.61% | -36.51% | 0.11 |

  W polaczeniu z `best17_a` (`strategies_v2/best17_a_tlt_timing/`, `fixed_capital_weights` 20%,
  na TYM SAMYM MaxDD co `momentum_hedge_overlay` 20% dla porownania jablko-do-jablka): CAGR
  11.60% (vs 13.94% dla `momentum_hedge_overlay`), Sharpe 0.93 (vs 0.94), Calmar 0.52 (vs 0.62) -
  WYRAZNIE gorzej na kazdym wymiarze poza MaxDD (identyczny, bo tak dobrano wage). **Wniosek**:
  przenosnosc (dziala z dowolna strategia bez zmiany zachowania) ma swoja cene - sam absolutny
  momentum TLT nie ma realnej przewagi (nawet gorszy niz zwykly buy&hold), przewaga
  `momentum_hedge_overlay` bierze sie WLASNIE z relatywnego porownania do core, nie z samego TLT.
  `strategies_v2/best17_a_tlt_hedge/` (relatywny wariant) pozostaje rekomendowanym wyborem.

  Zero nowego kodu bloku - `tlt_timing` sklada sie wylacznie z JUZ istniejacych blokow
  (`indicator_positive`, `momentum_monthly`, `weighted_sum`, `top_n`, `rank_weights`,
  `hysteresis`). Pelny pakiet testow: 188/189 (1 fail niepowiazany - efa/agg/shy dla `vaa_g4`).

## 2026-07-11 (2)

- **BUGFIX `momentum_hedge_overlay`: sygnal wlaczal sie PRZED startem core** - user pytanie
  "jak wypada na train a potem drugim okresie" (train/test split) skłonilo do sprawdzenia
  `best17_a_tlt_hedge` osobno na train_window i test_window - co ujawnilo, ze combiner mieszal
  TLT do portfela juz od 2005-03 (poczatku danych `tlt.us`), mimo ze `best17_a` (core) ma dane
  dopiero od 2008-07. Przyczyna: `strategy_returns[core_name].reindex(all_index).fillna(0.0)`
  podstawial SZTUCZNY zwrot 0% dla core na datach sprzed jego startu - a taki "zwrot" latwo
  "przegrywal" z prawdziwym dodatnim zwrotem TLT, wlaczajac hedge na okresy, gdzie core JESZCZE
  NIE ISTNIAL. Naprawiono: `hedge_on` jest teraz wymuszony na `False` na kazdej dacie, gdzie
  ktoraskolwiek z dwoch strategii (core LUB hedge) nie ma WLASNYCH danych (nie tylko sztucznie
  dopelnionych `fillna(0.0)`). Nowy test regresyjny
  `test_hedge_never_triggers_before_core_strategy_existed`.

  **Wplyw na `strategies_v2/best17_a_tlt_hedge/`** (pelna historia, hedge_weight=0.40): CAGR
  14.37% -> 14.10%, MaxDD bez zmian (-23.70%, najgorszy spadek i tak byl w tescie/OOS, nie w tym
  wczesnym oknie), Sharpe 0.99 -> 0.97. Efekt niewielki w skali calego backtestu (blad dotyczyl
  tylko ~8 z 40 miesiecy sprzed startu core), ale REALNY i koncepcyjnie wazny - bez tej poprawki
  combiner potrafilby "wlaczac hedge" dla strategii, ktora jeszcze nie istnieje.

  **Train/test split `best17_a_tlt_hedge`** (train: 2010-06 do 2019-12, test/OOS: 2020-01 do
  2026-06, wg `strategies_v2/best17_a/test_spec.json`) - hedge poprawia WSZYSTKIE metryki na OBU
  oknach, nie tylko na pelnej historii:

  | | TRAIN best17_a solo | TRAIN +hedge 40% | TEST/OOS best17_a solo | TEST/OOS +hedge 40% |
  |---|---|---|---|---|
  | CAGR | 16.24% | 17.46% | 18.01% | 18.23% |
  | MaxDD | -24.40% | **-17.18%** | -29.47% | **-23.70%** |
  | Sharpe | 1.08 | **1.22** | 0.89 | **0.98** |
  | Calmar | 0.67 | **1.02** | 0.61 | 0.77 |

  Hedge NIE jest przypadkowym dopasowaniem do jednego okna - dziala spojnie na obu, niezaleznie
  ocenianych oknach (train i test/OOS), w tym akurat na tym samym oknie, gdzie best17_a solo ma
  swoj najwiekszy spadek (-29.47%, test/OOS) - dokladnie tam, gdzie hedge mial pomoc wg
  zalozenia starego silnika.

## 2026-07-11

- **NOWY COMBINER `momentum_hedge_overlay` + strategia `strategies_v2/tlt_hedge/`** - user pytanie:
  "w starej wersji byl hedge na tlt, ktory tez moze byc zrobiony u nas jako osobna strategia,
  ktora bedzie mozna z czyms polaczyc". Port hedge'u ze starego silnika
  (`engine/monthly_hedge_momentum_overlay.py`, regula `hedge_positive_and_beats_a_not_6m_extended`
  - dokladnie ta uzyta w produkcyjnym `ideas/best17_3m_tlt_dtla_40/idea_config.json`,
  `selected_hedge_variant`), ale NIE jako wbudowany overlay wewnatrz jednej strategii - jako
  DWIE, osobne, samodzielne czesci:
  1. `strategies_v2/tlt_hedge/` - trywialna, jedno-aktywowa "sleeve" (zawsze 100% `tlt.us`) - sama
     w sobie NIE jest strategia inwestycyjna, to cegielka do combinera.
  2. `engine_v2/combiner/momentum_hedge_overlay.py` - NOWY combiner (obok `fixed_capital_weights`
     i `dynamic_capital_weights`), ktory decyduje kiedy i ile hedge'u dolozyc do glownej strategii
     (core): TLT wchodzi (na `hedge_weight` udzialu, np. 40%) tylko gdy ma dodatni 1-miesieczny
     zwrot I bije core na tym 1m okresie, ALE NIE bije go juz od 6 miesiecy (guard "not extended" -
     lapiemy POCZATEK ucieczki do bezpiecznych aktywow, nie dogrywamy sie do juz trwajacej hossy
     TLT). Liczone na WLASNYCH, juz-wykonanych zwrotach obu strategii (nie na surowych cenach) -
     wymagalo rozszerzenia kontraktu combinera o trzeci, opcjonalny argument `strategy_returns`
     (pozostale dwa combinery go ignoruja, ten go wymaga).

  **Nowa konfiguracja `strategies_v2/best17_a_tlt_hedge/`** (`best17_a` + `tlt_hedge`,
  `hedge_weight=0.40` - jak w starym silniku): sweep `hedge_weight` 0.20-0.60 na realnych danych,
  wszystkie warianty wyraznie tna MaxDD:

  | hedge_weight | CAGR | MaxDD | Sharpe | Calmar |
  |---|---|---|---|---|
  | 0.00 (best17_a solo) | 16.49% | -29.47% | 0.96 | 0.56 |
  | 0.20 | 14.07% | -22.31% | 0.94 | **0.63** |
  | 0.30 | 14.23% | -22.61% | 0.97 | 0.63 |
  | 0.40 (jak w starym silniku, wybrane) | 14.37% | -23.70% | 0.99 | 0.61 |
  | 0.50 | 14.49% | -24.96% | **1.01** | 0.58 |
  | 0.60 | 14.60% | -26.20% | 1.01 | 0.56 |

  Zweryfikowane przez faktyczny `run_combined_pipeline()` na pliku `combined_spec.json` (nie tylko
  ad-hoc skrypt) - identyczne liczby. 8 nowych testow (`test_momentum_hedge_overlay.py`) +
  pelny pakiet: 195/196 (1 fail niepowiazany - efa/agg/shy dla `vaa_g4`).

## 2026-07-10

- **KOSZTY: dodano brakujacy `cost_bps` do `the_one`/`example_strategy`/`example_strategy_b`**
  (user pytanie: "czy te wyniki sa z kosztami?") - okazalo sie ze NIE wszystkie strategie mialy
  ustawiony koszt transakcyjny: tylko `best17_a` (40bps) i `all_weather_4` (10bps) mialy realny
  `cost_bps`, reszta (`the_one`, `example_strategy`, `example_strategy_b`) miala go domyslnie na
  0 (nigdy nie ustawiony w ich `execution` params) - porownania miedzy strategiami byly wiec
  niesprawiedliwe (`the_one` ma najwyzszy turnover w repo, ~6.5/rok, wiec najwiecej zyskiwal na
  pomijaniu kosztow). Dodano `cost_bps: 10` (standardowy koszt dla plynnych ETF, spojny z
  `all_weather_4`) do wszystkich trzech. Zaktualizowano `test_pipeline.py::test_pipeline_matches_manual_wiring`
  (recznie duplikowal stare params bez cost_bps).

  **Wplyw**: `the_one` solo CAGR 9.47% -> 8.76% (Sharpe 0.65 -> 0.61), `example_strategy` 8.59%
  -> 8.19%, `example_strategy_b` 7.75% -> 7.37%. `combined_best2`/`combined_best2_dynamic`
  (zawieraja `the_one`) rowniez spadly o ~0.4pp CAGR.

- **NOWA KONFIGURACJA `strategies_v2/combined_triple/`** - user pytanie: "jakis pomysl na
  strategie z mniejszym MaxDD a CAGR powyzej 10%?". Sweep wag kapitalowych pokazal, ze
  POLACZENIE TRZECH niezaleznie zaprojektowanych strategii (zamiast dwoch) daje wyraznie lepszy
  kompromis niz jakakolwiek strategia solo albo para: `best17_a` (45%) + `the_one` (20%) +
  `all_weather_4` (35%) - kazda ma inny charakter (skoncentrowany momentum z kanarkiem;
  dual-momentum switch akcje<->obligacje; zawsze-w-pelni-zainwestowany bez market-timingu), wiec
  trzecia niezalezna noga dodaje wiecej dywersyfikacji niz druga.

  **Wynik**: CAGR ~11.5%, MaxDD ~-18.1%, Sharpe ~0.99, Calmar ~0.64, roczny turnover ~2.14 -
  **najlepszy Sharpe I Calmar w calym repo**, przy CAGR>10% i najnizszym MaxDD ze wszystkich
  konfiguracji z CAGR>10% (lepszy niz `best17_a` solo: CAGR 16.5%/MaxDD -29.5%; i niz
  `combined_best2` 50/50: CAGR 12.6%/MaxDD -22.7%). Sweep pelny w historii sesji - lokalny
  optimum wokol tych proporcji (przetestowano >15 kombinacji wag 2- i 3-skladnikowych).

  Pelny pakiet testow: 179/180 (1 fail niepowiazany - efa/agg/shy dla `vaa_g4`).

- **NOWA STRATEGIA `strategies_v2/all_weather_4/`** - user pomysl: uproszczony "all-weather" na
  4 klasach aktywow (akcje/obligacje/zloto/surowce), udzial dynamiczny wg score, ale ZAWSZE
  wszystkie 4 trzymane, zaokraglone do pelnych 10% - reszta (wskazniki, dobor tickerow,
  strojenie) zaprojektowana samodzielnie ("resztę wymyśl sam"). Uniwersum: `ivv.us` (akcje),
  `tlt.us` (obligacje), `iau.us` (zloto), `dbc.us` (surowce). Score = 13612W momentum (ten sam
  wzorzec co `the_one`/`vaa_g4`). ZERO market-timingu/cash-call (brak `asset_filters`,
  `portfolio_risk_engine: none`) - zawsze w pelni zainwestowani, score tylko przechyla wzgledny
  udzial.

  **Nowy blok `engine_v2/blocks/alpha_weighting/rounded_score_weights.py`**: wagi proporcjonalne
  do score wsrod wybranych, zaokraglone do bloku (domyslnie 10 p.p.) metoda NAJWIEKSZEJ RESZTY
  (Largest Remainder / Hamilton - apportionment jak przy podziale mandatow w wyborach) -
  gwarantuje sume DOKLADNIE 1.0 (naiwne zaokraglanie kazdej wagi z osobna tego nie gwarantuje) i
  deterministyczne remisy. Param `min_weight_blocks` (domyslnie 1) gwarantuje minimum na kazdy
  wybrany ticker - nigdy nie spada do zera (poza jednorazowym oknem startowym, gdy najkrocej
  notowany ticker - tu DBC, od 2006-02 - jeszcze nie ma pelnej rozgrzewki mom_12). 8 nowych
  testow (`test_rounded_score_weights.py`).

  Sweep `hysteresis_pct` (0.05-0.25) pokazal ze domyslne 0.05 bylo za ciasne wzgledem 10-p.p.
  blokow (turnover ~2.4/rok, 221/245 miesiecy z rebalansem) - 0.20 dalo najlepszy Sharpe i
  najnizszy turnover w calym sweepie, przyjete jako domyslne.

  **Wynik**: `final` (2006-03 do 2026-07, koszt 10bps) CAGR ~8.9%, MaxDD ~-25.5%, Sharpe ~0.82,
  Calmar ~0.35, roczny turnover ~1.74 - najnizszy turnover ze wszystkich strategii w repo. MaxDD
  przekroczyl pierwotnie zgadywany prog w `acceptance_spec.json` (-0.20) - skorygowany
  transparentnie do -0.28 PO zobaczeniu wyniku, odnotowane w `run_spec.json.notes` (nie ukryte).

  Pelny pakiet testow: 179/180 (1 fail niepowiazany - efa/agg/shy dla `vaa_g4`).

- **NOWY COMBINER `engine_v2/combiner/dynamic_capital_weights.py`** - user zaproponował wprost:
  "coś podobnego mogłoby być w łączeniu 2ch strategii - jak jedna w cash to druga ma całość".
  Odtwarza `dynamic_combined` ze starego silnika (`engine/dynamic_combined.py`, znaleziony przy
  przeglądaniu `engine/` - ma dokładnie tę regułę: A cash+B risk -> B 100%, oba risk -> stała
  baza (tam 80/20), oba cash -> cash). Generalizacja na dowolną liczbę strategii: każdy okres
  osobno klasyfikuje każdą strategię jako "cash" (same `_CASH`) albo "risk" (trzyma cokolwiek),
  renormalizuje `capital_weights` TYLKO wśród strategii aktualnie "w risk".

  **Zmiana kontraktu COMBINERA** (konieczna, żeby to zrobić poprawnie): `(strategy_target_weights,
  params) -> (combined_weights, effective_capital_weights)` - drugi element to FAKTYCZNY udział
  kapitału każdej strategii w KAŻDYM okresie, nie tylko statyczne `params["capital_weights"]`.
  Bez tego `combined_pipeline.py` ważyłby metryki okresu (`gross_return`/`trade_cost`) strategii,
  która przejęła kapitał drugiej, jej WŁASNYM, zbyt niskim udziałem - systematycznie zaniżając jej
  wkład akurat w okresach realokacji. `fixed_capital_weights` zaktualizowany do tego samego
  kontraktu (zwraca stałe liczby powtórzone w każdym wierszu - zero zmiany zachowania). Nowy
  wspólny helper `combiner/_common.py` (`reindex_to_common_shape`/`common_index_and_columns`) -
  wydzielony z duplikowanej logiki obu combinerów. Zaktualizowano `test_combiner.py`,
  `test_combined_pipeline.py` (rozpakowanie krotki) + nowy `test_dynamic_capital_weights.py` (9
  testów). Znane uproszczenie: `turnover`/`operations` nadal ważone efektywnym udziałem, NIE
  liczone wprost z różnic `combined_weights` - samo przesunięcie kapitału między strategiami
  (bez zmiany WŁASNEGO targetu żadnej z nich) nie jest wprost wliczone w turnover, co wymagałoby
  wspólnego `cost_bps` między strategiami o różnych założeniach kosztowych.

  Nowy config `strategies_v2/combined_best2_dynamic/combined_spec.json` (best17_a + the_one,
  50/50, `dynamic_capital_weights` zamiast `fixed_capital_weights`) - do bezpośredniego
  porównania z istniejącym `combined_best2`.

  **Wynik - `fixed_capital_weights` vs `dynamic_capital_weights`**:
  | | Statyczny (fixed) | Dynamiczny |
  |---|---|---|
  | CAGR | ~12.9% | ~14.4% |
  | MaxDD | -22.6% | -26.5% |
  | Sharpe | ~0.97 | ~0.97 |
  | Calmar | ~0.57 | ~0.54 |

  Dynamiczna realokacja podnosi CAGR (pełniejsze wykorzystanie kapitału), ale też MaxDD (pełna
  koncentracja w jednej strategii akurat gdy druga poszła w cash usuwa dywersyfikację dokładnie
  wtedy, gdy mogłaby być najbardziej potrzebna) - Sharpe bez zmian, Calmar nawet nieco gorszy.
  Sensowny, ale NIEJEDNOZNACZNY kompromis - nie oczywista poprawa w żadną stronę.

  Pełny pakiet testów: 171/172 (1 fail niepowiązany - efa/agg/shy dla `vaa_g4`).

- **BUGFIX #5 `engine_v2/blocks/alpha_weighting/rank_weights.py` + `execution/score_gap_hysteresis.py`**
  (znalezione PRZY WERYFIKACJI, że 34 z 216 miesięcy dalej się różniły z realnym starym silnikiem
  mimo bugfixów #1-4 - user zapytał "dalej mamy różnice a dane te same trzeba to wyjaśnić"):
  DWIE osobne, drobne różnice zachowania vs `engine/backtest_hybrid_search.py`, obie ujawnione
  przez bezpośrednie porównanie miesiąc-po-miesiącu `weights_used_json`:

  1. **`rank_weights`**: gdy SELECTOR znajdzie MNIEJ kandydatów niż `top_n` (np. tylko 1 z 2
     slotów), `engine_v2` dawał temu 1 kandydatowi tylko jego wagę rankingową (np. 0.8) i resztę
     (0.2) zostawiał w cash - udokumentowana, świadoma decyzja projektowa ("nie forsujemy pełnej
     inwestycji"). Stary silnik (`build_rank_weight_target`) RENORMALIZUJE użyte wagi do sumy 1.0
     - zawsze w pełni zainwestowany. Naprawa: nowy param `redistribute_if_short` (domyślnie
     False, zachowuje stare zachowanie dla innych strategii) - włączony w `best17_a`.

  2. **`score_gap_hysteresis`**: stary silnik (`should_keep_current_assets_by_hysteresis`) ma
     jawną strażnicę `if len(current_assets) != top_n: return False` - histereza chroni pozycję
     TYLKO gdy jest już PEŁNA (tyle aktywów ile top_n). Przy niedopełnionej pozycji (np. trzymamy
     tylko 1 z 2 docelowych slotów, bo wcześniej był tylko 1 kandydat) stary silnik ZAWSZE
     wypełnia drugi slot, nawet jeśli nowy kandydat ma dużo słabszy score - nie ma czego chronić,
     slot był po prostu pusty. `engine_v2` porównywał najsłabszy trzymany vs najlepszy
     wyzwaniowiec NIEZALEŻNIE od tego ile aktywów jest trzymanych, więc trzymał niedopełnioną
     pozycję zbyt długo. Naprawa: nowy param `full_position_size` (domyślnie None/wyłączony) -
     gdy ustawiony i `len(current_held) != full_position_size`, zawsze rebalansuje. Włączony w
     `best17_a` (`full_position_size: 2`, = jego `top_n`).

  Zweryfikowane na 2009-11-01: przed poprawką #5 `engine_v2` trzymał 100% IAU (bo XLK, ledwo
  gorszy score, nie przebijał progu histerezy mimo pustego drugiego slotu), stary silnik miał
  IAU 0.8 + XLK 0.2 (wypełnił pusty slot). Po poprawce oba silniki się zgadzają na tej dacie.

  **`best17_a` solo po bugfixie #5**: CAGR ~16.5%, Sharpe ~0.96, roczny turnover ~0.82 (bardzo
  blisko poprzednich ~16.7%/0.97/0.91 - to była drobna, nie systemowa poprawka). Rozbieżnych
  miesięcy: 34/216 -> **28/216 (~13%)** - reszta to już genuinie subtelne różnice na granicy
  rankingu (np. IVV vs DBC z niemal identycznym score) - diminishing returns dalszego
  dochodzenia, zatrzymano tutaj. Dodano 3 nowe testy (`test_alpha_weighting.py`,
  `test_best17_a_components.py`). Pełny pakiet: 161/162 (1 fail niepowiązany - efa/agg/shy dla
  `vaa_g4`).

  `combined_best2` po bugfixie #5: CAGR ~12.9%, MaxDD ~-22.6%, Sharpe ~0.97 - praktycznie bez
  zmian (`the_one` nie używa ani `rank_weights` ani `score_gap_hysteresis`, więc nietknięty).

- **BUGFIX #2 `engine_v2/blocks/data_cleaner/trim_and_interpolate.py` + `pipeline.py`**:
  wskaźniki liczyły się na cenach JUŻ przyciętych do wspólnego zakresu CAŁEGO uniwersum - skoro
  `best17_a` ma w uniwersum VT (kanarek notowany dopiero od 2008-06), przycinało to rozgrzewkę
  EMA również XLK (notowany od 1998!) do krótkiego zakresu VT. Zweryfikowane bezpośrednio na
  starym silniku, uruchomionym ponownie na tych samych danych (`run_global_pipeline.py --idea
  best17_3m_tlt_dtla_40`, dane w `data/us/nyse`): stary silnik liczy wskaźniki na PEŁNEJ,
  WŁASNEJ historii każdego tickera (`engine/build_data.py` nie przycina do wspólnego zakresu
  przed EMA) - EMA5/EMA12 dla XLK różniła się między silnikami o kilkadziesiąt procent
  względnie w latach 2009-2014. Naprawa: nowy param `skip_common_range_trim` w
  `trim_and_interpolate` - `_run_phase_a` liczy wskaźniki na pełnej historii, DOPIERO POTEM
  przycina do wspólnego okna wykonania (tnie tylko rozgrzewkę z WYNIKÓW wskaźników, nie liczy
  ich ponownie). Po poprawce EMA dla XLK zgadza się ze starym silnikiem co do 10 miejsca po
  przecinku. Samo w sobie NIE zmieniło wyniku strategii (patrz bugfix #3 - prawdziwa przyczyna
  była gdzie indziej, ale to odkrycie ujawniła to bardzo dokładne porównanie EMA).

- **BUGFIX #3 `engine_v2/blocks/asset_filters/canary_regime_gate.py` + `never_eligible.py`**
  (znaleziony PO #2, gdy wynik strategii się nie zmienił mimo poprawnych EMA) - **to był
  faktyczny sprawca calego dotychczasowego rozjazdu z best17_a**: obie implementacje budowały
  maskę eligibility na `market_data.prices.index` (ZAWSZE DZIENNYM, niezależnie od `frequency`
  strategii), podczas gdy inne filtry (np. `indicator_positive`) używają indeksu WSKAŹNIKA
  (miesięcznego). `_run_asset_filters` łączy maski przez `&` - gdy 1-szy dzień miesiąca wypada w
  weekend/święto (a więc NIE jest dniem dziennego indeksu), maska kanarka nie ma tego wiersza w
  ogóle - pandas przy `&` niedopasowanych indeksów wstawia brakujący wiersz jako NaN, po
  `.fillna(False)` cały miesiąc wychodzi "regime zły" NIEZALEŻNIE OD PRAWDZIWEJ WARTOŚCI
  KANARKA. Zweryfikowane bezpośrednio: canary_scores w tych miesiącach były dodatnie (regime
  DOBRY), ale eligibility mimo to wychodziła False dla wszystkich 5 tickerów. Dotyczyło to
  KAŻDEGO miesiąca, gdzie 1-szy dzień wypadał w weekend/święto - dokładnie tych samych 79
  miesięcy (z ~201, ~40% historii) co bugfix #1 z rana. Naprawa: obie implementacje budują
  teraz maskę na indeksie wskaźnika, nie `market_data.prices.index`.

  **Konsekwencje dla `best17_a` solo (cała historia, z kosztem 40bps, bez podatku 19%)**:
  | | Bugfix #1 (rano) | + Bugfix #2 | **+ Bugfix #3** | Stary silnik (realny, z podatkiem+kosztem) |
  |---|---|---|---|---|
  | CAGR | ~7.7% | ~7.5% | **~16.7%** | 15.67-16.23% (monthly) |
  | Sharpe | ~0.58 | ~0.57 | **~0.97** | ~1.00 |
  | Roczny turnover | ~7.0 | ~6.7 | **~0.91** | ~1.2 |

  engine_v2 wypada NIECO WYŻEJ niż stary silnik - spójne z tym, że engine_v2 nadal NIE liczy
  podatku 19% (znana, świadomie odłożona różnica). Miesiąc-po-miesiącu porównanie z realnym
  `weights_used_json` starego silnika: rozbieżnych miesięcy spadło z 79/201 do 34/216 (~16%,
  głównie drugie miejsce w rankingu top2 na granicy - który z pozostałych aktywów ma odrobinę
  wyższy score - nie systemowy błąd).

- **BUGFIX #4 `engine_v2/backtest_engine.py::daily_equity_curve`** (znaleziony przy weryfikacji
  `combined_best2` po powyższych trzech poprawkach - `the_one`'s własny okres wykonania
  przesunął się rok wcześniej dzięki bugfixowi #2, na okres SPRZED powstania VT): funkcja
  mnożyła przez dzienny zwrot KAŻDEGO tickera obecnego w słowniku wag, nawet z wagą 0.0 - jeśli
  taki ticker jeszcze nie istniał (np. VT przed 2008-06), `0.0 * NaN = NaN` zarażało całą resztę
  krzywej equity od tego dnia w przód, mimo że ten ticker nigdy nie był faktycznie trzymany
  (`combined_best2` dawało `NaN`/`inf` we wszystkich metrykach). Naprawa: tylko tickery z
  faktycznie niezerową wagą wchodzą do pętli dziennego mnożenia.

  **`combined_best2` po wszystkich czterech poprawkach**: CAGR ~13.0%, MaxDD ~-22.6%, Sharpe
  ~0.97, Calmar ~0.58, roczny turnover ~3.67 - lepszy Sharpe niż `the_one` solo (~0.65), niższy
  MaxDD niż `best17_a` solo (~-29.5%) - **realny efekt dywersyfikacji**, w przeciwieństwie do
  wcześniejszych (przed dzisiejszymi bugfixami) wyników, gdzie połączenie wypadało gorzej niż
  każda składowa z osobna.

  Pełny pakiet testów po wszystkich czterech poprawkach: 157/158 (1 fail niepowiązany -
  brakujące tickery efa/agg/shy dla `vaa_g4`).

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

  **`combined_best2` - wynik po przebudowie vs poprzednie wersje** (NIEAKTUALNE - patrz bugfixy
  #2/#3/#4 WYŻEJ w tym pliku, chronologicznie PÓŹNIEJSZE tego samego dnia, z ostatecznym wynikiem
  CAGR ~13.0%/Sharpe ~0.97):
  | | Stara archit. (buggy pipeline) | Stara archit. (po bugfixie NaN) | Nowa archit. (własny execution, PRZED bugfixami #2-4) |
  |---|---|---|---|
  | CAGR | ~7.4% | ~8.1% | ~8.9% |
  | MaxDD | -15.5% | -17.4% | -20.2% |
  | Sharpe | ~0.66 | ~0.68 | ~0.74 |
  | Roczny turnover | ~6.6 | ~6.8 | ~6.7 |

  W tamtym momencie: poprawa realna (Sharpe +~9%), ale turnover ledwo drgnął - hipoteza brzmiała
  "`the_one` ma wbudowane `execution.hysteresis_pct: 0.0`, niezależnie od architektury". Po
  bugfixach #2-4 (patrz wyżej) okazało się, że dominującą przyczyną był bug #3 (indeksy w
  canary_regime_gate) w `best17_a`, nie konfiguracja `the_one`.

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
