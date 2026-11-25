# Trading-system journal

Lettered entries `(k)…(u)` = milestones/keepers; `a13…` = numbered experiments.
Earlier entries `(k)(m)(q)(t)`, `a13/a14/a17` are referenced inline in the code
(power-hour era) but predate this file.

---

## (u) — 2026-06-30 — Power-hour retired; new champion candidate: KeyRev @ BB band

### Why power-hour was dropped
- Live record: the bot executed only **2 real trades ever**, both losses (−$853.80 on the
  old eval under fixed 5-lot sizing → the "a14 blowup"; −$228 on 2026-06-29 on practice).
- Reconstructed every rejected/paper signal in the live window: **0-for-11 — every
  power-hour signal hit its stop** (choppy regime; momentum-chase got faded).
- The big account losses were **manual ENQ scalping** (e.g. −$2.1k on 2026-06-26),
  NOT the bot — important: the strategy was barely tested, the *manual* trading lost the money.
- Backtests still ranked power-hour #1, but live + recent data didn't support it. Retired.

### Account / execution notes
- Trading the **PRACTICE** account `XXXX` (PRAC-V2-112211-37100419) until told otherwise
  (set in start-bot.bat env). Eval = `24717879`.
- Order rejection `errorCode=2 "Brackets cannot be used with Position Brackets"` is an
  **account setting**, not a code bug: the eval needs **Auto OCO Brackets** enabled
  (Settings→Risk, while flat). Practice account accepts brackets fine.
- Live bot's P&L logging was unreliable (logged −$30 vs broker's real −$228) — exits
  assumed bar-close when the OCO stop actually filled worse. Use broker trade history as truth.

### Strategy search (tooling: strat-gen.js, run90.js, optimize-strat.js)
- Generated **150 strategies** (50 entry edges × 3 RR exits), backtested on 13d MNQ + 58d NQ.
- Raw edges (FVG, pin, ADX momentum) make money on big samples but **blow the $2k Combine
  drawdown wall** at 5 MNQ (DD $7k–$17k) and win only ~22% — confirmed again on TopStep's
  recent 13 days (all 10 raw top configs busted the wall).
- **Risk control is the fix**, not the entry: vol-based sizing w/ per-trade $ risk cap +
  daily-loss stop + max-trades/day brought drawdowns to ~$1.3–1.6k (feasible).

### The FVG detour
- Optimized **FVG retest + ADX>20, s1.5/t3.5, $200 cap, 3/day, −$500 daily stop** →
  +$5.2k/89d net of costs, ~42% win, PF 1.55, DD ~$1.4k, feasible on all 3 samples.
- Deployed to **paper** (`live-fvg.js`, no orders) on practice — running.
- BUT on TopStep's recent 13 days it was **breakeven (−$156)** — the high-RR/low-win profile
  needs rare big winners that didn't show up. Prompted method tweaking.

### CHAMPION CANDIDATE — KeyRev @ Bollinger band (tooling: tweak-methods.js, optimize-keyrev.js)
Method: a **key-reversal bar** (new 5-bar extreme that reverses) **at a Bollinger band**;
best variant adds **"close back inside the band"** (wick pierces band, closes back in =
a genuine sweep-and-reclaim — mechanizes the QuantRepublic [WICK] idea).

**Selected config:** stop **1.5×ATR** / target **2.0×ATR** / **$200** risk cap (≤5 MNQ
vol-sized) / **2 trades/day** / **−$500** daily stop. All figures **net of fee+2-tick slippage**:

| Sample | Net | Win% | PF | Max DD |
|--------|----:|----:|---:|------:|
| 90d MNQ | +$4,776 | 54.5% | 1.52 | −$1,604 |
| 58d NQ (OOS) | +$2,001 | — | — | feasible |
| 13d cached | +$857 | — | — | — |
| recent-13d TopStep | +$1,754 | 58.3% | — | — |

- **Passes the chronological $50K Combine** (reaches +$3,000 before −$2,000 trailing DD / −$1,000 day).
- **Monte-Carlo (10k trade-order shuffles): 99% pass** — robust to luck, not one good sequence.
- Net-positive on **all four** independent samples after costs, and a **cluster** of ~148
  related configs also pass — strong anti-overfit signal.
- Beats FVG: higher win rate (54% vs 42%) and profitable on recent data where FVG was flat.

### Status / next
- FVG paper bot running on practice (live-fvg.js). Keep-alive: FVG-Paper-Heal task (15-min,
  hidden via wscript). Old NQ-EnsureBotRunning (relaunched the ARMED power-hour bot) DISABLED.
- **TODO:** deploy KeyRev @ BB band to paper (alongside FVG for a head-to-head forward test),
  then judge on real forward results before ever arming small.
- Reports: logs/strat150-report.md, optimize-strat-report.md, top10-90d-report.md,
  keyrev-optimized-report.md.

---

## (v) — 2026-06-30 — POST-MORTEM: every past config/strategy was a failure. Why.

Blunt truth for the record: **none of the strategies/configs built before the KeyRev@BB
candidate worked as a tradable, eval-passing system.** They were either unprofitable live,
un-survivable (blew the drawdown wall), overfit, or never actually executed. Listing them and
the real reasons, from the evidence:

### What was tried, and how each ended
- **simple_strategy v1–v5** (manual decision-support) — kept iterating: v2 added filters,
  v3 fixed "post-peak bleed," v4/v5 *chased frequency* (~1 trade/week → "5/week"). Abandoned.
- **ORB v1–v5** (opening-range breakout) — momentum/breakout archetype, "strong breaks only" by v5. Superseded.
- **meanrev_v1** — mean-reversion archetype. Superseded by the lab catalog.
- **lab 50 + catalog13 (123 methods)** — screen showed almost all **bust the Combine DLL/MLL walls**.
- **Power-hour + ADX (the "champion", journal (k)(m)(q)(t))** — backtested #1 of 210, then
  **0-for-11 live** (every signal stopped). The one big live loss under it (−$853) was the **a14
  fixed-5-lot blowup**.
- **Lunch bot (journal (xx))** — engineered candidate; lost (e.g. −$420). Abandoned.
- **150-strategy raw search** — all blew the $2k wall (≈22% win, $7k–$17k drawdowns).
- **FVG optimized** — feasible, but **breakeven on fresh TopStep data** (high-RR profile starved of big winners).

### ROOT CAUSES (the actual "why")
1. **No real risk control / position sizing — the #1 killer.** Early systems used fixed 5-lot
   sizing with ATR stops, so a wide-stop day risked **$850+ on a single trade** → blew the eval
   (a14). Raw strategies had no daily-loss stop and no trade cap → $7k–$17k drawdowns, far past
   the $2k Combine wall. **Profit was never the problem; survivability was.** Only fixed once
   vol-based sizing ($ risk cap) + daily-loss stop + max-trades/day were added.
2. **Backtest overfitting on tiny, in-sample, gross numbers.** Power-hour ranked #1 then went
   0-for-11 live; 13-day windows showed +$4k that turned to breakeven on fresh data. Picks were
   made on small samples with no out-of-sample / cost / Monte-Carlo discipline (added only now).
3. **Selection metric ignored feasibility.** Strategies were ranked by total net points/$, not by
   *Combine-feasibility* (DD<$2k, day<$1k) — so "winners" were chosen that mathematically could
   not pass the eval.
4. **Wrong edge type for the regime (momentum-in-chop).** ORB and power-hour chase breakouts; in
   the choppy regime they bought tops / sold bottoms and got faded. The edges that actually hold
   up are **reversal/mean-revert at stretched levels** (KeyRev@BB, RSI2, BB tag).
5. **Frequency-chasing degraded edge.** simple v4/v5 forced "more trades/week" for TopStep
   activity rules — extra low-quality trades added noise and drawdown, not profit.
6. **Execution/config breakage.** The Auto-OCO-Brackets account setting rejected every live order
   for days (the bot literally couldn't trade), and P&L logging was unreliable (−$30 logged vs
   −$228 real) — so even results that did happen were mis-measured.
7. **Manual losses blamed on the systems.** The largest real-money damage was **manual ENQ
   discretionary scalping** (−$2.1k on 2026-06-26), not the bots — but it dominated the account
   curve and the felt sense that "everything fails."

### The fix (already applied to the KeyRev candidate)
Risk control first (vol sizing + $ cap + daily stop + trade cap) → feasibility as a hard gate →
out-of-sample + cost + chronological-Combine + Monte-Carlo validation → reversal-at-level edge,
not momentum-chase. That combination is why KeyRev@BB passes where everything before failed.

---

## (w) — 2026-06-30 — CHOSEN METHOD: Engulfing Bar @ Bollinger Band

Continued the reversal-at-level search past KeyRev (strat-gen3…9, best-strategy.js) and landed on a
stronger, simpler edge. **This is now the method I'm running** (user confirmed "best method so far").
It supersedes both the KeyRev@BB candidate (u) and the FVG paper bot as the forward-test strategy.

### The edge — body-engulfing bar at the Bollinger band (`best-strategy.js`, `live-engulfing.js`)
A bar whose **body fully engulfs** the prior bar's body, printed **at a BB(20,2) extreme**, that
**closes back inside** the band — a mechanical sweep-and-reclaim with confirmed opposing pressure.
- LONG: prior bar red, current green, current body ⊇ prior body, body ≥ 0.4·ATR, low ≤ lowerBB+0.3·ATR,
  close > lowerBB. SHORT = exact mirror at the upper band.
- **Config:** stop **1.0×ATR(14)** / target **3.0×ATR** (3:1 R/R) / **$400** risk cap (size =
  floor($400/(stop_pts·$2)), ≤5 MNQ) / **max 3 trades/day** / **−$700** daily stop /
  **10:00am–3:30pm ET** only (skip the open-auction noise). Costs: $0.37/side + 2-tick slippage each way.

### Backtest (50 RTH days, Apr 9 – Jun 18 2026, net of costs) — beats prior K8 champion
| Metric | Engulf@BB | K8 (prior) |
|--------|----------:|-----------:|
| Net | **+$12,307** | +$9,300 |
| Max DD | **−$1,524** (under the $2k wall) | −$1,887 |
| Win% | 43.8% | — |
| PF | 1.80 | — |
| Combine pass | 6 trading days | 9 days |
| Monte-Carlo | **87.5%** of orderings still pass | — |

3:1 R/R keeps it profitable even at ~36% win; 62% of passing MC runs hit target in ≤13 days.

### Account-default bug — FIXED (was the live-engulfing.js account mismatch)
`live-engulfing.js` defaulted `ACCOUNT_ID` to **24717879** (the **EVAL** account) while every banner/
string said "Practice", and `start-engulfing-armed.bat` likewise printed "Practice" but (setting no
env) would have **armed real bracket orders on the eval account** — which is exactly the account with
the Auto-OCO-Brackets rejection issue (see (u) / [[trading-bot-bracket-rejection]]). Fixes applied:
- `live-engulfing.js` default → **XXXX** (practice); header comment corrected.
- `start-engulfing-armed.bat` + `start-engulfing-paper.bat` now `set PROJECTX_ACCOUNT_ID=XXXX`.
- No `START_BALANCE` needed here (engulf bot has no balance-based EVAL-PASSED alert, unlike live-signal.js).
- NOTE: env is read once at node launch — an already-running armed engulf bot must be **restarted**
  to pick this up. `.disarm` file halts order placement without killing the process.

### Status / next — SINGLE HARDENED BOT (2026-06-30)
- Engulf@BB is **the only bot**, ARMED on practice XXXX, running hidden, with full keep-alive.
- **Single-instance lock** added to `live-engulfing.js`: `.engulf-lock` (pid) + `.engulf-heartbeat`
  (written every poll). On startup `anotherInstanceRunning()` exits if a live lock-holder has a fresh
  (<3 min) heartbeat; stale lock (dead pid OR stale heartbeat) is taken over — survives reboots.
  **Tested:** a 2nd copy prints "already running — exiting" and quits. This makes duplicate orders
  impossible and **neutralizes the still-enabled `EngulfBB-AutoTrade` task** (admin needed to disable
  it, but any copy it spawns now self-exits, so it's harmless).
- **Keep-alive (mirrors the FVG pattern):** task **`Engulf-Heal`** (`schtasks /sc minute /mo 15`,
  interactive, no admin needed) → `ensure-engulfing-hidden.vbs` → hidden `ensure-engulfing.ps1` →
  relaunches via `run-engulfing-hidden.vbs` (→ `start-engulfing-armed.bat`, hidden) if no
  live-engulfing node proc is found. **Tested:** killed the bot, heal relaunched it. After a
  reboot+login or crash it returns within ≤15 min. (No at-logon task — that needs admin; 15-min heal
  covers it.)
- FVG paper bot (`live-fvg.js`) stopped + `FVG-Paper-Heal` disabled earlier today so only this bot
  posts to Discord (both share the `notify.js` webhook); every signal now = a real (sim) order.
- New files: `run-engulfing-hidden.vbs`, `ensure-engulfing.ps1`, `ensure-engulfing-hidden.vbs`.
- **Forward-test scorecard:** `live-report.js` (run via `run-report.bat`) reads `logs/live-engulfing.jsonl`
  and scores real armed trades vs the backtest (win 43.8% / PF 1.80) + chronological Combine
  feasibility (progress to +$3,000, max DD vs −$2,000, worst day vs −$1,000); writes
  `logs/forward-test-report.md`. Judge the strategy on this sample (~30+ trades), not trade-by-trade.
- **First live trade (2026-06-30):** LONG 30543.50 @ 14:15 ET (bullish engulf at lower BB), stopped
  −$265 at 15:55 ET. Bounced ~+50pt to 30593 (≈70% to the 3×ATR target) then faded; a late vol spike
  clipped the 1×ATR stop 5 min before the 4:00pm flatten. A normal loss for a 44%-win / 3:1-R system.
- **Partial scale-out TESTED (`test-partial.js`) and DEPLOYED (user chose it 2026-07-01):** best
  variant = **40% off at +1.5×ATR, runner→breakeven, target still 3×ATR**. vs fixed baseline it nets
  LESS ($8,702 vs $12,307) but win% 44→53, max DD $1,524→$1,016, MC 86→89% — chosen for the Combine
  phase because the constraint is the −$2k wall, not max profit (both clear +$3k; scale-out leaves ~2×
  the drawdown cushion). Impl: `projectx-orders.js` gained `placeMarket` (plain reducing order) +
  `cancelWorkingOrders`. `live-engulfing.js` position mgmt is now a 2-phase state machine: PRE-scale
  keeps the existing server OCO (identical behavior for trades that never reach +1.5R); at +1.5R it
  `placeMarket`s the partial, cancels the stale full-size OCO, banks it (`realized`), moves runner
  stop→BE; POST-scale the bot manages the runner locally (BE/target/EOD via flatten). Fail-safe: a
  failed partial order = no-op retry (OCO still protects); state fields scaled/rem/realized persist so
  the 15-min heal resumes a runner after a restart. Config: `SCALE_FRAC/SCALE_R/MOVE_BE`. New env
  overrides `ENGULF_STATE_FILE`/`ENGULF_HEARTBEAT_FILE` (for scratch-state testing). **Verified:**
  finish() P&L math exact (full +$554, runner combine +$475) via dry-run --once on scratch state.
  **Residual risk:** after scaling, the runner has no *server* stop (managed by the bot); if the bot
  dies mid-runner it's naked until the ≤15-min heal restart (state resumes it). Acceptable on sim.
  First real scale-out will be during RTH; watch it and reconcile the recorded fill vs backtest.
- **REVERTED to fixed exit 2026-07-01 (user chose speed over smoothness).** Added `SCALE_ENABLED=false`
  toggle gating both scale triggers; with it off the bot stays in the pre-scale phase (server OCO,
  1×ATR stop / 3×ATR target) = identical to the original fixed behavior. Scale-out code kept intact,
  flip the flag to re-enable. Reason: fixed is faster to +$3k (MC median 11d vs 16d, 63% vs 35% pass
  ≤13d) and the user prioritized a fast pass. Trade-off accepted: fixed loses 56% of trades (bigger
  give-backs) vs scale-out's 47%. Commitment noted: leave the exit alone for ~20–30 trades.
- **Trailing/breakeven stops TESTED and REJECTED (`test-trailing.js`, data/nq-5m.json, same entries):**
  prompted by that give-back. Every variant makes LESS net than the fixed 1×ATR/3×ATR baseline
  ($12,307, PF 2.06, DD $1,524): breakeven@+1R → $10,204 **and DD $2,253 = breaks the $2k wall**;
  trail 2ATR → $10,293 **DD $2,258 breaks wall**; trail 1.5ATR → $9,445 (feasible, Combine 10d);
  trail 1ATR → $5,865 (win% jumps to 57 but net HALVED). Reason: the profit lives in the few trades
  that run the full 3R; trailing cuts them on normal pullbacks — higher win%, much lower $. **Kept the
  fixed exit; live bot unchanged.** Next idea to test if pursued: partial scale-out (some off at
  +1.5R, runner to 3R w/ stop→BE) — the only "protect the green" method that keeps the big winners.
- **Time-gate bug FIXED (important — live now matches the backtest):** `live-engulfing.js` had
  collapsed both gates into one wrong constant `TIME_CUT=935` (3:35pm), used for *both* the entry
  cutoff and the EOD flatten. The `best-strategy.js` backtest uses TWO times — entries `600..930`
  (10:00am–3:30pm) and flatten at `!inRTH` = `RTH_E=960` (4:00pm). So live was entering 5 min late
  AND force-flattening 25 min early (3:35 vs 4:00), cutting the high-R/R winners short. Split into
  `ENTRY_CUT=930` (entries) + `RTH_E=960` (flatten); fixed the bogus "3:55pm" log label. ET/DST calc
  in `toET()` was verified correct (EDT/UTC-4 for the DST window; 2nd-Sun-Mar … 1st-Sun-Nov).
- **STALE-FEED / off-by-one bug FIXED (this is why 0 orders fired all morning):** `projectx.js`
  `fetchBars` is called with `includePartialBar:false`, so every returned bar is already CLOSED —
  but the bot did `const closed=bars.slice(0,-1)`, discarding the **freshest** completed bar. That
  added ~5 min of artificial lag on top of API finalization, pushing bar age to ~654s — past the
  `MAX_BAR_AGE=600` guard — so the armed bot logged "STALE FEED — skip" every poll and **never
  scanned**. It even **missed a real SHORT signal at 10:05 ET** (engulf at upper BB, closed back
  inside) because that bar was already stale by the time it surfaced. Fix: `const closed=bars`
  (no slice) + `MAX_BAR_AGE 600→900` (freshest closed bar is naturally 300–660s old with bar-open
  timestamps; 600 false-trips around each new bar). **Verified:** probe shows the bot now evaluates
  the latest bar at ~339s = FRESH and scans. NOTE: the same `slice(0,-1)` pattern is likely in
  `live-fvg.js`/other live bots — fix there too if reused. Practice-acct data is ~real-time (~1 min
  post-close), not significantly delayed.
- Minor cosmetic: the post-cutoff console string in `live-engulfing.js` says "After 3:55pm" while the
  actual `TIME_CUT` is 3:35pm (935 min); banner says 3:30. Behavior is the 3:35 cutoff — log text only.
- Reports/tooling: best-strategy.js (spec+backtest), strat-gen3…9-13d, run-topstep13.js.
