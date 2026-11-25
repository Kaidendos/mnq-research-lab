"""SCALPING entries — fast, high-frequency setups for MNQ.

Nothing else in this project tests holds shorter than the 5-min ATR bracket.
Scalping is a different animal and the economics are brutal: fees are $1.22
round-turn per contract, so a 5-point MNQ target ($10/ct) gives up 12% to costs
before slippage. A scalp entry has to be far more accurate than a swing entry to
survive that, which is exactly what makes it worth testing separately.

These are ENTRIES only — the harness applies brackets, sizing and account rules.
Designed to pair with tight fixed-tick targets and short time stops.

CAUSALITY: current-bar and trailing quantities only; session features use
cumsum/cummax/expanding; audited by lookahead_audit.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _b(s, idx):
    return s.reindex(idx).fillna(False).astype(bool)


def register(df: pd.DataFrame) -> dict:
    idx = df.index
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    pc = c.shift(1)
    atr, vwap, eth = df["atr"], df["vwap"], df["eth"]
    day = df["_day"]
    rng = (h - l).replace(0, np.nan)
    body = (c - o).abs()
    rvol = v / v.rolling(20).mean()
    up_bar, dn_bar = c > o, c < o

    # tick-scale features
    ret1 = c.pct_change()
    vol20 = ret1.rolling(20).std()
    z = ret1 / vol20.replace(0, np.nan)                 # per-bar move in sigma
    # running session extremes, causal (cummax/cummin include the current bar only)
    sess_hi = h.groupby(day).cummax()
    sess_lo = l.groupby(day).cummin()
    # micro pullback depth inside a short trend
    ema5 = c.ewm(span=5, adjust=False).mean()
    ema13 = c.ewm(span=13, adjust=False).mean()
    up_trend, dn_trend = ema5 > ema13, ema5 < ema13

    out = {}

    # ── 1. Volume-spike reversion. An outsized-volume bar that closes against
    # its own direction is often absorption; fade the exhaustion.
    out["scalp_vspike_fade_long"] = (
        _b((rvol > 2.5) & dn_bar & (c > l + 0.6 * rng), idx), +1)
    out["scalp_vspike_fade_short"] = (
        _b((rvol > 2.5) & up_bar & (c < h - 0.6 * rng), idx), -1)

    # ── 2. Sigma-extreme snapback. A single bar >2.5 sigma is a liquidity event;
    # the immediate next move tends to retrace part of it.
    out["scalp_sigma_snap_long"] = (_b((z < -2.5) & (c > l + 0.4 * rng), idx), +1)
    out["scalp_sigma_snap_short"] = (_b((z > 2.5) & (c < h - 0.4 * rng), idx), -1)

    # ── 3. Micro-pullback continuation. In a short-term trend, enter on the first
    # bar that reclaims after a 1-bar counter move — a classic scalp continuation.
    out["scalp_micro_pull_long"] = (
        _b(up_trend & dn_bar.shift(1) & up_bar & (c > pc) & (l > sess_lo), idx), +1)
    out["scalp_micro_pull_short"] = (
        _b(dn_trend & up_bar.shift(1) & dn_bar & (c < pc) & (h < sess_hi), idx), -1)

    # ── 4. Session-extreme sweep-and-reclaim. Price makes a new session extreme
    # then closes back inside — a stop run, faded.
    new_hi = (h >= sess_hi) & (h > h.shift(1))
    new_lo = (l <= sess_lo) & (l < l.shift(1))
    out["scalp_sweep_hi_short"] = (
        _b(new_hi & (c < h - 0.5 * rng) & (eth > 10.0), idx), -1)
    out["scalp_sweep_lo_long"] = (
        _b(new_lo & (c > l + 0.5 * rng) & (eth > 10.0), idx), +1)

    # ── 5. VWAP snap. A stretched move away from VWAP that turns back toward it.
    dist = (c - vwap) / atr.replace(0, np.nan)
    out["scalp_vwap_snap_long"] = (
        _b((dist < -1.5) & up_bar & (c > pc), idx), +1)
    out["scalp_vwap_snap_short"] = (
        _b((dist > 1.5) & dn_bar & (c < pc), idx), -1)

    # ── 6. Compression break. Three consecutive narrow bars then an expansion
    # bar — the classic coil-and-go, sized for a quick target.
    narrow = rng < rng.rolling(20).mean() * 0.6
    coil = narrow & narrow.shift(1) & narrow.shift(2)
    out["scalp_coil_break_long"] = (
        _b(coil.shift(1) & up_bar & (body > 0.8 * rng) & (rvol > 1.2), idx), +1)
    out["scalp_coil_break_short"] = (
        _b(coil.shift(1) & dn_bar & (body > 0.8 * rng) & (rvol > 1.2), idx), -1)

    return out
