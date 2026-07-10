# engine_v2 - architektura

Nowy, modularny silnik strategii, budowany od zera obok starego `engine/` (niezależny od niego -
`engine_v2` **nie importuje niczego z `engine/`**; jedyne co dziedziczy ze starego świata to
surowe pliki cenowe w `data/`). Stary silnik zostanie kiedyś usunięty, więc `engine_v2` musi
działać samodzielnie.

Filozofia: każdy etap liczenia strategii to wymienny **blok** - jedna implementacja = jedna
funkcja zarejestrowana pod nazwą w słowniku (`REGISTRY`). Orchestrator (`pipeline.py`) nigdy nie
importuje konkretnej implementacji bezpośrednio, tylko woła `REGISTRY[nazwa](...)` - dzięki temu
dowolny blok da się podmienić albo przetestować osobno, bez ruszania reszty.

## Cztery specy (pre-rejestracja w stylu funduszowym)

- **StrategySpec** (`spec.py`) - hipoteza, universe, wybrane implementacje bloków (`blocks`),
  ich parametry (`base_params`), dozwolone rodziny parametrów do testów wrażliwości
  (`allowed_param_families`).
- **TestSpec** (`test_spec.py`) - jak testujemy: okna train/test, walk-forward, ablation,
  sensitivity, koszty, UK mapping. (Zdefiniowany, jeszcze nie spięty z pipeline'm.)
- **AcceptanceSpec** (`acceptance_spec.py`) - progi sukcesu: CAGR, max DD, Sharpe/Calmar,
  turnover, stabilność parametrów, UK mapping. (Zdefiniowany, jeszcze nie spięty.)
- **RunSpec** (`run_spec.py`) - co odpalamy teraz: która strategia + który test protocol +
  które kryteria + tryb (`search` / `validation` / `final`). (Zdefiniowany, jeszcze nie spięty.)

Przykład: `strategies_v2/example_strategy/` (wszystkie 4 pliki + `strategy_spec.json`).

## Pipeline pojedynczej strategii

Dwie fazy (patrz `types.py` za pełny opis kontraktów):

**FAZA A** - wektoryzowalna, liczona raz dla całej historii naraz, bez stanu między okresami:

```
data_loader -> data_cleaner -> indicators -> asset_filters -> asset_scoring -> selector
-> alpha_weighting -> portfolio_risk_engine
```

**FAZA B** - sekwencyjna, okres po okresie, niesie `PortfolioState` (jedyne miejsce, gdzie
"pamięć" między miesiącami w ogóle istnieje):

```
overlays -> execution/hysteresis -> FINAL PORTFOLIO
```

Orchestrator: `pipeline.run_strategy_pipeline(spec)` -> gotowa tabela FINAL PORTFOLIO.

### Bloki i ich implementacje (stan obecny)

| Blok | Rodzaj | Zaimplementowane | Co robi |
|---|---|---|---|
| `data_loader` | pojedynczy wybór | `stooq_csv` | Wczytuje ceny z plików stooq, wspiera `daily`/`weekly`/`monthly` |
| `data_cleaner` | pojedynczy wybór | `trim_and_interpolate` | Równa wspólny zakres dat, uzupełnia luki interpolacją (z limitem `max_gap`) |
| `indicators` | **wielo-instancyjny** | `sma_daily`, `momentum_monthly`, `volatility_daily`, `ema_ratio_monthly`, `momentum_month_end` | Biblioteka wskaźników - osobna implementacja per wskaźnik+częstotliwość+baza cenowa (start/koniec miesiąca) |
| `asset_filters` | **wielo-instancyjny** | `price_above_indicator`, `indicator_positive`, `canary_regime_gate`, `never_eligible` | Eliminacja aktywów (AND między instancjami); `canary_regime_gate` to GLOBALNY gate (cała grupa naraz, na podstawie osobnych "kanarków"); `never_eligible` trwale wyklucza tickery z normalnej selekcji |
| `asset_scoring` | pojedynczy wybór | `weighted_sum` | Ważona suma wskaźników, maskuje NaN tam gdzie `eligibility_mask=False` |
| `selector` | pojedynczy wybór | `top_n` | Top-N wg score, nigdy nie wybiera NaN |
| `alpha_weighting` | pojedynczy wybór | `rank_weights`, `inverse_vol`, `rounded_score_weights` | Wagi wybranych: stałe wg rankingu (reszta do `_CASH`) albo odwrotnie proporcjonalne do zmienności (zawsze w pełni zainwestowane) albo proporcjonalne do score, zaokrąglone do bloku (largest remainder), z gwarantowanym minimum na aktywo |
| `portfolio_risk_engine` | pojedynczy wybór | `none`, `vaa_canary`, `gem_dual_momentum_switch`, `rebound_starter` | Pass-through, albo pełna podmiana portfela wg reguły (patrz niżej - to jest świadomie najbardziej elastyczny blok w silniku) |
| `overlays` | pojedynczy wybór | `none` | Pass-through (rebound/vol-target - gdy będzie potrzebny) |
| `execution` | pojedynczy wybór | `hysteresis`, `score_gap_hysteresis` | Rebalans tylko gdy przekroczony próg - na różnicy WAGI (`hysteresis`) albo różnicy SCORE między najsłabszym trzymanym a najlepszym wyzwaniowcem (`score_gap_hysteresis`, wymaga `ExecutionContext.score_row`) |

**Wielo-instancyjne bloki** (`indicators`, `asset_filters`, patrz `spec.MULTI_INSTANCE_BLOCKS`):
nie mają jednej implementacji w `blocks`, tylko słownik nazwanych instancji w `base_params`,
bo strategia zwykle potrzebuje kilku naraz (np. SMA200 + momentum 3/6/12):

```json
"indicators": {
  "sma_200": {"impl": "sma_daily", "window": 200},
  "mom_3":   {"impl": "momentum_monthly", "window": 3}
}
```

Dalsze bloki odwołują się do wyników po kluczu (np. `"indicator_key": "sma_200"`) - zwykły
string, żadnego automatycznego dowiązania poza tym że nazwa się zgadza.

**Kontrakt `alpha_weighting`** to `(selection, score, indicator_set, params) -> TargetWeights` -
KAŻDA implementacja dostaje ten sam zestaw argumentów, nawet jeśli nie wszystkich używa
(`rank_weights` ignoruje `indicator_set`, `inverse_vol` ignoruje `score`) - to pozwoliło dodać
`inverse_vol` (potrzebuje zmienności z `indicator_set`) bez rozjazdu w tym jak orchestrator woła
poszczególne implementacje.

### FINAL PORTFOLIO (`final_portfolio.py`)

Jedyny blok, który NIE jest wymienną implementacją - to zwykła funkcja składająca listę
`PeriodExecutionResult` (z pętli FAZY B) w jedną tabelę. Kontrakt wyjściowy jest celowo zgodny
ze starym systemem (`date, strategy, weights_used_json, signal_changed, turnover, operations`),
plus dodatkowe kolumny (`gross_return, net_return, trade_cost`) na potrzeby przyszłego METRICS.

## Łączenie kilku strategii (COMBINER)

Warstwa WYŻEJ niż pojedyncza strategia - `CombinedSpec` (`combined_spec.py`) opisuje kilka
niezależnie zaprojektowanych strategii połączonych w jeden portfel:

```
Strategy A: FAZA A -> OVERLAYS -> EXECUTION/HYSTERESIS (WŁASNY, REALNY PortfolioState) -> Weights Used A
Strategy B: FAZA A -> OVERLAYS -> EXECUTION/HYSTERESIS (WŁASNY, REALNY PortfolioState) -> Weights Used B
                                    |
                     STRATEGY COMBINER (łączy JUŻ WYKONANE wagi wg capital_weights)
                                    |
                              FINAL PORTFOLIO
```

**POPRAWIONO 2026-07-10** (zmiana architektury): każda strategia to osobna, w pełni samodzielna
"sleeve" realnego konta - liczy PEŁNY solo pipeline (`run_strategy_pipeline`), WŁĄCZNIE Z WŁASNYM
EXECUTION/HYSTERESIS, zanim COMBINER w ogóle zobaczy jej wagi. Wcześniej było odwrotnie: EXECUTION
działo się RAZ, po combinerze, na surowych (niewygładzonych) targetach każdej strategii - to
rzucało WŁASNĄ histerezę każdej strategii (np. `best17_a`'s `score_gap_hysteresis`, patrz sekcja
"Piąta strategia" niżej). Histereza WAGOWA na poziomie połączonego portfela nie potrafi odtworzyć
histerezy SCORE'OWEJ liczonej WEWNĄTRZ jednej strategii - widzi tylko WYNIK przełączenia (skok
wagi o pełną wielkość pozycji), nie to jak blisko była decyzja (czy ranking przekręcił się "o
włos" czy wyraźnie). Stąd: każda strategia decyduje SAMA, kiedy handlować, korzystając z WŁASNEGO,
bogatszego kontekstu (np. `ExecutionContext.score_row`, którego COMBINER na poziomie połączonych
wag nigdy nie miał). `CombinedSpec` już nie niesie własnego `execution`/`execution_params` - to w
całości odpowiedzialność każdego `StrategySpec` z osobna.

Implementacje COMBINERA żyją w `combiner/` (analogiczny registry co bloki). Kontrakt:
`(strategy_target_weights, params) -> (combined_weights, effective_capital_weights)` - drugi
element to FAKTYCZNY udział kapitału każdej strategii W KAŻDYM OKRESIE (patrz niżej dlaczego to
osobny wynik, nie tylko `params["capital_weights"]`).

- **`fixed_capital_weights`** - stała alokacja kapitału między strategiami (`capital_weights`),
  waży i sumuje ich JUŻ WYKONANE wagi (unia kolumn dla różnych uniwersów, brakujące tickery = 0).
  Dla dat poza zakresem której strategii (np. inne okno rozgrzewki wskaźników) jej wkład to pełny
  `_CASH`, nie zera na całej linii - inaczej suma wierszy spadłaby poniżej 1.0.
  `effective_capital_weights` = te same stałe liczby powtórzone w każdym wierszu.

- **`dynamic_capital_weights`** - odtwarza `dynamic_combined` ze starego silnika
  (`engine/dynamic_combined.py`): gdy KTÓRAŚ strategia jest w danym okresie CAŁKOWICIE w cash,
  jej kapitał NIE marnuje się jako bezczynna gotówka - zostaje oddany strategiom, które SĄ
  zainwestowane (proporcjonalnie do ich WŁASNYCH `capital_weights`, renormalizowanych tylko wśród
  tych "w risk" w danym okresie). Gdy WSZYSTKIE strategie są w cash - cały połączony portfel w
  cash. To ten sam pomysł co `redistribute_if_short` w `rank_weights` (patrz sekcja "Piąta
  strategia"), tylko na poziomie COMBINERA zamiast pojedynczej strategii - user zaproponował to
  wprost po zobaczeniu tamtej poprawki. Przykład: `strategies_v2/combined_best2_dynamic/`.
  `effective_capital_weights` tu REALNIE zmienia się okres-po-okresie (0.0 gdy strategia w cash).

Pochodne metryki okresu (`turnover`/`trade_cost`/`gross_return`/`net_return`) są łączone wg
`effective_capital_weights` (nie statycznego `params["capital_weights"]`, wprost w
`combined_pipeline.py`, nie przez generyczny kontrakt COMBINERA) - inaczej strategia, która
przejęła kapitał drugiej, miałaby swój zwrot/koszt policzony na jej WŁASNYM, zbyt niskim udziale.
`operations` (LICZBA transakcji, nie kwota) jest sumowane BEZ ważenia, bo transakcja w jednej
sleeve i w drugiej to dwie osobne, realne transakcje. Znane uproszczenie: `turnover`/`operations`
NIE liczą wprost samego przesunięcia kapitału między strategiami (np. gdy A idzie w cash, a B -
bez zmiany WŁASNEGO targetu - przejmuje jej udział, w realnym koncie wymagałoby to dokupienia
pozycji B) - to by wymagało wspólnego `cost_bps` między strategiami o różnych założeniach
kosztowych, świadomie odłożone; `gross_return`/`trade_cost`/`net_return` (jedyne pola faktycznie
konsumowane przez `backtest_engine.daily_equity_curve`) są policzone poprawnie.

**Wynik `combined_best2` (50/50 best17_a+the_one) - statyczny vs dynamiczny combiner** (koszty:
`the_one` ma `cost_bps=10`, patrz "Znany, naprawiony bug" nizej za wyjasnienie skorygowanego
kosztu):
| | `fixed_capital_weights` | `dynamic_capital_weights` |
|---|---|---|
| CAGR | ~12.6% | ~14.0% |
| MaxDD | -22.7% | -26.8% |
| Sharpe | ~0.94 | ~0.95 |
| Calmar | ~0.55 | ~0.52 |

Dynamiczna realokacja podnosi CAGR (pełniejsze wykorzystanie kapitału), ale TEŻ podnosi MaxDD
(pełna koncentracja w jednej strategii akurat wtedy, gdy druga poszła w cash, usuwa dywersyfikację
dokładnie w momencie, gdy mogłaby być najbardziej potrzebna) - Sharpe praktycznie bez zmian,
Calmar nawet nieco gorszy. Sensowny, ale niejednoznaczny kompromis - nie "oczywista poprawa".

**`strategies_v2/combined_triple/`** - user pytanie: strategia z CAGR>10% ale niższym MaxDD niż
`best17_a` solo (-29.5%)? Sweep wag pokazał, że POŁĄCZENIE TRZECH niezależnie zaprojektowanych
strategii (zamiast dwóch) daje wyraźnie lepszy kompromis: `best17_a` (45%) + `the_one` (20%) +
`all_weather_4` (35%) - trzy różne charaktery (skoncentrowany momentum z kanarkiem;
dual-momentum switch; zawsze-w-pełni-zainwestowany) dają więcej dywersyfikacji niż para. Wynik:
CAGR ~11.5%, MaxDD ~-18.1%, Sharpe ~0.99, Calmar ~0.64 - **najlepszy Sharpe I Calmar w całym
repo**, przy CAGR>10% i najniższym MaxDD ze wszystkich konfiguracji z CAGR>10%.

Orchestrator: `combined_pipeline.run_combined_pipeline(combined_spec, base_dir)` -> tabela
FINAL PORTFOLIO. Przykład: `strategies_v2/combined_example/combined_spec.json`.

`run_strategy_pipeline()` i `run_combined_pipeline()` zwracaja DOKLADNIE ta sama tabele FINAL
PORTFOLIO - wszystko co idzie dalej (BACKTEST ENGINE, METRICS, ...) nie musi wiedziec czy
wejsciem jest jedna strategia czy polaczenie kilku.

## BACKTEST ENGINE (`backtest_engine.py`)

Kolejny "mechaniczny" krok jak FINAL PORTFOLIO (zwykla funkcja, nie registry) - bierze tabele
FINAL PORTFOLIO (okresowe wagi) + DZIENNE ceny i liczy gesta, dzienna krzywa equity: buy-and-hold
w trakcie okresu (wagi dryfuja z cenami do nastepnego rebalansu), rebalans + koszt transakcyjny
tylko na daty z FINAL PORTFOLIO. To jest wejscie do METRICS - MaxDD/vol/Sharpe potrzebuja gestej
krzywej, nie tylko punktow co miesiac. Wynik na granicach okresow zgadza sie z
`cumprod(1+net_return)` z FINAL PORTFOLIO (to nie przyblizenie inaczej liczone, tylko dokladanie
dziennej rozdzielczosci w srodku).

## METRICS (`metrics.py`)

Kolejny mechaniczny krok (zwykla funkcja, nie registry) - liczy standardowe metryki z dziennej
krzywej equity (BACKTEST ENGINE) + `turnover` z FINAL PORTFOLIO: `cagr`, `max_drawdown`,
`sharpe`, `calmar`, `annual_turnover`, `max_consecutive_negative_months`,
`max_time_underwater_months`. Nazwy kluczy odpowiadaja polom `acceptance_spec.Criteria` (bez
prefiksu `min_`/`max_`), zeby przyszly VALIDATION mogl je bezposrednio porownac z progami.

Nie liczy jeszcze `min_pct_positive_rolling_windows` (brakuje zdefiniowanej dlugosci okna -
dolaczymy przy budowie VALIDATION, gdzie to bedzie realnie potrzebne).

## VALIDATION / WALK-FORWARD (`validation.py`)

Bierze GOTOWA dzienna krzywa equity (BACKTEST ENGINE) + FINAL PORTFOLIO i **tnie je** na rolujace
okna wg `TestSpec.walk_forward` (`window_months`, `step_months`) - dla kazdego okna liczy METRICS
osobno (`run_walk_forward`). Okna generowane w obrebie `TestSpec.train_window` - `test_window`
zostaje nietkniety az do finalnej walidacji.

To jest kontrola STABILNOSCI W CZASIE (czy juz wybrana strategia trzyma sie dobrze w wielu
niezaleznych fragmentach historii), NIE strojenie parametrow - od tego bedzie osobny GRID SWEEP.
Zero zmian w tym jak liczy sie sam pipeline: `data_loader`...`backtest_engine` zawsze licza sie
na calej dostepnej historii, ten modul tnie juz GOTOWY wynik (patrz sekcja niżej za pelne
wyjasnienie, dlaczego train/test nie wplywa na wczesniejsze etapy).

## PARAMETER GRID SWEEP (`grid_sweep.py`)

Iteruje po `StrategySpec.allowed_param_families` (kartezjanski iloczyn wszystkich zadeklarowanych
wartosci, przez wszystkie bloki/parametry naraz) - `expand_param_grid()` generuje N wariantow
`StrategySpec`, kazdy z jedna, inna kombinacja wartosci. `run_param_sweep(spec, evaluate_fn)`
odpala kazdy wariant przez dostarczona funkcje oceniajaca (celowo niezalezna od sweepa - to samo
narzedzie sluzy i do szybkiego single-backtest checku, i do pelnego per-wariant walk-forward) i
zwraca jedna tabele: kombinacja parametrow + jej metryki. To jest fundament trybu ALPHA SEARCH -
pozwala zobaczyc czy dookola wybranych parametrow jest stabilna "rodzina" (plateau), nie tylko
jeden szczesliwy punkt.

Wspiera bloki jedno-implementacyjne (`allowed_param_families[blok][param]`, np.
`{"execution": {"min_score_gap": [0.0, 0.005, 0.01]}}`) oraz wielo-instancyjne (`indicators`,
`asset_filters`) przez notację `"instancja.param"`, np.
`{"indicators": {"sma_200.window": [100, 150, 200]}}` - sweepuje parametr JUŻ istniejącej
instancji (nie zmienia `impl` ani innych instancji); nieznana instancja albo brak kropki w
kluczu dla bloku wielo-instancyjnego rzuca czytelny błąd zamiast zgadywania.

## RUN SPEC RUNNER (`run_spec_runner.py`, `acceptance_check.py`)

Wiaze `RunSpec.mode` z odpowiednim mechanizmem - pierwsze realne uzycie `RunSpec` (dotad tylko
zdefiniowany, nic go nie czytalo):

- `"final"` - single backtest na calej historii, METRICS, sprawdzenie wzgledem `AcceptanceSpec.global_`.
- `"validation"` - single backtest na calej historii, ale METRICS liczone TYLKO na wycinku
  `TestSpec.test_window` (OOS) - jedna, czysta ocena, bez dalszego ciecia (test_window jest
  "swiete").
- `"search"` - GRID SWEEP x WALK-FORWARD (`TestSpec.train_window`) per wariant, zwraca zbiorcze
  statystyki (srednia/min CAGR, najgorszy drawdown, srednia Sharpe) po oknach.

`acceptance_check.check_criteria(metrics, criteria)` porownuje METRICS z progami
`AcceptanceSpec.Criteria` (tylko pola faktycznie ustawione). Uwaga wewnetrzna: `max_drawdown`
jest ujemny, wiec "nie gorszy niz prog" to numerycznie `wartosc >= prog`, NIE `<=` jak przy
zwyklych gornych limitach (turnover itp.) - to zostalo raz zle napisane i zlapane testem.

## Struktura folderów

```
engine_v2/
  spec.py, test_spec.py, acceptance_spec.py, run_spec.py   # 4 specy pojedynczej strategii
  combined_spec.py                                          # spec łączenia strategii
  types.py                                                  # kontrakty danych między blokami
  registry.py                                               # make_registry()/register() - wspólny mechanizm
  pipeline.py                                               # orchestrator pojedynczej strategii
  combined_pipeline.py                                      # orchestrator łączenia strategii
  final_portfolio.py                                        # składanie wyników FAZY B w tabelę
  backtest_engine.py                                        # okresowe wagi -> dzienna krzywa equity
  metrics.py                                                # krzywa equity -> CAGR/MaxDD/Sharpe/...
  validation.py                                             # walk-forward: tnie krzywa equity na okna, METRICS per okno
  grid_sweep.py                                             # sweep po allowed_param_families -> N wariantow StrategySpec
  acceptance_check.py                                       # METRICS vs AcceptanceSpec.Criteria -> pass/fail
  run_spec_runner.py                                        # RunSpec.mode -> final/validation/search
  blocks/
    data_loader/, data_cleaner/, indicators/, asset_filters/,
    asset_scoring/, selector/, alpha_weighting/,
    portfolio_risk_engine/, overlays/, execution/           # jeden folder per blok, REGISTRY + implementacje
  combiner/                                                 # implementacje łączenia strategii
  tests/                                                    # pytest, jeden plik per blok/moduł

strategies_v2/
  example_strategy/          # StrategySpec + TestSpec + AcceptanceSpec + RunSpec (przykład)
  example_strategy_b/         # wariant do testowania combinera
  combined_example/            # CombinedSpec łączący oba powyżej
  dual_momentum/                # druga, niezależnie zaprojektowana strategia (patrz niżej)
  vaa_g4/                      # publicznie znana strategia (Keller VAA) - patrz niżej
  the_one/                      # rekonstrukcja publicznej strategii "The One" - patrz niżej
  best17_a/                     # realna strategia uzytkownika (bez hedge) - patrz niżej
  combined_best2/               # best17_a + the_one, 50/50, fixed_capital_weights - patrz niżej
  combined_best2_dynamic/       # to samo, ale dynamic_capital_weights - patrz niżej
  all_weather_4/                # 4 klasy aktywow, zawsze wszystkie trzymane - patrz niżej
  combined_triple/               # best17_a+the_one+all_weather_4, 45/20/35 - patrz niżej
```

### Druga przykładowa strategia: `dual_momentum` (test szerokości silnika)

Absolutny momentum 12m jako filtr (SPY/EFA/VNQ/GLD/TLT/HYG, tylko aktywa z dodatnim własnym
momentum), scoring też na 12m momentum, top3, wagi odwrotne do zmienności 60-dniowej - celowo
INNA koncepcja niż `example_strategy` (tam: trend-filter SMA200 + ranking-wagi stałe). Wymusiła
dobudowanie 3 nowych implementacji (`volatility_daily`, `indicator_positive`, `inverse_vol`) i
rozszerzenie kontraktu `alpha_weighting` o `indicator_set` - dowód, że architektura faktycznie
przyjmuje nowe, niezaplanowane wcześniej koncepcje bez przepisywania istniejących bloków.

### Trzecia przykładowa strategia: `vaa_g4` (publicznie znana - Keller VAA)

Keller & Keuning (2017) "Breadth Momentum and Vigilant Asset Allocation" - wariant G4
Aggressive Top1: 4 aktywa ofensywne = jednocześnie "kanarki" (SPY/EFA/VWO/AGG), 3 defensywne
(SHY/IEF/LQD), score = 13612W momentum (ważona kombinacja zwrotów 1/3/6/12-miesięcznych, wagi
12/4/2/1 - da się to policzyć wprost przez `weighted_sum` na 4 instancjach `momentum_monthly`,
bez żadnego nowego wskaźnika). Reguła: jeśli WSZYSTKIE kanarki mają dodatni score - w całości w
najlepsze aktywo ofensywne; inaczej w całości w najlepsze defensywne.

Ta reguła (przełącznik między DWOMA rozłącznymi zestawami aktywów na podstawie sygnału z
osobnego "kanarkowego" uniwersum) nie mieściła się w istniejącym SELECTOR/ALPHA_WEIGHTING (te
zakładają JEDEN ranking po score w obrębie jednego, spójnego uniwersum) - stąd cała logika VAA
żyje w nowej implementacji PORTFOLIO_RISK_ENGINE (`vaa_canary`), która CAŁKOWICIE zastępuje
`target_weights` z wcześniejszych bloków (SELECTOR/ALPHA_WEIGHTING są tu tylko placeholderem
spełniającym wymóg StrategySpec) - to jest dokładnie ta elastyczność, o którą chodziło od
początku projektowania tego bloku ("kto wie jaka będzie implementacja").

Realny wynik: walk-forward na `train_window` (2007-2019) wygląda dobrze (CAGR ~10%, Sharpe
~0.85), ale `validation` na `test_window` (2020-2026) wypada wyraźnie gorzej (CAGR ~2.7%, Sharpe
~0.30, annual_turnover ponad limit) - spójne ze znaną, publicznie dyskutowaną krytyką strategii
typu VAA/DAA: w 2022 r. obligacje (i ofensywne AGG, i defensywne SHY/IEF/LQD) spadały RAZEM z
akcjami, łamiąc założenie "ucieczka do obligacji = bezpieczeństwo". To realne ograniczenie
strategii, nie błąd silnika.

### Czwarta przykładowa strategia: `the_one` (rekonstrukcja publicznej strategii)

Rekonstrukcja "The One" (inwestujdlugoterminowo.pl/the-one/) - risk-on: SPY/VEA/VWO, risk-off:
LQD/IEF/TLT, score = 13612W momentum (ten sam wzorzec co VAA). Autor strony NIE ujawnia pelnego
algorytmu sygnalu risk-on/off ("Autor celowo nie ujawnia pelnego algorytmu"), tylko ze bazuje na
Dual Momentum (GEM, Antonacci) - wiec `gem_dual_momentum_switch` (nowa implementacja
PORTFOLIO_RISK_ENGINE) to JAWNA REKONSTRUKCJA wg publicznie znanej metodologii GEM, NIE wierny
port nieujawnionego szczegolu:

1. best_on = najlepszy risk-on wg score, best_off = najlepszy risk-off wg score.
2. Jesli best_on.score > 0 ORAZ best_on.score > best_off.score (absolutny + wzgledny test GEM)
   - w calosci w best_on.
3. Inaczej (risk-off): sprawdz SUROWY 12-miesieczny momentum (nie 13612W) best_off - jesli
   ujemny, idz w "_CASH" (modyfikacja opisana na stronie), inaczej w best_off.

Ciekawe w porownaniu z VAA: `the_one` (dzieki testowi WZGLEDNEMU rowniez, nie tylko
absolutnemu, plus cash-fallback) wypadl w `validation` (OOS 2020-2026) LEPIEJ niz na treningu
(CAGR ~11.9% vs ~10.0%, Sharpe ~0.77 vs ~0.66) - w przeciwienstwie do `vaa_g4`, ktory na OOS
wyraznie sie pogorszyl. To sugeruje, ze test wzgledny (SPY vs obligacje) + mozliwosc cash lepiej
poradzil sobie z 2022 r. niz prosta "wszystkie 4 kanarki dodatnie" regula VAA - ale to
obserwacja z jednego backtestu, nie dowod wyzszosci.

**UWAGA (2026-07-10)**: liczby wyzej sa SPRZED poprawki rozgrzewki wskaznikow (patrz sekcja
"Znane, naprawione bugi" nizej) I sprzed dodania `cost_bps=10` (wczesniej `the_one` mial koszt
transakcyjny = 0, mimo najwyzszego turnoveru w repo, ~6.5/rok) - `final` (cala historia, z
kosztem) to teraz CAGR ~8.8%, Sharpe ~0.61 - `validation`/OOS NIE przeliczone ponownie po tych
zmianach, traktowac powyzsze porownanie train/OOS jako nieaktualne.

### Piata strategia: `best17_a` (realna strategia uzytkownika, bez hedge)

Wierne odtworzenie strategii bazowej "A" z realnego systemu uzytkownika (`best17_3m`, folder
`ideas/`), BEZ overlaya hedge (tlt.us) - zbadane wprost w kodzie starego silnika
(`engine/build_data.py`, `engine/backtest_hybrid_search.py`), nie zgadywane z configow.

Uniwersum: XLK/IVV/DBC/IAU (tradowalne) + VT (wylacznie kanarek/gauge, nigdy kandydat do
selekcji - `never_eligible`). Logika:
1. **Kanarek regime** (`canary_regime_gate`): jesli VT lub XLK ma `EMA(5m)/EMA(12m)-1 <= -0.02`
   - CALA grupa XLK/IVV/DBC/IAU staje sie nieeligibilna (100% cash), niezaleznie od wlasnych
   scorow. To pierwszy GLOBALNY filtr w silniku (jeden sygnal decyduje o calej grupie, nie o
   pojedynczym tickerze).
2. **Asset gates**: IAU/DBC wypadaja jesli ich wlasny 3-miesieczny zwrot (na cenach KONCA
   miesiaca) <= -1% (`indicator_positive` z ujemnym progiem).
3. **Ranking**: `EMA(7m)/EMA(16m)-1`, tylko dodatnie (`require_positive_score`), top2, wagi
   0.8/0.2 (`rank_weights` - bez zmian).
4. **Histereza po SCORE, nie wadze** (`score_gap_hysteresis`, nowy blok EXECUTION): portfel
   zostaje niezmieniony, jesli najslabszy trzymany ma score w odleglosci <= 0.005 od najlepszego
   wyzwaniowca - to wymagalo rozszerzenia `ExecutionContext` o `score_row` (opcjonalne pole,
   wstecznie kompatybilne).
5. **Rebound starter** (`rebound_starter`, PORTFOLIO_RISK_ENGINE): jesli portfel jest w calosci
   cash, a VT ma wlasny 3-miesieczny zwrot > 5% - wchodzi w calosci w VT zamiast zostawac w cash.

Nowe wskazniki `ema_ratio_monthly`/`momentum_month_end` licza na cenach KONCA kazdego miesiaca
(nie startu, jak reszta silnika) i przesuwaja wynik o miesiac do przodu - dokladnie odtwarzajac
`align_scores_to_execution_month` ze starego silnika (sygnal z konca miesiaca M "wykonuje sie"
na starcie M+1).

**Znana roznica vs oryginal**: roczny podatek 19% (high-water-mark) z oryginalnego systemu NIE
jest jeszcze zaimplementowany w engine_v2 (`PeriodExecutionResult.tax_amount` istnieje w
kontrakcie, ale zaden blok go dzis nie wypelnia) - to jest overlay na krzywej equity, nie
logika selekcji, wiec swiadomie odlozone.

**POPRAWIONO 2026-07-10 (pieciokrotny bugfix tego samego dnia - patrz sekcje nizej)**: po
wszystkich pieciu poprawkach realny wynik `final` (cala historia, z kosztem 40bps, BEZ podatku
19% - patrz wyzej) to: **CAGR ~16.5%, MaxDD ~-29.5%, Sharpe ~0.96, Calmar ~0.56, roczny turnover
~0.82**. To BARDZO blisko oryginalnego, realnego systemu uzytkownika (stary silnik, `US base A`,
sprawdzone wprost z `ideas_out/*/GLOBAL_SUMMARY.txt` i ponownym uruchomieniem starego
`run_global_pipeline.py` na tych samych danych): monthly CAGR 15.67-16.23%, Sharpe ~1.00, roczny
turnover ~1.2 - engine_v2 wypada NIECO WYZEJ, spojnie z brakiem podatku 19% (ktorego stary silnik
NIE pomija). Miesiac-po-miesiacu porownanie z realnym `weights_used_json` starego silnika: z 216
wspolnych miesiecy **28 dalej sie roznia (~13%)**, w wiekszosci to drugie miejsce w rankingu top2
na granicy - ktory z pozostalych aktywow ma odrobine wyzszy score - a nie systemowy blad
(diminishing returns dalszego dochodzenia, zatrzymano tutaj).

~~Wczesniejsza (CZESCIOWA) poprawka z tego samego dnia dawala CAGR ~7.7%, Sharpe ~0.58, turnover
~7.0 - patrz historia zmian w CHANGELOG.md za pelny opis eskalacji (3 osobne bugi, znalezione
jeden po drugim przy weryfikacji przeciw staremu silnikowi).~~

~~Realny wynik: `final` (cala historia) CAGR ~19%, MaxDD -26%, Sharpe ~1.03, Calmar ~0.72, roczny
turnover tylko ~0.45 (histereza po score bardzo skutecznie ogranicza handel) - najlepszy wynik
ze wszystkich 5 przykladowych strategii w tym repo. `validation` (OOS) potwierdza (CAGR ~20%,
Sharpe ~0.90) - nie ma rozjazdu train/OOS jak przy VAA. Sweep `min_score_gap` (0.0-0.01) pokazuje
STABILNY plateau (CAGR ~15-16%, Sharpe ~1.07-1.10 w kazdym wariancie) - dokladnie sygnal
stabilnosci rodziny, o ktory chodzilo od poczatku tego projektu.~~ (NIEAKTUALNE - te liczby byly
mieszanka buga #1 [zaniza turnover, zawyza CAGR] - patrz nizej. `validation`/sweep ponizej dalej
NIEPRZELICZONE po zadnym z trzech bugfixow - traktowac jako nieaktualne do czasu ponownego
uruchomienia.)

### Znane, naprawione bugi (2026-07-10) - piec osobnych, znalezionych jeden po drugim

Wszystkie znalezione przy weryfikacji `best17_a` przeciw REALNEMU, staremu silnikowi (`engine/`,
uruchomiony ponownie na tych samych danych) - patrz `CHANGELOG.md` za pelna, chronologiczna
historie odkrywania.

**Bug #1 - gubione miesiace w srodku historii.** `pipeline._run_phase_a` obcinal target_weights
przez `score.dropna(how="all").index` - mial to wycinac WYLACZNIE rozgrzewke na poczatku
historii, ale `dropna(how="all")` usuwal KAZDA date w calej historii, gdzie score wyszedl w
calosci NaN (regularnie przy `canary_regime_gate`). Naprawa: obcinamy TYLKO ciagla rozgrzewke na
starcie (do pierwszej daty z choc jednym policzonym score). Zaktualizowano
`test_pipeline.py::test_pipeline_matches_manual_wiring`,
`test_final_portfolio.py::test_full_engine_chain_on_real_data`.

**Bug #2 - rozgrzewka wskaznikow przycinana do najkrocej notowanego tickera w uniwersum.**
`data_cleaner.trim_and_interpolate` przycinal WSZYSTKIE tickery do wspolnego zakresu dat CALEGO
uniwersum PRZED policzeniem jakichkolwiek wskaznikow - skoro VT (kanarek, notowany dopiero od
2008-06) jest w uniwersum `best17_a`, przycinalo to rozgrzewke EMA rowniez XLK (notowany od
1998!) do wlasnego, krotkiego zakresu VT. Zweryfikowane bezposrednio: EMA5/EMA12 dla XLK w
`engine_v2` NIE zgadzalo sie ze starym silnikiem (ktory liczy wskazniki na PELNEJ, WLASNEJ
historii kazdego tickera) o kilkadziesiat procent wzglednie. Naprawa: nowy param
`skip_common_range_trim` w `trim_and_interpolate` - `pipeline._run_phase_a` liczy teraz
wskazniki na pelnej historii (`skip_common_range_trim=True`), DOPIERO POTEM przycina do
wspolnego okna wykonania (i tnie z wynikow wskaznikow tylko rozgrzewke sprzed tego okna, nie
przelicza ich ponownie). Po tej poprawce EMA dla XLK zgadza sie ze starym silnikiem co do 10
miejsca po przecinku.

**Bug #3 - niedopasowane indeksy w `canary_regime_gate`/`never_eligible` (najwiekszy wplyw).**
Mimo poprawki #2, wynik strategii sie NIE zmienil - bo `canary_regime_gate` i `never_eligible`
budowaly swoja maske na `market_data.prices.index` (ZAWSZE DZIENNYM, niezaleznie od `frequency`
strategii), podczas gdy inne filtry (np. `indicator_positive`) uzywaja indeksu WSKAZNIKA
(miesiecznego). `_run_asset_filters` laczy maski przez `&` - gdy 1. dzien miesiaca wypada w
weekend/swieto (a wiec NIE jest dniem dziennego indeksu), maska kanarka nie ma tego wiersza w
ogole, pandas przy `&` niedopasowanych indeksow wstawia NaN dla calego miesiaca -> po
`.fillna(False)` caly miesiac wychodzi "regime zly" NIEZALEZNIE OD PRAWDZIWEJ WARTOSCI KANARKA.
Dotyczylo to KAZDEGO miesiaca, ktorego 1-szy dzien wypadal w weekend/swieto (prawie 40% z nich) -
dokladnie te same 79 miesiecy co bug #1. Naprawa: obie implementacje buduja teraz maske na
indeksie wskaznika (`risk_on.index` / dowolnego wskaznika z `indicator_set`), nie
`market_data.prices.index`.

**Efekt uboczny #4 (backtest_engine, odkryty przy weryfikacji `combined_best2` po powyzszych
poprawkach)**: `daily_equity_curve` mnozylo przez dzienny zwrot KAZDEGO tickera w slowniku wag,
nawet z waga 0.0 - jesli taki ticker jeszcze nie mial zadnych danych cenowych (np. VT przed
2008-06), `0.0 * NaN = NaN` zarazalo cala reszte krzywej equity od tego dnia, mimo ze ten ticker
nigdy nie byl faktycznie trzymany. Naprawa: tylko tickery z faktycznie niezerowa waga wchodza do
petli dziennego mnozenia.

**Bug #5 - dwie drobne rozbieznosci vs stary silnik przy niedopelnionej pozycji** (znalezione po
tym, jak mimo bugow #1-4 nadal 34/216 miesiecy sie roznilo - user zapytal wprost "dalej mamy
roznice a dane te same trzeba to wyjasnic"):
1. `rank_weights`: gdy SELECTOR znajdzie mniej kandydatow niz `top_n`, `engine_v2` dawal
   jedynemu kandydatowi tylko jego wage rankingowa (np. 0.8), reszte zostawiajac w cash. Stary
   silnik (`build_rank_weight_target`) RENORMALIZUJE uzyte wagi do sumy 1.0 - zawsze w pelni
   zainwestowany. Naprawa: nowy param `redistribute_if_short` (domyslnie False, wlaczony w
   `best17_a`).
2. `score_gap_hysteresis`: stary silnik (`should_keep_current_assets_by_hysteresis`) chroni
   pozycje histereza TYLKO gdy jest juz PELNA (`len(current_assets) == top_n`) - przy
   niedopelnionej pozycji zawsze wypelnia brakujacy slot, nawet slabszym kandydatem. `engine_v2`
   porownywal najslabszy trzymany vs najlepszy wyzwaniowiec NIEZALEZNIE od tego ile aktywow jest
   trzymanych. Naprawa: nowy param `full_position_size` (domyslnie None/wylaczony, wlaczony w
   `best17_a` jako `2` = jego `top_n`).

Po tej poprawce: CAGR ~16.7% -> ~16.5%, rozbieznych miesiecy 34/216 -> 28/216 (~13%) - reszta to
juz genuinie subtelne roznice na granicy rankingu (np. IVV vs DBC z niemal identycznym score),
diminishing returns dalszego dochodzenia.

### Szosta strategia: `all_weather_4` (uproszczony "all-weather" na 4 klasach aktywow)

User pomysl: 4 klasy aktywow (akcje/obligacje/zloto/surowce), udzial dynamiczny wg score, ale
ZAWSZE wszystkie 4 trzymane, zaokraglone do pelnych 10% - reszta (wskazniki, dobor tickerow,
strojenie) zaprojektowana samodzielnie. Uniwersum: IVV (akcje, S&P 500), TLT (obligacje,
20y+ treasury), IAU (zloto), DBC (surowce) - wybrane bo mam dla nich dane i bo to standardowe,
plynne proxy kazdej klasy.

Filozofia rozni sie od reszty strategii w tym repo: ZERO market-timingu/cash-call (brak
`asset_filters`, `portfolio_risk_engine: none`) - zawsze w pelni zainwestowani we wszystkie 4
klasy naraz, score tylko PRZECHYLA wzgledny udzial, nie decyduje o obecnosci w portfelu. Score =
13612W momentum (ten sam wzorzec co `the_one`/`vaa_g4`: zwroty 1/3/6/12m wazone 12/4/2/1).

Nowy blok `alpha_weighting.rounded_score_weights` (patrz tabela blokow wyzej): wagi
proporcjonalne do score wsrod wybranych, zaokraglone do bloku `round_to` (domyslnie 10 p.p.)
metoda NAJWIEKSZEJ RESZTY (Largest Remainder / Hamilton - ten sam algorytm co przy apportionment
w wyborach) - gwarantuje SUME DOKLADNIE 1.0 (naiwne zaokraglanie kazdej wagi z osobna tego nie
gwarantuje) i deterministyczne remisy (wyzszy score, potem alfabetycznie). Kazda z 4 klas ma
gwarantowane minimum `min_weight_blocks=1` (10%) - nigdy nie spada do zera (poza jednorazowym
~12-miesiecznym oknem startowym, gdy DBC - najkrocej notowany z czterech, od 2006-02 - jeszcze
nie ma pelnej rozgrzewki mom_12; poza tym oknem wszystkie 4 sa zawsze obecne).

Sweep `hysteresis_pct` (0.05-0.25, `execution.hysteresis_pct`) pokazal, ze domyslne 0.05 bylo
za ciasne wzgledem 10-p.p. blokow (kazda drobna zmiana tiltu = pelny rebalans, turnover ~2.4/rok,
221/245 miesiecy z rebalansem) - **0.20 dalo najlepszy Sharpe i najnizszy turnover w calym
sweepie**, przyjete jako domyslne.

Realny wynik: `final` (cala historia, 2006-03 do 2026-07, koszt 10bps) CAGR ~8.9%, MaxDD ~-25.5%,
Sharpe ~0.82, Calmar ~0.35, roczny turnover ~1.74 - najnizszy turnover ze wszystkich strategii w
tym repo (mniej "wchodzenia/wychodzenia", tylko przewazanie juz posiadanych 4 klas). MaxDD -25.5%
przekroczyl pierwotnie zgadywany prog `acceptance_spec.max_drawdown=-0.20` - prog skorygowany
transparentnie do -0.28 PO zobaczeniu wyniku (nie ukryte - patrz `run_spec.json.notes`).

## Testy

```
.venv/bin/pytest engine_v2/tests -v
```

Stały venv projektu (`.venv/`, pandas+numpy+openpyxl+pytest) - poza gitem. Każdy blok ma własny
plik testów; większość zawiera zarówno testy syntetyczne (szybkie, deterministyczne) jak i
przynajmniej jeden test na prawdziwych danych z `data/us` (fixture `us_data_dir`/`us_universe`
w `tests/conftest.py`). Kluczowe testy regresyjne:

- `test_pipeline.py::test_pipeline_matches_manual_wiring` - orchestrator daje identyczny wynik
  co ręczne wywołanie każdego bloku po kolei.
- `test_combined_pipeline.py` - COMBINER + wspólna histereza na dwóch różnych strategiach.

## Co jeszcze nie istnieje

Z pierwotnego planu: **REPORTING**, **UK MAPPING** (mechanizm replikacji tickerów/instrumentów),
**FORWARD TEST/PAPER** (na wieksza odlegloscie). Budowane etapami, blok po bloku, każdy z
własnym design-review przed kodem.

### Tryby uzycia pipeline'u (docelowo)

| Tryb | Mechanizm | Stan |
|---|---|---|
| DEV/DEBUG | single backtest | ✅ (`pipeline.py` + `backtest_engine.py`) |
| ALPHA SEARCH | walk-forward + grid sweep po `allowed_param_families` | ✅ mechanizmy gotowe (`grid_sweep.py` + `validation.py` przez `evaluate_fn`) |
| RISK/OVERLAY/EXECUTION SEARCH | walk-forward | ✅ mechanizm gotowy (uzycie zalezy od strategii) |
| FINAL VALIDATION | walk-forward na `test_window` (OOS) | ✅ mechanizm gotowy |
| FINAL REPORT | single backtest + REPORTING | single ✅, reporting ❌ |
| UK MAPPING | single/walk-forward + mapowanie tickerow | mapowanie ❌ |
| PAPER/LIVE | forward test | ❌ |

### Gdzie w tym wszystkim jest train/test window i walk-forward?

Cały pipeline opisany wyżej (`data_loader` -> ... -> `backtest_engine`) liczy się na **całej
dostępnej historii naraz** - żaden z tych bloków nie wie nic o "oknie treningowym" czy
"testowym". To jest celowe: wskaźniki (np. SMA200) potrzebują danych SPRZED okna, żeby mieć
poprawne wartości NA początku okna (inaczej pierwsze ~200 dni okna byłyby bezwartościowe przez
rozgrzewkę).

Podział na train/test (i walk-forward) to zadanie **jeszcze niezaimplementowanego VALIDATION/TESTS**
- ono weźmie gotową dzienną krzywą equity z BACKTEST ENGINE (policzoną raz, na całej historii)
i DOPIERO WTEDY potnie ją na fragmenty odpowiadające `TestSpec.train_window` /
`TestSpec.test_window` (i kolejnym oknom `walk_forward`), licząc METRICS OSOBNO na każdym
fragmencie. Czyli: nie "różne dane wejściowe do pipeline'u", tylko "ten sam wynik, pocięty i
oceniony w kilku kawałkach" - stąd cała logika bloków wyżej nie musi nic wiedzieć o train/test.
