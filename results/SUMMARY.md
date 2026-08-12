# Wyniki wszystkich strategii (wygenerowane, patrz `engine_v2/generate_results.py`)

Posortowane wg Calmar. `combined_final` = portfel laczony (podatek 19% zalozony przez generator, nie czesc specyfikacji). Pelne dane (walk-forward/sensitivity/UK mapping/named_periods) w odpowiadajacym `results/<nazwa>.json`.

| Strategia | Tryb | CAGR | MaxDD | Sharpe | Calmar | Turnover/rok | UK mapping |
|---|---|---|---|---|---|---|---|
| `best17_a_tlt_hedge` | combined_final | 14.12% | -19.80% | 0.881 | 0.713 | 1.45 | - |
| `gpm_uk` | final | 5.92% | -8.76% | 0.742 | 0.676 | 3.66 | - |
| `gpm_mid_13_best17_a_day10` | combined_final | 9.48% | -14.59% | 0.865 | 0.649 | 2.74 | fail (patrz JSON) |
| `gpm_mid_10_best17_a_day10` | combined_final | 9.20% | -14.36% | 0.848 | 0.641 | 2.65 | fail (patrz JSON) |
| `gpm_mid_13_best17_a_day5` | combined_final | 8.96% | -14.51% | 0.828 | 0.618 | 2.74 | fail (patrz JSON) |
| `gpm_best17_a` | combined_final | 8.27% | -13.55% | 0.803 | 0.611 | 3.12 | - |
| `gpm_mid_10_best17_a_day15` | combined_final | 9.58% | -15.90% | 0.877 | 0.602 | 2.65 | fail (patrz JSON) |
| `gpm_uk_best17_a_uk` | combined_final | 9.41% | -15.65% | 0.787 | 0.602 | 2.66 | - |
| `gpm_mid_13_best17_a_day15` | combined_final | 9.76% | -16.52% | 0.884 | 0.591 | 2.74 | fail (patrz JSON) |
| `gpm_mid_10_best17_a_day25` | combined_final | 9.79% | -17.25% | 0.891 | 0.568 | 2.69 | fail (patrz JSON) |
| `gpm_mid_13_best17_a` | combined_final | 9.15% | -16.39% | 0.853 | 0.558 | 2.82 | fail (patrz JSON) |
| `gpm_mid_10_best17_a` | combined_final | 9.02% | -16.15% | 0.848 | 0.558 | 2.73 | fail (patrz JSON) |
| `gpm_mid_13_best17_a_day25` | combined_final | 9.95% | -18.03% | 0.895 | 0.552 | 2.78 | fail (patrz JSON) |
| `gpm_mid_10_best17_a_day5` | combined_final | 8.83% | -16.18% | 0.824 | 0.546 | 2.65 | fail (patrz JSON) |
| `gpm_mid_13_best17_a_day20` | combined_final | 9.28% | -17.28% | 0.840 | 0.537 | 2.78 | fail (patrz JSON) |
| `gpm_mid_10_best17_a_day20` | combined_final | 9.06% | -16.95% | 0.829 | 0.534 | 2.69 | fail (patrz JSON) |
| `gpm_uk_best17_a` | combined_final | 9.94% | -19.21% | 0.791 | 0.517 | 2.50 | - |
| `best17_a_day10` | final | 14.37% | -29.01% | 0.825 | 0.495 | 1.38 | fail (patrz JSON) |
| `best17_a_day25` | final | 15.68% | -31.69% | 0.878 | 0.495 | 1.45 | fail (patrz JSON) |
| `best17_a_day15` | final | 14.75% | -30.51% | 0.838 | 0.484 | 1.37 | fail (patrz JSON) |
| `best17_a_day5` | final | 13.61% | -28.58% | 0.788 | 0.476 | 1.38 | fail (patrz JSON) |
| `combined_best2_dynamic` | combined_final | 11.26% | -23.69% | 0.754 | 0.475 | 4.08 | - |
| `best17_a_tlt_timing` | combined_final | 11.07% | -23.79% | 0.810 | 0.465 | 1.85 | - |
| `combined_triple` | combined_final | 9.34% | -20.28% | 0.766 | 0.461 | 2.63 | - |
| `gtaa_agg6_mid_best17_a` | combined_final | 9.59% | -21.09% | 0.799 | 0.455 | 2.28 | fail (patrz JSON) |
| `gtaa_agg6_best17_a` | combined_final | 8.85% | -19.77% | 0.765 | 0.448 | 2.34 | - |
| `vaa_g4_best17_a` | combined_final | 8.50% | -19.09% | 0.740 | 0.446 | 4.75 | - |
| `best17_a_day20` | final | 14.00% | -31.71% | 0.795 | 0.441 | 1.45 | fail (patrz JSON) |
| `combined_best2` | combined_final | 9.95% | -22.96% | 0.736 | 0.434 | 4.17 | - |
| `best17_a` | final | 13.48% | -31.19% | 0.791 | 0.432 | 1.54 | fail (patrz JSON) |
| `synergy_v2` | final | 13.10% | -31.19% | 0.759 | 0.420 | 1.54 | - |
| `dual_momentum_best17_a` | combined_final | 9.56% | -22.82% | 0.760 | 0.419 | 1.91 | - |
| `best17_a_all_weather_4` | combined_final | 9.54% | -23.04% | 0.759 | 0.414 | 1.60 | - |
| `best17_a_uk` | final | 12.83% | -31.10% | 0.718 | 0.412 | 1.80 | - |
| `gpm_mid_13` | final | 4.94% | -12.57% | 0.616 | 0.393 | 4.15 | PASS |
| `best17_a_gfm` | combined_final | 11.18% | -28.76% | 0.751 | 0.389 | 2.24 | - |
| `gpm_mid_10_day15` | final | 4.94% | -12.96% | 0.603 | 0.381 | 4.03 | PASS |
| `gpm_mid_10_defensive_best17_a_offensive` | combined_final | 7.77% | -20.81% | 0.773 | 0.373 | 2.11 | PASS |
| `best17_a_qqq` | final | 11.69% | -31.62% | 0.715 | 0.369 | 1.56 | fail (patrz JSON) |
| `gpm_mid_10` | final | 4.77% | -12.95% | 0.597 | 0.369 | 4.03 | PASS |
| `gpm_mid_13_day10` | final | 5.34% | -15.01% | 0.646 | 0.356 | 4.15 | PASS |
| `gpm_mid_10_day10` | final | 4.87% | -13.78% | 0.595 | 0.353 | 4.03 | PASS |
| `synergy_v1` | final | 10.55% | -29.99% | 0.658 | 0.352 | 1.56 | - |
| `dual_momentum_all_weather_4` | combined_final | 5.83% | -16.75% | 0.595 | 0.348 | 1.97 | - |
| `gpm_mid_13_day15` | final | 5.06% | -14.56% | 0.614 | 0.347 | 4.15 | PASS |
| `gpm_mid_13_day5` | final | 4.54% | -13.47% | 0.561 | 0.337 | 4.15 | PASS |
| `gtaa_agg6_mid` | final | 5.76% | -17.29% | 0.588 | 0.333 | 2.92 | fail (patrz JSON) |
| `gpm_mid_10_day5` | final | 4.36% | -13.12% | 0.543 | 0.332 | 4.03 | PASS |
| `gtaa_agg3_mid` | final | 7.03% | -21.16% | 0.552 | 0.332 | 3.64 | fail (patrz JSON) |
| `gpm_mid_13_day25` | final | 4.74% | -14.27% | 0.578 | 0.332 | 4.15 | PASS |
| `gpm_mid_10_day25` | final | 4.59% | -13.91% | 0.563 | 0.330 | 4.03 | PASS |
| `best17_a_best17_b` | combined_final | 9.76% | -30.28% | 0.716 | 0.322 | 1.82 | - |
| `best17_a_offensive` | final | 11.10% | -35.33% | 0.655 | 0.314 | 0.69 | fail (patrz JSON) |
| `gpm_mid_10_day20` | final | 4.59% | -14.89% | 0.564 | 0.309 | 4.03 | PASS |
| `gpm_mid_13_cash` | final | 3.63% | -11.79% | 0.516 | 0.308 | 3.61 | PASS |
| `vaa_g4_all_weather_4` | combined_final | 5.83% | -19.01% | 0.642 | 0.307 | 4.78 | - |
| `gpm_mid_13_day20` | final | 4.74% | -15.61% | 0.578 | 0.304 | 4.15 | PASS |
| `the_one_all_weather_4` | combined_final | 6.30% | -20.95% | 0.580 | 0.301 | 4.08 | - |
| `all_weather_4_best17_b` | combined_final | 6.20% | -21.43% | 0.597 | 0.289 | 1.96 | - |
| `all_weather_4_gfm` | combined_final | 6.37% | -22.65% | 0.595 | 0.281 | 2.59 | - |
| `gpm_mid_10_cash` | final | 3.49% | -12.56% | 0.499 | 0.278 | 3.43 | PASS |
| `all_weather_4` | final | 6.87% | -25.72% | 0.646 | 0.267 | 1.74 | - |
| `the_one_best17_b` | combined_final | 5.88% | -22.07% | 0.525 | 0.266 | 4.28 | - |
| `dual_momentum_the_one` | combined_final | 5.66% | -22.03% | 0.512 | 0.257 | 4.38 | - |
| `gpm_lite_7` | final | 3.50% | -14.02% | 0.421 | 0.249 | 4.07 | - |
| `dual_momentum_best17_b` | combined_final | 5.50% | -22.26% | 0.506 | 0.247 | 2.18 | - |
| `vaa_g4_best17_b` | combined_final | 5.01% | -20.39% | 0.519 | 0.246 | 5.00 | - |
| `dual_momentum_gfm` | combined_final | 5.92% | -25.73% | 0.544 | 0.230 | 2.92 | - |
| `gtaa_agg3` | final | 4.79% | -20.82% | 0.420 | 0.230 | 3.81 | - |
| `vaa_g4_the_one` | combined_final | 4.80% | -21.60% | 0.433 | 0.222 | 7.19 | - |
| `dual_momentum` | final | 4.99% | -22.49% | 0.464 | 0.222 | 2.28 | - |
| `gpm` | final | 3.43% | -15.93% | 0.448 | 0.215 | 4.34 | - |
| `dual_momentum_vaa_g4` | combined_final | 4.77% | -22.52% | 0.518 | 0.212 | 5.08 | - |
| `gpm_mid_10_defensive` | final | 3.42% | -16.45% | 0.520 | 0.208 | 3.58 | PASS |
| `gfm_breadth` | final | 5.49% | -26.55% | 0.504 | 0.207 | 4.41 | - |
| `the_one` | final | 5.51% | -26.85% | 0.414 | 0.205 | 6.50 | - |
| `gfm` | final | 7.11% | -35.22% | 0.545 | 0.202 | 3.47 | - |
| `gtaa_agg6` | final | 4.42% | -21.97% | 0.479 | 0.201 | 3.00 | - |
| `gfm_best17_b` | combined_final | 6.17% | -31.35% | 0.509 | 0.197 | 2.86 | - |
| `the_one_tlt_hedge` | combined_final | 5.30% | -28.15% | 0.415 | 0.188 | 5.97 | - |
| `the_one_gfm` | combined_final | 5.22% | -28.10% | 0.456 | 0.186 | 5.23 | - |
| `best17_b` | final | 5.04% | -30.53% | 0.396 | 0.165 | 2.26 | - |
| `vaa_g4` | final | 4.39% | -28.19% | 0.420 | 0.156 | 7.79 | - |
| `vaa_g4_gfm` | combined_final | 3.41% | -22.76% | 0.376 | 0.150 | 5.76 | - |
| `bh_spy` | final | 7.89% | -54.54% | 0.495 | 0.145 | 0.05 | fail (patrz JSON) |
| `bh_vt` | final | 6.35% | -47.26% | 0.404 | 0.134 | 0.06 | fail (patrz JSON) |
| `daa_g4` | final | 3.50% | -32.01% | 0.318 | 0.109 | 7.64 | - |
| `daa_g4_keller` | final | 2.86% | -32.12% | 0.343 | 0.089 | 4.82 | - |
| `tlt_hedge` | final | 1.46% | -49.23% | 0.172 | 0.030 | 0.05 | - |
| `tlt_timing` | final | 0.13% | -45.89% | 0.067 | 0.003 | 3.12 | - |
| `tbf_hedge` | final | -0.59% | -15.97% | -0.043 | -0.037 | 0.98 | - |
