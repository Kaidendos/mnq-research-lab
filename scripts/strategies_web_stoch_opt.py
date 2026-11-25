"""Structural optimisation variants of the user's live strategy (StochReclaim30).

Baseline being improved on:
    raw %K(14) crosses UP through 30, on a bar closing in its upper half, long only.

The harness already sweeps SL/TP/entry-window/gate/sizing, so these variants change
the SIGNAL itself: the oscillator's period and threshold, what confirms the reclaim,
what regime it is allowed to fire in, and the short mirror the live strategy lacks.

CAUSALITY: every quantity is current-bar or trailing. Rolling windows use only past
bars; session features use cumsum/cummax; no whole-day aggregates. Verified by
lookahead_audit.py (prefix-stability at two mid-session cut points).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _rawk(df, n):
    """Raw (unsmoothed) %K over n bars — matches the live NinjaTrader port."""
    ll = df["low"].rolling(n).min()
    hh = df["high"].rolling(n).max()
    rng = (hh - ll).replace(0, np.nan)
    return 100.0 * (df["close"] - ll) / rng


def _rvol(df, n=20):
    return df["volume"] / df["volume"].rolling(n).mean()


def _b(s, idx):
    return s.reindex(idx).fillna(False).astype(bool)


def register(df: pd.DataFrame) -> dict:
    idx = df.index
    c, o, h, l = df["close"], df["open"], df["high"], df["low"]
    atr, adx, rsi, vwap = df["atr"], df["adx"], df["rsi"], df["vwap"]
    ema20, ema50 = df["ema20"], df["ema50"]
    rvol = _rvol(df)
    upper_half = c > (h + l) / 2.0
    lower_half = c < (h + l) / 2.0
    bull, bear = c > o, c < o
    atr_pct = atr.rolling(250).rank(pct=True)          # trailing vol percentile
    vwap_dist = (c - vwap) / atr.replace(0, np.nan)

    K = {n: _rawk(df, n) for n in (7, 9, 14, 21)}
    out = {}

    def cross_up(n, th):
        k = K[n]
        return (k.shift(1) <= th) & (k > th)

    def cross_dn(n, th):
        k = K[n]
        return (k.shift(1) >= th) & (k < th)

    # ── 1. period x threshold grid, baseline confirmation (upper-half close) ──
    for n in (7, 9, 14, 21):
        for th in (20, 25, 30, 35):
            out[f"so_k{n}_th{th}"] = (_b(cross_up(n, th) & upper_half, idx), +1)

    # ── 2. confirmation variants on the live 14/30 core ──
    base = cross_up(14, 30)
    out["so_nofilter"]      = (_b(base, idx), +1)                      # drop the flow filter
    out["so_bullbar"]       = (_b(base & bull, idx), +1)               # bullish body instead
    out["so_prevdown"]      = (_b(base & upper_half & bear.shift(1), idx), +1)  # true reversal
    out["so_rvol"]          = (_b(base & upper_half & (rvol > 1.0), idx), +1)   # volume confirms
    out["so_rvol15"]        = (_b(base & upper_half & (rvol > 1.5), idx), +1)
    out["so_deep"]          = (_b((K[14].shift(1) <= 15) & (K[14] > 30) & upper_half, idx), +1)
    out["so_persist3"]      = (_b(base & upper_half
                                  & (K[14].shift(2) <= 30) & (K[14].shift(3) <= 30), idx), +1)
    out["so_rsi_confirm"]   = (_b(base & upper_half & (rsi < 45), idx), +1)
    out["so_body_atr"]      = (_b(base & upper_half & ((c - o).abs() > 0.3 * atr), idx), +1)

    # ── 3. regime gates (the live strategy has none) ──
    out["so_chop_adx20"]    = (_b(base & upper_half & (adx < 20), idx), +1)
    out["so_trend_adx25"]   = (_b(base & upper_half & (adx > 25), idx), +1)
    out["so_above_vwap"]    = (_b(base & upper_half & (c > vwap), idx), +1)
    out["so_below_vwap"]    = (_b(base & upper_half & (c < vwap), idx), +1)
    out["so_stretch_vwap"]  = (_b(base & upper_half & (vwap_dist < -1.0), idx), +1)
    out["so_above_ema50"]   = (_b(base & upper_half & (c > ema50), idx), +1)
    out["so_above_ema20"]   = (_b(base & upper_half & (c > ema20), idx), +1)
    out["so_lowvol"]        = (_b(base & upper_half & (atr_pct < 0.5), idx), +1)
    out["so_highvol"]       = (_b(base & upper_half & (atr_pct > 0.5), idx), +1)

    # ── 4. the SHORT mirror the live strategy is missing ──
    for th in (65, 70, 75, 80):
        out[f"so_short_th{th}"] = (_b(cross_dn(14, th) & lower_half, idx), -1)
    out["so_short_belowvwap"] = (_b(cross_dn(14, 70) & lower_half & (c < vwap), idx), -1)
    out["so_short_belowema50"] = (_b(cross_dn(14, 70) & lower_half & (c < ema50), idx), -1)

    # ── 5. best-guess stacked combinations ──
    out["so_combo_chop_vwap"] = (_b(base & upper_half & (adx < 20) & (c < vwap), idx), +1)
    out["so_combo_deep_rvol"] = (_b((K[14].shift(1) <= 20) & (K[14] > 30) & upper_half
                                    & (rvol > 1.0), idx), +1)
    out["so_combo_k9_ema50"]  = (_b(cross_up(9, 25) & upper_half & (c > ema50), idx), +1)
    out["so_combo_full"]      = (_b(base & upper_half & bull & (rvol > 1.0)
                                    & (adx < 25), idx), +1)
    return out
