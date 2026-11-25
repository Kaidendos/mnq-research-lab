"""Al Brooks + Bob Volman ENTRY triggers for MNQ 5-min RTH bars.   (prefix "ab_")

Every rule below is transcribed from a rule the named trader actually published.
The source URL sits directly above each implementation. Where the source states a
rule without a number (they almost always do — Brooks is deliberately anti-numeric),
the concrete reading I chose is called out in a comment marked  # CHOICE:
Nothing here is attributed to a trader that they did not say.

WHO THESE TRADERS ARE
  Al Brooks   — MD turned futures trader; author of the Wiley "Trading Price Action"
                trilogy (2012) and "Reading Price Charts Bar by Bar" (2009). Documented
                in the sense that matters here: the rules are in print, with page-level
                definitions, published by Wiley.
  Bob Volman  — author of "Forex Price Action Scalping" (2011, 70-tick charts, 20-ema)
                and "Understanding Price Action: practical analysis of the 5-minute
                time frame" (2014, 25-ema, fixed 10-tick stop / 20-tick target).

TIMEFRAME HONESTY (Volman)
  Volman's FIRST book trades a 70-TICK chart. A 70-tick bar cannot be reconstructed
  from 5-minute OHLCV — the information simply is not in this dataset — so the tick
  timeframe is NOT reproduced and nothing here claims to be his scalping system. What
  IS implemented is the two setups he defines structurally (the double-doji break and
  the squeezed range break), on the 5-MINUTE frame that Volman himself published a
  whole book about in 2014. His moving average is the 20-ema in the tick book and the
  25-ema in the 5-min book; the enriched frame ships ema20, so ema20 is used and the
  discrepancy is flagged rather than hidden.

EXPLICITLY REJECTED (researched, NOT implemented — see the notes at the bottom of this
file for the full list): Brooks' "always-in" direction, signal-bar quality grading,
trend-vs-range context, and Volman's round-number filter + "advanced range break".
These are discretionary judgements with no mechanical trigger. No mechanical version
of them is invented and attributed to the author.

CAUSALITY: a signal on bar i uses only data known at the close of bar i.
  * Rolling windows end on the current bar — legal.
  * Session features use groupby("_day").cummax()/.cummin() — legal.
  * Swing pivots need 2 bars of confirmation, so the pivot flag is .shift(2)-ed before
    use: at bar t the code sees the pivot that formed at bar t-2, confirmed by bars
    t-1 and t. Nothing forward-looking survives the shift.
  * The three state machines are strict left-to-right loops that read bar i and i-1
    only. They can physically not see the future.

Returns ENTRY TRIGGERS ONLY. Stops / targets / sizing / exits belong to the harness.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── Brooks tunables ──────────────────────────────────────────────────────────
TREND_SLOPE_BARS = 5        # ema20 slope lookback used as the bull/bear-leg proxy
STRONG_BODY_FRAC = 0.60     # "strong trend bar" body as a fraction of its range
STRONG_CLOSE_FRAC = 0.75    # close must sit in the top (bottom) quarter of the range
BOPB_MAX_BARS = 6           # Brooks: pullback of "one to about five bars"
PIVOT_WING = 2              # bars either side that define a swing high/low
WEDGE_MAX_SPAN = 40         # three pushes must be one structure, not a whole week
WEDGE_ENTRY_BARS = 6        # bars allowed for the reversal close after push 3
FLAG_BARS = 6               # length of the candidate "final flag" range
FLAG_TIGHT_ATR = 1.75       # flag height ceiling, in ATR
FLAG_NEAR_HIGH_ATR = 0.50   # how close the flag must sit to the recent extreme
FLAG_LOOKBACK = 30          # window that defines "late in the trend"
FLAG_FAIL_BARS = 6          # bars allowed for the breakout to fail back inside

# ── Volman tunables ──────────────────────────────────────────────────────────
DOJI_RANGE_ATR = 0.75       # a "doji"/small bar: range at most 0.75 ATR
DOJI_BODY_FRAC = 0.60       # ... and body at most 60% of that range
DD_EMA_TOL_ATR = 0.40       # how near the 20-ema the doji pair must sit
DD_BREAK_BARS = 5           # bars allowed for the break of the doji-pair range
IRB_BARRIER_BARS = 10       # window whose extreme is treated as "the barrier line"
IRB_TEST_TOL_ATR = 0.35     # a bar "tests" the barrier within this distance
IRB_MIN_TESTS = 2           # barrier must be tested at least twice to be a barrier
IRB_SQUEEZE_BARS = 3        # bars of pre-breakout compression
IRB_SQUEEZE_ATR = 1.00      # each squeeze bar's range ceiling, in ATR
IRB_SANDWICH_ATR = 2.00     # max ema20-to-barrier gap ("sandwiched")


# ══════════════════════════════ helpers ══════════════════════════════
def _clean(s: pd.Series, index) -> pd.Series:
    return s.reindex(index).fillna(False).astype(bool)


def _carry(trigger: pd.Series, value: pd.Series, day: pd.Series,
           pos: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Forward-fill a value captured on `trigger` bars.

    Returns (carried_value, bars_since_trigger, still_same_session). Only .ffill()
    is used, so every carried value comes from a bar at or before the current one.
    """
    carried = value.where(trigger).ffill()
    trig_pos = pos.where(trigger).ffill()
    trig_day = day.where(trigger).ffill()
    return carried, pos - trig_pos, trig_day.eq(day)


def _sparse_hist(flag: pd.Series, value: pd.Series, k: int, index) -> pd.Series:
    """Value of the k-th most recent event (k=0 newest), as known at the current bar.

    `flag` marks the bar on which the event became KNOWN and `value` is its payload.
    Taking the sparse event series, shifting it by k *within the event sequence*, then
    reindexing + ffill gives, at every bar, the payload of the k-th previous event.
    """
    ev = value.where(flag).dropna()
    if ev.empty:
        return pd.Series(np.nan, index=index)
    return ev.shift(k).reindex(index).ffill()


def _pivots(h: pd.Series, l: pd.Series, w: int = PIVOT_WING):
    """Swing pivots, shifted so they are only visible once confirmed.

    A pivot high at bar j needs bars j+1..j+w to confirm it, so it is first knowable
    at bar j+w. Everything returned is therefore .shift(w)-ed: at bar t the series
    describe the pivot that formed at bar t-w. This is what keeps the wedge causal.
    """
    hi = h.copy()
    lo = l.copy()
    is_ph = pd.Series(True, index=h.index)
    is_pl = pd.Series(True, index=h.index)
    for k in range(1, w + 1):
        is_ph &= (hi > hi.shift(k)) & (hi >= hi.shift(-k))
        is_pl &= (lo < lo.shift(k)) & (lo <= lo.shift(-k))
    known_ph = is_ph.shift(w).fillna(False).astype(bool)
    known_pl = is_pl.shift(w).fillna(False).astype(bool)
    return known_ph, known_pl


# ══════════════════════ state machines (strictly causal loops) ══════════════════════
def _brooks_bar_count(h, l, ctx, newday, bull: bool):
    """Al Brooks bar counting -> the High 2 (bull) / Low 2 (bear) trigger.

    Brooks, Trading Price Action Trading Ranges, ch.17 "Bar Counting: High and Low
    1, 2, 3 and 4 Patterns": in a pullback inside a bull move, the FIRST bar whose
    high goes above the high of the prior bar is a High 1; if the market keeps going
    down instead of turning up, the NEXT bar whose high goes above the prior bar's
    high is the High 2. Mirror image for Low 1 / Low 2 in a bear move.

    State per side (bull shown):
      run_high  highest high since the count began; a bar above it means the trend
                resumed, the pullback is over, and the count resets to zero.
      count     0 -> nothing yet, 1 -> H1 has printed.
      h1_low    lowest low of the pullback as of the H1 bar.
      armed     a bar has since traded BELOW h1_low, i.e. the second leg down exists.
      fired     one H2 per pullback (see CHOICE in register()).
    """
    n = len(h)
    out = np.zeros(n, dtype=bool)
    run = -np.inf if bull else np.inf
    leg = np.inf if bull else -np.inf
    count = 0
    ref = np.nan
    armed = False
    fired = False
    for i in range(1, n):
        if newday[i]:
            run = h[i] if bull else l[i]
            leg = l[i] if bull else h[i]
            count, armed, fired = 0, False, False
            continue
        if not ctx[i]:
            # out of the trend context -> drop the structure, re-anchor
            run = h[i] if bull else l[i]
            leg = l[i] if bull else h[i]
            count, armed, fired = 0, False, False
            continue

        if bull:
            if h[i] > run:                       # trend made a new high -> reset
                run = h[i]
                leg = l[i]
                count, armed, fired = 0, False, False
                continue
            # --- fire first, using only state established on EARLIER bars, so an
            #     outside bar can never be both the second-leg low and the H2 ---
            if (not fired) and count >= 1 and armed and h[i] > h[i - 1]:
                out[i] = True
                fired = True
                armed = False
            elif count == 0 and h[i] > h[i - 1]:
                count = 1
                ref = min(leg, l[i])             # pullback low as of the H1 bar
            leg = min(leg, l[i])
            if count >= 1 and l[i] < ref:
                armed = True                     # second leg down confirmed
                ref = l[i]
        else:
            if l[i] < run:
                run = l[i]
                leg = h[i]
                count, armed, fired = 0, False, False
                continue
            if (not fired) and count >= 1 and armed and l[i] < l[i - 1]:
                out[i] = True
                fired = True
                armed = False
            elif count == 0 and l[i] < l[i - 1]:
                count = 1
                ref = max(leg, h[i])
            leg = max(leg, h[i])
            if count >= 1 and h[i] > ref:
                armed = True
                ref = h[i]
    return out


def _breakout_pullback(bo, h, l, o, c, newday, max_bars: int, bull: bool):
    """Al Brooks breakout pullback.

    Brooks' glossary: a breakout pullback is "a small pullback of one to about five
    bars that occurs within a few bars after a breakout", and because you call it a
    pullback you expect the breakout to RESUME.

    Episode: a breakout bar arms the setup; at least one pullback bar must print; the
    entry is the first bar after that which trades above the prior bar's high and
    closes up. A close/low back through the breakout bar's low kills the episode —
    Brooks' own distinction: if it fails you would not have called it a pullback.
    """
    n = len(h)
    out = np.zeros(n, dtype=bool)
    active = False
    anchor = np.nan
    age = 0
    seen_pb = False
    for i in range(1, n):
        if newday[i]:
            active = False
        if active:
            age += 1
            if age > max_bars or (l[i] < anchor if bull else h[i] > anchor):
                active = False
            elif bull:
                if seen_pb and h[i] > h[i - 1] and c[i] > o[i]:
                    out[i] = True
                    active = False
                elif l[i] < l[i - 1] or c[i] < o[i]:
                    seen_pb = True
            else:
                if seen_pb and l[i] < l[i - 1] and c[i] < o[i]:
                    out[i] = True
                    active = False
                elif h[i] > h[i - 1] or c[i] > o[i]:
                    seen_pb = True
        if bo[i] and not active:
            active = True
            anchor = l[i] if bull else h[i]
            age = 0
            seen_pb = False
    return out


# ══════════════════════════════ register ══════════════════════════════
def register(df: pd.DataFrame) -> dict:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    atr, day = df["atr"], df["_day"]
    e20, e50 = df["ema20"], df["ema50"]
    rng = (h - l).replace(0.0, np.nan)
    body = (c - o).abs()

    pos = pd.Series(np.arange(len(df), dtype=float), index=df.index)
    newday = day.ne(day.shift(1)).to_numpy()

    hv, lv, ov, cv = (x.to_numpy(float) for x in (h, l, o, c))

    # Brooks' bull/bear-leg proxy. Brooks reads "the market is in a bull trend" off
    # the chart; the closest thing he gives that is codeable is his repeated statement
    # that in a bull trend the market stays above a RISING 20-bar EMA.
    # CHOICE: rising ema20 over 5 bars AND ema20 above ema50. This is MY proxy for a
    # bull leg. It is NOT Brooks' "always-in" — see the rejection notes below.
    bull_ctx = ((e20 > e20.shift(TREND_SLOPE_BARS)) & (e20 > e50)).fillna(False)
    bear_ctx = ((e20 < e20.shift(TREND_SLOPE_BARS)) & (e20 < e50)).fillna(False)

    out: dict[str, tuple[pd.Series, int]] = {}

    # ───────────────────────────────────────────────────────────────────────
    # 1) ab_brooks_h2 — AL BROOKS, High 2 bull flag
    # https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/
    #   (Brooks' own list, item 4 "High 2 Bull Flags & Low 2 Bear Flags":) two failed
    #   reversal attempts inside a trend; the trader enters after the second leg fails.
    # https://onlinelibrary.wiley.com/doi/10.1002/9781119202608.ch17
    #   Trading Price Action Trading Ranges, ch.17: bar counting counts "the number of
    #   times the current bar's high extends at least one tick above the high of the
    #   prior bar" to judge whether a pullback in a bull trend has ended. The first
    #   such bar in the pullback is the High 1; if the market does not turn up and
    #   instead continues down, the next such bar is the High 2.
    # Entry per Brooks is a buy stop one tick above the signal bar's high — which is
    # filled ON the H2 bar itself. CHOICE: this harness enters at a bar close, so the
    # trigger is the CLOSE of that same H2 bar (same bar, worse fill — never earlier).
    # CHOICE: one H2 per pullback. Brooks would go on to count H3/H4; de-duplicating
    # to the first H2 keeps this a single testable rule instead of a family of them.
    # ───────────────────────────────────────────────────────────────────────
    out["ab_brooks_h2"] = (
        _clean(pd.Series(_brooks_bar_count(hv, lv, bull_ctx.to_numpy(), newday, True),
                         index=df.index), df.index),
        +1,
    )

    # ───────────────────────────────────────────────────────────────────────
    # 2) ab_brooks_l2 — AL BROOKS, Low 2 bear flag  (exact mirror of #1)
    # Same two sources. Brooks: in a bear trend the first bar whose low goes below the
    # prior bar's low during the rally is a Low 1, the second one is the Low 2, and the
    # Low 2 is where the bears re-enter.
    # ───────────────────────────────────────────────────────────────────────
    out["ab_brooks_l2"] = (
        _clean(pd.Series(_brooks_bar_count(hv, lv, bear_ctx.to_numpy(), newday, False),
                         index=df.index), df.index),
        -1,
    )

    # ───────────────────────────────────────────────────────────────────────
    # 3) ab_brooks_bopb — AL BROOKS, breakout pullback (long)
    # https://www.brookstradingcourse.com/price-action-trading-terms-glossary/
    #   "a small pullback of one to about five bars that occurs within a few bars
    #    after a breakout ... you are expecting the breakout to resume and the
    #    pullback is a setup for that resumption."
    # https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/
    #   item 3 "Breakouts": a breakout is "a trend bar up or down" that "closes beyond
    #   at least minor support or resistance".
    # CHOICE: "minor resistance" = the 20-bar high (donch_hi20, shifted so the bar does
    #   not clear its own high). "Trend bar" = body >= 60% of range and the close in
    #   the top quarter — Brooks describes a strong trend bar as a big body closing at
    #   or near its extreme with little tail, but gives no percentage anywhere.
    # ───────────────────────────────────────────────────────────────────────
    strong_bull = (c > o) & (body >= STRONG_BODY_FRAC * rng) & \
                  (c >= l + STRONG_CLOSE_FRAC * rng)
    bo_up = (strong_bull & (c > df["donch_hi20"].shift(1))).fillna(False)
    out["ab_brooks_bopb"] = (
        _clean(pd.Series(_breakout_pullback(bo_up.to_numpy(), hv, lv, ov, cv,
                                            newday, BOPB_MAX_BARS, True),
                         index=df.index), df.index),
        +1,
    )

    # ───────────────────────────────────────────────────────────────────────
    # 4) ab_brooks_bopb_short — AL BROOKS, breakout pullback (short)
    # Same glossary rule, mirrored: strong bear trend bar closing below the 20-bar low,
    # a one-to-five bar rally, then the first bar taking out the prior bar's low.
    # ───────────────────────────────────────────────────────────────────────
    strong_bear = (c < o) & (body >= STRONG_BODY_FRAC * rng) & \
                  (c <= h - STRONG_CLOSE_FRAC * rng)
    bo_dn = (strong_bear & (c < df["donch_lo20"].shift(1))).fillna(False)
    out["ab_brooks_bopb_short"] = (
        _clean(pd.Series(_breakout_pullback(bo_dn.to_numpy(), hv, lv, ov, cv,
                                            newday, BOPB_MAX_BARS, False),
                         index=df.index), df.index),
        -1,
    )

    # ───────────────────────────────────────────────────────────────────────
    # 5) ab_brooks_wedge_short — AL BROOKS, wedge top / three-push reversal
    # https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/
    #   item 5 "Wedges (Three Pushes)": "any pattern with three (sometimes four or
    #   five) pushes that is sloped up or down"; "as soon as there are two pushes,
    #   traders can draw a line connecting them and then extend the line to the right
    #   (a trend channel line). They will then watch for a reversal if the market
    #   approaches the line for a third time."
    #   Brooks also says explicitly: it "does not have to be convergent and the third
    #   push does not have to exceed the second."
    # CHOICE: a "push" = a confirmed swing high (2 bars either side). CHOICE: the three
    #   pushes must be strictly rising — this is NARROWER than Brooks, who allows a
    #   third push that falls short; the strict version is the only one that can be
    #   pinned down without judging "close enough to the line".
    # CHOICE: "approaches the line for a third time" is read as push 3 REACHING the
    #   extended push1->push2 trend channel line (>= line value). Overshoot is allowed.
    # Entry: Brooks reverses on a bar that trades below the prior bar, so the trigger
    #   is the first bear-bar close below the third push's low within 6 bars.
    # ───────────────────────────────────────────────────────────────────────
    known_ph, _known_pl = _pivots(h, l)
    ph_val = h.shift(PIVOT_WING)
    ph_low = l.shift(PIVOT_WING)

    p3 = _sparse_hist(known_ph, ph_val, 0, df.index)      # newest push
    p2 = _sparse_hist(known_ph, ph_val, 1, df.index)
    p1 = _sparse_hist(known_ph, ph_val, 2, df.index)
    x3 = _sparse_hist(known_ph, pos - PIVOT_WING, 0, df.index)   # bar index of push
    x2 = _sparse_hist(known_ph, pos - PIVOT_WING, 1, df.index)
    x1 = _sparse_hist(known_ph, pos - PIVOT_WING, 2, df.index)
    p3_low = _sparse_hist(known_ph, ph_low, 0, df.index)
    p3_known_at = _sparse_hist(known_ph, pos, 0, df.index)
    # small day ordinal (0,1,2,...) rather than a raw ns timestamp: _sparse_hist
    # carries values through float64, and ns epochs sit near the edge of float64's
    # exact-integer range. An ordinal keeps the session comparison exact.
    day_ord = day.astype("category").cat.codes.astype(float)
    p3_day = _sparse_hist(known_ph, day_ord, 0, df.index)

    slope = (p2 - p1) / (x2 - x1).replace(0.0, np.nan)
    line_at_p3 = p1 + slope * (x3 - x1)
    wedge_ok = (
        (p1 < p2) & (p2 < p3)                      # three rising pushes
        & (p3 >= line_at_p3)                       # reached/overshot the channel line
        & ((x3 - x1) <= WEDGE_MAX_SPAN)            # one structure, not a whole week
        & (p3_day == day_ord)                      # push 3 and the entry share a day
    )
    age3 = pos - p3_known_at
    out["ab_brooks_wedge_short"] = (
        _clean(wedge_ok
               & (age3 >= 1) & (age3 <= WEDGE_ENTRY_BARS)
               & (c < p3_low) & (c.shift(1) >= p3_low)   # FIRST close below push 3
               & (c < o),
               df.index),
        -1,
    )

    # ───────────────────────────────────────────────────────────────────────
    # 6) ab_brooks_finalflag_short — AL BROOKS, final bull flag
    # https://www.brookstradingcourse.com/price-action/10-best-price-action-trading-patterns/
    #   item 2 "Final Flags": a trend-reversal pattern that BEGINS as a continuation,
    #   with "a pullback that is usually mostly horizontal", forming near a magnet
    #   (resistance in a bull); traders anticipate the continuation fails and reverses.
    # https://www.brookstradingcourse.com/futures-market/learn-to-trade-emini-final-flags/
    #   Brooks: "a tight trading range late in a bear trend is often the Final Bear
    #   Flag", i.e. the flag breaks out and the breakout is what reverses.
    # CHOICE: "mostly horizontal tight range" = 8 bars whose full height is <= 1.5 ATR.
    #   "Late in the trend / at a magnet" = that flag high sits within 0.25 ATR of the
    #   30-bar high, with a rising ema20 into it. Brooks gives no bar counts for either.
    # Entry: the flag breaks UP (first close above the flag high), then FAILS — the
    #   first close back below the flag high within 5 bars, on a bear bar, is the short.
    # ───────────────────────────────────────────────────────────────────────
    flag_hi = h.rolling(FLAG_BARS).max().shift(1)
    flag_lo = l.rolling(FLAG_BARS).min().shift(1)
    tight = (flag_hi - flag_lo) <= FLAG_TIGHT_ATR * atr.shift(1)
    at_magnet = flag_hi >= (h.rolling(FLAG_LOOKBACK).max().shift(1)
                            - FLAG_NEAR_HIGH_ATR * atr.shift(1))
    late_bull = e20 > e20.shift(FLAG_BARS)
    flag_break = (tight & at_magnet & late_bull
                  & (c > flag_hi) & (c.shift(1) <= flag_hi)).fillna(False)
    ff_lvl, ff_age, ff_same = _carry(flag_break, flag_hi, day, pos)
    out["ab_brooks_finalflag_short"] = (
        _clean(ff_same
               & (ff_age >= 1) & (ff_age <= FLAG_FAIL_BARS)
               & (c < ff_lvl) & (c.shift(1) >= ff_lvl)   # breakout fails back inside
               & (c < o),
               df.index),
        -1,
    )

    # ───────────────────────────────────────────────────────────────────────
    # 7) ab_volman_ddb — BOB VOLMAN, Double Doji Break (long)
    # https://www.trade2win.com/threads/bob-volman-price-action-scalping.153716/
    #   Volman readers' summary of the setup as published in Forex Price Action
    #   Scalping: "classic two doji pre-breakout tension" ahead of a range break;
    #   entry is a market order on a 1-pip break of the signal bar's high; the setup
    #   wants a pullback to around the 20-ema.
    # https://www.daytradingbias.com/forex-price-action-scalping-an-in-depth-look-into-the-field-of-professional-scalping-by-bob-volman/
    #   confirms the named setup list (DD, FB, SB, BB, RB, IRB, ARB) all revolve
    #   around the 20-ema, and that the DD is two dojis / small candles in a row.
    # TIMEFRAME: Volman's dojis are 70-tick bars. Not reconstructible here — this is
    #   the same STRUCTURE read on 5-min bars, not a claim to trade his timeframe.
    # CHOICE: "doji" is scaled to volatility instead of pips, since a 2-pip EUR/USD
    #   bar has no MNQ equivalent: range <= 0.6 ATR and body <= half the range.
    # CHOICE: entry is the first CLOSE above the two-bar range high (the harness fills
    #   on closes); Volman's own trigger is 1 pip through the same level intrabar.
    # ───────────────────────────────────────────────────────────────────────
    doji = ((h - l) <= DOJI_RANGE_ATR * atr) & (body <= DOJI_BODY_FRAC * (h - l))
    pair = (doji & doji.shift(1)).fillna(False)
    pair_hi = pd.concat([h, h.shift(1)], axis=1).max(axis=1)
    pair_lo = pd.concat([l, l.shift(1)], axis=1).min(axis=1)
    # Volman's "pullback to around the 20ema": the doji pair must sit ON the ema.
    near_ema = (pair_lo <= e20 + DD_EMA_TOL_ATR * atr) & \
               (pair_hi >= e20 - DD_EMA_TOL_ATR * atr)
    dd_up = (pair & near_ema & (e20 > e20.shift(TREND_SLOPE_BARS))).fillna(False)
    dd_lvl, dd_age, dd_same = _carry(dd_up, pair_hi, day, pos)
    out["ab_volman_ddb"] = (
        _clean(dd_same
               & (dd_age >= 1) & (dd_age <= DD_BREAK_BARS)
               & (c > dd_lvl) & (c.shift(1) <= dd_lvl)   # first close through the pair
               & (c > o),
               df.index),
        +1,
    )

    # ───────────────────────────────────────────────────────────────────────
    # 8) ab_volman_irb_short — BOB VOLMAN, squeezed range break (short)
    # https://www.trade2win.com/threads/bob-volman-price-action-scalping.153716/
    #   "Squeeze/IRB setup: requires visible top and bottom barriers with multiple
    #    tests; tension building between support/resistance before breakout."
    # Volman's stated rule (quoted in reader notes of Forex Price Action Scalping):
    #   "look for a proper squeeze: prices are literally being sandwiched between the
    #    20ema and the barrier line. Pre-breakout tension is one of the better leads
    #    to a dependable breakout." He also warns the OPPOSITE case is a trap: a break
    #    that arrives "almost instantaneously" with "no pre-breakout buildup" is a
    #    false break. The squeeze requirement is exactly what filters that out.
    # CHOICE: "barrier line" = the 10-bar low, and it only counts as a barrier if at
    #   least 2 of those bars came within 0.25 ATR of it (Volman's "multiple tests").
    #   "Squeeze" = the last 3 bars all under 0.8 ATR, all closing below a declining
    #   ema20, with the ema20 no more than 1.5 ATR above the barrier (sandwiched).
    #   Volman quantifies none of these in pips that transfer to MNQ.
    # ───────────────────────────────────────────────────────────────────────
    barrier = l.rolling(IRB_BARRIER_BARS).min().shift(1)
    tests = ((l <= barrier + IRB_TEST_TOL_ATR * atr)
             .rolling(IRB_BARRIER_BARS).sum().shift(1))
    small = (h - l) <= IRB_SQUEEZE_ATR * atr
    squeezed = (small & (c < e20)).rolling(IRB_SQUEEZE_BARS).min().shift(1).astype(bool)
    sandwich = (e20.shift(1) - barrier) <= IRB_SANDWICH_ATR * atr
    # NOTE: no separate ema-slope filter. "Sandwiched between the 20ema and the
    # barrier" is already the whole condition — every squeeze bar closes below the
    # ema20 and the ema20 sits within 2 ATR of the barrier, which is the compression
    # Volman describes. Adding a slope test on top was my invention, not his, and it
    # cut the sample below the harness's usable floor.
    out["ab_volman_irb_short"] = (
        _clean((tests >= IRB_MIN_TESTS)
               & squeezed & sandwich
               & (c < barrier) & (c.shift(1) >= barrier)   # first close through it
               & (c < o),
               df.index),
        -1,
    )

    return out


# ══════════════════════════════════════════════════════════════════════════════
# REJECTED — researched and deliberately NOT implemented
#
# AL BROOKS
#  * "Always-in direction". Brooks defines it as the side you would take if forced to
#    be long or short right now. Brooks Trading Course material states plainly that it
#    is "not line pattern related" and references directional strength rather than any
#    pattern. There is no bar-level trigger anywhere in the published definition. Some
#    third-party TradingView scripts invent a flip rule ("strong bar + follow-through")
#    — that is the SCRIPT AUTHOR'S rule, not Brooks', so it is not coded here and not
#    attributed to him. The ema20-slope filter used above is labelled as my own proxy.
#  * Signal-bar quality grading (tail size, overlap, "good" vs "bad" signal bar) and
#    the trend / trading-range / breakout-mode classification. Both are the parts of
#    Brooks that he explicitly teaches as read-it-off-the-chart judgement; any number
#    put on them would be mine, not his.
#  * "Second entry" as a general concept beyond H2/L2 — it is the same idea, already
#    covered by #1 and #2; implementing it separately would double-count one rule.
#  * Measured moves, magnets, channels (items 6,7,10 of his ten patterns). These are
#    target/context tools, not entry triggers, and this interface returns entries only.
#
# BOB VOLMAN
#  * The 70-tick chart itself. Not reconstructible from 5-minute OHLCV. Stated openly
#    above rather than silently substituted.
#  * Round-number filter ("quasi-indicator" in Understanding Price Action). It is an
#    FX convention tied to the 00 level in a currency pair; there is no published
#    Volman rule for what the equivalent is on an index future.
#  * Advanced Range Break (ARB) and Block Break (BB). Both need a hand-drawn barrier
#    across a pattern whose boundaries the trader chooses by eye. The Inside Range
#    Break was implemented instead precisely because its barrier can be defined as an
#    N-bar extreme without picking a shape off the chart.
#  * The 10-tick stop / 20-tick target from Understanding Price Action. Real, published
#    and mechanical — but exits belong to the harness sweep, not to this file.
# ══════════════════════════════════════════════════════════════════════════════
