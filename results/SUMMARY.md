# Wyniki wszystkich strategii (wygenerowane, patrz `engine_v2/generate_results.py`)

Posortowane wg Calmar. `combined_final` = portfel laczony (podatek 19% zalozony przez generator, nie czesc specyfikacji). Pelne dane (walk-forward/sensitivity/UK mapping/named_periods) w odpowiadajacym `results/<nazwa>.json`.

| Strategia | Tryb | CAGR | MaxDD | Sharpe | Calmar | Turnover/rok | UK mapping |
|---|---|---|---|---|---|---|---|
| `gpm_uk` | final | 5.92% | -8.76% | 0.742 | 0.676 | 3.66 | - |
| `gpm_mid_10_best17_a_day10` | combined_final | 9.11% | -14.93% | 0.858 | 0.610 | 2.66 | fail (patrz JSON) |
| `gpm_best17_a` | combined_final | 8.00% | -13.22% | 0.793 | 0.605 | 3.06 | - |
| `gpm_mid_13_best17_a_day5` | combined_final | 8.71% | -14.51% | 0.824 | 0.600 | 2.72 | fail (patrz JSON) |
| `best17_a_tlt_hedge` | combined_final | 11.77% | -19.80% | 0.808 | 0.594 | 1.22 | - |
| `gpm_mid_10_best17_a_day15` | combined_final | 9.43% | -15.90% | 0.882 | 0.593 | 2.66 | fail (patrz JSON) |
| `gpm_mid_13_best17_a_day10` | combined_final | 9.36% | -15.84% | 0.873 | 0.591 | 2.72 | fail (patrz JSON) |
| `gpm_mid_13_best17_a_day15` | combined_final | 9.49% | -16.52% | 0.880 | 0.575 | 2.72 | fail (patrz JSON) |
| `gpm_mid_10_best17_a_day25` | combined_final | 9.69% | -17.25% | 0.900 | 0.562 | 2.70 | fail (patrz JSON) |
| `gpm_mid_13_best17_a_day25` | combined_final | 9.75% | -18.03% | 0.896 | 0.541 | 2.75 | fail (patrz JSON) |
| `gpm_mid_10_best17_a` | combined_final | 8.71% | -16.15% | 0.839 | 0.540 | 2.74 | fail (patrz JSON) |
| `gpm_mid_13_best17_a` | combined_final | 8.80% | -16.39% | 0.841 | 0.537 | 2.80 | fail (patrz JSON) |
| `gpm_uk_best17_a_uk` | combined_final | 8.40% | -15.65% | 0.758 | 0.537 | 2.60 | - |
| `gpm_mid_10_best17_a_day5` | combined_final | 8.61% | -16.18% | 0.822 | 0.532 | 2.66 | fail (patrz JSON) |
| `gpm_mid_10_best17_a_day20` | combined_final | 8.94% | -16.95% | 0.836 | 0.527 | 2.70 | fail (patrz JSON) |
| `gpm_mid_13_best17_a_day20` | combined_final | 9.00% | -17.28% | 0.833 | 0.521 | 2.75 | fail (patrz JSON) |
| `best17_a_day10` | final | 14.37% | -29.01% | 0.825 | 0.495 | 1.38 | fail (patrz JSON) |
| `best17_a_day25` | final | 15.68% | -31.69% | 0.878 | 0.495 | 1.45 | fail (patrz JSON) |
| `best17_a_day15` | final | 14.75% | -30.51% | 0.838 | 0.484 | 1.37 | fail (patrz JSON) |
| `best17_a_day5` | final | 13.61% | -28.58% | 0.788 | 0.476 | 1.38 | fail (patrz JSON) |
| `combined_best2_dynamic` | combined_final | 10.66% | -23.69% | 0.734 | 0.450 | 3.88 | - |
| `combined_triple` | combined_final | 8.98% | -20.28% | 0.774 | 0.443 | 2.42 | - |
| `best17_a_day20` | final | 14.00% | -31.71% | 0.795 | 0.441 | 1.45 | fail (patrz JSON) |
| `vaa_g4_best17_a` | combined_final | 8.32% | -19.09% | 0.750 | 0.436 | 4.56 | - |
| `best17_a` | final | 13.48% | -31.19% | 0.791 | 0.432 | 1.54 | fail (patrz JSON) |
| `gtaa_agg6_mid_best17_a` | combined_final | 8.95% | -21.09% | 0.766 | 0.425 | 2.25 | fail (patrz JSON) |
| `synergy_v2` | final | 13.10% | -31.19% | 0.759 | 0.420 | 1.54 | - |
| `gtaa_agg6_best17_a` | combined_final | 8.22% | -19.77% | 0.731 | 0.416 | 2.30 | - |
| `best17_a_uk` | final | 12.83% | -31.10% | 0.718 | 0.412 | 1.80 | - |
| `best17_a_all_weather_4` | combined_final | 9.48% | -23.04% | 0.784 | 0.411 | 1.55 | - |
| `combined_best2` | combined_final | 9.42% | -22.96% | 0.717 | 0.411 | 3.97 | - |
| `gpm_mid_13` | final | 4.94% | -12.57% | 0.616 | 0.393 | 4.15 | PASS |
| `best17_a_tlt_timing` | combined_final | 9.31% | -23.79% | 0.744 | 0.391 | 1.67 | - |
| `dual_momentum_best17_a` | combined_final | 8.92% | -22.82% | 0.728 | 0.391 | 1.86 | - |
| `gpm_mid_10_day15` | final | 4.94% | -12.96% | 0.603 | 0.381 | 4.03 | PASS |
| `best17_a_qqq` | final | 11.69% | -31.62% | 0.715 | 0.369 | 1.56 | fail (patrz JSON) |
| `gpm_mid_10` | final | 4.77% | -12.95% | 0.597 | 0.369 | 4.03 | PASS |
| `gpm_mid_13_day10` | final | 5.34% | -15.01% | 0.646 | 0.356 | 4.15 | PASS |
| `gpm_mid_10_defensive_best17_a_offensive` | combined_final | 7.36% | -20.81% | 0.756 | 0.354 | 1.99 | PASS |
| `gpm_mid_10_day10` | final | 4.87% | -13.78% | 0.595 | 0.353 | 4.03 | PASS |
| `synergy_v1` | final | 10.55% | -29.99% | 0.658 | 0.352 | 1.56 | - |
| `dual_momentum_all_weather_4` | combined_final | 5.85% | -16.75% | 0.606 | 0.349 | 1.95 | - |
| `gpm_mid_13_day15` | final | 5.06% | -14.56% | 0.614 | 0.347 | 4.15 | PASS |
| `gpm_mid_13_day5` | final | 4.54% | -13.47% | 0.561 | 0.337 | 4.15 | PASS |
| `gtaa_agg6_mid` | final | 5.76% | -17.29% | 0.588 | 0.333 | 2.92 | fail (patrz JSON) |
| `gpm_mid_10_day5` | final | 4.36% | -13.12% | 0.543 | 0.332 | 4.03 | PASS |
| `gtaa_agg3_mid` | final | 7.03% | -21.16% | 0.552 | 0.332 | 3.64 | fail (patrz JSON) |
| `gpm_mid_13_day25` | final | 4.74% | -14.27% | 0.578 | 0.332 | 4.15 | PASS |
| `gpm_mid_10_day25` | final | 4.59% | -13.91% | 0.563 | 0.330 | 4.03 | PASS |
| `best17_a_gfm` | combined_final | 9.37% | -28.76% | 0.709 | 0.326 | 2.03 | - |
| `best17_a_offensive` | final | 11.10% | -35.33% | 0.655 | 0.314 | 0.69 | fail (patrz JSON) |
| `gpm_mid_10_day20` | final | 4.59% | -14.89% | 0.564 | 0.309 | 4.03 | PASS |
| `gpm_mid_13_cash` | final | 3.63% | -11.79% | 0.516 | 0.308 | 3.61 | PASS |
| `vaa_g4_all_weather_4` | combined_final | 5.79% | -19.01% | 0.638 | 0.305 | 4.76 | - |
| `gpm_mid_13_day20` | final | 4.74% | -15.61% | 0.578 | 0.304 | 4.15 | PASS |
| `the_one_all_weather_4` | combined_final | 6.17% | -20.95% | 0.582 | 0.295 | 3.89 | - |
| `all_weather_4_best17_b` | combined_final | 6.09% | -21.43% | 0.589 | 0.284 | 1.99 | - |
| `best17_a_best17_b` | combined_final | 8.56% | -30.28% | 0.662 | 0.283 | 1.80 | - |
| `gpm_mid_10_cash` | final | 3.49% | -12.56% | 0.499 | 0.278 | 3.43 | PASS |
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
| `gpm_mid_10_defensive` | final | 3.42% | -16.45% | 0.520 | 0.208 | 3.58 | PASS |
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
