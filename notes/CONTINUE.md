# RESUME STATE — MNQ funded-account strategy research

Handoff file. A scheduled task reads this after a usage-limit reset and continues.
Whatever is written here is ALL a fresh session will know. Keep it current.

**Working dir:** `C:\Users\YOU\daytrading-automation`
**Python:** `C:\Python314\python.exe`
**Last updated:** 2026-08-09 14:40 — new-trader sweep + fold-in resolved; random
control found invalid and rewritten (see "START HERE NEXT SESSION" below).
All background processes were stopped for a machine restart; nothing is running.

---

## THE GOAL

A tradable MNQ strategy for a **LucidPro $25K funded account**: **bust under 30%**
with a meaningful payout cadence. The user is running this overnight and wants
continuous progress — new strategies, optimisation, and scalping research.
Do NOT stop and wait for input; keep working and keep this file updated.

## VERIFIED ACCOUNT RULES (vendor-checked 2026-08-08 — do not re-derive)

- Start $25,000, max loss limit **$1,000**, **end-of-day** basis
- Floor trails on the highest **closing** balance, then **locks permanently at
  $25,100** once a closing balance clears $26,100
- Payout buffer **$26,100** — withdraw only the amount **above** it, so a full
  $1,000 payout needs $27,100
- Max payout **$1,000 first cycle, $1,500 after**
- **40% consistency** per cycle, **3 trading-day** minimum, no daily loss limit

Implemented in `lucid_rules.py` (reference) and `lucid_fast.py` (fast, use this).

## CURRENT BEST RESULTS  (`lb3_*.csv`, ranked by `rank_lowbust.py`)

92 of 10,368 configs clear **bust < 30% AND median withdrawal > 0**.

| Long + Short | SL/TP | risk_frac | cushion | mean | median | paid | bust |
|---|---|---|---|---|---|---|---|
| sr_round100_break + vol_lw_stretch_short | 2.0/1.5 | 1.00 | 0 | $1,710 | $286 | 52.0% | 3.2% |
| sr_round100_break + vol_lw_stretch_short | 2.0/3.0 | 1.00 | 0 | $1,459 | $323 | 53.9% | 3.1% |
| rsi_bounce35_long + vol_lw_stretch_short | 2.0/3.0 | 0.50 | 0 | $1,266 | **$1,095** | 57.0% | **0.0%** |
| ema20_50_long + vol_lw_stretch_short | 1.0/1.5 (10:00-13:00) | 0.35 | 0 | $1,077 | $971 | **68.0%** | **0.0%** |

**Established:** `risk_frac` (cap daily risk at a share of room above the floor)
is the lever that kills bust. **`cushion` is counterproductive** — median withdrawn
falls $135 → $74 → $9 as cushion goes $500 → $1,000 → $2,000. Every good config
uses cushion = 0.

**HORIZON RESOLVED (2026-08-09).** `verify_lowbust.py --mode horizon` shows bust is
IDENTICAL at 180/270/365/545 days (1.9% / 0.0% / 0.0%). Not a horizon artifact —
once the floor locks at $25,100 and risk_frac caps exposure, an account dies early
or never. Withdrawals compound with horizon while bust stays flat:
`ema20_50_long + vol_lw_stretch_short` 1.0/1.5 10:00-13:00 rf=0.35 cap300 →
h=365: 0% bust, mean $1,470, med $1,137, paid 71.9%
h=545: 0% bust, mean $2,160, med $2,094, paid **73.8%**

## ⚠ RESOLVED 2026-08-09 — THE "0% BUST" RESULT WAS WRONG. DO NOT REPORT IT.

`reconcile_sims.py` found two compounding problems. Both are fixed in code, but the
conclusion stands: **bust_pct from `lucid_fast` is not a trustworthy metric.**

1. **BUG (fixed).** `run_account` only assigned `last_day` inside the `horizon_days`
   branch, so it held the day an account DIED. `evaluate` then dropped any run with
   `days < 20` — silently deleting every account that busted in its first 20 days,
   i.e. exactly the failures. Fixed: `last_day` always tracked; the filter now gates
   on available DATA span, never on outcome. Moved bust 3.2% → 5.5%.

2. **NOT a bug — a metric problem.** `budget = min(base_budget, room * risk_frac)`
   means size shrinks as the balance nears the floor. The account stops trading
   (`n < 1`) before it can breach, so it never counts as a bust — it is just
   economically dead. **Floor-aware sizing converts busts into zombies.** This is why
   `lucid_fast` shows 5.5% bust while withdrawing LESS than `lucid_rules`
   ($1,805 vs $2,059) which reports 95.1% on the same realised series.

**USE THESE INSTEAD OF bust_pct:** mean/median withdrawn and pay%. Both simulators
agree there (~$1,800-2,100 mean, ~50% paid), and they are what actually matters.

**STILL TO CONFIRM:** the zombie hypothesis. Check the final balances of non-busted
accounts in `lucid_fast` — if they cluster just above the floor with 0 payouts, the
hypothesis is confirmed. Then add a `zombie_pct` metric (survived but withdrew $0)
and rank on `mean_out` / `pay_pct`, never on `bust_pct` alone.

## ══ THE ANSWER — READ THIS FIRST ══

**STRATEGY:** `sr_round100_break` (long) + `vol_lw_stretch_short` (short), together.
Long = close above a 100-pt multiple, ≥0.15×ATR beyond it, bullish bar, RVOL>1.
Short = **Larry Williams stretch** — first bar closing below
`session_open − K × prior-day range`, one per session.
**SL 2.0×ATR / TP 3.0×ATR. Window 09:45–11:00 ET. All weekdays. risk_frac 1.0.**

**TWO VIABLE SETTINGS — the user must choose between speed and reliability:**

| | cap $440 / bud $300 | cap $250 / bud $400 |
|---|---|---|
| days to 1st payout | **27** | 92 |
| paid | 55.6% | **75.3%** |
| stalled | 42.4% | **24.7%** |
| bust | 2.1% | **1.7%** |
| mean/yr | **$2,372** | $2,079 |
| median/yr | $325 | **$1,503** |

cap $440 = fast feedback + highest mean. cap $250 = reliability + best typical
outcome. **The user has been leaning toward the 27-day version — keep it in play.**

### ⚠⚠ FOLD-IN RETRACTED 2026-08-09 (later the same day) — IT FAILS THE PAIRED TEST
`verify_foldin.py` applied the SAME 36-config paired test that rejected
`wy_lps_long` at 67%. The fold-in does worse:

| candidate | wins on mean | median delta | wins on median | bust worse in |
|---|---|---|---|---|
| `+L ema20_50_long` | **17/36 (47%)** | **−$20** | 5/36 (14%) | 21/36 |
| 3L2S full stack | **18/36 (50%)** | **−$33** | 9/36 (25%) | 21/36 |

A coin flip. The headline numbers below were measured at ONE bracket
(9:45-11:00, SL2.0/TP3.0, cap $250) and do not generalise — the same mistake that
produced every earlier false positive in this project.

**The cap split DOES survive**, which is the one durable part:
  - cap $250: 3L2S wins 9/12, median +$340, bust −0.2 pts  → weak but positive
  - cap $440: 3L2S wins 9/24, median −$193, bust +1.8 pts  → clearly negative

9/12 is 12 configs and only marginally above the 67% that got `wy_lps_long`
killed. **Verdict: do NOT fold it in. The recommendation is unchanged — cap $440
base pair, no additions.** Retain the section below only as the record of what was
measured where.

### ══ FOLD-IN as originally measured (ONE bracket — see retraction above) ══

`speed_test.py`'s "2L+2S is a free improvement" was directionally right and
specifically wrong: it used `mf_wkpiv_long` + `lr_raschke_firstcross_short`,
chosen by STANDALONE rank. `foldin_2l2s.py` tested all 10 candidates one at a
time against a fixed base (a paired test) and the real winners are different:

| added to base | paid | bust | mean | median | 1st payout |
|---|---|---|---|---|---|
| — (base 1L+1S) | 73.6% | 1.7% | $2,079 | $1,503 | 92d |
| **+L `ema20_50_long`** | **84.4%** | **0.0%** | $2,414 | **$2,270** | 104d |
| +S `lw_oops_short` | 75.7% | 0.3% | $2,257 | $2,174 | 95d |
| +S `pdh_fade_short` | 74.0% | 4.5% | $2,376 | $1,759 | 97d |
| speed_test's guess | 71.1% | 1.7% | $1,733 | $1,608 | 85d |

Best combination (`foldin_combo.py`): **3L2S = base + `ema20_50_long` +
`mf_wkpiv_long` + `lw_oops_short`** → holdout **87.6% paid, 0.0% bust, mean
$2,856, median $2,926, 88 days**. That is better than base on every axis at once.

**⚠ BUT IT ONLY APPLIES TO cap $250.** On cap $440 (the 27-day config) every
addition is a DOWNGRADE — 3L2S gives 45.0% paid / 4.5% bust / mean $1,612 against
the base's 56.0% / 2.1% / $2,352. Do not fold it into the fast config.

### ⚠ THE LAST 5 MONTHS: cap $250 HAS PRODUCED NOTHING (`runway_check.py`)
Selection window (2026-03-09 → 2026-08-07), cap $250: **0.0% paid at every runway
length** — 0/23, 0/18, 0/13, 0/8 accounts, all STALLED, 0% bust. Not a
short-runway artifact: on the holdout, raising the runway requirement moves the
number barely at all (72.9% → 78.2%), so the runway is not what is binding.
Same window, cap $440: **43.5% → 76.9% paid as runway rises, 26 days, 0% bust.**

**This is the strongest argument yet for cap $440 and against cap $250**, and it
matches the user's original complaint that the strategy stopped working. A $250
daily ceiling needs a long string of good days to clear the $26,100 buffer; the
current regime does not supply them, so accounts grind sideways forever.

### ══ NEW TRADER RESEARCH 2026-08-09 — 9 more methodologies, NO improvement ══

Added `strategies_web/tr_{rh,ic,bw,ae,jr,bs,wy,ww,qm}.py` — **89 new families,
326 total**. Rob Hoffman (IRB 45% rule), ICT (Silver Bullet 10-11, FVG, liquidity
sweep + MSS, Judas), Bill Williams (Profitunity: alligator, fractals, AO saucer),
Alexander Elder (Impulse, Triple Screen, Elder-Ray, Force), Joe Ross (1-2-3, Ross
hook, Trader's Trick), Brian Shannon (anchored VWAP — the only volume-anchored
level in the registry), Wyckoff (spring/upthrust/SOS/LPS), Wilder (PSAR, DMI/ADX,
Volatility System), Qullamaggie (continuation breakout, EP, parabolic short).
**87/89 pass the lookahead audit, 0 disqualified** (2 WARN = too few fires).

`pair_new.py` tested the 10 best new longs and 10 best new shorts against the
fixed base, each as REPLACE and as ADD, on both windows and both cap configs:

> **BEATS BASELINE ON cap $440 (higher hold mean AND bust no worse): NONE. 0 of 20.**

Standalone rank misled AGAIN, exactly as it did with `mf_wkpiv_long`:
`ww_volsys_short` ranks #2 of 156 shorts standalone ($6,439) and produces
hold440 mean $813 as a replacement — a third of the incumbent's.

ONE near-miss was verified and **REJECTED**: `+L wy_lps_long` (Wyckoff last point
of support, OR'd into the base long). It looked good on one bracket — cap 440
holdout mean $2,532 vs $2,352, median $407 vs $334, recent window $596 vs $324 —
but `verify_wylps.py` ran the paired test across 36 matched configs:

  - wins on mean in **24/36 (67%)**, median delta only **+$104**
  - wins on median in **14/36 (39%)**
  - **bust WORSE in 26/36, median +2.2 points**
  - helps in 5/6 years; survives slippage to 4 ticks

67% is weak. Compare the `%K 14→21` result that WAS trusted: **96.2% of 840
matched configs and 6/6 years.** This buys ~$104 of mean for +2.2 points of bust —
a trade, not a free win. **Do not adopt.** (Its one strong cell, 9:45-12:00 SL2/TP3,
gains +$1,093 — that is cherry-picking a cell out of 36 and is how the earlier
false positives were born.)

Also notable but rejected on the regime test (recent window 0.0% paid):
`replace_L wy_lps_long` turns the FAST config into a reliable one — cap 440
holdout 65.3% paid, 0.7% bust, **median $1,562** (vs $334), but 49 days not 27.

### ⚠ "THE EDGE MOVED TO THE AFTERNOON" — TESTED AND KILLED
`window_regime.py` found the wide 9:45-15:30 window beating narrow 9:45-11:00 in
the last 5 months at cap $440 ($1,053 vs $324 mean) while losing badly on the
4.5-year holdout ($1,907/med $0/bust 7.6% vs $2,352/med $334/bust 2.1%). Tempting
regime story, on 23 accounts.

`rolling_window_edge.py` scored both windows in eleven non-overlapping 5-month
blocks across the whole 5 years: **WIDE wins 6 of 11, scattered throughout**
(2022-01, 2022-11, 2024-07, 2024-12, 2025-05, 2026-03). It is not a shift, it is a
coin flip that has landed on WIDE most recently. **Keep the narrow window.**

The same table is the best available answer to "how much does a 5-month verdict
mean": narrow_mean by block ranges **$76 to $2,839**. Any conclusion drawn from a
single 5-month window — including the live account's recent losses — is noise at
that scale.

### ⚠ PANDAS BUG FOUND AND FIXED — check any new plug-in for it
`~bool_series.shift(1).fillna(False)` is **silently always True**: `.shift()`
promotes bool to object dtype, and `~` then does integer negation (`~True == -2`,
truthy). Any "first bar of a state" mask built this way fires on EVERY bar of the
state. Caught because a stop-and-reverse PSAR reported 52,735 long flips vs 4,374
short — arithmetically impossible. Fix is `.astype(bool)` after `.fillna()`.
It had also been silently affecting the pre-existing `rg_ms.py` and `tr_cn.py`.

### MONEY-MANAGEMENT FINDINGS (all holdout, 288 accounts/row, 1-yr horizon)
- **Profit cap:** payout rate falls monotonically above $250 — 72.2% ($250),
  55.6% ($440), 52.4% ($900), 51.7% ($1,200). **Never raise the cap above $440.**
- **40% consistency rule barely binds:** 0.0% blocked at ≤$440, only 2.5% at $1,200.
  It is NOT the reason big caps fail — they fail because one day carries the run,
  you take a partial payout, drop back to the buffer and stall.
- **Loss budget optimum is $300–$400.** Below $250 positions are too small to reach
  the buffer; above $400 gives back more than it gains.
- **MaxContracts is inert** — 5, 10, 15 give identical results. The budget binds first.
- **Withdrawal threshold:** take-all at $250 beats waiting. Holding for $800 costs
  7.6 points of payout rate and 39 extra days. $600 is the most you should wait.
- **Banking a FIXED $400 and leaving the rest** cuts bust 1.7%→0.3% and gives the
  best payout rate found (74.3%), because the median account keeps a $1,200+ cushion
  above the floor instead of sitting at $25,202. Costs ~$650/yr in mean. Only works
  with cap $250 — on cap $440 it makes things worse.

### SPEED: possible, but it buys nothing
16-day configs exist (3L+3S wide, cap 440) but bust jumps 1.7%→**13.5%**, payout
rate drops to 40.3%, median to **$0**. More signals fire in the same conditions and
compound each other's drawdowns — same lesson as "best long + best short".
**27 days (cap $440) is the fastest SANE setting.** Do not go below it.

### WHAT "FAILING" ACTUALLY MEANS (important — I mis-stated this once)
Of the ~25% that never pay on the cap-$250 config: only **1.7% actually bust**.
The other ~23% **stall** — median final balance **$24,664**, median peak $25,519,
a median **$831 short** of the $26,350 needed to withdraw anything, with only 23%
still above the $25,000 start. They are not healthy accounts waiting for a break;
floor-aware sizing shrinks them until they can neither die nor escape.

### PAYOUT TIMELINE (cap $250, take-all)
1st payout median day 92 ($318) · 2nd day 134 ($670) · 3rd day 176 · 4th day 216.
By day 30 only **3.8%** of accounts have been paid; day 60 **17.7%**; day 92 **37.8%**;
day 365 **75.3%**. Payouts/yr: 24.7% get 0, 19.1% get 8+. The mean of 3.61 describes
almost no real account.

## ══ HARVEST RESULTS 2026-08-09 — ALL FIVE SWEEPS COMPLETE ══

### 1. SCALPING IS DEAD. Do not re-sweep it.
- 5-month window: **0 of 4,800 configs produced a single payout.**
- Full 5 years: 150 of 6,000 (2.5%) produced any payout; best mean **$11**,
  pay 1.9%, dead 98.1%.
- The only configs that produce anything at all use **24-tick targets** (the
  largest tested) — exactly what the fee arithmetic predicts: $1.22 RT = 2.44
  ticks, so a 4-tick target burns 61% of gross and a 24-tick target 10%.
- **Conclusion: MNQ scalping cannot clear costs on a $25k funded account.** This is
  a definitive negative result, not an under-explored area.

### 2. THE SELECTION-WINDOW TRAP — the clearest example yet
`scalp_micro_pull_long + scalp_micro_pull_short`, 1.0/2.0, 10:00-13:00, rf 0.25:
  - 5-month window: mean **$3,636**, median $5,030, **96.9% paid**, dead 3.1%
  - 4.5yr holdout:   mean **$114**,   median $0,     **17.9% paid**, dead 82.1%
A **32x collapse**. Anything selected on 5 months alone will look like this.
ALWAYS report the holdout next to the selection number.

### 3. DAY OF WEEK: no day is special — filtering by day makes it WORSE
| dow | sel_mean | hold_mean | hold_pay |
|---|---|---|---|
| **all** | **123.5** | **258.6** | **25.0%** |
| noMon | 105.6 | 242.8 | 24.9% |
| noFri | 113.5 | 196.6 | 22.2% |
| midweek | 94.9 | 165.3 | 20.1% |
| ThuFri | 45.6 | 104.6 | 14.9% |
| MonTue | 10.0 | 99.9 | 15.2% |
"all" wins on every metric. Fewer trading days = fewer chances, with no
compensating edge. **Do not filter by weekday.**

### 4. TIME WINDOW: the 9:45 START is what matters
| window | hold_mean | hold_pay |
|---|---|---|
| **9.75-15.50** | **424.5** | 34.4% |
| 9.75-12.00 | 372.8 | 34.5% |
| 9.75-11.00 | 347.1 | **34.8%** |
| 10.50-12.50 | 95.3 | 15.4% |
| 11.00-13.00 | 54.3 | 9.4% |
Every window starting at 9:45 beats every window starting later, by 3-7x.
The edge is concentrated in the early session. **Never start after ~10:00.**

### 5. FULL-REGISTRY (196 never-tested pairings): nothing beats the incumbent
Best new pairing `so_k21_th25 + bb_break_short` → hold_mean $1,187, vs the
incumbent's $1,355-1,458. `bb_break_short` recurs in the registry top-20 and is
the only short showing independent merit — worth a closer look, but it did not win.

### ══ CURRENT BEST, CONFIRMED BY HOLDOUT ACROSS ALL SWEEPS ══
**`sr_round100_break` (long) + `vol_lw_stretch_short` (short)**
9:45-15:30, ALL weekdays, cap $440, ≤10 ct, risk_frac 1.0
  - SL 2.0 / TP 3.0 → holdout mean **$1,458**, 45.9% paid
  - SL 2.0 / TP 1.5 → holdout mean $1,269, **48-49% paid**, holdout median $339
Selection-window numbers are much lower ($276-961) — i.e. this is NOT fitted to the
recent window, which is the right way round.

### ⭐ 7. NEW BEST LONG — Mark Fisher's ACD weekly pivot
`rank_traders.py` over all 271 families:

| role | family | trader | hold_net | hold_bust | both_pos |
|---|---|---|---|---|---|
| **BEST LONG** | **`mf_wkpiv_long`** | **Mark Fisher (ACD)** | **$8,726** | **37.5%** | yes |
| prev best long | `sr_round100_break` | generic | $6,114 | 58.1% | yes |
| BEST SHORT | `vol_lw_stretch_short` | **Larry Williams** | $10,635 | 35.3% | no |
| best trader short | `lr_raschke_firstcross_short` | **Linda Raschke** | $5,825 | 57.1% | yes |

Mark Fisher's weekly pivot beats the incumbent long by **43% on holdout with 20
points LESS bust**. Also strong: `tt_turtle_s2_long` ($6,737 / 38.5% bust / both_pos),
`lr_raschke_anti_long` ($2,592, 16 holdout payouts), `cn_connors_rsi2_short` ($3,342).

**BOTH top families in the entire registry are now published trader methodologies.**
That is the strongest argument yet for mining named methods over generic strategy
blogs — 85 trader strategies produced a new #1 long, while 196 never-tested generic
registry pairings produced nothing that beat the incumbent.

**IN FLIGHT:** `pair_traders.py` -> `tp_0..7.csv` (incremental). 100 pairings of the
10 best trader/incumbent longs x 10 best shorts, windows all starting 9:45.
FIRST THING TO CHECK ON RESUME: does `mf_wkpiv_long + vol_lw_stretch_short` beat
`sr_round100_break + vol_lw_stretch_short` (holdout mean $1,458, 45.9% paid)?

### 6. TRADER METHODOLOGIES — 85 new strategies, all audited clean
`strategies_web/tr_*.py`: cn (Connors 14), lr (Raschke 14), lw (Larry Williams 13),
mf (Mark Fisher ACD 12), tt (Turtles 14), jc (Carter/Crabel 10), ab (Brooks 8).
**All 85 pass the lookahead audit; 0 disqualified.** Note the 5 agents that
"failed" on session limits had already written their files — always check disk.
NOT YET EVALUATED. `rank_sides.py` re-run is in flight (`rank2_out.log`,
writes `rank_sides.csv`). Next: rank them, then pair the best against the incumbent.

## ██ 2026-08-09 EVENING — AUTONOMOUS RESEARCH RUN (user away, continue until "done") ██

### ⭐ FINDING 1 — EVERY RANKING IN THIS PROJECT USED THE WRONG METRIC
`rank_clean.py` / `harvest_clean_rank.py` re-scored all **349 families** by EDGE
OVER THE CLEAN CONTROL instead of net P&L. The two orderings barely relate:

> **Spearman correlation between old `hold_net` and clean edge: +0.265** (n=349)

Of the old top-10 by holdout net, where they actually rank on edge:

| family | old net | edge | edge rank |
|---|---|---|---|
| `vol_lw_stretch_short` | $10,635 | **+19.88** | **5 / 349** |
| `mf_wkpiv_long` | $8,726 | +3.22 | 89 |
| `so_k21_th30` | $8,235 | +4.05 | 77 |
| `ema20_50_long` | $7,304 | +4.21 | 76 |
| `tt_turtle_s2_long` | $6,737 | **−0.11** | 162 |
| `ww_volsys_short` | $6,439 | +7.30 | 44 |
| `wy_lps_long` | $6,121 | +9.96 | 26 |
| **`sr_round100_break`** | $6,114 | **+4.77** | **71** |
| `ww_psar_short` | $6,101 | **−4.70** | 272 |

Across all families: median real +0.28 ppt, median control +0.46, **median edge
−0.18**. 53.5% look profitable on net; only **46.8% have positive edge**. Net was
measuring the market, not the rule.

**THE INCUMBENT SHORT IS EXCELLENT (rank 5). THE INCUMBENT LONG IS THE WEAK LINK
(rank 71, edge +4.77).** Eleven longs clear +9.9. Best by edge, ≥100 trades:
`vwap_avwap_pdhigh_reclaim_long` +25.75 · `qm_ep_long` +20.84 ·
`ic_sweep_fvg_long` +15.32 · `lw_gsv_long` +11.68 · `wy_lps_long` +9.96.
Best shorts: `ib_va80_short` +27.87 (only 68 tr) · **`lw_gsv_short` +26.71 (174 tr)**
· `ms_kfade_short` +20.50 · incumbent +19.88.
⚠ 678 rows searched, so ~75 would show "0/8 shuffles beat it" by chance. Edge
MAGNITUDE plus trade count is the signal; `beaten==0` alone is not.
Full ranking: `rank_clean_sorted.csv`.

### ⭐ FINDING 2 — THE EXITS WANT LESS MANAGEMENT, NOT MORE
`exit_sweep.py`, 576 combos. Every lever is monotonic and they all point the same way:

| lever | mean ppt across the range |
|---|---|
| stop 1.5 → 2.0 → 2.5 → **3.0** ×ATR | 6.77 → 8.09 → 8.28 → **9.30** |
| target 2.0 → 3.0 → 4.0 → **5.0** ×ATR | 7.13 → 7.84 → 8.67 → **8.80** |
| time stop **off** / 48 / 24 / 12 bars | **9.03** / 8.98 / 7.66 / 6.78 |
| breakeven **off** / 1.0 / 1.5 ×ATR | **9.05** / 7.22 / 8.06 |
| trailing **off** / 1.5 / 2.5 ×ATR | **9.05** / 6.72 / 8.57 |

Best: **SL 3.0 / TP 5.0, nothing else → +16.91 ppt vs the incumbent's +12.25 (+38%)**,
positive in all 6 years, worst year +5.01. 32 of 576 beat the incumbent in all 6 years.
**Breakeven stops, trailing stops and time stops all HURT.** Do not add them.

**RESOLVED — THE EXIT FINDING IS DEAD (candidate #5 killed).** At account level only
1 of 40 combos survived (SL3.0/TP3.0 cap440 bud400: paid 61.5%, bust 2.1%, mean
$2,716, median $1,230 vs $334). `verify_exit33.py` then ran the 81-cell paired
toggle: **wins on mean 39/81 (48%), median delta −$6, median wins 22/81 (27%)**. It
collapses to **7/27 on the one signal pair it was not found on** (median −$215) and
is budget-dependent (10/27 at $300, 15/27 at $500). A genuine exit improvement must
generalise across signals; this does not. **Keep SL 2.0 / TP 3.0.**

The one real, generalisable effect: a wider stop reliably LOWERS bust (worse in only
17/81, median **−2.1 points**) because it shrinks position size. It buys safety, not
return. Also: the account optimum (TP 3.0) differs from the points optimum (TP 6.0,
a true interior peak) because `(cap − net)/(ATR×TP×$2)` shrinks the position that
funds a wider target. **Points and dollars optimise in opposite directions here.**

### ⭐ FINDING 3 — THE RIGHT METRIC IS TOTAL EDGE (edge × trades), NOT EDGE/TRADE
`pair_edge.py` built 384 pairings from the edge-per-trade leaders: **0 beat the
incumbent** on mean+median with bust no worse. The incumbent config is #1 by holdout
mean in the whole grid. Reason: edge-dense signals are RARE, and a rare signal cannot
climb $1,100 to the buffer inside a year.

| family | trades | edge/trade rank | **total-edge rank** |
|---|---|---|---|
| `sr_round100_break` | 624 | 68 | **13** |
| `vol_lw_stretch_short` | 225 | 5 | **2** |
| `vwap_avwap_pdhigh_reclaim_long` | 101 | 3 | 16 |
| `qm_ep_long` | 130 | 9 | 36 |

Total-edge leaders: **`lw_gsv_short` 4,648 (rank 1)** · `vol_lw_stretch_short` 4,473
· `rh_irb_gated_short` 4,131 · `macd_x_short` 3,870 · `donch20_short` 3,798 ·
`tm_open_newlow` 3,750 · **`ic_fvg_long` 3,656 — the best LONG, 505 trades, and it
was not in the previous sweep at all** · `sr_round100_break` 2,976.
`pair_total.py` → `pt_*.csv` is testing this corrected list.

**METHODOLOGY, three metrics deep:** net P&L reads the market; edge/trade reads the
rule but ignores frequency; **edge × trades is what the account experiences.** Rank
on the third.

**RESOLVED — the total-edge list ALSO fails (candidate #7).** `pair_total.py`, 128
pairings from the corrected list: **0 beat the incumbent** on mean+median with bust
no worse. The incumbent config is #1 AND #2 by holdout mean, and both incumbents top
their own per-family averages (`sr_round100_break` $1,335 best long,
`vol_lw_stretch_short` $1,557 best short — next best $956).
**Three metrics, three sweeps, 708 pairings today. The incumbent pair is unbeaten.**
Worth noting but NOT actionable (23 recent accounts): `ww_psar_dmi_long +
vol_lw_stretch_short` bud300 gives recent paid 52.2% / mean $590 vs the incumbent's
43.5% / $324, on a holdout mean of only $1,511.

### ⭐⭐ FINDING 5 — THE SIGNALS' OWN CONSTANTS WERE NEVER SWEPT. TWO SURVIVE AT 81%.
`param_sweep.py` + `verify_params.py`. The re-implementation was validated to
reproduce both plug-ins **bar-for-bar** first (the first attempt over-fired by 240
bars — `same_day` is `day == day.shift(1)`, NOT a pdh/pdl validity check).

27-cell paired toggle on the holdout, one parameter at a time:

| change | mean wins | d_mean | d_bust | verdict |
|---|---|---|---|---|
| `RVOL_THRESH` 1.0 → **0.8** | **22/27 (81%)** | **+$274** | −0.4 | live |
| `VOL_LOOKBACK` 20 → **40** | **22/27 (81%)** | **+$641** | 0.0 | live |
| `BREAK_BUF_ATR` 0.15 → 0.10 | 14/27 (52%) | +$11 | +0.7 | **reject** |
| `LW_K` 0.50 → 0.35 | **1/27 (4%)** | **−$481** | +2.1 | **reject hard** |
| `LW_K` 0.50 → 0.45 | 8/27 (30%) | −$184 | −1.4 | reject |
| ALL FOUR | 8/27 (30%) | −$441 | +2.4 | reject |
| LONG THREE only | 19/27 (70%) | +$443 | 0.0 | weak |
| `ROUND_STEP` 100 | — | — | — | genuine optimum, keep |

**`LW_K` is the cleanest demonstration yet that total edge can mislead.** The sweep
said 0.35 was better (total edge 5,096 vs 4,474) because it trades more; the account
says **1 of 27**, because the daily cap and loss budget bind and the extra trades are
lower-quality. **Keep LW_K = 0.50.**

**RECENT 5 MONTHS (untouched by this search), cap440/bud300:**

| variant | paid | mean | median | days |
|---|---|---|---|---|
| DEFAULT | 43.5% | $324 | $0 | 26 |
| rvol 0.8 | 47.8% | $628 | $0 | 22 |
| vol_look 40 | 47.8% | **$778** | $0 | **16** |
| **ALL FOUR** | **52.2%** | **$930** | **$316** | 17 |

⚠ **DIRECT CONFLICT: ALL FOUR is the BEST in the recent window and only 30% on the
holdout.** With 23 recent accounts that is most likely noise, not regime adaptation.
Do not act on the recent column alone — that is the exact error that produced the
"26-day payout" config from an edgeless strategy.

Per year, neither survivor is clean: `vol_look 40` is better in **3/5** years,
`rvol 0.8` in **2/5**. Compare `%K 14→21`: **6/6**. So 81% + 3/5 is the strongest
lead of the day but below the standard that has ever been trusted here.
**⭐ THE 2-D GRID CAME BACK CLEAN — THIS IS THE STRONGEST FINDING OF THE SESSION.**
`verify_rv.py`, rvol 0.7-1.0 × vol_look 20-60, win% vs the default over 27 cells:

| rvol \ vol_look | 20 | 30 | 40 | 50 | 60 |
|---|---|---|---|---|---|
| **0.7** | 81 | 78 | **85** | 81 | 78 |
| **0.8** | 78 | 74 | 81 | 78 | 81 |
| **0.9** | **96** | 81 | 81 | 81 | 81 |
| **1.0** | *default* | 81 | 81 | 74 | 81 |

**19 of 19 alternatives beat the default, every one at 74-96%.** Median d_mean
+$290 to +$664 across the whole surface. This is not an isolated spike — it says
the default RVOL setting (>1.0 against a 20-bar mean) is simply a bad choice, and
almost any loosening improves the account. A smooth, uniformly positive surface is a
categorically different object from the eight single-cell picks that died today.

Recent 5-month mean (untouched; default $324) rises monotonically as the filter
loosens: **$311 → $839 → $1,316**, paid 46.7% → 60.0%.

**PER-YEAR VERDICT (`verify_rv2.py`, 9 cells per year, 6 years) — REAL BUT MODEST:**

| point | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | total | yrs better |
|---|---|---|---|---|---|---|---|---|
| **`vol_look` 20→40 only** | 7/9 | 7/9 | 8/9 | **1/9** | 7/9 | 6/9 | **36/54 (67%)** | **4/6** |
| rvol 0.9 + vl 40 | 8/9 | 3/9 | 9/9 | 1/9 | 7/9 | 4/9 | 32/54 (59%) | 3/6 |
| rvol 0.7 + vl 40 | 8/9 | 3/9 | 9/9 | 2/9 | 3/9 | 6/9 | 31/54 (57%) | 3/6 |
| rvol 0.9 + vl 20 | 9/9 | 5/9 | 7/9 | 7/9 | 5/9 | 4/9 | 37/54 (69%) | 3/6 |

Mean $/yr at 9:45-11:00 cap440: default 66 / 2,595 / 951 / 228 / 2,243 / 507 →
`vol_look 40`: **633 / 2,705 / 1,785 / 212 / 1,687 / 891**.

### ⛔⛔ RETRACTED — `VOL_LOOKBACK` 20→40 IS ALSO REJECTED (candidate #9)
I accepted this one iteration ago on the aggregate evidence. `final_config.py`
scored it end-to-end **at the cell we actually trade** (9:45-11:00, cap 440, bud
300) and it is WORSE there:

| config | paid | **bust** | mean | med | days | recent mean | recent paid |
|---|---|---|---|---|---|---|---|
| **INCUMBENT vl20** | **56.0** | **2.1** | **$2,352** | **$334** | 27 | $324 | 43.5 |
| NEW vl40 | 52.2 | **4.1** | $2,087 | $317 | 25 | **$778** | **47.8** |
| NEW vl40, 9:45-10:45 | 51.2 | **5.2** | $1,938 | $322 | 25 | $714 | 43.5 |

**Bust DOUBLES (2.1% → 4.1%)** while paid, mean and median all fall. It is better
only in the recent 23-account window.

**THE METHODOLOGICAL LESSON — this one is new and important.** The 22/27 cell win
and the +$641 median d_mean were real, but they are an average over 27 cells
*including caps, budgets and windows we do not trade*. **A parameter can win most of
the cell space and still lose at the one cell you actually run.** From now on:
verify at the TARGET CELL before accepting anything, not just on aggregate win rate.
All three configs still pass the clean control (edge +11.09 to +11.87, 0/12 beaten),
so the edge is real in every case — the account economics are what differ.

**Keep every parameter at its default: `ROUND_STEP` 100, `BREAK_BUF_ATR` 0.15,
`RVOL_THRESH` 1.0, `VOL_LOOKBACK` 20, `LW_K` 0.50.**

### ⭐⭐ FINDING 7 — EVERY HEADLINE NUMBER HAS BEEN QUOTED WITH FALSE PRECISION
`bootstrap_ci.py`, 400 resampled 5-year paths, 10-session blocks (blocks preserve
volatility clustering; an i.i.d. shuffle would give intervals far too tight):

| metric | 5th pct | **median** | 95th pct | realised (what I quoted) |
|---|---|---|---|---|
| paid | 25.0% | **50.0%** | 75.0% | 56.0% |
| **bust** | 0.0% | **0.0%** | **16.7%** | 2.1% |
| mean | $738 | **$1,891** | $3,402 | $2,352 |
| median | $0 | **$378** | $2,549 | $334 |

**The realised path beats the bootstrap median on every single metric — 67.5% of
paths have a mean below the $2,352 I have been quoting.** The 5-year history is a
mildly lucky draw, and every figure in this file should be read down accordingly.

**The two corrections that matter most:**
- **"56% get paid" is really "25%-75%".** The point estimate carried far more
  precision than 291 heavily-overlapping starts on one path can support.
- **"2.1% bust" badly understates the tail. 9.2% of paths bust above 10%**, and the
  95th percentile is **16.7%**. The near-zero bust rate is the typical case, not the
  bound. Anyone sizing off 2.1% is under-reserving.

Honest restatement for any future report: *payout probability ~50% (range 25-75%);
bust usually near zero but roughly 1 path in 11 exceeds 10%; mean ~$1,900 (range
$740-$3,400); the typical account clears ~$378 and could easily clear nothing.*

**BY STARTING DEFICIT (`bootstrap_down.py`, 300 paths each) — the user's real case:**

| deficit | room | paid 5/50/95 | bust 5/50/95 | mean 5/50/95 | paths bust >10% |
|---|---|---|---|---|---|
| −$0 | $1,000 | 25 / **50** / 75% | 0 / 0 / **17%** | $767 / **$1,819** / $3,401 | 11.7% |
| −$250 | $750 | 17 / **42** / 67% | 0 / 0 / **17%** | $429 / **$1,586** / $3,161 | 15.7% |
| **−$500** | **$500** | **8 / 33 / 58%** | 0 / 0 / **17%** | **$169 / $1,191 / $2,505** | 12.7% |

Note what does and does not move. The **payout probability collapses** as the
cushion shrinks (median 50% → 42% → 33%, and the 5th percentile falls 25% → 8%), but
the **bust tail is flat at ~17% across all three** — because floor-aware sizing
converts a shrinking cushion into smaller positions, so a wounded account stalls
rather than dying. Confirms the earlier point-estimate finding with an error bar
around it. At −$500 there is also a **1.3% chance no account pays at all** over five
years, which is zero at a full cushion.

### ✅ FILL REALISM — THE 5-MINUTE BACKTEST IS HONEST
`fill_realism.py` replayed all 799 holdout trades against the **1-minute** series
(495,150 bars):

> **0 trades differ. 0.00 pts/trade difference. 0 bars straddled both levels.**

The stop-first tie-break never had to be invoked, and no exit changes at finer
resolution — so the 2.0 ATR / 3.0 ATR brackets are wide enough that intrabar path
never decides the outcome. Combined with the earlier slippage test (survives to 4
ticks/side), execution assumptions are not where the risk lies.

⚠ **MY OWN BUG, caught before reporting.** The first run showed −3.96 pts/trade
(−32%) and I nearly reported "the backtest is 32% optimistic". **5-min timestamps
are the bar START** (verified 400/400 bars match the 1-min bars in `[t, t+5)`, vs
4/400 for `(t−5, t]`), so a bar stamped 09:45 CLOSES at 09:50. Scanning 1-min bars
from `hidx[i]` let the stop be hit by the four 1-min bars *inside the entry bar* —
price action before the position existed. Fix: start the scan at `hidx[i] + 5 min`.
**Any future 1-min work must add 5 minutes to a 5-min bar stamp to get its close.**


### ══ SESSION 2 (2026-08-10) — SIX MORE AXES, ALL REJECTED. 17 TOTAL. ══

**LONG-ONLY / SHORT-ONLY / SHORT+SHORT — all worse than the pair.**
| config | paid | bust | mean | med | days | recent |
|---|---|---|---|---|---|---|
| PAIR | 56.0 | 2.1 | **$2,352** | $334 | **27** | **$324** |
| long only `sr_round100_break` | 38.1 | 1.0 | $973 | $0 | 36 | $320 |
| long only `mf_wkpiv` (Fisher) | 30.2 | 0.0 | $710 | $0 | 77 | $676 |
| short only `vol_lw_stretch` | 60.5 | 0.0 | $1,304 | $526 | 88 | **$0** |
| short+short | 52.2 | 0.3 | $1,222 | $282 | 66 | $16 |

Short-only looked like a find (60.5% paid, 0% bust, positive median) but across 27
cells it wins payout in only 14/27 (52%) and **mean in 1/27**. Per year its ENTIRE
advantage is 2024 ($1,019 vs the pair's $228; in the other five years $73-$163 vs
$508-$2,597), and **all 80 short-only configs earn $0 in the recent 5 months.**
Bootstrapped it is genuinely lower-risk/higher-hit-rate (paid median 66.7% vs 50%,
bust 95th 8.3% vs 16.7%) but lower-return (mean $1,342 vs $1,891). Not a replacement.
Short+short: **0/27 cells**, d_mean −$1,148. **The shorts carry the edge per trade;
they cannot carry an account.**

**"BUY THE LOW" IS CLOSED — it fails at BOTH timescales and deeper is always worse.**
Built `tr_lo.py` (22 fade families, all audit-clean). Only 4 of 11 longs have positive
edge, best +3.71 (below the incumbent long's +4.74), median across the family −2.72.
The most intuitive versions are the worst: RSI(2) oversold −13.19, prior-day-low
reclaim −10.67, failed breakdown −9.69, all beaten 9-10/10.
`extreme_low.py` swept extremity: below session open −1→−4 ATR gives edge −4.63 →
**−7.95**, monotonically worse, all beaten 10/10. RSI(2) only turns positive at
**n=13** — the textbook small-sample mirage.
`tr_ex.py` then tested the MULTI-DAY washout (the version left untested when a broken
rolling window returned 0 trades): 3d −3.83/deep −6.44, 5d −9.58/deep −11.43,
10d −5.48/deep −12.07. **Deeper is worse at the multi-day scale too.**
Mechanism: when MNQ is genuinely low intraday it KEEPS GOING. That is trend
continuation, and it is why the incumbent long buys STRENGTH (a break above a round
number) rather than weakness.

**EXHAUSTION SHORTS: real but irreducibly rare.** The highest per-trade edges found
anywhere were `hi_rsi2_short` +22.56 (56 trades) and `hi_blowoff_short` +14.80 (48).
Loosening destroys it: RSI(2)@88 +7.54 → RSI(5) +2.15 → RSI(9) −4.70 → RSI(14) −5.37,
and the whole blow-off family is negative at every strictness (−1.99 to −4.29, beaten
7-9/10) — so +14.80 was noise. One survivor, `ex_streak5_short` (5 up-closes then a
down-close, 230 trades, edge +6.31, beaten 1/10) scored **7/27 (26%), d_mean −$374**
at account level. Rejected.

**TIMEFRAME — the last untouched axis. 5-minute is right.**
| signal TF | paid | bust | mean | days | recent |
|---|---|---|---|---|---|
| **5m** | 56.0 | 2.1 | **$2,352** | **27** | **$324** |
| 15m | 55.3 | 1.4 | $1,480 | 50 | $0 |
| 30m | 67.7 | 0.0 | $846 | 119 | $0 |

Slower bars raise payout rate and cut bust but roughly halve the mean and 2-4x the
wait, and produce **$0 recently**. Sizing brackets from a slower ATR while keeping
5-min entries is worse on every axis (mean $1,126-$1,265, median $0).

**RUNNING TALLY: 17 candidates/axes tested across both sessions, 17 rejected. The
incumbent config has not moved.** Further mining has negative expected value.

### ══ NINE CANDIDATES TESTED THIS SESSION, NINE REJECTED ══
1. fold-in `ema20_50_long` (47% of 36) · 2. `wy_lps_long` (67% of 36) ·
3. 20 new-trader pairings (0/20) · 4. wide session window (6/11 blocks, coin flip) ·
5. exit SL3.0/TP3.0 (48% of 81) · 6. 384 edge-ranked pairings (0/384) ·
7. 128 total-edge pairings (0/128) · 8. 10 total-edge fold-ins (all 0-19%) ·
9. `VOL_LOOKBACK` 40 (worse at the target cell, bust doubles).

**The incumbent config is unchanged and has now survived a far harder battery than
it originally passed.** Further mining of this space has negative expected value —
the search has been thorough enough that additional "winners" are more likely to be
false positives than improvements.

### ⛔ FOLD-IN ATTEMPT #3 — DECISIVELY REJECTED (candidate #8)
`foldin_total.py`, 10 candidates chosen by TOTAL EDGE, paired across 27 cells:
**every single one scored 0-19%**, d_mean −$157 to −$1,045.

| addition | mean wins | d_mean |
|---|---|---|
| `+S lw_gsv_short` (total-edge rank 1) | 5/27 (19%) | −$157 |
| `+S rh_irb_gated_short` | 2/27 (7%) | −$542 |
| `+S donch20_short` / `tm_open_newlow` / `wy_sow_short` | **0/27** | −$586 to −$885 |
| `+L ic_fvg_long` (best long by total edge) | 3/27 (11%) | −$599 |
| `+L vwap_reclaim_long` | 0/27 | −$1,045 |

**THREE fold-in attempts, three different selection metrics (standalone net, paired
account mean, total edge), all rejected.** This is now a firm structural conclusion,
not a series of near-misses: **the two-signal pairing is COMPLETE. Do not add
signals.** Mechanism — the daily loss budget is consumed by the extra lower-quality
trades while the daily profit cap prevents the extra winners from compounding, so
the account penalises trade volume beyond what the base pair supplies.

### ⭐ FINDING 6 — THE TRADES-PER-DAY CAP IS INERT, AND THE STRATEGY BARELY TRADES
`sweep_struct.py`. Max trades/day swept 1, 2, 3, 4, 6, 8 — **every value gives
byte-identical results** (paid 56.0%, bust 2.1%, mean $2,352, med $334, 27 days).
The paired test confirms it: 0/6 cells differ for any value ≥ 2.

**Because the strategy takes 0.68 trades per session.** 799 trades over 1,181
sessions, and ~40% of sessions produce no trade at all. The "6 trades/day" in every
spec written so far is decoration — the cap has never once bound. Practical
consequence for the user: this is a **fewer-than-one-trade-a-day** system, so most
days there is nothing to do, and a quiet week is not evidence of anything.

**SUB-WINDOWS inside 9:45-11:00** (the window had been tested against later starts
but never split internally):

| window | paid | bust | mean | recent mean | yrs > base |
|---|---|---|---|---|---|
| 9:45-10:15 | 51.9 | 1.4 | $1,813 | $224 | 2/6 |
| 9:45-10:30 | 51.2 | 4.5 | $1,961 | $380 | 2/6 |
| **9:45-10:45** | 54.0 | **1.7** | $2,332 | **$397** | **4/6** |
| 9:45-11:00 (incumbent) | **56.0** | 2.1 | **$2,352** | $324 | — |
| 9:45-11:30 | 51.5 | 2.7 | $1,714 | $494 | 1/6 |
| 10:00-11:00 | 41.6 | **10.3** | $1,264 | $143 | 1/6 |

**9:45-10:45 is a tie, not a win** — $2,332 vs $2,352 mean, slightly lower bust and
better recent, 4/6 years. Worth noting only as "the last 15 minutes contribute
nothing", which is an operational convenience, not an edge. The 10:00 start
collapsing to 10.3% bust re-confirms that the 9:45 open is essential.

### ⭐ FINDING 4 — YOU CANNOT SEE THE DEAD PATCHES COMING, AND REACTING COSTS MONEY
`regime_predict.py`, 24 half-blocks of ~2.5 months:

- **PERSISTENCE IS ZERO.** Block edge vs next block edge: **Pearson +0.065,
  Spearman −0.093** (n=23). Last period tells you nothing about the next.
- **A LOSING BLOCK IS FOLLOWED BY BETTER THAN AVERAGE.** After a negative block
  (n=4): next edge mean **+16.70, positive 4/4**. After a positive block (n=19):
  **+9.34, positive 79%**. Small n, but the direction is the opposite of decay.
- **A STAND-DOWN RULE LOSES MONEY.** Hold through everything: total edge **+246.0
  over 24 blocks (+10.25/block)**. Skip the block after any loss: **+179.2 over 20
  blocks (+8.96/block)**. Worse on both the total and the per-block average.
- Market-state predictors are noise: prior-block volatility correlates +0.405 with
  next edge but same-block ATR correlates **−0.342** and same-block range −0.338 —
  opposite signs, which at n=23 means no structure.

**⚠ THIS RETRACTS MY OWN ADVICE, TWICE OVER.** I told the user to "trade at minimum
size until the block edge turns positive." Sizing down was already shown wrong
(`starting_down.py`: at a $100 budget only 4.8% ever get paid). Now the WAITING half
is wrong too — the edge is unpredictable, and the one historical case of standing
down would have missed the best block in the sample. **Correct guidance: hold size,
hold through.**

## ██ 2026-08-09 FINAL — THE EDGE IS REAL. THE CURRENT REGIME IS THE WORST ON RECORD. ██

Three controls were run, each fixing the previous one's flaw. **Only the third is
valid — `clean_control.py`. Use it, not `bog_control.py`, for any future verdict.**

| control | flaw | verdict |
|---|---|---|
| 2026-08-08 "0/14 seeds" | scattered fires across the WHOLE session → randomised trade count HALVED | pass (wrong) |
| redo #1 | same flaw | absurd — random won 7x |
| redo #2 (in-window) | preserved per-session fire COUNT → random arm knew WHICH SESSIONS would fire | real lost 59/60 (wrong) |
| **`clean_control.py`** | **permutes the session profile AND the bar** | **real wins 20/20** |

**CLEAN RESULT, holdout 2021-2026, trade level, no fees/sizing/account rules:**
> REAL **+12.25 pts/trade** vs shuffled-random **+0.39** (range −4.86 to +4.98).
> **0 of 20 seeds beat it.** 799 trades.

The edge is real, and it lives in **SESSION SELECTION** — knowing which days to
trade — not in bar timing. That is why redo #2 failed: handing the random arm the
session list gave it ~+17 pts/trade for free.

**PER 5-MONTH BLOCK (`edge_by_block.py`) — edge = real minus same-block control:**

| block | trades | real | control | edge | shuffles beating real |
|---|---|---|---|---|---|
| 2022-01 | 86 | +8.38 | −10.10 | **+18.49** | 1/10 |
| 2022-06 | 77 | +21.24 | −0.54 | **+21.78** | 0/10 |
| 2022-11 | 64 | +27.23 | +8.99 | **+18.25** | 0/10 |
| 2023-04 | 70 | +12.74 | +5.64 | +7.10 | 0/10 |
| 2023-09 | 61 | +10.07 | −0.41 | +10.48 | 2/10 |
| 2024-02 | 61 | +7.02 | +3.51 | +3.51 | 4/10 |
| 2024-07 | 81 | +10.81 | −0.27 | +11.08 | 1/10 |
| 2024-12 | 80 | −4.71 | −3.55 | −1.16 | 5/10 |
| 2025-05 | 71 | +25.58 | +2.18 | **+23.40** | 0/10 |
| 2025-10 | 92 | +10.66 | +3.09 | +7.57 | 2/10 |
| **2026-03 (now)** | **104** | **+0.17** | **+5.35** | **−5.18** | **6/10** |

**9 of 11 blocks positive, median edge +10.48. The CURRENT block is the worst of
all eleven.** The only other negative block (2024-12) was followed immediately by
the best block in the sample. So "it is failing now" is correct and measurable —
and is not, on this evidence, proof the edge is gone.

### ⛔ DEAD END — the "+39 pts/trade at 09:45" replacement was LOOKAHEAD
It entered on the 09:45 bar in the direction of a signal that had not fired yet —
84.4% of the time the signal comes later, median 15 minutes. Front-running itself.
Stripped of the foreknowledge it collapses: "signal days, always LONG" +4.97,
"EVERY day always LONG" +2.20 gross / **+0.59 after 2 ticks**, and −9.72 in the
recent window. Raw 09:45→close drift is only +2.23 pts/session. **There is no
drift-harvesting strategy here.** Do not revive it.

### ══ superseded verdict, kept for the record ══

`diag_entry_edge.py`, trade-level only — no fees, no sizing, no account rules, so
none of the simulator's quirks can be blamed. Signal count, trade count, side mix
and WHICH SESSIONS TRADE are all held identical; only the choice of bar changes:

| cut | real pts/trade | random median | seeds beating real |
|---|---|---|---|
| both sides, SL2/TP3 | **+12.25** | +20.74 | **10/10** |
| long only | +6.77 | +13.32 | 10/10 |
| short only | +19.59 | +34.25 | 10/10 |
| SL2.0/TP1.5 | +7.31 | +12.76 | 10/10 |
| SL1.0/TP1.5 | +3.55 | +8.62 | 10/10 |
| 2021 / 22 / 23 / 24 / 25 / 26 | — | — | 9/10 then 10/10 ×5 |

**59 of 60 comparisons.** Both sides. Every year. Every bracket.

### WHY THE 2026-08-08 CONTROL PASSED IT (0/14 seeds) AND THIS ONE FAILS IT
That control had the same trade-count bug found and fixed today: it scattered
random fires across the WHOLE session and let the window filter them afterwards,
which HALVED the randomised trade count. It was comparing "real, N trades" to
"random, N/2 trades" — so random looked weak and the pairing looked strong. **The
pairing was accepted on a broken control.** Fixed in `bog_control.randomise()`,
which now draws only from bars the window accepts and hard-fails if in-window
counts do not match (all 12 processes printed the match confirmation).

### WHAT IS ACTUALLY GOING ON
The book is 78% long by trade count and MNQ rises across most of the holdout, so a
long-biased position with a 3:2 reward:risk earns from DRIFT regardless of when it
opens. `sr_round100_break` buys closes above round numbers — local highs — which
is a systematically bad moment to open a long that would otherwise ride drift.
The profit was never the signal; the signal was subtracting from it.

### THE ACTIONABLE PART (`diag_fixed_entry.py`)
Same sessions, same directions, same trade counts — only the entry bar differs:

| entry rule | pts/trade | trades | win% |
|---|---|---|---|
| signal (incumbent) | +12.25 | 799 | 50.2 |
| random (control) | +20.53 | 801 | 54.1 |
| **fixed first bar 09:45** | **+39.38** | 691 | **65.4** |
| fixed 10:00 | +28.39 | 692 | 58.7 |
| fixed 10:30 | +20.86 | 691 | 53.5 |

Monotonic decay by clock time — earlier is better, and the trigger is worse than
every fixed time AND worse than random. **A tradable replacement exists: keep the
day/direction the signal picks, discard its opinion about the minute, enter on the
09:45 bar.** 3.2x the incumbent's points per trade.

### ⚠ DO NOT TRADE THE 09:45 RULE YET — IT IS AN UNVERIFIED IN-SAMPLE FINDING
It was found on the holdout after three clock times were tried, which is exactly
the search that produced every false positive in this project. Before it means
anything:
  1. Does the DAY/DIRECTION selection carry anything? Test "long at 09:45 EVERY
     session" against "long at 09:45 only on signal days". If they match, the
     whole signal is worthless and this is pure drift harvesting — which is NOT
     fundable on a $1,000 trailing drawdown.
  2. Fees and slippage — none applied above.
  3. Out-of-sample: the last 5 months are untouched by this.
  4. Its own random control, using the FIXED randomiser.
  5. Account-level: points per trade is not payout rate.

## ══ superseded — the old "start here" note ══

The best-of-grid control was re-run 2026-08-09 and the run is **INVALID**. Output
archived to `invalid_runs/bogc_*.csv`. **Do not quote it.** It appeared to show
all 11 random seeds beating the real signals by 2-4x (random max mean $4,750-8,277
vs real $2,295) — which is not "the edge is fake", it is impossible, and that
impossibility is what exposed the bug.

**The bug:** `randomise()` scattered fires across the WHOLE session and let
`LF.prep` filter to the window afterwards. Real signals are concentrated in the
morning, so randomising halved the in-window trade count:

| signal | real in-window | randomised in-window |
|---|---|---|
| `sr_round100_break` | 782 | 432 |
| `vol_lw_stretch_short` | 225 | 107 |

Trade count is NOT a neutral variable in this account model. The $1,000 MLL bounds
the downside, floor-aware sizing shrinks positions near the floor, and the
withdrawal ratchet banks the upside — so **trading less is a large structural
advantage**. The control was comparing "real, N trades" against "random, N/2
trades" and measuring exposure, not timing.

**Already fixed in `bog_control.py`:** `randomise()` now takes an `eligible` mask
and draws only from bars the window would have accepted, so the in-window count is
held fixed; and randomisation happens PER WINDOW inside the loop, since
eligibility depends on the window. A `n_sig` column was added so the next run can
be checked for exactly this failure before anything is concluded from it.

**TO RUN (≈85 min wall-clock, 12 parallel processes):**
```
for s in -1 0 1 2 3 4 5 6 7 8 9 10; do
  n=$(echo $s | sed 's/-1/real/')
  nohup C:/Python314/python.exe bog_control.py --seed $s --out bogc_$n.csv > bogc_$n.log 2>&1 &
done
```
then `python harvest_bog.py`. **FIRST CHECK: `n_sig` must be near-identical
between REAL and every RND tag at the same window.** If it is not, the control is
broken again and its numbers mean nothing.

**This remains the one check standing between the recommendation and a fundable
decision. Nothing else is outstanding.**

## IN FLIGHT RIGHT NOW (detached processes — survive limits and session end)

26 python processes on a 20-core box. All write to `C:\Users\YOU\daytrading-automation`.

| Output | What |
|---|---|
| `m5_0..7.csv` | 5-MONTH window, 110 pairings x 144 configs, holdout alongside |
| `scA_0..4.csv` | 1-min SCALPING, 5-month window, tick targets + minute time stops |
| `scB_0..4.csv` | 1-min SCALPING, full 5 years (the 5mo window lacks power) |
| `ev_0..5.csv` | DAY-OF-WEEK x 13 time windows x 6 pairings x brackets |
| `rg_0..5.csv` | FULL-REGISTRY pairings — 14 new longs x 14 new shorts, none previously tested. **Appends incrementally**, so partial output is still usable |

**IMPORTANT:** only `rg_*.csv` writes incrementally. `m5_*`, `scA_*`, `scB_*`, `ev_*`
write ONLY on completion — if one is killed mid-run its work is lost and the slice
must be re-launched. Prefer incremental writes in any new script.

`zombie_pct` and `dead_pct` are now in `lucid_fast.evaluate`. **Rank on `dead_pct`
(busted OR never paid) and `mean_out`/`pay_pct` — never on `bust_pct` alone.**

## NAMED-TRADER METHODOLOGIES (launched 2026-08-09)

Workflow `named-trader-methodologies` researches DOCUMENTED mechanical rules from
traders with verified records and writes plug-ins to `strategies_web/tr_*.py`
(lw=Larry Williams, lr=Linda Raschke, cn=Larry Connors, mf=Mark Fisher ACD,
jc=John Carter/Toby Crabel, tt=Turtles/Dennis, ab=Al Brooks/Volman).

**Rationale, and it is empirical not aesthetic:** `vol_lw_stretch_short` — the best
short in the whole 174-family registry, present in nearly every winning pairing —
IS Larry Williams' stretch. Named published methods have outperformed generic
strategy-blog research here by a wide margin. Mine more of them.

**Literal copy-trading is NOT possible** and should not be attempted: individual
traders' entry/exit records are not public, prop leaderboards publish P&L only, and
signal-seller feeds are unverifiable. Mining published mechanical RULES is the
viable version of that idea.

When the plug-ins land: run `lookahead_audit.py --only tr_` first, then
`rank_sides.py` to score them individually, then pair the good ones. Agent files
persist even if the agent dies at the reporting step — check
`strategies_web/tr_*.py` on disk regardless of whether the workflow reported.

## NEXT STEPS, IN ORDER

1. **Harvest whatever has landed.** Concatenate `m5_*.csv`, `scA_*.csv`, `scB_*.csv`.
   Rank on: `sel_dead` low, `sel_mean`/`sel_pay` high, and check `hold_*` alongside.
   Re-launch any slice whose CSV is missing.
2. **Scalping reality check.** Early smoke test: `s3_sweep_long` at 4-tick targets
   showed `dead_pct 100%` — no payouts at all. Fees are 2.44 ticks round-turn, so
   small targets cannot clear costs. Look for whether ANY tick target/stop/time-stop
   combination produces payouts; if none does on either window, that is the answer
   and scalping should be reported as dead rather than re-swept.
3. **Best-of-grid random control** on any survivor, using the FIXED `lucid_fast`.
   The earlier `vlb_ctl_*` run used the buggy evaluate and was killed — redo it.
4. **Broader pairings.** `rank_sides.py` ranks all 174 families; only ~26 have been
   paired. `vol_lw_stretch_short` carries nearly every winner — establish whether any
   other short is independently good or whether this is a one-signal result.

## KNOWN-BAD SIGNALS (do not waste compute)

- `s1_vspike_*`, `s2_sigma_*` on a 5-month window: only 1-11 in-window fires. They
  need the full 5 years (scB) or looser thresholds.
- `scalp_coil_break_*` (5-min plug-in): 2-3 fires in 5 years. Over-constrained.
3. **Scalping research** (user explicitly asked). Nothing so far tests holds shorter
   than the 5-min bracket. Worth building: 1-minute bars (`mnq_2021-2026_1min.csv.gz`
   is already downloaded and unused), fixed-tick targets rather than ATR multiples,
   time-stop exits measured in minutes, and entries from order-flow proxies
   (volume spikes, tick imbalance). Fees are $1.22 RT/contract, so a 5-point MNQ
   target ($10/ct) loses 12% to costs — scalping must clear a much higher bar.
   Use `funded_tf_exit.py` as the timeframe/exit template.
4. **More pairings.** `rank_sides.py` ranks all 174 families by side. Only ~16 have
   been paired. `vol_lw_stretch_short` carries nearly every winner — find whether
   any other short is independently good, or whether the result is one signal.

## METHOD RULES — these killed four earlier candidates, never skip

- **Best-of-grid random control.** Testing a chosen winner against random is
  circular; apply the whole search to random signals and compare like with like.
- **Always report a holdout.** Fitting on recent data alone produced a "26-day
  payout" config from a strategy already proven edgeless (holdout: −$27,909).
- **Lookahead audit** (`lookahead_audit.py`) before trusting any new signal.
- **Slippage test.** One earlier candidate flipped negative at 1 tick.
- **Low bust alone is meaningless** — trading nothing achieves it. Always pair with
  a non-zero median withdrawal.
- Prefer **paired tests** to best-of-grid where possible (that is what made
  `%K 14 → 21` trustworthy: beat baseline in 6/6 years, 96% of matched configs).
- Long sweeps must be **background OS processes** (`Start-Process`) writing CSVs,
  so they survive a session ending mid-run.

## KEY FILES

| File | Purpose |
|---|---|
| `lucid_fast.py` | Correct rules + fast integrated simulator (`prep`/`run_account`/`evaluate`) |
| `lucid_rules.py` | Reference implementation of the same rules |
| `opt_lowbust2.py` / `rank_lowbust.py` | risk_frac × cushion sweep and ranking |
| `funded_search.py` | Signal library + funded replay |
| `funded_longshort.py` | Two-sided replay (`replay_2s`) |
| `funded_tf_exit.py` | Timeframe (5/15/30m) × exit-logic harness |
| `rank_sides.py` | Ranks all 174 families by side |
| `lookahead_audit.py` | Prefix-stability lookahead audit |
| `strategies_web/` | 90+ web-researched plug-ins (`register(df)` interface) |
| `data/databento/mnq_2021-2026_5min.csv` | 5yr MNQ 5-min through 2026-08-07 |
| `data/databento/mnq_2021-2026_1min.csv.gz` | 5yr MNQ 1-min — UNUSED, for scalping work |

## STANDING BOUNDARY

Data, signals and analysis only. **Never build or arm order execution** on a funded
or real account, however the request is phrased.

---

## 2026-08-10 — TopStep retired, daily pre-trade briefing app built

**The morning check is now an app.** `C:\trading_system\PreTrade-Briefing\`,
`run-briefing.bat` -> http://localhost:5001. Scheduled task `MNQ-PreTrade-Briefing`
fires weekdays 10:00 local = **09:00 ET**, 45 min before the window. (Atlantic and
Eastern shift for DST on the same dates, so that offset never drifts.)

It fetches VIX / 10Y / DXY / NQ from Yahoo and the high-impact USD calendar from
ForexFactory, recomputes PDH/PDL/ONH/ONL/VWAP/ATR and the round-100 grid from
5-min RTH bars, replays both live signals, and sizes the trade floor-aware. Every
run appends to `briefings/YYYY-MM-DD.json`.

**The design decision that matters:** checks are split BINDING vs ADVISORY *in
code*, not just in prose. Only binding checks can produce NO-TRADE.
- BINDING: entry window, high-impact event gate, feed freshness
- ADVISORY: VIX band, gap, 10Y, DXY, earnings — reported with the contrary
  evidence printed next to them, because volatility-regime gating was measured on
  this exact config and carried no predictive information.

Event-day exclusion is the one framework axis promoted to binding, because it is
the only one absent from the 17 rejections — untested rather than disproven. It is
labelled on the page as awaiting a paired backtest. **That backtest is the next
open item:** exclude 09:45-11:00 on CPI/PPI/NFP/FOMC/retail-sales mornings, hold
everything else fixed, paired toggle. Success = bust% falls further than payout%.

### TopStep app retired (reversible — see MNQ-Signal-System/RETIRED.md)
`claude2_app.py` was **running** with `AUTO_TRADE = True` against TopStep account
XXXX, relaunched every weekday by `Claude2_MNQ_Bot` **and** healed every 15
minutes by a `Claude2-Heal` watchdog that resurrected it once mid-session before I
found it. It could not have authenticated (PROJECTX keys live in `apex/.env`, which
`config.py`'s bare `load_dotenv()` never loads) but the intent in config was live.
Now: both tasks disabled, `.no-heal` written, `AUTO_TRADE = False`,
`launch_dashboard.bat` retired, `.disarm` written in signal-tool.
**Still needs an elevated shell:** `Disable-ScheduledTask -TaskName 'EngulfBB-AutoTrade'`
(registered `-RunLevel Highest`; currently failing harmlessly since its target
.bat was renamed in June).

### Two data traps the app works around
1. **Yahoo `chartPreviousClose` is range-dependent** — the close before the FIRST
   BAR OF THE RANGE, not yesterday's. `^VIX` over 3mo reported 17.19 as "prev
   close" when the real prior close was 14.90. Day-change is computed from the bar
   series instead. This would have silently mis-stated every macro tile.
2. **ForexFactory rate-limits (HTTP 429)** on repeated polls. Uncached, a
   rate-limit knocks out the only binding gate and turns a tradeable morning into
   STAND DOWN. Now disk-cached with a 15-min TTL, falling back to a stale copy on
   failure and reporting the age.

`selftest.py` — 41 offline assertions on the signal, level, floor, sizing, and
cache-fallback math. All passing. Run it after touching signals/levels/account.

### 2026-08-10 (later) — briefing app corrected to brief the LIVE bot

User clarified: **execution is automatic via NinjaTrader**, not manual. Three fixes.

**1. It was briefing the wrong strategy.** The app reported `sr_round100_break` +
`vol_lw_stretch_short` at SL 2.0 / TP 3.0. NinjaTrader actually runs
**StochReclaim30**, read from the deployed `.cs`:
%K(14) crosses up through 30 **and** the bar closes in its upper half, long only,
**09:45-11:35 ET**, **SL 0.75 / TP 0.5 ATR**, day stops -$300 / +$440 / 6 trades /
net green, its own FF news guard (30 pre / 10 post, pre-open settle to 10:30).
Reproduction verified bar-for-bar on today's tape: 10:55 %K=17.0 -> 11:00 %K=30.4
with an upper-half close -> fires at 29,800. The researched pair is now a clearly
labelled reference section.

Two knock-on bugs this exposed:
- The window gate used the researched 11:00, so at 11:23 it said "NO-TRADE, window
  closed" while NT could still place an order. Now gates on the bot's 11:35.
- The newest Yahoo bar is usually STILL FORMING (timestamps are bar start). NT runs
  `Calculate.OnBarClose`, so partial bars are now excluded from %K and from fires.

**2. The sizing calculator was genuinely broken.** `account.state()` did
`max(balance, max_closing, START)` — letting the CURRENT balance raise a floor that
only trails END-OF-DAY closes. Consequence: **`room` came out as exactly $1,000 for
every balance entered.** Fixed (balance must not appear in that expression) with a
regression test. The panel is now client-side JS so it updates as you type instead
of refetching five endpoints per click (~3s of apparent nothing), it shows
"STAND DOWN, 0 contracts" instead of hiding the table, and it remembers the balance.

**3. The headline no longer says "TRADE".** It says `TAPE CLEAR`, because:

> At 0.75 risk for 0.5 reward StochReclaim30 needs **60.0% wins to break even**.
> Measured over 5 years of MNQ at 1-min fills it won **58.7%**; a random-entry
> control scored **59.4%** — better than the signal. Expectancy is negative.

That is the 2026-08-08 correction, now surfaced on the page every morning as the
first thing under the verdict rather than buried here. **The highest-value change is
not day-selection — it is the reward:risk.** A 0.67 R:R needing 60% wins is the
binding problem; widening the target is the only lever that moves break-even down.
That is the open research item, ahead of the news-gate backtest.

`selftest.py` now 50 assertions, all passing.

### 2026-08-10 — 2-month backtest of the briefing gate (`PreTrade-Briefing/backtest_gate.py`)

Tested the briefing exactly as it runs: check each morning, block the session if a
high-impact USD release prints before the bot stops taking entries (11:35 ET).
Bars = Yahoo NQ=F 5m (60d, all StochReclaim30 needs — no volume). Calendar = the
saved `ff_high_usd_events_2026.csv` (verified through 2026-07-15) plus 11
individually sourced reconstructed events for the 07-16..08-10 gap, since FF
publishes no historical endpoint (lastweek/thismonth all 404).

Window **2026-06-01 .. 2026-08-07, 48 full RTH sessions. Gate blocks 16 of them (33%).**

| arm | trades | win% | need | net | worst day | maxDD | bust |
|---|---|---|---|---|---|---|---|
| baseline TP-first | 30 | 66.7% | 60.0% | +$408 | −$304 | −$1,321 | no |
| baseline SL-first | 30 | 63.3% | 60.0% | −$4 | −$304 | −$1,734 | **YES** |
| gated TP-first | 21 | 76.2% | 60.0% | +$1,228 | −$302 | −$783 | no |
| gated SL-first | 21 | 71.4% | 60.0% | +$816 | −$302 | −$1,158 | no |

Split: blocked-day trades won **4/9 = 44.4%** (net −$820); clear-day trades won
**15/21 = 71.4%** (net +$816). Intra-bar ambiguity only 1/30 (3%).

**MECHANISM CONFIRMED: all 9 removed trades were after 10:30.** The bot's own guard
already blanks 09:45-10:30 on an 08:30 release (pre-open settle), so the briefing
gate only adds the 10:30-11:35 slice. This is a ~65-minute marginal test, not
"trade CPI days or not".

#### Why this is NOT adoptable evidence — three independent reasons
1. **n = 9 blocked-day trades.** 95% CI on 4/9 is about ±32 points; 44% is
   indistinguishable from the 60% break-even.
2. **The bust is decided by $6.** Baseline peaked at +$1,534 (07-17), which locked
   the floor at +$100; a 7-of-9-losing-days streak (07-20..07-31) took equity to
   +$94 — breaching by **six dollars**. "Gate saves the account" is a coin flip that
   landed one way. Gated arm's closest approach was $520.
3. **The window ran 4.6 points HOT** (63.3% vs the 5-year 58.7%). A filter that
   looks good on a favourable sample is the standard way to adopt a filter that
   does nothing.

Not folded in. It joins the 17 rejections as **untested-at-scale**, not confirmed.
The real test needs the 4.5-year frame — but **`data/databento/mnq_2021-2026_5min.csv`
is GONE** (only derived CSVs remain), so that needs a fresh Databento pull, and that
key was burned in a previous session and should be rotated first.

Standing conclusion unchanged and reinforced by the 07-20..07-31 stretch: the
binding problem is the **0.67 reward:risk needing 60% wins**, not day selection.

### 2026-08-10 — CORRECTION: the Databento data was never gone

I reported `data/databento/mnq_2021-2026_5min.csv` as missing and told the user a
fresh paid pull was needed. **Wrong** — the earlier check globbed `data/*.csv`, which
does not descend into `data/databento/`. Everything is present:
`mnq_2021-2026_5min.csv` (354,334 rows, 2021-08-08..2026-08-07),
`mnq_2021-2026_1min.csv.gz`, `nq_2021-2026_5min.csv`. No purchase, no API key needed.
Also fixed in `fetch_mnq_databento.py`: it wrote `mnq_5min_2021-2026.csv` while every
analysis script reads `mnq_2021-2026_5min.csv` (names transposed), and END was stale.

### 2026-08-10 — SETTLED: StochReclaim30 has no edge at ANY bracket

`rr_sweep.py` — 13 stop/target combinations, 5 years, exits resolved on **1-minute**
bars (5-min entry stamp + 5 min, the bar-START alignment lesson), $1.22/ct fees,
full NT day-rules including StopWhenGreen and the no-overlapping-position guard.

**Every one of the 13 lost money net.** And the win rate tracked its own break-even
within ±1.7 points at every single combination:

| SL/TP | win% | need | edge | | SL/TP | win% | need | edge |
|---|---|---|---|---|---|---|---|---|
| 0.75/0.50 | 59.3 | 60.0 | −0.7 | | 0.75/1.50 | 32.3 | 33.3 | −1.1 |
| 0.75/0.75 | 49.4 | 50.0 | −0.6 | | 1.00/1.50 | 40.1 | 40.0 | +0.1 |
| 0.75/1.00 | 43.6 | 42.9 | +0.8 | | 1.50/3.00 | 35.1 | 33.3 | +1.7 |
| 0.75/1.25 | 36.5 | 37.5 | −1.0 | | 2.00/3.00 | 40.8 | 40.0 | +0.8 |

**A win rate that follows the break-even line wherever you move it is the signature
of an entry carrying zero information.** The reward:risk hypothesis — my own standing
recommendation for two sessions — is therefore DEAD. Widening the target cannot help
because the win rate falls exactly as fast as the bar it must clear. Two combos are
gross-positive (0.75/1.00 +$3,272; 1.00/1.50 +$3,318) but fees exceed the gross edge,
and both are positive in only 1-2 of 6 years.

### The comparison that makes it actionable — `live_vs_researched.py`

Same 5 years, same 1-min fills, same fees, same account rules:

| book | trades | win% | need | pts/trade | net $ | profitable years |
|---|---|---|---|---|---|---|
| **A** live StochReclaim30 0.75/0.50 | 923 | 59.3 | 60.0 | +0.34 | **−$10,852** | **1 of 6** |
| **B** researched pair 2.0/3.0 | 940 | 48.1 | 40.0 | **+9.64** | **+$28,157** | **6 of 6** |
| B′ researched, under NT day-rules | 825 | 48.2 | 40.0 | +10.39 | +$25,184 | 6 of 6 |

**$39,010 apart over 5 years on identical bars**, at near-identical trade counts (940
vs 923), so it is not a frequency artefact. B's +9.64 pts/trade corroborates the
original +12.25 clean-control measurement.

Honest asymmetry: B was developed on this data (with a holdout and a clean control
0/20 seeds beat), A is being tested on data it never saw. That flatters B — but not
by $39,000, and not to 6/6 years.

**Conclusion: NinjaTrader should not be running StochReclaim30.** The app now carries
this on the briefing page every morning instead of only the weaker "58.7% vs 60%".

### 2026-08-10 — the researched pair WITH the floor on (`account_outlook.py`)

The +$28,157 figure is honest about the strategy and dishonest about the account: the
harness never applied the trailing limit, so it let equity run to −$3,000 and keep
trading. Re-run with the real LucidPro rules (floor = min(peak EOD, $26,100) − $1,000;
payout at $26,100 with 3+ days and the 40% consistency rule), starting a fresh account
every 3 sessions across all 5 years — **429 simulated accounts, 180-day horizon**:

| outcome | share | median days |
|---|---|---|
| **PAYOUT** reached $26,100 | **52.7%** | 15 |
| **BUST** hit the floor | **46.4%** | 16 |
| stall | 0.9% | — |

Ending balance: 5th $23,811 · median $26,110 · 95th $26,951.
**136 of the 199 busts happened inside 20 trading days** — the first month is the risk.

**Payout rate is strongly regime-dependent, and 2026 is a bad one:**

| start year | payout | bust |
|---|---|---|
| 2021 | 25.7% | 74.3% |
| 2022 | 68.6% | 31.4% |
| 2023 | 67.4% | 32.6% |
| 2024 | 32.6% | 67.4% |
| 2025 | 65.1% | 34.9% |
| **2026** | **32.0%** | **60.0%** |

Corroborates the earlier bootstrap (~53% payout) from an independent direction.

**The real constraint is the ACCOUNT, not the strategy.** A genuinely positive-edge
book (+9.64 pts/trade, 6/6 profitable years) still busts 46% of the time because a
$1,000 trailing limit against a 2.0-ATR stop risking $150–300 means 3–6 losers ends
it. Sizing down to buy room was already tested and rejected — it destroys payout odds
without fixing bust. So expect to need multiple funded attempts; that is the shape of
the product, not a defect in the strategy.

**Not deployed.** No NinjaScript port of the pair exists. Porting it, and verifying the
port bar-for-bar against the Python replay, is the prerequisite before any live use.

### 2026-08-10 — REJECTION #18: pre-open information does not work as a filter

Tested every pre-open feature the briefing app computes against the researched pair,
5 years, strict no-lookahead (overnight range from the ETH bars the RTH frame discards;
gap from the 09:30 open; VIX/10Y/DXY from the PRIOR daily close and the SAME-DAY daily
OPEN — never the same-day close, which is 16:15 and would be lookahead).

`preopen_test.py` — 9 features x 3 terciles = **27 comparisons**. Bar set before
looking: the high-minus-low direction must hold in ≥5 of 6 years.

**8 of 9 failed immediately** (3/6 or 4/6 years): overnight range width, open's position
in the overnight range, gap (signed and absolute), prior-day range, VIX level, VIX
change, DXY change. Note in passing that VIX level ran the OPPOSITE way to the
discretionary framework's claim — high VIX was the *better* bucket ($36.18 vs $13.38
per session), consistent with the earlier finding that volatility gating carries no
information.

**1 survived: the 10Y move into the open** (5/6 years). Falling yields $38.83/session
and 51.8% wins; rising yields $10.28 and 45.5%. Monotonic across all three buckets, and
a coherent mechanism — the pair is ~74% long, rising yields are risk-off for the Nasdaq.

At ACCOUNT level (`preopen_account.py`) it looked genuinely good:

| arm | sessions | net | payout% | bust% |
|---|---|---|---|---|
| all sessions | 833 | $28,157 | 52.7 | 46.4 |
| **10Y-low tercile** | 276 | $15,642 | **62.5** | **30.5** |

And it was NOT just "trade less often" — `preopen_control.py`, 60 trade-count-matched
random thirds, median payout **48.7%** (i.e. cutting frequency at random is slightly
WORSE than trading everything). So the feature was doing something beyond frequency.

**Then it failed out-of-sample.** `preopen_oos.py` — threshold frozen on 2021-08..2024-12
(10Y ≤ −1.60 bps), evaluated once on 2025-01..2026-08, nothing re-tuned:

| arm | payout% | bust% |
|---|---|---|
| all sessions (test) | **56.2** | 40.9 |
| frozen 10Y filter | **39.4** | 38.7 |
| random third, median | 45.6 | 45.6 |

The filter came in **17 points below trading everything and below random**, with 55% of
random arms beating it. The in-sample 62.5% was in-sample luck, and 1 survivor from 27
comparisons is exactly the count chance predicts at a 5/6-year bar (~11% per feature).

**I nearly reported the 62.5% as a win. The OOS split is the only thing that caught it.**

Consequence: **no change to the app** — and that is the point. Its pre-open macro panel
is already labelled ADVISORY / not gating, with the contrary evidence printed beside it.
That design choice is now independently validated. The only binding market gate stays
the event calendar, itself still untested at scale.

### 2026-08-10 — weekly review, auto-kill rules, gold panel added to the app

**`/weekly`** — scheduled task `MNQ-Weekly-Review`, Fridays 16:20 local (15:20 ET,
after the close). Answers the five review questions, with three guards that exist
because of this project's own findings:
- refuses to name a winning/losing pattern below **10 trades** (a week is ~3 trades;
  week-to-week persistence measures **+0.065**, statistically zero)
- "new rule for next week" **defaults to NO CHANGE** — rules change on multi-year
  paired tests, not five days
- "research topic" comes from a **pre-registered backlog**, not from the week

**`killrules.py`** — every rule carries provenance and only TESTED ones can KILL:
3 TESTED (window, fade-the-low, StochReclaim30-at-all), 1 UNTESTED (event day),
7 ANECDOTAL. Two of the anecdotal rules ship with their own refutation attached —
"VIX>25 size down" (high-VIX tercile was the BEST, $36.18 vs $13.38/session) and
"yields+DXY surge → bearish" (failed OOS, 39.4% vs 56.2%). A rule whose inputs are
missing reports CANNOT CHECK, never a silent pass.

**`gold.py`** — GC=F 5-min, Asian/London session H/L, prior-day H/L, $50 round grid,
ATR, London fix clock. **No gold strategy has ever been backtested here**, so every
gold rule is ANECDOTAL and the panel is explicitly levels-not-signals.

selftest still 50/50. README reconciled (the old 58.7%-vs-random paragraph was
superseded by the 13-bracket sweep).

### 2026-08-10 — REJECTION #19: 1-minute signal timeframe (`tf_compare.py`)

15m/30m were rejected earlier; going FINER had never been tested. Both best signals
run on 5-min vs 1-min bars, exits resolved on 1-min in every arm, window 09:45-11:00,
same account rules.

| arm | trades | win% | **pts/tr** | avg ct | net $ | +years |
|---|---|---|---|---|---|---|
| 5m `sr_round100_break` | 730 | 45.9 | +4.56 | 1.7 | $12,138 | 3/6 |
| 5m `vol_lw_stretch_short` | 257 | 50.2 | **+17.97** | 1.8 | $12,174 | **6/6** |
| **5m PAIR** | 927 | 48.1 | +9.77 | 1.7 | **$27,661** | **6/6** |
| 1m `sr_round100_break` | 1258 | 40.1 | +0.20 | 3.5 | −$4,529 | 2/6 |
| 1m `vol_lw_stretch_short` | 246 | 52.0 | +13.83 | 3.6 | $17,155 | 6/6 |
| 1m PAIR | 1460 | 42.5 | +2.73 | 3.5 | $16,824 | 5/6 |
| 1m entries + 5m brackets | 1111 | 47.9 | +11.44 | 1.7 | $36,088 | 5/6 |

**⚠ SIZING CONFOUND — net $ is not comparable across timeframes.** A 1-min ATR is
~half a 5-min ATR, so the 2.0-ATR stop is half as wide and the same $300 budget buys
~2x the contracts (3.5 vs 1.7). That inflates net $ with no gain in edge. Compare
**points per contract**. On that basis every native-1m arm is WORSE: +2.73 vs +9.77
for the pair, and `sr_round100_break` collapses from +4.56 to +0.20 (the 0.15-ATR
break buffer becomes trivial at 1-min ATR, so it fires on marginal crossings — 6,723
raw signals vs 2,568 — into a stop too tight to survive noise).

**Diagnostic isolated the cause:** 1-min ENTRY TIMING with 5-min BRACKET WIDTH scored
+11.44 pts/tr and $36,088 — better than the 5m pair on both. So the tighter STOP is
what breaks the 1-min version, not the earlier entry.

**But it fails out-of-sample.** Fit 2021-24 / test 2025-26:

| arm | fit 2021-24 | test 2025-26 |
|---|---|---|
| 5m PAIR | $19,596 | **$8,065** |
| 1m entries + 5m brackets | **$30,702** | $5,387 |

The fit-period winner is not the test-period winner — the hybrid's whole advantage is
2021-2024 and it did not carry. **Do not adopt. The 5-minute pair stays.** Same
pattern as the 10Y filter yesterday: a post-hoc hybrid that looks strong in aggregate
and dies on the recent half.

**One durable finding, consistent with earlier work:** the SHORT side carries the pair.
`vol_lw_stretch_short` is 6/6 positive years at +17.97 pts/tr on 257 trades;
`sr_round100_break` is 3/6 at +4.56 on 730. Matches the earlier clean-control read
(+20.90 short vs +4.74 long). Short-only was already rejected at account level —
0.2 trades/session cannot reach the payout threshold in time.

### 2026-08-10 — "what if you used the website to decide?" (`website_gate.py`)

The app's only market-facing binding gate is the event-day check (window is already
in the strategy; feed freshness has no historical analogue). Tested on the RESEARCHED
PAIR at account level over the full span the real FF file covers, 2026-02-18..07-15,
105 sessions, 51 account starts.

| arm | net | payout% | bust% |
|---|---|---|---|
| ALL sessions (ignore the app) | −$831 | 21.6 | 78.4 |
| **GATED by the app** | −$200 | **27.5** | **58.8** |
| control: random days, same count | — | 11.8 | 67.6 |

Gate beats trading everything (+5.9 payout, −19.6 bust) AND beats count-matched random
removal (+15.7 payout). Random removal made things WORSE (11.8%), so exposure
reduction alone does not explain it. 11/60 random arms still beat it → p ≈ 0.18.

**But two things badly weaken it:**

1. **Win rates are essentially identical** — blocked sessions 41.5% (41 trades),
   clear sessions 40.0% (50 trades). The gate did NOT select better-quality setups.
   The whole difference is $/session (−$18.57 vs −$4.99), which on 41 vs 50 trades is
   very likely variance.
2. **The window is badly unrepresentative** — −$7.92/session here vs **+$21.83/session**
   over the full 5 years. It is a losing stretch, and any filter that removes trades
   has more to work with in one.

Status: **directionally positive in two windows now** (this one, and the earlier
2-month StochReclaim30 run) but the windows overlap ~6 weeks and neither is
conclusive. NOT adopted. The blocker is unchanged and it is NOT the bars — it is that
ForexFactory publishes no historical calendar, so there is no way to test this over
the 5 years of price data already on disk. Sourcing a multi-year high-impact US
release calendar is the single highest-value unblock in the backlog.

### 2026-08-10 — full-system backtest: the app making real decisions (`system_backtest.py`)

Every prior test isolated one component. This runs the whole deployed decision stack
day-by-day for 5 years, strictly causal (overnight range complete at 09:30; the fade
test uses the price AT THE SIGNAL BAR, not the day's close).

**FULL 5 YEARS — the fade-low kill, the one app rule testable over the whole span:**

| arm | trades | win% | net | payout% | bust% |
|---|---|---|---|---|---|
| strategy alone | 940 | 48.1 | $28,157 | 52.7 | 46.4 |
| + app's fade-low KILL | 813 | 48.2 | $25,020 | 50.3 | 48.7 |

**The rule HURTS: −$3,137, −2.3 pts payout, +2.3 pts bust.** It killed 204 long
signals (22% of trades) and win rate was unchanged (48.1 → 48.2), i.e. it removed
trades at random with respect to quality. Better in 4 of 6 years but worse overall.

**Root cause — my own category error, caught by testing a rule I wrote hours earlier.**
The fade evidence says entering long BECAUSE price is cheap fails. I coded it as any
long WHILE price is in the bottom third. `sr_round100_break` is a round-number
BREAKOUT that sometimes triggers when the day happens to be low in its overnight
range — "long WHEN low", not "long BECAUSE low". Different trade; the fade evidence
does not cover it. **Fixed:** `killrules.py` now exempts breakout-kind signals, and
`app.py` passes `signal_kind="breakout"`. Verified: kind=breakout → CLEAR,
kind=fade → KILL, kind unknown → KILL (conservative default).

**CALENDAR WINDOW 2026-02-18..07-15, the FULL stack:**

| decisions applied | trades | net | payout% | bust% |
|---|---|---|---|---|
| nothing | 90 | −$1,154 | 14.7 | 85.3 |
| event gate only | 49 | −$523 | 26.5 | 61.8 |
| fade-low kill only | 77 | −$973 | 14.7 | 61.8 |
| **FULL stack** | 41 | −$59 | **32.4** | **29.4** |

Looks strong, but the window is unrepresentative (strategy net-NEGATIVE in it) and
n=34 account starts. Consistent with the earlier read: the event gate is the only
component with a repeated positive lean, and it is still untestable at scale.

**Net conclusion: the app's decisions did NOT improve the account over 5 years.** One
rule actively hurt until narrowed; the other cannot be tested beyond 5 months. The
app's demonstrated value remains operational (it caught the wrong-strategy briefing,
and that NT had not traded since Aug 5), not predictive.

### 2026-08-10 — GOLD: first real measurements (`gold_research.py`, `gold_folklore.py`)

No gold data was on disk and no Databento key in env, so this used **GC=F hourly from
Yahoo, 13,772 bars, 2024-03..2026-08**. `fetch_gold_databento.py` is written and ready
(GC.v.0, cost-preview mode) for a 1-minute upgrade. Same discipline as MNQ: clean
control (permute session profile + bar), OOS split (fit ..2025-12 / test 2026+),
stop assumed on ambiguity. 16 signals tested. Brackets SL 1.5 / TP 2.0 ATR.

**FOUR SURVIVORS** — positive edge, control beaten ≤2/20, AND positive out-of-sample:

| signal | n | win% | pts/tr | edge | control | OOS n | OOS pts |
|---|---|---|---|---|---|---|---|
| **gd_round50_break_short** | 429 | 46.2 | +3.06 | **+2.70** | **0/20** | 181 | **+7.11** |
| gd_asia_break_short | 214 | 44.4 | +3.60 | +2.69 | 2/20 | 50 | +17.35 |
| gd_london_break_long | 178 | 52.8 | +2.59 | +3.42 | 1/20 | 38 | +6.96 |
| gd_stretch_long | 394 | 49.2 | +0.60 | +2.13 | 1/20 | 96 | +2.97 |

`gd_round50_break_short` is the standout — biggest OOS sample (181), control beaten
0/20. Note `gd_asia_fade_short` had edge +3.10 and control 0/20 but OOS −1.19, and was
correctly excluded — the OOS filter is doing real work.

**STRUCTURAL FINDING: on gold the SHORT breaks work and the LONG breaks do not.**
round25 long −2.57 / short +1.41; round50 long −2.19 / short +3.06; asia long −1.32 /
short +3.60. This is *counter*-drift — gold rose from ~$2,000 to $4,457 over the
sample — which makes it harder to dismiss as an artefact and mirrors the MNQ result
where the short side carried the edge.

**FOLKLORE TESTED AS FILTERS on those four survivors:**

| rule | mean change | helped | verdict |
|---|---|---|---|
| London fix (10-11 ET) is a manipulation window | **+0.08 pts/tr** | 2/4 | **NOT SUPPORTED** |
| Never fight the dollar (DXY alignment) | **+1.11 pts/tr** | 3/4 | **SUPPORTED**, needs OOS |

The DXY result is credible because of the sanity check, not the filter itself: trading
DXY-**OPPOSED** did WORSE on the same three signals by 1.0–3.7 pts/trade. A pure
frequency artefact would show both halves alike. But it costs ~55% of trades and has
had no OOS split of its own, so `killrules.py` now carries it as **UNTESTED (flag)**,
upgraded from ANECDOTAL. The London-fix rule was downgraded to **NOTE** with its
refutation attached.

Rule book now: 3 TESTED / 2 UNTESTED / 6 ANECDOTAL.

**Next on gold:** OOS-split the DXY filter; combine the four survivors into a book and
test at account level; pull Databento GC for 1-minute fills.

### 2026-08-10 — ★ THE FIRST FINDING TO SURVIVE AN OOS SPLIT: cut the per-trade budget

`combined_book.py` set out to test MNQ + gold diversification. It found something
bigger by accident, and the control caught it.

**Gold as a book FAILS at account level** despite four signals with positive per-trade
edge: −$4,951, 11.5% payout, 86% bust. The four survivors overlap in time and compete
for the same 12-hour holds, so combining them takes a worse subset than any of them
alone. MNQ/gold daily P&L correlation is **−0.030** (genuinely uncorrelated, both red
on only 26% of shared days) — the diversification premise was sound, the gold book is
not. Do not trade gold on this evidence.

**But the control exposed the real finding.** "BOTH at $150 each" looked best — until
MNQ-alone-at-$150 reproduced almost all of it. It was never diversification. It was
**position size**.

**BUDGET SWEEP, MNQ pair alone, full 5 years, fit/test split:**

| budget | fit pay% | fit bust% | fit spread | | test pay% | test bust% | test spread |
|---|---|---|---|---|---|---|---|
| $150 | 50.9 | 28.5 | +22.4 | | 45.4 | 0.0 | +45.4 |
| **$175** | **65.5** | **32.0** | **+33.6** | | **58.0** | **0.0** | **+58.0** |
| $200 | 50.7 | 46.8 | +3.9 | | 67.3 | 15.6 | +51.7 |
| $250 | 58.7 | 39.5 | +19.2 | | 55.1 | 41.0 | +14.1 |
| **$300 (current)** | 52.3 | 46.1 | +6.2 | | 56.1 | 41.5 | +14.6 |
| $400 | 44.5 | 55.5 | −11.0 | | 48.8 | 49.3 | −0.5 |

**$175 is the optimum in BOTH halves independently, and it carried over: test spread
+58.0 vs +14.6 for the current $300.** After 19 rejections this is the first candidate
to pass an out-of-sample split.

**MECHANISM — it is not only "smaller size", it is a volatility filter in disguise.**
A 2.0-ATR stop on MNQ costs $107/contract at median ATR but $204 at the 90th
percentile. So the budget sets a *skip threshold*:

| budget | trades skipped (ATR too wide for even 1 contract) |
|---|---|
| $300 | 2.2% |
| **$175** | **16.0%** |
| $150 | 24.2% |

At $175 the widest-ATR 16% of setups are declined outright, and mid-ATR ones size
down. That is why bust collapses while payout holds — it removes precisely the trades
where one loser eats a fifth of the account.

**CORRECTS AN EARLIER CONCLUSION.** This project previously retracted "trade smaller"
on the grounds that sizing down destroys payout odds. That is true at the extreme —
$100 gives 0% payout, 100% stall, it never reaches the threshold — but false in the
middle. There is a sweet spot and $300 is on the wrong side of it.

**Cost: time.** Median days to payout goes 13 → 48 at $175. The 180-day horizon
absorbs it, but if LucidPro charges a monthly fee that is a real expense to weigh.

**ACTION: change `RISK_BUDGET_USD` from 300 to 175** in the app and in any NinjaScript
port. Single highest-value change found in this session.

### 2026-08-10 — NEW GROUND: the Globex session (`overnight_hunt.py`, `new_book.py`)

Every prior measurement lived in RTH 09:45-11:00 — ~15 bars a day out of 288. The
overnight session was already in `mnq_2021-2026_5min.csv` (the RTH filter discards 58%
of the file) and had never been looked at. 22 signals x 4 sessions, clean control, OOS
split at 2025-01.

**★ BEST SIGNAL FOUND ANYWHERE IN THIS PROJECT:**

`ASIA|round100_long` — round-100 break long, 18:00-03:00 ET
- edge **+3.95** pts/trade, n=1237, control beaten **0/20**
- **OOS +8.52 on 560 trades** (vs the incumbent long's +4.56 in-sample)
- LIQUIDITY CHECKED: fires on median **2,480 contracts/bar** vs the Asia session's own
  861 baseline — 3x session volume, not dead tape
- tolerates **16 ticks** of round-trip slippage before the edge dies (MNQ is 1 tick wide)

Other survivors: `RTH|overnight_hi_break` (+2.24, n=2961, OOS +3.03 — breaking the ONH
during RTH, a signal we never had), `RTH|stretch_long` (+2.36, OOS +3.51),
`RTH|stretch_short` (+2.23, OOS +3.96).

**Strong session effect:** ASIA round-100 longs +4.93 ppt; the SAME signal in LONDON
−1.69 and PRE-NY −2.81. London and pre-NY are dead ground on every shape tested.

**BUT: good signals ≠ good book (again).** The 4-signal new book at $175 gave 27.3%
sub-month payout but **61.6% bust** and only 37.4% total paid — worse than the
incumbent on both. Same failure as gold: overlapping signals, clustered daily losses.

**The surgical version works.** Incumbent pair + `ASIA|round100_long` ONLY:

| config | sub-month | total paid | bust | med days |
|---|---|---|---|---|
| incumbent alone @$175 | 9.8% | **65.0%** | **21.8%** | 47 |
| **incumbent + ASIA @$175** | **22.9%** | 63.4% | 36.0% | **26** |
| incumbent alone @$350 | **42.8%** | 50.1% | 49.8% | ~13 |
| 4-signal new book @$175 | 27.3% | 37.4% | 61.6% | 13 |

Adding just the one signal **more than doubles sub-month payout (9.8 -> 22.9%) while
keeping total payout intact (65.0 -> 63.4%)** and halving median days (47 -> 26). Bust
rises 21.8 -> 36.0%.

**For pure speed the answer is still incumbent @$350 (42.8%)** — adding Asia at $350
gives only 32.7% and busts 58.6%, i.e. worse on both.

**NOT YET VALIDATED:** the signal passed control + OOS + liquidity, but the BOOK
(incumbent + Asia at account level) has not had its own OOS split. That is the next
test and it is exactly what killed the 10Y filter and the 1-min hybrid.

**OPERATIONAL:** Asia trades run 18:00-03:00 ET. NinjaTrader must be up overnight, and
LucidPro's overnight-holding rules need checking before this is usable.

### 2026-08-10 — LucidPro rules VERIFIED against the firm's published terms

User confirmed the $1,000 MLL; the rest was looked up. Until now every account number
in this project rested on hardcoded constants with no documented source.

**CONFIRMED CORRECT:**
- MLL **$1,000** on the 25K (user + multiple sources)
- **End-of-day** trailing, not intraday — "only updates at market close (4:45 PM EST)".
  My sim already did EOD, and a direct test showed intraday vs EOD checking changes
  bust by only **0.2 pts**, so it was never load-bearing anyway.
- Floor **locks permanently at initial balance + $100 = $25,100** once trailed out.
  My constant was right.
- Payout buffer = **max drawdown + $100 = $1,100** → threshold **$26,100**. Correct.
- **No daily loss limit** on the 25K (the 50K/100K/150K have one). Correct.

**FOUND WRONG — `MIN_DAYS` was 3, the real rule is 5 PROFITABLE days.** My sim also
counted any day with a trade rather than green days only. Fixed in `funded_search.py`.
Impact is small because $1,100 of profit already needs 5+ green days at this win rate:

| budget | sub-month | total paid | bust |
|---|---|---|---|
| $350, old (3 trading days) | 42.8% | 50.1% | 49.8% |
| $350, real (5 profitable days) | **40.9%** | **48.8%** | **50.9%** |

**⚠ ONE UNRESOLVED CONFLICT — and it is the most dangerous number left.** The official
Lucid FAQ lists consistency at **≤40%**; one third-party source claims **20%** for
LucidPro. It is not a rounding difference:

| budget | consistency | sub-month | total paid | bust |
|---|---|---|---|---|
| $350 | 40% | 40.9% | 48.8% | 50.9% |
| $350 | **20%** | **7.3%** | **33.1%** | **66.3%** |
| $175 | 40% | 9.8% | 65.0% | 21.8% |
| $175 | 20% | 5.1% | 61.3% | 24.4% |

**At 20% consistency the entire fast-payout route collapses — 40.9% → 7.3%.** Because
a big single day is exactly how you get to $1,100 quickly, and a 20% cap forbids it.
The $175 route barely moves (9.8 → 5.1), so it is far more robust to this being wrong.

**ACTION: confirm the consistency percentage in the LucidPro dashboard before sizing
up.** If it is 20%, sizing up is actively counterproductive and $175 is the only
sensible route.
