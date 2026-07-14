# Wyniki wszystkich strategii (wygenerowane, patrz `engine_v2/generate_results.py`)

Posortowane wg Calmar. `combined_final` = portfel laczony (podatek 19% zalozony przez generator, nie czesc specyfikacji). Pelne dane (walk-forward/sensitivity/UK mapping/named_periods) w odpowiadajacym `results/<nazwa>.json`.

| Strategia | Tryb | CAGR | MaxDD | Sharpe | Calmar | Turnover/rok | UK mapping |
|---|---|---|---|---|---|---|---|
| `gpm_mid_10_best17_a` | combined_final | 8.81% | -14.65% | 0.846 | 0.601 | 2.74 | fail (patrz JSON) |
| `gpm_best17_a` | combined_final | 8.70% | -14.87% | 0.855 | 0.585 | 2.90 | - |
| `combined_triple` | combined_final | 9.56% | -20.30% | 0.822 | 0.471 | 2.27 | - |
| `vaa_g4_best17_a` | combined_final | 9.48% | -21.07% | 0.842 | 0.450 | 4.39 | - |
| `combined_best2` | combined_final | 10.43% | -23.58% | 0.783 | 0.442 | 3.79 | - |
| `best17_a` | final | 13.71% | -31.19% | 0.802 | 0.440 | 1.16 | fail (patrz JSON) |
| `synergy_v2` | final | 13.32% | -31.19% | 0.769 | 0.427 | 1.16 | - |
| `best17_a_all_weather_4` | combined_final | 9.81% | -23.05% | 0.813 | 0.426 | 1.38 | - |
| `best17_a_tlt_hedge` | combined_final | 11.58% | -27.39% | 0.795 | 0.423 | 0.97 | - |
| `gtaa_agg6_best17_a` | combined_final | 8.75% | -20.76% | 0.776 | 0.421 | 2.14 | - |
| `dual_momentum_best17_a` | combined_final | 9.32% | -22.78% | 0.756 | 0.409 | 1.68 | - |
| `best17_a_tlt_timing` | combined_final | 9.64% | -23.79% | 0.765 | 0.405 | 1.41 | - |
| `synergy_v1` | final | 11.96% | -29.99% | 0.726 | 0.399 | 1.07 | - |
| `vaa_g4_all_weather_4` | combined_final | 7.05% | -18.05% | 0.761 | 0.390 | 4.76 | - |
| `combined_best2_dynamic` | combined_final | 11.56% | -29.68% | 0.786 | 0.389 | 3.68 | - |
| `dual_momentum_all_weather_4` | combined_final | 6.35% | -16.61% | 0.652 | 0.382 | 1.95 | - |
| `the_one_all_weather_4` | combined_final | 7.20% | -19.83% | 0.665 | 0.363 | 3.89 | - |
| `best17_a_gfm` | combined_final | 9.84% | -28.74% | 0.741 | 0.343 | 1.85 | - |
| `vaa_g4_best17_b` | combined_final | 6.30% | -18.52% | 0.636 | 0.340 | 4.99 | - |
| `vaa_g4_the_one` | combined_final | 6.74% | -20.04% | 0.593 | 0.336 | 6.91 | - |
| `gpm_mid_10` | final | 4.48% | -13.38% | 0.584 | 0.335 | 4.39 | fail (patrz JSON) |
| `gpm` | final | 4.54% | -13.90% | 0.575 | 0.327 | 4.34 | - |
| `gpm_lite_7` | final | 4.53% | -13.91% | 0.529 | 0.326 | 4.07 | - |
| `dual_momentum_the_one` | combined_final | 6.54% | -20.78% | 0.581 | 0.315 | 4.35 | - |
| `all_weather_4_best17_b` | combined_final | 6.60% | -21.40% | 0.632 | 0.309 | 1.99 | - |
| `the_one_best17_b` | combined_final | 6.42% | -20.89% | 0.579 | 0.307 | 4.12 | - |
| `dual_momentum_vaa_g4` | combined_final | 6.03% | -19.92% | 0.652 | 0.303 | 4.97 | - |
| `best17_a_best17_b` | combined_final | 8.97% | -30.28% | 0.692 | 0.296 | 1.63 | - |
| `gtaa_agg3` | final | 5.76% | -19.69% | 0.490 | 0.293 | 3.81 | - |
| `all_weather_4_gfm` | combined_final | 6.32% | -21.63% | 0.671 | 0.292 | 2.00 | - |
| `vaa_g4_gfm` | combined_final | 5.95% | -20.48% | 0.664 | 0.291 | 5.02 | - |
| `all_weather_4` | final | 7.31% | -25.54% | 0.683 | 0.286 | 1.74 | - |
| `the_one` | final | 7.23% | -25.26% | 0.515 | 0.286 | 6.50 | - |
| `vaa_g4` | final | 6.54% | -24.50% | 0.591 | 0.267 | 7.79 | - |
| `dual_momentum_best17_b` | combined_final | 5.58% | -20.97% | 0.522 | 0.266 | 2.19 | - |
| `dual_momentum` | final | 5.57% | -21.05% | 0.509 | 0.264 | 2.28 | - |
| `the_one_gfm` | combined_final | 6.55% | -25.71% | 0.589 | 0.255 | 4.46 | - |
| `gtaa_agg6` | final | 5.19% | -20.76% | 0.551 | 0.250 | 3.00 | - |
| `gfm` | final | 8.02% | -33.71% | 0.603 | 0.238 | 3.47 | - |
| `dual_momentum_gfm` | combined_final | 5.62% | -24.10% | 0.568 | 0.233 | 2.33 | - |
| `the_one_tlt_hedge` | combined_final | 6.08% | -26.66% | 0.482 | 0.228 | 5.28 | - |
| `daa_g4` | final | 5.47% | -25.50% | 0.455 | 0.214 | 7.64 | - |
| `best17_b` | final | 5.61% | -29.71% | 0.431 | 0.189 | 2.26 | - |
| `gfm_best17_b` | combined_final | 5.47% | -30.12% | 0.512 | 0.182 | 2.24 | - |
| `bh_spy` | final | 7.88% | -54.54% | 0.495 | 0.145 | 0.05 | fail (patrz JSON) |
| `bh_vt` | final | 6.35% | -47.26% | 0.404 | 0.134 | 0.06 | fail (patrz JSON) |
| `tlt_hedge` | final | 1.45% | -49.23% | 0.172 | 0.030 | 0.05 | - |
| `tlt_timing` | final | 0.95% | -41.94% | 0.141 | 0.023 | 3.12 | - |
