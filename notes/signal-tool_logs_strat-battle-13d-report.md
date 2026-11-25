# Strategy Battle - 13-Day Window (2026-06-30)

**Data:** NQ 5m, 13492 bars, 2026-04-09 to 2026-06-18
**13d window:** 2026-06-02 to 2026-06-18
**Cost model:** fee $0.37/side + 2-tick slippage, vol-sized ($200 risk cap, max 5 MNQ)
**Risk gates:** max 2 trades/day, daily stop -$700, feasibility hard gate (DD<$2k, worst-day<$1k)

## Results - ranked by 13d net P&L

| # | Strategy | Config | 13d Net | 13d Trd | 13d Win | 13d PF | Full Net | Feasible | Combine | MC% |
|---|---|---|---:|---:|---:|---:|---:|:---:|:---:|---:|
| 1 | S6: OR false-break fade | s1.5/t2.5 $200 2/d | +$1,836 | 8 | 75.0% | 5.11 | +$1,765 | YES | FAIL-no-target | 0.4% |
| 2 | BENCH: KeyRev@BB+Reclaim | s1.5/t2 $200 2/d | +$1,498 | 24 | 58.3% | 1.97 | +$2,001 | YES | FAIL-no-target | 11% |
| 3 | S7: EMA21 pullback + trend | s1.5/t2.5 $200 2/d | +$1,423 | 16 | 56.3% | 2.17 | +$1,920 | YES | FAIL-no-target | 6.8% |
| 4 | S10: KeyRev@BB + vol thrust | s1.5/t2.5 $200 2/d | +$1,155 | 16 | 56.3% | 2.2 | +$2,770 | YES | FAIL-no-target | 41.9% |
| 5 | S2: KeyRev@BB + 3-bar exhaust | s1.5/t2 $200 3/d | +$1,097 | 21 | 57.1% | 1.7 | +$1,038 | NO | FAIL-MLL | 1.9% |
| 6 | S5: VWAP rubber-band fade | s1.5/t2 $200 3/d | +$1,044 | 7 | 85.7% | 5.66 | +$533 | YES | FAIL-no-target | 0% |
| 7 | S3: KeyRev@BB + Stoch extreme | s1.2/t2 $200 2/d | +$547 | 13 | 46.2% | 1.55 | +$82 | NO | FAIL-MLL | 0.1% |
| 8 | S8: BB squeeze band-fade | s1.5/t2.5 $200 2/d | +$308 | 9 | 55.6% | 1.54 | +$1,677 | YES | FAIL-no-target | 0% |
| 9 | S1: KeyRev@BB + VWAP bias | s1.5/t2.5 $200 2/d | +$99 | 18 | 38.9% | 1.05 | -$111 | YES | FAIL-no-target | 0.1% |
| 10 | S4: RSI2 extreme + BB + body | s1.2/t2 $200 2/d | -$138 | 1 | 0.0% | 0 | -$506 | YES | FAIL-no-target | 0% |
| 11 | S9: RSI14 midline cross + BB | s1.5/t2 $200 2/d | -$339 | 3 | 0.0% | 0 | +$937 | YES | FAIL-no-target | 0% |

## Top 3 - Day-by-Day (13d window)

### 1. S6: OR false-break fade
Config: s1.5/t2.5 $200, 2/day, -700 daily stop
- **13d:** +$1,836 | 8 trades | 75.0% win | PF 5.11 | MaxDD -$317 | WorstDay -$0
- **Full period:** +$1,765 | 33 trades | 45.5% win | MaxDD -$922 | Feasible: YES
- **Combine:** FAIL (no-target)  |  Monte-Carlo: 0.4%

| Date | P&L |
|---|---|
| 2026-06-05 | +$270 |
| 2026-06-08 | +$661 |
| 2026-06-10 | +$240 |
| 2026-06-11 | +$525 |
| 2026-06-17 | +$140 |

### 2. BENCH: KeyRev@BB+Reclaim
Config: s1.5/t2 $200, 2/day, -700 daily stop
- **13d:** +$1,498 | 24 trades | 58.3% win | PF 1.97 | MaxDD -$1101 | WorstDay -$361
- **Full period:** +$2,001 | 87 trades | 49.4% win | MaxDD -$1282 | Feasible: YES
- **Combine:** FAIL (no-target)  |  Monte-Carlo: 11%

| Date | P&L |
|---|---|
| 2026-06-02 | +$204 |
| 2026-06-03 | +$370 |
| 2026-06-04 | -$281 |
| 2026-06-05 | -$293 |
| 2026-06-08 | -$143 |
| 2026-06-09 | -$23 |
| 2026-06-10 | -$361 |
| 2026-06-11 | +$660 |
| 2026-06-12 | +$642 |
| 2026-06-15 | +$67 |
| 2026-06-16 | +$10 |
| 2026-06-17 | +$393 |
| 2026-06-18 | +$254 |

### 3. S7: EMA21 pullback + trend
Config: s1.5/t2.5 $200, 2/day, -700 daily stop
- **13d:** +$1,423 | 16 trades | 56.3% win | PF 2.17 | MaxDD -$477 | WorstDay -$279
- **Full period:** +$1,920 | 58 trades | 43.1% win | MaxDD -$819 | Feasible: YES
- **Combine:** FAIL (no-target)  |  Monte-Carlo: 6.8%

| Date | P&L |
|---|---|
| 2026-06-02 | -$169 |
| 2026-06-03 | +$132 |
| 2026-06-04 | +$218 |
| 2026-06-05 | +$518 |
| 2026-06-10 | +$418 |
| 2026-06-11 | -$279 |
| 2026-06-15 | -$198 |
| 2026-06-16 | +$448 |
| 2026-06-17 | -$16 |
| 2026-06-18 | +$350 |

