# Optimized strategies — risk-controlled, 90-day primary (2026-06-29)

Each surviving edge re-tested with **vol-based sizing (risk cap), daily-loss stop ($500), max-trades/day, and trend/ADX filters**, scored on a **chronological $50K Combine sim** over the **89-day MNQ chart** (2026-03-08 → 2026-06-19). "Feasible" = max trailing DD < $2000 AND worst day < $1000 at the realized vol-based size (≤5 MNQ). 58d + 13d columns are out-of-sample confirmation. Gross of fees/slippage.

- Configs tested: **1584**  ·  feasible + net-positive (≥20 trades) on 90d: **243**.

## Best feasible configs (ranked by 90d net)

| 90d Net | Win% | PF | 90d MaxDD | 90d WorstDay | 58d Net | 58d DD | 58d Feas | 13d Net | Config |
|------:|--:|--:|------:|------:|------:|------:|:--:|------:|--------|
| +$6,737 | 24.6 | 1.55 | -$1382 | -$586 | +$7,353 | -$1247 | yes | +$1,579 | Pin bar at EMA50 [both] s0.7/t3.5 cap$300 3t/d |
| +$6,555 | 33.3 | 1.41 | -$1971 | -$697 | +$5,822 | -$1840 | yes | +$1,640 | FVG retest + EMA50 trend [adx] s1/t3.5 cap$300 3t/d |
| +$6,160 | 43.2 | 1.51 | -$1886 | -$587 | +$6,081 | -$1707 | yes | +$3,963 | FVG retest + EMA50 trend [adx] s1.5/t3.5 cap$300 3t/d |
| +$6,144 | 24.8 | 1.43 | -$1670 | -$516 | +$4,545 | -$1669 | yes | +$1,534 | Pin bar at EMA50 [trend] s0.7/t3.5 cap$200 3t/d |
| +$5,494 | 41.6 | 1.58 | -$1420 | -$459 | +$6,036 | -$994 | yes | +$4,191 | FVG retest (win6, gap.2ATR) [adx] s1.5/t3.5 cap$200 3t/d |
| +$5,493 | 24.6 | 1.67 | -$899 | -$370 | +$5,263 | -$883 | yes | +$1,282 | Pin bar at EMA50 [both] s0.7/t3.5 cap$200 3t/d |
| +$5,431 | 41.7 | 1.49 | -$1928 | -$587 | +$5,743 | -$1485 | yes | +$4,444 | FVG retest + EMA50 trend [both] s1.5/t3.5 cap$300 3t/d |
| +$5,410 | 42.5 | 1.52 | -$1928 | -$579 | +$5,409 | -$1485 | yes | +$3,727 | FVG retest + EMA50 trend [both] s1.5/t3.5 cap$300 2t/d |
| +$5,250 | 42.2 | 1.48 | -$1939 | -$579 | +$5,532 | -$1485 | yes | +$3,727 | FVG retest (win6, gap.2ATR) [both] s1.5/t3.5 cap$300 2t/d |
| +$5,120 | 43.2 | 1.45 | -$1886 | -$579 | +$5,272 | -$1706 | yes | +$3,246 | FVG retest + EMA50 trend [adx] s1.5/t3.5 cap$300 2t/d |
| +$4,889 | 42.7 | 1.6 | -$1315 | -$459 | +$5,180 | -$1201 | yes | +$3,730 | FVG retest + EMA50 trend [adx] s1.5/t3.5 cap$200 3t/d |
| +$4,639 | 35.4 | 1.29 | -$1803 | -$541 | +$2,452 | -$1806 | yes | +$1,999 | FVG retest (win6, gap.2ATR) [none] s1/t2.5 cap$200 3t/d |
| +$4,595 | 42.4 | 1.54 | -$1332 | -$414 | +$5,287 | -$1046 | yes | +$3,484 | FVG retest (win6, gap.2ATR) [adx] s1.5/t3.5 cap$200 2t/d |
| +$4,590 | 47.1 | 1.36 | -$1633 | -$588 | +$5,375 | -$1484 | yes | +$4,069 | FVG retest (win6, gap.2ATR) [adx] s1.5/t2.5 cap$300 2t/d |
| +$4,485 | 22.6 | 1.37 | -$1382 | -$586 | +$6,239 | -$1247 | yes | +$1,579 | Pin bar at EMA50 [both] s0.7/t3.5 cap$300 2t/d |
