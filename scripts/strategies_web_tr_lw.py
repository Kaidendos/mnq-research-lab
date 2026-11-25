"""LARRY WILLIAMS — documented, mechanical entry rules, ported to MNQ 5-min RTH.

Area: lw.  Every rule below is a published Larry Williams rule.  Williams won the
1987 Robbins World Cup Championship of Futures Trading with a verified +11,376%
return on a real, audited account, and his methods are published in books
("How I Made One Million Dollars Last Year Trading Commodities", 1973;
"Long-Term Secrets to Short-Term Trading", 1999) rather than sold as signals.

The project's single best short signal is already Williams' "stretch"
(session_open - K * prior-day range).  Nothing here duplicates it: the closest
relative, rule 3, uses the GREATEST SWING VALUE, which is an average of *failure
swings* on down-close days, not the full range.

SOURCE URL sits directly above each rule.  Where a source leaves a number or a
timeframe to the reader, the concrete choice is flagged "READING:" and is my
choice, not a claim about what Williams said.

ENTRY TRIGGERS ONLY — the harness owns stops / targets / sizing / exits / gates.
Williams insists his %R signals only be taken with the dominant trend; that is
deliberately NOT baked in here because the harness sweeps `gate_ema50` /
`gate_below50` itself.

TIMEFRAME HONESTY
-----------------
Williams wrote for DAILY bars.  Two different ports are used and each is labelled:
  * DAILY PORT  — the rule keeps its daily meaning.  Prior-session values
    (pdh / pdl / prior closes / prior ranges) are daily aggregates passed
    through .shift(1) or .shift(2) and mapped back onto bars; the intraday
    trigger is the 5-min bar on which price crosses the level Williams names.
  * BAR PORT    — the pattern is applied to the 5-min bar series itself, so
    "day" in Williams' text becomes "bar".  This is a transposition, flagged as
    such; the pattern's shape is his, the timeframe is mine.

CAUSALITY
---------
*  Daily aggregates are ALWAYS .shift(1)+ before being mapped back onto bars.
   No groupby("_day").transform("max") on the live session anywhere.
*  The session open is `open` of bar 0, i.e. transform("first") — a value that is
   already known at the close of bar 0, so it is legal on every bar of the day.
*  Session-cumulative WAD uses groupby(day).cumsum() only.
*  Every rolling window is backward-looking and includes at most the current bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ───────────────────────── documented constants ─────────────────────────
# Williams %R, original 1973 formulation: 10-period lookback, 0-100 scale where
# 100% = close at the LOW of the range (oversold) and 0% = close at the high.
PCTR_LEN = 10
PCTR_EXTREME = 99.5      # "%R reaches 100%"  (float tolerance)
PCTR_RETEST = 95.0       # "%R again reaches 95% or 100%"
PCTR_GAP = 5             # "five trading days have passed since 100% was reached"

# Greatest Swing Value: average of the last 4 failure swings, buy stop at
# open + <multiplier> x that average. The cited worked example uses 180%; the
# MQL5 write-up states plainly that the percentage is user-defined.
# READING: 1.0, not 1.8. This is a DATA-STRUCTURE adjustment, not a rule change.
# Williams measured the failure swing on a full daily bar, where the open sits
# mid-range and the swing is a fraction of the day. This feed is RTH-only, so
# the session opens at 09:30 and the 09:30 print is at or near the session
# extreme far more often. Measured on this data the 4-day average buy failure
# swing is 215 pts against a 240 pt median RTH range — i.e. it is already almost
# a whole day wide, so 1.8x lands ~390 pts above the open and fires on 0.08% of
# bars. 1.0x restores the intended "a bit more than a normal counter-swing".
GSV_N = 4
GSV_MULT = 1.0

# Hidden smash day: close inside the lower/upper 25% of the bar's own range.
HIDDEN_PCT = 0.25

# WAD divergence lookback (READING: Williams describes the divergence
# qualitatively; 20 bars = 100 minutes is my concrete swing window).
WAD_LOOK = 20


def _b(s, idx) -> pd.Series:
    """Coerce to a clean boolean Series on idx."""
    return pd.Series(s, index=idx).reindex(idx).fillna(False).astype(bool)


def register(df: pd.DataFrame) -> dict:
    idx = df.index
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    day = df["_day"]
    # NOTE: use the column itself, not pd.Series(day.values, ...) — `.values` on
    # a tz-aware column silently converts to UTC-naive and every daily .map()
    # below then misses on every row.
    dmap = day
    pdh, pdl = df["pdh"], df["pdl"]

    # ── causal scaffolding ────────────────────────────────────────────────
    # Bar ordinal inside the session: guards every rolling window that must not
    # straddle the 16:00 -> 09:30 seam.
    bar_no = df.groupby(day).cumcount()

    # Session open = open of bar 0. Known at the close of bar 0 -> legal all day.
    sess_open = o.groupby(day).transform("first")

    # Daily OHLC built from RTH bars, then shifted before use.
    d_open = o.groupby(day).first()
    d_high = h.groupby(day).max()
    d_low = l.groupby(day).min()
    d_close = c.groupby(day).last()

    pdc = dmap.map(d_close.shift(1))          # prior session close
    pdc2 = dmap.map(d_close.shift(2))         # session-before-last close
    pdl2 = dmap.map(d_low.shift(2))
    pdh2 = dmap.map(d_high.shift(2))

    prev_c = c.shift(1)

    # Williams' entries are STOP orders: the trade exists the moment price TRADES
    # through the level, not when a bar closes beyond it. `touch_up`/`touch_dn`
    # model that — the level is taken out on this bar and had not been taken out
    # on the previous bar of the same session. At bar 0 there is no previous bar,
    # so the guard opens up (prior extreme = -inf / +inf) instead of leaking the
    # prior session's bar across the seam.
    prev_hi = h.shift(1).where(bar_no >= 1, -np.inf)
    prev_lo = l.shift(1).where(bar_no >= 1, np.inf)

    def touch_up(level):
        return (h > level) & (prev_hi <= level)

    def touch_dn(level):
        return (l < level) & (prev_lo >= level)

    out: dict = {}

    # ══════════════════════════════════════════════════════════════════════
    # 1. THE "OOPS!" GAP REVERSAL          [DAILY PORT]
    # Williams, published 1979, restated in "Long-Term Secrets to Short-Term
    # Trading". The market opens beyond yesterday's range, then reverses back
    # into it; you are filled on a stop at yesterday's extreme.
    # https://steadyoptions.com/articles/the-%E2%80%9Coops-signal%E2%80%9D-trade-r415/
    # https://www.tradingview.com/script/7Gqs0Sqn-Larry-Williams-Oops-Strategy/
    #   Long : open BELOW yesterday's LOW, buy stop at yesterday's low.
    #   Short: open ABOVE yesterday's HIGH, sell stop at yesterday's high.
    # READING: the signal is the bar on which the stop would have been ELECTED
    # (price trades through yesterday's extreme); the harness then fills at that
    # bar's close rather than at the stop price, which is a slightly worse fill
    # than Williams would have got. Re-crosses later in the same session are
    # allowed to fire again — Williams does not say one-shot per day.
    # ══════════════════════════════════════════════════════════════════════
    gap_dn = sess_open < pdl
    gap_up = sess_open > pdh
    out["lw_oops_long"] = (_b(gap_dn & touch_up(pdl), idx), +1)
    out["lw_oops_short"] = (_b(gap_up & touch_dn(pdh), idx), -1)

    # ══════════════════════════════════════════════════════════════════════
    # 2. SMASH DAY REVERSAL                [DAILY PORT]
    # "Long-Term Secrets to Short-Term Trading". A smash-day BUY setup is a day
    # that CLOSES BELOW the previous day's LOW; the signal is the next day
    # trading ABOVE the smash day's high — the breakdown failed.
    # https://roboforex.com/blog/education/catch-your-smash-day-with-larry-williams/
    # https://www.mql5.com/en/articles/21127
    # "trades above the high" is taken literally: the bar whose HIGH takes out
    # yesterday's high (= the smash day's high). Fill is at that bar's close.
    # ══════════════════════════════════════════════════════════════════════
    smash_dn_yday = pdc < pdl2      # yesterday closed below the low of 2 days ago
    smash_up_yday = pdc > pdh2      # yesterday closed above the high of 2 days ago
    out["lw_smash_long"] = (_b(smash_dn_yday & touch_up(pdh), idx), +1)
    out["lw_smash_short"] = (_b(smash_up_yday & touch_dn(pdl), idx), -1)

    # ══════════════════════════════════════════════════════════════════════
    # 3. VOLATILITY BREAKOUT — GREATEST SWING VALUE   [DAILY PORT]
    # Williams' GSV. Buy swing = open->high, sell swing = open->low. The
    # *failure* swings are the ones that matter: buy-side uses the open->low
    # distance measured only on DOWN-CLOSE days, averaged over the last 4 such
    # days; the buy stop goes at today's open + 180% of that average.
    # https://futurestradingstrategies.weebly.com/strategies/volatility-breakouts-with-greatest-swing-value
    # https://www.mql5.com/en/articles/20862
    # NOTE: distinct from the "stretch" — this is an average of one-sided
    # failure swings on a filtered subset of days, not the full daily range.
    # See GSV_MULT above for the one number that was changed, and why.
    # ══════════════════════════════════════════════════════════════════════
    dn_close = d_close < d_open
    up_close = d_close > d_open
    # buy-side failure swing: open->low on down-close days
    bs = (d_open - d_low).where(dn_close)
    bs4 = bs.dropna().rolling(GSV_N).mean().reindex(d_close.index).ffill()
    gsv_buy = dmap.map(bs4.shift(1))          # strictly prior days only
    # sell-side failure swing: open->high on up-close days
    ss = (d_high - d_open).where(up_close)
    ss4 = ss.dropna().rolling(GSV_N).mean().reindex(d_close.index).ffill()
    gsv_sell = dmap.map(ss4.shift(1))

    buy_lvl = sess_open + GSV_MULT * gsv_buy
    sell_lvl = sess_open - GSV_MULT * gsv_sell
    out["lw_gsv_long"] = (_b(touch_up(buy_lvl), idx), +1)
    out["lw_gsv_short"] = (_b(touch_dn(sell_lvl), idx), -1)

    # ══════════════════════════════════════════════════════════════════════
    # 4. WILLIAMS %R — THE ORIGINAL 1973 RULE          [BAR PORT]
    # "How I Made One Million Dollars Last Year Trading Commodities" (1973).
    # Original scale is 0-100 INVERTED: %R = 100*(HH - C)/(HH - LL), so 100% is
    # the close sitting on the low of the 10-period range (oversold).
    # Williams' stated buy rule: %R reaches 100%, FIVE trading days pass since
    # that 100% reading, and %R then again reaches 95% or 100%. Mirror for sells
    # at 0% / 5%.
    # https://www.traderslog.com/williams-r-indicator
    # https://www.ireallytrade.com/williamspercentr/
    # READING: "five trading days" becomes FIVE BARS on the 5-min series — the
    # rule is a re-test-after-a-pause rule and it is being run on 5-min bars.
    # Williams also requires the dominant trend to agree; left to the harness's
    # gate sweep rather than hard-coded here.
    # ══════════════════════════════════════════════════════════════════════
    hh = h.rolling(PCTR_LEN).max()
    ll = l.rolling(PCTR_LEN).min()
    span = (hh - ll).replace(0, np.nan)
    pctr = 100.0 * (hh - c) / span            # 100 = oversold, 0 = overbought

    pos = np.arange(len(idx), dtype=float)
    hit100 = pctr >= PCTR_EXTREME
    hit0 = pctr <= (100.0 - PCTR_EXTREME)
    last100 = pd.Series(np.where(hit100, pos, np.nan), index=idx).ffill()
    last0 = pd.Series(np.where(hit0, pos, np.nan), index=idx).ffill()
    since100 = pd.Series(pos, index=idx) - last100
    since0 = pd.Series(pos, index=idx) - last0

    # "again reaches 95%" is an EVENT, not a state: fire on the bar that re-enters
    # the zone, not on every bar spent inside it.
    # NB: .astype(bool) before `~` — shifting a bool Series yields OBJECT dtype,
    # and `~` on object dtype returns ints (~True == -2, which is truthy), so the
    # negation would silently pass everything through.
    in_lo = (pctr >= PCTR_RETEST).astype(bool)
    in_hi = (pctr <= 100.0 - PCTR_RETEST).astype(bool)
    fresh_lo = ~in_lo.shift(1).fillna(False).astype(bool)
    fresh_hi = ~in_hi.shift(1).fillna(False).astype(bool)
    out["lw_pctr_retest_long"] = (
        _b(in_lo & fresh_lo & (since100 >= PCTR_GAP), idx), +1)
    out["lw_pctr_retest_short"] = (
        _b(in_hi & fresh_hi & (since0 >= PCTR_GAP), idx), -1)

    # ══════════════════════════════════════════════════════════════════════
    # 5. WILLIAMS ACCUMULATION / DISTRIBUTION (WAD) DIVERGENCE   [BAR PORT]
    # Williams, 1970s. TRH = max(prior close, high); TRL = min(prior close, low).
    # AD = close - TRL on an up close, close - TRH on a down close, 0 if
    # unchanged; WAD is the running sum. Price making a new low that WAD does
    # NOT confirm is accumulation.
    # https://www.quantifiedstrategies.com/williams-accumulation-distribution/
    # https://www.marketvolume.com/technicalanalysis/williamsaccumulationdistribution.asp
    # READING: Williams describes the divergence qualitatively. Concrete form
    # used here: price prints a new WAD_LOOK-bar low while WAD is NOT at its own
    # WAD_LOOK-bar low, and the current bar closes up (the turn is underway).
    # WAD is reset each session so the running sum is comparable within the day.
    # ══════════════════════════════════════════════════════════════════════
    trh = pd.concat([h, prev_c], axis=1).max(axis=1)
    trl = pd.concat([l, prev_c], axis=1).min(axis=1)
    ad = pd.Series(
        np.where(c > prev_c, c - trl, np.where(c < prev_c, c - trh, 0.0)),
        index=idx).fillna(0.0)
    wad = ad.groupby(day).cumsum()

    l_lo = l.rolling(WAD_LOOK).min()
    h_hi = h.rolling(WAD_LOOK).max()
    w_lo = wad.rolling(WAD_LOOK).min()
    w_hi = wad.rolling(WAD_LOOK).max()
    intraday = bar_no >= WAD_LOOK             # keeps the window inside one session
    rng0 = (h - l).replace(0, np.nan)
    close_up_half = (c - l) / rng0 >= 0.5
    close_dn_half = (c - l) / rng0 <= 0.5

    out["lw_wad_div_long"] = (
        _b(intraday & (l <= l_lo) & (wad > w_lo) & close_up_half, idx), +1)
    out["lw_wad_div_short"] = (
        _b(intraday & (h >= h_hi) & (wad < w_hi) & close_dn_half, idx), -1)

    # ══════════════════════════════════════════════════════════════════════
    # 6. TRADING DAY OF WEEK (TDW) — SEASONAL BIAS      [DAILY PORT]
    # "Long-Term Secrets to Short-Term Trading". Williams tested day-of-week
    # bias extensively on the S&P and concluded Monday is the best day to buy,
    # that buy signals work on Monday / Tuesday / Friday and should be avoided
    # on Wednesday / Thursday, and offered the variation "buy Monday if Friday
    # closed down".
    # https://www.financialwisdomtv.com/post/larry-williams-trading-strategy-3-key-methods-for-huge-profits
    # https://www.tradingcoachu.com/larry-williams-trading-strategies/
    # READING: the two ideas are combined — a Williams buy-day (Mon/Tue/Fri)
    # following a DOWN prior close, entered on the first bar that closes back
    # above the session open. Only the long side is implemented: Williams says
    # to AVOID buying Wed/Thu, which is not the same as saying to sell them, and
    # inventing a short would be putting words in his mouth.
    # ══════════════════════════════════════════════════════════════════════
    dow = pd.Series(idx.dayofweek, index=idx)
    buy_day = dow.isin([0, 1, 4])             # Mon, Tue, Fri
    prior_down = pdc < pdc2
    out["lw_tdw_buyday"] = (
        _b(buy_day & prior_down & (c > sess_open) & (prev_c <= sess_open)
           & (bar_no >= 1), idx), +1)

    # ══════════════════════════════════════════════════════════════════════
    # 7. HIDDEN SMASH DAY                                [BAR PORT]
    # "Long-Term Secrets to Short-Term Trading". The quiet cousin of the smash
    # day: the bar closes HIGHER than the previous close yet parks its close in
    # the LOWER 25% of its own range (buying is being hidden). The trade only
    # exists on confirmation — the following bar closing above the hidden smash
    # bar's high. Mirror for the sell side.
    # https://www.mql5.com/en/articles/21391
    # ══════════════════════════════════════════════════════════════════════
    rng = (h - l).replace(0, np.nan)
    cpos = (c - l) / rng                      # 0 = close on the low, 1 = on the high
    hid_bull = ((c > prev_c) & (cpos <= HIDDEN_PCT)).fillna(False)
    hid_bear = ((c < prev_c) & (cpos >= 1.0 - HIDDEN_PCT)).fillna(False)

    # READING: on daily bars "the following session" is one shot. On 5-min bars a
    # single 5-min window is too tight, so the setup stays live for HID_LIVE bars
    # and the trade is the first close through the hidden bar's high/low.
    HID_LIVE = 3
    fired_l = pd.Series(False, index=idx)
    fired_s = pd.Series(False, index=idx)
    for k in range(1, HID_LIVE + 1):
        setup_l = hid_bull.shift(k).fillna(False) & (bar_no >= k + 1)
        setup_s = hid_bear.shift(k).fillna(False) & (bar_no >= k + 1)
        # no earlier bar in the window may have already taken the level out
        for j in range(1, k):
            setup_l &= ~(c.shift(k - j) > h.shift(k))
            setup_s &= ~(c.shift(k - j) < l.shift(k))
        fired_l |= setup_l & (c > h.shift(k))
        fired_s |= setup_s & (c < l.shift(k))

    out["lw_hidden_smash_long"] = (_b(fired_l, idx), +1)
    out["lw_hidden_smash_short"] = (_b(fired_s, idx), -1)

    return out
