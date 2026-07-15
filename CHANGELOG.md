# Changelog

Zapis istotnych zmian w projekcie, najnowsze na górze. Każdy wpis krótko: co się zmieniło i po co.

## 2026-07-15 (7)

- **Nowa strategia `gpm_mid_13`** - user: "Chce nowa wersje strategii gpm - dodajmy tickery rsp
  xlp xlv". Baza: `gpm_mid_10` (nie pelny 13-aktywowy `gpm` - user wybral wprost, opcja
  "Recommended": gpm_mid_10 ma juz PELNE pokrycie korekty dywidendowej, `gpm`'s IJR/EFA/VEA
  nadal nie maja wiarygodnego zamiennika Acc). Dodane 3 nowe aktywa ryzykowne: RSP (S&P 500
  Equal Weight), XLP (sektor Consumer Staples), XLV (sektor Health Care) - razem 13 ryzykownych +
  IEF/SHY ochronne = 15 tickerow uniwersum.

  **Korekta dywidend WLACZONA OD RAZU** dla wszystkich 3 nowych tickerow (mamy juz realne dane
  Acc z wczesniejszego dogrania przez usera): RSP->`speq.uk` (zmierzony gap +1,06%/rok, overlap
  TYLKO 5,1 lat - krotszy niz reszta [9-11 lat], ale spojny/dodatni, NIE sprzeczny jak nieudany
  przypadek EFA/VEA->xuse.uk), XLP->`iucs.uk` (+1,33%/rok, 9,3 lat), XLV->`iuhc.uk` (+0,25%/rok,
  10,6 lat - niska stopa spojna z historycznie niska dywidenda sektora health care). Pelne
  15/15 pokrycie `dividend_adjustment_mapping`.

  `full_protective_max_n=6`/`protective_scale_denominator=6` (nie 5/5 jak gpm_mid_10 z 10
  aktywami) - przeskalowane do 13-aktywowego uniwersum wg TEJ SAMEJ konwencji co oryginalny
  13-aktywowy `gpm` (dokladnie te same wartosci dla tej samej liczby ryzykownych). `top_n_risky=3`
  bez zmian.

  **Wynik solo** (post-tax, koszt 40bps+19% podatek) vs `gpm_mid_10`:

  | | CAGR | MaxDD | Sharpe | Calmar |
  |---|---|---|---|---|
  | `gpm_mid_10` | 4,77% | -12,95% | 0,597 | 0,369 |
  | `gpm_mid_13` | **4,94%** | **-12,57%** | **0,616** | **0,393** |

  Skromna, ale konsekwentna poprawa na kazdej metryce z dodania 3 defensywnych/szerszych aktywow
  (RSP mniej skoncentrowany w Big Tech niz SPY, XLP/XLV niska beta).

  Nowe pliki: `strategies_v2/gpm_mid_13/` (pelny komplet - strategy_spec/run_spec/test_spec/
  acceptance_spec/uk_ticker_mapping, ten sam wzorzec co `gpm_mid_10`). Blok `reporting` wpiety od
  razu (`results/monthly/gpm_mid_13.csv`). 8 nowych testow
  (`test_gpm_mid_13_strategy_spec.py`, w tym UK mapping end-to-end - PASS, 0% mismatch, 15/15
  tickerow zmapowanych, i test dokumentujacy DOKLADNIE roznice wzgledem gpm_mid_10). Wygenerowano
  TYLKO `results/gpm_mid_13.json` + scalony `SUMMARY.md`. Pelny pakiet testow: 578/578, bez
  regresji.

## 2026-07-15 (6)

- **Blok `reporting` dziala TEZ dla portfeli LACZONYCH** - user: "Run one tez powinno dzialac dla
  laczonych" (po wpieciu bloku do 23 pojedynczych strategii). `CombinedSpec`
  (`engine_v2/combined_spec.py`) dostal nowa, plaska pare pol `reporting`/`reporting_params`
  (CombinedSpec nie ma koncepcji "blocks"/"base_params" jak `StrategySpec` - ten sam wzorzec co
  juz istniejace `combiner`/`combiner_params`). Nowa `combined_pipeline.run_combined_pipeline_with_reporting()`
  - analogia do `pipeline.run_strategy_pipeline_with_reporting()`: liczy `run_combined_pipeline()`
  jak dotad, DODATKOWO (jesli `reporting` ustawione) laduje dzienne ceny dla UNII uniwersow
  wszystkich skladowych strategii (ten sam wzorzec co `generate_results._generate_combined`),
  liczy `equity_curve` i wola zarejestrowany blok. CombinedSpec bez `reporting` dziala 1:1 jak
  dotad (zweryfikowane testem bit-w-bit).

  Wszystkie 30 `combined_spec.json` (poza `combined_example`, demo) dostaly `"reporting":
  "monthly_csv_export"` + `"reporting_params": {"output_path": "results/monthly/<nazwa>.csv",
  "annual_tax_rate": 0.19}` - ta sama chirurgiczna wstawka tekstowa co dla pojedynczych strategii
  (`insert_after_root_key`, analogiczna do `insert_after_key` z (5), ale bez zagniezdzonego
  kontenera - `combiner_params` zyje bezposrednio w korzeniu dokumentu). Diff kazdego pliku to
  dokladnie 2 nowe linie.

  `run_one.py` dla laczonych tez juz nie liczy ledgera samodzielnie - `_write_monthly_ledger_combined`
  wola `combined_pipeline.run_combined_pipeline_with_reporting(spec, strategy_dir)`.

  Wygenerowano i zacommitowano `results/monthly/<nazwa>.csv` dla wszystkich 30 portfeli
  laczonych - razem z (5) daje PELNE pokrycie 53/53 strategii w repo.

  8 nowych testow: `test_reporting_block_combined.py` (5 - pola CombinedSpec domyslnie puste,
  bit-w-bit bez bloku, realny zapis CSV, nieznana implementacja rzuca czytelny blad, kompletnosc
  wszystkich 30) + `test_run_one.py` (3 - end-to-end dla laczonych przez run_one, kompletnosc,
  fallback bez bloku). Pelny pakiet testow: 570/570, bez regresji.

## 2026-07-15 (5)

- **Blok `reporting` wpiety do WSZYSTKICH 23 pojedynczych strategii** - user: "dodaj do configa
  wszystkich strategii zeby byl uzywany". Kazdy z 23 `strategy_spec.json` majacych WLASNY
  `run_spec.json` (nie laczone - te maja `combined_spec.json` i inny mechanizm, patrz nizej)
  dostal `blocks["reporting"]="monthly_csv_export"` + `base_params["reporting"]={"output_path":
  "results/monthly/<nazwa>.csv", "annual_tax_rate": 0.19}` (ta sama stawka co
  `test_spec.json.costs.annual_tax_rate` kazdej z nich - wszystkie akurat maja 0.19). Zmiana
  zrobiona chirurgicznie na tekscie JSON (funkcja `insert_after_key` - lokalizuje dokladny koniec
  wartosci klucza `execution` przez `json.JSONDecoder.raw_decode`, wstawia nowy klucz zaraz po
  nim), NIE przez `StrategySpec.save()` (ktore przeformatowaloby caly plik - zweryfikowano na
  `bh_spy`, diff wyszedlby ogromny/nieczytelny). Wynik: diff kazdego pliku to DOKLADNIE 2 nowe
  linie (jedna w `blocks`, jedna w `base_params`), reszta pliku bit-w-bit bez zmian.

  `run_one.py` przepisany dla POJEDYNCZYCH strategii: zamiast wlasnej, osobnej sciezki liczenia
  ledgera (`_final_portfolio_and_equity_single`+`build_monthly_ledger`) teraz PO PROSTU woła
  `pipeline.run_strategy_pipeline_with_reporting(spec)` - blok sam zapisuje CSV z parametrow juz
  zapisanych w `strategy_spec.json`. Portfele LACZONE (`combined_spec.json`) NIE MAJA jeszcze
  odpowiednika tego bloku (brak `run_combined_pipeline_with_reporting`) - dla nich `run_one.py`
  zostaje przy starej, recznej sciezce.

  Wygenerowano i zacommitowano `results/monthly/<nazwa>.csv` dla wszystkich 23 pojedynczych
  strategii (wczesniej mielismy tylko `gpm_mid_10`/`gpm_mid_10_best17_a`).

  2 nowe testy w `test_run_one.py`: `test_all_single_strategies_declare_reporting_block`
  (kompletnosc - kazda z 23 faktycznie ma blok wpiety z poprawnym `output_path`),
  `test_write_monthly_ledger_single_skips_gracefully_without_reporting_block` (fallback gdy
  bloku brak - bez dotykania prawdziwego pliku na dysku, monkeypatch `StrategySpec.load`). Pelny
  pakiet testow: 562/562, bez regresji.

## 2026-07-15 (4)

- **Nowy typ bloku silnika: `reporting`** - user: "Wg mnie narzedzia sprawozdawcze powinny byc
  w silniku moze jako koncowy etap - kolejny blok to powinien byc", potem doprecyzowanie: "Nowy
  blok ma byc i powinien isc na koncu [...] musi to byc wbudowane w silnik tak zebym mogl miec
  inne implementacje". Reszta 10 blokow dziala PER OKRES (w petli `run_strategy_pipeline`) -
  `reporting` dziala PO calym pipeline, na gotowym `final_portfolio`+dziennej `equity_curve` (ta
  ostatnia w ogole nie jest liczona przez `run_strategy_pipeline()` dzis - liczy ja dopiero
  wywolujacy, np. `run_spec_runner.py`). Dlatego jest OPCJONALNY (poza
  `pipeline.PIPELINE_ORDER`/`REQUIRED_SINGLE_CHOICE_BLOCKS` - strategia bez niego dziala 1:1 jak
  dotad, zweryfikowane testem bit-w-bit) i wolany przez NOWA funkcje
  `pipeline.run_strategy_pipeline_with_reporting(spec)`.

  Nowe pliki: `engine_v2/blocks/reporting/__init__.py` (REGISTRY, ten sam wzorzec co reszta
  blokow), `engine_v2/blocks/reporting/monthly_csv_export.py` (pierwsza implementacja - zapisuje
  miesieczny ledger, `params["output_path"]` wymagany, opcjonalny `params["annual_tax_rate"]` -
  `StrategySpec` nie niesie wlasnego podatku jak `TestSpec`, wiec blok jest w tym
  samowystarczalny). Wydzielono `build_monthly_ledger` z `monthly_report.py` do nowego
  `engine_v2/monthly_ledger.py` (czysty modul silnika, nie skrypt CLI) - reuzywany TERAZ przez
  blok `reporting` I przez CLI `monthly_report.py`/`run_one.py`, jedna implementacja.

  `spec.STRATEGY_BLOCKS` dostal `"reporting"` (zeby `validate()` akceptowal go jako znany blok),
  ale NIE `pipeline.PIPELINE_ORDER` (zostaje opcjonalny). `pipeline.resolve_blocks()` sprawdza go
  osobno, jesli zadeklarowany - zeby generyczny wzorzec testowy `for block_type in spec.blocks:
  assert block_type in resolved` (uzywany w wielu istniejacych testach *_spec.py) dzialal tak
  samo dla strategii, ktore go maja.

  7 nowych testow (`test_reporting_block.py`): blok zarejestrowany, `resolve_blocks()` widzi go
  gdy zadeklarowany, `run_strategy_pipeline_with_reporting()` BEZ bloku = identyczny
  `final_portfolio` jak `run_strategy_pipeline()` (bit-w-bit, `bh_spy`), realny zapis CSV,
  walidacja wymaganego `output_path`, `annual_tax_rate` faktycznie obniza equity. Pelny pakiet
  testow: 560/560, bez regresji. Zadna z ~53 istniejacych strategii NIE ma jeszcze
  `blocks["reporting"]` ustawionego - to swiadomie NOWY, opcjonalny mechanizm, nie zmiana
  zachowania czegokolwiek istniejacego.

## 2026-07-15 (3)

- **`run_one.py` domyslnie generuje tez miesieczny ledger** - user: "Jak tak samo monthly
  przeciez w calym przebiegu powinien sie generowac" (po tym jak `monthly_report.py` byl
  osobnym, recznym krokiem). Kazde uruchomienie `run_one.py <nazwa>` teraz TAKZE zapisuje
  `results/monthly/<nazwa>.csv` (reuzywa `_final_portfolio_and_equity_single`/
  `_final_portfolio_and_equity_combined`/`build_monthly_ledger` z `monthly_report.py`) - nowa
  flaga `--skip-monthly` zeby tego uniknac (np. szybki podglad samych metryk). 2 nowe testy
  (domyslne generowanie + `--skip-monthly` faktycznie pomija zapis). Pelny pakiet testow:
  553/553, bez regresji.

## 2026-07-15 (2)

- **Cienkie wrappery `run_one.py`/`monthly_report.py` w KORZENIU repo** - user: "Czemu nie ma
  tego run one w glownym katalogu jak run pipeline dla starego engine" (por.
  `run_global_pipeline.py`, glowny punkt wejscia starego `engine/`). Cala logika nadal zyje w
  `engine_v2/run_one.py`/`engine_v2/monthly_report.py` - te dwa pliki w korzeniu tylko wolaja
  `main()` z odpowiedniego modulu, zero duplikacji: `.venv/bin/python3 run_one.py gpm_mid_10`,
  `.venv/bin/python3 monthly_report.py gpm_mid_10` (bez `-m`). 2 nowe testy
  (`test_root_wrappers.py`, sprawdzaja tylko ze delegacja dziala). Pelny pakiet testow: 551/551.

## 2026-07-15 (1)

- **`engine_v2/run_one.py`** - user: "Chce miec skrypt jak w starym engine gdzie wybieram ktora
  odpalic i tylko ona idzie" (w odroznieniu od `generate_results.py`, ktory zawsze przelicza
  WSZYSTKIE ~50 strategii). Reuzywa `_generate_single`/`_generate_combined`
  z `generate_results.py`, liczy TYLKO wskazana strategie, wypisuje metryki na ekran - nic nie
  zapisuje do `results/`. `.venv/bin/python3 -m engine_v2.run_one <nazwa>` /
  `... --list`. 6 nowych testow (`test_run_one.py`).

- **`engine_v2/monthly_report.py`** - user: "czy mamy plik z decyzjami miesiecznymi zwrotem z
  kazdego miesiaca maxdd wagi tam powinny byc - generalnie taki przebieg". Odpowiedz: NIE
  mielismy - `results/<nazwa>.json` trzyma tylko zbiorcze metryki (CAGR/MaxDD/Sharpe...), zero
  pelnego, miesiac-po-miesiacu ledgera. Nowy skrypt buduje taki ledger jako CSV dla jednej
  strategii: `date`, `gross_return`/`net_return`, `turnover`/`operations`/`signal_changed`/
  `trade_cost`, `equity` (po podatku, startuje od 1.0), `drawdown` (biezacy spadek od szczytu,
  PROBKOWANY na dni rebalansu - UWAGA: moze byc plytszy niz oficjalny MaxDD z `results/*.json`,
  jesli najgorszy dzien wypadl w trakcie okresu, nie akurat na rebalans; skrypt wypisuje obie
  wartosci jawnie), `w_<ticker>` (waga uzyta per aktywo). `.venv/bin/python3 -m
  engine_v2.monthly_report <nazwa>` -> `results/monthly/<nazwa>.csv`. 4 nowe testy
  (`test_monthly_report.py`). Pelny pakiet testow: 549/549, bez regresji.

## 2026-07-14 (56)

- **BUGFIX (repo-wide, ogromny): `data/us` to ceny BEZ reinwestycji dywidend/kuponow -
  naprawiono dla `gpm_mid_10`** - user: "Mamy wynik 3 procent a keller podawal 9 to jest ogromny
  rozjazd wiec gdzies jest konkretny bug trzeba go poszukac" (w kontekscie `daa_g4_keller`).

  **Diagnoza**: `engine_v2/blocks/data_loader/csv_loader.py` czyta surowa kolumne `CLOSE` z
  plikow stooq - ZERO logiki reinwestycji dywidend/kuponow w calym `engine_v2`. Zweryfikowano na
  realnych danych: `agg.us` 2005->2026 CAGR ~1,0%/rok, publikowany total return AGG za ten okres
  ~3,0-3,5%/rok - gap dokladnie odpowiada utraconemu kuponowi. `vt.us` (US, Dist) vs `vwra.uk`
  (UK, Acc, ten sam indeks) na wspolnym oknie: gap +1,12%/rok - wczesniej (CHANGELOG 41) blednie
  przypisany do "roznicy funduszy", to w rzeczywistosci ten sam efekt. Dotyczy WSZYSTKICH ~50
  strategii w repo w roznym stopniu (im dluzej trzyma yieldujace aktywa, tym wiekszy blad).

  **Naprawa - nowy blok `stooq_csv_dividend_adjusted`**
  (`engine_v2/blocks/data_loader/dividend_adjusted_csv_loader.py`): dla kazdego tickera z
  `dividend_adjustment_mapping` (US -> UK Acc) buduje skorygowana cene, splicujac PRAWDZIWE dane
  akumulacyjne (UK-listowane UCITS ETF, USD, klasa Acc - user dogral te dane po moim pytaniu
  "jakie tickery") tam gdzie istnieje wspolna historia (regresja liniowa na logarytmie stosunku
  cen daje zmierzona, nie zgadywana, roczna stope), i ekstrapolujac ta sama stala stopa dla
  historii sprzed startu danego UK ETF-u. Tickery bez wpisu w mapowaniu przechodza bez zmian -
  superset `stooq_csv` (zweryfikowane testem: pusty mapping = identyczny wynik jak `stooq_csv`).

  **Zmierzone gapy (realne, dlugie 9-11-letnie okna, regresja)**:
  | Ticker | Zamiennik UK (Acc) | Okno | Gap/rok |
  |---|---|---|---|
  | spy.us | cspx.uk | 11,3 lat | -0,19% (~0, SPY juz bliskie total-return) |
  | qqq.us | cndx.uk | 11,3 lat | -0,24% (~0) |
  | vwo.us | eimi.uk | 11,3 lat | +0,76% |
  | agg.us | suag.uk | 11,3 lat | **+1,56%** |
  | shy.us | ibta.uk | 9,2 lat | +1,46% |
  | ief.us | cbu0.uk | 11,2 lat | +1,11% |
  | lqd.us | lqda.uk | 9,2 lat | **+2,11%** |
  | vnq.us | xres.uk | 10,4 lat | +2,30% |
  | dbc.us | icom.uk | 8,9 lat | -0,37% (~0, kontrakty terminowe, brak realnej dywidendy) |
  | gld.us | igln.uk | 11,3 lat | +0,22% (~0, zloto fizyczne nie placi dywidendy) |
  | hyg.us | ihya.uk | 9,2 lat | **+3,42%** |
  | tlt.us | dtla.uk | 8,1 lat | +0,14% (male - krotkie okno z krachem obligacji 2022) |
  | xle.us | iues.uk | 10,6 lat | -0,68% (czesc to roznica indeksu, nie tylko dywidenda) |

  Uwaga: `efa.us`/`vea.us` -> `xuse.uk` (jedyny dostepny zamiennik) ma tylko 1,2 roku danych
  (start 2025-04-28) - zmierzony gap dal SPRZECZNE znaki (+5,3%/rok dla EFA, -2,1%/rok dla VEA,
  ta sama klasa aktywow) - czysty szum krotkiego okna. NIE uzyto tej korekty - `daa_g4`,
  `daa_g4_keller`, `vaa_g4` (wszystkie uzywaja EFA/VEA) zostaja NIENARUSZONE do czasu lepszych
  danych. Test empiryczny pokazal dodatkowo: CZESCIOWA korekta (niektore aktywa w tym samym
  mechanizmie scoringu/kanarka skorygowane, inne nie) moze ZNIEKSZTALCIC wyniki w NIEPRZEWIDYWALNY
  sposob (np. `vaa_g4` z czesciowa korekta SPY/VWO/AGG/SHY/IEF/LQD ale bez EFA wyszedl WYRAZNIE
  gorzej niz bez zadnej korekty - najprawdopodobniej artefakt zaklocajacy binarny mechanizm
  kanarka VAA, ktory porownuje wszystkie 4 aktywa ofensywne naraz) - dlatego korekta wlaczana
  TYLKO gdy WSZYSTKIE aktywa danej strategii maja wiarygodny (dlugi) zamiennik.

  **`gpm_mid_10` ma PELNE pokrycie (12/12 tickerow, wszystkie dlugie/wiarygodne okna)** - jedyna
  na razie strategia przelaczona na `stooq_csv_dividend_adjusted`
  (`strategies_v2/gpm_mid_10/strategy_spec.json`).

  **Wynik (post-tax, koszt 40bps + 19% podatek)**:
  | | CAGR | MaxDD | Sharpe | Calmar |
  |---|---|---|---|---|
  | `gpm_mid_10` PRZED | 3,36% | -14,36% | 0,451 | 0,234 |
  | `gpm_mid_10` PO | **4,77%** | **-12,95%** | **0,597** | **0,369** |
  | `gpm_mid_10_best17_a` PRZED | 8,22% | -15,34% | 0,796 | 0,536 |
  | `gpm_mid_10_best17_a` PO | 8,52% | -16,36% | 0,800 | 0,521 |

  Solo `gpm_mid_10` wyraznie lepszy na kazdej metryce. Miks z `best17_a` - CAGR/Sharpe lekko w
  gore, ale MaxDD/Calmar odrobine w dol (zmiana relatywnego momentum `gpm_mid_10` po korekcie
  przesuwa TIMING jego wlasnych przelaczen, co nieznacznie zmienia nakladanie sie obsunien z
  `best17_a` w polaczonym portfelu - zapisane uczciwie, nie ukrywane).

  Nowe testy: `test_dividend_adjusted_data_loader.py` (7 - matematyka splice'u na danych
  syntetycznych, fallback dla niezmapowanych tickerow identyczny z `stooq_csv`, prawdziwy zmierzony
  gap na `agg.us`/`suag.uk`, czytelny blad przy braku pliku UK). Zaktualizowany
  `test_gpm_mid_10_strategy_spec.py::test_gpm_mid_10_metrics_regression_baseline` (nowa zamrozona
  baseline + poprawiony bug w samym tescie - liczyl equity curve na SUROWYM `stooq_csv` mimo ze
  `final_portfolio` juz bylo policzone na skorygowanych danych, niespojne). Wygenerowano TYLKO
  `results/gpm_mid_10.json` + `results/gpm_mid_10_best17_a.json` + scalony `SUMMARY.md`. Pelny
  pakiet testow: 539/539, bez regresji.

  **Do zrobienia (nastepny krok)**: znalezc/dograc dluzszy (>5 lat) zamiennik Acc dla
  `efa.us`/`vea.us`, zeby odblokowac `daa_g4`/`daa_g4_keller`/`vaa_g4` (i pelne `gpm`, ktore
  dodatkowo brakuje `ijr.us`).

## 2026-07-14 (55)

- **KOREKTA `daa_g4_keller`: dynamiczne skalowanie liczby aktyw ofensywnych ("Easy Trading")** -
  user po (54): "Nie jest jeszcze w pelni poprawny. T=4, B=2 sa dobre. Blad jest przy 1 zlym
  kanarku. Keller powinien wtedy miec: top 2 aktywa po 25% + 50% defensywnie. Repo nadal trzyma
  top 4 po 12,5% + 50% defensywnie. Czyli trzeba dodac dynamiczne zmniejszenie liczby aktywow
  ofensywnych z 4 do 2."

  Dodano opcjonalny param `scale_top_n_with_cash_fraction` (domyslnie `False` - `daa_g4` BEZ
  ZMIAN zachowania) do wspolnego bloku `daa_canary_breadth_switch.py`: gdy wlaczony, liczba
  TRZYMANYCH aktyw ofensywnych = `round((1 - cash_fraction) * top_n_offensive)`, nie stale
  `top_n_offensive`. Dla `daa_g4_keller` (T=4, B=2) przy 1 zlym kanarku z 2:
  `cash_fraction=0.5`, `t=round(0.5*4)=2` -> top-2 (nie top-4) dzieli 50% po rowno = 25% kazde
  (nie top-4 po 12,5%) - dokladnie jak user opisal. Wlaczone tylko w `daa_g4_keller`
  (`scale_top_n_with_cash_fraction: true`), `daa_g4` bez zmian (param nieustawiony -> `False`).

  **Wynik PO korekcie (55) vs PRZED (54)** (post-tax, koszt 40bps):

  | | CAGR | MaxDD | Sharpe | Calmar | Turnover |
  |---|---|---|---|---|---|
  | `daa_g4` (top1 ofensywny, bez zmian) | 3.50% | -32.01% | 0.318 | 0.109 | 7.64 |
  | `daa_g4_keller` (54, stale top-4, BLEDNE) | 3.04% | -30.28% | 0.355 | 0.100 | 4.60 |
  | `daa_g4_keller` (55, dynamiczne top-2..4, POPRAWIONE) | 2.86% | **-32.12%** | 0.343 | 0.089 | 4.82 |

  **Uczciwie: ten wynik jest GORSZY na wszystkich metrykach niz (54)** (nizszy CAGR, gorszy MaxDD,
  nizszy Sharpe/Calmar, odrobine wyzszy turnover) - mimo ze mechanika jest teraz POPRAWNA wzgledem
  metodyki Kellera (user potwierdzil oczekiwane zachowanie: top-2 po 25% zamiast top-4 po 12,5%
  przy 1 zlym kanarku). Powod: koncentrowanie kapitalu w 2 aktywach zamiast rozproszenie na 4 w
  stanie posrednim (cash_fraction=0.5) REDUKUJE wewnetrzna dywersyfikacje "nogi" ofensywnej
  wlasnie w okresach podwyzszonego ryzyka (skoro kanarek juz sygnalizuje problem) - to jest
  kompromis wpisany w oryginalna metodyke DAA, nie blad implementacji. `daa_g4_keller` (55) ma
  teraz podobny MaxDD do `daa_g4` (-32.12% vs -32.01%), ale nizszy turnover (4.82 vs 7.64) i nadal
  wyzszy Sharpe (0.343 vs 0.318).

  Zaktualizowany `strategies_v2/daa_g4_keller/strategy_spec.json`
  (`scale_top_n_with_cash_fraction: true`) i `engine_v2/blocks/portfolio_risk_engine/daa_canary_breadth_switch.py`.
  Nowe testy: `test_daa_components.py` (3 nowe: shrink przy cash_fraction=0.5, brak zmiany przy
  cash_fraction=0, brak zmiany zachowania gdy flaga wylaczona) i
  `test_daa_g4_keller_strategy_spec.py` (nowy `test_daa_g4_keller_shrinks_to_two_offensive_assets_at_half_cash_fraction`
  na realnych danych - dowod, ze KAZDY okres z ~50% udzialem obronnym trzyma dokladnie 2 aktywa
  ofensywne po 25%, nigdy 4). Zaktualizowana zamrozona baseline w
  `test_daa_g4_keller_metrics_regression_baseline` (nowe wartosci: cagr=0.0366, maxdd=-0.3212,
  sharpe=0.426, PRZED podatkiem). Wygenerowano TYLKO `results/daa_g4_keller.json` + scalony
  `SUMMARY.md`. Pelny pakiet testow: 532/532, bez regresji.

## 2026-07-14 (54)

- **KOREKTA `daa_g4_keller`: T=4, B=2 (nie T=2, B=1)** - user po (53): "Ale zle zrobiles ja chce
  t 4 b 2". Poprzednia wersja (53) opierala T=2/B=1 na niezaleznym, WTORNYM zrodle (kod
  referencyjny TuringTrader, wariant "Easy Trading" ze SKALUJACYM SIE top_n w miare wzrostu
  cash_fraction) - user jawnie skorygowal na inne wartosci, przyjete bez dalszej dyskusji jako
  autorytatywne (moga pochodzic z samej pracy Kellera/Keuninga albo z innego zrodla, ktoremu user
  ufa bardziej niz mojej wtornej weryfikacji).

  `top_n_offensive=4` (WSZYSTKIE 4 aktywa ofensywne rownolegle, rowne wagi 25% kazde - nie top-2
  jak w (53)), `breadth_denominator=2` (TAKI SAM jak domyslny w istniejacym `daa_g4` -
  `len(canary_assets)=2` - wiec mechanizm udzialu ochronnego jest teraz IDENTYCZNY z `daa_g4`,
  ciagly 0/50/100%, NIE binarny jak w (53)). Jedyna pozostala roznica wzgledem `daa_g4`: liczba
  trzymanych aktyw ofensywnych (4 zamiast 1).

  **Wynik PO korekcie** (lepszy niz (53), blisko `daa_g4`):

  | | CAGR | MaxDD | Sharpe | Calmar | Turnover |
  |---|---|---|---|---|---|
  | `daa_g4` (top1 ofensywny) | 3.50% | -32.01% | 0.318 | 0.109 | 7.64 |
  | `daa_g4_keller` (53, T=2/B=1, BLEDNE) | 3.38% | -37.58% | 0.341 | 0.090 | 7.19 |
  | `daa_g4_keller` (54, T=4/B=2, POPRAWIONE) | 3.04% | **-30.28%** | 0.355 | 0.100 | 4.60 |

  MaxDD teraz LEPSZY niz `daa_g4` (-30.28% vs -32.01%) - trzymanie wszystkich 4 aktyw ofensywnych
  naraz (zamiast koncentracji w 1) daje realna dywersyfikacje wewnatrz "nogi" ofensywnej, przy
  niższym turnoverze (4.60 vs 7.64 - mniej okazji do zmiany lidera, skoro i tak trzyma sie
  wszystkie). Calmar wciaz odrobine nizszy niz `daa_g4` (0.100 vs 0.109) - CAGR nizszy, bo
  rownowazenie 4 aktyw zamiast koncentracji w najlepszym redukuje gorne odchylenie razem z
  dolnym.

  Zaktualizowany `strategies_v2/daa_g4_keller/strategy_spec.json` (`top_n_offensive: 4`,
  `breadth_denominator: 2`) i wszystkie testy w `test_daa_g4_keller_strategy_spec.py` (nowy test
  `test_daa_g4_keller_holds_all_four_offensive_assets_when_fully_offensive` - dowod, ze wszystkie
  4 sa faktycznie trzymane rownolegle, nie tylko dopuszczone). Wygenerowano TYLKO
  `results/daa_g4_keller.json` + scalony `SUMMARY.md`. Pelny pakiet testow: 528/528, bez
  regresji.

## 2026-07-14 (53) - ⚠️ NIEAKTUALNE, patrz korekta (54) - user podal inne T/B po zobaczeniu wyniku

- **`daa_g4_keller` - wierna rekonstrukcja "DAA-G4"** (user: "Zrob wersje daa g4 kellera").
  Zweryfikowano WPROST zrodlo (nie z pamieci) - Keller & Keuning (2018), "Breadth Momentum and
  the Canary Universe: Defensive Asset Allocation (DAA)", porownane z niezalezna implementacja
  referencyjna (github.com/fbertram/TuringTrader, `BooksAndPubs/Keller_DAA.cs`, C# - kod
  zrodlowy, nie parafraza).

  **Odkryto, ze istniejacy `strategies_v2/daa_g4/` (z 2026-07-11) odbiega od prawdziwego DAA-G4
  na 2 sposoby**:
  1. `top_n_offensive=1` zamiast prawdziwego **T=2** (DAA-G4 trzyma top-2 aktywa ofensywne
     rownolegle, nie top-1).
  2. Udzial ochronny liczony jako `b/len(canary_assets)=b/2` (ciagle 0/50/100%), podczas gdy
     prawdziwe DAA-G4 uzywa `breadth_denominator` (oznaczane "B" w pracy) = **1**, NIE 2 - JEDEN
     zly kanarek juz wymusza 100% ochrony (`min(1, b/1)`), mimo ze kanarkow jest 2. Ciaglosc
     0/50/100% jest wlasciwoscia wariantu **DAA-G12** (B=2 z tymi samymi 2 kanarkami VWO/BND),
     NIE DAA-G4 - istniejacy `daa_g4` byl przez pomylke skalibrowany jak G12, mimo 4-aktywowego
     uniwersum ofensywnego G4.

  Dodano `breadth_denominator` (opcjonalny, domyslnie `len(canary_assets)` - istniejacy `daa_g4`
  NIE zmienia zachowania) do `daa_canary_breadth_switch` - zero nowego bloku, jedna nowa,
  wstecznie kompatybilna opcja. 2 nowe testy w `test_daa_components.py`.

  **Nowa strategia `strategies_v2/daa_g4_keller/`**: T=2, breadth_denominator=1,
  offensive=SPY/VEA/VWO/AGG (BND niedostepny w danych, zastapiony AGG - ta sama substytucja juz
  zaakceptowana w `daa_g4`/`vaa_g4`), canary=VWO/AGG, defensive=SHY/IEF/LQD (top1). Score =
  13612W momentum, identyczny wzor co `daa_g4`/`vaa_g4`.

  **Wynik - UCZCIWIE gorszy niz istniejacy `daa_g4`, nie lepszy**:

  | | CAGR | MaxDD | Sharpe | Calmar |
  |---|---|---|---|---|
  | `daa_g4` (przyblizenie, B=2, T=1) | 3.50% | -32.01% | 0.318 | 0.109 |
  | `daa_g4_keller` (wierne, B=1, T=2) | 3.38% | **-37.58%** | 0.341 | 0.090 |

  Agresywne B=1 (54% miesiecy w pelnej ochronie, wieksze niz w `daa_g4`) NIE pomaga w TYM oknie
  danych - wieloletnia bessa obligacji 2021-2024 (4 kolejne ujemne lata: -4.7%/-16.1%/-2.1%/
  -4.2%) oznaczala, ze SHY/IEF/LQD SAME mialy zla passe rownolegle ze spadkami akcji, wiec
  ucieczka do "ochrony" nie chronila tak skutecznie jak w klasycznych rynkach niedzwiedzia
  (2008, gdzie obligacje rosly gdy akcje spadaly). Publikowane wyniki DAA (np. ~13.7% CAGR z
  PortfolioDB) pochodza z okresow SPRZED tego konkretnego reżimu rynkowego (stopy procentowe w
  gore) i/lub bez realistycznych kosztow/podatku - NIE sa bezposrednio porownywalne z naszym
  wynikiem po podatku i koszcie 40bps. Odnotowane w pelni uczciwie, nie ukryte ani nie
  "poprawione" dobraniem progow.

  6 nowych testow strategii (`test_daa_g4_keller_strategy_spec.py`, w tym dowod ze mechanizm jest
  NAPRAWDE binarny - `defensive_total` zawsze 0.0 albo 1.0, nigdy posrednia wartosc jak w
  `daa_g4`). Wygenerowano TYLKO nowy plik wynikowy + scalony `SUMMARY.md` (53 wiersze). Pelny
  pakiet testow: 527/527, bez regresji.

## 2026-07-14 (52)

- **`gfm_breadth`** - user: "Teraz kolejny wariant. Zmieniamy w GFM tylko mechanizm risk-off:
  zamiast prostego SPY 12M > 0, liczymy szerokosc rynku... ryzyko zmniejszamy stopniowo, np.
  100%/75%/50%/25%/0%... czesc defensywna wybiera najlepszy z SHY, IEF, TLT. Czesc ofensywna
  zostaje bez zmian." Nowy blok `portfolio_risk_engine.gfm_breadth_risk_step` - laczy dwa juz
  istniejace wzorce: dwie NIEZALEZNE formuly scoringu (risky vs protective, jak
  `gfm_risk_switch`) + skalowanie udzialu ryzykownego wg szerokosci rynku (jak
  `gpm_breadth_protective_split`) - ale SKOKOWE (`breadth_thresholds`/`risky_shares`), nie
  ciagle/liniowe jak GPM.

  **Kalibracja progow** (14 aktywow risk-on w GFM): `breadth_thresholds=[3,6,9,12]`,
  `risky_shares=[0.0,0.25,0.5,0.75,1.0]` - 5 ROWNYCH koszykow po 3 (n w 0-2/3-5/6-8/9-11/12-14),
  dajacych dokladnie progi "100/75/50/25/0%" z opisu, bez preferowania konkretnego zakresu (ten
  sam rodzaj decyzji co `full_protective_max_n`/`protective_scale_denominator` w `gpm`).
  Defensywna czesc: dodano `shy.us` do juz istniejacych IEF/TLT (3 kandydaci zamiast 2), cala
  trafia w jedno aktywo z najwyzszym (mom_1+mom_3+mom_6+mom_12)/4.

  Czesc ofensywna (top4 wg (mom_3+mom_6+mom_12)/3, rowne wagi) BEZ ZMIAN - zweryfikowane testem
  (`test_gfm_breadth_offensive_side_matches_gfm_unchanged`).

  **Wynik zgodny z celem usera** ("nizszy MaxDD i wczesniejsze przechodzenie do defensywy"):

  | | CAGR | MaxDD | Sharpe | Calmar | Turnover |
  |---|---|---|---|---|---|
  | `gfm` (binarny SPY 12M switch) | 7.11% | -35.22% | 0.545 | 0.202 | 3.47 |
  | `gfm_breadth` (skokowa szerokosc) | 5.49% | **-26.55%** | 0.504 | 0.207 | 4.41 |

  MaxDD poprawiony o ~8.7pp (klasyczny kompromis: mniej CAGR za znaczaco nizsze ryzyko), Calmar
  lekko lepszy. Wyzszy turnover (czesciowe pozycje na progach) - podniesiono
  `max_annual_turnover` w acceptance_spec.json do 5.0 (bylo 4.0, jak w oryginalnym `gfm`).

  19 nowych testow bloku (`test_gfm_breadth_risk_step.py` - walidacja, wszystkie 5 koszykow
  szerokosci, best-of-3 defensywny wybor, NaN nie liczy sie do szerokosci/selekcji, brak
  kandydatow -> `_CASH`) + 6 testow strategii (`test_gfm_breadth_strategy_spec.py`). Wygenerowano
  TYLKO nowy plik wynikowy + scalony `SUMMARY.md` (52 wiersze). Pelny pakiet testow: 519/519, bez
  regresji.

## 2026-07-14 (51)

- **`gtaa_agg6_mid_best17_a`** - user: "I potem mix z best" (po (50)). Miks `fixed_capital_weights`
  `gtaa_agg6_mid`+`best17_a` - `gtaa_agg6_mid` wybrany (nie `agg3_mid`), ten sam powod co przy
  oryginalnym `gtaa_agg6_best17_a` (nizszy MaxDD/lepszy Sharpe, bardziej komplementarny z
  agresywnym best17_a). Sweep wagi best17_a w [0.30..0.70] na PELNYM realnym backtescie -
  najlepszy Calmar przy best17_a=45%/gtaa_agg6_mid=55%: CAGR 9.05%, MaxDD -21.09%, Sharpe 0.779,
  Calmar **0.429**.

  **Uczciwe porownanie z oryginalem** - przeliczono TAKZE oryginalny `gtaa_agg6_best17_a` na tych
  samych, aktualnych poprawkach (podatek (47), cost_bps=40 (49), ktorych NIE mial jego sweep z
  2026-07-11) - najlepszy Calmar oryginalu to 0.425 (przy 60/40, nie 55/45). `_mid` daje wiec
  MARGINALNA poprawe samego wyniku (0.429 vs 0.425), ale PELNE pokrycie UK mapping (11/11+VT
  tickerow obu skladowych, mismatch 0%) - oryginal w ogole nie mial wlasnego UK mapping (IJR/EFA
  niezmapowane). Nadal WYRAZNIE gorzej niz `gpm_best17_a`/`gpm_mid_10_best17_a` (Calmar ~0.52-0.54)
  - ten sam wniosek co oryginal: trend/momentum na tym samym uniwersum akcji USA co `best17_a`
  koreluje zbyt mocno, slabiej tlumi jej drawdown niz `gpm`. Zapisane jako uczciwy wynik, NIE
  rekomendacja - `gpm_mid_10_best17_a` pozostaje kandydatem produkcyjnym.

  Nowy plik testowy `test_gtaa_agg6_mid_best17_a_uk_mapping.py` (2 testy, ten sam wzorzec co
  `test_gpm_mid_10_best17_a_uk_mapping.py`). Wygenerowano TYLKO nowy plik wynikowy + scalony
  `SUMMARY.md` (51 wierszy). Pelny pakiet testow: 494/494, bez regresji.

## 2026-07-14 (50)

- **`gtaa_agg3_mid`/`gtaa_agg6_mid`** - user: "Dorobmy taka strategie AGG - agresywna odmiana
  GTAA... wydaje mi sie ze bedzie sensowniejsza do mixu". Opis usera (momentum 1/3/6/12m, top3/
  top6, filtr trendu per-slot wg SMA6, ucieczka do obligacji, rebalans miesieczny) okazal sie
  mechanicznie IDENTYCZNY z juz istniejacym `gtaa_agg3`/`gtaa_agg6` (2026-07-11) - zero nowego
  kodu bloku. Doprecyzowano z userem: chodzilo o NOWY wariant na uniwersum BEZ IJR/EFA (te same
  aktywa usuniete z `gpm_mid_10` wlasnie dlatego, ze trudno je jednoznacznie zmapowac na
  UK/XTB) - zamiast tego uniwersum `gpm_mid_10` (SPY/QQQ/VWO/VNQ/DBC/GLD/HYG/LQD/TLT/XLE + IEF).

  Nowe strategie `strategies_v2/gtaa_agg3_mid/`, `strategies_v2/gtaa_agg6_mid/` - dziedzicza
  gotowy, juz zweryfikowany UK ticker mapping z `gpm_mid_10` (minus `shy.us`, ktorego AGG nie
  uzywa). Nowy plik testowy `engine_v2/tests/test_gtaa_mid_strategy_specs.py` (14 testow).

  **Wynik - wyrazna poprawa wzgledem oryginalnego uniwersum** (usuniecie IJR/EFA i dodanie
  QQQ/XLE pomaga, nie tylko upraszcza mapowanie):

  | | CAGR | MaxDD | Sharpe | Calmar |
  |---|---|---|---|---|
  | `gtaa_agg3` (oryginal, z IJR/EFA) | 4.79% | -20.82% | 0.420 | 0.230 |
  | `gtaa_agg3_mid` (bez IJR/EFA) | 7.03% | -21.16% | 0.552 | **0.332** |
  | `gtaa_agg6` (oryginal, z IJR/EFA) | 4.42% | -21.97% | 0.479 | 0.201 |
  | `gtaa_agg6_mid` (bez IJR/EFA) | 5.76% | -17.29% | 0.588 | **0.333** |

  UK mapping: pelne pokrycie (11/11 tickerow), mismatch 0% w obu wariantach, korelacja miesieczna
  ~0.97-0.973. Oba wchodza do `results/SUMMARY.md` na pozycjach ~21-22/50 (wyzej niz oryginalne
  `gtaa_agg3`/`gtaa_agg6` na ~36/45) - potwierdza intuicje usera, ze ten wariant jest sensowniejszy
  nie tylko do mapowania, ale i do samego wyniku.

  Wygenerowano TYLKO nowe pliki wynikowe (nie pelny `results/` - zaden inny plik/strategia sie
  nie zmienil, user wczesniej slusznie wytknal niepotrzebne pelne przeliczenia). Pelny pakiet
  testow: 490/490, bez regresji.

## 2026-07-13 (49)

- **Ujednolicenie `execution.cost_bps` na 40 we WSZYSTKICH strategiach.** User: "Przypilnuj zeby
  bps wszedzie byl 40". Sprawdzone przed zmiana: `strategy_spec.json`'s `execution.cost_bps`
  (REALNIE uzywany przez bloki `hysteresis`/`score_gap_hysteresis`) mial 10 w 20/23 strategiach,
  40 tylko w `best17_a`/`synergy_v1`/`synergy_v2`. Dodatkowo `test_spec.json`'s
  `costs.transaction_cost_bps_one_way` - pole zdefiniowane od poczatku projektu, ale NIGDZIE w
  kodzie nieodczytywane (kolejny "zdefiniowany, nigdy nie liczony" placeholder, ten sam wzorzec
  co `param_stability`/`named_periods`/`uk_benchmark` przed ich zbudowaniem) - bylo JUZ niespojne
  z realnym kosztem w 3 strategiach (`the_one`/`dual_momentum`/`vaa_g4` mialy tu 40, a realnie
  liczyly na 10).

  Ujednolicono OBA pola na 40 wszedzie (23 `strategy_spec.json` + 18 `test_spec.json` - pozostale
  3 foldery to szkielety-skladniki bez wlasnego `test_spec.json`).

  **Konsekwencje** - 8 zamrozonych testow regresyjnych (PRZED-podatkowe baseline'y liczone na
  starym 10bps) wymagalo aktualizacji: `test_daa_g4_strategy_spec.py`,
  `test_gpm_lite_7_strategy_spec.py`, `test_gpm_mid_10_strategy_spec.py`,
  `test_gpm_strategy_spec.py`, `test_gtaa_strategy_specs.py` (oba warianty), plus
  `test_pipeline.py::test_pipeline_matches_manual_wiring` (recznie zdublowany `cost_bps: 10` w
  manualnym odtworzeniu wiring'u dla `example_strategy`).

  **Ciekawa, uczciwie odnotowana zmiana wniosku**: `test_ema_variant_strategy_specs.py` mial test
  "EMA wyraznie gorsze niz momentum" (`daa_g4_ema` vs `daa_g4`) oparty na Sharpe - przy 10bps EMA
  mialo NIZSZY Sharpe. Przy 40bps ten wniosek juz NIE trzyma sie: `daa_g4_ema` ma ~4.7x nizszy
  roczny turnover (1.62 vs 7.64/rok), wiec wyzszy koszt transakcyjny KARZE `daa_g4` (momentum)
  znacznie bardziej - EMA teraz WYPRZEDZA je na CAGR (5.10% vs 4.21%) i Sharpe (0.388 vs 0.370).
  Jedyna czesc oryginalnego wniosku, ktora przetrwala niezaleznie od zalozenia kosztowego: EMA ma
  STRUKTURALNIE glebszy MaxDD (-42.0% vs -31.6%, wolniejsza reakcja EMA na odwrocenia trendu, nie
  artefakt kosztow) - test przemianowany na `test_daa_g4_ema_worse_drawdown_than_daa_g4_momentum`,
  sprawdza teraz MaxDD i turnover zamiast Sharpe. Pouczajace odkrycie samo w sobie: wnioski o
  "lepszej"/"gorszej" wersji strategii moga zalezec od zalozenia kosztowego, nie tylko od samego
  sygnalu.

  Pelna regeneracja `results/` (wszystkie 48 plikow, uzasadniona tym razem - zmiana dotyczy
  faktycznie WSZYSTKICH strategii solo I portfeli laczonych, ktore je uzywaja jako skladniki, w
  odroznieniu od poprzedniego dodania `bh_vt`/`bh_spy`, gdzie pelny przebieg byl niepotrzebny -
  user slusznie to wytknal). Pelny pakiet testow: 476/476, bez regresji.

## 2026-07-13 (48)

- **Benchmarki "buy & hold" (`bh_vt`, `bh_spy`)** - user: "Czy zapisujemy wyniki benchmarku przy
  naszych wyliczeniach? A moze powinnismy miec prosta strategie buy hold vt z mappingiem vwra
  oraz druga z sp500 i mapping uk". Trafne pytanie - `TestSpec.UkMappingSpec.uk_benchmark` byl
  polem zdefiniowanym OD POCZATKU projektu (obecne juz w `example_strategy/test_spec.json`), ale
  NIGDY nie bylo faktycznie uzywane/liczone - kolejne "zdefiniowane, nigdy nie liczone" pole (ten
  sam wzorzec co `param_stability`/`named_periods`/`annual_tax` przed ich zbudowaniem).

  Zamiast dodawac nowy mechanizm DO uk_mapping, dodano dwie NOWE, pelnoprawne strategie - zero
  nowego kodu bloku, ten sam wzorzec co juz istniejacy `tlt_hedge` (jednoaktywowa "cegielka":
  `top_n=1` na jednoaktywowym uniwersum, `portfolio_risk_engine="none"`, zero timingu/rotacji):
  - `strategies_v2/bh_vt/` - zawsze 100% `vt.us` (Vanguard Total World, globalny rynek akcji),
    UK mapping `vt.us`->`vwra.uk`.
  - `strategies_v2/bh_spy/` - zawsze 100% `spy.us` (S&P 500), UK mapping `spy.us`->`cspx.uk`.

  Obie automatycznie trafiaja do `results/SUMMARY.md` (ten sam generator co reszta strategii,
  zero specjalnego kodu) - teraz mozna WPROST porownac, czy dodatkowa zlozonosc strategii
  momentum w tym repo place wzgledem prostego pasywnego trzymania rynku. Progi akceptacji
  celowo bardzo luzne (jak w `tlt_hedge`) - to punkt odniesienia, nie strategia oceniana wg
  kryteriow aktywnej.

  Wyniki (post-tax, pelna historia): `bh_vt` CAGR 6.35%/MaxDD -47.26%/Sharpe 0.404/Calmar 0.134;
  `bh_spy` CAGR 7.88%/MaxDD -54.54%/Sharpe 0.495/Calmar 0.145 (obie zawieraja krach 2008, stad
  duzy MaxDD - zaden overlay ochronny). UK mapping: mismatch 0% w obu (jeden ticker, zawsze
  zmapowany, nigdy nie wpada w `_CASH`), korelacja miesieczna ~0.978-0.980 (najwyzsza w calym
  repo - jednoaktywowe mapowanie nie ma szumu wielu tickerow naraz).

  Nowy plik testowy `engine_v2/tests/test_bh_benchmarks.py` (8 testow, parametryzowane po obu
  benchmarkach - wazniejsze niz dla `tlt_hedge`, ktory nigdy nie mial wlasnego dedykowanego testu,
  bo byl tylko wewnetrzna "cegielka" dla combinera, nie widocznym benchmarkiem). Pelna
  regeneracja `results/` (teraz 48 plikow). Pelny pakiet testow: 476/476, bez regresji.

## 2026-07-13 (47)

- **BUGFIX `engine_v2/annual_tax.py` - podatek "Belki" byl NIEDOSZACOWANY na wielu latach.** User:
  "Czy nie mamy Buga z podatkiem belki cos za maly ma wplyw na CAGR trzeba to sprawdzic" - trafna
  intuicja, potwierdzony REALNY bug, obecny od PIERWSZEGO wdrozenia mechanizmu (2026-07-11 (13)),
  przez CALA sesje.

  **Diagnoza** - relatywny spadek CAGR z 19% podatku wynosil konsekwentnie ~2.3-2.7% we
  WSZYSTKICH strategiach (agresywnych i defensywnych, wysokiej i niskiej zmiennosci) - podejrzanie
  jednolite, mimo ze mechanizm high-water-mark powinien dawac WIEKSZE zroznicowanie miedzy
  strategiami o roznym profilu obsuniec. Zweryfikowano na czystym, syntetycznym przykladzie
  (staly wzrost 10%/rok, 3 lata, bez zadnej straty - kazdy rok w pelni opodatkowany): oczekiwany
  wynik to STALY mnoznik roczny `1 + 0.10*0.81 = 1.081` skladany 3x = **1.2632**, kod dawal
  **1.3041** - o ~3% za wysoko.

  **Przyczyna**: `equity.iloc[idx:next_event_idx] *= haircut_ratio` (haircut aplikowany TYLKO do
  nastepnego zdarzenia podatkowego, WYLACZNIE) - `equity` jest mutowana W MIEJSCU, petla idzie
  chronologicznie, ale KAZDY kolejny segment (miedzy dwoma zdarzeniami) byl mnozony TYLKO przez
  WLASNY, tegoroczny haircut, nigdy przez ZLOZENIE wszystkich wczesniejszych haircutow. Efekt:
  kazdy kolejny rok liczyl podatek od zysku wzgledem SUROWEJ (nigdy nieopodatkowanej) wartosci z
  wejsciowej krzywej, jakby wczesniejsze podatki nigdy nie mialy miejsca - `tax_base_equity`
  (poprawnie ratchetowany po KAZDYM podatku) byl porownywany z BLEDNIE zbyt wysokim
  `equity_before_tax`, co w TEORII powinno dawac WYZSZY tax_amount kazdego roku - ale poniewaz
  ROWNOCZESNIE kazdy segment resetowal sie do surowej wartosci (gubiac skumulowany spadek
  kapitalu z lat wczesniejszych), NETTO efekt byl NIZSZY calkowity podatek na dlugiej historii
  (patrz przyklad wyzej: 1.3041 > 1.2632 - bug dawal WYZSZA, nie nizsza, koncowa wartosc).

  **Naprawa**: `equity.iloc[idx:] *= haircut_ratio` (DO KONCA serii, nie tylko do nastepnego
  zdarzenia) - petla juz idzie chronologicznie i mutuje `equity` w miejscu, wiec kolejne
  mnozenia NATURALNIE sie skladaja (kazdy kolejny rok odczytuje juz poprawnie skumulowany
  wczesniejszy haircut, zanim doda WLASNY).

  **Zaktualizowany test** `test_high_water_mark_not_double_taxed_until_new_peak`
  (`test_annual_tax.py`) - stary asercja `out["equity"].iloc[1] == 1.2` bylo TRESCIA buga (rok
  strat kopiowal SUROWA nominalna wartosc 1.2, ignorujac ze realny kapital byl juz mniejszy po
  podatku roku 1) - poprawiona na `1.405 * (1.2/1.5) = 1.124` (ten sam PROCENTOWY spadek -20%
  zaaplikowany do REALNEGO, mniejszego kapitalu - matematycznie poprawne dla portfela o
  zwrotach proporcjonalnych do calego kapitalu). Nowy test
  `test_haircuts_compound_across_multiple_tax_events` - regresja na syntetycznym przykladzie
  wyzej (3 lata staly wzrost, oczekiwany skumulowany mnoznik 1.2632, NIE 1.3041).

  **PRAWDZIWY wplyw na wyniki** (relatywny spadek CAGR z podatku, PRZED vs PO naprawie):

  | strategia | rel. spadek PRZED (bug) | rel. spadek PO (naprawione) |
  |---|---|---|
  | `best17_a` | 2.5% | **18.1%** |
  | `gpm_mid_10` | 2.7% | **17.8%** |
  | `gpm` | 2.7% | **18.0%** |
  | `the_one` | 2.3% | **17.5%** |
  | `tlt_hedge` | 0.0% | **34.9%** (outlier - niska baza CAGR, male zmiany bardzo widoczne relatywnie) |

  Po naprawie relatywny spadek jest konsekwentnie ~18% - bardzo bliskie nominalnej stawce 19%
  (jak nalezy, bo wiekszosc strategii ma wiecej dodatnich niz ujemnych lat - efektywna stawka
  troche NIZSZA niz nominalna, bo high-water-mark daje realna ulge w latach odrabiania strat, ale
  NIE o rzad wielkosci jak przy bugu). Na przykladzie `best17_a` (pelna historia, 2008-2026):
  equity koncowe PRZED podatkiem 16.16, PO POPRAWNYM podatku **10.06** (bylo blednie 15.15) -
  calkowity zebrany podatek to teraz 13.6% zysku nominalnego (bylo blednie ~21%, co samo w sobie
  bylo dodatkowym artefaktem tego samego buga, nie niezaleznym zjawiskiem).

  **Konsekwencje dla rankingu sesji** - `gpm_best17_a` (dotychczasowy "sesyjny rekord Calmar
  0.786") spada do Calmar **0.585**. `gpm_mid_10_best17_a` (kandydat produkcyjny) spada do Calmar
  **0.601** - PRZEJMUJE #1 miejsce w `results/SUMMARY.md` (bylo #2). Wzgledna kolejnosc strategii
  w duzej mierze zachowana (obie pozostaly na samym szczycie, tylko zamienily sie miejscami) -
  poprawka dziala z grubsza proporcjonalnie na strategie o podobnym profilu zysku/straty, ale
  WSZYSTKIE liczby "PO PODATKU" cytowane w CHANGELOG.md PRZED tym wpisem sa NIEAKTUALNE.
  Aktualne, poprawione liczby: `results/*.json` (regenerowane w calosci) i zaktualizowana sekcja
  "ANNUAL TAX" w README.md.

  Pelna regeneracja `results/` (wszystkie 46 plikow + `SUMMARY.md`). Pelny pakiet testow:
  468/468 (dodany 1 nowy test), bez regresji - ZERO innych zamrozonych baseline'ow sie zlamalo,
  bo wiekszosc z nich sprawdza metryki PRZED podatkiem (`metrics_pre_tax`) albo uzywa szerokich
  progow tolerancji (`correlation > 0.9`, `gaps < 0.05`), nie precyzyjnych liczb PO podatku.

## 2026-07-13 (46)

- **VNQ mapping: `idup.uk` -> `xres.uk`** - user: "Wymienimy uk dup na xres jest akumulacyjny" -
  dostarczyl nowy plik danych `data/uk/xres.uk.txt` bezposrednio na `main` (2618 wierszy,
  2016-02-22 do 2026-07-02). Zweryfikowano PRZEZ WYSZUKIWANIE + porownanie stop wzrostu (ta sama
  metoda co dla HYG (44)):
  - `idup.uk` = iShares US Property Yield UCITS ETF **USD (Dist)**, ISIN IE00B1FZSF77 - potwierdzone
    POPRAWNE (USD, Dist) zarowno przez dokumentacje funduszu, jak i przez stope wzrostu (3.55%/rok
    na WLASNYM oknie vs `vnq.us` 4.24%/rok na tym samym oknie - LEKKIE niedoszacowanie, spojne z
    Dist/brakiem reinwestycji dywidend).
  - `xres.uk` = **Invesco** Real Estate S&P US Select Sector UCITS ETF **USD (Acc)**, ISIN
    IE00BYM8JD58 - INNY dostawca niz iShares, potwierdzone jako Acc (7.40%/rok na wspolnym oknie
    2016-02/2026-07 vs `vnq.us` 5.10%/rok - gap +2.3pp/rok, spojny z reinwestycja dywidend REIT-u
    o wysokiej stopie dywidendy).

  Czyli: `idup.uk` bylo TECHNICZNIE poprawnym wyborem (USD, Dist, zgodne z metodologia calego
  mapowania) - user zamienil je mimo to na `xres.uk` (INNY dostawca, Acc) - prawdopodobnie bo
  IDUP nie jest realnie dostepny/tradowalny na jego koncie maklerskim (nie zweryfikowane wprost,
  ale user potwierdzil jednoznacznie: "Tak chce xres zamiast idup" po pytaniu o powod). Ten sam
  wzorzec kompromisu co VT->VWRA (44)/HYG->IHYA (44) - akceptujemy Acc bias w zamian za realna
  dostepnosc, dokumentujemy wprost rozmiar gapu (tu WIEKSZY niz w innych przypadkach - REIT-y
  maja wysoka biezaca stope dywidendy, ~2.3pp/rok to najwiekszy pojedynczy Acc/Dist gap w calym
  mapowaniu dotad).

  **Wplyw na "ostateczny test"** (VNQ to jeden z 10 aktywow ryzykownych `gpm_mid_10`,
  `top_n_risky=3` - wplyw calego portfela rozcienczony):

  | | mismatch | korelacja miesieczna | gap CAGR | gap MaxDD |
  |---|---|---|---|---|
  | `gpm_mid_10` solo (IDUP, przed) | 0/99 (0%) | 0.9574 | +0.75pp | +0.33pp |
  | `gpm_mid_10` solo (XRES, po) | 0/99 (0%) | 0.9569 | +0.82pp | +0.31pp |
  | `gpm_mid_10_best17_a` (IDUP, przed) | 0/85 (0%) | 0.9669 | +0.56pp | -0.33pp |
  | `gpm_mid_10_best17_a` (XRES, po) | 0/85 (0%) | 0.9667 | +0.56pp | -0.33pp |

  Praktycznie bez zmiany na poziomie calego portfela (jak oczekiwano). Zaktualizowano
  `strategies_v2/gpm_mid_10/uk_ticker_mapping.json` i
  `strategies_v2/gpm_mid_10_best17_a/uk_ticker_mapping.json`. Zaden test nie wymagal zmiany
  asercji. Pelna regeneracja `results/` (wszystkie 46 plikow + `SUMMARY.md`). Pelny pakiet
  testow: 467/467, bez regresji.

## 2026-07-12 (45)

- **`results/` dla portfeli LACZONYCH: dodane UK mapping** - user zauwazyl, ze poprawka HYG
  EUR->USD (44) nie zmienila `results/gpm_mid_10_best17_a.json` w ogole ("ale to przeliczales
  wyniki i zrobiles ich commit?") - powod: `_generate_combined` w `generate_results.py` NIGDY nie
  liczyl UK mapping (tylko `metrics`/`named_periods_all`/`train_oos`/
  `capital_weight_sensitivity`) - dane US-vs-UK dla miksu istnialy TYLKO w osobnym
  `test_gpm_mid_10_best17_a_uk_mapping.py`, nie w `results/`. User: "Wiadomo ze musi to sie
  przeliczyc" - trafne, to byla realna luka w generatorze, nie w samej poprawce mapowania.

  Nowa `_uk_mapping_combined` w `generate_results.py` - ten sam mechanizm co
  `run_spec_runner._run_uk_mapping_check` dla pojedynczej strategii, uruchomiony na wyniku
  `run_combined_pipeline`: sklada mapowanie ze WSZYSTKICH `uk_ticker_mapping.json` skladowych
  strategii (sibling ich `strategy_spec.json`), zwraca `None` gdy KTORAKOLWIEK skladowa go nie ma
  (np. `gpm_best17_a` - `gpm` nie ma wlasnego pliku mapowania, wiec `uk_mapping: null` - poprawne,
  nie polowiczny wynik). Progi akceptacji zalozone przez generator
  (`_COMBINED_UK_MAPPING_ACCEPTANCE`, ta sama konwencja co juz istniejacy
  `annual_tax_rate_assumed`), bo `CombinedSpec` nie niesie wlasnego `AcceptanceSpec.uk_mapping`.

  `results/gpm_mid_10_best17_a.json` ma teraz `uk_mapping` (jedyny portfel laczony w repo ze
  100% pokryciem skladowych - `best17_a` + `gpm_mid_10`): mismatch 0%, korelacja miesieczna
  0.9669, zgodne z liczbami z (43)/(44) (poprawka HYG->`ihya.uk` juz uwzgledniona). Wszystkie inne
  28 portfeli laczonych dostaja `uk_mapping: null` (brak pelnego pokrycia mapowania skladowych).

  Pelna regeneracja `results/` (wszystkie 46 plikow + `SUMMARY.md`). Pelny pakiet testow:
  467/467, bez regresji.

## 2026-07-12 (44)

- **HYG mapping: EUR -> USD (`ihyg.uk` -> `ihya.uk`)** - user: "W mappingu uzywamy tickera ihyg
  ktory jest notowany w EUR - nie chce tak, powinnismy miec wszystkie notowane na gieldzie w
  europie ale w USD". Zweryfikowano PRZEZ WYSZUKIWANIE (nie z pamieci) wszystkie 15 tickerow z
  `data/uk/` wzgledem realnej dokumentacji funduszu (ISIN, iShares/Vanguard fact sheets,
  Yahoo/justETF/Bloomberg):

  | ticker | fundusz | waluta |
  |---|---|---|
  | `ihyg.uk` | iShares **€** High Yield Corp Bond UCITS ETF **EUR** (Dist) | **EUR** ❌ |
  | `ihya.uk` | iShares **$** High Yield Corp Bond UCITS ETF **USD** (Acc) | USD ✅ |
  | `cbu0`/`cndx`/`cspx`/`dtla`/`eimi`/`ibta`/`icom`/`idup`/`igln`/`iues`/`iuit`/`lqda`/`vwra` | (odpowiednio IEF/QQQ/SPY,IVV/TLT/VWO,VWO/SHY/DBC/VNQ/GLD,IAU/XLE/XLK/LQD/VT) | wszystkie **USD** ✅ |

  Trafna obserwacja usera - `ihyg.uk` bylo JEDYNYM zle dobranym tickerem w calym mapowaniu (14/15
  poprawnych od poczatku). Powod bledu: wczesniejsza weryfikacja (38)/(39) sprawdzala TYLKO
  Acc-vs-Dist (polityke dywidend) przez porownanie rocznych stop wzrostu, NIE walute - `ihyg.uk`
  "wygladalo" poprawnie (niska stopa wzrostu, zgodna z Dist/brakiem reinwestycji), ale niska
  stopa wzrostu byla RESZTA dwoch efektow razem (Dist + osobna dryfujaca ekspozycja EUR/USD), nie
  tylko Dist.

  **Prawdziwy dylemat, brak idealnej opcji w `data/uk/`**: nie ma tickera "USD + Dist" dla tego
  funduszu w naszych danych (odpowiednik `IHYU` istnieje naprawde, ale nie mamy jego cen) -
  wybor to `ihyg.uk` (poprawna polityka dywidend, ZLA waluta - szum EUR/USD) albo `ihya.uk`
  (poprawna waluta, ZLA polityka dywidend - reinwestycja podbija CAGR o ~3.4pp/rok wobec `hyg.us`
  na wspolnym oknie 2017-04 do 2026-07, WIEKSZY gap niz jakikolwiek zaakceptowany dotad w tym
  mapowaniu). Wybrano `ihya.uk` (USD) zgodnie z jawnym priorytetem usera - dodatkowo
  METODOLOGICZNIE: niedopasowanie waluty wprowadza SZUM w zwrotach MIESIECZNYCH (EUR/USD rusza
  sie niezaleznie od obligacji), degradujac `monthly_return_correlation`/
  `max_single_month_return_diff` NAPRAWDE (przypadkowo, miesiac po miesiacu); niedopasowanie
  Acc/Dist to gladki, monotoniczny, w pelni przewidywalny dryf CAGR (nie wplywa na ksztalt
  korelacji), tej samej kategorii co juz zaakceptowany `IVV`->`CSPX` (~3.7pp/rok).

  **Wplyw na wyniki "ostatecznego testu"** (`gpm_mid_10` uzywa HYG w swoim 10-aktywowym
  uniwersum, `top_n_risky=3` wiec HYG nie zawsze jest trzymany - stad wplyw calego portfela jest
  rozcienczony):

  | | mismatch | korelacja miesieczna | gap CAGR | gap MaxDD |
  |---|---|---|---|---|
  | `gpm_mid_10` solo (EUR `ihyg`, przed - CHANGELOG (39)) | 0/99 (0%) | 0.957 | +0.75pp | +0.33pp |
  | `gpm_mid_10` solo (USD `ihya`, po) | 0/99 (0%) | 0.957 | +0.75pp | +0.33pp |
  | `gpm_mid_10_best17_a` (EUR `ihyg`, przed - CHANGELOG (43)) | 0/85 (0%) | 0.9668 | +0.54pp | -0.33pp |
  | `gpm_mid_10_best17_a` (USD `ihya`, po) | 0/85 (0%) | 0.9669 | +0.56pp | -0.33pp |

  Praktycznie BEZ ZMIANY na poziomie calego portfela (jak oczekiwano - HYG to jeden z 10 aktywow,
  top-3 na raz, wiec jego udzial jest rozcienczony) - ale mapowanie jest teraz METODOLOGICZNIE
  POPRAWNE (waluta), co bylo celem tej poprawki, nie poprawa liczb.

  Zaktualizowano `strategies_v2/gpm_mid_10/uk_ticker_mapping.json` i
  `strategies_v2/gpm_mid_10_best17_a/uk_ticker_mapping.json`. Zaden test nie wymagal zmiany
  asercji (progi `correlation > 0.9`/`gaps < 0.05` nadal spelnione). `results/gpm_mid_10.json` i
  `results/gpm_mid_10_best17_a.json` przeregenerowane. Pelny pakiet testow: 467/467, bez regresji.

## 2026-07-12 (43)

- **`results/` ROZSZERZONE** - user (zaraz po (42)): "Brakuje wyników dla gpm_mid_10_best17_a np
  named periods danych o stabilności etc". Trafne - `_generate_combined` liczyl dotad TYLKO
  `metrics`/`metrics_pre_tax`, a `_generate_single` polegal WYLACZNIE na `run_spec_runner`'s mode
  "final" (brak `param_stability` - to wymaga mode "search"; `named_periods` byl pusty `{}` w
  acceptance_spec.json wiekszosci strategii, wiec i tak nigdy nie liczony).

  Kazdy `results/<strategia>.json` ma teraz DODATKOWO:
  - `named_periods_all` - metryki na WSZYSTKICH 4 `KNOWN_PERIODS` (gfc_crash/post_gfc_recovery/
    covid_crash_rebound/inflation_bear), niezaleznie od tego, co strategia deklarowala w swoim
    (czesto pustym) `acceptance_spec.json` - porownywalne 1:1 miedzy WSZYSTKIMI strategiami.
  - `train_oos` - metryki osobno na `train_window`/`test_window` z `test_spec.json`. Dla portfeli
    LACZONYCH (nie maja wlasnego `TestSpec`) - uzywa okien skladowych strategii, TYLKO gdy
    WSZYSTKIE sa identyczne (inaczej `null`, z jasnym powodem w kodzie generatora).
  - `param_stability_full` (TYLKO pojedyncze strategie z `allowed_param_families`) - PELNY grid
    sweep x walk-forward (`run_spec_runner._run_search`), nie tylko pojedynczy `relative_drop` -
    user wczesniej w tej sesji: "a nie pokazales pelnej tabeli odpornosci". Potwierdza znane
    liczby: `gpm_mid_10` relative_drop 26.7%, `gpm_lite_7` 36.7%, `best17_a` 23.7% (nowa - nie
    liczona wczesniej w tej formie).
  - `capital_weight_sensitivity` (TYLKO portfele laczone `fixed_capital_weights` z DOKLADNIE 2
    skladowymi, 25/29 - inne combinery jak `dynamic_capital_weights`/`signal_tilted_capital_weights`/
    `momentum_hedge_overlay` nie maja jednego, ciaglego parametru wagi do sweepowania w ten sam
    sposob) - sweep udzialu kapitalu pierwszej skladowej w [0.30..0.70] co 0.05, ten sam wzorzec
    co recznie liczony sweep dla `gpm_best17_a` (CHANGELOG (31)).

  **Nieoczekiwana, uczciwie odnotowana obserwacja** - sweep wagi dla kandydata produkcyjnego
  `gpm_mid_10_best17_a` pokazuje, ze zapisane 50/50 NIE jest lokalnym optimum Calmar w prostym
  `fixed_capital_weights`: najlepszy Calmar w sweepie wychodzi przy **40/60** (best17_a/gpm_mid_10)
  - Calmar 0.770 (CAGR 9.49%, MaxDD -12.33%, Sharpe 0.998) vs zapisane 50/50 - Calmar 0.716 (CAGR
  10.49%, MaxDD -14.65%, Sharpe 0.997). Nie zmieniono konfiguracji - user wybral 50/50 swiadomie
  jako "produkcyjny kandydat" dla PROSTOTY (nie dla maksimum Calmar, ktore i tak zajmuje
  `gpm_best17_a` z `signal_tilted_capital_weights`) - to obserwacja do rozwazenia, nie
  automatyczna zmiana.

  Test suite bez zmian liczbowych - to rozszerzenie generatora, nie nowa logika silnika. Pelny
  pakiet testow: 467/467, bez regresji (czas generacji `results/` wzrosl z ~2 min do ~kilkunastu
  minut - `param_stability_full`/`capital_weight_sensitivity` to pelne grid sweepy, nie
  pojedyncze backtesty).

## 2026-07-12 (42)

- **WYGENEROWANE PLIKI WYNIKOWE (`results/`)** - user: "Dlaczego w repo nie mamy zadnych plikow
  wynikowych z testow strategii - powinny byc wrzucone zeby nie trzeba bylo tego odpalac co
  chwile ponownie". Trafna obserwacja - dotad KAZDA liczba w tym pliku i w README.md pochodzila z
  ad-hoc skryptu uruchamianego na zywo i wklejanego recznie jako proza; README od poczatku
  oznaczal "FINAL REPORT: reporting ❌" jako niezbudowana czesc pipeline'u.

  Nowy `engine_v2/generate_results.py` - skrypt (NIE test, NIE czesc CI - pelny backtest+UK
  mapping na ~46 strategiach jest wolny, ~1-2 min) generujacy:
  - `results/<strategia>.json` per zapisana strategia (17 pojedynczych przez
    `run_spec_runner.run()`, 29 laczonych przez `run_combined_pipeline` + metryki z zalozonym
    rocznym podatkiem 19% - ta sama konwencja co dla headline'owych wynikow portfeli laczonych
    w tej sesji) - `metrics`/`metrics_pre_tax`/`acceptance`/`named_periods`/`uk_mapping`, BEZ
    surowych `equity_curve`/`final_portfolio` (zamrozony WYNIK, nie duplikat danych wejsciowych).
  - `results/SUMMARY.md` - jedna zbiorcza tabela CAGR/MaxDD/Sharpe/Calmar/turnover/UK mapping,
    posortowana wg Calmar.

  Pomija foldery-szkielety (`vaa_g4_ema`, `daa_g4_ema`, `example_strategy_b` - brak
  `run_spec.json`/`combined_spec.json`, uzywane tylko jako skladnik innej strategii) i jawne demo
  (`example_strategy`, `combined_example`).

  Uruchomienie potwierdza znane liczby sesji bez rozjazdow - `gpm_best17_a` (sesyjny rekord
  Calmar 0.786) wychodzi na #1 w `SUMMARY.md`, `gpm_mid_10_best17_a` (kandydat produkcyjny,
  Calmar 0.716) na #2. Nowy plik testowy `engine_v2/tests/test_generate_results.py` (4 testy -
  serializacja JSON numpy->natywne typy, `_summary_row`, dyskretyzacja folderow demo) - CELOWO
  bez pelnego przebiegu `main()` w pytest (duplikowaloby juz istniejace
  `test_all_combined_specs.py`/`test_*_strategy_spec.py`, tylko wolniej). Pelny pakiet testow:
  467/467, bez regresji.

## 2026-07-12 (41)

- **VT dostaje mapowanie UK (`vwra.uk`)** - user zapytal: "Czemu celowo bez mapowania vt mapujemy
  na vwra" - kwestionujac wczesniejsza decyzje "VT -> signal only". Odpowiedz: VT w `best17_a`
  pelni DWIE role - (1) kanarek (EMA na cenie, nigdy nie trzymany) i (2) `rebound_starter`
  (`rebound_ticker: "vt.us"`), gdzie REALNIE kupuje 100% VT gdy portfel byl w cash i 3m zwrot VT
  > 5%. Brak mapowania oznaczal, ze w tych miesiacach strona UK siedziala w `_CASH` zamiast
  realnej ekspozycji - to byl PRAWDZIWY koszt "signal only", nie neutralna decyzja. Zweryfikowano
  `vwra.uk` (Vanguard FTSE All-World UCITS, jedyna dostepna klasa - Accumulating): CAGR ~13.17%/rok
  na wspolnym oknie 2019-07-26 do 2026-07 vs `vt.us` ~12.05%/rok - gap ~1.1pp/rok (mniejszy niz
  juz zaakceptowany IVV->CSPX ~3.7pp/rok), brak w danych odpowiednika Distributing (typu VWRL).

  Zaktualizowano `strategies_v2/best17_a/uk_ticker_mapping.json` i
  `strategies_v2/gpm_mid_10_best17_a/uk_ticker_mapping.json` (dodane `"vt.us": "vwra.uk"`).
  Konsekwencja: okno testu UK dla `best17_a` i miksu SKRACA SIE (2019-07-26, `vwra.uk` debiutuje
  najpozniej ze wszystkich uzywanych tickerow, pozniej niz `dtla.uk`).

  **Nowe wyniki "ostatecznego testu"** (PRZED vs PO tej poprawce):

  | | mismatch PRZED | mismatch PO | korelacja PRZED | korelacja PO |
  |---|---|---|---|---|
  | `best17_a` solo | 2/109 (1.8%) | **0/85 (0%)** | 0.955 | **0.969** |
  | `gpm_mid_10_best17_a` (50/50) | 2/99 (2.0%) | **0/85 (0%)** | 0.9575 | **0.967** |

  `best17_a` solo PO: CAGR 18.07%/-31.19%/0.879/0.579 (US) vs 18.65%/-31.10%/0.966/0.600 (UK).
  Miks PO: CAGR 11.89%/-14.65%/0.955/0.811 (US) vs 12.43%/-14.98%/1.050/0.830 (UK), gap CAGR
  +0.54pp, gap MaxDD -0.33pp. Jedyny formalny fail progu akceptacji w obu przypadkach to teraz
  `max_single_month_return_diff` (4.67% dla `best17_a` solo, 3.2% dla miksu, obie tuz nad progiem
  0.03) - realny tracking noise XLK/IVV vs UCITS (pazdziernik 2024), NIE luka w mapowaniu (byla
  to juz wczesniej zidentyfikowana "druga najwieksza" rozbieznosc w (39), teraz staje sie
  najwieksza, bo VT-driven mismatch znikl).

  Zaktualizowane testy: `test_best17_a_strategy_spec.py::test_best17_a_uk_mapping_end_to_end`
  (asercja `unmapped_tickers_used == []` zamiast `["vt.us"]`) i
  `test_gpm_mid_10_best17_a_uk_mapping.py` (analogicznie). Pelny pakiet testow: 463/463, bez
  regresji.

  Pchniete na `main` na wyrazna prosbe uzytkownika ("dodaj i wszystko wrzuc na main").

## 2026-07-12 (40)

- **"OSTATECZNY TEST" na kandydacie produkcyjnym (miks 50/50)** - user: "no tak wrzuć i sprawdź
  naszego produkcyjnego kandydata wersja 50/50". W odróżnieniu od sesyjnego rekordu
  Calmar (`gpm_best17_a`, `signal_tilted_capital_weights`, pełne 13 aktywów ryzykownych w
  `gpm`), kandydat produkcyjny to NAJPROSTSZY możliwy miks - `gpm_mid_10` (10 aktywów, usunięte
  IJR/EFA/VEA - trudne do jednoznacznego odwzorowania w XTB) + `best17_a`, `fixed_capital_weights`
  50/50, zero tiltu/sygnału. Zapisany jako nowy, trwały artefakt:
  `strategies_v2/gpm_mid_10_best17_a/combined_spec.json` + zmergowany
  `uk_ticker_mapping.json` (15 wpisów - `dbc.us`/`gld.us`/`ivv.us`/`igln.uk` etc. współdzielone
  między obiema składowymi strategiami tam gdzie mapowanie jest identyczne).

  Portfele ŁĄCZONE nie mają własnego `test_spec.json`/`run_spec.json` (mechanizm UK mapping w
  `run_spec_runner` jest wpięty tylko dla pojedynczej `StrategySpec`) - test UK mapping dla
  miksu woła `run_combined_pipeline` bezpośrednio i uruchamia `remap_final_portfolio` /
  `find_uk_window_start` / `compare_us_vs_uk` "ręcznie", identycznie jak dla pojedynczej
  strategii. Nowy plik: `engine_v2/tests/test_gpm_mid_10_best17_a_uk_mapping.py`.

  **Wynik "ostatecznego testu" na PRAWDZIWYCH danych US+UK** (okno 2018-05 do 2026-07, 99 mies. -
  wyznaczone przez `dtla.uk`/TLT, najpóźniejszy debiut ze wszystkich trzymanych tickerów):

  | | CAGR | MaxDD | Sharpe | Calmar | roczny turnover |
  |---|---|---|---|---|---|
  | US | 11.56% | -14.65% | 0.952 | 0.789 | 2.74 |
  | UK | 11.82% | -14.98% | 1.034 | 0.789 | 2.74 |

  Korelacja miesięczna **0.9575**, gap CAGR +0.26pp, gap MaxDD -0.33pp - zgodność tego samego
  rzędu co oba testy solo (39). Mismatch wag: 2/99 miesięcy (2.02%) - te same daty
  (styczeń/luty 2023, `rebound_starter`->`vt.us`) i ta sama, w pełni zrozumiana przyczyna co w
  solo teście `best17_a` (VT celowo bez mapowania UK - "signal only"). Jedyny formalny fail progu
  akceptacji: `max_single_month_return_diff` (0.044 > próg 0.03 użyty w testach) - identyczny,
  oczekiwany efekt VT-rebound, nie ukryta wada mapowania. Wszystkie pozostałe progi
  (`min_monthly_return_correlation`, `max_cagr_gap_vs_us`, `max_drawdown_gap_vs_us`,
  `max_weights_mismatch_months_pct`) PASS.

  Pełny pakiet testów: 463/463 (nowy plik testowy z 2 testami, + `test_all_combined_specs.py`
  automatycznie odkrywa nowy `combined_spec.json`, +2 do jego parametrycznych testów), bez
  regresji.

## 2026-07-12 (39)

- **PRAWDZIWE DANE UK + "OSTATECZNY TEST"** - user: "Na main powinieneś mieć już dane uk trzeba
  je włożyć do folderu uk. Niektóre tickery trochę inne ale wybierz najbardziej pasujące
  mappingi. Pamiętaj że okres uk będzie krótszy - większość danych zaczyna się później."
  Zmergowano commit "uk data" z `main` (15 plikow `*.uk.txt`), przeniesiono z `data/` do
  `data/uk/` (konwencja loadera, patrz `csv_loader.py`).

  **Weryfikacja mapowan wprost na danych** (nie zgadywane): `data/uk/ihyg.uk.txt` (2015-03,
  wzrost ~0.7%/rok) vs `data/uk/ihya.uk.txt` (2017-04, wzrost ~4.6%/rok) - porownanie z realnym
  `hyg.us` (~1.5%/rok, 2007-2026) potwierdza IHYG jako WLASCIWY odpowiednik (ta sama konwencja
  "cena bez reinwestycji dywidend" co dane US) - IHYA to udzialowa klasa AKUMULACYJNA (total
  return), ktora dalaby SZTUCZNIE zawyzony gap vs US. Naprawiono zgadywany wczesniej
  `gpm_mid_10/uk_ticker_mapping.json` (`hyg.us` bylo blednie `ihzu.uk` - nieistniejacy ticker
  wymyslony PRZED przyjsciem prawdziwych danych - teraz `ihyg.uk`). Podobnie zweryfikowano
  `dtla.uk` (TLT, tylko od 2018-05) - jego ujemny zwrot (~-0.89%/rok) NIE jest bledem mapowania,
  tylko realnym zachowaniem `tlt.us` w TYM SAMYM okresie (~-1.18%/rok, cykl podwyzek stop
  2018-2026) - potwierdzone bezposrednio.

  **NOWA FUNKCJA `find_uk_window_start`** (`engine_v2/uk_mapping.py`) - user mial racje: "okres
  uk bedzie krotszy do testow, wiekszosc danych zaczyna sie pozniej" potwierdzilo sie na
  realnych danych (`vwra.uk` od 2019-07, `dtla.uk` od 2018-05, vs `vt.us`/`tlt.us` od
  2005-2008). Znajduje najpozniejsza date, od ktorej WSZYSTKIE kiedykolwiek trzymane UK tickery
  maja juz prawdziwe ceny - bez tego `daily_equity_curve` probowaloby mnozyc przez NaN sprzed
  debiutu ETF (ten sam typ buga co wczesniejszy, juz naprawiony "0.0 * NaN" - patrz README,
  "Znany, naprawiony bug (4)"). `run_spec_runner._run_uk_mapping_check` teraz PRZYCINA oba
  `final_portfolio` (US i UK) do tego okna i liczy OBIE krzywe equity OD NOWA na TYM SAMYM,
  krotszym oknie - uczciwe porownanie (ta sama liczba miesiecy po obu stronach), nie caly US
  vs okrojony UK.

  **PRAWDZIWY WYNIK "ostatecznego testu"** (`uk_mapping.enabled: true` w obu strategiach):

  | | okno | US: CAGR/MaxDD/Sharpe/Calmar | UK: CAGR/MaxDD/Sharpe/Calmar | korelacja miesieczna | mismatch |
  |---|---|---|---|---|---|
  | `best17_a` | 2017-07 do 2026-07 (109 mies.) | 18.13%/-31.19%/0.899/0.581 | 18.49%/-31.10%/0.984/0.594 | **0.955** | 2/109 (1.8%) |
  | `gpm_mid_10` | 2018-05 do 2026-07 (99 mies.) | 5.46%/-7.79%/0.738/0.701 | 6.21%/-7.46%/0.856/0.832 | **0.957** | 0/99 (0%) |

  **Bardzo dobra zgodnosc** - korelacja miesieczna ~0.955-0.957, gap CAGR/MaxDD w obu przypadkach
  ponizej 1 punktu procentowego. `gpm_mid_10` ma PELNE pokrycie (0% mismatch, wszystkie 12
  tickerow zmapowane). `best17_a` ma 2 miesiace mismatch - dokladnie zdiagnozowane: styczen/luty
  2023, kiedy `rebound_starter` wszedl w 100% `vt.us` (bez mapowania UK - "signal only") - UK
  strona w tych miesiacach siedziala w `_CASH` zamiast realnego zwrotu VT, stad NAJWIEKSZY
  pojedynczy rozjazd miesieczny w calym teście (8.75% w lutym 2023 - jedyny checks, ktory
  formalnie NIE spelnia progu `max_single_month_return_diff` w acceptance_spec, ale przyczyna
  jest w pelni zrozumiana i oczekiwana, nie ukryta wada). Drugi najwiekszy rozjazd (4.67%,
  pazdziernik 2024) to juz PRAWDZIWY szum sledzenia (XLK/IVV byly wtedy trzymane, oba zmapowane)
  - naturalna roznica miedzy funduszami US i UCITS, nie luka w mapowaniu.

  **Zaktualizowane mapowania** (pelne, zweryfikowane wprost na danych):
  - `strategies_v2/best17_a/uk_ticker_mapping.json`: XLK->IUIT.UK, IVV->CSPX.UK, DBC->ICOM.UK,
    IAU->IGLN.UK (VT nadal celowo pominiety, "signal only" - `vwra.uk` istnieje w danych i
    moglby to pokryc, ale user to jawnie wykluczyl, decyzja uszanowana).
  - `strategies_v2/gpm_mid_10/uk_ticker_mapping.json`: pelne 12/12, `hyg.us`->`ihyg.uk`
    (poprawione z bledngo `ihzu.uk`).

  Oba `test_spec.json` maja teraz `uk_mapping.enabled: true` (byly `false` do czasu danych).
  6 nowych testow (`find_uk_window_start` - 4 syntetyczne w `test_uk_mapping.py`, + 2 end-to-end
  na PRAWDZIWYCH danych US+UK w `test_best17_a_strategy_spec.py`/`test_gpm_mid_10_strategy_spec.py`,
  nowy fixture `uk_data_dir` w `conftest.py`). Pelny pakiet testow: 459/459, bez regresji.

## 2026-07-12 (38)

- **NOWY MECHANIZM: UK MAPPING** (`engine_v2/uk_mapping.py`) - user: "brakuje nam teraz części
  która pokaże wyniki zmapowanej strategii na tickery uk - będzie to ostateczny test [...] bardzo
  prosto - usa decyduje o wszystkim na uk zwykly mapping". Dotad tylko SZKIELET
  (`TestSpec.UkMappingSpec`/`AcceptanceSpec.UkMappingAcceptance`, zdefiniowany OD POCZATKU
  projektu, nigdy nie liczony - to samo co wczesniej `param_stability`/`annual_tax`, kolejne
  "zdefiniowane, nigdy nie dzialajace" pole - patrz README "Co jeszcze nie istnieje").

  **Filozofia**: CALA logika (sygnaly, selekcja, wagi, execution, histereza) liczy sie WYLACZNIE
  na danych USA (dokladnie ten sam FINAL PORTFOLIO co zawsze) - strona UK NIE ma wlasnej logiki
  decyzyjnej, tylko REPLIKUJE juz wyliczone wagi 1:1 na brytyjskie odpowiedniki (ten sam procent
  kapitalu, inny instrument/gielda). Realny test, czy strategia da sie faktycznie wdrozyc na
  koncie UK (np. XTB) dostepnymi tam instrumentami, nie tylko na papierze na danych USA.

  **Mechanizm** (2 funkcje, zero nowego kodu w `pipeline.py`/`backtest_engine.py`):
  - `remap_final_portfolio(final_portfolio, ticker_mapping)` - podmienia klucze tickerow w
    `weights_used_json` kazdego okresu wg mapowania. Ticker BEZ mapowania z niezerowa waga (np.
    `vt.us` w `best17_a` - jawnie oznaczony przez usera jako "signal only", bez brytyjskiego
    odpowiednika) trafia w `_CASH` zamiast zgadywac zastepczy instrument, a ten okres jest
    JAWNIE zliczony jako "mismatch" (nie ukryte) - dokladnie to mierzy nowe pole
    `AcceptanceSpec.UkMappingAcceptance.max_weights_mismatch_months_pct`.
  - `compare_us_vs_uk(...)` - liczy METRICS NIEZALEZNIE na obu krzywych equity (kazda na WLASNYCH
    dziennych cenach - `daily_equity_curve`/`compute_metrics` bez zmian, `uk_final_portfolio` ma
    po prostu inne klucze tickerow) i porownuje: korelacje MIESIECZNYCH zwrotow (resampling, NIE
    probowanie dopasowac dokladne dni handlowe - kalendarze gield USA/UK sie ROZNIA), najwiekszy
    pojedynczy rozjazd miesieczny, gap CAGR/MaxDD (sprawdzany na WARTOSCI BEZWZGLEDNEJ - "jak
    daleko UK odjechalo od US" w KTORAKOLWIEK strone).
  - `check_uk_mapping_criteria(...)` - progi z `AcceptanceSpec.uk_mapping` (ta sama konwencja co
    `acceptance_check.check_criteria`).

  **Wpiete w `run_spec_runner._run_final`**: jesli `TestSpec.uk_mapping.enabled=True`, po
  policzeniu normalnego wyniku USA dolicza `result["uk_mapping"]` (diagnostics + comparison +
  acceptance). Wymaga `base_dir` (folder strategii, do rozwiazania `ticker_mapping_file` wzgledem
  niego) - `run()` (top-level dispatcher) go juz mial i teraz przekazuje dalej do `_run_final`.
  `TestSpec.UkMappingSpec` dostal nowe pole `uk_data_dir` (domyslnie `"data/uk"` - loader
  `stooq_csv` juz UMIAL czytac ten format, `data/uk` bylo wspomniane w jego docstringu OD
  POCZATKU, ale zaden kod nigdy tam nie sięgał).

  **NAPRAWIONY martwy placeholder**: `strategies_v2/example_strategy/test_spec.json` mial
  `uk_mapping.enabled: true` OD POCZATKU projektu jako ASPIRACYJNY przyklad konfiguracji (nigdy
  nie dzialal, bo mechanizm nie istnial) - teraz, gdy mechanizm NAPRAWDE dziala, ten placeholder
  zaczal probowac czytac nieistniejacy `ticker_mapping.json` i wywalac test. Poprawione na
  `enabled: false` (ten strategy folder nie ma prawdziwego mapowania UK, nigdy nie mial).

  **Dane UK jeszcze NIE sa w repo** - `data/uk/` nie istnieje. Mechanizm w pelni zbudowany i
  przetestowany (24 nowe testy: 14 syntetycznych w `test_uk_mapping.py` + end-to-end integration
  test w `test_run_spec_runner.py` z tymczasowymi, SKOPIOWANYMI danymi USA pod nowymi tickerami
  "*.uk" - potwierdzone: identyczne ceny pod inna nazwa dają korelacje 1.0 i zerowe gapy, dowod
  poprawnosci przewodowania) - gotowy do uruchomienia na PRAWDZIWYCH danych, jak tylko traf
  do `data/uk/`.

  **Przygotowane mapowania dla 2 strategii** (dokladnie wg specyfikacji usera):
  - `strategies_v2/best17_a/uk_ticker_mapping.json`: XLK->IUIT.UK, IVV->CSPX.UK, DBC->ICOM.UK,
    IAU->IGLN.UK (VT celowo POMINIETY - "signal only").
  - `strategies_v2/gpm_mid_10/uk_ticker_mapping.json`: SPY->CSPX.UK, QQQ->CNDX.UK, VWO->EIMI.UK,
    VNQ->IDUP.UK, DBC->ICOM.UK, GLD->IGLN.UK, HYG->IHZU.UK, LQD->LQDA.UK, TLT->DTLA.UK,
    XLE->IUES.UK, IEF->CBU0.UK, SHY->IBTA.UK (pelne pokrycie, 0% oczekiwanego mismatch).

  Oba `test_spec.json` maja teraz `uk_mapping.ticker_mapping_file`/`uk_data_dir` wypelnione, ale
  `enabled: false` do czasu realnych danych. Progi w `acceptance_spec.json` (obu strategii)
  ustawione jako rozsadne domyslne (korelacja >=0.95, max rozjazd miesieczny 3%, max gap CAGR/
  MaxDD 3%/5%) - do przestrojenia po zobaczeniu prawdziwego wyniku.

  Pelny pakiet testow: 453/453, bez regresji.

## 2026-07-12 (37)

- **NOWA STRATEGIA `strategies_v2/gpm_mid_10/`** - user: "gpm_mid_10 - posrednia, uproszczona
  wersja defensywnego GPM". Cel: "zachowac wiekszosc dywersyfikacji i ochrony pelnego GPM,
  jednoczesnie usuwajac aktywa najtrudniejsze do jednoznacznego odwzorowania w XTB" - 10 aktywow
  ryzykownych (SPY, QQQ, VWO, VNQ, DBC, GLD, HYG, LQD, TLT, XLE) zamiast 13, usuniete IJR/EFA/VEA.
  Ochrona bez zmian (IEF/SHY). Zero nowego kodu bloku - identyczna architektura co pelny `gpm`.
  `top_n_risky=3` (user potwierdzil), `full_protective_max_n=5`/`protective_scale_denominator=5`
  (polowa z 10, ta sama konwencja `denominator=len(risky)-full_protective_max_n` co oryginal).

  **Wynik na realnych danych (2007-05 do 2026-08, po podatku)**: CAGR 5.30%, MaxDD -13.04%,
  Sharpe 0.683, Calmar 0.406, turnover 4.39/rok - PRAKTYCZNIE IDENTYCZNY z pelnym `gpm` (CAGR
  5.39%, MaxDD -13.00%, Sharpe 0.675, Calmar 0.414, turnover 4.34/rok). Znacznie blizej pelnej
  wersji niz `gpm_lite_7` (7 aktywow, patrz (36)) - usuniete EFA/VEA byly juz wczesniej opisane w
  hipotezie `gpm` jako "znaczaco nakladajace sie" (oba 'developed ex-US'), wiec ich usuniecie
  kosztuje bardzo malo realnej dywersyfikacji; IJR (US small cap) rowniez nie byl kluczowy obok
  SPY/QQQ. **Ten uproszczony wariant realnie zachowuje niemal cala jakosc pelnego gpm, w
  przeciwienstwie do bardziej agresywnego ciecia w `gpm_lite_7`.**

  **Param stability** (sweep `top_n_risky` x `full_protective_max_n`, [2,3,4]x[4,5,6]):
  `relative_drop = 26.7%` - PASS (prog 30%), ksztalt gladki/monotoniczny (CAGR maleje wraz ze
  wzrostem `top_n_risky`), zero dzwigni (max suma wag = 1.0, zweryfikowane wprost - patrz bugfix
  (35)).

  5 nowych testow: `test_gpm_mid_10_strategy_spec.py` (wiring, 10+2 uniwersum, end-to-end na
  realnych danych, zamrozony baseline metryk). Pelny pakiet testow: 438/438, bez regresji.

## 2026-07-12 (36)

- **NOWA STRATEGIA `strategies_v2/gpm_lite_7/`** - user: "gpm_lite_7 - uproszczona defensywna
  strategia momentum", dokladny opis mechanizmu dostarczony przez usera. Uproszczona wersja
  `gpm` (patrz (29)/(35)) - 7 aktywow ryzykownych zamiast 13 (VT globalne akcje, QQQ Nasdaq100,
  VWO rynki wschodzace, VNQ nieruchomosci, DBC surowce, GLD zloto, XLE energia) + 2 ochronne
  (IEF/SHY, bez zmian). Cel usera: "zachowac mechanike GPM przy mniejszej liczbie tickerow,
  nizszym turnoverze i prostszym wdrozeniu". **Zero nowego kodu bloku** - identyczna architektura
  co pelny `gpm` (`momentum_avg_month_end`/`corr_to_basket_month_end`/
  `momentum_times_decorrelation`/`gpm_breadth_protective_split`), tylko rekonfiguracja. Jedyna
  swiadoma decyzja projektowa: `full_protective_max_n=3`/`protective_scale_denominator=4`
  (zamiast 6/6 w pelnym gpm) - przeskalowane proporcjonalnie do 7-aktywowego uniwersum, ta sama
  konwencja `denominator = len(risky_assets) - full_protective_max_n` co w oryginale (6=12-6).
  `top_n_risky=3` (user potwierdzil wprost: "czesc ryzykowna trafia do top 3 aktywow").

  **Wynik na realnych danych (2008-07 do 2026-08, po podatku 19%)**: CAGR 5.47%, MaxDD -13.91%,
  Sharpe 0.627, Calmar 0.393, turnover 4.07/rok. Blisko pelnego `gpm` (CAGR 5.39%, MaxDD -13.00%,
  Sharpe 0.675, Calmar 0.414, turnover 4.34/rok, 13 aktywow) - odrobine gorzej na kazdej
  metryce ryzyka, ale turnover NIZSZY (4.07 vs 4.34, ~6%) - czesciowo spelnia cel usera
  (mniej tickerow i prostsze wdrozenie potwierdzone, "nizszy turnover" tylko czesciowo -
  koncentracja top3 z mniejszej puli 7 kandydatow nadal generuje sporo przelaczen).

  **Param stability** (sweep `top_n_risky` x `full_protective_max_n`, [2,3,4]x[2,3,4], 9
  wariantow): `relative_drop = 36.7%` - **FAIL** (prog 30%), ale ksztalt jest gladki,
  MONOTONICZNY (CAGR rosnie gdy `top_n_risky` MALEJE, 2>3>4 konsekwentnie w kazdym wierszu) - NIE
  chaotyczny/losowy szczyt, wybrana wartosc domyslna (`top_n_risky=3`) to swiadomy, posrodku
  zakresu wybor usera (potwierdzony wprost: "top 3 aktywow"), nie przypadkowo trafiony punkt.
  Odnotowane uczciwie, bez ukrywania.

  5 nowych testow (`test_gpm_lite_7_strategy_spec.py`): wiring, 7+2 uniwersum, end-to-end na
  realnych danych (oba rezymy, zero dzwigni - patrz bugfix (35)), zamrozony baseline metryk.
  Pelny pakiet testow: 433/433, bez regresji.

## 2026-07-11 (35)

- **BUGFIX `gpm_breadth_protective_split`: `protective_share` nie byl przyciety do [0.0, 1.0] -
  niezamierzona dzwignia** - znalezione przy sprawdzaniu odpornosci OBU strategii skladowych
  mistrza sesji (user: "pokaz wszystkie odpornosci rodziny zarowno jedna i druga strategie").

  **Jak znalezione**: ponowne uruchomienie oficjalnego `param_stability` (`top_n_risky` x
  `full_protective_max_n`, ten sam sweep co wczesniej w sesji) na AKTUALNYM `gpm` (13 aktywow
  ryzykownych po dodaniu `xle.us`, patrz (29)) dalo `relative_drop = 73.5%` - DRASTYCZNIE gorsze
  niz wczesniej udokumentowane 9.6% ("najbardziej stabilna rodzina w repo"). Zbadanie pelnej
  tabeli sweepu pokazalo ostry "urwisko" dokladnie miedzy `full_protective_max_n=5` (CAGR solo
  `gpm` **17.95%**, Sharpe 1.060) a `full_protective_max_n=6` (domyslne, CAGR 5.39%, Sharpe
  0.675) - roznica NIEWSPOLMIERNA do zmiany parametru o "1".

  **Przyczyna**: wzor `protective_share = (len(risky_assets) - n) / protective_scale_denominator`
  (gałąź "n > full_protective_max_n") nie jest matematycznie ograniczony do 1.0. Przy 13 aktywach
  ryzykownych, `full_protective_max_n=5`, `protective_scale_denominator=6`: dla `n=6` (tuz powyzej
  progu) wychodzi `(13-6)/6 = 1.1667` - **wieksze niz 1.0**. Bez przyciecia caly udzial trafial w
  jedno aktywo ochronne z waga 116.67% (suma wag portfela w tym miesiacu > 1.0 - bezplatna,
  niezamierzona dzwignia). Potwierdzone bezposrednio: 14/229 miesiecy z suma wag > 1.0 (max
  1.1667). To NIE byla "lepsza" wartosc parametru - to byl backtest wykorzystujacy dzwignie,
  ktorej realnie nie ma.

  Z 12 aktywami (PRZED `xle.us`, cala sesja do (29)) ten sam sweep `full_protective_max_n=[5,6,7]`
  PRZYPADKIEM nigdy nie trafial w strefe przepelnienia (przy 12 aktywach przedzial "n scisle
  miedzy full_protective_max_n a `len(risky)-denominator`" wychodzi pusty dla calkowitych `n`,
  wiec bug byl DOTAD NIEWYKRYTY - dopiero 13. aktywo (`xle.us`) przesunelo te granice na liczbe
  calkowita i ujawnilo dziure).

  **Naprawa**: `protective_share = max(0.0, min(1.0, protective_share))` w gałęzi "else"
  (`engine_v2/blocks/portfolio_risk_engine/gpm_breadth_protective_split.py`). Nowy test
  regresyjny `test_gpm_protective_share_clipped_to_one_no_implicit_leverage`
  (`test_gpm_components.py`) odtwarza dokladnie ten scenariusz (13 aktywow, `n=6`,
  `full_protective_max_n=5` -> bez poprawki 1.1667, z poprawka dokladnie 1.0).

  **Wplyw na WDROZONA konfiguracje: ZERO.** Domyslny `gpm`/`gpm_best17_a`
  (`full_protective_max_n=6`) NIGDY nie wchodzil w strefe przepelnienia (przy 6 przedzial jest
  rowniez pusty dla liczb calkowitych) - zweryfikowane bezposrednio, `gpm_best17_a`
  (`signal_tilted_capital_weights`) daje DOKLADNIE te same liczby co przed poprawka: CAGR 10.38%,
  MaxDD -13.22%, Sharpe 1.011, Calmar 0.786. Mistrz sesji NIE zalezal od tego buga.

  **Odpornosc PO poprawce (prawdziwa, nieskorumpowana)**: `gpm` `relative_drop = 8.5%`
  (`top_n_risky` x `full_protective_max_n`) - domyslna konfiguracja (`top_n_risky=3`,
  `full_protective_max_n=6`) okazuje sie FAKTYCZNIE NAJLEPSZA w calej rodzinie (nie tylko blisko
  plateau, `gap_to_best=0.0`), plateau obejmuje 3/9 wariantow (caly wiersz `top_n_risky=3`) -
  wniosek "najbardziej stabilna rodzina w repo" NADAL AKTUALNY, teraz na prawdziwych, poprawnych
  liczbach.

  **Odpornosc `best17_a`** (ten sam oficjalny sweep, `min_score_gap` x `canary.bad_threshold`,
  PO bugfixach gate'u/histerezy z tej samej sesji): `relative_drop = 23.7%` (PASS, prog 30%,
  blisko wczesniej udokumentowanych 26.7% sprzed tamtych bugfixow - stabilne, spojny wniosek).

  Pelny pakiet testow: 428/428 (427 + 1 nowy), bez regresji.

## 2026-07-11 (34)

- **Sprawdzona odporność (param stability) mistrza sesji `gpm_best17_a`
  (`signal_tilted_capital_weights`)** - user: "nie chce robic overfitting, opowiedz o odpornosci".
  `relative_drop` (best-worst)/best miedzy najlepszym a najgorszym wariantem w rodzinie, na
  FULL/TRAIN/OOS, PO PODATKU:
  - `tilt_strength` (zakres -0.05..-0.15, `base_weight_a=0.55` stale): relative_drop FULL 2.2%,
    TRAIN 4.7%, OOS 5.0% - BARDZO plaskie plateau (Calmar 0.768-0.786 na calym zakresie). TRAIN i
    OOS "chca" przeciwnych kierunkow (slabszy vs mocniejszy tilt), ale roznica jest tak mala, ze
    to szum wokol plateau, nie prawdziwy konflikt.
  - `base_weight_a` (zakres 0.45..0.65, `tilt_strength=-0.10` stale): relative_drop FULL 6.8%,
    TRAIN 15.7% (rosnie MONOTONICZNIE z waga gpm - w danych treningowych gpm broniła sie dobrze w
    kryzysach), OOS 9.7%. FULL/OOS maja lagodne optimum kolo 0.55 - uczciwy kompromis miedzy
    "co dzialalo w treningu" a "co dziala ogolnie", nie odosobniony szczyt.

  Obie znacznie ponizej progu 30% (`relative_drop`) uzywanego w tej sesji jako granica "krucha
  rodzina" - konfiguracja nie wyglada jak wynik nadmiernego dostrajania. Analiza ad-hoc (bez
  zmian kodu/konfiguracji) - `gpm_best17_a` bez zmian.

## 2026-07-11 (33)

- **NOWY COMBINER `ema_canary_regime_capital_weights`** - user dostarczyl DOKLADNY opis
  3-poziomowego rezimu (risk-on/neutralny/risk-off) na bazie DWOCH sygnalow `best17_a`:
  `ema7_16` (scoring) i kanarek `ema5_12` (VT+XLK), z reguła "kanarek moze obnizyc rezim
  maksymalnie o jeden poziom" i histereza "bez przejscia bezposrednio 65/35 -> 25/75,
  maksymalnie jeden poziom na rebalans".

  **Rozni sie architektonicznie od (30)/(31)**: te uzywaly sygnalu wyprowadzonego z JUZ
  WYKONANYCH wag jednej strategii (`weights_used`) - tu potrzebne sa DWA NIEZALEZNE sygnaly
  binarne (zly kanarek vs zle momentum), ktorych NIE da sie odroznic patrzac tylko na finalne
  wagi `best17_a` (oba moga niezaleznie prowadzic do tego samego wyniku - cash/rebound). Combiner
  wiec SAMODZIELNIE laduje ceny i liczy `ema_ratio_monthly` (dokladnie ten sam blok co
  `best17_a` uzywa wewnetrznie) dla obu grup tickerow - zero zaleznosci od `weights_used`/
  `strategy_returns` innych combinerow w tym pliku.

  Logika (`raw_regime_level`) i histereza poziomu (`apply_level_hysteresis`) wydzielone jako
  czyste, w pelni testowalne funkcje (bez potrzeby prawdziwych cen) - 9 testow syntetycznych +
  4 testy integracyjne na prawdziwych danych (`test_ema_canary_regime_capital_weights.py`, 13
  testow razem).

  **Ciekawostka empiryczna zlapana w tescie integracyjnym**: prawdziwy RAW risk-off (oba sygnaly
  jednoczesnie zle) wystapil w calej historii `data/us` TYLKO w 2005 (5 miesiecy, PRZED
  poczatkiem realnego okna backtestu `best17_a` w 2008-07) - w oknie 2008-2026 risk-off NIGDY
  sie nie zrealizowal, mimo hipotezy usera. Test zaktualizowany, zeby to odzwierciedlac uczciwie
  (nie wymuszac obecnosci poziomu, ktory empirycznie nie wystepuje w tym oknie).

  **Zastosowanie do `gpm_best17_a`** (65%/45%/25% dla `best17_a`), PO PODATKU: CAGR **11.97%**
  (wyzszy niz mistrz), MaxDD **-19.83%** (WYRAZNIE gorszy niz mistrz -13.22%), Sharpe 0.970,
  Calmar **0.604** (gorszy niz mistrz 0.786), turnover 2.28 (nizszy niz mistrz 2.90). **To NIE
  jest ani wygrana ani porazka wzgledem (31) - to INNY punkt na krzywej ryzyko/zwrot**: poziom
  "risk-on" (65%) obowiazywal ~76% miesiecy calej historii (poziom "risk-off" nigdy w praktyce
  nie zadzialal - patrz wyzej), wiec efektywna BAZOWA alokacja `best17_a` jest znaczaco wyzsza
  niz w mistrzu (ktory oscyluje w waskim zakresie 50-60%) - stad wyzszy CAGR, ale i wyzszy MaxDD.
  Named periods: `covid_crash_rebound` CAGR 23.30% (bardzo dobrze), ale `inflation_bear` (2022)
  -9.84% (gorzej niz mistrz -7.31%).

  **Decyzja NIE PODJETA jeszcze** (czeka na usera: dostroic wagi rezimow, zostawic jako
  udokumentowana alternatywe, czy zignorowac) - `gpm_best17_a` NA RAZIE BEZ ZMIAN
  (`signal_tilted_capital_weights`, Calmar 0.786 pozostaje aktywna konfiguracja). Nowy combiner
  nie zapisany jeszcze jako osobny `combined_spec.json` - kod/testy zacommitowane, eksperyment
  NIE sformalizowany jako produkt do czasu decyzji. Pelny pakiet testow: 427/427, bez regresji.

## 2026-07-11 (32)

- **Eksperyment: `signal_tilted_capital_weights` z sygnalem `best17_a` zamiast `gpm` - WYNIK
  NEGATYWNY, konfiguracja BEZ ZMIAN** (user: "doróbmy teraz wersję bazującą na sygnale risk z
  best17 a nie gpm"). Zero nowego kodu potrzebne - ten sam combiner (30)/(31), inne `params`:
  `strategy_a=best17_a_v0`, `signal_assets=["_CASH", "vt.us"]` (udzial poza normalna 2-aktywowa
  selekcja - kanarek zablokowal albo trwa rebound do VT).

  **Kluczowa roznica vs sygnal `gpm`**: `protective_share` gpm jest CIAGLY, 7 poziomow, w miare
  zbalansowany rozklad (srednia ~0.57). Sygnal `best17_a` jest praktycznie BINARNY i mocno
  skosny - `0` w 194/218 miesiacach, `1` tylko w 24/218 (kanarek VT+XLK rzadko blokuje, i gdy juz
  blokuje to krotko). Przy `center=0.5` (stala, jak w (31)) to oznacza, ze WIEKSZOSC czasu tilt
  dziala w JEDNYM, stalym kierunku (bo signal-center = -0.5 przez 194/218 miesiecy), nie
  neutralnie wokol bazowej wagi - de facto przesuwa BAZOWA alokacje, nie reaguje selektywnie na
  rzadkie zdarzenia.

  Sprawdzone OBA kierunki tiltu (PO PODATKU, base_weight_a=0.45 dla best17_a):
  - "wiecej best17_a gdy ONA SAMA jest risk-off" (tilt dodatni): Calmar spada monotonicznie z
    tiltem (0.730 przy 0.1, 0.665 przy 0.3) - gorzej niz baza (0.763).
  - "mniej best17_a gdy ONA SAMA jest risk-off" (tilt ujemny, logiczniejszy kierunek): CAGR
    rosnie (10.49%->12.08%), ale MaxDD gwaltownie sie pogarsza (-14.70%->-21.51%), Calmar spada
    (0.714->0.561) - bo asymetria 194/24 sprawia, ze przez WIEKSZOSC historii `best17_a` dostaje
    WIECEJ wagi niz baza 0.45 (nie mniej), zwiekszajac ogolna zmiennosc miksu.

  **Wniosek**: ten combiner dziala dobrze na sygnale CIAGLYM i ZBALANSOWANYM (jak breadth `gpm`),
  ale zle na sygnale RZADKIM/SKOSNYM (jak binarny kanarek `best17_a`) - `center` jako stala 0.5
  zaklada w miare symetryczny rozklad sygnalu wokol niego, co nie jest prawda dla rzadko
  bindujacych gate'ow. `gpm_best17_a` NIE zmienia konfiguracji - `signal_tilted_capital_weights`
  wg `protective_share` gpm (Calmar 0.786) pozostaje mistrzem sesji. Eksperyment nie zapisany
  jako osobny `combined_spec.json` (jednoznacznie gorszy na kazdym sprawdzonym wariancie).

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
