"""VWAP entry triggers for the MNQ funded harness (category: vwap).

Every rule below is a translation of a published, mechanical VWAP setup.
Sources (one per strategy, recorded in the docstring of each builder):

  [A] footprint-lab.com/guides/vwap-trading/
      "Setup 1: Balance-Day Band Fade", "Setup 2: Trend-Day Pullback",
      "Setup 3: VWAP Reclaim/Rejection Pivot", plus the Anchored-VWAP section
      ("High-Value Anchors: significant swing high or low";
       "Control Rule: price above a rising AVWAP means buyers control").
  [B] crosstrade.io/learn/trading-strategies/vwap-reversion
      2-sigma session-VWAP reversion, ADX(14) 5-min regime filter, skip 09:30-10:00.
  [C] futureshive.com/blog/vwap-trading-strategy-futures-2025
      "Strategy #4: VWAP Mean Reversion from Bands" (2nd/3rd sigma tag + reversal
      candle + entry on first candle closing back toward VWAP).
  [D] snappchart.app/blog/strategy-playbooks/vwap-momentum-trading-strategy
      "Setup 2: The First VWAP Bounce", "Setup 4: The Failed VWAP Reclaim (Short)".

CAUSALITY: every session-scoped quantity is a per-_day cumulative sum / cummax /
cumcount or a per-_day .shift(+n). There is no whole-day .max()/.min()/.last()
anywhere in this file, and no .shift(-n).

The harness owns stops / targets / sizing / exits - these are ENTRY triggers only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── concrete readings of vague source language (documented, not hidden) ──
SLOPE_LOOKBACK = 6          # 6 x 5min = 30 min, the "at least 30-60 minutes" [C] horizon
FLAT_SLOPE_ATR = 0.35       # "flat VWAP" [A] -> |30-min VWAP drift| < 0.35 ATR
STEEP_SLOPE_ATR = 0.60      # "steep VWAP" [A] -> +30-min VWAP drift > 0.60 ATR
ADX_RANGE_MAX = 25.0        # [B] mandatory: fades only when ADX(14) < 25
ADX_TREND_MIN = 20.0        # my reading of [A] "trend day" for the pullback setup
OPEN_SKIP_BARS = 6          # [B] "avoid 09:30-10:00 ET" -> first 6 five-min bars
MIN_SD_ATR = 0.25           # bands are pinched to ~0 at the open [A]; ignore them
                            # until the volume-weighted sigma is a real distance
RUNUP_ATR = 1.00            # [D] Setup 2 "already trending up, well above VWAP"
VOL_LOOKBACK = 20           # "average volume" -> trailing 20-bar mean
VOL_SPIKE = 2.0             # [D] "at least 2x average" (kept for the fade's
                            # exhaustion test, inverted: volume must NOT spike)


# ───────────────────────────── helpers ─────────────────────────────
def _vw_sigma(df: pd.DataFrame) -> pd.Series:
    """Volume-weighted standard deviation of price around the session VWAP.

    Same cumulative construction the harness uses for df["vwap"], so
    vwap +/- k*sigma reproduces the platform "VWAP with St.Dev Bands" [A][C].
    Cumulative -> uses only bars up to and including the current one.
    """
    day = df["_day"]
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    v = df["volume"].astype(float)
    cv = v.groupby(day).cumsum()
    cpv2 = (tp * tp * v).groupby(day).cumsum()
    var = (cpv2 / cv) - df["vwap"] ** 2
    return np.sqrt(var.clip(lower=0.0))


def _avwap_prior_session_high(df: pd.DataFrame) -> pd.Series:
    """Anchored VWAP whose anchor is the PRIOR session's highest bar [A].

    The anchor bar is fully in the past (it is fixed once yesterday closed), so
    the running average is causal at every bar. NaN on the first session.
    """
    n = len(df)
    pos = pd.Series(np.arange(n), index=df.index)
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    v = df["volume"].astype(float)
    cpv = (tp * v).cumsum().to_numpy()
    cv = v.cumsum().to_numpy()

    hi_bar_ts = df.groupby("_day")["high"].idxmax()            # day -> timestamp
    hi_bar_pos = pd.Series(pos.reindex(hi_bar_ts).to_numpy(),
                           index=hi_bar_ts.index)              # day -> position
    anchor_by_day = hi_bar_pos.shift(1)                         # yesterday's high bar
    a = df["_day"].map(anchor_by_day).to_numpy(dtype=float)

    ok = ~np.isnan(a)
    ai = np.where(ok, a, 0.0).astype(np.int64)
    prev = np.maximum(ai - 1, 0)
    base_pv = np.where(ai > 0, cpv[prev], 0.0)
    base_v = np.where(ai > 0, cv[prev], 0.0)
    num = cpv - base_pv
    den = cv - base_v
    good = ok & (den > 0)
    out = np.where(good, num / np.where(den > 0, den, 1.0), np.nan)
    return pd.Series(out, index=df.index)


def _b(s: pd.Series, index) -> pd.Series:
    """Coerce to a clean boolean Series aligned to the frame."""
    return s.reindex(index).fillna(False).astype(bool)


# ───────────────────────────── register ─────────────────────────────
def register(df: pd.DataFrame) -> dict:
    day = df["_day"]
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    vwap, atr, adx, vol = df["vwap"], df["atr"], df["adx"], df["volume"].astype(float)

    sess_i = df.groupby(day).cumcount()                 # 0-based bar # in session
    late_open = sess_i >= OPEN_SKIP_BARS                # [B] skip 09:30-10:00

    sd = _vw_sigma(df)
    band1_up = vwap + sd
    band2_up, band2_dn = vwap + 2.0 * sd, vwap - 2.0 * sd
    sd_real = sd >= MIN_SD_ATR * atr                    # bands wide enough to mean anything

    # per-session shifts (never reach back into yesterday)
    g = df.groupby(day)
    p_c = g["close"].shift(1)
    p_l = g["low"].shift(1)
    p_vwap = g["vwap"].shift(1)

    slope = vwap - g["vwap"].shift(SLOPE_LOOKBACK)       # 30-min VWAP drift
    flat_vwap = slope.abs() < FLAT_SLOPE_ATR * atr
    steep_up = slope > STEEP_SLOPE_ATR * atr
    falling = slope < 0

    up_bar = c > (h + l) / 2.0
    dn_bar = c < (h + l) / 2.0
    vol_ma = vol.rolling(VOL_LOOKBACK).mean()
    vol_fading = vol < vol_ma                            # [D] "volume fading"
    no_vol_surge = vol < VOL_SPIKE * vol_ma              # [C] exhaustion, not conviction

    # "price crossed VWAP 2+ times" balance-day test [A] Setup 1 - cumulative,
    # counted per session, current bar's own cross included (known at its close).
    above = c > vwap
    prev_above = above.groupby(day).shift(1)
    # first bar of a session has no predecessor and must NOT count as a cross,
    # otherwise every session starts with a free cross and the ">=2" test is really ">=1".
    has_prev = prev_above.notna()
    crossed = has_prev & (above != prev_above.fillna(False).astype(bool))
    cross_count = crossed.astype(int).groupby(day).cumsum()
    balance_day = cross_count >= 2

    out: dict[str, tuple[pd.Series, int]] = {}

    # 1 ── Balance-day fade of the upper 2-sigma band  [A] Setup 1 / [B] / [C] #4
    #      Tag of +2 sigma, close back inside it, bearish bar, flat VWAP, ADX<25,
    #      rotational session (>=2 VWAP crosses), no volume surge.
    out["vwap_band2_fade_short"] = (
        _b(late_open & sd_real
           & (h >= band2_up) & (c < band2_up)
           & dn_bar & flat_vwap & balance_day
           & (adx < ADX_RANGE_MAX) & no_vol_surge, df.index),
        -1,
    )

    # 2 ── Mirror: balance-day fade of the lower 2-sigma band  [A]/[B]/[C]
    out["vwap_band2_fade_long"] = (
        _b(late_open & sd_real
           & (l <= band2_dn) & (c > band2_dn)
           & up_bar & flat_vwap & balance_day
           & (adx < ADX_RANGE_MAX) & no_vol_surge, df.index),
        +1,
    )

    # 3 ── First VWAP bounce of the session  [D] Setup 2
    #      Uptrend (EMA9>EMA20, VWAP rising), price ran >=1 ATR above VWAP earlier,
    #      then the FIRST PULLBACK into VWAP produces a green bar that wicks below
    #      the line and closes back above it.
    #      "first pullback ... not the second, third, or fourth" [D] is counted as
    #      contiguous touch EPISODES, not individual bars: a pullback usually spends
    #      2-4 bars at the line and it is a later bar of that same pullback that
    #      prints the green reclaim, so per-bar counting would discard the setup.
    #      The episode counter is a per-session cumsum -> causal.
    #      Bars 0-5 are excluded from the touch test: on bar 0 the VWAP equals that
    #      bar's typical price, so low<=vwap is trivially true and would burn episode 1.
    ran_above = (c - vwap).groupby(day).cummax()
    had_runup = ran_above.groupby(day).shift(1) >= RUNUP_ATR * atr
    touch = (l <= vwap) & late_open
    # NB: groupby().shift() yields object dtype; cast before "~" or bitwise-not
    # runs on Python bools (~False == -1, truthy) and every bar looks like a new episode.
    prev_touch = touch.groupby(day).shift(1).fillna(False).astype(bool)
    new_episode = touch & ~prev_touch
    episode = new_episode.astype(int).groupby(day).cumsum()
    #      "Already trending up, well above VWAP" [D] is encoded by had_runup (>=1 ATR
    #      above VWAP earlier this session) plus [D]'s universal filter "rising VWAP
    #      means look long only" (slope>0). No EMA test is added on top: [D] names no
    #      moving average, and stacking one merely re-states the same trend condition.
    out["vwap_first_touch_long"] = (
        _b(touch & (episode == 1) & had_runup
           & (c > vwap) & (c > o) & (slope > 0), df.index),
        +1,
    )

    # 4 ── Failed VWAP reclaim, short  [D] Setup 4
    #      Downtrend (VWAP falling, EMA9<EMA20), price already below VWAP, relief
    #      rally wicks THROUGH VWAP and closes back below it on fading volume.
    out["vwap_failed_reclaim_short"] = (
        _b(late_open & (p_c < p_vwap)
           & (h >= vwap) & (c < vwap) & dn_bar
           & falling & (df["ema9"] < df["ema20"]) & vol_fading, df.index),
        -1,
    )

    # 5 ── Trend-day pullback that holds the +1-sigma band  [A] Setup 2
    #      Steep rising VWAP, price on the upper side, the prior bar pulled back into
    #      the +1 sigma band, and this bar makes a HIGHER LOW and closes back above it.
    out["vwap_trend_pullback_long"] = (
        _b(late_open & sd_real & steep_up & (c > vwap)
           & (p_l <= band1_up) & (c > band1_up)
           & (c > p_c) & (l >= p_l)
           & (adx > ADX_TREND_MIN), df.index),
        +1,
    )

    # 6 ── Reclaim of the anchored VWAP from the prior session's high  [A] AVWAP
    #      "Price above a rising AVWAP means buyers control": cross from below to
    #      above, on an up bar, with the AVWAP itself not falling.
    avwap = _avwap_prior_session_high(df)
    p_av = avwap.groupby(day).shift(1)
    av_rising = avwap >= avwap.groupby(day).shift(SLOPE_LOOKBACK)
    out["vwap_avwap_pdhigh_reclaim_long"] = (
        _b((sess_i >= 3) & (p_c < p_av) & (c >= avwap)
           & up_bar & av_rising & (c > vwap), df.index),
        +1,
    )

    return out
