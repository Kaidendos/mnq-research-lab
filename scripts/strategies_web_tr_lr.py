"""Linda Bradford Raschke — mechanical setups from *Street Smarts* (Connors &
Raschke, 1995) and her published LBR Group / 3-10 oscillator material.

WHY HER: Raschke is a Market Wizard (Schwager, *The New Market Wizards*, 1992),
ran Granat Partners / LBR Asset Management, and — unusually for a famous
discretionary trader — published her setups as NUMBERED RULES. Every strategy
below is traceable to printed rule text, not to a guru screenshot.

SOURCES (one per setup, recorded on each block):
  Turtle Soup / Turtle Soup Plus One — Street Smarts ch.4/ch.5, rules quoted at
    https://pdfcoffee.com/street-smarts-laurence-a-connors-and-linda-bradford-raschke-1995-file-goc-5-pdf-free.html
  80-20's — Street Smarts ch.3, rules quoted at
    https://pdfcoffee.com/80-20x27s-from-street-smarts-high-probability-short-term-trading-strategiesraschke--pdf-free.html
  Holy Grail — Street Smarts, rules restated at
    https://www.tradingsetupsreview.com/the-holy-grail-trading-setup/
  The Anti — Street Smarts ch.9, stochastic settings at
    https://www.netpicks.com/anti-trading-pattern/
  First Cross (3-10 oscillator) — LBR's own 3/10 material, rules restated at
    http://toddstrade.blogspot.com/2009/03/3-10-first-cross.html
  3-10 oscillator construction (3 SMA - 10 SMA, 16-SMA signal line) —
    https://www.netpicks.com/310-oscillator-macd/

ATTRIBUTION HONESTY. Raschke wrote these for DAILY bars on futures/stocks of the
1990s. This project trades 5-minute MNQ RTH bars. Every setup here is a
SCALE PORT: the rule's structure is preserved exactly, but "day" is read as
"bar" and "20-day channel" as "20-bar channel". Where the book left a number
vague ("5-10 ticks", "trending"), the concrete reading I picked is flagged in a
CHOICE: comment. Nothing here is attributed to her that she did not print.

CAUSALITY. Bar i uses only data closed at bar i. Session aggregates are cummin/
cummax; prior-day values are groupby-then-.shift(1)-then-map, the same pattern
funded_search.py uses for pdh/pdl. No groupby("_day").transform("max").
NOTE: rolling windows here are bar-count windows over the RTH-only frame, so a
20-bar window near the open reaches back into the previous session. That is
backward-looking and therefore causal; it is not a lookahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── concrete readings of vague book numbers (MNQ: 1 tick = 0.25 index points) ──
TICK = 0.25
ENTRY_TICKS = 10.0            # Turtle Soup: "an entry buy stop 5-10 ticks above"
ENTRY_OFF = ENTRY_TICKS * TICK
PEN_TICKS = 10.0              # 80-20's: "must trade at least 5-15 ticks below"
PENETRATION = PEN_TICKS * TICK
REVERSAL_WINDOW = 6           # bars a failed-breakout level stays "live"
ADX_TREND = 30.0              # Street Smarts: "14-period ADX ... above 30"
ADX_LOOKBACK = 10             # bars over which "INITIALLY above 30" is checked
MAX_8020_PER_DAY = 5          # 80-20 is a day trade; the stop order is re-placed


def _b(s, idx) -> pd.Series:
    return pd.Series(s, index=idx).reindex(idx).fillna(False).astype(bool)


def _prior_day(series_by_day: pd.Series, daymap: pd.Series) -> pd.Series:
    """Map each bar to the PREVIOUS session's value. Causal by construction."""
    return daymap.map(series_by_day.shift(1))


def _failed_break_long(low, close, level, live, idx):
    """Shared engine for Turtle-Soup-family longs.

    `level` is the channel low that was violated; `live` marks bars where a
    qualifying violation has occurred within REVERSAL_WINDOW bars. Entry is the
    first bar that closes back ABOVE the violated level — the close-bar analogue
    of Raschke's "entry buy stop 5-10 ticks above the previous 20-day low",
    since this harness fills at the close of the signal bar.
    """
    lvl = level.where(live).ffill(limit=REVERSAL_WINDOW)
    reclaim = (close > lvl) & lvl.notna()
    first = reclaim & ((close.shift(1) <= lvl) | (live & (low < lvl)))
    return _b(first, idx)


def _failed_break_short(high, close, level, live, idx):
    lvl = level.where(live).ffill(limit=REVERSAL_WINDOW)
    reclaim = (close < lvl) & lvl.notna()
    first = reclaim & ((close.shift(1) >= lvl) | (live & (high > lvl)))
    return _b(first, idx)


def register(df: pd.DataFrame) -> dict:
    idx = df.index
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    adx, ema20, atr = df["adx"], df["ema20"], df["atr"]
    day = df["_day"]
    daymap = pd.Series(day, index=idx)
    same_day = day == day.shift(1)

    out: dict = {}

    # ═══════════════════════════════════════════════════════════════════════
    # 1. TURTLE SOUP  — Street Smarts ch.4, verbatim rules:
    #    "1. Today must make a new 20-day low - the lower the better.
    #     2. The previous 20-day low must have occurred at least four trading
    #        sessions earlier.
    #     3. After the market falls below the prior 20-day low, place an entry
    #        buy stop 5-10 ticks above the previous 20-day low."
    #    Sells are the mirror at the 20-day high.
    #    PORT: 20 BARS instead of 20 days. Rule 2's "four sessions earlier"
    #    becomes "the prior 20-bar extreme is at least 4 bars old", tested as
    #    "the last 3 bars did not contain that extreme".
    #    Rule 3's "5-10 ticks above" is the ENTRY OFFSET, not a requirement on
    #    how deep the breakout goes — rule 1 only asks for a new 20-bar low.
    # ═══════════════════════════════════════════════════════════════════════
    p20lo = l.rolling(20).min().shift(1)          # prior 20-bar low, excl. now
    p20hi = h.rolling(20).max().shift(1)
    lo3 = l.rolling(3).min().shift(1)             # extreme of the last 3 bars
    hi3 = h.rolling(3).max().shift(1)

    # rule 1: today makes a new 20-bar low / high
    ts_break_dn = l < p20lo
    ts_break_up = h > p20hi
    # rule 2: the violated extreme is >= 4 bars old
    ts_gap_dn = lo3 > p20lo
    ts_gap_up = hi3 < p20hi

    ts_live_dn = ts_break_dn & ts_gap_dn
    ts_live_up = ts_break_up & ts_gap_up
    # rule 3: the buy stop sits 5-10 ticks ABOVE the violated 20-bar low
    ts_lvl_dn = p20lo + ENTRY_OFF
    ts_lvl_up = p20hi - ENTRY_OFF

    out["lr_raschke_turtlesoup_long"] = (
        _failed_break_long(l, c, ts_lvl_dn, ts_live_dn, idx), +1)
    out["lr_raschke_turtlesoup_short"] = (
        _failed_break_short(h, c, ts_lvl_up, ts_live_up, idx), -1)

    # ═══════════════════════════════════════════════════════════════════════
    # 2. TURTLE SOUP PLUS ONE — Street Smarts ch.5, verbatim rules:
    #    "1. The market makes a new 20-day low. The previous 20-bar low must
    #        have been made at least three trading sessions earlier.
    #     2. An entry buy stop is placed the next day (day two) at the earlier
    #        20 day low."
    #    Plus One waits for the breakout bar to CLOSE outside the channel and
    #    only then arms the reclaim order on the FOLLOWING bar. That is the one
    #    structural difference from plain Turtle Soup, and it is preserved here:
    #    `.shift(1)` on the arming condition = "the next day (day two)".
    #    PORT: gap requirement is 3 bars (rule text says three, not four).
    # ═══════════════════════════════════════════════════════════════════════
    lo2 = l.rolling(2).min().shift(1)
    hi2 = h.rolling(2).max().shift(1)
    p1_close_out_dn = (c < p20lo) & (lo2 > p20lo)   # closed BELOW the channel
    p1_close_out_up = (c > p20hi) & (hi2 < p20hi)
    # armed on the following bar, carrying the level that was violated
    p1_lvl_dn = p20lo.where(p1_close_out_dn).shift(1)
    p1_lvl_up = p20hi.where(p1_close_out_up).shift(1)
    p1_live_dn = p1_lvl_dn.notna() & same_day
    p1_live_up = p1_lvl_up.notna() & same_day

    out["lr_raschke_ts_plus1_long"] = (
        _failed_break_long(l, c, p1_lvl_dn.ffill(limit=1), p1_live_dn, idx), +1)
    out["lr_raschke_ts_plus1_short"] = (
        _failed_break_short(h, c, p1_lvl_up.ffill(limit=1), p1_live_up, idx), -1)

    # ═══════════════════════════════════════════════════════════════════════
    # 3. THE 80-20'S — Street Smarts ch.3, verbatim buy rules:
    #    "1. Yesterday the market opened in the top 20 percent of its daily
    #        range and closed in the lower 20 percent of its daily range.
    #     2. Today the market must trade at least 5-15 ticks below yesterday's
    #        low."
    #    Then: buy stop at the previous day's low; day trade only.
    #    This one is NOT scale-ported — it is the genuine daily-bar rule, run on
    #    the prior RTH session, which is exactly how Raschke stated it.
    #    CHOICE: "5-15 ticks" -> 10 MNQ ticks (2.5 index points).
    # ═══════════════════════════════════════════════════════════════════════
    d_open = o.groupby(day).first()
    d_high = h.groupby(day).max()
    d_low = l.groupby(day).min()
    d_close = c.groupby(day).last()
    po = _prior_day(d_open, daymap)
    ph = _prior_day(d_high, daymap)
    pl_ = _prior_day(d_low, daymap)
    pcl = _prior_day(d_close, daymap)
    prng = (ph - pl_).replace(0, np.nan)

    setup_buy = (po >= pl_ + 0.80 * prng) & (pcl <= pl_ + 0.20 * prng)
    setup_sell = (po <= pl_ + 0.20 * prng) & (pcl >= pl_ + 0.80 * prng)

    # rule 2: running session extreme has penetrated yesterday's extreme.
    # cummin/cummax = causal (they see only bars up to and including now).
    sess_lo = l.groupby(day).cummin()
    sess_hi = h.groupby(day).cummax()
    pen_dn = sess_lo <= (pl_ - PENETRATION)
    pen_up = sess_hi >= (ph + PENETRATION)
    first_pen_dn = pen_dn & ~(pen_dn.shift(1).fillna(False) & same_day)
    first_pen_up = pen_up & ~(pen_up.shift(1).fillna(False) & same_day)

    # entry: "place a buy stop at the previous day's low". A stop is taken out
    # when price TRADES to the level, so the trigger is high >= pdl (not a
    # close above it); the harness then fills at that bar's close. Either a
    # fresh touch, or the same bar that penetrated and traded back up.
    raw_l = (setup_buy & pen_dn & (h >= pl_)
             & (((h.shift(1) < pl_) & same_day) | first_pen_dn))
    raw_s = (setup_sell & pen_up & (l <= ph)
             & (((l.shift(1) > ph) & same_day) | first_pen_up))
    # "Strictly a day trade" — the book allows the stop to be re-placed after a
    # stop-out on the same session. CHOICE: cap at 5 attempts per session.
    raw_l = raw_l.fillna(False)
    raw_s = raw_s.fillna(False)
    cap_l = raw_l & (raw_l.groupby(day).cumsum() <= MAX_8020_PER_DAY)
    cap_s = raw_s & (raw_s.groupby(day).cumsum() <= MAX_8020_PER_DAY)

    out["lr_raschke_8020_long"] = (_b(cap_l, idx), +1)
    out["lr_raschke_8020_short"] = (_b(cap_s, idx), -1)

    # ═══════════════════════════════════════════════════════════════════════
    # 4. THE HOLY GRAIL — Street Smarts. Rules as restated by TradingSetupsReview:
    #    "1. 14-period ADX is initially above 30 and rising.
    #     2. Prices pull back to touch the 20-period moving average.
    #     3. Place buy order at the high of the bar that touches the MA."
    #    CHOICE 1: sources split between 20 SMA and 20 EMA. The harness ships
    #    ema20, so EMA is used; the book's own text reads "20 period exponential
    #    moving average".
    #    CHOICE 2: the rules give no mechanical TREND DIRECTION filter (Raschke
    #    read it off the chart). I use the slope of the 20-EMA over 10 bars.
    #    CHOICE 3: "buy at the high of the touch bar" is a stop order; this
    #    harness fills at the close, so entry is the first bar AFTER the touch
    #    whose high exceeds the touch bar's high.
    #    CHOICE 4 (important): the word is "INITIALLY above 30 and rising" —
    #    i.e. during the trend leg, BEFORE the pullback. ADX almost always falls
    #    while price retraces, so testing "rising" on the touch bar itself is a
    #    misreading (it leaves 0.13% of bars). Here the qualification is
    #    "ADX was >30 and rising at some point in the last 10 bars".
    # ═══════════════════════════════════════════════════════════════════════
    adx_ok = ((adx > ADX_TREND) & (adx > adx.shift(1))) \
        .rolling(ADX_LOOKBACK).max().fillna(0).astype(bool)
    slope_up = ema20 > ema20.shift(10)
    slope_dn = ema20 < ema20.shift(10)
    touch_dn = (l <= ema20) & (h >= ema20) & slope_up & adx_ok   # pullback in uptrend
    touch_up = (l <= ema20) & (h >= ema20) & slope_dn & adx_ok   # rally in downtrend

    # "first bar that trades above the high of the [touch] bar", within 3 bars
    touch_hi = h.where(touch_dn).ffill(limit=3)
    touch_lo = l.where(touch_up).ffill(limit=3)
    armed_up = touch_dn.rolling(4).max().shift(1).fillna(0).astype(bool)
    armed_dn = touch_up.rolling(4).max().shift(1).fillna(0).astype(bool)

    out["lr_raschke_holygrail_long"] = (
        _b(armed_up & (h > touch_hi.shift(1)) & (c > ema20), idx), +1)
    out["lr_raschke_holygrail_short"] = (
        _b(armed_dn & (l < touch_lo.shift(1)) & (c < ema20), idx), -1)

    # ═══════════════════════════════════════════════════════════════════════
    # 5. THE ANTI — Street Smarts ch.9. Book entry text: "Enter when the price
    #    action causes the fast line to turn up once again in the direction of
    #    the slow line (forming a hook)." Indicator: 7-period %K with a
    #    10-period moving average of it acting as the slow/trend line.
    #    So mechanically: slow line sloping one way, fast line counter-moves
    #    against it for a couple of bars, then hooks back — that hook is the
    #    entry. Raschke describes it as "the first pullback after a trend
    #    change", shaped like a small bull/bear flag.
    #    CHOICE: "a couple of bars" -> the fast line fell (rose) on each of the
    #    two bars before the hook.
    # ═══════════════════════════════════════════════════════════════════════
    ll7 = l.rolling(7).min()
    hh7 = h.rolling(7).max()
    rng7 = (hh7 - ll7).replace(0, np.nan)
    fastK = 100.0 * (c - ll7) / rng7
    slowK = fastK.rolling(10).mean()

    slow_up = (slowK > slowK.shift(1)) & (slowK > slowK.shift(3))
    slow_dn = (slowK < slowK.shift(1)) & (slowK < slowK.shift(3))
    # two-bar counter-move against the slow line, then the hook back
    dip = (fastK.shift(1) < fastK.shift(2)) & (fastK.shift(2) < fastK.shift(3))
    pop = (fastK.shift(1) > fastK.shift(2)) & (fastK.shift(2) > fastK.shift(3))
    hook_up = fastK > fastK.shift(1)
    hook_dn = fastK < fastK.shift(1)

    out["lr_raschke_anti_long"] = (
        _b(slow_up & dip & hook_up & (fastK.shift(1) < slowK.shift(1)), idx), +1)
    out["lr_raschke_anti_short"] = (
        _b(slow_dn & pop & hook_dn & (fastK.shift(1) > slowK.shift(1)), idx), -1)

    # ═══════════════════════════════════════════════════════════════════════
    # 6. FIRST CROSS (3-10 oscillator) — LBR's own 3/10 material:
    #    "Buy the first pullback in the fast oscillator after the slow line
    #     crosses above zero for the first time. For a short the rules are
    #     simply the reverse."
    #    3-10 oscillator = SMA(close,3) - SMA(close,10); the SLOW/signal line is
    #    a 16-period SMA of that oscillator. SIMPLE moving averages, per LBR.
    #    CHOICE: "the first pullback" -> the first bar after the zero-cross on
    #    which the fast oscillator has declined for >=2 bars and then turns back
    #    up. Counted once per cross via a causal cumsum within the cross-group,
    #    and only for 30 bars after the cross.
    # ═══════════════════════════════════════════════════════════════════════
    osc = c.rolling(3).mean() - c.rolling(10).mean()
    sig = osc.rolling(16).mean()

    cross_up = (sig > 0) & (sig.shift(1) <= 0)
    cross_dn = (sig < 0) & (sig.shift(1) >= 0)
    grp_up = cross_up.cumsum()          # causal: counts crosses seen so far
    grp_dn = cross_dn.cumsum()
    age_up = grp_up.groupby(grp_up).cumcount()
    age_dn = grp_dn.groupby(grp_dn).cumcount()

    pull_up = (osc.shift(1) < osc.shift(2)) & (osc > osc.shift(1)) & (sig > 0)
    pull_dn = (osc.shift(1) > osc.shift(2)) & (osc < osc.shift(1)) & (sig < 0)
    first_up = pull_up & (pull_up.groupby(grp_up).cumsum() == 1) & (age_up <= 30) & (grp_up > 0)
    first_dn = pull_dn & (pull_dn.groupby(grp_dn).cumsum() == 1) & (age_dn <= 30) & (grp_dn > 0)

    out["lr_raschke_firstcross_long"] = (_b(first_up, idx), +1)
    out["lr_raschke_firstcross_short"] = (_b(first_dn, idx), -1)

    # ═══════════════════════════════════════════════════════════════════════
    # 7. 3-10 MOMENTUM DIVERGENCE — Raschke's stated use of her own oscillator:
    #    a new price extreme that the 3-10 oscillator does NOT confirm is a
    #    warning of exhaustion. Mechanically: price makes a new 10-bar high
    #    while the oscillator prints below its own 10-bar peak and turns down.
    #    HONESTY NOTE: Raschke states the divergence CONCEPT in print but does
    #    not publish a numbered rule for it the way she does for Turtle Soup or
    #    the 80-20's. The 10-bar lookback and the "turns down" trigger are MY
    #    concrete reading, not her printed numbers.
    # ═══════════════════════════════════════════════════════════════════════
    px_hh = h > h.rolling(10).max().shift(1)
    px_ll = l < l.rolling(10).min().shift(1)
    osc_lh = osc < osc.rolling(10).max().shift(1)
    osc_hl = osc > osc.rolling(10).min().shift(1)

    out["lr_raschke_310_divg_short"] = (
        _b(px_hh & osc_lh & (osc < osc.shift(1)) & (c < h - 0.3 * (h - l)), idx), -1)
    out["lr_raschke_310_divg_long"] = (
        _b(px_ll & osc_hl & (osc > osc.shift(1)) & (c > l + 0.3 * (h - l)), idx), +1)

    return out
