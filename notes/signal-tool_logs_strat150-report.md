# Strategy generator — 150 candidates (2026-06-29)

**50 distinct entry edges × 3 reward:risk exits = 150 strategies.** No time-of-day limit (any RTH bar). Biased toward FVG / sweep / reversal / mean-revert families per the power-hour post-mortem (0-for-11 momentum-chase) and the [WICK] liquidity-sweep example.

Backtested on **13d** (2026-06-04 → 2026-06-19) PRIMARY + **58d** (2026-04-09 → 2026-06-18) out-of-sample. Dollars @5 MNQ ($10/pt), gross (no slippage/commissions). "Feasible" = worst day < $1000 (DLL) and max drawdown < $2000 (MLL).

- **Robust survivors** (net-positive AND feasible on BOTH samples, ≥5/≥8 trades): **0 of 150**.

> SCREEN, not proof. 13 days is tiny; survivors must also clear the 58-day column and ideally fresh out-of-sample before any live use. Exits use a fixed ATR bracket — no per-strategy stop/target tuning beyond the 3 RR profiles.

## Robust survivors (ranked by weakest-sample net)

_None cleared the strict both-samples-feasible bar — expected on 13 days (its worst-day wall is noisy). See the promising tier below._

## Promising (net+ on both, feasible on the larger 58d sample) — 0

These bust the Combine drawdown wall at **5 MNQ** on the tiny 13d sample but are net-positive on both and feasible on 58d — i.e. real candidates to deepen and/or trade at smaller size.


## Top 30 by score (all strategies)

| # | Strategy | Cat | 13d Trd | 13d Win% | 13d PF | 13d Net | 13d DD | 58d Net | 58d PF | Robust |
|---|----------|-----|----:|----:|---:|------:|------:|------:|---:|:--:|
| 1 | ADX>20 + EMA200 momentum · RR5 | MOM | 77 | 26 | 1.52 | +$15,060 | -$10558 | +$21,624 | 1.27 |  |
| 2 | FVG retest (win8, gap.3ATR) · RR5 | FVG | 26 | 38.5 | 3.17 | +$17,366 | -$2179 | +$17,183 | 1.52 |  |
| 3 | Pin bar (wick 2x body) · RR5 | REV | 54 | 25.9 | 1.64 | +$11,727 | -$6716 | +$21,313 | 1.36 |  |
| 4 | FVG retest (win6, gap.4ATR) · RR3 | FVG | 17 | 52.9 | 3.39 | +$14,965 | -$3113 | +$15,710 | 1.58 |  |
| 5 | Pin bar (wick 2x body) · RR3 | REV | 46 | 32.6 | 1.57 | +$11,944 | -$6698 | +$16,733 | 1.24 |  |
| 6 | FVG retest (win8, gap.3ATR) · RR3 | FVG | 26 | 42.3 | 2.18 | +$13,051 | -$3113 | +$14,365 | 1.38 |  |
| 7 | FVG retest (win6, gap.4ATR) · RR5 | FVG | 17 | 47.1 | 4.75 | +$17,373 | -$2179 | +$9,987 | 1.42 |  |
| 8 | FVG retest (win6, gap.2ATR) · RR5 | FVG | 26 | 38.5 | 2.99 | +$16,303 | -$2794 | +$10,881 | 1.34 |  |
| 9 | FVG retest (win6, gap.2ATR) · RR3 | FVG | 27 | 40.7 | 2.03 | +$11,888 | -$3991 | +$14,476 | 1.38 |  |
| 10 | Pin bar (wick 2x body) · RR1.5 | REV | 49 | 42.9 | 1.57 | +$10,948 | -$5770 | +$14,818 | 1.21 |  |
| 11 | ADX>20 + EMA200 momentum · RR3 | MOM | 63 | 33.3 | 1.37 | +$11,425 | -$10027 | +$13,782 | 1.15 |  |
| 12 | Doji-range break · RR3 | VOL | 36 | 36.1 | 1.69 | +$10,683 | -$5389 | +$11,670 | 1.22 |  |
| 13 | FVG retest (win6, gap.2ATR) · RR1.5 | FVG | 29 | 55.2 | 2.38 | +$13,465 | -$2345 | +$8,231 | 1.18 |  |
| 14 | NR4 narrow-range break · RR3 | VOL | 44 | 38.6 | 1.64 | +$12,638 | -$4499 | +$8,288 | 1.12 |  |
| 15 | Three soldiers/crows · RR5 | MOM | 64 | 21.9 | 1.27 | +$6,160 | -$8280 | +$14,236 | 1.21 |  |
| 16 | FVG retest + EMA50 trend · RR5 | FVG | 24 | 37.5 | 2.52 | +$11,968 | -$3716 | +$8,219 | 1.32 |  |
| 17 | FVG retest (win4, gap.2ATR) · RR5 | FVG | 24 | 37.5 | 2.72 | +$13,279 | -$2794 | +$6,364 | 1.23 |  |
| 18 | FVG retest (win6, gap.4ATR) · RR1.5 | FVG | 19 | 63.2 | 3.57 | +$12,920 | -$1171 | +$6,601 | 1.21 |  |
| 19 | NR4 narrow-range break · RR1.5 | VOL | 52 | 46.2 | 1.42 | +$9,573 | -$4459 | +$9,125 | 1.12 |  |
| 20 | EMA20 pullback in trend · RR3 | MOM | 47 | 29.8 | 1.29 | +$5,676 | -$7265 | +$12,488 | 1.2 |  |
| 21 | FVG retest + EMA50 trend · RR1.5 | FVG | 26 | 53.8 | 2.15 | +$10,264 | -$2714 | +$7,617 | 1.21 |  |
| 22 | Pin bar at EMA50 · RR5 | REV | 18 | 33.3 | 2.05 | +$6,705 | -$3047 | +$11,033 | 1.4 |  |
| 23 | FVG retest (win4, gap.2ATR) · RR1.5 | FVG | 26 | 53.8 | 2.31 | +$11,692 | -$1579 | +$5,902 | 1.16 |  |
| 24 | FVG retest + EMA50 trend · RR3 | FVG | 25 | 40 | 1.76 | +$8,372 | -$5308 | +$8,828 | 1.28 |  |
| 25 | Key reversal bar · RR1.5 | REV | 65 | 47.7 | 1.22 | +$6,521 | -$5299 | +$10,144 | 1.12 |  |
| 26 | EMA20 pullback in trend · RR5 | MOM | 50 | 26 | 1.47 | +$8,051 | -$6267 | +$8,125 | 1.14 |  |
| 27 | CCI zero-cross + EMA200 · RR3 | MR | 31 | 25.8 | 1.25 | +$3,390 | -$5387 | +$12,503 | 1.32 |  |
| 28 | FVG retest (win4, gap.2ATR) · RR3 | FVG | 25 | 40 | 1.88 | +$9,558 | -$3991 | +$6,035 | 1.17 |  |
| 29 | ADX>20 + EMA200 momentum · RR1.5 | MOM | 78 | 47.4 | 1.25 | +$8,910 | -$8574 | +$5,902 | 1.05 |  |
| 30 | FVG retest (win8, gap.3ATR) · RR1.5 | FVG | 28 | 53.6 | 2.15 | +$11,780 | -$3060 | +$3,017 | 1.07 |  |
