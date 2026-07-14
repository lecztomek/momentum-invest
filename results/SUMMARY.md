# Wyniki wszystkich strategii (wygenerowane, patrz `engine_v2/generate_results.py`)

Posortowane wg Calmar. `combined_final` = portfel laczony (podatek 19% zalozony przez generator, nie czesc specyfikacji). Pelne dane (walk-forward/sensitivity/UK mapping/named_periods) w odpowiadajacym `results/<nazwa>.json`.

| Strategia | Tryb | CAGR | MaxDD | Sharpe | Calmar | Turnover/rok | UK mapping |
|---|---|---|---|---|---|---|---|
| `gpm_mid_10_best17_a` | combined_final | 8.22% | -15.34% | 0.796 | 0.536 | 2.74 | fail (patrz JSON) |
| `gpm_best17_a` | combined_final | 8.06% | -15.48% | 0.799 | 0.521 | 2.90 | - |
| `combined_triple` | combined_final | 9.07% | -20.41% | 0.785 | 0.444 | 2.27 | - |
| `best17_a` | final | 13.71% | -31.19% | 0.802 | 0.440 | 1.16 | fail (patrz JSON) |
| `gtaa_agg6_mid_best17_a` | combined_final | 9.05% | -21.09% | 0.779 | 0.429 | 2.10 | fail (patrz JSON) |
| `synergy_v2` | final | 13.32% | -31.19% | 0.769 | 0.427 | 1.16 | - |
| `best17_a_tlt_hedge` | combined_final | 11.58% | -27.39% | 0.795 | 0.423 | 0.97 | - |
| `best17_a_all_weather_4` | combined_final | 9.58% | -23.04% | 0.797 | 0.416 | 1.38 | - |
| `synergy_v1` | final | 11.96% | -29.99% | 0.726 | 0.399 | 1.07 | - |
| `best17_a_tlt_timing` | combined_final | 9.47% | -24.09% | 0.754 | 0.393 | 1.41 | - |
| `dual_momentum_best17_a` | combined_final | 9.01% | -22.93% | 0.735 | 0.393 | 1.68 | - |
| `combined_best2` | combined_final | 9.53% | -24.40% | 0.725 | 0.391 | 3.79 | - |
| `gtaa_agg6_best17_a` | combined_final | 8.31% | -21.54% | 0.742 | 0.386 | 2.14 | - |
| `vaa_g4_best17_a` | combined_final | 8.42% | -22.57% | 0.759 | 0.373 | 4.39 | - |
| `combined_best2_dynamic` | combined_final | 10.66% | -30.24% | 0.734 | 0.352 | 3.68 | - |
| `dual_momentum_all_weather_4` | combined_final | 5.85% | -16.75% | 0.606 | 0.349 | 1.95 | - |
| `gtaa_agg6_mid` | final | 5.76% | -17.29% | 0.588 | 0.333 | 2.92 | fail (patrz JSON) |
| `gtaa_agg3_mid` | final | 7.03% | -21.16% | 0.552 | 0.332 | 3.64 | fail (patrz JSON) |
| `best17_a_gfm` | combined_final | 9.49% | -28.76% | 0.719 | 0.330 | 1.85 | - |
| `vaa_g4_all_weather_4` | combined_final | 5.79% | -19.01% | 0.638 | 0.305 | 4.76 | - |
| `the_one_all_weather_4` | combined_final | 6.17% | -20.95% | 0.582 | 0.295 | 3.89 | - |
| `best17_a_best17_b` | combined_final | 8.67% | -30.28% | 0.672 | 0.286 | 1.63 | - |
| `all_weather_4_best17_b` | combined_final | 6.09% | -21.43% | 0.589 | 0.284 | 1.99 | - |
| `all_weather_4` | final | 6.87% | -25.72% | 0.646 | 0.267 | 1.74 | - |
| `all_weather_4_gfm` | combined_final | 5.80% | -22.65% | 0.622 | 0.256 | 2.00 | - |
| `gpm_lite_7` | final | 3.50% | -14.02% | 0.421 | 0.249 | 4.07 | - |
| `dual_momentum_the_one` | combined_final | 5.40% | -22.03% | 0.494 | 0.245 | 4.35 | - |
| `vaa_g4_best17_b` | combined_final | 5.00% | -20.39% | 0.519 | 0.245 | 4.99 | - |
| `the_one_best17_b` | combined_final | 5.35% | -22.07% | 0.495 | 0.242 | 4.12 | - |
| `gpm_mid_10` | final | 3.36% | -14.36% | 0.451 | 0.234 | 4.39 | fail (patrz JSON) |
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
| `daa_g4_keller` | final | 3.38% | -37.58% | 0.341 | 0.090 | 7.19 | - |
| `tlt_hedge` | final | 1.46% | -49.23% | 0.172 | 0.030 | 0.05 | - |
| `tlt_timing` | final | 0.13% | -45.89% | 0.067 | 0.003 | 3.12 | - |
