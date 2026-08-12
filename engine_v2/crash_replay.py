"""
CRASH REPLAY - symulacja hipotetycznego krachu na strategii/portfelu LACZONYM, budowana z
REALNEGO wzorca zwrotow z przeszlosci (np. GFC 2008), "doklejonego" do dzisiejszych (ostatnich
realnych) cen kazdego tickera - user: "chcialbym zebys jakos zasymulowal krach ktory wlasnie
teraz sie wydarza - i zeby przypominal ten z 2008 - moze to jakis nowy tryb", potem: "i moze ten
tryb dzialac tak ze tylko co miesiac generuje dane a nie dzienne - bedzie latwiej".

Mechanizm (MIESIECZNA granulacja - jeden syntetyczny wiersz na miesiac, nie dzienny replay):
  1. Dla kazdego tickera w uniwersum - realne ceny resamplowane do cen wykonania miesiaca
     (`nth_trading_day_prices`, `day_of_month=1`) w OKNIE REFERENCYJNYM (np. `gfc_crash` z
     `named_periods.py`) - to daje sekwencje PRAWDZIWYCH miesiecznych zwrotow z tamtego kryzysu.
  2. Ostatnia realna (dzienna) cena kazdego tickera = punkt startowy syntetycznej przyszlosci.
  3. Syntetyczne miesiace (jeden wiersz/miesiac, dzien roboczy nastepujacy po ostatnim realnym
     dniu, potem +1 miesiac kalendarzowy za kazdym razem) - cena = poprzednia cena * (1 + ten
     sam zwrot % co w oknie referencyjnym, w tej samej kolejnosci).
  4. Real + synthetic zapisywane jako jeden plik .txt w formacie stooq (jak `data/us/nyse/*.txt`)
     do TYMCZASOWEGO katalogu - pipeline (loader/wskazniki/execution) NIE WIE, ze dane sa
     syntetyczne, dziala w 100% swoja normalna, juz przetestowana logika (kanarek, gate'y,
     breadth-protective, histereza) - to jest clue tego podejscia: nie symulujemy WYNIKU
     strategii, tylko podajemy jej SYNTETYCZNE DANE WEJSCIOWE i pozwalamy jej samej zdecydowac.

Dla strategii LACZONYCH (`combined_spec.json`) - kazda skladowa strategia dostaje WLASNA,
zmodyfikowana kopie swojego `strategy_spec.json` (loader wymuszony na `stooq_csv` + nowy
`data_dir`, reszta bez zmian) w TYMCZASOWYM katalogu, ktory mirroruje strukture `strategies_v2/`
(kazda skladowa we WLASNYM podkatalogu, ten sam wzgledny layout co `combined_spec.strategy_spec_paths`
oczekuje) - `run_combined_pipeline` dziala WIEC BEZ ZADNYCH ZMIAN, uzywajac normalnego combinera
(np. `fixed_capital_weights`) na tych podmienionych danych.

Uproszczenie: wymusza plain `stooq_csv` (nie `stooq_csv_dividend_adjusted`) dla wszystkich
skladowych - unika komplikacji z syntetycznymi danymi UK dla korekty dywidend, nieistotne dla
kierunkowego stress-testu.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY
from engine_v2.combined_pipeline import run_combined_pipeline
from engine_v2.combined_spec import CombinedSpec
from engine_v2.metrics import compute_metrics
from engine_v2.named_periods import KNOWN_PERIODS
from engine_v2.period_anchor import nth_trading_day_prices
from engine_v2.pipeline import run_strategy_pipeline
from engine_v2.spec import StrategySpec


def resolve_reference_window(reference) -> tuple[str, str]:
    """`reference` moze byc nazwa znanego okresu z `named_periods.KNOWN_PERIODS` (np.
    "gfc_crash") albo para (start, end) w formacie ISO."""
    if isinstance(reference, str):
        if reference not in KNOWN_PERIODS:
            raise ValueError(
                f"crash_replay: nieznany named_period '{reference}' (dostepne: {sorted(KNOWN_PERIODS)})."
            )
        period = KNOWN_PERIODS[reference]
        return period["start"], period["end"]
    start, end = reference
    return start, end


def extract_reference_monthly_returns(
    daily_prices: pd.DataFrame, reference_start: str, reference_end: str
) -> pd.DataFrame:
    """Miesieczne zwroty (execution-day, day_of_month=1) KAZDEGO tickera w oknie referencyjnym -
    kolumny = tickery, index = miesiace okna (pierwszy wiersz = NaN, brak poprzedniego miesiaca
    do policzenia zwrotu - odrzucany przez wolajacego)."""
    monthly_prices = nth_trading_day_prices(daily_prices, day_of_month=1)
    window = monthly_prices[
        (monthly_prices.index >= pd.Timestamp(reference_start)) & (monthly_prices.index <= pd.Timestamp(reference_end))
    ]
    if len(window) < 2:
        raise ValueError(
            f"crash_replay: okno referencyjne [{reference_start}, {reference_end}] ma < 2 "
            f"miesiecznych punktow w dostepnych danych - nie da sie policzyc zwrotow."
        )
    return window.pct_change().iloc[1:]


def build_replay_price_series(
    daily_price_series: pd.Series, reference_returns: pd.Series
) -> pd.Series:
    """Real + syntetyczne wiersze dla JEDNEGO tickera: syntetyczny miesiac N ma cene
    = (cena poprzedniego wiersza) * (1 + reference_returns.iloc[N]) - NaN zwroty (ticker bez
    danych w danym miesiacu okna referencyjnego u INNEGO tickera z tej samej strategii) pomijane
    (cena zostaje bez zmian ten miesiac, 0% - bezpieczny fallback, nie zgadujemy)."""
    real = daily_price_series.dropna()
    if real.empty:
        raise ValueError("crash_replay: pusta seria cen - brak realnych danych.")

    last_real_date = real.index.max()
    last_real_price = real.loc[last_real_date]

    synthetic_dates = []
    current = pd.Timestamp(last_real_date)
    for _ in range(len(reference_returns)):
        current = current + pd.DateOffset(months=1)
        # najblizszy dzien roboczy NA/PO tej dacie - unika weekendow w syntetycznym kalendarzu
        while current.weekday() >= 5:
            current = current + pd.Timedelta(days=1)
        synthetic_dates.append(current)

    prices = [last_real_price]
    for r in reference_returns.values:
        step = 0.0 if pd.isna(r) else float(r)
        prices.append(prices[-1] * (1.0 + step))
    synthetic_prices = prices[1:]

    synthetic_series = pd.Series(synthetic_prices, index=pd.DatetimeIndex(synthetic_dates))
    return pd.concat([real, synthetic_series])


def _write_stooq_txt(ticker: str, price_series: pd.Series, path: Path) -> None:
    lines = ["<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>"]
    ticker_label = ticker.upper()
    for date, price in price_series.items():
        date_str = pd.Timestamp(date).strftime("%Y%m%d")
        lines.append(f"{ticker_label},D,{date_str},000000,{price},{price},{price},{price},0,0")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_component_replay(
    strategy_spec: StrategySpec, reference_start: str, reference_end: str, dest_data_dir: Path
) -> pd.Timestamp:
    """Zwraca NAJPOZNIEJSZA z 'ostatnich realnych dat' po tickerach tej skladowej - granica
    real/synthetic (potrzebna do wyciecia okna repliki PO fakcie, bo raz zapisane pliki .txt nie
    rozrozniaja juz realnych/syntetycznych wierszy)."""
    dest_data_dir.mkdir(parents=True, exist_ok=True)
    daily_params = dict(strategy_spec.base_params.get("data_loader", {}))
    daily_params["frequency"] = "daily"
    daily_prices = DATA_LOADER_REGISTRY[strategy_spec.blocks["data_loader"]](
        strategy_spec.universe, daily_params
    ).prices

    reference_returns = extract_reference_monthly_returns(daily_prices, reference_start, reference_end)

    last_real_dates = []
    for ticker in strategy_spec.universe:
        real = daily_prices[ticker].dropna()
        last_real_dates.append(real.index.max())
        extended = build_replay_price_series(daily_prices[ticker], reference_returns[ticker])
        _write_stooq_txt(ticker, extended, dest_data_dir / f"{ticker}.txt")

    return max(last_real_dates)


def _write_component_spec_copy(strategy_spec: StrategySpec, dest_dir: Path, data_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    spec_dict = {
        "name": strategy_spec.name,
        "hypothesis": strategy_spec.hypothesis,
        "universe": strategy_spec.universe,
        "blocks": dict(strategy_spec.blocks),
        "base_params": json.loads(json.dumps(strategy_spec.base_params)),
        "allowed_param_families": strategy_spec.allowed_param_families,
        "created_at": strategy_spec.created_at,
    }
    spec_dict["blocks"]["data_loader"] = "stooq_csv"
    spec_dict["base_params"]["data_loader"] = {"data_dir": str(data_dir), "frequency": "monthly"}
    (dest_dir / "strategy_spec.json").write_text(json.dumps(spec_dict, indent=2, ensure_ascii=False), encoding="utf-8")


def run_crash_replay_single(strategy_dir: Path, reference, workspace_dir: Path) -> Dict[str, Any]:
    """Replay dla POJEDYNCZEJ strategii (`strategy_spec.json`). Zwraca metryki + alokacje
    miesiac po miesiacu w oknie repliki (od pierwszego syntetycznego miesiaca)."""
    reference_start, reference_end = resolve_reference_window(reference)
    strategy_spec = StrategySpec.load(strategy_dir / "strategy_spec.json")

    data_dir = workspace_dir / "data"
    sim_start = _build_component_replay(strategy_spec, reference_start, reference_end, data_dir)

    spec_copy_dir = workspace_dir / strategy_dir.name
    _write_component_spec_copy(strategy_spec, spec_copy_dir, data_dir)
    replay_spec = StrategySpec.load(spec_copy_dir / "strategy_spec.json")

    final_portfolio = run_strategy_pipeline(replay_spec)
    daily_prices = DATA_LOADER_REGISTRY["stooq_csv"](
        replay_spec.universe, {"data_dir": str(data_dir), "frequency": "daily"}
    ).prices

    return _summarize_replay(final_portfolio, daily_prices, strategy_spec.universe[0], sim_start)


def run_crash_replay_combined(combined_dir: Path, reference, workspace_dir: Path) -> Dict[str, Any]:
    """Replay dla strategii LACZONEJ (`combined_spec.json`) - kazda skladowa dostaje wlasny,
    podmieniony `strategy_spec.json` w `workspace_dir`, ktory mirroruje layout `strategies_v2/`
    (relatywne `strategy_spec_paths` w skopiowanym `combined_spec.json` dzialaja bez zmian)."""
    reference_start, reference_end = resolve_reference_window(reference)
    combined_spec = CombinedSpec.load(combined_dir / "combined_spec.json")

    data_dir = workspace_dir / "data"
    benchmark_ticker = None
    sim_starts = []
    for rel_path in combined_spec.strategy_spec_paths:
        strategy_spec = StrategySpec.load(combined_dir / rel_path)
        sim_starts.append(_build_component_replay(strategy_spec, reference_start, reference_end, data_dir))
        component_name = Path(rel_path).parent.name
        _write_component_spec_copy(strategy_spec, workspace_dir / component_name, data_dir)
        if benchmark_ticker is None:
            benchmark_ticker = strategy_spec.universe[0]
    sim_start = max(sim_starts)

    combined_dest_dir = workspace_dir / combined_dir.name
    combined_dest_dir.mkdir(parents=True, exist_ok=True)
    (combined_dest_dir / "combined_spec.json").write_text(
        json.dumps(
            {
                "name": combined_spec.name,
                "hypothesis": combined_spec.hypothesis,
                "strategy_spec_paths": combined_spec.strategy_spec_paths,
                "combiner": combined_spec.combiner,
                "combiner_params": combined_spec.combiner_params,
                "reporting": combined_spec.reporting,
                "reporting_params": combined_spec.reporting_params,
                "created_at": combined_spec.created_at,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    replay_spec = CombinedSpec.load(combined_dest_dir / "combined_spec.json")

    final_portfolio = run_combined_pipeline(replay_spec, combined_dest_dir)
    universe = sorted(
        {
            t
            for rel_path in combined_spec.strategy_spec_paths
            for t in StrategySpec.load(combined_dir / rel_path).universe
        }
    )
    daily_prices = DATA_LOADER_REGISTRY["stooq_csv"](
        universe, {"data_dir": str(data_dir), "frequency": "daily"}
    ).prices

    return _summarize_replay(final_portfolio, daily_prices, benchmark_ticker, sim_start)


def _summarize_replay(
    final_portfolio: pd.DataFrame,
    daily_prices: pd.DataFrame,
    benchmark_ticker: str,
    sim_start: pd.Timestamp,
) -> Dict[str, Any]:
    """Metryki strategii + naiwnego buy&hold benchmarku (pierwszy ticker uniwersum pierwszej
    skladowej) na SAMYM oknie repliki (od `sim_start` - granica real/synthetic, patrz
    `_build_component_replay` - PRZED nia dane sa 100% realne, nie mozna jej odtworzyc z gotowych
    plikow .txt, wiec musi byc przekazana explicit przez wolajacego).

    Rownowa strategii liczymy z WLASNYCH miesiecznych `net_return` z `final_portfolio` (cumprod),
    NIE przez `backtest_engine.daily_equity_curve` - ta druga zaklada gesta, faktycznie dzienna
    serie cen (dnia po dniu wewnatrz okresu), a nasza syntetyczna seria ma z definicji JEDEN
    wiersz/miesiac (patrz docstring modulu) - `daily_equity_curve` w takim przypadku widzi tylko
    1 punkt na okres i CICHO gubi caly zwrot tego miesiaca (brak drugiego punktu w okresie, wiec
    nigdy nie liczy zadnego stosunku cen). `net_return` jest juz policzony poprawnie przez
    execution (na PRAWDZIWYCH cenach wykonania miesiaca, real czy syntetycznych), wiec to jest
    jedyne poprawne miejsce do zbudowania miesiecznej equity repliki."""
    fp = final_portfolio.sort_values("date").reset_index(drop=True)
    split_label = pd.Timestamp(year=sim_start.year, month=sim_start.month, day=1)
    if fp[fp["date"] <= split_label].empty:
        raise ValueError("crash_replay: final_portfolio nie ma zadnego wiersza sprzed repliki - sprawdz dane wejsciowe.")
    fp_replay = fp[fp["date"] > split_label].reset_index(drop=True)
    if fp_replay.empty:
        raise ValueError("crash_replay: final_portfolio nie ma zadnego syntetycznego wiersza po repliki - sprawdz okno referencyjne.")

    replay_equity = (1.0 + fp_replay["net_return"]).cumprod()
    ec_replay = pd.concat(
        [
            pd.DataFrame({"date": [split_label], "equity": [1.0]}),
            pd.DataFrame({"date": fp_replay["date"], "equity": replay_equity}),
        ],
        ignore_index=True,
    )

    bench = daily_prices[benchmark_ticker]
    bench_sim = bench[bench.index >= sim_start]
    bench_sim = bench_sim / bench_sim.iloc[0]

    strategy_return = float(ec_replay["equity"].iloc[-1] - 1.0)
    strategy_trough = float(ec_replay["equity"].min() - 1.0)
    bench_return = float(bench_sim.iloc[-1] - 1.0)
    bench_trough = float(bench_sim.min() - 1.0)

    # equity_curve repliki jest z definicji MIESIECZNA (jeden wiersz/miesiac) - compute_metrics
    # annualizuje Sharpe wg `trading_days_per_year`, wiec musi dostac 12, nie domyslne 252
    # (inaczej Sharpe/CAGR bylyby liczone jakby te miesieczne skoki byly dziennymi zwrotami).
    strategy_metrics = (
        compute_metrics(ec_replay, fp_replay, {"trading_days_per_year": 12}) if len(fp_replay) > 1 else None
    )

    monthly_allocations = []
    for _, row in fp_replay.iterrows():
        weights = json.loads(row["weights_used_json"])
        held = {t: round(w, 4) for t, w in weights.items() if w > 1e-4}
        monthly_allocations.append({"date": row["date"].strftime("%Y-%m-%d"), "weights": held})

    return {
        "replay_start": split_label.strftime("%Y-%m-%d"),
        "replay_end": fp_replay["date"].iloc[-1].strftime("%Y-%m-%d"),
        "strategy_return": strategy_return,
        "strategy_trough": strategy_trough,
        "strategy_metrics": strategy_metrics,
        "benchmark_ticker": benchmark_ticker,
        "benchmark_return": bench_return,
        "benchmark_trough": bench_trough,
        "monthly_allocations": monthly_allocations,
    }


def run_crash_replay(spec_dir: Path, reference="gfc_crash", workspace_dir: Path | None = None) -> Dict[str, Any]:
    """Punkt wejscia - wykrywa, czy `spec_dir` to pojedyncza (`strategy_spec.json`) czy laczona
    (`combined_spec.json`) strategia, buduje tymczasowy workspace i odpala replay. `workspace_dir`
    domyslnie tymczasowy katalog USUWANY po zakonczeniu (chyba ze podany explicit - przydatne w
    testach do inspekcji wygenerowanych plikow)."""
    cleanup = workspace_dir is None
    if workspace_dir is None:
        import tempfile

        workspace_dir = Path(tempfile.mkdtemp(prefix="crash_replay_"))
    try:
        if (spec_dir / "combined_spec.json").exists():
            return run_crash_replay_combined(spec_dir, reference, workspace_dir)
        if (spec_dir / "strategy_spec.json").exists():
            return run_crash_replay_single(spec_dir, reference, workspace_dir)
        raise ValueError(f"crash_replay: {spec_dir} nie ma ani strategy_spec.json ani combined_spec.json.")
    finally:
        if cleanup:
            shutil.rmtree(workspace_dir, ignore_errors=True)
