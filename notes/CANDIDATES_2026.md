# Strategy candidates - LucidDaily 50K eval (EOD trail $2,000, DLL $1,200, target $3,000)
Tested on 2026 only: tuned Jan-Apr 2026, checked May-Aug 2026 (unseen). Updated 2026-09-28.

## From strat300.py (round 3) - held up in BOTH 2026 halves with 0% bust
| Strategy | Risk/trade | Jan-Apr pass/bust | May-Aug pass/bust |
|---|---|---|---|
| Al Brooks H2/L2, both ways, stop 2.0x ATR, target 1.5R | $400 | 46% / 0% | 59% / 0% |
| 5-min ORB, SHORT only, stop 0.75x ATR, target 2R | ramp $200->$400 | 62% / 0% | 17% / 0% |
| FVG retest, LONG only, stop 1.25x ATR, target 2R | $300 | 4% / 0% | 21% / 0% |

Caveat: ~470 strategies were tried to find these three; forward-test before trusting.

## From strat500.py (round 4) - pass>=20% and bust<=10% in BOTH 2026 halves
- three_bar_rev|both|none|time60_2R (risk ramp): Jan-Apr 21%/0%, May-Aug 21%/0%, R/trade +0.18/+0.23

## From C:\trading_system (ts_backtest.py, 2026-09-28) - BEST SO FAR
- ema_pullback [1/0.5 adxgt25], both ways, 3 MNQ fixed (their good_strategies.csv #1, their signal code):
  EMA21>EMA50 and rising, low touches EMA21, close back above (mirror short); ADX>=25; stop 1.0 ATR, target 0.5 ATR;
  entries 09:40-15:30, one position at a time, flat at close.
  2026 net +$6,624 (320 trades, 72.5% win, PF 1.3, worst day -$1,148, maxDD -$1,594).
  LucidDaily eval: 79% pass / 0% bust; starts in months their selection never saw: 84% pass / 0% bust (median 62 days).
  Holds at 2x slippage (72% / 3% at 3 MNQ). 4 MNQ = 91% / 1% at normal cost but 22% bust at 2x slippage -> stay at 3.
  Weak spot: lost money in Jan and Feb 2026. Edge per trade is thin (~$12 in unseen months).
- Claude 2 (StochReclaim %K cross 30, 0.75/0.5 ATR) LIVE EVAL MODE: 2026 net -$1,763, eval 40% pass / 60% bust.
  Its 100% pass claim came from Jun 8 - Jul 8 2026 only; June was its best month of the year. Do not run it.

## Mix test (mix_lab.py, 2026-09-29) - news-legal window Feb 18 - Jul 15 2026
- LucidDaily news rule (flat T-2 min, no entries T-15..T+2) barely hurts EMA pullback: 206 vs 210 trades, +3.8 vs +4.1 pts/trade.
- BEST MIX (no tuning): EMA pullback @3 MNQ + post-news FADE @3 MNQ (T+5, stop 1x release-bar range, 50% retrace target, 60 min):
  Feb-Apr 17% pass / 0% bust (base alone 0% / 0%), May-Jul 59% / 0% (base alone 27% / 0%). ~2.7 trades/day.
- Greedy optimiser picked EMA + two long VWAP-reversion configs: 100% / 0% Feb-Apr -> 41% / 57% bust May-Jul. OVERFIT - do not use.
- mix_lab2.py: size ramp "EMA 3 -> 4 MNQ once eval profit >= $1,000, news fade stays 3" improves BOTH halves:
  Feb-Apr 17% -> 39% pass, May-Jul 59% -> 63% pass, still 0% bust. Starting smaller (2/2) or cutting size after
  losses made it worse. Strict partner screening (positive in all 3 Feb-Apr slices, low correlation) still failed:
  only 9 of 40 stayed positive in May-Jul and every partner added LOWERED May-Jul pass rate. CURRENT PLAN:
  EMA pullback (news-legal) 3 MNQ, ramp to 4 at +$1,000 + post-news fade 3 MNQ.

## bottom_lab.py (2026-09-29) - buy-the-bottom / sell-the-top methods as partners (news-legal, Feb 18 - Jul 15)
- No method buys near the real low: median entry 2.3-4.3 ATR from the day's actual low; only 0-8% of entries within 0.5 ATR.
- 126 variants; only 7 positive in both halves; corr(Feb-Apr, May-Jul) -0.20. Short-side tops were worse than longs.
- ONE partner improved the plan in both halves AND was the #1 pick on Feb-Apr: VWAP 3-sigma band reclaim, LONG only
  (low pierces VWAP - 3 sigma, bar closes back above), stop below the signal-bar low (max 2 ATR), target 2R.
  Plan + this @1 MNQ: Feb-Apr 39% -> 70% pass, May-Jul 63% -> 69% pass, 0% bust both. @2 MNQ: May-Jul 82% / 0%.
  Standalone edge is thin in May-Jul (+2.4 pts/trade). Neighbours (2.5 sigma, VWAP-target exit) also helped -> family-level signal.

## asia_test2.py (2026-09-29) - overnight sessions: DO NOT TRADE THE PLAN OUTSIDE RTH
| strategy | session | trades/day | win% | pts/trade | Jan-Apr | May-Aug | 2026 @3 MNQ | months positive |
| EMA pullback | RTH | 2.10 | 72.6 | +3.49 | +1.14 | +5.92 | +$6,811 | 6/8 |
| EMA pullback | ASIA 19:00-02:00 | 2.82 | 64.8 | -2.40 | -1.86 | -3.02 | -$6,337 | 1/8 |
| EMA pullback | LONDON 02:40-07:30 | 2.53 | 62.7 | -2.30 | -2.48 | -2.09 | -$5,446 | 0/8 |
| VWAP 3sd long | RTH | 0.82 | 33.9 | +5.60 | +8.42 | +1.79 | +$4,269 | 6/8 |
| VWAP 3sd long | ASIA | 0.38 | 20.3 | -12.58 | | | -$4,452 | 2/8 |
CRITICAL: the EMA pullback edge needs indicators computed from RTH bars only. Same rules on a 24h series: -1.6 pts/trade.
EmaPullbackSim.cs now refuses to trade unless the chart uses an RTH trading-hours template.

## Night add-on test (asia_lab.py + merge_night.py, 2026-09-29)
- Best overnight strategy: LONG drift 18:05 -> 08:25 ET. Clean 2026 (2 contract-roll nights removed, they were +557 of +3,136 pts):
  +2,579 pts/contract, 54% win, worst night -403 pts. Jan-Apr vs May-Aug ranking corr +0.60 (only structural effect found).
  BUT it is market beta: NQ 2022 lost -3,268 pts outside the day session. Added to the day plan at 1 MNQ: May-Jul bust 35%;
  at 2-3 MNQ: 33-63% bust. TOO VOLATILE for the $2,000 trailing drawdown. Do not add.
- London breakout of the Asia range (02:00-05:00, both ways, 2/2 ATR) @2 MNQ: Feb-Apr 70% -> 61% pass, May-Jul 69% -> 71%,
  0% bust both -> neutral, not worth the complexity. All mean-reversion / EMA pullback variants at night lost money.
- NOTE: MNQ.v.0 continuous data has roll jumps (~Mar 18, Jun 16 2026, 7-8 pm ET). Exclude roll nights in any overnight test.

## Size optimisation (size_opt.py + size_boot.py, 2026-09-29) - NEW RECOMMENDED SIZES
1,600 size combos on the real path all look 0% bust at high size (window too short to tell), so sizes were judged on a
2,000-path block bootstrap of Feb 18 - Jul 15 2026 daily P&L, eval + 60 funded days (intraday-trail proxy):
| sizes EMA(step)/fade/VWAP3/London | eval pass | eval bust | median days | funded bust 60d | avg withdrawable 60d |
| current 3(+1@$1k)/3/1/0            | 94% | 5%  | 28 | 21% | $3.7k |
| MID 4(+1@$1.5k)/3/2/2  <- PICK     | 99% | 1%  | 18 | 4%  | $7.6k |
| 4(+1@$1.5k)/4/2/3                  | 98% | 2%  | 16 | 5%  | $9.0k |
| 5(+1@$1.5k)/4/3/3                  | 97% | 3%  | 13 | 23% | $11.5k |
| 5(+2@$1.5k)/5/3/4                  | 96% | 4%  | 12 | 24% | $13.0k |
| EMA only 5                         | 72% | 27% | 24 | 46% | $4.3k |
Double slippage MID: 97% / 2% eval, 7% funded bust. Bootstrap re-uses 2026 days, so it inherits 2026's regime.
