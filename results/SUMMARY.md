# Wyniki wszystkich strategii (wygenerowane, patrz `engine_v2/generate_results.py`)

Posortowane wg Calmar. `combined_final` = portfel laczony (podatek 19% zalozony przez generator, nie czesc specyfikacji). Pelne dane (walk-forward/sensitivity/UK mapping/named_periods) w odpowiadajacym `results/<nazwa>.json`.

| Strategia | Tryb | CAGR | MaxDD | Sharpe | Calmar | Turnover/rok | UK mapping |
|---|---|---|---|---|---|---|---|
| `gpm_uk` | final | 5.92% | -8.76% | 0.742 | 0.676 | 3.66 | - |
| `gpm_mid_10_best17_a` | combined_final | 8.34% | -16.15% | 0.806 | 0.517 | 2.69 | fail (patrz JSON) |
| `gpm_mid_13_best17_a` | combined_final | 8.44% | -16.39% | 0.810 | 0.515 | 2.75 | fail (patrz JSON) |
| `gpm_best17_a` | combined_final | 7.51% | -15.05% | 0.750 | 0.499 | 3.02 | - |
| `gpm_uk_best17_a_uk` | combined_final | 7.64% | -15.65% | 0.713 | 0.488 | 2.60 | - |
| `combined_triple` | combined_final | 8.55% | -20.41% | 0.745 | 0.419 | 2.38 | - |
| `gtaa_agg6_mid_best17_a` | combined_final | 8.50% | -21.09% | 0.737 | 0.403 | 2.21 | fail (patrz JSON) |
| `best17_a_tlt_hedge` | combined_final | 10.65% | -26.86% | 0.743 | 0.397 | 1.14 | - |
| `best17_a` | final | 12.34% | -31.19% | 0.736 | 0.396 | 1.44 | fail (patrz JSON) |
| `gpm_mid_13` | final | 4.94% | -12.57% | 0.616 | 0.393 | 4.15 | PASS |
| `best17_a_all_weather_4` | combined_final | 9.00% | -23.04% | 0.754 | 0.390 | 1.50 | - |
| `synergy_v2` | final | 11.96% | -31.19% | 0.705 | 0.383 | 1.44 | - |
| `gtaa_agg6_best17_a` | combined_final | 7.76% | -21.02% | 0.700 | 0.369 | 2.26 | - |
| `gpm_mid_10` | final | 4.77% | -12.95% | 0.597 | 0.369 | 4.03 | PASS |
| `dual_momentum_best17_a` | combined_final | 8.40% | -22.82% | 0.693 | 0.368 | 1.81 | - |
| `vaa_g4_best17_a` | combined_final | 7.84% | -21.43% | 0.713 | 0.366 | 4.51 | - |
| `combined_best2` | combined_final | 8.90% | -24.40% | 0.683 | 0.365 | 3.92 | - |
| `best17_a_tlt_timing` | combined_final | 8.57% | -23.79% | 0.693 | 0.360 | 1.60 | - |
| `synergy_v1` | final | 10.62% | -29.99% | 0.659 | 0.354 | 1.36 | - |
| `best17_a_uk` | final | 10.94% | -31.10% | 0.636 | 0.352 | 1.80 | - |
| `dual_momentum_all_weather_4` | combined_final | 5.85% | -16.75% | 0.606 | 0.349 | 1.95 | - |
| `gtaa_agg6_mid` | final | 5.76% | -17.29% | 0.588 | 0.333 | 2.92 | fail (patrz JSON) |
| `gtaa_agg3_mid` | final | 7.03% | -21.16% | 0.552 | 0.332 | 3.64 | fail (patrz JSON) |
| `combined_best2_dynamic` | combined_final | 10.02% | -30.24% | 0.696 | 0.331 | 3.82 | - |
| `best17_a_gfm` | combined_final | 8.83% | -28.76% | 0.678 | 0.307 | 1.98 | - |
| `vaa_g4_all_weather_4` | combined_final | 5.79% | -19.01% | 0.638 | 0.305 | 4.76 | - |
| `the_one_all_weather_4` | combined_final | 6.17% | -20.95% | 0.582 | 0.295 | 3.89 | - |
| `all_weather_4_best17_b` | combined_final | 6.09% | -21.43% | 0.589 | 0.284 | 1.99 | - |
| `best17_a_best17_b` | combined_final | 8.09% | -30.28% | 0.632 | 0.267 | 1.75 | - |
| `all_weather_4` | final | 6.87% | -25.72% | 0.646 | 0.267 | 1.74 | - |
| `all_weather_4_gfm` | combined_final | 5.80% | -22.65% | 0.622 | 0.256 | 2.00 | - |
| `gpm_lite_7` | final | 3.50% | -14.02% | 0.421 | 0.249 | 4.07 | - |
| `dual_momentum_the_one` | combined_final | 5.40% | -22.03% | 0.494 | 0.245 | 4.35 | - |
| `vaa_g4_best17_b` | combined_final | 5.00% | -20.39% | 0.519 | 0.245 | 4.99 | - |
| `the_one_best17_b` | combined_final | 5.35% | -22.07% | 0.495 | 0.242 | 4.12 | - |
| `gtaa_agg3` | final | 4.79% | -20.82% | 0.420 | 0.230 | 3.81 | - |
| `vaa_g4_the_one` | combined_final | 4.92% | -21.60% | 0.454 | 0.228 | 6.91 | - |
| `dual_momentum_best17_b` | combined_final | 5.01% | -22.26% | 0.476 | 0.225 | 2.19 | - |
| `dual_momentum` | final | 4.99% | -22.49% | 0.464 | 0.222 | 2.28 | - |
| `gpm` | final | 3.43% | -15.93% | 0.448 | 0.215 | 4.34 | - |
| `dual_momentum_vaa_g4` | combined_final | 4.73% | -22.52% | 0.526 | 0.210 | 4.97 | - |
| `gfm_breadth` | final | 5.49% | -26.55% | 0.504 | 0.207 | 4.41 | - |
| `the_one` | final | 5.51% | -26.85% | 0.414 | 0.205 | 6.50 | - |
| `vaa_g4_gfm` | combined_final | 4.64% | -22.76% | 0.532 | 0.204 | 5.02 | - |
| `gfm` | final | 7.11% | -35.22% | 0.545 | 0.202 | 3.47 | - |
| `gtaa_agg6` | final | 4.42% | -21.97% | 0.479 | 0.201 | 3.00 | - |
| `dual_momentum_gfm` | combined_final | 5.02% | -25.73% | 0.514 | 0.195 | 2.33 | - |
| `the_one_gfm` | combined_final | 5.38% | -28.10% | 0.497 | 0.191 | 4.46 | - |
| `the_one_tlt_hedge` | combined_final | 4.68% | -28.15% | 0.390 | 0.166 | 5.30 | - |
| `best17_b` | final | 5.04% | -30.53% | 0.396 | 0.165 | 2.26 | - |
| `gfm_best17_b` | combined_final | 4.89% | -31.35% | 0.465 | 0.156 | 2.24 | - |
| `vaa_g4` | final | 4.39% | -28.19% | 0.420 | 0.156 | 7.79 | - |
| `bh_spy` | final | 7.89% | -54.54% | 0.495 | 0.145 | 0.05 | fail (patrz JSON) |
| `bh_vt` | final | 6.35% | -47.26% | 0.404 | 0.134 | 0.06 | fail (patrz JSON) |
| `daa_g4` | final | 3.50% | -32.01% | 0.318 | 0.109 | 7.64 | - |
| `daa_g4_keller` | final | 2.86% | -32.12% | 0.343 | 0.089 | 4.82 | - |
| `tlt_hedge` | final | 1.46% | -49.23% | 0.172 | 0.030 | 0.05 | - |
| `tlt_timing` | final | 0.13% | -45.89% | 0.067 | 0.003 | 3.12 | - |
