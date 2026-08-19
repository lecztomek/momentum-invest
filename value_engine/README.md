# value_engine - strategie "value" na GPW

Osobny silnik, poza `engine_v2`. Dwie przetestowane koncepcje, obie oparte na tych samych,
wspolnych fundamentach technicznych (parser BiznesRadaru + panel point-in-time + ceny PL).

| koncepcja | plik silnika | runner | wynik |
|---|---|---|---|
| v1: przeceniona + zdrowa, profit target | `backtest.py` | `run_test.py` | odrzucona (niszczy wartosc) |
| v2: quality value, score 0-100, sloty | `quality_value_backtest.py` | `run_quality_value.py` | blisko benchmarku, ale go nie bije |

## Dlaczego osobny folder, a nie `engine_v2`

Ocena zrobiona PRZED napisaniem kodu. Z pieciu elementow koncepcji **cztery** mieszcza sie w
`engine_v2` bez problemu, ale **piaty go lamie**:

| element | `engine_v2` |
|---|---|
| ceny dzienne PL | ✅ ten sam format stooq co US/UK - `stooq_csv` czyta `data/pl` bez zmian |
| sygnal cenowy (>=25% pod 52W high) | ✅ zwykly wskaznik + filtr |
| filtr/score fundamentalny | ✅ moglby byc wskaznikiem (pipeline nie pyta, skad wartosci) |
| ranking + portfel (top N, equal weight) | ✅ `top_n` + `rank_weights` |
| **exit po odbiciu / po N miesiacach, sloty z podmiana** | ❌ **nie da sie** |

`engine_v2` jest silnikiem **rotacyjnym i bezstanowym wzgledem pozycji**: kazdy miesiac liczy wagi
docelowe od zera z biezacych wskaznikow, a `PortfolioState` niesie tylko `current_weights` /
`equity` / `tax_base_equity` / `last_target_signature`. Nie ma tam **ceny wejscia**, **czasu
trzymania** ani **tozsamosci pozycji** - a te koncepcje wymagaja wszystkich trzech. Dorzucenie ich
znaczylo by przebudowe wspolnego silnika ~50 istniejacych strategii, wprost przeciwko zasadzie repo
("wariant eksperymentalny = osobny plik, nigdy flaga w produkcyjnym bloku").

**Co JEST ponownie uzyte z `engine_v2`** (bez kopiowania kodu): loader cen `stooq_csv` oraz
`metrics.compute_metrics` - te same definicje CAGR/MaxDD/Sharpe/Calmar, wiec liczby sa
porownywalne 1:1 z reszta repo.

## Moduly

| plik | rola |
|---|---|
| `biznesradar_scraper.py` | (dostarczony) zapis surowych stron BiznesRadaru do SQLite |
| `br_parser.py` | surowy HTML -> uporzadkowane szeregi (okresy, **daty publikacji**, metryki) |
| `fundamentals.py` | panel **point-in-time**: co bylo publicznie znane na dana date |
| `signals.py` | obsuniecie od 52W high, daty decyzyjne (1. dzien handlowy miesiaca) |
| `scoring.py` | QUALITY (4 kryteria x 25 pkt), percentyle DD/REL, skladanie SCORE 0-100 |
| `backtest.py` | silnik koncepcji v1 |
| `quality_value_backtest.py` | silnik koncepcji v2 (sloty + regula podmiany) |

```
.venv/bin/python3 -m value_engine.run_quality_value
.venv/bin/python3 -m value_engine.run_quality_value --sweep
.venv/bin/python3 -m value_engine.run_quality_value --max-holding-months 36 --show-trades
.venv/bin/pytest value_engine/tests/ -v
```

## Fundament wspolny: point-in-time (look-ahead bias)

Raport za okres konczacy sie 2020-12-31 **nie jest znany** 2020-12-31. Zmierzone na tych danych:
mediana opoznienia publikacji **35-58 dni**, maksimum **115 dni**.

BiznesRadar podaje w tabeli wiersz "Data publikacji" (`data-field="PrimaryReport"`), wiec panel
indeksuje wartosci po **dacie publikacji**, nie po koncu okresu. Dowod, ze dziala (test na
prawdziwych danych) - CD Projekt, raport za 2020 opublikowany 2021-04-22:

| data | TTM zysk netto, jaki strategia "zna" |
|---|---|
| 2021-04-21 | 279 019 tys. PLN |
| 2021-04-23 | **1 154 327 tys. PLN** |

4-krotny skok wiedzy w jeden dzien. Bez tego rozgraniczenia backtest podejmowalby decyzje na
danych z przyszlosci.

**Czego to NIE naprawia:** BiznesRadar pokazuje liczby po ewentualnych korektach (restatements) -
wyrownanie po dacie publikacji naprawia **timing**, nie **tresc**. Prawdziwa historia
point-in-time powstanie z czasem, bo `snapshots` trzyma `fetched_at`.

---

# Koncepcja v2: "quality value" (aktualna)

Uniwersum: **22 spolki GPW** (bez bankow i ubezpieczycieli): acp ale asb car cdr cps dnp dom dvl
kgh kru lpp lwb neu opl pep pge pkn rbw ten tpe txt.

    SCORE = 0.50 * DD + 0.25 * REL + 0.25 * QUALITY

- **DD** - percentyl obsuniecia od 52W high (najbardziej przeceniona ~100)
- **REL** - percentyl slabosci wzgledem rynku za 6M (najbardziej odstajaca w tyl ~100)
- **QUALITY** - 0/25/50/75/100, po 25 pkt za: zysk TTM > 0; CFO TTM > 0; CFO >= zysk;
  dlug/aktywa <= rok wczesniej

Bramka wejscia: `drawdown >= 25%` ORAZ `QUALITY >= 50`. Max 4 pozycje po 25%. Wolny slot -> najlepszy
kandydat. Portfel pelny -> podmiana najslabszej, gdy nowy ma score wyzszy o >= 10 pkt. Wyjscie:
fundamental fail albo max holding 24m; bez profit targetu. Decyzje raz w miesiacu.

## Wynik (okno 2006-03 -> 2026-08)

| | CAGR | MaxDD | Sharpe | Calmar |
|---|---|---|---|---|
| strategia (ekspozycja 97%) | 10.61% | -65.82% | 0.540 | 0.161 |
| buy&hold uniwersum (100%) | **14.56%** | -69.89% | **0.634** | **0.208** |
| buy&hold skalowany do 97%, zero timingu | **14.23%** | -68.75% | **0.634** | **0.207** |

**Strategia nie bije benchmarku** - ani na zwrocie, ani na miarach ryzyka. Poprawia jedynie MaxDD
(-65.8% vs -68.8%), i to nieznacznie. Jest to jednak **duzo blizej** niz koncepcja v1 (tam
stosunek CAGR do benchmarku byl 0.46, tu 0.75).

## Sweep 12 wariantow

| wariant | CAGR | MaxDD | Sharpe | Calmar | transakcji | ekspozycja |
|---|---|---|---|---|---|---|
| bazowa (24m, margin 10) | 10.61% | -65.82% | 0.540 | 0.161 | 114 | 97% |
| max holding 36m | 11.96% | -62.47% | 0.598 | 0.191 | 109 | 98% |
| max holding 12m | 8.97% | -57.65% | 0.477 | 0.156 | 129 | 90% |
| margin podmiany 0 | 10.56% | -65.82% | 0.543 | 0.161 | 140 | 97% |
| margin podmiany 20 | 8.82% | -67.65% | 0.474 | 0.130 | 93 | 97% |
| bramka dd >= 15% | 9.14% | -58.52% | 0.494 | 0.156 | 150 | 99% |
| bramka dd >= 35% | 7.68% | -68.90% | 0.428 | 0.112 | 70 | 82% |
| QUALITY >= 75 | 9.12% | -59.95% | 0.487 | 0.152 | 106 | 89% |
| **QUALITY >= 0 (bez bramki jakosci)** | **15.36%** | -63.63% | **0.694** | **0.241** | 129 | 100% |
| rebalans do 25% co miesiac | 10.42% | **-74.06%** | 0.503 | 0.141 | 114 | 97% |
| max 2 pozycje | 5.94% | -77.53% | 0.341 | 0.077 | 83 | 99% |
| max 6 pozycji | 11.25% | -67.99% | 0.612 | 0.165 | 125 | 92% |

## Najwazniejsze: dlaczego "QUALITY >= 0" to NIE odkrycie

Jedyny wariant bijacy benchmark (15.36% / Sharpe 0.694) to ten **bez bramki jakosci**. Wygladalo
to na realne odkrycie ("bramka jakosci szkodzi"), ale sprawdzenie pokazalo, ze to **artefakt
jednej spolki** - CD Projekt (86x w oknie). Bez bramki strategia kupuje CDR 13 razy, w tym w
momentach o QUALITY 0-25.

Wystarczylo usunac CDR z uniwersum (21 spolek zamiast 22), zeby wniosek sie odwrocil:

| | CAGR | MaxDD | Sharpe | Calmar |
|---|---|---|---|---|
| **z CDR** QUALITY>=50 | 10.61% | -65.82% | 0.540 | 0.161 |
| **z CDR** QUALITY>=0 | 15.36% | -63.63% | 0.694 | 0.241 |
| **z CDR** buy&hold | 14.56% | -69.89% | 0.634 | 0.208 |
| **bez CDR** QUALITY>=50 | 10.96% | -65.55% | 0.560 | 0.167 |
| **bez CDR** QUALITY>=0 | 12.31% | -63.53% | 0.594 | 0.194 |
| **bez CDR** buy&hold | **13.27%** | -70.39% | **0.607** | 0.189 |

Przewaga "bez bramki" nad "z bramka" spada z +4.75pp do +1.35pp, a przewaga nad benchmarkiem
(+0.80pp) zamienia sie w strate (-0.96pp). **Jedna spolka z 22 przewraca wniosek** - to miara
tego, jak krucha jest ta probka.

## Obserwacja strukturalna: regula podmiany to de facto szybkie wyjscie

Spec mowil "bez szybkiego profit targetu" i "max holding 24/36 miesiecy", ale w praktyce:

| powod wyjscia | udzial |
|---|---|
| podmiana (`replaced`) | **77%** (88/114) |
| fundamental fail | 11% (13) |
| timeout 24m | **8%** (9) |
| koniec danych | 4% (4) |

Mediana czasu trzymania: **182 dni**, 51% pozycji trzymane krocej niz 6 miesiecy. Limit 24 miesiecy
zadzialal 9 razy. Czyli **regula podmiany przejela role profit targetu**, ktorego spec chcial
uniknac - strategia realnie zachowuje sie jak miesieczna rotacja po obsunieciu, a nie jak
cierpliwy value. To najwazniejsza rozbieznosc miedzy intencja spec a jej faktycznym dzialaniem.

## Wnioski powtarzalne miedzy v1 i v2

1. **Dluzsze trzymanie jest lepsze** - v2: 12m -> 24m -> 36m daje 8.97% -> 10.61% -> 11.96%;
   v1: 3m -> 24m daje 2.38% -> 8.16%. Spojne w obu koncepcjach.
2. **Koncentracja szkodzi** - max 2 pozycje: CAGR 5.94% i MaxDD -77.5% (najgorszy wariant).
3. **Wymuszony rebalans do 25% co miesiac pogarsza MaxDD** (-65.8% -> -74.1%) przy tym samym CAGR.
4. **Bramka jakosci nie pomaga** (v2), choc w v1 filtr fundamentalny pomagal - roznica: w v1 byl
   jedynym filtrem, w v2 QUALITY jest juz w score, wiec bramka dubluje ten sam sygnal i tylko
   zawęża wybor.

## Ograniczenia (istotne)

- **Uniwersum to spolki, ktore PRZETRWALY do dzis** - brak spolek wycofanych z obrotu/upadlych.
  Zawyza to i strategie, i benchmark, ale najbardziej "kup przecenione", bo testujemy je wylacznie
  na przecenach, po ktorych nastapilo odbicie.
- **Brak WIG20**: `REL` liczony wzgledem rownowazonej sredniej uniwersum (fallback z jawnym
  ostrzezeniem w kazdym uruchomieniu). To NIE to samo co spec - dodatkowo taki REL jest czesciowo
  redundantny z DD (oba mierza slabosc wzgledem grupy). Wystarczy wrzucic `data/pl/wig20.txt`
  w formacie stooq, silnik uzyje go automatycznie.
- 114 transakcji w oknie 20 lat, portfel 4 z 22 spolek - probka mala, MaxDD ~-65% bardzo wysoki.
- Fundamenty: TTM z kwartalow (zweryfikowane, ze kwartaly sa jednostkowe - suma 4Q = wartosc
  roczna, 8/8 sprawdzonych par).
- `Debt` = oprocentowane zadluzenie (`Borrowings` biezace + dlugoterminowe), **bez leasingu** -
  leasing wszedl do bilansow z IFRS 16 (~2019) i jego wliczenie dawalo by sztuczny skok zadluzenia
  u kazdej spolki naraz w roku przejscia.

## Co dalej

1. **Wrzucic WIG20** - jedyna brakujaca czesc spec, i jedyny sposob, zeby REL byl niezaleznym
   sygnalem, a nie powtorzeniem DD.
2. **Poszerzyc uniwersum o spolki wycofane z obrotu** - bez tego kazdy wynik "value" jest zawyzony,
   a wnioski krucha (patrz test bez CDR).
3. **Rozstrzygnac konflikt regula-podmiany vs cierpliwe trzymanie** - albo podniesc margin i
   swiadomie trzymac dluzej, albo przyjac, ze to strategia rotacyjna i przestac ja opisywac jako
   value.

---

# Koncepcja v1: "przeceniona + zdrowa, profit target" (odrzucona)

Uniwersum 4 spolki (DNP, CDR, KGH, PKN), okno 2006-03 -> 2026-08. Bramka: dd <= -25% + zdrowe
fundamenty. Wyjscie: +20% od wejscia albo 6 miesiecy.

| | CAGR | MaxDD | Sharpe | Calmar |
|---|---|---|---|---|
| strategia (ekspozycja 31%) | 3.27% | -42.72% | 0.288 | 0.077 |
| buy&hold 4 spolki (100%) | 18.94% | -80.04% | 0.651 | 0.237 |
| **buy&hold skalowany do 31%, zero timingu** | **7.15%** | **-37.22%** | **0.651** | **0.192** |

**Koncepcja niszczy wartosc**: "trzymaj 31% tych spolek na stale, bez zadnego sygnalu" bije ja na
kazdej metryce. Statystyki transakcji wygladaly przy tym niewinnie (47 transakcji, 62% zyskownych,
srednio +6.08%) - dowod, ze sam "win rate" jest mylacym miernikiem.

Sweep 14 wariantow: (1) regula wyjscia ucina zwyciezcow (3m->24m: CAGR 2.38%->8.16%; +10%->+60%:
2.55%->5.91%); (2) filtr fundamentalny realnie pomagal (bez niego 1.98% / MaxDD -62%).
