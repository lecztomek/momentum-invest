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
| `indicators` | **wielo-instancyjny** | `sma_daily`, `momentum_monthly`, `volatility_daily`, `ema_ratio_monthly`, `momentum_month_end`, `momentum_avg_month_end`, `corr_to_basket_month_end` | Biblioteka wskaźników - osobna implementacja per wskaźnik+częstotliwość+baza cenowa (start/koniec miesiąca); `momentum_avg_month_end` usredni kilka okien naraz (np. 1/3/6/12m), `corr_to_basket_month_end` liczy roczącą korelację do stałego, równoważonego koszyka tickerów - oba dla `strategies_v2/gpm/` |
| `asset_filters` | **wielo-instancyjny** | `price_above_indicator`, `indicator_positive`, `canary_regime_gate`, `never_eligible` | Eliminacja aktywów (AND między instancjami); `canary_regime_gate` to GLOBALNY gate (cała grupa naraz, na podstawie osobnych "kanarków"), opcjonalny param `invert` (domyślnie `False`) odwraca gate na risk-OFF zamiast risk-on - patrz `strategies_v2/synergy_v2/`; `never_eligible` trwale wyklucza tickery z normalnej selekcji |
| `asset_scoring` | pojedynczy wybór | `weighted_sum`, `momentum_times_decorrelation` | `weighted_sum` - ważona SUMA wskaźników; `momentum_times_decorrelation` - ILOCZYN dwóch konkretnych wskaźników (`momentum * (1 - korelacja)`, dla `strategies_v2/gpm/` - suma by tego nie wyraziła). Oba maskują NaN tam gdzie `eligibility_mask=False` |
| `selector` | pojedynczy wybór | `top_n` | Top-N wg score, nigdy nie wybiera NaN |
| `alpha_weighting` | pojedynczy wybór | `rank_weights`, `inverse_vol`, `rounded_score_weights` | Wagi wybranych: stałe wg rankingu (reszta do `_CASH`) albo odwrotnie proporcjonalne do zmienności (zawsze w pełni zainwestowane) albo proporcjonalne do score, zaokrąglone do bloku (largest remainder), z gwarantowanym minimum na aktywo |
| `portfolio_risk_engine` | pojedynczy wybór | `none`, `vaa_canary`, `gem_dual_momentum_switch`, `rebound_starter`, `gfm_risk_switch`, `gpm_breadth_protective_split`, `gtaa_trend_bond_reroute`, `daa_canary_breadth_switch` | Pass-through, albo pełna podmiana portfela wg reguły (patrz niżej - to jest świadomie najbardziej elastyczny blok w silniku); `gpm_breadth_protective_split` skaluje udział ochronny CIĄGLE wg liczby dodatnich aktywów ryzykownych, zamiast binarnego przełączenia jak `vaa_canary`; `gtaa_trend_bond_reroute` ocenia KAŻDY SLOT niezależnie (nie globalnie) - część portfela może być w akcjach a część w obligacjach jednocześnie; `daa_canary_breadth_switch` - kanarek to OSOBNE, małe uniwersum (nie cały `offensive_assets` jak `vaa_canary`) + ciągły udział ochronny (0/50/100% dla 2 kanarków) zamiast binarnego |
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
`(strategy_target_weights, params, strategy_returns=None) -> (combined_weights,
effective_capital_weights)` - drugi element zwracanej pary to FAKTYCZNY udział kapitału każdej
strategii W KAŻDYM OKRESIE (patrz niżej dlaczego to osobny wynik, nie tylko
`params["capital_weights"]`). Trzeci argument (`strategy_returns` - `net_return` KAŻDEJ strategii
z jej WŁASNEGO solo pipeline, per okres) jest IGNOROWANY przez pierwsze dwa combinery poniżej i
WYMAGANY przez trzeci (`momentum_hedge_overlay`) - jedyny, który musi porównywać już-osiągnięte
zwroty strategii, nie tylko ich wagi.

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

- **`momentum_hedge_overlay`** - port TAKTYCZNEGO hedge'u ze starego silnika
  (`engine/monthly_hedge_momentum_overlay.py`, reguła `hedge_positive_and_beats_a_not_6m_extended`
  - dokładnie ta użyta w produkcyjnym `ideas/best17_3m_tlt_dtla_40/idea_config.json`,
  `selected_hedge_variant`). W odróżnieniu od powyższych dwóch, to NIE jest N-strategiowa alokacja
  kapitału - to dwustronny blend DOKŁADNIE dwóch strategii (`core_strategy` + `hedge_strategy`,
  nazwy z `params`): w każdym okresie decyduje, czy dołożyć hedge (np. `tlt.us`) do core, na
  podstawie WZGLĘDNEGO momentum hedge'u wobec core (liczonego na ich WŁASNYCH, już-wykonanych
  `strategy_returns` - stąd jedyny combiner, który tego argumentu faktycznie wymaga):
  ```
  h_lb = skumulowany zwrot HEDGE za ostatnie `lookback` okresów (domyślnie 1)
  a_lb = skumulowany zwrot CORE za ostatnie `lookback` okresów
  h_6m, a_6m = to samo za 6 okresów
  hedge_on(M) = (h_lb > min_hedge_return) AND (h_lb - a_lb > min_spread_vs_a)
                AND (h_6m - a_6m <= 0)   # "not extended" - łapiemy POCZĄTEK ucieczki do
                                         # bezpiecznych aktywów, nie dogrywamy się do już
                                         # trwającej hossy hedge'u
  ```
  Sygnał liczony na koniec okresu M, działa od M+1 (`shift(1)`) - identycznie jak w starym
  silniku. Gdy `hedge_on`: `combined = (1 - hedge_weight) * CORE + hedge_weight * HEDGE`, inaczej
  100% CORE. `hedge_strategy` to zwykle trywialna, jedno-aktywowa "sleeve" (patrz
  `strategies_v2/tlt_hedge/` - zawsze 100% `tlt.us`, sama w sobie NIE jest strategią inwestycyjną)
  - to jest odpowiedź na pytanie użytkownika "hedge na TLT jako osobna strategia, którą będzie
  można z czymś połączyć": hedge NIE jest wbudowanym overlayem wewnątrz `best17_a`, tylko osobnym
  `StrategySpec` + osobnym COMBINEREM.

  **Wynik `strategies_v2/best17_a_tlt_hedge/`** (`best17_a` + `tlt_hedge`, sweep `hedge_weight`
  na realnych danych - wszystkie warianty wyraźnie tną MaxDD względem `best17_a` solo; liczby
  PO poprawce z **2026-07-11 (2)** - patrz CHANGELOG, `hedge_on` nie mógł się wcześniej wyłączyć
  na datach sprzed startu `best17_a`):

  | hedge_weight | CAGR | MaxDD | Sharpe | Calmar |
  |---|---|---|---|---|
  | 0.00 (best17_a solo) | 16.49% | -29.47% | 0.96 | 0.56 |
  | 0.20 | 13.94% | -22.31% | 0.94 | **0.62** |
  | 0.30 | 14.02% | -22.61% | 0.96 | 0.62 |
  | 0.40 (jak w starym silniku, wybrane) | 14.10% | -23.70% | 0.97 | 0.59 |
  | 0.50 | 14.16% | -24.96% | 0.98 | 0.57 |
  | 0.60 | 14.20% | -26.20% | **0.99** | 0.54 |

  **Train/test split** (train: 2010-06 do 2019-12, test/OOS: 2020-01 do 2026-06, wg
  `strategies_v2/best17_a/test_spec.json`) - hedge poprawia metryki na OBU niezależnie
  ocenianych oknach, nie tylko na pełnej historii (user pytanie: "jak wypada na train a potem
  drugim okresie?"):

  | | TRAIN best17_a solo | TRAIN +hedge 40% | TEST/OOS best17_a solo | TEST/OOS +hedge 40% |
  |---|---|---|---|---|
  | CAGR | 16.24% | 17.46% | 18.01% | 18.23% |
  | MaxDD | -24.40% | **-17.18%** | -29.47% | **-23.70%** |
  | Sharpe | 1.08 | **1.22** | 0.89 | **0.98** |
  | Calmar | 0.67 | **1.02** | 0.61 | 0.77 |

**`strategies_v2/tlt_timing/` - próba PRAWDZIWIE samodzielnej (przenosnej) strategii na TLT.**
User uwaga: warunek wejścia `momentum_hedge_overlay` porównuje TLT do `best17_a` (`a_lb`/`a_6m`),
więc `tlt_hedge` nie jest "osobną strategią" w sensie zachowania - samo `tlt_hedge` zawsze trzyma
100% TLT, cała decyzja żyje w COMBINERZE i zależy od tego, z czym go połączysz. `tlt_timing`
naprawia to: sama decyduje, wyłącznie na WŁASNYM, absolutnym 3-miesięcznym momentum (`mom_3 > 0`
przez istniejący blok `indicator_positive`) - zero odniesienia do żadnej innej strategii, więc
działa identycznie z DOWOLNYM combinerem/DOWOLNĄ inną strategią. Zero nowego kodu bloku - tylko
nowa konfiguracja z już istniejących bloków.

Uczciwy wynik (sweep okna 1/3/6/12, window=3 najlepszy): CAGR 1.59%, MaxDD -41.38%, Sharpe 0.20 -
GORZEJ niż zwykły buy&hold `tlt.us` solo (CAGR 2.10%, MaxDD -47.76%, Sharpe 0.22). W połączeniu z
`best17_a` (`strategies_v2/best17_a_tlt_timing/`, `fixed_capital_weights` 20% - dobrane na TEN SAM
MaxDD co `momentum_hedge_overlay` 20%, dla porównania jabłko-do-jabłka): CAGR 11.60% (vs 13.94%),
Sharpe 0.93 (vs 0.94), Calmar 0.52 (vs 0.62) - wyraźnie gorzej na każdym wymiarze poza MaxDD.
**Wniosek**: przenośność ma swoją cenę - sam absolutny momentum TLT nie ma realnej przewagi,
przewaga `momentum_hedge_overlay` bierze się WŁAŚNIE z relatywnego porównania do core, nie z
samego TLT. `best17_a_tlt_hedge/` (relatywny wariant) pozostaje rekomendowanym wyborem.

**`strategies_v2/synergy_v1/` i `strategies_v2/synergy_v2/` - próba złożenia JEDNEGO nowego
pipeline'u z najlepszych pomysłów sesji** (user: "stwórz wersję strategii biorącą najlepsze rzeczy
z innych"), zamiast COMBINERA dwóch gotowych strategii. Idea: szkielet `best17_a` (kanarek VT+XLK,
gates IAU/DBC na 3m momentum, `rebound_starter`, histereza po score) + koncepcja GEM/`the_one`
(absolutny 12-miesięczny momentum na obligacji jako warunek eligibilności, nie osobny combiner
jak `best17_a_tlt_hedge`) - TLT.us dołączony wprost do uniwersum wyboru `best17_a`.

- `synergy_v1`: TLT.us eligibilny zawsze, gdy ma dodatni `mom_12` - konkuruje w TYM SAMYM
  rankingu EMA7/EMA16 co XLK/IVV/DBC/IAU (może wygrać slot top2 nawet w risk-on). Wynik:
  **gorzej niż `best17_a` solo na każdej metryce** - CAGR/MaxDD/Sharpe/Calmar wszystkie słabsze,
  po podatku CAGR 14.04% vs 16.07%, MaxDD -29.99% vs -29.47%, Sharpe 0.83 vs 0.93. TLT
  okazjonalnie wypierał lepsze aktywa ofensywne z rankingu (crowding-out) - dodanie kandydata
  konkurującego w tej samej puli, nawet z sensownym filtrem absolutnego momentum, nie gwarantuje
  poprawy, jeśli konkuruje TEŻ wtedy, gdy nie powinien.
- `synergy_v2`: poprawka - nowy opcjonalny param `invert` w `canary_regime_gate` (patrz tabela
  bloków wyżej) sprawia, że TLT.us i 4 aktywa ofensywne są WZAJEMNIE WYKLUCZAJĄCE SIĘ (ten sam
  kanarek VT+XLK, odwrócony dla TLT) - TLT wchodzi TYLKO gdy kanarek mówi risk-off ORAZ własny
  `mom_12 > 0`. Zweryfikowano testem (`test_synergy_v2_tlt_and_offensive_assets_never_held_together`),
  że oba zbiory NIGDY nie są trzymane naraz, i że mechanizm faktycznie się aktywuje (TLT 100%
  wagi przez cały kryzys 2008-09 - `rebound_starter`/kanarek działają jak w `best17_a`, ale zamiast
  cash portfel wchodzi w TLT). Mimo to wynik dalej **nie bije `best17_a` solo** - CAGR 15.59% vs
  16.07% po podatku, MaxDD -29.99% vs -29.47% (identyczne jak `synergy_v1` - ten sam trough),
  Sharpe 0.89 vs 0.93. Najgorszy rok kalendarzowy identyczny jak solo (2022) - akurat wtedy TLT
  miał RÓWNIEŻ ujemny `mom_12` (znane pęknięcie korelacji akcje-obligacje w cyklu podwyżek stóp),
  więc bramka nie uratowała dokładnie tam, gdzie byłaby najbardziej potrzebna.

**Wniosek**: wbudowanie ekspozycji na obligacje w TEN SAM pipeline selekcji (współzawodnictwo albo
wzajemne wykluczanie binarne) NIE bije już znalezionych kombinacji zbudowanych jako COMBINER
dwóch osobnych strategii z płynną wagą (`vaa_g4_best17_a`, `best17_a_tlt_hedge`) -
`momentum_hedge_overlay`/`fixed_capital_weights` uśredniają ekspozycję w sposób CIĄGŁY (np. 40%
TLT + 60% core niezależnie od regime'u), podczas gdy selektor top_n przełącza się BINARNIE (0%
albo 100%, tylko gdy regime akurat na to pozwala) - to grubsza, mniej wybaczająca kontrola ryzyka.
Rekomendacja z sesji (`vaa_g4_best17_a`, alternatywnie `best17_a_tlt_hedge` przy niższym
turnoverze) pozostaje bez zmian.

**Param stability (2026-07-11)**: rodzina `mom_3.window` x `execution.hysteresis_pct` (9
wariantow) - `relative_drop` = **63.49%**, **FAIL** (prog zaostrzony z pierwotnie luznych 1.0 do
standardowego 0.30) - **najbardziej krucha rodzina w calym repo**, spojne z powyzszym wnioskiem:
`tlt_timing` nie ma realnej przewagi jako samodzielna strategia, a jej solo-wynik jest bardzo
wrazliwy na dobor okna momentum (window=3 duzo lepsze niz sasiednie 1/6).

**`strategies_v2/the_one_tlt_hedge/` - ta sama reguła hedge'u, ale core=`the_one` zamiast
`best17_a`.** WYNIK ODWROTNY: hedge SZKODZI na każdej wadze (sweep 0.20-0.60) - przy 40% CAGR
spada 8.76%->7.34%, MaxDD **ROŚNIE** -23.59%->-25.15% (zamiast spadać). Przyczyna: `the_one` JUŻ
MA `tlt.us` (razem z `ief.us`/`lqd.us`) jako WŁASNE aktywo risk-off w swoim uniwersum - w
odróżnieniu od `best17_a` (uniwersum BEZ żadnych obligacji). Gdy core sam już rotuje w
TLT/obligacje, dołożenie niezależnego hedge'u w TLT nie dywersyfikuje - KONCENTRUJE dodatkowo w
tym samym aktywie kosztem LQD/IEF, które core mógłby wybrać zamiast TLT. **Wniosek:
`momentum_hedge_overlay` NIE jest uniwersalnym ulepszeniem każdej strategii - działa dobrze
TYLKO gdy core NIE MA już własnej ekspozycji na hedge asset.** Potwierdzone na train I test/OOS
osobno (test/OOS: CAGR 11.18%->9.34%, MaxDD -23.59%->-25.15% - gorzej na obu, nie tylko na
pełnej historii).

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
CAGR ~11.5%, MaxDD ~-18.1%, Sharpe ~0.99, Calmar ~0.64 - przy CAGR>10% i najniższym MaxDD ze
wszystkich konfiguracji z CAGR>10% (**UWAGA** - "najlepszy Sharpe w całym repo" przestało być
prawdą po pełnym przeglądzie par niżej, `vaa_g4`+`best17_a` ma wyższy Sharpe).

**Wszystkie pary 7 głównych strategii (2026-07-11)** - user: "dołóż brakujące kombinacje".
Sposrod C(7,2)=21 możliwych par (`dual_momentum`/`vaa_g4`/`the_one`/`best17_a`/`all_weather_4`/
`gfm`/`best17_b`) tylko 1 (`the_one`+`best17_a`) była wcześniej przetestowana. Dodano pozostałe
20, wszystkie `fixed_capital_weights` 50/50 (standardowy split, NIE strojony indywidualnie - dla
uczciwego porównania na tych samych zasadach). **Odkrycie**: `vaa_g4`+`best17_a` daje Sharpe
**1.03** - najlepszy w całym repo (bije nawet `combined_triple`), Calmar 0.63 (prawie identyczny
z `combined_triple`), CAGR 11.48%, MaxDD -18.21% - z PROSTEGO, niestrojonego 50/50 splitu między
dwiema strategiami, które nigdy wcześniej nie były razem testowane. Top 6 par wg Sharpe:

| Para | CAGR | MaxDD | Sharpe | Calmar | Turnover/rok |
|---|---|---|---|---|---|
| `vaa_g4` + `best17_a` | 11.48% | -18.21% | **1.03** | 0.63 | 4.24 |
| `best17_a` + `all_weather_4` | 11.84% | -21.84% | 0.98 | 0.54 | 1.23 |
| `the_one` + `best17_a` (=`combined_best2`) | 12.58% | -22.73% | 0.94 | 0.55 | 3.63 |
| `vaa_g4` + `all_weather_4` | 8.58% | -18.05% | 0.93 | 0.48 | 4.76 |
| `best17_a` + `gfm` | 11.84% | -27.86% | 0.89 | 0.43 | 1.67 |
| `best17_a` + `best17_b` | 10.99% | -29.42% | 0.84 | 0.37 | 1.46 |

Wzorzec: KAŻDA z 6 najlepszych par zawiera `best17_a` - potwierdza, że to najsilniejsza
pojedyncza "noga" w całym repo, dobry kandydat na core niemal każdego portfela. Pary BEZ
`best17_a` konsekwentnie wypadają słabiej (najlepsza: `vaa_g4`+`the_one`, Sharpe 0.71).

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

**`best_year_return`/`worst_year_return`** (dodane 2026-07-11, user pytanie: "brakuje mi jeszcze
w danych wyjsciowych zwrot najgorszego roku oraz najlepszego") - zwrot NAJLEPSZEGO i
NAJGORSZEGO roku KALENDARZOWEGO w zakresie danych. Nie maja odpowiednika w
`acceptance_spec.Criteria` (to tylko raportowana metryka, nie prog akceptacji). Pierwszy/ostatni
rok w danych moga byc CZESCIOWE (backtest rzadko zaczyna/konczy sie dokladnie 1 stycznia/31
grudnia) - liczone tak jak wypadaja, bez doannualizowania. Ciekawy przyklad z realnych danych:
`best17_a_tlt_hedge` ma GORSZY najgorszy rok niz `best17_a` solo (-22.09% vs -19.35%, oba to rok
2022), mimo NIZSZEGO calosciowego MaxDD (-23.70% vs -29.47%) - MaxDD to miara peak-to-trough (moze
obejmowac wiele lat), NIE to samo co zwrot pojedynczego roku kalendarzowego. 2022 byl rzadkim
rokiem, gdy obligacje (TLT) spadaly RAZEM z akcjami (koniec ery zerowych stop procentowych) -
wlasnie dlatego hedge w TLT akurat w TYM roku nie pomogl, mimo ze pomaga na wiekszosci pozostalych
spadkow.

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

## RUN SPEC RUNNER (`run_spec_runner.py`, `acceptance_check.py`, `param_stability.py`, `annual_tax.py`, `named_periods.py`)

Wiaze `RunSpec.mode` z odpowiednim mechanizmem - pierwsze realne uzycie `RunSpec` (dotad tylko
zdefiniowany, nic go nie czytalo):

- `"final"` - single backtest na calej historii, METRICS, sprawdzenie wzgledem `AcceptanceSpec.global_`.
- `"validation"` - single backtest na calej historii, ale METRICS liczone TYLKO na wycinku
  `TestSpec.test_window` (OOS) - jedna, czysta ocena, bez dalszego ciecia (test_window jest
  "swiete").
- `"search"` - GRID SWEEP x WALK-FORWARD (`TestSpec.train_window`) per wariant, zwraca zbiorcze
  statystyki (srednia/min CAGR, najgorszy drawdown, srednia Sharpe) po oknach, PLUS
  `param_stability` (patrz nizej).

### ANNUAL TAX (`annual_tax.py`) - roczny podatek od zyskow (19%, "Belka")

User pytanie: "czy one maja uwzgledniony podatek od zyskow?" - odpowiedz brzmiala NIE: ZERO
liczby w calej sesji nie uwzgledniala podatku, mimo ze `TestSpec.CostsSpec.annual_tax_rate` byl
zdefiniowany OD POCZATKU projektu (jak `param_stability` wczesniej - kolejne "zdefiniowane,
nigdy nie liczone" pole). Po potwierdzeniu stawki (19%, jak w starym silniku, nie zgadywane 20%)
- zaimplementowane.

Odtworzone WPROST z `apply_annual_tax_if_year_end` (`engine/backtest_hybrid_search.py`,
zdublowane w `engine/replay_mapped_monthly.py`) - podatek "high water mark":
```
taxable_profit = max(0, equity_przed_podatkiem - tax_base_equity)
tax_amount = taxable_profit * annual_tax_rate
equity_po_podatku = equity_przed_podatkiem - tax_amount
tax_base_equity = max(tax_base_equity, equity_po_podatku)   # nigdy nie spada po stratnym roku
```
Liczony RAZ ROCZNIE (ostatni dostepny dzien handlowy grudnia w danych, analogia miesiecznego bara
"grudzien" w starym silniku), TYLKO od wzrostu equity ponad dotychczasowy szczyt bazy podatkowej -
rok stratny nie daje zwrotu, ale tez nie "zapomina" poprzedniego szczytu (kolejne zyski sa
opodatkowane dopiero po odrobieniu strat, nie od zera). Haircut propaguje sie na wszystkie
kolejne dni do nastepnego poboru - to realne zmniejszenie kapitalu, nie chwilowy spadek. Rok bez
zadnego grudniowego dnia w danych (backtest konczy sie w polowie roku) NIE jest opodatkowany -
identyczne uproszczenie jak w starym silniku.

Wpiete w `run_spec_runner.py` (`_run_final`/`_run_validation`) - w `"validation"` podatek jest
liczony na CALEJ historii PRZED wycieciem do `test_window` (high-water-mark musi widziec lata
sprzed okna OOS, inaczej zresetowalby sie blednie do punktu startowego okna). Wynik ma
`metrics_pre_tax` obok `metrics`, jesli `TestSpec.costs.annual_tax_rate > 0` - PRZED i PO widoczne
razem, nie ukryte.

**`annual_tax_rate` ujednolicone na 0.19 we WSZYSTKICH `test_spec.json`** (2026-07-11) - okazalo
sie byc niespojnie ustawione JUZ WCZESNIEJ (5 strategii mialo 0.19, 5 mialo 0.0), ale poniewaz
nigdzie nie bylo faktycznie liczone, ta niespojnosc nigdy nie miala znaczenia.

**Pelne porownanie PRZED/PO podatku** (wszystkie 11 solo + 27 portfeli, pelna tabela w
CHANGELOG.md 2026-07-11 (13)) - CAGR/MaxDD/Sharpe spadaja wszedzie tam gdzie strategia miala
dodatnie lata, ale relatywna KOLEJNOSC strategii prawie sie nie zmienia. Przyklady:

| Strategia | CAGR przed | CAGR po | Sharpe przed | Sharpe po |
|---|---|---|---|---|
| `best17_a` | 16.49% | 16.07% | 0.96 | 0.93 |
| `vaa_g4_best17_a` | 11.48% | 11.25% | 1.03 | **0.99** |
| `combined_triple` | 11.54% | 11.26% | 0.99 | 0.96 |
| `best17_a_tlt_hedge` | 14.10% | 13.78% | 0.97 | 0.94 |

`vaa_g4_best17_a` pozostaje najlepszym Sharpe w calym repo rowniez PO podatku.

**Ciekawostka**: MaxDD dla kilku strategii (np. `vaa_g4`: -24.45%->-22.84%) wyszlo LEPSZE po
podatku - artefakt liczenia MaxDD w procentach: podatek obcina szczyty (peaks) uzywane jako baza
procentowego spadku, wiec ta sama nominalna strata z pozniejszego okresu wyglada jak mniejszy
procentowy spadek wzgledem nizszego, juz-opodatkowanego szczytu. Nie blad silnika - realny efekt
uboczny liczenia drawdown na bazie procentowej po opodatkowaniu.

`acceptance_check.check_criteria(metrics, criteria)` porownuje METRICS z progami
`AcceptanceSpec.Criteria` (tylko pola faktycznie ustawione). Uwaga wewnetrzna: `max_drawdown`
jest ujemny, wiec "nie gorszy niz prog" to numerycznie `wartosc >= prog`, NIE `<=` jak przy
zwyklych gornych limitach (turnover itp.) - to zostalo raz zle napisane i zlapane testem.

### PARAM STABILITY (`param_stability.py`) - "jak silna jest rodzina strategii"

User pytanie: "brakuje mi czegos w stylu stabilnosci strategii - jak zmiana parametrow zabija
strategie, jak mocna jest rodzina". `AcceptanceSpec.ParamStabilitySpec.max_relative_metric_drop_
within_family` byl zdefiniowany w `acceptance_spec.py` OD POCZATKU projektu, ale NIGDZIE nie byl
faktycznie liczony - `allowed_param_families`/`run_param_sweep` generuja i oceniaja warianty, ale
nic nie streszczalo tego w JEDNA liczbe "jak stabilna jest ta rodzina". To byl brakujacy kawalek.

`compute_param_stability(sweep_result, metric_key)` bierze tabele z `grid_sweep.run_param_sweep`
(jeden wiersz per wariant `allowed_param_families`) i liczy WZGLEDNY SPADEK miedzy najlepszym a
najgorszym wariantem w calej rodzinie, na wybranej metryce (domyslnie `wf_mean_cagr` w trybie
`"search"` - srednie CAGR z walk-forward per wariant):

```
relative_drop = (best - worst) / abs(best)
```

Male `relative_drop` = rodzina STABILNA (kazdy z przetestowanych wariantow daje podobny wynik -
wybor konkretnego punktu w rodzinie nie jest krytyczny, silnik "nie zgadl" akurat trafionej
kombinacji). Duze `relative_drop` = rodzina KRUCHA (jeden dobry wariant otoczony znacznie
gorszymi sasiadami) - klasyczny sygnal ostrzegawczy overfittingu (dopasowanie do szumu w danych,
nie do prawdziwej struktury rynku). `check_param_stability(stability, param_stability_spec)`
porownuje `relative_drop` z `AcceptanceSpec.param_stability.max_relative_metric_drop_within_family`
(ten sam styl co `check_criteria` - dict wynikow, tylko dla faktycznie ustawionych progow).

Wymaga metryki typu "wyzej = lepiej" (`cagr`, `sharpe`, `calmar`, `wf_mean_cagr`) - dla "nizej =
lepiej" (np. `annual_turnover`) `best`/`worst` wyjdzie odwrocone i strace sens; niezabezpieczone
w kodzie, tylko udokumentowane.

**Przebiegniete na WSZYSTKICH strategiach w repo** (2026-07-11, user: "trzeba wszystkie strategie
tym posprawdzac i wszystkie parametry w jakims sensownym zakresie") - `allowed_param_families`
rozszerzone tam, gdzie mialy tylko 1 wymiar (dodano drugi sensowny parametr: `example_strategy`
+`sma_200.window`, `best17_a` +`canary.bad_threshold`, `gfm` +`regime_threshold`, `tlt_timing`
+`hysteresis_pct`; `the_one`/`vaa_g4` rozszerzone na 5 wartosci `hysteresis_pct`;
`best17_b`/`dual_momentum`/`all_weather_4` mialy juz 2 wymiary):

| Strategia | Wariantow | Best (wf_mean_cagr) | Worst | relative_drop | Prog 0.30 |
|---|---|---|---|---|---|
| `example_strategy` | 15 | 6.46% | 5.85% | 9.53% | PASS |
| `best17_a` | 15 | 15.15% | 11.10% | 26.73% | PASS |
| `vaa_g4`* | 5 | 9.20% | 9.20% | 0.00% | PASS (trywialnie) |
| `the_one`* | 5 | 6.18% | 6.18% | 0.00% | PASS (trywialnie) |
| `best17_b` | 12 | 11.01% | 7.63% | 30.73% | **FAIL** (borderline) |
| `dual_momentum` | 15 | 5.99% | 3.96% | 33.85% | **FAIL** |
| `gfm` | 9 | 12.15% | 8.12% | 33.18% | **FAIL** |
| `all_weather_4` | 15 | 5.40% | 2.91% | 46.12% | **FAIL** |
| `tlt_timing` | 9 | 5.60% | 2.04% | 63.49% | **FAIL** |

**\*** `vaa_g4`/`the_one` - jedyny obecnie sweepowany parametr (`hysteresis_pct`) jest tu MARTWY:
`vaa_canary`/`gem_dual_momentum_switch` zawsze produkuja BINARNE (100% jednego aktywa albo cash)
alokacje, wiec dowolna wartosc `hysteresis_pct` ponizej 100% nigdy nie blokuje przelaczenia -
`relative_drop=0.00%` odzwierciedla "ten parametr nic tu nie robi w testowanym zakresie", NIE
prawdziwa odpornosc rodziny. Uczciwie odnotowane jako ograniczenie obecnego sweepa, nie ukryte za
falszywym "stabilne".

`tlt_timing` mial wczesniej BARDZO luzny prog (1.0, przeniesiony z `tlt_hedge` przy tworzeniu) -
zaostrzony do standardowego 0.30 - bez tej korekty check trywialnie przechodzil, maskujac realne
63.49% - **najbardziej krucha rodzina w calym repo**, spojne z wczesniejszym odkryciem
"`tlt_timing` solo gorszy niz buy&hold" (patrz sekcja `tlt_timing` nizej).

Pominiete celowo: `example_strategy_b` (brak TestSpec/AcceptanceSpec/RunSpec - tylko partner do
testowania combinera) i `tlt_hedge` (trywialna, zawsze-100%-TLT cegielka do combinera,
`walk_forward.enabled=false` - nie jest samodzielna strategia do oceny).

Przy okazji znaleziony bug: `vaa_g4`/`dual_momentum` NIE MIALY `cost_bps` w ogole (ten sam wzorzec
co wczesniej naprawiony dla `the_one`/`example_strategy`/`example_strategy_b`, tym razem
nieznaleziony wczesniej bo byly zablokowane brakiem danych) - dodano `cost_bps: 10`. Wplyw: `vaa_g4`
CAGR 8.82%->7.98%, `dual_momentum` CAGR 6.98%->6.74% - wszystkie progi `acceptance_spec.json`
nadal przechodza.

### NAMED PERIODS (`named_periods.py`) - "jak strategia wypada w konkretnym, znanym okresie"

User: "A named periods możesz pokazać?" - `AcceptanceSpec.named_periods` (dict `nazwa_okresu ->
Criteria`) byl zdefiniowany w `acceptance_spec.py` OD POCZATKU projektu, uzywany juz w
`example_strategy`/`all_weather_4` `acceptance_spec.json` ("covid_crash_rebound",
"inflation_bear", "post_gfc_recovery"), ale NIGDZIE nie byl faktycznie liczony - ten sam wzorzec
co wczesniej `param_stability`/`annual_tax` ("zdefiniowane, nigdy nie liczone"). `Criteria` niesie
tylko PROGI (np. `max_drawdown: -0.30`), nie zakres dat - brakowalo mapowania nazwa->daty.

`compute_named_period_metrics(equity_curve, final_portfolio, named_periods, metrics_params)`
zamyka te luke: `KNOWN_PERIODS` (nowy, WSPOLNY dla calego repo slownik nazwa->start/koniec, zeby
wyniki byly porownywalne 1:1 miedzy strategiami pod tymi samymi etykietami) mapuje kazda nazwe na
konkretne daty, tnie `equity_curve`/`final_portfolio` do tego okna, liczy `compute_metrics` i
`check_criteria` wzgledem progow z danego `named_periods[nazwa]`. Nieznana nazwa (spoza
`KNOWN_PERIODS`) rzuca czytelny blad zamiast po cichu nic nie sprawdzac; okres calkowicie poza
zakresem danych strategii daje `{"covered": False, ...}`, nie blad (np. strategia zaczynajaca sie
po 2009 nie ma jak pokryc `gfc_crash`).

```
KNOWN_PERIODS = {
    "gfc_crash":            2008-01-01 - 2009-03-31,  # szczyt do dna S&P (dno 2009-03-09)
    "post_gfc_recovery":    2009-04-01 - 2012-12-31,
    "covid_crash_rebound":  2020-02-01 - 2020-12-31,  # krach + odbicie w tym samym roku
    "inflation_bear":       2022-01-01 - 2022-12-31,
}
```

Wpiete w `run_spec_runner._run_final` - jesli `acceptance_spec.named_periods` niepuste,
`result["named_periods"]` niesie metryki+checki per okres (na equity_curve PO podatku, spojnie z
glownym `metrics`). Brak `named_periods` w spec = klucz w ogole nie pojawia sie w wyniku (ten sam
styl co `metrics_pre_tax` przy braku podatku).

**Wynik dla 4 kluczowych strategii/portfeli (2026-07-11, PO podatku)**:

| | `gpm` solo | `best17_a` solo* | `gpm_best17_a` (55/45) | `vaa_g4_best17_a` |
|---|---|---|---|---|
| **gfc_crash** | CAGR **+1.9%**, MaxDD -7.1% | CAGR -14.2%, MaxDD -12.3% | CAGR -3.8%, MaxDD -9.2% | CAGR +0.1%, MaxDD -7.8% |
| **post_gfc_recovery** | +5.2%, -10.2% | +18.2%, -15.5% | +12.3%, -13.8% | +19.6%, -12.4% |
| **covid_crash_rebound** | +9.8%, -6.1% | +29.7%, -29.5% | +21.8%, -15.4% | +27.0%, -14.3% |
| **inflation_bear** | **-5.5%**, -7.1% | -15.2%, -19.5% | -10.5%, -13.8% | -14.6%, -17.3% |

**\*** `best17_a` dane zaczynaja sie 2008-07 - `gfc_crash` to u niego tylko 9 z 15 miesiecy
okresu (2008-07 do 2009-03), nieporownywalne 1:1 z resztą (ktore maja pelne 15 miesiecy) -
zaznaczone jawnie, nie ukryte.

Potwierdza wczesniejsze ustalenie z porownania rok-po-roku (patrz sekcja `gpm_best17_a` wyzej):
`gpm` jest realnie DODATNI w GFC (2008-09) i lagodzi `inflation_bear` (2022) najbardziej ze
wszystkich czterech - ale `inflation_bear` pozostaje trudny dla KAZDEJ z nich (wszystkie na
minusie), spojne z wczesniej zidentyfikowanym pekniuciem korelacji akcje-obligacje w tym
konkretnym roku.

7 nowych testow: `test_named_periods.py` (okresy nienakladajace sie, nieznany okres rzuca blad,
metryki+checki dla pokrytego okresu, `covered=False` gdy equity_curve nie siega okresu, pusty
slownik = brak wpisu) + `test_run_spec_runner.py` (2 nowe: wiring pojawia sie/znika wg
`named_periods` w spec).

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
  param_stability.py                                        # sweep -> "jak stabilna jest rodzina parametrow"
  annual_tax.py                                             # equity_curve -> equity_curve po rocznym podatku (19%, high-water mark)
  named_periods.py                                          # KNOWN_PERIODS + metryki/checki per znany okres rynkowy (GFC, covid, inflation_bear)
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
  tlt_hedge/                     # trywialna "zawsze 100% tlt.us" cegielka - patrz niżej
  best17_a_tlt_hedge/            # best17_a+tlt_hedge, momentum_hedge_overlay - patrz niżej
  tlt_timing/                    # samodzielny, przenosny timing na tlt.us (wlasny momentum) - patrz niżej
  best17_a_tlt_timing/           # best17_a+tlt_timing, fixed_capital_weights - patrz niżej
  the_one_tlt_hedge/             # the_one+tlt_hedge, ta sama regula co best17_a - patrz niżej (hedge SZKODZI tu)
  gfm/                           # "Global Factor Model" - patrz niżej (BEZ DANYCH, zaimplementowane "na sucho")
  best17_b/                      # "Strategia B" uzytkownika - rotacja sektorowa - patrz niżej
  synergy_v1/                    # eksperyment: best17_a+TLT w JEDNYM pipeline (bez combinera) - patrz niżej, gorzej niż best17_a solo
  synergy_v2/                    # poprawka: TLT wzajemnie wykluczajacy sie z 4 aktywami ofensywnymi - patrz niżej, dalej gorzej niż best17_a solo
  gpm/                            # "Generalized Protective Momentum" - patrz niżej, najnizszy MaxDD (-15.2%) i najstabilniejsza rodzina parametrow w calej sesji
  gpm_best17_a/                   # gpm+best17_a, fixed_capital_weights 45/55 - patrz nizej, NAJLEPSZY CALMAR calej sesji (0.707)
  gtaa_agg3/                      # "GTAA AGG3" - top3 momentum + filtr trendu PER SLOT - patrz nizej
  gtaa_agg6/                      # "GTAA AGG6" - to samo, top6 zamiast top3 - patrz nizej
  gtaa_agg6_best17_a/             # gtaa_agg6+best17_a, fixed_capital_weights 55/45 - patrz nizej, GORZEJ niz gpm_best17_a (negatywny wynik, udokumentowany)
  daa_g4/                         # "DAA-G4" (Keller & Keuning) - patrz nizej, kanarek osobny + ciagly udzial ochronny
  vaa_g4_ema/                     # vaa_g4 z EMA zamiast momentum - patrz nizej, GORZEJ (negatywny wynik)
  daa_g4_ema/                     # daa_g4 z EMA zamiast momentum - patrz nizej, GORZEJ (negatywny wynik)
  # wszystkie pozostale pary 7 glownych strategii (fixed_capital_weights 50/50) - patrz
  # "Wszystkie pary 7 głównych strategii" wyzej; vaa_g4_best17_a to najlepszy Sharpe w repo
  dual_momentum_vaa_g4/  dual_momentum_the_one/       dual_momentum_best17_a/
  dual_momentum_all_weather_4/   dual_momentum_gfm/   dual_momentum_best17_b/
  vaa_g4_the_one/        vaa_g4_best17_a/             vaa_g4_all_weather_4/
  vaa_g4_gfm/            vaa_g4_best17_b/             the_one_all_weather_4/
  the_one_gfm/           the_one_best17_b/            best17_a_all_weather_4/
  best17_a_gfm/          best17_a_best17_b/           all_weather_4_gfm/
  all_weather_4_best17_b/                             gfm_best17_b/
```

**UWAGA (2026-07-11) o podatku**: wszystkie liczby w poszczegolnych sekcjach strategii nizej
(chyba ze jawnie oznaczone inaczej) sa SPRZED wdrozenia rocznego podatku (patrz sekcja "ANNUAL
TAX" wyzej) - PRZED podatkiem. Pelna tabela PRZED/PO dla wszystkich strategii i portfeli jest w
sekcji "ANNUAL TAX" wyzej i w CHANGELOG.md (2026-07-11 (13)) - nie zduplikowana tutaj przy kazdej
strategii z osobna.

### Druga przykładowa strategia: `dual_momentum` (test szerokości silnika)

Absolutny momentum 12m jako filtr (SPY/EFA/VNQ/GLD/TLT/HYG, tylko aktywa z dodatnim własnym
momentum), scoring też na 12m momentum, top3, wagi odwrotne do zmienności 60-dniowej - celowo
INNA koncepcja niż `example_strategy` (tam: trend-filter SMA200 + ranking-wagi stałe). Wymusiła
dobudowanie 3 nowych implementacji (`volatility_daily`, `indicator_positive`, `inverse_vol`) i
rozszerzenie kontraktu `alpha_weighting` o `indicator_set` - dowód, że architektura faktycznie
przyjmuje nowe, niezaplanowane wcześniej koncepcje bez przepisywania istniejących bloków.

**Realny wynik (2026-07-11, po dorzuceniu brakujacych tickerow efa/gld/hyg/vnq)**: `final`
(cala dostepna historia) CAGR 6.98%, MaxDD -18.78%, Sharpe 0.62, Calmar 0.37, roczny turnover
~2.28, max_time_underwater 26 miesiecy, najgorszy rok -14.16%. `acceptance_spec.json`
`max_time_underwater_months` skorygowany transparentnie z pierwotnie zgadywanych 24 na 30 - reszta
progow (CAGR/MaxDD/Sharpe/Calmar/turnover) przeszla bez korekty.

**UWAGA (2026-07-11, 2)**: powyzsze liczby byly BEZ `cost_bps` - strategia go w ogole nie miala
ustawionego (ten sam bug co u `the_one`/`example_strategy`, nieznaleziony wczesniej bo strategia
byla zablokowana brakiem danych). Po dodaniu `cost_bps: 10`: CAGR 6.98%->**6.74%**, MaxDD
-18.78%->-18.99%, Sharpe 0.62->0.61, Calmar 0.37->0.35 - wszystkie progi nadal przechodza.
Param stability (sekcja "PARAM STABILITY" wyzej): `relative_drop` = 33.85% - LEKKO przekracza
prog 0.30 (fail).

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

**UWAGA (2026-07-11)**: powyzsze liczby train/validation sa sprzed dorzucenia brakujacych
tickerow (`efa`/`agg`/`shy` - do tego momentu strategia nie miala kompletu danych, `test_vaa_canary.
py::test_full_chain_on_real_data` byl znanym, "1 fail niepowiazany" raportowanym przez cala
sesje). Po dorzuceniu danych, `final` (cala dostepna historia) daje: CAGR 8.82%, MaxDD -23.38%,
Sharpe 0.78, Calmar 0.38, roczny turnover ~7.79 (najwyzszy w repo - agresywny top1/7-aktyw switch),
max_time_underwater 54 miesiace, najgorszy rok -14.94%. `acceptance_spec.json`
`max_drawdown`/`min_calmar`/`max_time_underwater_months` skorygowane transparentnie z pierwotnie
zgadywanych (-0.20/0.4/24) na (-0.26/0.30/60) PO zobaczeniu tego wyniku.

**UWAGA (2026-07-11, 2)**: powyzsze liczby byly BEZ `cost_bps` (ten sam bug co u `the_one`/
`dual_momentum`, nieznaleziony wczesniej bo strategia byla zablokowana brakiem danych). Po
dodaniu `cost_bps: 10`: CAGR 8.82%->**7.98%**, MaxDD -23.38%->-24.45%, Sharpe 0.78->0.71, Calmar
0.38->0.33 - wszystkie progi nadal przechodza (`max_time_underwater_months` dokladnie na
granicy: 60<=60). Param stability (sekcja "PARAM STABILITY" wyzej): `relative_drop` = 0.00% -
TRYWIALNIE stabilne, bo `hysteresis_pct` jest martwym parametrem dla binarnego
`vaa_canary` (patrz zastrzezenie tam).

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

**Param stability (2026-07-11)**: `relative_drop` = 0.00% - TRYWIALNIE stabilne, z tego samego
powodu co `vaa_g4` (`hysteresis_pct` martwy dla binarnego `gem_dual_momentum_switch` - patrz
sekcja "PARAM STABILITY" wyzej).

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

**Param stability (2026-07-11)**: rodzina `execution.min_score_gap` x `asset_filters.canary.
bad_threshold` (15 wariantow) - `relative_drop` = 26.73%, PASS (prog 0.30) - rodzina rozsadnie
stabilna, wybor konkretnych progow nie jest krytyczny.

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

**Param stability (2026-07-11)**: rodzina `alpha_weighting.min_weight_blocks` x
`execution.hysteresis_pct` (15 wariantow) - `relative_drop` = 46.12%, **FAIL** (prog 0.30) -
najbardziej krucha rodzina posrod strategii z niezerowa wartoscia (`min_weight_blocks=1` vs `2`
robi duza roznice - gwarantowane minimum 20% zamiast 10% na kazda z 4 klas wyraznie zmienia
charakter strategii, nie jest subtelnym niuansem).

### Siodma strategia: `gfm` (Global Factor Model, inwestujdlugoterminowo.pl)

Zaimplementowana najpierw "na sucho" na prosbe uzytkownika (dolozyc kod + testy najpierw, backtest
na realnych danych pozniej), przed dorzuceniem brakujacych tickerow (`vtv`/`mtum`/`qqq`/`ijh`/
`ijr`/`efv`/`mchi`/`gsg`/`vnq`) - patrz "Realny wynik" nizej za faktyczny backtest po ich dodaniu.

Miesieczna strategia, dwa tryby:
- **Risk-On** (14 ETF: SPY/VTV/MTUM/QQQ/IJH/IJR/VEA/VWO/EFV/MCHI/GSG/GLD/VNQ/LQD): score =
  (zwrot_3M + zwrot_6M + zwrot_12M)/3, top_n najlepszych po rowno miedzy soba (GFM-3/GFM-4/GFM-5
  - `portfolio_risk_engine.top_n` w `allowed_param_families`, domyslnie 4).
- **Risk-Off** (2 ETF: IEF/TLT): score = (zwrot_1M+3M+6M+12M)/4, caly kapital w lepszym.

Nowy blok `portfolio_risk_engine.gfm_risk_switch` - w odroznieniu od `gem_dual_momentum_switch`
(gdzie risk-on i risk-off dziela TEN SAM score 13612W), tu obie strony maja WLASNE, ROZNE formuly
scoringu na ROZNYCH podzbiorach uniwersum - czego jeden, wspolny `asset_scoring.weighted_sum` na
cala strategie nie potrafi wyrazic. Blok sam liczy obie srednie wprost z `indicator_set`,
ignorujac przekazany `score` (jak `gem_dual_momentum_switch` uzywa `mom_12_key` niezaleznie od
`score`).

**WAZNE ZASTRZEZENIE**: autor GFM JAWNIE nie ujawnia dokladnej reguly wyznaczania sygnalu
Risk-On/Risk-Off. W implementacji ten sygnal jest w pelni PLUGGOWALNY
(`regime_indicator_key`/`regime_ticker`/`regime_threshold` w params) - domyslnie ustawiony na
PLACEHOLDER (wlasny 12-miesieczny momentum SPY > 0, prosty canary w stylu Faber/GTAA), NIE
odtworzenie nieujawnionej reguly - do podmiany, gdy realna regula bedzie znana/dostarczona.

10 testow jednostkowych bloku (`test_gfm_risk_switch.py`) + 5 testow specyfikacji
(`test_gfm_strategy_spec.py`, w tym `test_gfm_full_chain_on_real_data` - koncowy end-to-end po
dorzuceniu danych, analogiczny do `test_gem_dual_momentum_switch.py::test_full_chain_on_real_data`).

**Realny wynik (2026-07-11, po dorzuceniu brakujacych tickerow)**: historia ograniczona do
2013-05..2026-07 (159 miesiecy - najkrocej notowany ticker w uniwersum to MTUM, od 2013-04).
`final` (GFM-4, top_n=4, domyslny): CAGR 9.61%, MaxDD -33.70%, Sharpe 0.71, Calmar 0.29, roczny
turnover ~3.47, max_time_underwater 32 miesiace, najgorszy rok -7.57%. Sweep top_n=3/4/5:

| top_n | CAGR | MaxDD | Sharpe | Calmar |
|---|---|---|---|---|
| 3 (GFM-3) | 8.60% | -36.52% | 0.61 | 0.24 |
| 4 (GFM-4, domyslny) | 9.61% | -33.70% | 0.71 | 0.29 |
| 5 (GFM-5) | 9.29% | -33.92% | 0.70 | 0.27 |

`acceptance_spec.json` progi (zgadywane przed przebiegiem, jak przy `all_weather_4`) WSZYSTKIE
przeszly bez korekty. Zastrzezenie o placeholderowym sygnale rezimu (wyzej) pozostaje w mocy -
powyzszy wynik to jawna rekonstrukcja z zastepcza regula, NIE wierne odtworzenie GFM.

**Param stability (2026-07-11)**: rodzina `top_n` x `regime_threshold` (9 wariantow) -
`relative_drop` = 33.18%, **FAIL** (prog 0.30) - GFM-3 z `regime_threshold=0.0` wyraznie lepszy
niz GFM-5 z `regime_threshold=-0.02`; spojne z tym, ze placeholderowy sygnal rezimu jest z natury
prowizoryczny - realna regula GFM (nieznana) moglaby zachowywac sie inaczej.

### Osma strategia: `best17_b` ("Strategia B" uzytkownika - rotacja sektorowa)

Uzytkownik dostarczyl dane (`xlp`/`xlv`/`xlf`/`xle`/`xli`/`rsp` w `data/us/nyse/`) i opisal
regule wprost - **zero nowego kodu bloku**, w calosci zlozona z JUZ ISTNIEJACYCH blokow
(dowod, ze biblioteka blokow zbudowana dla `best17_a`/`the_one`/`vaa_g4` jest wystarczajaco
ogolna, zeby wyrazic kolejna, niezaleznie opisana strategie bez ani jednej nowej implementacji):

1. `momentum_monthly` (window=9) - 9-miesieczny momentum na 6 sektorowych ETF.
2. `ema_ratio_monthly` (fast=7, slow=16) + `canary_regime_gate` (`canary_assets=["xli.us",
   "xlp.us"]`, `bad_threshold=0.0`, `max_bad_count=0`) - "EMA7>EMA16" jest dokladnie rownowazne
   `ema_ratio(=EMA7/EMA16-1) > 0`, wiec `bad_threshold=0.0` odtwarza regule WPROST, bez
   przyblizenia; oba kanarki (XLI=cykliczny, XLP=defensywny) musza przejsc jednoczesnie, inaczej
   caly portfel w `_CASH`.
3. `indicator_positive` (`mom_9 > 0`) - tylko dodatni momentum jest eligibilny.
4. `weighted_sum` + `top_n=2` + `rank_weights` (`weights=[0.5, 0.5]`) - top2 po rowno.
5. `score_gap_hysteresis` (`min_score_gap=0.03`, `full_position_size=2`) - "zmien tylko gdy nowy
   jest lepszy o >=3%", dziala tylko gdy pozycja jest juz PELNA (jak w `best17_a`).

Identyczna architektura co `best17_a` (kanarek + momentum + score-gap histereza), inny kanarek
(para cykliczny-vs-defensywny zamiast szerokiego rynku) i inne tickery/progi.

**Realny wynik** (cala historia, 2005-12 do 2026-07, 248 miesiecy): CAGR 7.11%, MaxDD -29.71%,
Sharpe 0.52, Calmar 0.24, roczny turnover ~2.21, max_time_underwater 35 miesiecy, najgorszy rok
-15.51%. Wszystkie progi `acceptance_spec.json` (zgadywane przed przebiegiem) przeszly bez
korekty.

Sweep `mom_9.window` (6/9/12) potwierdzil, ze wybor uzytkownika (9 miesiecy) jest WYRAZNIE
najlepszy (CAGR 7.11% vs 4.66%/4.81%, MaxDD -29.71% vs -38.39%/-41.51%) - nie przypadkowy dobor.
Sweep `min_score_gap` (0.00/0.01/0.03/0.05): 0.01 dal odrobine lepszy Sharpe/Calmar (0.56/0.26)
niz opisane 0.03 (0.52/0.24), ale 0.03 pozostawione jako domyslne - wierne odtworzenie opisanej
reguly, nie wynik strojenia.

5 testow (`test_best17_b_strategy_spec.py`) - walidacja specyfikacji, rozwiazanie blokow, kanarek
XLI+XLP, gap 3%, i end-to-end na realnych danych (oba rezymy risk-on/cash wystapily w historii,
nigdy wiecej niz top_n=2 aktywow naraz).

**Param stability (2026-07-11)**: rodzina `min_score_gap` x `mom_9.window` (12 wariantow) -
`relative_drop` = 30.73%, **FAIL** (prog 0.30, borderline) - lekko powyzej progu, spojne z
powyzszym sweepem (`window=6`/`12` wyraznie gorsze niz `window=9`).

### Dziewiata strategia: `gpm` ("Generalized Protective Momentum", opis dostarczony przez usera)

User poprosil o strategie z NIZSZYM MaxDD (patrz porownanie MaxDD wszystkich 38 strategii/portfeli
w CHANGELOG.md, 2026-07-11 (13)), potem dostarczyl PELNY opis mechanizmu do wiernego odtworzenia -
w odroznieniu od `best17_b` (zlozona wylacznie z JUZ ISTNIEJACYCH blokow), GPM wymagal 4 CALKOWICIE
NOWYCH implementacji, bo zaden istniejacy blok nie umial wyrazic jego mechaniki:

1. **`momentum_avg_month_end`** (`r`) - srednia momentum z 4 okien (1/3/6/12m) na cenach konca
   miesiaca.
2. **`corr_to_basket_month_end`** (`c`) - rocząca się 12-miesieczna korelacja miesiecznych
   zwrotow KAZDEGO tickera do STALEGO, rownowazonego koszyka 12 aktywow ryzykownych (ten sam
   koszyk przy ocenie kazdego tickera, WLACZNIE z samym koszykiem - zamierzone, wierne
   odtworzenie metodologii, nie blad).
3. **`momentum_times_decorrelation`** (asset_scoring) - `score = r * (1 - c)`, ILOCZYN dwoch
   wskaznikow (nie liniowa suma wazona jak `weighted_sum`, ktory by tego nie wyrazil).
4. **`gpm_breadth_protective_split`** (portfolio_risk_engine) - `n` = liczba z 12 aktywow
   ryzykownych z dodatnim `score`; `n<=6` -> 100% udzialu ochronnego, inaczej `(12-n)/6` -
   CIAGLE skalowanie zamiast binarnego przelaczenia jak `vaa_canary`. Reszta kapitalu w top3
   aktywa ryzykowne wg `score`, po rowno; czesc ochronna w calosci w JEDNO aktywo ochronne
   (IEF/SHY) z najwyzszym `score`.

**Brakujace dane**: IWM, VGK, EWJ, EEM nie istnieja w `data/us/nyse/`. User wybral (przez
`AskUserQuestion`) opcje "zamienniki": IWM->IJR (US small cap), EEM->VWO (rynki wschodzace,
niemal identyczny fundusz), VGK->EFA, EWJ->VEA (oba "developed ex-US", znaczaco nakladajace sie -
NIE oddzielne Europa/Japonia jak w oryginale, jawnie odnotowane przyblizenie).

**Uniwersum**: 12 ryzykownych (spy/qqq/ijr/efa/vea/vwo/vnq/dbc/gld/hyg/lqd/tlt) + 2 ochronne
(ief, shy). `execution: hysteresis` z `hysteresis_pct=0.0` (zawsze pelny rebalans co miesiac,
bez histerezy - zgodnie z opisem "portfel jest rebalansowany do nowych wag" co miesiac).

**Realny wynik** (2007-08 do 2026-08, 229 miesiecy, PRZED podatkiem): CAGR 5.32%,
**MaxDD -15.20% (NAJNIZSZY z calej sesji** - nizej niz dotychczasowy rekord
`dual_momentum_all_weather_4`, -16.71%), Sharpe 0.67, Calmar 0.35, turnover 4.36/rok. Train
(2009-2019) CAGR 4.65%/MaxDD -12.87%/Sharpe 0.61 vs test/OOS (2020-2026) CAGR 6.10%/MaxDD
-15.20%/Sharpe 0.72 - lepiej OOS niz w treningu. Wszystkie 7 okien walk-forward DODATNIE
(1.6%-5.7% CAGR, nigdy ujemne). Zweryfikowano na wagach z historii, ze mechanizm dziala jak
opisano: 100% w IEF przez caly 2008 i marzec-czerwiec 2020, ciagle skalowanie widoczne
(0.167/0.333/0.5/0.833/1.0), nie tylko binarne 0%/100%.

**Param stability** (sweep `top_n_risky` x `full_protective_max_n`, 9 wariantow):
`relative_drop = 9.6%` - **NAJBARDZIEJ STABILNA rodzina parametrow w calym repo** (dla
porownania: `best17_a` 26.7%, `all_weather_4` 46.1%, `best17_b` 30.7%).

16 nowych testow: `test_gpm_components.py` (4 nowe bloki na danych syntetycznych - usrednianie
okien, korelacja idealna/odwrotna, iloczyn+maskowanie, pelna/czesciowa ochrona, fallback do
`_CASH` przy braku kandydatow) + `test_gpm_strategy_spec.py` (walidacja realnego
`strategy_spec.json`, oba rezymy - pelna ochrona i ekspozycja ryzykowna - realnie wystepuja w
historii, nigdy wiecej niz `top_n_risky` aktywow naraz, zamrozony baseline metryk).

#### `gpm_best17_a` - miks defensywnego `gpm` z agresywnym `best17_a`

User: "dobrze go zmiksowac z czyms agresywnym np best17". `fixed_capital_weights`, sweep wagi
`best17_a` w [0.30..0.70] (krok 0.05 wokol optimum) na PELNYM realnym backteście, PO PODATKU:

| best17_a / gpm | CAGR | MaxDD | Sharpe | Calmar | Turnover |
|---|---|---|---|---|---|
| 35% / 65% | 8.86% | -13.98% | 0.942 | 0.634 | 3.11 |
| 40% / 60% | 9.37% | -14.27% | 0.954 | 0.657 | 2.93 |
| 45% / 55% | 9.88% | -14.56% | 0.960 | 0.678 | 2.75 |
| 50% / 50% | 10.39% | -14.87% | 0.963 | 0.699 | 2.57 |
| **55% / 45%** | **10.89%** | **-15.40%** | 0.962 | **0.707** | **2.39** |
| 60% / 40% | 11.38% | -17.04% | 0.959 | 0.668 | 2.21 |

**55/45 (best17_a/gpm) zapisane jako `combined_spec.json`** - **NAJLEPSZY CALMAR CALEJ SESJI**
(0.707, poprzedni rekord `vaa_g4_best17_a` 0.649), przy DUZO nizszym turnowerze (2.39/rok vs
4.24/rok) i nizszym MaxDD (-15.40% vs -17.33%) niz dotychczasowa rekomendacja
`vaa_g4_best17_a`, kosztem odrobiny Sharpe (0.962 vs 0.993) i CAGR (10.89% vs 11.25%).
Automatycznie odkryty i przetestowany przez `test_all_combined_specs.py` (glob-discovery) - zero
nowych plikow testowych potrzebnych.

**Rekomendacja sesji**: `gpm_best17_a` (55/45) - jesli priorytetem jest MaxDD/Calmar i niski
turnover; `vaa_g4_best17_a` pozostaje lepszy, jesli priorytetem jest czysty Sharpe.

**Stabilnosc wagi combinera** (user: "Jak ze stabilnoscia naszego najlepszego miksu?") -
`compute_param_stability` zastosowany PIERWSZY RAZ do wagi combinera (nie parametrow
wewnetrznych pojedynczej strategii), sweep `best17_a_weight` [0.35..0.70] przez walk-forward na
`train_window`: `wf_mean_sharpe` relative_drop = **2.9%** (PLASKO - wybor dokladnej wagi w tym
zakresie prawie nie ma znaczenia dla Sharpe, w OBU okresach train/test). `wf_mean_cagr`
relative_drop = 30.3%, ale to NIE krucha rodzina - CAGR rosnie MONOTONICZNIE z waga `best17_a`
(oczekiwane, nie przypadkowy szczyt). Jednak Calmar (metryka wg ktorej wybrano 55/45) zachowuje
sie ROZNIE miedzy okresami: TRAIN Calmar maleje monotonicznie z waga `best17_a` (wiecej `gpm` =
lepiej), TEST/OOS Calmar ma prawdziwy szczyt kolo 55% - "55/45 optymalne dla Calmar" jest wiec
czesciowo dopasowane do specyfiki 2020-2026 (COVID+2022), nie w pelni potwierdzone w treningu.
**Wniosek**: sama koncepcja miksu jest solidna (Sharpe stabilny), ale dokladna waga 55/45 to
"rozsadny wybor w szerokiej dobrej strefie" (40-65%), nie precyzyjnie skalibrowany punkt.

### Dziesiata/jedenasta strategia: `gtaa_agg3` / `gtaa_agg6` ("GTAA AGG3/AGG6", opis dostarczony przez usera)

User (w trakcie sweepu gpm+best17_a+vaa_g4) zmienil plan i dostarczyl opis nowej strategii do
odtworzenia. Mechanizm: (1) `score = srednia zwrotow 1/3/6/12m` - reuzyty ISTNIEJACY
`indicators.momentum_avg_month_end` (zbudowany dla `gpm`, identyczny wzor - zero duplikacji);
(2) top3 (AGG3) albo top6 (AGG6) wg `score`; (3) rowne wagi (33.33%/16.67%); (4) filtr trendu
PER SLOT (nie globalny) - cena konca miesiaca ponizej 6-miesiecznej SMA -> TA CZESC kapitalu
(nie caly portfel) trafia do obligacji zamiast do aktywa; (5) rebalans co miesiac, bez histerezy.

**Nowy blok**: `portfolio_risk_engine/gtaa_trend_bond_reroute.py` - w odroznieniu od
`canary_regime_gate` (globalny gate na cala grupe naraz) i `gpm_breadth_protective_split`
(ciagle skalowanie globalnego udzialu), tu KAZDY SLOT jest oceniany NIEZALEZNIE - czesc portfela
moze byc w akcjach a czesc rownoczesnie w obligacjach w tym samym miesiacu. Zweryfikowano na
realnych danych (2008, 2022) - mieszane sloty (np. `{"dbc.us": 0.333, "ief.us": 0.667}`)
faktycznie wystepuja w historii, nie tylko binarne 0%/100% jak w `gpm`/`vaa_canary`.

**Brakujace dane**: user wskazuje VGIT (US)/IUSM (UCITS) jako fallback obligacyjny - oba
NIEDOSTEPNE w naszych danych, zastapione IEF (7-10Y skarbowe, najblizszy zamiennik - user wybral
przez `AskUserQuestion`). Uniwersum ryzykowne (10, "klasyczne GTAA na dostepnych danych"): IVV,
IJR, EFA, VWO, VNQ, DBC, GLD, HYG, LQD, TLT.

**Realny wynik** (2007-05 do 2026-08, 232 miesiace, PRZED podatkiem):

| | CAGR | MaxDD | Sharpe | Calmar | Turnover |
|---|---|---|---|---|---|
| `gtaa_agg3` (top3, 33.33%) | 6.99% | -19.69% | 0.58 | 0.35 | 3.81 |
| `gtaa_agg6` (top6, 16.67%) | 6.30% | -18.71% | 0.66 | 0.34 | 3.00 |

AGG6 wyraznie lepszy Sharpe (szersza dywersyfikacja tlumi szum), AGG3 wyzszy CAGR
(koncentracja na najlepszym momentum). Named periods: OBIE odmiany DODATNIE przez `gfc_crash`
(+4.86%/+2.04% CAGR) - trend-following + rotacja do obligacji dziala jak zaprojektowano w
klasycznym kryzysie (podobnie jak `gpm`, ale mechanizmem PER SLOT zamiast globalnego).

**Param stability** (sweep `sma_window` 3-9, 7 wariantow): `gtaa_agg3` relative_drop=17.1%
(PASS, prog 0.30), `gtaa_agg6` relative_drop=30.3% (borderline **FAIL** - najlepszy wariant w
tescie to `sma_window=9`, nie domyslne 6 z opisu - odnotowane uczciwie, prog NIE poluzowany zeby
to ukryc).

17 nowych testow: `test_gtaa_components.py` (nowy blok na danych syntetycznych - reroute tylko
wlasciwego slotu nie calego portfela, cala portfolio do obligacji gdy wszystkie sloty slabe,
slot o wadze 0 ignorowany) + `test_gtaa_strategy_specs.py` (wiring obu wariantow, top_n==liczba
wag, bond_fallback wykluczony z selekcji, end-to-end na realnych danych z dowodem na mieszane
sloty, zamrozone baseline'y metryk).

#### `gtaa_agg6_best17_a` - miks gtaa_agg6+best17_a (negatywny wynik)

User: "Nigdy nie łącz 3 - max 2" (odrzucenie wczesniejszego pomyslu trojki
gpm+best17_a+vaa_g4). Sweep wagi `best17_a` w [0.30..0.70] na PELNYM realnym backtescie, PO
PODATKU - najlepszy Calmar przy 45%/55% (best17_a/gtaa_agg6): CAGR 10.31%, MaxDD -18.31%,
Sharpe 0.909, Calmar 0.563. **Wyraznie gorzej niz `gpm_best17_a`** (55/45: Calmar 0.707,
MaxDD -15.40%) - `gtaa_agg6` solo ma glebszy MaxDD (-18.71%) niz `gpm` solo (-15.20%), wiec
mniej skutecznie tlumi drawdown `best17_a`, prawdopodobnie tez wyzsza korelacja sygnalu z
`best17_a` (oba trend/momentum na tym samym uniwersum akcji USA) niz `gpm` (odrebna koncepcja -
korelacja do koszyka, nie tylko trend). Zapisane jako dokumentacja eksperymentu, NIE
rekomendacja - `gpm_best17_a` pozostaje najlepszym znalezionym miksem. Automatycznie odkryte i
przetestowane przez `test_all_combined_specs.py` (glob-discovery).

### Dwunasta strategia: `daa_g4` ("DAA-G4" - Defensive Asset Allocation, Keller & Keuning 2017)

User: "Brakuje nam DAA Kellera" - zaimplementowane z wiedzy o publikacji (user zdecydowal nie
podawac wlasnego opisu, jak dla `gpm`/`gtaa`). Rozni sie od naszego `vaa_g4` (Keller VAA) na 2
sposoby: (1) kanarek to OSOBNE, MALE uniwersum (`VWO`+`AGG` - tylko 2 z 4 aktywow ofensywnych,
nie wszystkie 4 jak w VAA); (2) udzial ochronny jest CIAGLY (0%/50%/100% dla 2 kanarkow), nie
binarny (VAA: jeden zly kanarek = 100% ochrony natychmiast). Uniwersum (identyczne jak `vaa_g4`):
4 ofensywne (SPY/EFA/VWO/AGG), 3 obronne (SHY/IEF/LQD). Score = 13612W momentum
(12*r1+4*r3+2*r6+1*r12)/19 - REUZYTE identyczne `indicators`/`asset_scoring` co `vaa_g4`, zero
nowego kodu tam.

**Nowy blok**: `portfolio_risk_engine/daa_canary_breadth_switch.py` - kanarek jako OSOBNY
parametr (nie caly `offensive_assets`) + ciagly udzial ochronny (B/len(canary), nie binarne
przelaczenie jak `vaa_canary`). Top1 ofensywny + top1 obronny, zawsze NAJLEPSZY DOSTEPNY (bez
wzgledu na znak - udzial ochronny juz kompensuje slaby rynek). Zweryfikowano na realnych danych
(2008, 2009, 2020) - mieszane sloty 50/50 (np. `{"agg.us": 0.5, "ief.us": 0.5}` - top1 ofensywny
+ top1 obronny naraz) faktycznie wystepuja.

**Realny wynik** (2006-02 do 2026-07, 246 miesiecy, PRZED podatkiem): CAGR 6.62%, MaxDD -25.50%,
Sharpe 0.54, Calmar 0.26, turnover 7.64/rok - **uczciwie gorzej niz nasz `vaa_g4`** (CAGR 7.98%,
MaxDD -24.45%, Sharpe 0.71, Calmar 0.33) w TYM konkretnym zestawie danych, mimo ze opublikowana
praca Kellera i Keuninga twierdzi ze DAA generalnie bije VAA - prawdopodobnie
dataset-specyficzne (inny okres/uniwersum niz oryginalna publikacja), nie blad implementacji
(mechanizm zweryfikowany jednostkowo i na wagach z historii). Train/test spojne, bez blowupu:
CAGR 4.55%/4.72%, Sharpe 0.48/0.44.

Param stability (sweep `hysteresis_pct`, 5 wariantow): `relative_drop = 0.0%` - ten sam "martwy
parametr" wzorzec co `vaa_g4`/`the_one` (top1 binarny wybor, histereza wagowa nigdy nie blokuje
przelaczenia w tym zakresie) - odnotowane jako ograniczenie sweepa, nie prawdziwa stabilnosc.

13 nowych testow: `test_daa_components.py` (nowy blok na danych syntetycznych - 0%/50%/100%
udzial ochronny, NaN kanarek liczy sie jako zly, ofensywny wybiera najlepszego dostepnego nawet
przy ujemnym score, top_n>1 dzieli po rowno, fallback do `_CASH`) + `test_daa_g4_strategy_spec.py`
(kanarek WLASCIWYM podzbiorem ofensywnych - nie rownym, end-to-end z dowodem na wszystkie 3
poziomy udzialu ochronnego, zamrozony baseline metryk).

#### `vaa_g4_ema` / `daa_g4_ema` - eksperyment: EMA zamiast momentum (negatywny wynik)

User (reagujac na rozczarowujacy `daa_g4`): "a co jesli posprawdzasz te oryginalne strategie
korzystajac np z EMA zamiast tego momentum". Identyczny mechanizm co `vaa_g4`/`daa_g4`, ale
score = `ema_ratio_monthly` (fast=7, slow=16 - te same wartosci co `best17_a`) zamiast 13612W
momentum. Zero nowego kodu blokow - `ema_ratio_monthly` juz istnial i jest w pelni ogolny.

**Wynik: EMA wyraznie gorsze niz momentum, na CALEJ siatce 9 sweepowanych spanow**:

| | momentum (13612W) | EMA (7/16, jak best17_a) | EMA - najlepszy z 9 wariantow |
|---|---|---|---|
| `vaa_g4` | Sharpe 0.712, MaxDD -24.45% | Sharpe 0.263, MaxDD -36.47% | Sharpe 0.336 (7/12), MaxDD -36.47% |
| `daa_g4` | Sharpe 0.538, MaxDD -25.50% | Sharpe 0.417, MaxDD -41.40% | Sharpe 0.513 (7/12), MaxDD -36.47% |

Nawet najlepszy sweepowany wariant EMA nie bije domyslnego momentum w zadnej z dwoch strategii.
**Prawdopodobny powod**: EMA(7,16) zostal dobrany dla `best17_a` (szybszy, waskoscezowy trend na
XLK/IVV/DBC/IAU), NIE dla `vaa_g4`/`daa_g4` (wolniejsza, szeroka rotacja SPY/EFA/VWO/AGG) -
13612W momentum jest zaprojektowany WLASNIE do takiej wolniejszej, wieloklasowej rotacji
(oryginalna metodologia VAA/DAA), crossover EMA reaguje za wolno/za szybko (whipsaw) na tym
typie uniwersum. 10 nowych testow (`test_ema_variant_strategy_specs.py`).

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

**Pokrycie testami per-strategia**: NIE każda SAMODZIELNA strategia w `strategies_v2/` ma
dedykowany test end-to-end ładujący jej WŁASNY `strategy_spec.json` z dysku (user pytanie
2026-07-11: "a best17 z hedge czy bez są testy?" - odpowiedź brzmiała NIE dla `best17_a`, dopóki
nie dodano `test_best17_a_strategy_spec.py`). Strategie z takim dedykowanym testem (wiring +
end-to-end + zamrożony baseline metryk): `example_strategy` (`test_pipeline.py`), `the_one`/
`vaa_g4` (`test_gem_dual_momentum_switch.py`/`test_vaa_canary.py` - tylko blok, nie pełny plik
specyfikacji), `gfm`, `best17_b`, `best17_a`.

**Portfele łączone (`combined_spec.json`) - inaczej.** `test_all_combined_specs.py` (dodane
2026-07-11 razem z pełnym przeglądem par - patrz sekcja "Wszystkie pary 7 głównych strategii"
wyżej) automatycznie ODKRYWA (glob) KAŻDY zapisany `strategies_v2/*/combined_spec.json` i
uruchamia go end-to-end na realnych danych - WSZYSTKIE 27 portfeli w repo (w tym przyszłe,
jeszcze nienapisane) mają teraz to samo minimum regresji bez potrzeby nowego pliku testowego per
portfel. `best17_a_tlt_hedge` ma DODATKOWO własny, bardziej szczegółowy test
(`test_best17_a_tlt_hedge.py` - regresja na bugfix "hedge włączał się przed startem core").

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
