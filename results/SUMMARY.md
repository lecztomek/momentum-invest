# Wyniki wszystkich strategii (wygenerowane, patrz `engine_v2/generate_results.py`)

Posortowane wg Calmar. `combined_final` = portfel laczony (podatek 19% zalozony przez generator, nie czesc specyfikacji). Pelne dane (walk-forward/sensitivity/UK mapping/named_periods) w odpowiadajacym `results/<nazwa>.json`.

| Strategia | Tryb | CAGR | MaxDD | Sharpe | Calmar | Turnover/rok | UK mapping |
|---|---|---|---|---|---|---|---|
| `gpm_best17_a` | combined_final | 10.38% | -13.22% | 1.011 | 0.786 | 2.90 | - |
| `gpm_mid_10_best17_a` | combined_final | 10.49% | -14.65% | 0.997 | 0.716 | 2.74 | fail (patrz JSON) |
| `vaa_g4_best17_a` | combined_final | 11.37% | -18.09% | 0.995 | 0.629 | 4.39 | - |
| `best17_a_tlt_hedge` | combined_final | 13.77% | -22.09% | 0.929 | 0.623 | 0.97 | - |
| `combined_triple` | combined_final | 11.37% | -20.75% | 0.961 | 0.548 | 2.27 | - |
| `combined_best2` | combined_final | 12.41% | -22.73% | 0.914 | 0.546 | 3.79 | - |
| `gtaa_agg6_best17_a` | combined_final | 10.42% | -19.44% | 0.910 | 0.536 | 2.14 | - |
| `best17_a` | final | 16.32% | -31.19% | 0.930 | 0.523 | 1.16 | fail (patrz JSON) |
| `combined_best2_dynamic` | combined_final | 13.79% | -26.61% | 0.918 | 0.518 | 3.68 | - |
| `synergy_v2` | final | 15.84% | -31.19% | 0.890 | 0.508 | 1.16 | - |
| `best17_a_all_weather_4` | combined_final | 11.66% | -23.20% | 0.949 | 0.502 | 1.38 | - |
| `vaa_g4_all_weather_4` | combined_final | 8.42% | -17.22% | 0.899 | 0.489 | 4.76 | - |
| `dual_momentum_best17_a` | combined_final | 11.06% | -22.79% | 0.881 | 0.485 | 1.68 | - |
| `best17_a_tlt_timing` | combined_final | 11.51% | -23.87% | 0.896 | 0.482 | 1.41 | - |
| `synergy_v1` | final | 14.17% | -29.99% | 0.837 | 0.472 | 1.07 | - |
| `the_one_all_weather_4` | combined_final | 8.52% | -18.63% | 0.774 | 0.457 | 3.89 | - |
| `vaa_g4_the_one` | combined_final | 8.07% | -17.85% | 0.694 | 0.452 | 6.91 | - |
| `dual_momentum_all_weather_4` | combined_final | 7.49% | -16.71% | 0.757 | 0.448 | 1.95 | - |
| `vaa_g4_best17_b` | combined_final | 7.57% | -17.87% | 0.750 | 0.423 | 4.99 | - |
| `dual_momentum_vaa_g4` | combined_final | 7.22% | -17.34% | 0.770 | 0.416 | 4.97 | - |
| `gpm` | final | 5.39% | -13.00% | 0.675 | 0.414 | 4.34 | - |
| `dual_momentum_the_one` | combined_final | 7.73% | -18.92% | 0.674 | 0.408 | 4.35 | - |
| `gpm_mid_10` | final | 5.30% | -13.04% | 0.683 | 0.406 | 4.39 | fail (patrz JSON) |
| `best17_a_gfm` | combined_final | 11.62% | -29.15% | 0.858 | 0.399 | 1.85 | - |
| `gpm_lite_7` | final | 5.47% | -13.91% | 0.627 | 0.393 | 4.07 | - |
| `vaa_g4_gfm` | combined_final | 7.07% | -18.23% | 0.778 | 0.388 | 5.02 | - |
| `the_one` | final | 8.56% | -22.98% | 0.591 | 0.373 | 6.50 | - |
| `the_one_best17_b` | combined_final | 7.63% | -20.89% | 0.674 | 0.365 | 4.12 | - |
| `all_weather_4_best17_b` | combined_final | 7.82% | -21.65% | 0.734 | 0.361 | 1.99 | - |
| `best17_a_best17_b` | combined_final | 10.66% | -30.31% | 0.804 | 0.352 | 1.63 | - |
| `vaa_g4` | final | 7.98% | -22.84% | 0.705 | 0.349 | 7.79 | - |
| `all_weather_4_gfm` | combined_final | 7.40% | -21.32% | 0.775 | 0.347 | 2.00 | - |
| `gtaa_agg3` | final | 6.77% | -19.69% | 0.563 | 0.344 | 3.81 | - |
| `all_weather_4` | final | 8.63% | -25.54% | 0.793 | 0.338 | 1.74 | - |
| `the_one_gfm` | combined_final | 7.69% | -23.39% | 0.677 | 0.329 | 4.46 | - |
| `gtaa_agg6` | final | 6.18% | -19.06% | 0.645 | 0.324 | 3.00 | - |
| `dual_momentum` | final | 6.53% | -20.32% | 0.583 | 0.321 | 2.28 | - |
| `dual_momentum_best17_b` | combined_final | 6.58% | -20.97% | 0.602 | 0.314 | 2.19 | - |
| `the_one_tlt_hedge` | combined_final | 7.20% | -24.03% | 0.555 | 0.300 | 5.28 | - |
| `dual_momentum_gfm` | combined_final | 6.53% | -22.26% | 0.649 | 0.293 | 2.33 | - |
| `gfm` | final | 9.22% | -31.72% | 0.680 | 0.291 | 3.47 | - |
| `daa_g4` | final | 6.49% | -24.43% | 0.523 | 0.265 | 7.64 | - |
| `gfm_best17_b` | combined_final | 6.40% | -28.55% | 0.587 | 0.224 | 2.24 | - |
| `best17_b` | final | 6.65% | -29.71% | 0.495 | 0.224 | 2.26 | - |
| `tlt_hedge` | final | 2.23% | -46.48% | 0.224 | 0.048 | 0.05 | - |
| `tlt_timing` | final | 1.59% | -40.22% | 0.199 | 0.040 | 3.12 | - |
