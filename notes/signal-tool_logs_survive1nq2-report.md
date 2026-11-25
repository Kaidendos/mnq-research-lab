# Survive-1NQ round 2 — deeper optimization, triple out-of-sample (2026-06-21)

Round 2 of the 1-NQ ($20/pt) hunt: finer bracket grid + two new tuning dims (ADX threshold {20,25}, entry window {tight 15:00-15:45, wide 14:30-16:00}), and a **third** out-of-sample chart (the 89-day MNQ CSV). A config counts only if it is Combine-feasible (worst day < $1000 AND maxDD < $2000) AND net-positive on **all three** samples. Ranked by the weakest sample's net (anti-overfit). Dollars @1 NQ, gross.

13d 2026-06-04->2026-06-19 | 58d 2026-04-09->2026-06-18 | 89d 2026-03-08->2026-06-19.

**Triple-sample survivors: 7/12.**

## Survivors (feasible + net+ on 13d AND 58d AND 89d)

| Candidate | Config | 13d Net | 58d Net | 89d Net | 89d Trd | 89d maxDD | 89d worstDay | 89d Win/PF |
|-----------|--------|------:|------:|------:|--:|------:|------:|:--:|
| Champion (PH+EMA200+ADX) | RTH 0.5/2 cap2 | +$13567 | +$23738 | +$33343 | 75 | -$1674 | -$979 | 46.7%/3.22 |
| ROC acceleration | PH25/wide 0.5/1.5 cap2 $500 | +$8450 | +$11063 | +$17909 | 54 | -$1419 | -$935 | 44.4%/2.85 |
| Donchian-55 break | PH25/wide 0.7/1.5 cap2 | +$8384 | +$9021 | +$10072 | 31 | -$1903 | -$849 | 45.2%/2.57 |
| Pin-bar | PH25/wide 0.5/2.5 cap1 | +$7111 | +$7479 | +$7590 | 12 | -$803 | -$803 | 41.7%/3.85 |
| RSI band-ride | PH20/tight 0.5/2.5 cap1 | +$6703 | +$9760 | +$10177 | 31 | -$1443 | -$491 | 35.5%/2.58 |
| 5-bar momentum | PH25/tight 0.5/2 cap2 | +$4960 | +$7643 | +$10617 | 41 | -$1994 | -$741 | 36.6%/2.1 |
| Morning/evening star | PH20/wide 1/2 cap1 | +$1279 | +$3016 | +$3276 | 15 | -$1856 | -$907 | 40%/1.67 |

### Best round-2 survivor: **Champion (PH+EMA200+ADX)**
- Config: **RTH**, stop **0.5×ATR**, target **2×ATR**, **2 trade(s)/day**.
- 13d +$13567 (11t) · 58d +$23738 (51t) · 89d +$33343 (75t, 46.7%, PF 3.22), maxDD -$1674, worstDay -$979, maxLossStreak 4.

No config feasible+profitable on all three samples for: Three-inside, NR4 break, Failed-breakout fade, IBS extreme, Three-inside + Pin-bar (merge).

> Caveat unchanged: 1 NQ doubles every swing. Surviving three backtests is a stronger signal than two, but a future streak worse than the sample can still breach the $2000 trailing wall. 5 MNQ remains the safer collectable size. DATA-ONLY: champion locked, nothing live touched.
