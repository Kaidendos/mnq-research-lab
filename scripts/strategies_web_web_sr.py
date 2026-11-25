"""Support/resistance & levels entries for MNQ 5-min RTH bars.

Category: floor-trader pivots, Camarilla pivots, prior-day high/low sweeps,
round numbers, initial balance (Market Profile).

Sources (documented, mechanical rule sets):
  * Classic floor-trader pivots + "pivot point bounce" / "pivot point breakout"
      https://www.tradingsim.com/blog/pivot-points
  * Camarilla equation (H1..H5 / L1..L5) + "buy at L3, target H3", stop beyond L4
      https://pivotboss.com/2010/05/31/the-camarilla-equation-explained/
  * Initial Balance = first 60 min of RTH; breakout & failed-breakout fade,
    RVOL filter, narrow-IB-favors-breakout / wide-IB-favors-fade
      https://steady-turtle.com/knowledge/initial-balance-trading-strategy
      https://marketprofile.info/articles/initial-balance-breakout-strategy
  * Round / psychological numbers ("70% of S/R end at 00, 95% at 00 or 50")
      https://atas.net/market-theory/the-magic-of-round-numbers/
  * Prior-day high/low liquidity sweep + reclaim, confirmed by acceptance back
    through the level
      https://ninjatrader.com/futures/blogs/how-to-trade-liquidity-traps-in-futures/
      https://dailypriceaction.com/blog/liquidity-sweep-reversals/

NOTE ON OVERNIGHT LEVELS: the harness hands us RTH-only bars (09:30-16:00), so a
true overnight high/low is not derivable here. Prior-day RTH high/low (df.pdh /
df.pdl) and prior-day-derived pivots stand in for that part of the category.

CAUSALITY: every session-scoped quantity below is built from cumsum / cummax /
cummin / ffill or from a .shift(1)-ed daily aggregate. Nothing reads a bar that
has not closed. Cross-day shift(1) artifacts are suppressed with `same_day`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── tunables (named, not magic) ──────────────────────────────────────────────
IB_END_ETH = 10.5          # Initial Balance = 09:30-10:30 ET (bars are open-labelled)
IB_REF_DAYS = 20           # trailing sessions used for "is today's IB narrow/wide"
IB_REF_MIN = 5
ROUND_STEP = 100.0         # NQ/MNQ trades ~10k-31k; the "00" grid is 100 points
BREAK_BUF_ATR = 0.15       # decisive close beyond a level, in ATR units
WICK_FRAC = 0.35           # upper wick >= this share of bar range == rejection bar
SWEEP_MAX_ACCEPT = 3       # bars closed beyond the level today -> still a sweep ("1-3 candles")
VOL_LOOKBACK = 20          # bars in the RVOL baseline (RVOL = bar volume / this mean)


def _bool(s: pd.Series, idx: pd.Index) -> pd.Series:
    """Coerce a comparison result to a clean bool Series on df.index."""
    out = s.reindex(idx)
    if out.dtype != bool:
        out = out.fillna(False).astype(bool)
    return out


def _levels(df: pd.DataFrame) -> dict:
    """Prior-session-derived levels + causal session-scoped Initial Balance."""
    g = df["_day"]
    h, l, c = df["high"], df["low"], df["close"]

    # prior-session close (pdh / pdl are already correctly shifted by the harness)
    pdc = g.map(c.groupby(g).last().shift(1))
    pdh, pdl = df["pdh"], df["pdl"]
    prng = pdh - pdl

    # classic floor-trader pivots  (tradingsim)
    p = (pdh + pdl + pdc) / 3.0
    s1 = 2.0 * p - pdh

    # Camarilla equation  (pivotboss).  Only the 3rd (reversal) and 4th
    # (breakout/invalidation) layers are used; the source notes layers 1-2 are
    # "typically ignored".
    l3, l4 = pdc - prng * 1.1 / 4.0, pdc - prng * 1.1 / 2.0

    # Initial Balance, built causally: running extreme inside the window,
    # then forward-filled. Never a whole-day .max()/.transform("last").
    in_ib = df["eth"] < IB_END_ETH
    ib_hi = h.where(in_ib).groupby(g).cummax().groupby(g).ffill()
    ib_lo = l.where(in_ib).groupby(g).cummin().groupby(g).ffill()
    ib_w = ib_hi - ib_lo

    # today's finished IB width vs the mean of the PRIOR IB_REF_DAYS sessions
    ibw_day = ib_w.groupby(g).last()
    ib_ref = g.map(ibw_day.shift(1).rolling(IB_REF_DAYS, min_periods=IB_REF_MIN).mean())

    return dict(s1=s1, l3=l3, l4=l4, pdh=pdh,
                ib_hi=ib_hi, ib_w=ib_w, ib_ref=ib_ref,
                ib_ready=df["eth"] >= IB_END_ETH,
                same_day=g == g.shift(1))


def register(df: pd.DataFrame) -> dict:
    idx = df.index
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    pc, ph, pl = c.shift(1), h.shift(1), l.shift(1)
    atr = df["atr"]
    g = df["_day"]
    L = _levels(df)
    same = L["same_day"]
    bull = c > o
    rng = (h - l).replace(0, np.nan)

    # RVOL against a trailing VOL_LOOKBACK-bar mean. A trailing window is the
    # right baseline here: intraday volume decays sharply after the open, so
    # comparing a late-morning bar against opening-hour volume would reject
    # essentially every breakout regardless of how strong it was.
    vol_ref = v.rolling(VOL_LOOKBACK).mean()
    rvol_hi, rvol_lo = v > vol_ref, v <= vol_ref

    out: dict[str, tuple[pd.Series, int]] = {}

    # ── 1. Floor-trader pivot bounce at S1 (long) ────────────────────────────
    # tradingsim "Pivot Point Bounce": price tests a pivot line from above and
    # bounces off it. Concrete reading: the bar pierces/touches S1 (low <= S1)
    # but closes back above it, the previous bar was still above S1 (so this is
    # a fresh test from above, not price already living underneath), and the bar
    # itself is bullish.
    out["sr_pivot_s1_bounce"] = (
        _bool(same & (l <= L["s1"]) & (c > L["s1"]) & (pc > L["s1"]) & bull, idx), +1)

    # ── 2. Camarilla L3 reversal (long) ──────────────────────────────────────
    # pivotboss: "Buy at L3, Target at H3", stop beyond L4 — i.e. the trade is
    # only valid while price is still inside the L4 boundary. Concrete reading:
    # bar reaches L3 (low <= L3), closes back above it, close is still above L4
    # (thesis not invalidated), previous bar was above L3, bullish bar.
    out["sr_cam_l3_rev"] = (
        _bool(same & (l <= L["l3"]) & (c > L["l3"]) & (c > L["l4"])
              & (pc > L["l3"]) & bull, idx), +1)

    # ── 3. Initial Balance breakout (long) ───────────────────────────────────
    # steady-turtle / marketprofile.info: IB = 09:30-10:30 RTH high/low; enter on
    # "a close outside the IB range on a bar with a visibly larger body and volume
    # than the last several inside-range bars", skipping the break if RVOL < 1.0;
    # narrow-IB days favour breakouts. Concrete reading of "narrowest tercile":
    # today's IB width below the mean of the prior 20 sessions' IB widths.
    out["sr_ib60_break"] = (
        _bool(same & L["ib_ready"] & (c > L["ib_hi"]) & (pc <= L["ib_hi"])
              & bull & rvol_hi & (L["ib_w"] < L["ib_ref"]), idx), +1)

    # ── 4. Initial Balance failed-breakout fade at the IB high (short) ───────
    # steady-turtle: "a rejection candle at the IB extreme, a long wick, doji or
    # pin bar on weak volume, with the close back inside the range"; wide IB days
    # favour fades. Concrete reading: high pokes above the IB high, close back
    # inside, upper wick >= WICK_FRAC of the bar range ("long wick"), RVOL <= 1
    # ("weak volume"), today's IB width above the prior-20-session mean ("wide").
    upper_wick = h - np.maximum(c, o)
    out["sr_ib60_fade"] = (
        _bool(same & L["ib_ready"] & (h > L["ib_hi"]) & (c < L["ib_hi"])
              & (upper_wick >= WICK_FRAC * rng) & rvol_lo
              & (L["ib_w"] > L["ib_ref"]), idx), -1)

    # ── 5. Round-number ("00") breakout (long) ───────────────────────────────
    # atas.net: >70% of S/R levels end in 00. Concrete reading: an upward cross of
    # the 100-point grid — the bar closes above a multiple of 100 that the prior
    # close was below — confirmed by a decisive 0.15*ATR close beyond that level,
    # a bullish body, and above-average (20-bar) volume.
    lvl = np.floor(c / ROUND_STEP)
    cross_up = lvl > np.floor(pc / ROUND_STEP)
    out["sr_round100_break"] = (
        _bool(same & cross_up & (c >= lvl * ROUND_STEP + BREAK_BUF_ATR * atr)
              & bull & rvol_hi, idx), +1)

    # ── 6. Prior-day-high liquidity sweep + reclaim (short) ──────────────────
    # NinjaTrader / dailypriceaction: price wicks through the prior-day high to
    # take stops, then trades back through it; entry on the confirmation bar that
    # accepts below the low of the sweep bar. Concrete reading: previous bar's
    # high > PDH with its close back below PDH (the sweep), current bar closes
    # below that sweep bar's low and below PDH, and price has closed above PDH on
    # at most SWEEP_MAX_ACCEPT bars so far today (cumsum -> causal), matching the
    # source's "usually lasting only 1-3 candles before snapping back" — i.e. a
    # sweep rather than genuine acceptance above the level.
    accept = (c > L["pdh"]).astype(int).groupby(g).cumsum()
    out["sr_pdh_sweep"] = (
        _bool(same & (ph > L["pdh"]) & (pc < L["pdh"]) & (c < pl) & (c < L["pdh"])
              & (accept <= SWEEP_MAX_ACCEPT), idx), -1)

    return out
