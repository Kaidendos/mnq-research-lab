"""TWO-SIDED strategies: long AND short in one account.

Everything in this project so far has been one signal, one direction. The live
strategy is long-only, which is why it was on the wrong side of the late-July
selloff and why its edge inverted when the tape went flat.

A two-sided system should reduce drawdown — the core problem — because it is not
structurally long. This harness runs a long signal and a short signal in ONE
account, one position at a time, under the same funded rules.

Also supports SIDE-SPECIFIC TREND GATING, which is what makes two-sided coherent:
    gate="split"  -> longs only on days closing above the daily EMA50,
                     shorts only on days closing below it (both no-lookahead).
Otherwise the two signals just fight each other in every regime.
"""
from __future__ import annotations

import argparse
import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1

PV, FEE = 2.0, 1.22


def replay_2s(df, ent_l, ent_s, sl, tp, win, gate, cap, budget,
              stop_green=True, max_trades=6, maxc=10, fee=FEE, slip_ticks=0.0):
    """One account, both directions, one position at a time."""
    hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
    atr, eth = df["atr"].values, df["eth"].values
    el = np.asarray(ent_l, dtype=bool)
    es = np.asarray(ent_s, dtype=bool)
    if gate == "split":                       # side-specific daily trend gate
        up = df["gate_ema50"].values
        el = el & up
        es = es & ~up
    elif gate:
        g = df[gate].values
        el, es = el & g, es & g
    both = el & es                            # contradictory bar -> take neither
    el, es = el & ~both, es & ~both

    dayid = df["_day"].values
    ws, we = win
    starts = np.flatnonzero(np.r_[True, dayid[1:] != dayid[:-1]])
    ends = np.r_[starts[1:], len(df)]

    out, tot, wins, nl, ns = {}, 0, 0, 0, 0
    for s, e in zip(starts, ends):
        net, ntr, day_won, pos = 0.0, 0, False, None
        for i in range(s, e):
            last = i == e - 1
            if pos is not None:
                sd = pos["side"]
                px = None
                if sd > 0:
                    if lo[i] <= pos["sl"]: px = pos["sl"]
                    elif hi[i] >= pos["tp"]: px = pos["tp"]
                else:
                    if hi[i] >= pos["sl"]: px = pos["sl"]
                    elif lo[i] <= pos["tp"]: px = pos["tp"]
                if px is None and (eth[i] >= 16.0 or last):
                    px = cl[i]
                if px is not None:
                    # slippage: pay it on BOTH sides of the round turn
                    slip = slip_ticks * 0.25 * 2.0
                    pnl = sd * (px - pos["entry"]) * PV * pos["n"] \
                        - fee * pos["n"] - slip * PV * pos["n"]
                    net += pnl; ntr += 1; tot += 1
                    if pnl > 0: wins += 1
                    if sd > 0: nl += 1
                    else: ns += 1
                    if stop_green and net > 0: day_won = True
                    pos = None
            if (pos is None and not last and not day_won
                    and ws <= eth[i] <= we and atr[i] > 0 and not np.isnan(atr[i])
                    and ntr < max_trades and (el[i] or es[i])):
                sd = 1 if el[i] else -1
                su, tu = atr[i] * sl * PV, atr[i] * tp * PV
                n = min(maxc, int((budget + net) / su), int((cap - net) / tu))
                if n < 1:
                    continue
                pos = dict(side=sd, entry=cl[i], n=n,
                           sl=cl[i] - sd * atr[i] * sl,
                           tp=cl[i] + sd * atr[i] * tp)
        if ntr > 0:
            out[df.index[s].normalize()] = net
    return pd.Series(out).sort_index(), tot, wins, nl, ns


# Data-driven: the LOWEST-BUST holdout-positive families from rank_sides.py,
# not hand-picked names. Bust rate is the binding constraint, so the pairing
# pool is selected on bust first, net second.
LONGS = ["ema20_50_long", "sr_ib60_break", "sr_pivot_s1_bounce", "so_k21_th30",
         "rsi_bounce35_long", "vwap_trend_pullback_long", "so_combo_deep_rvol",
         "sr_round100_break"]
SHORTS = ["vol_lw_stretch_short", "pdh_fade_short", "mr_rsi2_short",
          "engulf_bb_short", "sc_vsa_upthrust_short", "hv_gapx_fade",
          "so_short_th75", "orb30_short"]
SLS = (0.75, 1.0, 1.25, 1.5)
TPS = (0.5, 1.0, 1.5, 2.0)
WINS = ((9.6667, 11.5), (10.0, 13.0), (9.75, 15.5))
GATES = (None, "split")
SIZES = ((300, 300, 5), (440, 300, 10), (200, 200, 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", default="ls.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    plugins = f1.load_plugins(df)

    def get(nm):
        e, sd = plugins[nm] if nm in plugins else fs.sig(df, nm)
        return pd.Series(e).reindex(df.index).fillna(False)

    L = {n: get(n) for n in LONGS}
    S = {n: get(n) for n in SHORTS}

    end = df.index[-1]
    w5 = end - pd.DateOffset(months=5)
    sel = df[df.index >= w5]
    hold = df[df.index < w5]
    sp_s = (sel.index[-1] - sel.index[0]).days
    sp_h = (hold.index[-1] - hold.index[0]).days
    print(f"SEL {sel.index[0]:%Y-%m-%d}->{sel.index[-1]:%Y-%m-%d} ({sel['_day'].nunique()}d) | "
          f"HOLD {hold['_day'].nunique()}d", flush=True)

    pairs = list(itertools.product(LONGS, SHORTS))
    if args.slice:
        i, n = (int(x) for x in args.slice.split("/"))
        pairs = pairs[i::n]

    rows = []
    for ln, sn in pairs:
        for sl, tp, win, gate, (cap, bud, mc) in itertools.product(
                SLS, TPS, WINS, GATES, SIZES):
            r = dict(long=ln, short=sn, sl=sl, tp=tp, win=f"{win[0]:.2f}-{win[1]:.2f}",
                     gate=gate or "-", cap=cap, maxc=mc)
            for tag, d, sp in (("sel", sel, sp_s), ("hold", hold, sp_h)):
                daily, tt, ww, nl, ns = replay_2s(
                    d, L[ln].reindex(d.index).fillna(False),
                    S[sn].reindex(d.index).fillna(False),
                    sl, tp, win, gate, cap, bud, maxc=mc)
                m = f1.score(daily, sp)
                r[f"{tag}_tr"] = tt
                r[f"{tag}_win"] = round(100 * ww / tt, 1) if tt else 0.0
                r[f"{tag}_nl"] = nl; r[f"{tag}_ns"] = ns
                r[f"{tag}_net"] = m["net"]; r[f"{tag}_pay"] = m["payouts"]
                r[f"{tag}_bust"] = m["bust_pct"]; r[f"{tag}_cal"] = m["cal_per_payout"]
            rows.append(r)
        print(f"  done {ln} + {sn}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)
    print(f"\n{len(out):,} configs -> {args.out}")


if __name__ == "__main__":
    main()
