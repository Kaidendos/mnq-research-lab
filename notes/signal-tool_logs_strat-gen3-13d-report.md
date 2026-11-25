# Gen-3 Strategy Battle - 13d (2026-06-30)

**10 brand-new entry edges.** Same risk model: $200 cap, vol-sized, max 5 MNQ, daily stop -$700, net of fee+2-tick slip.

| # | Strategy | Config | 13d Net | 13d Trd | 13d Win | 13d PF | Full Net | Full Win | DD | Feasible | Combine | MC% |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|---:|
| 1 | G8: Morning/evening star | s1.5/t2 $200 3/d | +$1,808 | 35 | 54.3% | 1.58 | +$2,612 | 50.9% | -$1103 | YES | PASS | 52.5% |
| 2 | G4: ATR spike exhaustion | s1.5/t2 $200 3/d | +$1,161 | 24 | 58.3% | 1.64 | +$632 | 46.1% | -$1469 | YES | FAIL-no-target | 0.2% |
| 3 | G10: VWAP reclaim + trend | s1.5/t2.5 $200 2/d | +$1,115 | 23 | 52.2% | 1.54 | +$2,556 | 47.1% | -$1891 | YES | FAIL-no-target | 42.2% |
| 4 | G7: NR7 false-breakout fade | s1.5/t3 $200 2/d | +$206 | 24 | 45.8% | 1.07 | +$557 | 38.9% | -$1721 | YES | FAIL-no-target | 4.4% |
| 5 | G1: Gap fade (>0.5 ATR) | s1.2/t2 $200 2/d | +$194 | 12 | 41.7% | 1.17 | +$959 | 44.4% | -$833 | YES | FAIL-no-target | 0.1% |
| 6 | G6: 5-bar consecutive fade | s1.5/t2 $200 2/d | +$156 | 8 | 62.5% | 1.28 | -$19 | 41.4% | -$555 | YES | FAIL-no-target | 0% |
| 7 | G3: RSI14 divergence | s1.5/t2 $200 2/d | +$0 | 0 | 0.0% | 0 | +$0 | 0.0% | -$0 | YES | FAIL-no-target | 0% |
| 8 | G5: Prior-day level rejection | s1.2/t2 $200 2/d | -$186 | 15 | 40.0% | 0.89 | -$1,723 | 30.4% | -$1897 | YES | FAIL-no-target | 0% |
| 9 | G11: Post-lunch trend continuation | s1.5/t3 $200 2/d | -$465 | 23 | 30.4% | 0.84 | -$1,523 | 34.1% | -$2757 | NO | FAIL-MLL | 0.1% |
| 10 | G2: HOD/LOD test-reverse | s1.5/t2 $200 2/d | -$773 | 25 | 36.0% | 0.71 | -$1,844 | 37.5% | -$2612 | NO | FAIL-MLL | 0% |
| 11 | G9: Double-tap level fade | s1.5/t2 $200 3/d | -$1,152 | 39 | 33.3% | 0.74 | -$2,424 | 38.8% | -$3447 | NO | FAIL-MLL | 0.2% |

## Top 3 Day-by-Day

### 1. G8: Morning/evening star
- 13d: +$1,808 | 35 trades | 54.3% win | PF 1.58 | MaxDD -$736
- Full: +$2,612 | 116t | 50.9% win | MaxDD -$1103 | Feasible: YES
- Combine: PASS | MC: 52.5%

| Date | P&L |
|---|---|
| 2026-06-02 | +$365 |
| 2026-06-03 | +$169 |
| 2026-06-04 | -$21 |
| 2026-06-05 | -$103 |
| 2026-06-08 | +$364 |
| 2026-06-09 | +$323 |
| 2026-06-10 | -$247 |
| 2026-06-11 | +$1,024 |
| 2026-06-12 | +$111 |
| 2026-06-15 | +$196 |
| 2026-06-16 | -$55 |
| 2026-06-17 | -$222 |
| 2026-06-18 | -$95 |

### 2. G4: ATR spike exhaustion
- 13d: +$1,161 | 24 trades | 58.3% win | PF 1.64 | MaxDD -$521
- Full: +$632 | 89t | 46.1% win | MaxDD -$1469 | Feasible: YES
- Combine: FAIL(no-target) | MC: 0.2%

| Date | P&L |
|---|---|
| 2026-06-03 | +$19 |
| 2026-06-04 | +$13 |
| 2026-06-05 | +$228 |
| 2026-06-08 | +$728 |
| 2026-06-09 | -$373 |
| 2026-06-10 | +$327 |
| 2026-06-11 | -$27 |
| 2026-06-12 | +$112 |
| 2026-06-15 | +$149 |
| 2026-06-16 | -$127 |
| 2026-06-17 | -$48 |
| 2026-06-18 | +$160 |

### 3. G10: VWAP reclaim + trend
- 13d: +$1,115 | 23 trades | 52.2% win | PF 1.54 | MaxDD -$707
- Full: +$2,556 | 87t | 47.1% win | MaxDD -$1891 | Feasible: YES
- Combine: FAIL(no-target) | MC: 42.2%

| Date | P&L |
|---|---|
| 2026-06-02 | +$155 |
| 2026-06-03 | +$57 |
| 2026-06-04 | -$146 |
| 2026-06-05 | +$498 |
| 2026-06-08 | +$210 |
| 2026-06-09 | -$124 |
| 2026-06-10 | -$208 |
| 2026-06-11 | +$191 |
| 2026-06-12 | -$379 |
| 2026-06-15 | +$495 |
| 2026-06-16 | +$205 |
| 2026-06-17 | +$31 |
| 2026-06-18 | +$131 |

