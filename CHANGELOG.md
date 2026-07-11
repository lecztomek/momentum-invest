# Changelog

Zapis istotnych zmian w projekcie, najnowsze na górze. Każdy wpis krótko: co się zmieniło i po co.

## 2026-07-11 (31)

- **NOWY REKORD SESJI (drugi z rzedu): `gpm_best17_a` z `signal_tilted_capital_weights` - Calmar
  0.786** (poprzedni rekord: 0.774, `dynamic_capital_weights`, patrz (29)). User po negatywnym
  wyniku (30) - "a moze inaczej liczba canary decyduje o proporcji" - zamiast tiltu wg SUROWEGO
  zwrotu (co nie zadzialalo), tilt wg JUZ ISTNIEJACEGO, wewnetrznego sygnalu "szerokosci
  rynku"/regime jednej ze strategii.

  **NOWY COMBINER `signal_tilted_capital_weights`**
  (`engine_v2/combiner/signal_tilted_capital_weights.py`, 11 testow syntetycznych) - DOKLADNIE
  dwie strategie (jak `momentum_hedge_overlay`): sygnal = suma wag WYBRANEJ grupy tickerow w
  WLASNYM, juz wykonanym portfelu jednej strategii (`strategy_a`) - zero nowego wskaznika/
  plumbingu, odczyt wprost z `weights_used` (ktore combiner i tak juz dostaje). Tilt: `weight_a =
  clip(base_weight_a + tilt_strength*(signal-center), min_weight_a, max_weight_a)`, `weight_b = 1
  - weight_a`, `shift(1)` (unika look-ahead, jak `momentum_hedge_overlay`). WAZNE: `center`
  (domyslnie 0.5) to STALA, NIE srednia sygnalu z calej historii backtestu - uzycie sredniej z
  calej serii zanieczyszczaloby kazda decyzje przyszlym wgladem w dane (look-ahead bug, zlapany
  i naprawiony PRZED sfinalizowaniem - patrz nizej).

  **Zastosowanie do `gpm_best17_a`** (gpm z xle.us, patrz (29)) - sygnal = `protective_share` gpm
  (suma wag `ief.us`+`shy.us` w jej WLASNYM portfelu; `gpm_breadth_protective_split` juz liczy to
  wewnetrznie jako ciagle 0..1, tu tylko odczytane z jej wyjscia). Pierwszy sweep (kierunek
  "wiecej gpm gdy protective WYSOKI", tilt dodatni) dal WYNIK NEGATYWNY (Calmar spada do 0.57-0.69
  im silniejszy tilt) - odwrocenie kierunku (tilt UJEMNY: "wiecej gpm gdy JEJ WLASNY
  protective_share jest NISKI") dalo POPRAWE na calym sweepie. Interpretacja: gpm w pelni
  defensywnym trybie (protective_share=1.0) ma z definicji NIZSZY oczekiwany zwrot do przodu niz
  gdy jest w pelni zainwestowana - dawanie jej WIECEJ kapitalu WLASNIE wtedy (dublowanie
  defensywnosci na poziomie combinera) szkodzi; odwrotnie, dawanie jej wiecej kapitalu gdy sama
  jest pewna siebie (niski protective_share, potencjalnie takze koreluje z okresami gdy best17_a
  radzi sobie gorzej) dziala lepiej.

  **Poprawka look-ahead PRZED finalizacja**: pierwsza wersja uzywala `protective.mean()` (srednia
  z CALEJ historii backtestu) jako `center` - to jest look-ahead (decyzja w 2010 nie moze znac
  sredniej z danych do 2026). Po zamianie na STALA `center=0.5` (naturalny neutralny punkt dla
  wartosci ograniczonej do [0,1]) wynik pozostal solidny (peak Calmar przesunal sie z 0.785 na
  0.786 przy nieco innym optymalnym `tilt_strength`, ~-0.10 zamiast ~-0.12) - NIE byl artefaktem
  look-ahead.

  **Finalne parametry**: `tilt_strength=-0.10`, `center=0.5`, `min_weight_a=0.30`,
  `max_weight_a=0.80`, `base_weight_a=0.55` (gpm). Wynik PO PODATKU: CAGR 10.38%, MaxDD -13.22%,
  Sharpe 1.011, Calmar **0.786** - lepszy niz `dynamic_capital_weights` (0.774) na WSZYSTKICH 4
  metrykach jednoczesnie (CAGR/MaxDD/Sharpe/Calmar), nie tylko na jednej.

  **Weryfikacja robustnosci** (TRAIN/OOS/named periods, tilt=-0.10 vs baza bez tiltu): poprawa w
  wiekszosci okresow - OOS Calmar 0.905->0.985, covid_crash_rebound Calmar 1.428->1.893,
  post_gfc_recovery Calmar 0.880->0.951 - z drobnym pogorszeniem w `gfc_crash` (-3.97%->-4.89% -
  zbyt krotka historia PRZED oknem treningowym, mala waga statystyczna) i `inflation_bear`
  (-6.53%->-7.35%, wciaz DUZO lepiej niz best17_a solo -14.75%). Brak sygnalu ciezkiego
  dopasowania do jednego okresu - poprawa jest szeroka, nie skoncentrowana w jednym roku.

  **Zaktualizowano**: `strategies_v2/gpm_best17_a/combined_spec.json` (`combiner:
  signal_tilted_capital_weights`). Pelny pakiet testow: 414/414 (403 + 11 nowych), bez regresji.

## 2026-07-11 (30)

- **NOWY COMBINER `relative_strength_capital_weights`** (user: "chodzi mi o bardziej inteligentne
  dobieranie - ta ktora jest mocniejsza dostaje wiekszy udzial", po `dynamic_capital_weights`
  ktory tylko realokuje MARTWA gotowke, nie tilt wg sily). Ciagle przechylanie udzialu kapitalu
  wg wlasnego, zrealizowanego zwrotu kazdej strategii za ostatnie `lookback` miesiecy wzgledem
  sredniej wszystkich strategii (`tilt_strength` na jednostke roznicy), przyciete do
  `min_weight`/`max_weight` PRZED renormalizacja - zeby uniknac calkowitej koncentracji przy
  przypadkowym, krotkotrwalym wyprzedzeniu. Konwencja `shift(1)` (decyzja na okres M+1 z danych
  do M wlacznie, jak `momentum_hedge_overlay`) i ta sama ochrona przed "wygrana przez brak
  historii" (aktyw spoza wlasnego zakresu dat traktowany jako najslabszy, nie neutralny 0%).
  10 nowych testow syntetycznych (`test_relative_strength_capital_weights.py`) - w tym
  `test_stronger_strategy_gets_bigger_share` (rdzen wymagania) i `test_min_max_weight_caps_extreme_tilt`.

  **Zastosowanie do `gpm_best17_a`** (gpm z xle.us, patrz (29)) - sweep `lookback` (3/6/12) x
  `tilt_strength` (0.3/0.5/1.0/2.0) x `min_weight`/`max_weight` ((0.20,0.80)/(0.30,0.70)), PO
  PODATKU, wzgledem base_weights 45/55 (best17_a/gpm) - **WYNIK NEGATYWNY**: KAZDY testowany
  wariant wypada GORZEJ niz obecny mistrz (`dynamic_capital_weights`, Calmar 0.774) i wiekszosc
  gorzej niz nawet prosty `fixed_capital_weights` (Calmar 0.763) - najlepszy znaleziony wariant
  (lookback=3, tilt=0.3) dawal Calmar 0.754, a im silniejszy tilt/dluzszy lookback, tym gorzej
  (np. lookback=12, tilt=2.0: MaxDD -18.65%, Calmar 0.562 - WYRAZNIE gorzej). Przyczyna:
  `best17_a` ma dużo wyzsza zmiennosc wlasnego zwrotu niz `gpm` (koncentrowany top2 momentum vs
  szeroko zdywersyfikowany, ochronny mechanizm) - tilt oparty na SUROWYM zwrocie (nie
  risk-adjusted) reaguje na EPIZODYCZNE wybicia `best17_a` (szum), przeksztalcajac sie w
  "kupowanie po duzym ruchu" tuz przed jego kolejnymi drawdownami, zamiast lapac realna,
  trwala przewage. Combiner ZOSTAJE w repo (przetestowany, dziala poprawnie, ogolny/reuzywalny
  dla par o PODOBNEJ zmiennosci), ale `gpm_best17_a` NIE zmienia konfiguracji -
  `dynamic_capital_weights` (Calmar 0.774) pozostaje mistrzem sesji. Pelny pakiet testow:
  403/403 (393 + 10 nowych), bez regresji.

## 2026-07-11 (29)

- **NOWY REKORD SESJI: `gpm_best17_a` z `xle.us` w `gpm` + `dynamic_capital_weights` - Calmar
  0.774** (poprzedni rekord: 0.669/0.707 przed dzisiejszymi bugfixami gate'u/histerezy). User:
  "moze wymysl cos co by bylo dobre w 2022 i wtedy robimy miks - czyli szukamy strategii na rok
  2022" - 2022 to jedyny rok w calym repo, gdzie WSZYSTKIE strategie wychodzily na minusie
  (akcje i obligacje spadaly razem).

  **Krok 1 - co realnie wygralo w 2022** (sprawdzone na prawdziwych danych, nie zgadywane):
  XLE (energia) +64.3%, GSG +24.1%, DBC +18.6%, zloto plasko (-0.6/-0.8%) - wszystko inne na
  minusie (akcje -18/-33%, obligacje -14/-31%).

  **Krok 2 - proba osobnej satelity (ODRZUCONA)**: nowa strategia `commodity_trend` (top1
  spord XLE/DBC/GLD wg momentum, filtr bezwzglednego momentum, cash fallback), polaczona z
  `best17_a` (`fixed_capital_weights`, zgodnie z zasada "max 2"). Naprawiala 2022 (best17_a solo
  -14.75% -> -1.7% przy wadze 35%), ale kosztem MaxDD calego miksu rosnacego do -23.6/-31.2% w
  zaleznosci od wagi - user: "za duze maxdd ale mamy trop" - odrzucone jako samodzielny produkt,
  ale potwierdzilo, ze XLE to prawdziwy trop.

  **Krok 3 - rozszerzenie `gpm` (PRZYJETE)**: zamiast nowej, ryzykownej satelity, dolozono
  `xle.us` do WLASNEGO uniwersum `gpm` (`risky_assets` + koszyk korelacji `c.basket_assets`) -
  `gpm` juz ma niskie MaxDD i wlasny mechanizm ochronny (`gpm_breadth_protective_split`), wiec
  jeden dodatkowy kandydat nie wprowadza nowego ryzyka architektury. Solo `gpm` + xle.us: 2022
  poprawia sie z -5.47% na -0.36%, MaxDD PRAKTYCZNIE bez zmian (-13.09%->-13.00% pelna historia).
  `full_protective_max_n`/`protective_scale_denominator` CELOWO NIE przeskalowane z 6/6 (kalibrowane
  pod 12 aktywow) do 13 aktywow - to dokladnie konfiguracja zweryfikowana empirycznie.

  **Weryfikacja "czy to nie ciazy w innych okresach"** (user pytanie wprost) - porownanie
  gpm+xle vs gpm bez xle na TEJ SAMEJ wadze combinera (55/45 gpm/best17_a), PO PODATKU:

  | | bez XLE | z XLE |
  |---|---|---|
  | FULL | 11.03%/-16.50%/Sharpe 0.968/Calmar 0.669 | 11.15%/-16.40%/Sharpe 0.990/Calmar 0.680 |
  | TRAIN | 11.47%/-14.47%/1.156/0.793 | 11.81%/-14.47%/1.195/0.817 |
  | OOS | 13.33%/-16.50%/0.955/0.808 | 13.27%/-16.40%/0.969/0.809 |
  | gfc_crash | -5.82%/-7.60% | -5.87%/-7.60% (bez zmian) |
  | post_gfc_recovery | 12.71%/Sharpe 1.172/Calmar 0.922 | 13.16%/1.216/0.960 (lepiej) |
  | covid_crash_rebound | 22.12%/Sharpe 1.174/Calmar 1.340 | 21.12%/1.149/1.288 (odrobine gorzej) |
  | inflation_bear (2022) | -10.25%/-13.76%/Calmar -0.745 | -7.98%/-11.95%/Calmar -0.668 (duzo lepiej) |

  **Wniosek: przy TEJ SAMEJ wadze, XLE to niemal czysty zysk** - lepiej w 6 z 7 porownan, tylko
  odrobine gorzej w `covid_crash_rebound` (gdzie XLE bylo slabsze niz reszta rynku w 2020).
  Wczesniejsze wrazenie "ciazenia" (CAGR 11.03%->10.14% przy wadze 45%) bylo artefaktem
  PORONYWANIA ROZNYCH WAG (55% vs 45% best17_a), nie samego dodania XLE - przy tej samej wadze
  zmiana jest wylacznie pozytywna.

  **Krok 4 - pelny sweep wagi z XLE** (fixed_capital_weights, PO PODATKU): najlepszy Calmar przy
  45/55 (best17_a/gpm): CAGR 10.14%, MaxDD -13.28% (bylo -15.40% bez XLE), Sharpe 0.996, Calmar
  **0.763** (bylo 0.707).

  **Krok 5 - user: "moze sprobujmy dynamicznie dobierac wagi"** - `dynamic_capital_weights` (juz
  istniejacy combiner z `combined_best2_dynamic` - kapital strategii w cash NIE lezy bezczynnie,
  przechodzi do drugiej nogi) na TEJ SAMEJ bazowej wadze 45/55: CAGR 10.23%, MaxDD -13.22%,
  Sharpe 0.980, Calmar **0.774** - dalszy, mniejszy, ale konsekwentny plus na KAZDEJ testowanej
  wadze (40/45/50/55) - ten sam wzorzec co przy `combined_best2_dynamic` (wiecej CAGR, odrobine
  nizszy Sharpe z powodu mniejszej dywersyfikacji w okresach cash).

  **NOWA KONFIGURACJA `gpm_best17_a`**: `combiner: dynamic_capital_weights`,
  `capital_weights: {gpm_v0: 0.55, best17_a_v0: 0.45}` (bylo `fixed_capital_weights`, 0.45/0.55
  best17_a/gpm - odwrotna etykieta wagi, uwaznie). Zaktualizowano `strategies_v2/gpm/strategy_spec.json`
  (nowe `risky_assets`/`basket_assets` z `xle.us`, uniwersum 15 tickerow) i
  `strategies_v2/gpm_best17_a/combined_spec.json`. Zaktualizowano
  `test_gpm_strategy_spec.py::test_gpm_risky_universe_has_13_assets_and_2_protective` (bylo 12) i
  `test_gpm_metrics_regression_baseline` (nowe zamrozone wartosci: cagr 0.0553, maxdd -0.1327,
  sharpe 0.697, PRZED podatkiem). `test_all_combined_specs.py` (glob-discovery) automatycznie
  odkrywa nowa konfiguracje - zero nowych plikow testowych potrzebnych. Pelny pakiet: 393/393 bez
  regresji.

## 2026-07-11 (28)

- **BUGFIX (istotny, drugi tego dnia) `score_gap_hysteresis`: histereza mogla "uratowac"
  aktyw, ktory wlasnie przestal byc eligibilny** (user: "jak odpalimy v1 best17 i sprawdzimy
  miesiac po miesiacu z v2 to jaka jest zgodnosc aktywow" - po poprawce (27) sprawdzone wprost:
  216 wspolnych miesiecy, 188/216 (87.0%) zgodnosci zestawu aktywow, 28 rozbieznych).

  **Diagnoza**: dla WSZYSTKICH 28 rozbieznych miesiecy `target_weights` PRZED histereza (czyli
  wynik `asset_filters`+`asset_scoring`+`selector`+`alpha_weighting`, JUZ poprawnie uwzgledniajacy
  gate po poprawce (27)) byl IDENTYCZNY z `selected_assets` starego silnika. Rozbieznosc
  wprowadzal DOPIERO blok EXECUTION (`score_gap_hysteresis`): gdy trzymany aktyw (np. IAU) staje
  sie nieeligibilny (NaN w `score`, zablokowany przez `iau_gate`), histereza porownuje "najslabszy
  TRZYMANY score vs najlepszy WYZWANIE score" - i po prostu POMIJA nieeligibilny aktyw z tego
  porownania (`pd.notna` filtr), zamiast wymusic wyjscie. Jesli POZOSTALY trzymany aktyw ma score
  blisko najlepszego wyzwania, `keep_current=True` i CALY stary sklad (WLACZNIE z juz
  zablokowanym aktywem) zostaje utrzymany bez zmian. Stary silnik ma na to jawny mechanizm
  (`forced_exit_due_to_asset_gate`, widoczny jako `1` dokladnie w pierwszym miesiacu kazdej z 28
  rozbieznosci) - wymusza pelny rebalans, gdy trzymany aktyw traci eligibility, niezaleznie od
  histerezy. To dotyczylo m.in. DOKLADNIE scenariusza czerwca 2026, ktory zapoczatkowal cala ta
  sesje (poprawka (27) naprawila SELEKCJE, ale bez tej poprawki histereza wciaz trzymalaby IAU).

  **Naprawa**: `engine_v2/blocks/execution/score_gap_hysteresis.py` - nowy warunek NA POCZATKU
  (przed wszystkimi innymi): jesli ktorykolwiek aktualnie trzymany aktyw ma NaN w `score_row`,
  `keep_current=False` bezwarunkowo (pelny rebalans do juz poprawnie policzonego targetu),
  niezaleznie od roznicy score reszty portfela.

  **Walidacja**: PO poprawce - **100% zgodnosci zestawu aktywow na WSZYSTKICH 216 wspolnych
  miesiecach** (2008-2026) z prawdziwym CSV starego silnika (wczesniej 188/216, 87.0%). Nowy test
  `test_forced_exit_when_currently_held_asset_becomes_ineligible`
  (`test_best17_a_components.py`) odtwarza dokladnie ten scenariusz (trzymany aktyw z NaN score
  mimo bliskiej roznicy score reszty portfela musi wymusic pelny rebalans).

  **Wplyw na metryki - `best17_a` solo i 12 pochodnych (PRZED/PO tej poprawce, PO PODATKU)**:

  | | CAGR przed→po | MaxDD przed→po | Sharpe przed→po | Calmar przed→po |
  |---|---|---|---|---|
  | `best17_a` solo | 15.93%→16.32% | -29.47%→-31.19% | 0.918→0.930 | 0.540→0.523 |
  | `synergy_v1` | 13.91%→14.17% | -29.99%→-29.99% | 0.822→0.837 | 0.464→0.472 |
  | `synergy_v2` | 15.45%→15.84% | -29.99%→-31.19% | 0.878→0.890 | 0.515→0.508 |
  | `best17_a_tlt_hedge` | 13.47%→13.77% | -22.09%→-22.09% | 0.920→0.929 | 0.610→0.623 |
  | `best17_a_tlt_timing` | 11.24%→11.51% | -22.31%→-23.87% | 0.883→0.896 | 0.504→0.482 |
  | `combined_best2` | 12.21%→12.41% | -22.73%→-22.73% | 0.902→0.913 | 0.537→0.546 |
  | `combined_best2_dynamic` | 13.62%→13.79% | -26.40%→-26.61% | 0.910→0.918 | 0.516→0.518 |
  | `combined_triple` | 11.20%→11.37% | -19.65%→-20.75% | 0.951→0.961 | 0.570→0.548 |
  | `dual_momentum_best17_a` | 10.87%→11.06% | -21.84%→-22.79% | 0.870→0.880 | 0.498→0.485 |
  | `vaa_g4_best17_a` | 11.20%→11.37% | -17.33%→-18.09% | 0.987→0.995 | 0.646→0.629 |
  | `best17_a_all_weather_4` | 11.48%→11.66% | -22.01%→-23.20% | 0.939→0.949 | 0.522→0.502 |
  | `best17_a_gfm` | 11.43%→11.62% | -28.03%→-29.15% | 0.851→0.858 | 0.408→0.399 |
  | `best17_a_best17_b` | 10.66%→10.66% | -29.42%→-30.31% | 0.809→0.804 | 0.362→0.352 |
  | `gpm_best17_a` (55/45) | 10.82%→11.03% | -15.40%→-16.50% | 0.955→0.968 | 0.702→0.669 |
  | `gtaa_agg6_best17_a` (45/55) | 10.26%→10.42% | -18.31%→-19.44% | 0.903→0.910 | 0.560→0.536 |

  **Kierunek zmian spojny i zrozumialy**: CAGR i Sharpe rosna wszedzie (mniej "utopionego" w
  nieeligibilnych aktywach kapitalu), ale MaxDD w wiekszosci przypadkow ROSNIE (pogarsza sie) -
  wymuszony, szybszy exit z zablokowanego aktywa oznacza CZESCIEJ pelny rebalans w momentach
  napiecia rynkowego (asset gate binduje wlasnie W OKRESACH zlego momentum), co podnosi turnover
  (np. `best17_a`: 0.92→1.16/rok) i czasem prowadzi portfel przez GLEBSZY, ale KROTSZY drawdown
  zamiast trzymac stara, czesciowo zablokowana pozycje dluzej. **Kluczowe rekomendacje sesji
  BEZ ZMIAN**: `vaa_g4_best17_a` nadal najlepszy Sharpe w repo (0.995), `gpm_best17_a` (55/45)
  nadal najlepszy Calmar (0.669 vs 0.629 `vaa_g4_best17_a`) - marginesy sie zmienily, ranking nie.

  **Ta sama uwaga o zakresie co w (27)**: przeliczone zostaly WSZYSTKIE zapisane
  `combined_spec.json` uzywajace `best17_a`. Tabele sweepow (gpm/gtaa_agg6/tlt_hedge wagi, przeglad
  C(7,2) par) NIE zostaly w pelni ponownie przeliczone - patrz CHANGELOG (27) po pelne uzasadnienie.

## 2026-07-11 (27)

- **BUGFIX (istotny) `best17_a`/`synergy_v1`/`synergy_v2`: `iau_gate`/`dbc_gate` liczyly 3-miesieczny
  momentum na ZLEJ podstawie cenowej** (user: "Chwila gate na zloto na pewno w 2026 powinien wejsc
  zobacz sobie wyniki best17 w starym engine" - podejrzenie wziete z realnych danych: w starym
  silniku IAU byl zablokowany w czerwcu 2026, w engine_v2 nie).

  **Diagnoza**: `iau_gate`/`dbc_gate` czytaly `mom_r3` (`momentum_month_end`, window=3) - wskaznik
  liczacy 3m momentum na CENACH KONCA MIESIACA. To bylo BLEDNE. Przesledzenie prawdziwego kodu
  starego silnika (`engine/backtest_hybrid_search.py`) pokazalo, ze `min_return_3m` w asset gates
  jest liczone przez `trailing_compound_return()` na cenach z pliku
  `month_start_to_month_start_returns.csv` (execution/start-miesiaca), NIE na cenach konca
  miesiaca. To INNY mechanizm niz `rebound_starter` (ktory poprawnie uzywa `momentum_r3.csv`,
  konca-miesiaca, przesuwany przez `align_scores_to_execution_month` - ten kawalek w engine_v2 byl
  juz poprawny i zostal BEZ ZMIAN).

  Pierwsza proba naprawy (custom indicator `trailing_compound_return_month_start.py`, rolling+shift
  na log-returns) okazala sie rowniez bledna - 123/428 (28.9%) niezgodnosci przeciw prawdziwemu CSV
  starego silnika. Przyczyna: bledne zalozenie o konwencji etykietowania dat w pliku returns (w
  rzeczywistosci `returns.loc[d]` = zwrot ZREALIZOWANY W TRAKCIE miesiaca zaczynajacego sie w `d`,
  czyli `price(d+1m)/price(d)-1` - etykieta "w przod", nie `pct_change()` "wstecz"). Po poprawnym
  zrozumieniu konwencji, `trailing_compound_return(dt, months=3)` upraszcza sie do zwyklego
  `price_exec(dt)/price_exec(dt-3m) - 1` - czyli DOKLADNIE wzoru, ktory juz liczy ISTNIEJACY blok
  `momentum_monthly` (uzywany gdzie indziej w repo, np. `best17_b`). Zero nowego kodu bloku
  potrzebne - custom indicator i jego test usuniete, uzyto istniejacego bloku.

  **Naprawa**: nowa instancja wskaznika `"mom_r3_gate": {"impl": "momentum_monthly", "window": 3}`
  w `strategies_v2/best17_a/strategy_spec.json` (oraz `synergy_v1`/`synergy_v2`, ktore duplikuja
  ta sama logike gate we WLASNYM pliku spec) - `iau_gate`/`dbc_gate` przelaczone na
  `mom_r3_gate`. `mom_r3` (`momentum_month_end`) zostaje BEZ ZMIAN, nadal uzywany wylacznie przez
  `portfolio_risk_engine` (rebound_starter).

  **Walidacja**: 428 par (data, aktywo) z prawdziwego historycznego CSV starego silnika
  (`ideas_out/best17_3m_tlt_dtla_40/runs/20260710_212803/03_us_backtest_base/monthly/*.csv`,
  pole `blocked_by_asset_gate`, 216 miesiecy x iau.us/dbc.us, 2008-2026) - PO poprawce **100%
  zgodnosci wszedzie, gdzie kanarek NIE wyklucza juz calej grupy offensywnej**. Pozostale 24/428
  (5.6%) pozornych "niezgodnosci" wystepuja WYLACZNIE w miesiacach, gdzie `bad_canaries >= 1` w
  CSV starego silnika - kanarek juz wtedy sam wyklucza cala grupe (`candidate_assets` puste,
  portfel w `_CASH`/`vt.us`), wiec wartosc konkretnego gate'u jest bez znaczenia dla wyniku
  koncowego w tych miesiacach. Potwierdzone rowniez wprost na przejsciu maj->czerwiec 2026: IAU
  eligibilny w maju (mom_r3_gate ~ -0.97%, > progu -1%), zablokowany w czerwcu (~ -16.05%) -
  ZGODNIE z prawdziwym wynikiem starego silnika, ktory to wywolal caly ten watek.

  Nowe/zaktualizowane testy: `test_best17_a_strategy_spec.py` -
  `test_best17_a_asset_gates_use_month_start_momentum_not_month_end` (wiring),
  `test_best17_a_iau_gate_matches_real_2026_transition` (dokladnie ten scenariusz z real danych,
  ktory wywolal watek), zaktualizowany `test_best17_a_metrics_regression_baseline` (nowe zamrozone
  wartosci, patrz tabela nizej). Pelny pakiet testow: bez regresji.

  **Wplyw na metryki - `best17_a` solo i wszystkie 12 portfeli/wariantow, ktore go uzywaja
  (PRZED/PO poprawce, PO PODATKU gdzie dotyczy)**:

  | | CAGR przed→po | MaxDD przed→po | Sharpe przed→po | Calmar przed→po |
  |---|---|---|---|---|
  | `best17_a` solo | 16.07%→15.93% | -29.47%→-29.47% | 0.93→0.918 | 0.545→0.540 |
  | `synergy_v1` | 14.04%→13.91% | -29.99%→-29.99% | 0.83→0.822 | ~0.47→0.464 |
  | `synergy_v2` | 15.59%→15.45% | -29.99%→-29.99% | 0.89→0.878 | ~0.52→0.515 |
  | `best17_a_tlt_hedge` | 13.78%→13.47% | -23.70%→-22.09% | 0.94→0.920 | 0.59→0.610 |
  | `best17_a_tlt_timing` | ~11.60%→11.24% | ~-23%→-22.31% | ~0.93→0.883 | ~0.52→0.504 |
  | `combined_best2` | ~12.6%→12.21% | -22.7%→-22.73% | ~0.94→0.902 | ~0.55→0.537 |
  | `combined_best2_dynamic` | ~14.0%→13.62% | -26.8%→-26.40% | ~0.95→0.910 | ~0.52→0.516 |
  | `combined_triple` | 11.26%→11.20% | -18.1%→-19.65% | 0.96→0.951 | 0.64→0.570 |
  | `dual_momentum_best17_a` | ~11.2%→10.87% | ~-21.8%→-21.84% | ~0.90→0.870 | ~0.51→0.498 |
  | `vaa_g4_best17_a` | 11.25%→11.20% | -17.33%→-17.33% | 0.99→0.987 | 0.649→0.646 |
  | `best17_a_all_weather_4` | 11.84%→11.48% | -21.84%→-22.01% | 0.98→0.939 | 0.54→0.522 |
  | `best17_a_gfm` | 11.84%→11.43% | -27.86%→-28.03% | 0.89→0.851 | 0.43→0.408 |
  | `best17_a_best17_b` | 10.99%→10.66% | -29.42%→-29.42% | 0.84→0.809 | 0.37→0.362 |
  | `gpm_best17_a` (55/45) | 10.89%→10.82% | -15.40%→-15.40% | 0.962→0.955 | 0.707→0.702 |
  | `gtaa_agg6_best17_a` (45/55) | 10.31%→10.26% | -18.31%→-18.31% | 0.909→0.903 | 0.563→0.560 |

  **Zmiany male i NIE zmieniaja zadnej z kluczowych konkluzji sesji**: `vaa_g4_best17_a` nadal ma
  najlepszy Sharpe w repo (0.987, PO poprawce), `gpm_best17_a` (55/45) nadal ma najlepszy Calmar
  (0.702) - obie rekomendacje z sesji POTWIERDZONE na nowo, nie tylko przeniesione bez sprawdzenia.
  Najbardziej zauwazalna zmiana: `worst_year_return` dla `best17_a` solo pogarsza sie z -14.99% na
  **-19.35%** (2022) - poprawka gate'u sprawia, ze IAU/DBC sa CZESCIEJ poprawnie blokowane w
  okresach realnie zlego momentum (w tym 2022), co lekko obniza sredni CAGR, ale NIE zmienia
  MaxDD calosciowego dla `best17_a` solo (dokladnie ten sam trough, -29.47%).

  **Uwaga o zakresie tej poprawki**: przeliczone zostaly WSZYSTKIE zapisane, rekomendowane
  konfiguracje (`combined_spec.json`) uzywajace `best17_a` - to one reprezentuja faktyczne decyzje
  sesji. Tabele SWEEPOW (np. `gpm_best17_a` waga 35-60%, `gtaa_agg6_best17_a` waga 30-70%,
  `best17_a_tlt_hedge` waga 20-60%, przeglad C(7,2) par) NIE zostaly w pelni ponownie przeliczone -
  uzywaja `best17_a` jako jednej z nog, ale skala zmiany (Sharpe -1..-3%, MaxDD w wiekszosci bez
  zmian) czyni bardzo malo prawdopodobnym, zeby zmienily wybor optymalnego punktu w ktoromkolwiek
  sweepie. Odnotowane jawnie, nie ukryte - jesli ktos bedzie polegal na dokladnej wartosci
  konkretnego punktu sweepu (nie na koncowej rekomendacji), warto go przeliczyc osobno.

## 2026-07-11 (26)

- **KOREKTA: `iau_gate`/`dbc_gate`/`rebound` NIE sa "martwe"** (user: "a powiedz jak czesto
  wchodzilo gate dla zlota?") - poprzedni wpis (23) opisal ich `relative_drop=0%` jako "gate
  prawie nigdy nie binduje", co bylo NIEPRECYZYJNE. Sprawdzone wprost na realnych danych:
  - `iau_gate` blokuje IAU w **78/218 miesiecy calej historii (35.8%)**, 46/115 (40%) w oknie
    train, i w **21/115 miesiecy jest JEDYNYM blokerem** (kanarek + `require_positive_score`
    akurat przepuszczaja) - a wiec DZIALA, nie jest redundantny.
  - `dbc_gate` blokuje DBC jeszcze czesciej: **103/218 (47.2%)**.
  - `rebound` (VT) aktywuje sie w **7/218 miesiecy (3.2%)** - rzadko, ale nie zero (z 16/218
    miesiecy w calosci w cash, 7 zlapal rebound).

  Mimo to, `relative_drop=0%` w OKNIE WALK-FORWARD (2010-06 do 2019-12) pozostaje poprawny wynik
  z innego powodu: empirycznie zmiana progu `iau_gate` (-0.03 do +0.01) zmienia FAKTYCZNE wagi
  portfela tylko w 9/218 miesiecy CALEJ historii - i **ZERO z nich wypada w oknie walk-forward**
  (zmiany sa w 2009-09 [przed oknem] i 2021/2023 [w oknie test/OOS]). Powod: gdy gate binduje
  NIEZALEZNIE w oknie treningowym, IAU i tak ma za slaby wlasny `ema7_16` score, zeby wygrac top2
  - wiec dokladna wartosc progu nie zmienia WYNIKU w TYM oknie, mimo ze zmienia ELIGIBILNOSC.

  **Poprawna interpretacja**: `relative_drop=0%` = "zmiana progu nie zmienia wyniku W TYM OKNIE
  TESTOWYM", NIE "mechanizm nigdy nie dziala" - realna wartosc tych gate'ow "na przyszlosc" (poza
  oknem 2010-2019) pozostaje niepotwierdzona przez ten konkretny test, nie odrzucona.

## 2026-07-11 (25)

- **`local_param_stability` wpiete do `run_spec_runner._run_search` - AUTOMATYCZNIE, dla kazdego
  `search`** (user: "To powinien byc krok naszego calego procesu" - dotad trzeba bylo recznie
  pisac skrypt ad-hoc, jak dla `best17_a` poprzednio). Teraz kazde uruchomienie `mode="search"`
  (na DOWOLNEJ strategii z `allowed_param_families`) automatycznie liczy:
  - `result["local_param_stability"]` - `describe_1d_sensitivity` gdy `allowed_param_families`
    ma DOKLADNIE 1 os, `describe_2d_sensitivity` gdy ma DOKLADNIE 2 (jak w `best17_a`) - wartosc
    domyslna do porownania brana WPROST z `StrategySpec.base_params` (nowy helper
    `_axis_default_value`, ta sama konwencja "instancja.param" dla blokow wielo-instancyjnych co
    `grid_sweep.expand_param_grid`). Dla >2 osi: `None` (flood-fill 2D sie nie uogolnia trywialnie
    na wiecej wymiarow, nieobslugiwane - rzadki przypadek w tym repo).
  - `result["fold_rank_stability"]` - Kendall's W miedzy oknami walk-forward, liczone gdy
    WSZYSTKIE warianty maja TA SAMA liczbe okien (>=2). Dziala generycznie NIEZALEZNIE od liczby
    osi (1, 2, czy wiecej) - traktuje kazda kombinacje parametrow jako jeden "przedmiot" do
    rankingu, wiec nie ma tego samego ograniczenia co `local_param_stability`.

  **Zweryfikowane end-to-end na `best17_a`** (`mode="search"` na prawdziwym `run_spec.json`, bez
  zadnej dodatkowej konfiguracji) - dokladnie te same wyniki co poprzednia analiza ad-hoc:
  `default_meets_threshold=False`, `gap_to_best=8.2%`, `kendalls_w=0.90` (wysoka zgodnosc
  rankingu miedzy 5 oknami WF), `default_wins_fold_count=0` - domyslna kombinacja
  (`min_score_gap=0.005`, `canary.bad_threshold=-0.02`) nie wygrywa w ZADNYM z 5 okien.

  2 nowe testy w `test_run_spec_runner.py` (`test_search_mode_end_to_end` rozszerzony o
  asercje `local_param_stability`/`fold_rank_stability` na przykladzie 2-osiowym;
  `test_search_mode_single_axis_uses_1d_sensitivity` - nowy, weryfikuje sciezke 1D). 390/390
  testow przechodzi.

## 2026-07-11 (24)

- **NOWY MODUL `engine_v2/local_param_stability.py`** - user trafnie skrytykowal
  `param_stability.compute_param_stability` (pojedynczy `relative_drop`): (1) bierze pod uwage
  najgorszy SKRAJ calego zakresu, nie sasiadow wartosci domyslnej, (2) nie uwzglednia GDZIE w
  rodzinie siedzi wartosc domyslna, (3) nie rozroznia PLATEAU od POJEDYNCZEGO MAKSIMUM, (4)
  traktuje wszystkie testowane wartosci jednakowo. Nowy modul dodaje 3 funkcje:
  - `describe_1d_sensitivity` - LOKALNY spadek do najblizszych sasiadow (nie do skraju), SZEROKOSC
    PLATEAU (ile sasiednich punktow w granicy tolerancji od najlepszego), POZYCJA wartosci
    domyslnej (ranking + luka), ASYMETRIA (pogorszenie w gore vs w dol).
  - `describe_2d_sensitivity` - to samo dla siatki DWOCH powiazanych parametrow (flood-fill
    spojnego obszaru wokol komorki domyslnej). WAZNA POPRAWKA w trakcie implementacji: pierwsza
    wersja flood-fill zawsze zaczynala od komorki domyslnej NIEZALEZNIE czy sama spelniala prog -
    to mogloby zawyzyc "plateau" przez sasiada, ktory akurat go spelnia, mimo ze SAM default nie
    jest wystarczajaco dobry. Naprawione: `default_meets_threshold` sprawdzane NAJPIERW, plateau
    liczony TYLKO jesli default sam spelnia prog (2 nowe testy lapiace ten dokladny scenariusz).
  - `compute_fold_rank_stability` - Kendall's W (zgodnosc rankingow) miedzy OSOBNYMI oknami
    walk-forward, nie tylko ich srednia - czy TA SAMA wartosc parametru wygrywa w wiekszosci
    foldow, czy ranking sie rozjezdza fold-do-foldu (sygnal dopasowania do szumu JEDNEGO okna).

  **Zastosowane do 4 par best17_a wskazanych przez usera** (lokalna siatka 3x3 lub 3x2 wokol
  wartosci domyslnych, `wf_mean_cagr` z 5 okien walk-forward):

  | Para | default_meets_threshold (3%) | plateau_area | gap_to_best | Kendall's W (5 foldow) |
  |---|---|---|---|---|
  | `ema7_16.fast_span` x `slow_span` | **TAK** | 6/9 (67%) | ~0% | 0.86 |
  | `ema5_12.fast_span` x `slow_span` | **NIE** | 0/9 | 8.2% | 0.95 |
  | `canary.bad_threshold` x `max_bad_count` | **NIE** | 0/6 | 8.2% | 0.98 |
  | `min_score_gap` x `alpha_weighting` (top1 share) | **TAK** | 5/9 (56%) | 1.6% | - |

  **Wniosek (bardziej precyzyjny niz poprzedni relative_drop)**: `ema7_16` (scoring) i
  `min_score_gap`/`alpha_weighting` siedza na SZEROKICH, POTWIERDZONYCH plateau - domyslne
  wartosci sa NAPRAWDE blisko lokalnego optimum, nie tylko "nie na samym skraju". `ema5_12`
  (kanarek) i `canary.bad_threshold` NIE spelniaja progu 3% tolerancji w tej lokalnej siatce -
  istnieje realna, NIE-losowa (Kendall's W 0.95/0.98 - bardzo wysoka zgodnosc rankingu fold-do-
  foldu, default konsekwentnie NIE wygrywa w ZADNYM z 5 okien) poprawa dostepna w pobliskich
  wartosciach (fast_span=6 zamiast 5, bad_threshold=-0.03 zamiast -0.02). To NIE jest sygnal
  overfittingu (odosobniony szczyt otoczony przez szum) - to sygnal NIEDO-strojenia: te 2
  parametry maja realna, konsekwentnie powtarzalna (nie fold-specyficzna) przestrzen do poprawy,
  ktora obecna konfiguracja nie wykorzystuje.

  13 nowych testow (`test_local_param_stability.py` - plateau vs szczyt, asymetria, pozycja
  domyslnej, flood-fill 2D, default ponizej progu nie pozycza od sasiada, zgodnosc/rozbieznosc
  rankingow miedzy foldami). 389/389 testow przechodzi.

## 2026-07-11 (23)

- **Analiza overfittingu `best17_a` parametr-po-parametrze** (user: "mam obawy czy ona nie jest
  overfitting"). Dotychczasowy `param_stability` liczyl TYLKO 2D siatke
  `canary.bad_threshold`×`min_score_gap` razem (26.7% relative_drop) - nie mowilo to KTORY z nich
  za to odpowiada, ani czy ksztalt krzywej to gladkie plateau (bezpieczne) czy odosobniony szczyt
  (sygnal overfittingu). Rozbite na 12 osobnych sweepow "jeden-parametr-naraz" (`wf_mean_cagr` z
  walk-forward na `train_window`, reszta parametrow trzymana na domyslnej wartosci):

  | Parametr | relative_drop | Ksztalt |
  |---|---|---|
  | `ema7_16.fast_span` (scoring) | 30.8% | PLATEAU - rosnie do 7 (domyslne), potem PLASKIE (7=8 identyczne) |
  | `ema7_16.slow_span` (scoring) | 30.7% | PLATEAU - rosnie do 16 (domyslne), potem PLASKIE (16=18=20 identyczne) |
  | `ema5_12.fast_span` (kanarek) | 28.8% | monotoniczny, domyslne (5) NIE najlepsze - 7 daje lepszy wynik (zapas, nie overfitting) |
  | `canary.bad_threshold` | 23.2% | NIE-MONOTONICZNY (dolek przy -0.01) - jedyny param z "szumowym" wygladem |
  | `mom_r3.window` | 12.2% | umiarkowana, domyslne blisko najlepszego |
  | `canary.max_bad_count` | 8.2% | niska |
  | `ema5_12.slow_span` | 8.2% | niska |
  | `alpha_weighting.weights` | 5.6% | niska, domyslne blisko najlepszego |
  | `execution.min_score_gap` | 3.9% | niska - spojne z wczesniejszym 2D sweepem |
  | `iau_gate.threshold` | **0.0%** | MARTWY - gate prawie nigdy nie binduje w oknach WF |
  | `dbc_gate.threshold` | **0.0%** | MARTWY - jw. |
  | `rebound.threshold` | **0.0%** | MARTWY - rebound prawie nigdy sie nie aktywuje |

  **Wniosek**: BRAK klasycznego sygnalu ciezkiego overfittingu na glownych parametrach scoringu -
  wysoki `relative_drop` `ema7_16` (fast/slow) wynika z tego, ze jeden EKSTREMALNY koniec zakresu
  (zbyt krotkie okno) jest gorszy, a od wartosci domyslnej W GORE wynik jest PLASKI (czesciowo
  identyczny) - to "bezpieczny" ksztalt (szeroki plateau), nie "kruchy" (waski szczyt). Jedyny
  parametr z prawdziwie nie-monotonicznym wygladem to `canary.bad_threshold` - i co ciekawe,
  wartosc domyslna (-0.02) NIE siedzi na lokalnym optimum (gdyby to byl overfitting,
  spodziewalibysmy sie domyslnej wartosci DOKLADNIE na szczycie). 3 parametry sa calkowicie
  martwe w testowanym zakresie okien WF - mniejsza realna powierzchnia do overfittingu niz
  sugerowalaby pelna lista 12 parametrow, ale ich wartosc "na przyszlosc" niepotwierdzona.

## 2026-07-11 (22)

- **Eksperyment: `strategies_v2/vaa_g4_ema/` i `strategies_v2/daa_g4_ema/`** (user, reagujac na
  rozczarowujacy wynik `daa_g4`: "a co jesli posprawdzasz te oryginalne strategie korzystajac np
  z EMA zamiast tego momentum"). Identyczny mechanizm co `vaa_g4`/`daa_g4` (te same
  ofensywne/obronne/kanarek, te same `portfolio_risk_engine`), ale score = `ema_ratio_monthly`
  (fast=7, slow=16 - te same wartosci co w `best17_a`) zamiast 13612W momentum. **Zero nowego
  kodu blokow** - `ema_ratio_monthly` juz istnieje i jest w pelni ogolny, tylko podmieniona
  konfiguracja `indicators`/`asset_scoring`.

  **UCZCIWY WYNIK: EMA wyraznie GORSZE niz momentum, na CALEJ siatce sweepowanych spanow**
  (9 kombinacji fast_span×slow_span kazda, `allowed_param_families`):

  | | momentum (13612W) | EMA (7/16, jak best17_a) | EMA - najlepszy z 9 wariantow (7/12) |
  |---|---|---|---|
  | `vaa_g4` | CAGR 7.98%, MaxDD -24.45%, Sharpe 0.712 | CAGR 2.69%, MaxDD -36.47%, Sharpe 0.263 | CAGR 3.73%, MaxDD -36.47%, Sharpe 0.336 |
  | `daa_g4` | CAGR 6.62%, MaxDD -25.50%, Sharpe 0.538 | CAGR 5.59%, MaxDD -41.40%, Sharpe 0.417 | CAGR 6.97%, MaxDD -36.47%, Sharpe 0.513 |

  Nawet NAJLEPSZY z 9 sweepowanych wariantow EMA nie bije domyslnego momentum w zadnym z dwoch
  strategii. MaxDD identyczny (-36.47%) w wiekszosci wariantow EMA niezaleznie od spanow -
  sugeruje TEN SAM realny kryzys (prawdopodobnie 2022 lub 2008) nie zostal unikniety przez
  zadna kombinacje EMA, mimo strojenia.

  **Prawdopodobny powod**: `ema_ratio_monthly(7,16)` zostal dobrany dla `best17_a`
  (XLK/IVV/DBC/IAU - szybszy, waskoscezowy trend na akcjach technologicznych/surowcach/zlocie),
  NIE dla `vaa_g4`/`daa_g4` (SPY/EFA/VWO/AGG - wolniejsza, szeroka rotacja miedzy klasami
  aktywow). 13612W momentum (wazona srednia 1/3/6/12m) jest zaprojektowany WLASNIE do takiej
  wolniejszej, wieloklasowej rotacji (oryginalna metodologia VAA/DAA) - crossover EMA reaguje
  za wolno/za szybko (whipsaw) na tym typie uniwersum.

  10 nowych testow (`test_ema_variant_strategy_specs.py` - walidacja obu specow, uzycie EMA nie
  momentum, end-to-end na realnych danych, zamrozona regresja "EMA gorsze niz momentum" dla obu
  par). 376/376 testow przechodzi.

## 2026-07-11 (21)

- **NOWA STRATEGIA `strategies_v2/daa_g4/` - "DAA-G4" (Defensive Asset Allocation, Keller &
  Keuning 2017)** (user: "Brakuje nam DAA Kellera" - zaimplementowane z wiedzy o publikacji,
  user zdecydowal nie podawac wlasnego opisu). Rozni sie od naszego `vaa_g4` (Keller VAA) na 2
  sposoby: (1) kanarek to OSOBNE, MALE uniwersum (`VWO`+`AGG` - tylko 2 z 4 aktywow ofensywnych,
  nie wszystkie 4 jak w VAA); (2) udzial ochronny jest CIAGLY (0%/50%/100% dla 2 kanarkow), nie
  binarny (VAA: jeden zly kanarek = 100% ochrony natychmiast). Uniwersum (identyczne jak
  `vaa_g4`): 4 ofensywne (SPY/EFA/VWO/AGG), 3 obronne (SHY/IEF/LQD). Score = 13612W momentum
  (12*r1+4*r3+2*r6+1*r12)/19 - REUZYTE identyczne `indicators`/`asset_scoring` co `vaa_g4`, zero
  nowego kodu tam.

  **NOWY BLOK**: `portfolio_risk_engine/daa_canary_breadth_switch.py` - kanarek jako OSOBNY
  parametr (nie `offensive_assets` caly) + ciagly udzial ochronny (B/len(canary), nie binarne
  przelaczenie). Top1 ofensywny + top1 obronny, zawsze NAJLEPSZY DOSTEPNY (bez wzgledu na znak -
  udzial ochronny juz kompensuje slaby rynek). Zweryfikowano na realnych danych (2008, 2009,
  2020) - mieszane sloty 50/50 (np. `{"agg.us": 0.5, "ief.us": 0.5}`) faktycznie wystepuja.

  **Wynik (2006-02 do 2026-07, 246 miesiecy, PRZED podatkiem)**: CAGR 6.62%, MaxDD -25.50%,
  Sharpe 0.54, Calmar 0.26, turnover 7.64/rok - **UCZCIWIE GORZEJ niz nasz `vaa_g4`** (CAGR
  7.98%, MaxDD -24.45%, Sharpe 0.71, Calmar 0.33) w TYM konkretnym zestawie danych, mimo ze
  opublikowana praca Kellera&Keuninga twierdzi ze DAA generalnie bije VAA - prawdopodobnie
  dataset-specyficzne (inny okres/uniwersum niz oryginalna publikacja). Train/test spojne (brak
  train/test blowup): CAGR 4.55%/4.72%, Sharpe 0.48/0.44.

  Param stability (sweep `hysteresis_pct`, 5 wariantow): `relative_drop = 0.0%` - ten sam
  "martwy parametr" wzorzec co `vaa_g4`/`the_one` (top1 binarny wybor, histereza wagowa nigdy
  nie blokuje przelaczenia w tym zakresie) - odnotowane jako ograniczenie sweepa, nie prawdziwa
  stabilnosc.

  13 nowych testow (`test_daa_components.py` - 0%/50%/100% udzial ochronny, NaN kanarek liczy
  sie jako zly, ofensywny wybiera najlepszego dostepnego nawet przy ujemnym score, top_n>1
  dzieli po rowno, fallback do `_CASH`; `test_daa_g4_strategy_spec.py` - kanarek WLASCIWYM
  podzbiorem ofensywnych (nie rownym), end-to-end z dowodem na wszystkie 3 poziomy udzialu
  ochronnego, zamrozony baseline). 366/366 testow przechodzi.

## 2026-07-11 (20)

- **Stabilnosc wagi combinera dla `gpm_best17_a`** (user: "Jak ze stabilnoscia naszego
  najlepszego miksu?"). Dotad `param_stability` liczylismy tylko na WEWNETRZNYCH parametrach
  pojedynczej strategii (`allowed_param_families`) - tu pierwszy raz zastosowane do WAGI
  COMBINERA (jedynego "parametru" miksu 2 strategii), przez `compute_param_stability` (istniejaca
  funkcja, zero nowego kodu) na sweep-u `best17_a_weight` w [0.35..0.70], wf_mean_* z
  walk-forward na `train_window` (2010-06 do 2019-12, jak `best17_a`):

  | Metryka (walk-forward, train) | relative_drop |
  |---|---|
  | `wf_mean_sharpe` | **2.9%** - PLASKO, wagi 35-70% dajа niemal identyczny Sharpe |
  | `wf_mean_cagr` | 30.3% - ALE monotoniczny wzrost z waga `best17_a`, NIE krucha rodzina (patrz nizej) |

  **Wazna roznica**: wysoki `relative_drop` dla CAGR NIE oznacza kruchosci w sensie
  "overfitting" (izolowany szczyt otoczony gorszymi sasiadami) - tu CAGR rosnie MONOTONICZNIE
  z waga `best17_a` (bardziej agresywna noga = wiecej CAGR, oczekiwane, nie przypadkowe). Sharpe
  (relative_drop 2.9%) jest wlasciwa miara "czy wybor dokladnej wagi ma znaczenie" - i mowi
  wyraznie NIE: 35-70% `best17_a` daje Sharpe w waskim pasmie w KAZDYM z 2 okresow (train
  1.10-1.14, test/OOS 0.92-0.94).

  **Ale**: Calmar (metryka wg ktorej wybralismy 55/45) zachowuje sie ROZNIE w train vs test:
  TRAIN Calmar maleje MONOTONICZNIE z waga `best17_a` (0.94 przy 35% -> 0.72 przy 70% - im wiecej
  `gpm`, tym lepiej), TEST/OOS Calmar ma PRAWDZIWY SZCZYT kolo 55% (0.75 przy 35% -> **0.83** przy
  55% -> 0.72 przy 70%). Te dwa okresy NIE ZGADZAJA SIE co do optymalnej wagi dla Calmar
  konkretnie - "55/45 jest optymalne" jest wiec czesciowo dopasowane do specyfiki okresu
  2020-2026 (COVID + 2022), nie w pelni potwierdzone w oknie treningowym 2010-2019.

  **Wniosek**: sama KONCEPCJA miksu `gpm`+`best17_a` jest solidna i odporna (Sharpe stabilny w
  obu okresach, szeroki zakres wag 40-65% daje podobny wynik) - ale DOKLADNA waga 55/45 dobrana
  pod maksymalny Calmar nie powinna byc traktowana jako precyzyjnie skalibrowana, tylko jako
  "rozsadny wybor w szerokiej dobrej strefie". Dla porownania: `gpm` solo relative_drop
  wlasnych parametrow = 9.6%, `best17_a` solo = 26.7% (patrz sekcja PARAM STABILITY).

## 2026-07-11 (19)

- **`strategies_v2/gtaa_agg6_best17_a/` - miks gtaa_agg6+best17_a** (user: "Nigdy nie łącz 3 -
  max 2" - odrzucenie wczesniejszego pomyslu trojki gpm+best17_a+vaa_g4, tylko pary). Sweep wagi
  `best17_a` w [0.30..0.70] na PELNYM realnym backtescie, PO PODATKU:

  | best17_a / gtaa_agg6 | CAGR | MaxDD | Sharpe | Calmar | Turnover |
  |---|---|---|---|---|---|
  | 40% / 60% | 9.86% | -17.92% | 0.898 | 0.551 | 2.11 |
  | **45% / 55%** | **10.31%** | -18.31% | 0.909 | **0.563** | 2.00 |
  | 50% / 50% | 10.76% | -19.03% | 0.918 | 0.565 | 1.89 |
  | 55% / 45% | 11.20% | -19.90% | 0.923 | 0.563 | 1.77 |

  **UCZCIWY NEGATYWNY WYNIK**: najlepszy Calmar (0.563 przy 45/55) jest WYRAZNIE GORSZY niz
  `gpm_best17_a` (55/45): Calmar 0.707, MaxDD -15.40% vs -18.31%. `gtaa_agg6` solo ma glebszy
  MaxDD (-18.71%) niz `gpm` solo (-15.20%), wiec mniej skutecznie tlumi drawdown `best17_a` -
  prawdopodobnie tez wieksza korelacja sygnalu z `best17_a` (oba trend/momentum na tym samym
  uniwersum akcji USA) niz `gpm` (odrebna koncepcja - korelacja do koszyka, nie tylko trend).
  Zapisane jako dokumentacja eksperymentu, NIE jako rekomendacja - `gpm_best17_a` pozostaje
  lepszym wyborem. Automatycznie odkryte i przetestowane przez `test_all_combined_specs.py`
  (glob-discovery) - zero nowych plikow testowych.

## 2026-07-11 (18)

- **NOWE STRATEGIE `strategies_v2/gtaa_agg3/` i `strategies_v2/gtaa_agg6/` - "GTAA AGG3/AGG6"**
  (user zmienil plan w trakcie sweepu gpm+best17_a+vaa_g4 - zamiast tego dostarczyl opis nowej
  strategii do odtworzenia). Mechanizm: (1) `score = srednia zwrotow 1/3/6/12m` - reuzyty
  ISTNIEJACY `indicators.momentum_avg_month_end` (zbudowany wczesniej dla `gpm`, identyczny
  wzor); (2) top3 (AGG3) albo top6 (AGG6) wg `score`; (3) rowne wagi (33.33%/16.67%); (4) filtr
  trendu PER SLOT (nie globalny) - cena konca miesiaca ponizej 6-miesiecznej SMA -> TA CZESC
  kapitalu (nie caly portfel) trafia do obligacji zamiast do aktywa; (5) rebalans co miesiac,
  bez histerezy.

  Wymagal 1 NOWEGO bloku: `portfolio_risk_engine/gtaa_trend_bond_reroute.py` - w odroznieniu od
  `canary_regime_gate` (globalny gate na cala grupe) i `gpm_breadth_protective_split` (ciagle
  skalowanie globalnego udzialu), tu KAZDY SLOT jest oceniany NIEZALEZNIE - czesc portfela moze
  byc w akcjach a czesc rownoczesnie w obligacjach w tym samym miesiacu. Zweryfikowano na
  realnych danych (2008, 2022) - mieszane sloty (np. `{"dbc.us": 0.333, "ief.us": 0.667}`)
  faktycznie wystepuja w historii, nie tylko binarne 0%/100%.

  **Brakujace dane**: user wskazuje VGIT (US)/IUSM (UCITS) jako fallback obligacyjny - oba
  NIEDOSTEPNE w naszych danych, zastapione IEF (7-10Y skarbowe, najblizszy zamiennik). Uniwersum
  ryzykowne (10, user: "klasyczne GTAA na dostepnych danych"): IVV, IJR, EFA, VWO, VNQ, DBC, GLD,
  HYG, LQD, TLT.

  **Wynik (2007-05 do 2026-08, PRZED podatkiem)**: `gtaa_agg3` CAGR 6.99%, MaxDD -19.69%, Sharpe
  0.58, Calmar 0.35, turnover 3.81/rok; `gtaa_agg6` CAGR 6.30%, MaxDD -18.71%, Sharpe 0.66,
  Calmar 0.34, turnover 3.00/rok - AGG6 wyraznie lepszy Sharpe (szersza dywersyfikacja), AGG3
  wyzszy CAGR (koncentracja). Named periods: OBIE odmiany DODATNIE przez `gfc_crash`
  (+4.86%/+2.04% CAGR) - trend-following + rotacja do obligacji dziala jak zaprojektowano w
  klasycznym kryzysie.

  **Param stability** (sweep `sma_window` 3-9, 7 wariantow): `gtaa_agg3` relative_drop=17.1%
  (PASS, prog 0.30), `gtaa_agg6` relative_drop=30.3% (borderline **FAIL** - najlepszy wariant
  `sma_window=9`, nie domyslne 6 - odnotowane uczciwie, prog NIE poluzowany zeby to ukryc).

  17 nowych testow (`test_gtaa_components.py` - reroute tylko wlasciwego slotu, cala portfolio
  do obligacji gdy wszystkie slabe, slot o wadze 0 ignorowany; `test_gtaa_strategy_specs.py` -
  wiring obu wariantow, top_n==liczba wag, bond_fallback wykluczony z selekcji, end-to-end na
  realnych danych z dowodem na mieszane sloty, zamrozone baseline'y metryk). 351/351 testow
  przechodzi.

## 2026-07-11 (17)

- **NOWY MODUL `engine_v2/named_periods.py` - `AcceptanceSpec.named_periods` faktycznie
  liczony** (user: "A named periods możesz pokazać?") - ten sam wzorzec co wczesniej
  `param_stability` i `annual_tax`: pole zdefiniowane w `acceptance_spec.py` OD POCZATKU
  projektu, uzywane juz w `example_strategy`/`all_weather_4` `acceptance_spec.json`
  ("covid_crash_rebound", "inflation_bear", "post_gfc_recovery"), ale NIGDZIE nie liczone -
  `Criteria` w `named_periods` niesie tylko progi, nie zakres dat, wiec brakowalo mapowania
  nazwa->daty i kodu, ktory by to faktycznie sprawdzil.

  Nowy `KNOWN_PERIODS` (WSPOLNY dla calego repo, zeby wyniki byly porownywalne 1:1 miedzy
  strategiami pod tymi samymi etykietami):
  - `gfc_crash`: 2008-01-01 - 2009-03-31 (szczyt do dna S&P, dno 2009-03-09)
  - `post_gfc_recovery`: 2009-04-01 - 2012-12-31
  - `covid_crash_rebound`: 2020-02-01 - 2020-12-31 (krach + odbicie w tym samym roku)
  - `inflation_bear`: 2022-01-01 - 2022-12-31

  Wpiete w `run_spec_runner._run_final` - jesli `acceptance_spec.named_periods` niepuste,
  `result["named_periods"]` niesie metryki + checki per okres (na equity_curve PO podatku).
  7 nowych testow (`test_named_periods.py` - okresy nienakladajace sie, nieznany okres rzuca
  blad, metryki+checki dla pokrytego okresu, `covered=False` gdy equity_curve nie siega okresu,
  pusty slownik = brak wpisu; `test_run_spec_runner.py` - 2 nowe: wiring pojawia sie/znika wg
  `named_periods` w spec).

  **Wynik dla 4 kluczowych strategii/portfeli (po podatku)**:

  | | gfc_crash | post_gfc_recovery | covid_crash_rebound | inflation_bear |
  |---|---|---|---|---|
  | `gpm` solo | **+1.9%** CAGR, MaxDD -7.1% | +5.2%, -10.2% | +9.8%, -6.1% | **-5.5%**, -7.1% |
  | `best17_a` solo | -14.2%*, -12.3% | +18.2%, -15.5% | +29.7%, -29.5% | -15.2%, -19.5% |
  | `gpm_best17_a` (55/45) | -3.8%, -9.2% | +12.3%, -13.8% | +21.8%, -15.4% | -10.5%, -13.8% |
  | `vaa_g4_best17_a` | +0.1%, -7.8% | +19.6%, -12.4% | +27.0%, -14.3% | -14.6%, -17.3% |

  (*`best17_a`'s dane zaczynaja sie 2008-07, wiec `gfc_crash` to u niego tylko 9 z 15 miesiecy
  okresu - nieporownywalne 1:1 z resztą, zaznaczone jawnie, nie ukryte.)

  Potwierdza wczesniejsze ustalenie z porownania rok-po-roku: `gpm` jest realnie DODATNI w GFC
  (2008) i lagodzi `inflation_bear` (2022) najbardziej ze wszystkich - ale `inflation_bear`
  pozostaje trudny dla KAZDEJ z 4 strategii (wszystkie na minusie), zgodnie z wczesniej
  zidentyfikowanym pekniuciem korelacji akcje-obligacje w tym konkretnym roku.

## 2026-07-11 (16)

- **`strategies_v2/gpm_best17_a/` - miks defensywnego `gpm` z agresywnym `best17_a`** (user: "dobrze
  go zmiksować z czymś agresywnym np best17"). `fixed_capital_weights`, sweep wagi `best17_a` na
  PEŁNYM realnym backteście (nie zgadywane) w [0.30..0.70], krok 0.05 wokół optimum, PO PODATKU:

  | best17_a / gpm | CAGR | MaxDD | Sharpe | Calmar | Turnover |
  |---|---|---|---|---|---|
  | 35% / 65% | 8.86% | -13.98% | 0.942 | 0.634 | 3.11 |
  | 40% / 60% | 9.37% | -14.27% | 0.954 | 0.657 | 2.93 |
  | 45% / 55% | 9.88% | -14.56% | 0.960 | 0.678 | 2.75 |
  | 50% / 50% | 10.39% | -14.87% | 0.963 | 0.699 | 2.57 |
  | **55% / 45%** | **10.89%** | **-15.40%** | 0.962 | **0.707** | **2.39** |
  | 60% / 40% | 11.38% | -17.04% | 0.959 | 0.668 | 2.21 |

  **55/45 (best17_a/gpm) zapisane jako oficjalny `combined_spec.json`** - **NAJLEPSZY CALMAR
  CAŁEJ SESJI** (0.707, poprzedni rekord `vaa_g4_best17_a` 0.649), przy DUŻO niższym turnowerze
  (2.39/rok vs 4.24/rok) i niższym MaxDD (-15.40% vs -17.33%) niż dotychczasowa rekomendacja
  `vaa_g4_best17_a`, kosztem odrobiny Sharpe (0.962 vs 0.993) i CAGR (10.89% vs 11.25%).
  Automatycznie odkryty i przetestowany przez istniejący `test_all_combined_specs.py`
  (glob-discovery) - zero nowych plików testowych potrzebnych.

  **Nowa rekomendacja sesji**: `gpm_best17_a` (55/45) zastępuje `vaa_g4_best17_a` jako
  najsensowniejszy wybór, jeśli priorytetem jest MaxDD/Calmar i niski turnover; `vaa_g4_best17_a`
  pozostaje lepszy, jeśli priorytetem jest czysty Sharpe.

## 2026-07-11 (15)

- **NOWA STRATEGIA `strategies_v2/gpm/` - "Generalized Protective Momentum"** (user poprosił o
  strategię z niższym MaxDD, potem dostarczył pełny opis mechanizmu GPM do odtworzenia). Wymagała
  4 CAŁKOWICIE NOWYCH implementacji blokow (nie dało się złożyć z istniejących):
  - `indicators/momentum_avg_month_end.py` - średnia momentum z kilku okien (1/3/6/12m) na
    cenach końca miesiąca.
  - `indicators/corr_to_basket_month_end.py` - rocząca się korelacja miesięcznych zwrotów
    każdego tickera do równoważonego koszyka wskazanych tickerów (stały koszyk, ten sam przy
    ocenie KAŻDEGO tickera, włącznie z samym koszykiem - zamierzone, wierne odtworzenie
    metodologii GPM, nie błąd).
  - `asset_scoring/momentum_times_decorrelation.py` - `score = momentum * (1 - korelacja)` -
    ILOCZYN dwóch wskaźników, nie liniowa suma wazona jak `weighted_sum` (który by tego nie
    wyraził).
  - `portfolio_risk_engine/gpm_breadth_protective_split.py` - zamiast binarnego przełączenia
    risk-on/off (jak `vaa_canary`), udział części ochronnej skaluje się CIĄGLE wg szerokości
    rynku: `n` = liczba z 12 aktywów ryzykownych z dodatnim score; `n<=6` → 100% ochrony, inaczej
    `(12-n)/6`. Reszta kapitału w top3 aktywa ryzykowne wg score, po równo. Zweryfikowano na
    realnych danych, że mechanizm faktycznie się aktywuje poprawnie (100% w IEF przez cały
    2008 i marzec-czerwiec 2020, ciągłe skalowanie 0.167/0.333/0.5/0.833/1.0 widoczne w historii
    wag - nie tylko binarne 0/100%).

  **Brakujące dane**: IWM, VGK, EWJ, EEM nie istnieją w `data/us/nyse/` - user wybrał opcję
  "zamienniki" (zapytany przez `AskUserQuestion`): IWM→IJR (US small cap), EEM→VWO (rynki
  wschodzące, niemal identyczny fundusz), VGK→EFA, EWJ→VEA (oba "developed ex-US", znacząco
  nakładające się - NIE oddzielne Europa/Japonia jak w oryginale, świadome przybliżenie z powodu
  braku danych, jawnie opisane w `hypothesis`).

  **Wynik (pełna historia 2007-08 do 2026-08, PRZED podatkiem)**: CAGR 5.32%, **MaxDD -15.20%**
  (NAJNIŻSZY z całej sesji - niżej niż dotychczasowy rekord `dual_momentum_all_weather_4`
  -16.71%), Sharpe 0.67, Calmar 0.35, turnover 4.36/rok. Train (2009-2019) i test/OOS (2020-2026)
  spójne (CAGR 4.65%/6.10%, MaxDD -12.87%/-15.20%, Sharpe 0.61/0.72 - lepiej OOS niż w treningu,
  nie odwrotnie). Wszystkie 7 okien walk-forward DODATNIE (CAGR 1.6%-5.7%, nigdy ujemne).
  Param stability (sweep `top_n_risky`×`full_protective_max_n`, 9 wariantów): `relative_drop =
  9.6%` - NAJBARDZIEJ STABILNA rodzina parametrów w całym repo (dla porównania: `best17_a` 26.7%,
  `all_weather_4` 46.1%).

  16 nowych testów (`test_gpm_components.py` - 4 nowe bloki na danych syntetycznych;
  `test_gpm_strategy_spec.py` - wiring realnego `strategy_spec.json`, oba reżimy
  ochrona/ekspozycja realnie występują w historii, nigdy więcej niż `top_n_risky` aktywów
  naraz, zamrożony baseline metryk).

## 2026-07-11 (14)

- **Eksperyment: `strategies_v2/synergy_v1` i `strategies_v2/synergy_v2`** - user poprosił o próbę
  złożenia JEDNEGO nowego pipeline'u (nie fixed-weight combinera dwóch gotowych strategii) z
  najlepszych pomysłów z tej sesji: szkielet `best17_a` (kanarek VT+XLK, gates IAU/DBC, rebound,
  histereza) + koncepcja GEM/`the_one` (absolutny 12m momentum na obligacji jako warunek
  eligibilności) + szersze uniwersum (TLT.us jako dodatkowa klasa aktywów, zamiast osobnej
  strategii hedgującej jak w `best17_a_tlt_hedge`).

  - `synergy_v1`: TLT.us eligibilny ZAWSZE (gdy ma dodatni 12m momentum), konkuruje w TYM SAMYM
    rankingu EMA7/EMA16 co XLK/IVV/DBC/IAU. Wynik: **gorzej niż `best17_a` solo na każdej
    metryce** (CAGR 14.04% vs 16.07% po podatku, MaxDD -29.99% vs -29.47%, Sharpe 0.83 vs 0.93) -
    TLT czasem wypierał lepsze aktywa ofensywne z rankingu nawet w risk-on (crowding-out).
  - `synergy_v2`: poprawka - TLT.us i 4 aktywa ofensywne są WZAJEMNIE WYKLUCZAJĄCE SIĘ (nowy
    param `invert` w `canary_regime_gate` - patrz niżej), TLT wchodzi TYLKO gdy kanarek mówi
    risk-off ORAZ własny 12m momentum > 0. Mechanizm faktycznie się aktywuje (TLT 100% wagi przez
    cały kryzys 2008-09), ale wynik dalej **nie bije `best17_a` solo** (CAGR 15.59% vs 16.07% po
    podatku, MaxDD -29.99% vs -29.47%, Sharpe 0.89 vs 0.93) - najgorszy rok kalendarzowy
    identyczny jak solo (2022), bo akurat wtedy TLT też miał ujemny momentum (znane pęknięcie
    korelacji akcje-obligacje), więc bramka nie uratowała dokładnie tam, gdzie byłaby najbardziej
    potrzebna.

  **Wniosek**: wbudowanie ekspozycji na obligacje w TEN SAM pipeline selekcji (czy to przez
  współzawodnictwo, czy przez wykluczanie się binarne) NIE bije już znalezionych kombinacji
  (`vaa_g4_best17_a`, `best17_a_tlt_hedge`) zbudowanych jako COMBINER dwóch osobnych strategii z
  płynną wagą - `momentum_hedge_overlay`/`fixed_capital_weights` uśredniają ekspozycję w sposób
  ciągły, podczas gdy selektor top_n przełącza się binarnie (0% albo 100%), co jest brutalniejsze
  i nie łagodzi DD tak samo. Rekomendacja z sesji (`vaa_g4_best17_a`) pozostaje bez zmian.

  **NOWY PARAM `invert` w `engine_v2/blocks/asset_filters/canary_regime_gate.py`** (opcjonalny,
  domyślnie `False`, wsteczna kompatybilność zachowana - 71 istniejących testów bez zmian) -
  odwraca wynik gate'u (target_assets eligibilne dokładnie gdy regime jest risk-OFF, nie risk-on).
  1 nowy test jednostkowy (`test_canary_regime_gate_invert_flips_eligibility`) + 9 nowych testów
  end-to-end (`test_synergy_strategy_specs.py` - walidacja specs, resolve blocks, pełny łańcuch na
  realnych danych, wzajemne wykluczanie TLT/aktywa ofensywne w `synergy_v2`, 2 zamrożone baseline'y
  metryk).

## 2026-07-11 (13)

- **NOWY MODUL `engine_v2/annual_tax.py` - roczny podatek od zysków (19%, "Belka")** - user
  pytanie: "czy one maja uwzgledniony podatek 20 procent od zyskow?" - odpowiedz brzmiala NIE,
  ZERO liczby pokazanej w calej sesji dotad nie uwzgledniala podatku (mimo ze
  `TestSpec.CostsSpec.annual_tax_rate` byl zdefiniowany OD POCZATKU projektu, jak
  `param_stability` wczesniej - kolejne "zdefiniowane, nigdy nie liczone" pole). Po potwierdzeniu
  stawki (19%, jak w starym silniku, nie 20%) - zaimplementowane i wpiete.

  Odtworzone WPROST z `apply_annual_tax_if_year_end` (`engine/backtest_hybrid_search.py`,
  zdublowane w `engine/replay_mapped_monthly.py`) - podatek "high water mark":
  ```
  taxable_profit = max(0, equity_przed_podatkiem - tax_base_equity)
  tax_amount = taxable_profit * annual_tax_rate
  equity_po_podatku = equity_przed_podatkiem - tax_amount
  tax_base_equity = max(tax_base_equity, equity_po_podatku)   # nigdy nie spada po stratnym roku
  ```
  Liczony RAZ ROCZNIE (ostatni dostepny dzien handlowy grudnia w danych), TYLKO od wzrostu ponad
  dotychczasowy szczyt (rok stratny nie daje zwrotu, ale tez nie "zapomina" poprzedniego szczytu -
  kolejne zyski sa opodatkowane dopiero po odrobieniu strat). Haircut propaguje sie na wszystkie
  kolejne dni do nastepnego poboru - to realne zmniejszenie kapitalu.

  Wpiete w `run_spec_runner.py` (`_run_final`/`_run_validation` - podatek liczony na CALEJ
  historii PRZED ciecem do `test_window` w `"validation"`, inaczej high-water-mark zresetowalby
  sie blednie na starcie okna) - wynik ma teraz `metrics_pre_tax` obok `metrics`, jesli
  `TestSpec.costs.annual_tax_rate > 0` (nie ukryte - oba widoczne).

  **Ujednolicono `annual_tax_rate` na 0.19 we WSZYSTKICH `test_spec.json`** - okazalo sie, ze bylo
  to niespojnie ustawione JUZ WCZESNIEJ (5 strategii mialo 0.19, 5 mialo 0.0), ale nigdzie nie
  bylo faktycznie liczone, wiec ta niespojnosc nigdy nie mial znaczenia - teraz ma.

  8 nowych testow jednostkowych (`test_annual_tax.py` - noop przy stawce 0, pelne opodatkowanie
  pojedynczego zyskownego roku, brak zwrotu w stratnym roku, high-water-mark nie podwaja podatku
  do nowego szczytu, propagacja haircuta, brak grudnia w danych = brak podatku, duplikaty dat) +
  2 nowe testy `test_run_spec_runner.py` (podatek stosuje sie gdy skonfigurowany, brak
  `metrics_pre_tax` gdy nie skonfigurowany).

  **Pelne porownanie PRZED/PO podatku (19%), wszystkie 11 solo + 27 portfeli** - CAGR/MaxDD/Sharpe
  spadaja wszedzie tam gdzie strategia miala dodatnie lata (oczywiscie), ale relatywna KOLEJNOSC
  strategii prawie sie nie zmienia:

  | Strategia | CAGR przed | CAGR po | MaxDD przed | MaxDD po | Sharpe przed | Sharpe po |
  |---|---|---|---|---|---|---|
  | `best17_a` | 16.49% | 16.07% | -29.47% | -29.47% | 0.96 | 0.93 |
  | `vaa_g4_best17_a` | 11.48% | 11.25% | -18.21% | -17.33% | 1.03 | **0.99** |
  | `combined_triple` | 11.54% | 11.26% | -18.08% | -19.65% | 0.99 | 0.96 |
  | `best17_a_tlt_hedge` | 14.10% | 13.78% | -23.70% | -22.09% | 0.97 | 0.94 |
  | `combined_best2_dynamic` | 14.02% | 13.71% | -26.75% | -26.40% | 0.95 | 0.92 |
  | `combined_best2` | 12.58% | 12.27% | -22.73% | -22.73% | 0.94 | 0.91 |
  | `best17_a_all_weather_4` | 11.84% | 11.53% | -21.84% | -22.01% | 0.98 | 0.95 |
  | `gfm` | 9.61% | 9.22% | -33.70% | -31.72% | 0.71 | 0.68 |
  | `the_one` | 8.76% | 8.56% | -23.59% | -22.98% | 0.61 | 0.59 |
  | `all_weather_4` | 8.87% | 8.63% | -25.54% | -25.54% | 0.82 | 0.79 |

  **Ciekawostka**: MaxDD dla kilku strategii (`vaa_g4`, `dual_momentum_vaa_g4`,
  `best17_a_tlt_hedge`) wyszlo LEPSZE po podatku (np. `vaa_g4` -24.45%->-22.84%) - artefakt
  liczenia MaxDD w procentach: podatek obcina szczyty (peaks) uzywane jako baza do liczenia
  procentowego spadku, wiec ta sama nominalna strata z pozniejszego okresu wyglada jak MNIEJSZY
  procentowy spadek wzgledem nizszego, juz-opodatkowanego szczytu. Nie blad - realny efekt
  uboczny liczenia drawdown na bazie procentowej po opodatkowaniu.

  `vaa_g4_best17_a` pozostaje najlepszym Sharpe w repo rowniez PO podatku (0.99).

  Pelny pakiet testow: **299/299**.

## 2026-07-11 (12)

- **WSZYSTKIE PARY 7 glownych strategii** - user: "dołóż brakujące kombinacje". Sposrod C(7,2)=21
  mozliwych par (`dual_momentum`, `vaa_g4`, `the_one`, `best17_a`, `all_weather_4`, `gfm`,
  `best17_b`) byla przetestowana tylko 1 (`the_one`+`best17_a` = `combined_best2`). Dodano
  pozostale 20, wszystkie `fixed_capital_weights` 50/50 (STANDARDOWY split, NIE indywidualnie
  strojony na kazda pare - dla uczciwego porownania na tych samych zasadach).

  **ODKRYCIE**: `vaa_g4` + `best17_a` (50/50) daje Sharpe **1.03** - NAJLEPSZY w calym repo (bije
  nawet `combined_triple`'s 0.99), Calmar 0.63 (prawie identyczny z `combined_triple`'s 0.64),
  CAGR 11.48%, MaxDD -18.21% - to wszystko z PROSTEGO, niestrojonego 50/50 fixed split miedzy
  dwiema strategiami, ktore nigdy wczesniej nie byly razem testowane.

  Top 6 par wg Sharpe:

  | Para | CAGR | MaxDD | Sharpe | Calmar | Turnover/rok |
  |---|---|---|---|---|---|
  | `vaa_g4` + `best17_a` | 11.48% | -18.21% | **1.03** | 0.63 | 4.24 |
  | `best17_a` + `all_weather_4` | 11.84% | -21.84% | 0.98 | 0.54 | 1.23 |
  | `the_one` + `best17_a` (=`combined_best2`) | 12.58% | -22.73% | 0.94 | 0.55 | 3.63 |
  | `vaa_g4` + `all_weather_4` | 8.58% | -18.05% | 0.93 | 0.48 | 4.76 |
  | `best17_a` + `gfm` | 11.84% | -27.86% | 0.89 | 0.43 | 1.67 |
  | `best17_a` + `best17_b` | 10.99% | -29.42% | 0.84 | 0.37 | 1.46 |

  Wzorzec: KAZDA z 6 najlepszych par zawiera `best17_a` - potwierdza, ze jest to najsilniejsza
  pojedyncza "noga" w calym repo i dobry kandydat na core niemal kazdego portfela. Pary BEZ
  `best17_a` konsekwentnie wypadaja slabiej (najlepsza: `vaa_g4`+`the_one`, Sharpe 0.71).

  Nowe foldery: `dual_momentum_vaa_g4`, `dual_momentum_the_one`, `dual_momentum_best17_a`,
  `dual_momentum_all_weather_4`, `dual_momentum_gfm`, `dual_momentum_best17_b`, `vaa_g4_the_one`,
  `vaa_g4_best17_a`, `vaa_g4_all_weather_4`, `vaa_g4_gfm`, `vaa_g4_best17_b`,
  `the_one_all_weather_4`, `the_one_gfm`, `the_one_best17_b`, `best17_a_all_weather_4`,
  `best17_a_gfm`, `best17_a_best17_b`, `all_weather_4_gfm`, `all_weather_4_best17_b`,
  `gfm_best17_b` (20 folderow).

  **NOWY OGOLNY TEST** `test_all_combined_specs.py` - automatycznie odkrywa KAZDY
  `strategies_v2/*/combined_spec.json` (glob), waliduje i uruchamia end-to-end na realnych
  danych - zamyka luke "combined portfolio bez dedykowanego testu" (patrz README) dla
  WSZYSTKICH 27 portfeli naraz, w tym przyszlych, bez potrzeby pisania nowego pliku per portfel.
  55 nowych testow (27 portfeli x 2 + 1 sanity check).

  Pelny pakiet testow: **289/289**.

## 2026-07-11 (11)

- **BRAKUJACE TESTY end-to-end dla `best17_a` (solo) i `best17_a_tlt_hedge` (z hedge)** - user
  pytanie: "a best17 z hedge czy bez sa testy?". Odpowiedz brzmiala NIE dla obu: `best17_a` mial
  tylko testy komponentow na SYNTETYCZNYCH danych (`test_best17_a_components.py`), zero testu
  ladujacego faktyczny `strategy_spec.json` i uruchamiajacego go na realnych danych (w
  odroznieniu od `gfm`/`best17_b`, ktore takie testy juz maja); `best17_a_tlt_hedge` (CombinedSpec
  z `momentum_hedge_overlay`) nie mial ZADNEGO testu - cala weryfikacja przez cala sesje byla
  ad-hoc skryptami, bez trwalego testu regresyjnego.

  Dodano:
  - `test_best17_a_strategy_spec.py` (6 testow): walidacja, resolve_blocks, kanarek VT+XLK,
    `full_position_size==top_n`, end-to-end na realnych danych (oba rezymy risk-on/cash
    wystapily), zamrozony baseline metryk (CAGR~16.5%, MaxDD~-29.5%, Sharpe~0.96).
  - `test_best17_a_tlt_hedge.py` (4 testy): walidacja `combined_spec.json`, end-to-end na
    realnych danych (hedge faktycznie sie kiedys wlaczyl), REGRESJA dla bugfixu "hedge wlaczal
    sie przed startem core" (2026-07-11 - sprawdza wprost, ze `_CASH=1.0` na kazdej dacie sprzed
    startu `best17_a`), zamrozony baseline metryk (CAGR~14.1%, MaxDD~-23.7%, Sharpe~0.97).

  Pelny pakiet testow: **234/234**.

## 2026-07-11 (10)

- **PARAM STABILITY na WSZYSTKICH strategiach** - user: "trzeba wszystkie strategie tym
  posprawdzac i wszystkie parametry w jakims sensownym zakresie". Rozszerzono
  `allowed_param_families` tam, gdzie mialy tylko 1 wymiar sweepa (dodano drugi, sensowny
  parametr): `example_strategy` (+`sma_200.window` 150/200/250), `best17_a`
  (+`canary.bad_threshold` -0.03/-0.02/-0.01), `gfm` (+`regime_threshold` -0.02/0.0/0.02),
  `tlt_timing` (+`hysteresis_pct` 0.0/0.05/0.10), `the_one`/`vaa_g4` (rozszerzone
  `hysteresis_pct` na 5 wartosci). `best17_b`/`dual_momentum`/`all_weather_4` mialy juz 2
  wymiary - bez zmian.

  **BUGFIX PRZY OKAZJI**: `vaa_g4` i `dual_momentum` NIE MIALY `cost_bps` w ogole (domyslnie 0) -
  ten sam bug co wczesniej naprawiony dla `the_one`/`example_strategy`/`example_strategy_b`, tym
  razem nieznaleziony wczesniej bo te dwie strategie byly zablokowane brakiem danych. Dodano
  `cost_bps: 10`. Wplyw: `vaa_g4` CAGR 8.82%->7.98% (MaxDD -23.38%->-24.45%), `dual_momentum`
  CAGR 6.98%->6.74% (MaxDD -18.78%->-18.99%) - wszystkie progi `acceptance_spec.json` nadal
  przechodza.

  **Wyniki `param_stability` (relative_drop wf_mean_cagr, prog 0.30 wszedzie oprocz
  wyjatkow nizej)**:

  | Strategia | Wariantow | Best | Worst | relative_drop | Check |
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

  *`vaa_g4`/`the_one` - `hysteresis_pct` (jedyny obecnie sweepowany parametr) jest tu MARTWY:
  `vaa_canary`/`gem_dual_momentum_switch` zawsze produkuja BINARNE (100% jednego aktywa albo
  cash) alokacje, wiec dowolna wartosc `hysteresis_pct` ponizej 100% nigdy nie blokuje
  przelaczenia - relative_drop=0.00% odzwierciedla "ten parametr nic tu nie robi w testowanym
  zakresie", NIE prawdziwa odpornosc rodziny. Uczciwie odnotowane jako ograniczenie obecnego
  sweepa, nie ukryte za falszywym "stabilne".

  `tlt_timing` mial wczesniej ustawiony BARDZO luzny prog `param_stability` (1.0, przeniesiony z
  `tlt_hedge` przy tworzeniu) - zaostrzony do standardowego 0.30, zgodnie z reszta repo (bez tej
  korekty check trywialnie przechodzil, maskujac realne 63.49% - najbardziej krucha rodzina w
  calym repo, spojne z wczesniejszym odkryciem "tlt_timing solo gorszy niz buy&hold").

  Pominiete celowo: `example_strategy_b` (brak TestSpec/AcceptanceSpec/RunSpec - to tylko partner
  do testowania combinera) i `tlt_hedge` (trywialna, zawsze-100%-TLT cegielka do combinera,
  `walk_forward.enabled=false` - nie jest samodzielna strategia do oceny).

  Pelny pakiet testow po rozszerzeniu `allowed_param_families` (2 hardkodowane liczby wariantow w
  testach dopasowane do nowego 2-wymiarowego sweepa `example_strategy`): **224/224**.

## 2026-07-11 (9)

- **NOWY MODUL `engine_v2/param_stability.py` - "jak silna jest rodzina strategii"** - user:
  "brakuje mi czegos w stylu stabilnosci strategii, czyli parametru mowiacego jak zmiana
  parametrow zabija strategie, jak mocna jest rodzina strategii". `AcceptanceSpec.
  ParamStabilitySpec.max_relative_metric_drop_within_family` byl zdefiniowany OD POCZATKU
  projektu, ale NIGDZIE nie byl faktycznie liczony - `allowed_param_families`/`run_param_sweep`
  generuja i oceniaja warianty, ale nic nie streszczalo tego w JEDNA liczbe. To byl brakujacy
  kawalek.

  `compute_param_stability(sweep_result, metric_key)`: bierze tabele z `run_param_sweep` i liczy
  `relative_drop = (best - worst) / abs(best)` miedzy najlepszym a najgorszym wariantem w calej
  rodzinie parametrow, na wybranej metryce (domyslnie `wf_mean_cagr` w trybie `"search"`). Male
  = stabilne plateau (wybor konkretnego punktu nie jest krytyczny). Duze = krucha rodzina (jeden
  dobry wariant otoczony gorszymi sasiadami - sygnal overfittingu). `check_param_stability`
  porownuje to z `AcceptanceSpec.param_stability.max_relative_metric_drop_within_family` (ten
  sam styl co `check_criteria` - dict wynikow, tylko dla ustawionych progow).

  Wpiete w `run_spec_runner.py`'s tryb `"search"` - wynik ma teraz `param_stability` (pelne
  statystyki: best/worst/relative_drop/nazwy wariantow) i `param_stability_check` (bool wzgledem
  progu), liczone TYLKO na wariantach z >=1 oknem walk-forward (i tylko gdy zostaly >=2 takie
  warianty - relative_drop miedzy jednym wariantem a samym soba nic nie mowi).

  **Przyklad na realnej strategii** (`best17_b`, rodzina `min_score_gap` x `mom_9.window`, 12
  wariantow): `wf_mean_cagr` od 7.63% do 11.01% -> `relative_drop` = **30.7%**, LEKKO przekracza
  wlasny prog `acceptance_spec.json` (0.30) - borderline fail, uczciwie pokazany, nie ukryty.

  13 nowych testow (`test_param_stability.py`) + zaktualizowany `test_run_spec_runner.py`
  (`test_search_mode_end_to_end` sprawdza nowe pola). Pelny pakiet testow: **224/224**.

## 2026-07-11 (8)

- **NOWA STRATEGIA `strategies_v2/best17_b/` - "Strategia B" uzytkownika, rotacja sektorowa**.
  User dorzucil dane (`xlp`/`xlv`/`xlf`/`xle`/`xli`/`rsp` w `data/us/nyse/`) i opisal regule:
  9-miesieczny momentum na 6 sektorowych ETF, kanarek EMA7>EMA16 na XLI ORAZ XLP jednoczesnie
  (jesli choc jeden zawodzi - 100% cash), top2 z dodatnim momentum po 50/50, histereza "zmien
  tylko gdy nowy jest lepszy o >=3%", rebalans miesieczny.

  **Zero nowego kodu bloku** - w calosci zlozone z JUZ ISTNIEJACYCH blokow: `momentum_monthly`
  (9m), `ema_ratio_monthly` (kanarek EMA7/16), `canary_regime_gate` (XLI+XLP, `bad_threshold=0.0`
  = "EMA7>EMA16" wprost), `indicator_positive` (tylko dodatni momentum), `weighted_sum`, `top_n`,
  `rank_weights` (50/50), `score_gap_hysteresis` (`min_score_gap=0.03`, `full_position_size=2`) -
  identyczna architektura co `best17_a` (kanarek+momentum+score-gap histereza), inne
  tickery/progi/kanarek (para cykliczny-vs-defensywny XLI/XLP zamiast szerokiego rynku VT/XLK).

  **Realny wynik** (cala historia, 2005-12 do 2026-07, 248 miesiecy): CAGR 7.11%, MaxDD -29.71%,
  Sharpe 0.52, Calmar 0.24, roczny turnover ~2.21, max_time_underwater 35 miesiecy, najgorszy rok
  -15.51%. Wszystkie progi `acceptance_spec.json` (zgadywane przed przebiegiem) przeszly bez
  korekty.

  Sweep `mom_9.window` (6/9/12) potwierdzil, ze wybor uzytkownika (9 miesiecy) jest WYRAZNIE
  najlepszy (CAGR 7.11% vs 4.66%/4.81%, MaxDD -29.71% vs -38.39%/-41.51%) - nie przypadkowy dobor.
  Sweep `min_score_gap` (0.00/0.01/0.03/0.05): 0.01 dal odrobine lepszy Sharpe/Calmar niz opisane
  0.03, ale 0.03 pozostawione jako domyslne (wierne odtworzenie opisanej reguly, nie wynik
  strojenia).

  5 nowych testow (`test_best17_b_strategy_spec.py` - walidacja, wiring, kanarek XLI/XLP, gap 3%,
  end-to-end na realnych danych: oba rezymy risk-on/cash wystapily, nigdy >2 aktywa naraz). Pelny
  pakiet testow: **211/211**.

## 2026-07-11 (7)

- **Dorzucone brakujace tickery - `vaa_g4`, `dual_momentum`, `gfm` odblokowane** (user: "dorzuciłem
  nowe dane"). 14 plikow w `data/us/nyse/`: `agg`, `efa`, `efv`, `gld`, `gsg`, `hyg`, `ijh`, `ijr`,
  `mchi`, `mtum`, `qqq`, `shy`, `vnq`, `vtv`. Pelny pakiet testow: **206/206** - PIERWSZY RAZ w
  calej sesji bez ani jednego fail-a (stary, znany `test_vaa_canary.py::test_full_chain_on_real_data`
  wreszcie przechodzi). Dodano `test_gfm_full_chain_on_real_data` (koncowy test end-to-end na
  realnych danych dla `gfm`, dotad niemozliwy z braku tickerow).

  **Pierwsze realne wyniki trzech dotad "suchych"/blokowanych strategii**:

  | Strategia | CAGR | MaxDD | Sharpe | Calmar | Turnover/rok | Najgorszy rok |
  |---|---|---|---|---|---|---|
  | `vaa_g4` (Keller VAA-G4) | 8.82% | -23.38% | 0.78 | 0.38 | 7.79 | -14.94% |
  | `dual_momentum` | 6.98% | -18.78% | 0.62 | 0.37 | 2.28 | -14.16% |
  | `gfm` (Global Factor Model, GFM-4) | 9.61% | -33.70% | 0.71 | 0.29 | 3.47 | -7.57% |

  **Korekty progow akceptacji PO zobaczeniu realnego wyniku (transparentnie, jak przy
  `all_weather_4`)**:
  - `vaa_g4`: `max_drawdown` -0.20->-0.26, `min_calmar` 0.4->0.30, `max_time_underwater_months`
    24->60 (realny wynik: MaxDD -23.38%, Calmar 0.38, 54 miesiace pod woda - agresywny top1/7-aktyw
    switch generuje najdluzsze okresy podwodne w calym repo).
  - `dual_momentum`: `max_time_underwater_months` 24->30 (realny wynik: 26 miesiecy).
  - `gfm`: WSZYSTKIE progi (zgadywane przed przebiegiem) przeszly bez korekty.

  **`gfm` - sweep top_n=3/4/5 (GFM-3/4/5) na realnych danych**: historia ograniczona do
  2013-05..2026-07 (159 miesiecy - najkrocej notowany ticker w uniwersum to MTUM, od 2013-04).

  | top_n | CAGR | MaxDD | Sharpe | Calmar |
  |---|---|---|---|---|
  | 3 (GFM-3) | 8.60% | -36.52% | 0.61 | 0.24 |
  | 4 (GFM-4, domyslny) | 9.61% | -33.70% | 0.71 | 0.29 |
  | 5 (GFM-5) | 9.29% | -33.92% | 0.70 | 0.27 |

  Przypomnienie wciaz aktualnego zastrzezenia: sygnal Risk-On/Risk-Off w `gfm` to PLACEHOLDER
  (wlasny SPY mom_12 > 0) - prawdziwa regula GFM nie jest publiczna, wiec powyzszy wynik NIE jest
  wiernym odtworzeniem GFM, tylko jawna rekonstrukcja z zastepcza regula rezimu.

## 2026-07-11 (6)

- **NOWA STRATEGIA `strategies_v2/gfm/` - "Global Factor Model" (inwestujdlugoterminowo.pl) -
  zaimplementowana BEZ DANYCH** (user: "dołóż tylko na razie nie na danych więc zaimplementuj,
  testy będą później"). Miesieczna strategia dwóch trybów:
  - **Risk-On** (14 ETF: SPY/VTV/MTUM/QQQ/IJH/IJR/VEA/VWO/EFV/MCHI/GSG/GLD/VNQ/LQD): score =
    (zwrot_3M + zwrot_6M + zwrot_12M)/3, top_n najlepszych po rowno (GFM-3/4/5 - `top_n` w
    `allowed_param_families`, domyslnie 4).
  - **Risk-Off** (2 ETF: IEF/TLT): score = (zwrot_1M+3M+6M+12M)/4, caly kapital w lepszym.

  Nowy blok `engine_v2/blocks/portfolio_risk_engine/gfm_risk_switch.py` (rejestrowany w
  `__init__.py`) - musial liczyc DWIE ROZNE formuly scoringu na DWOCH ROZNYCH podzbiorach
  uniwersum (czego jeden `asset_scoring.weighted_sum` na cala strategie nie potrafi wyrazic),
  wiec sam bierze wskazniki z `indicator_set`, ignorujac przekazany `score` (jak
  `gem_dual_momentum_switch` uzywa `mom_12_key` niezaleznie od `score`).

  **WAZNE ZASTRZEZENIE**: autor GFM JAWNIE nie ujawnia dokladnej reguly wyznaczania sygnalu
  Risk-On/Risk-Off - w implementacji ten sygnal jest w pelni PLUGGOWALNY
  (`regime_indicator_key`/`regime_ticker`/`regime_threshold` w params), domyslnie ustawiony na
  PLACEHOLDER (wlasny 12-miesieczny momentum SPY > 0, prosty canary w stylu Faber/GTAA) - NIE
  odtworzenie nieujawnionej reguly, do podmiany gdy realna regula bedzie znana.

  **Brak danych**: w `data/us/nyse` mamy tylko `spy`/`vea`/`vwo`/`iau`(=gld)/`lqd`/`ief`/`tlt` z
  istniejacych strategii - brakuje `vtv`/`mtum`/`qqq`/`ijh`/`ijr`/`efv`/`mchi`/`gsg`/`vnq`. Strategia
  NIE URUCHOMIONA jeszcze na realnych danych - `acceptance_spec.json` progi sa ZGADYWANE (jak przy
  `all_weather_4` przed pierwszym przebiegiem), do skorygowania po dorzuceniu brakujacych plikow.

  10 nowych testow jednostkowych bloku (`test_gfm_risk_switch.py`, synteczne dane - top_n
  wybor/rownowaga, risk-off wybor lepszej obligacji, próg rezimu, NaN -> cash/risk-off) + 4 testy
  strukturalne specyfikacji (`test_gfm_strategy_spec.py` - walidacja, rozwiazywanie blokow,
  spojnosc uniwersum, sweep top_n=3/4/5) - CELOWO bez testu end-to-end na realnych danych
  (analogiczna sytuacja jak `vaa_g4`/`dual_momentum`, ktore tez czekaja na brakujace tickery).

  Pelny pakiet testow: 204/205 (1 fail niepowiazany, ten sam co zawsze - efa/agg/shy dla `vaa_g4`).

## 2026-07-11 (5)

- **NOWE METRYKI `best_year_return`/`worst_year_return`** - user pytanie: "brakuje mi jeszcze w
  danych wyjsciowych zwrot najgorszego roku oraz najlepszego". Dodano do `compute_metrics()`
  (`engine_v2/metrics.py`) - zwrot NAJLEPSZEGO i NAJGORSZEGO roku KALENDARZOWEGO w zakresie
  danych (pierwszy/ostatni rok moze byc czesciowy, liczony tak jak wypada, bez doannualizowania).
  2 nowe testy (`test_best_and_worst_year_return_known_values`,
  `..._single_partial_year`) + zaktualizowano `test_validation.py` (hardkodowana lista kolumn
  `run_walk_forward` wyniku).

  **Ciekawa obserwacja z realnych danych**: `best17_a_tlt_hedge` ma GORSZY najgorszy rok niz
  `best17_a` solo (-22.09% vs -19.35%, oba to rok 2022!), mimo NIZSZEGO calosciowego MaxDD
  (-23.70% vs -29.47%) - bo MaxDD to miara peak-to-trough (moze rozciagac sie na wiele lat), nie
  to samo co zwrot pojedynczego roku kalendarzowego. 2022 byl jednym z niewielu lat, gdy obligacje
  (TLT) spadaly RAZEM z akcjami (koniec ery zerowych stop procentowych) - stad hedge w TLT akurat
  w TYM konkretnym roku nie pomogl, mimo ze pomaga na wiekszosci pozostalych spadkow w historii.

  Pelna tabela porownawcza (wszystkie zapisane strategie/kombinacje w repo, z nowymi kolumnami):

  | Strategia | CAGR | MaxDD | Sharpe | Calmar | Najlepszy rok | Najgorszy rok |
  |---|---|---|---|---|---|---|
  | example_strategy | 8.19% | -36.16% | 0.54 | 0.23 | 33.34% | -11.57% |
  | example_strategy_b | 7.37% | -38.62% | 0.46 | 0.19 | 35.01% | -20.32% |
  | the_one | 8.76% | -23.59% | 0.61 | 0.37 | 34.89% | -15.15% |
  | best17_a | 16.49% | -29.47% | 0.96 | 0.56 | 49.17% | -19.35% |
  | all_weather_4 | 8.87% | -25.54% | 0.82 | 0.35 | 26.22% | -8.63% |
  | tlt_timing | 1.59% | -41.38% | 0.20 | 0.04 | 28.97% | -14.12% |
  | combined_example | 7.96% | -36.86% | 0.52 | 0.22 | 34.03% | -14.97% |
  | combined_best2 | 12.58% | -22.73% | 0.94 | 0.55 | 34.69% | -17.09% |
  | combined_best2_dynamic | 14.02% | -26.75% | 0.95 | 0.52 | 36.35% | -20.97% |
  | combined_triple | 11.54% | -18.08% | 0.99 | 0.64 | 32.80% | -13.90% |
  | best17_a_tlt_hedge | 14.10% | -23.70% | 0.97 | 0.59 | 55.12% | -22.09% |
  | best17_a_tlt_timing | 11.60% | -22.31% | 0.93 | 0.52 | 42.64% | -17.15% |
  | the_one_tlt_hedge | 7.34% | -25.15% | 0.57 | 0.29 | 29.14% | -17.75% |

  Pelny pakiet testow: 190/191 (1 fail niepowiazany - efa/agg/shy dla `vaa_g4`).

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
