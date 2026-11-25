"""REAL scalping harness — 1-minute bars, fixed TICK targets, minute time-stops.

Everything else in this project uses 5-minute bars with ATR-multiple brackets.
That is not scalping. A scalp is a fixed, small target taken quickly, and its
economics are dominated by cost rather than by the size of the move:

    MNQ tick = 0.25 pt = $0.50/contract
    fees     = $1.22 round-turn/contract  ->  2.44 ticks of edge burned per trade
    a 4-tick target ($2.00/ct) gives up 61% of gross to fees
    a 8-tick target ($4.00/ct) gives up 31%
    a 16-tick target ($8.00/ct) gives up 15%

So the harness charges fees explicitly and sweeps target/stop in TICKS, plus a
time stop in MINUTES — because a scalp that has not worked in N minutes is wrong,
regardless of where price is.

Account rules are the verified LucidPro 25K set via lucid_fast.
"""
from __future__ import annotations

import argparse
import itertools
import time

import numpy as np
import pandas as pd

import funded_search as fs
import lucid_fast as LF

TICK, PV, FEE = 0.25, 2.0, 1.22
DATA = "data/databento/mnq_2021-2026_1min.csv.gz"


def load_1min(months=None):
    df = pd.read_csv(DATA, parse_dates=["ts_et"])
    df["ts_et"] = pd.to_datetime(df["ts_et"], utc=True).dt.tz_convert("America/New_York")
    d = df.set_index("ts_et").sort_index()
    h = d.index.hour + d.index.minute / 60.0
    d = d[(h >= 9.5) & (h < 16.0)].copy()
    if months:
        d = d[d.index >= d.index[-1] - pd.DateOffset(months=months)]
    c, hi, lo = d["close"], d["high"], d["low"]
    pc = c.shift(1)
    tr = pd.concat([hi - lo, (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    d["eth"] = d.index.hour + d.index.minute / 60.0
    d["_day"] = d.index.normalize()
    day = d["_day"]
    tp_ = (hi + lo + c) / 3.0
    d["vwap"] = (tp_ * d["volume"]).groupby(day).cumsum() / d["volume"].groupby(day).cumsum()
    d["rvol"] = d["volume"] / d["volume"].rolling(30).mean()
    d["ema9"] = c.ewm(span=9, adjust=False).mean()
    d["ema21"] = c.ewm(span=21, adjust=False).mean()
    ret = c.pct_change()
    d["z"] = ret / ret.rolling(30).std().replace(0, np.nan)
    d["sess_hi"] = hi.groupby(day).cummax()
    d["sess_lo"] = lo.groupby(day).cummin()
    return d.dropna(subset=["atr"])


def signals(d):
    """1-minute scalp entries. All causal: current bar + trailing only."""
    o, h, l, c = d["open"], d["high"], d["low"], d["close"]
    pc = c.shift(1)
    rng = (h - l).replace(0, np.nan)
    up, dn = c > o, c < o
    out = {}
    # exhaustion: outsized volume bar closing against itself
    out["s1_vspike_long"] = (d["rvol"] > 3.0) & dn & (c > l + 0.6 * rng)
    out["s1_vspike_short"] = (d["rvol"] > 3.0) & up & (c < h - 0.6 * rng)
    # sigma snapback
    out["s2_sigma_long"] = (d["z"] < -3.0) & (c > l + 0.4 * rng)
    out["s2_sigma_short"] = (d["z"] > 3.0) & (c < h - 0.4 * rng)
    # session-extreme sweep and reclaim
    out["s3_sweep_long"] = (l <= d["sess_lo"]) & (l < l.shift(1)) & (c > l + 0.5 * rng)
    out["s3_sweep_short"] = (h >= d["sess_hi"]) & (h > h.shift(1)) & (c < h - 0.5 * rng)
    # VWAP snap
    dist = (c - d["vwap"]) / d["atr"].replace(0, np.nan)
    out["s4_vwap_long"] = (dist < -2.0) & up & (c > pc)
    out["s4_vwap_short"] = (dist > 2.0) & dn & (c < pc)
    # micro momentum continuation
    tr_up, tr_dn = d["ema9"] > d["ema21"], d["ema9"] < d["ema21"]
    out["s5_micro_long"] = tr_up & dn.shift(1) & up & (c > pc) & (d["rvol"] > 1.2)
    out["s5_micro_short"] = tr_dn & up.shift(1) & dn & (c < pc) & (d["rvol"] > 1.2)
    return {k: v.fillna(False).to_numpy(bool) for k, v in out.items()}


def prep_ticks(d, ent, side, win):
    """Precompute signal bars once (see lucid_fast for why)."""
    eth = d["eth"].to_numpy(float)
    ok = (eth >= win[0]) & (eth <= win[1])
    sig = np.where(ent & ok, side, 0).astype(np.int8)
    dayid = d["_day"].to_numpy()
    starts = np.flatnonzero(np.r_[True, dayid[1:] != dayid[:-1]])
    ends = np.r_[starts[1:], len(d)]
    per = []
    for s, e in zip(starts, ends):
        idxs = np.flatnonzero(sig[s:e]) + s
        per.append((s, e, idxs, sig[idxs] if len(idxs) else np.empty(0, np.int8)))
    return dict(hi=d["high"].to_numpy(float), lo=d["low"].to_numpy(float),
                cl=d["close"].to_numpy(float), eth=eth, per=per,
                dates=d.index[starts])


def run(P, tp_ticks, sl_ticks, tmax, budget, maxc, risk_frac, max_trades=20):
    """Continuous funded account, fixed-tick brackets, minute time stop."""
    hi, lo, cl, eth, per, dates = (P["hi"], P["lo"], P["cl"], P["eth"],
                                   P["per"], P["dates"])
    bal, floor, locked = LF.START, LF.START - LF.MLL, False
    cyc_d = cyc_p = cyc_b = 0.0
    cyc_d = 0
    payouts, withdrawn = 0, 0.0
    tp_pt, sl_pt = tp_ticks * TICK, sl_ticks * TICK
    for k in range(len(per)):
        s, e, idxs, sides = per[k]
        room = bal - floor
        if room <= 0:
            return True, payouts, withdrawn
        day_budget = min(budget, room * risk_frac)
        net, ntr, j = 0.0, 0, 0
        while j < len(idxs) and ntr < max_trades:
            i, sd = idxs[j], int(sides[j])
            risk_ct = sl_pt * PV + FEE
            n = min(maxc, int((day_budget + net) / risk_ct))
            if n < 1:
                break
            entry = cl[i]
            slp, tpp = entry - sd * sl_pt, entry + sd * tp_pt
            px, m = None, i + 1
            while m < e and (m - i) <= tmax:
                if sd > 0:
                    if lo[m] <= slp: px = slp; break
                    if hi[m] >= tpp: px = tpp; break
                else:
                    if hi[m] >= slp: px = slp; break
                    if lo[m] <= tpp: px = tpp; break
                if eth[m] >= 16.0:
                    px = cl[m]; break
                m += 1
            if px is None:
                m = min(m, e - 1)
                px = cl[m]
            net += sd * (px - entry) * PV * n - FEE * n
            ntr += 1
            while j < len(idxs) and idxs[j] <= m:
                j += 1
        if ntr == 0:
            continue
        bal += net
        cyc_d += 1; cyc_p += net; cyc_b = max(cyc_b, net)
        if bal <= floor:
            return True, payouts, withdrawn
        if not locked:
            floor = max(floor, bal - LF.MLL)
            if bal >= LF.BUFFER:
                floor, locked = LF.LOCK_FLOOR, True
        if bal > LF.BUFFER and cyc_d >= LF.MIN_DAYS and cyc_p > 0 \
                and cyc_b <= LF.CONSISTENCY * cyc_p:
            amt = min(bal - LF.BUFFER, LF.CAP_FIRST if payouts == 0 else LF.CAP_AFTER)
            if amt >= 250:
                bal -= amt; withdrawn += amt; payouts += 1
                cyc_d, cyc_p, cyc_b = 0, 0.0, 0.0
    return False, payouts, withdrawn


def evaluate(P, tp_t, sl_t, tmax, budget, maxc, rf, stride=3):
    # stride 6 + a 25-session tail cut left n=14 on a 109-session window, one below
    # the n>=15 gate — every config silently produced nothing. stride 3 / cut 15.
    outs, bust, paid, n = [], 0, 0, 0
    per = P["per"]
    for k in range(0, len(per), stride):
        if len(per) - k < 15:
            continue
        sub = dict(P); sub["per"] = per[k:]; sub["dates"] = P["dates"][k:]
        b, p, w = run(sub, tp_t, sl_t, tmax, budget, maxc, rf)
        outs.append(w); bust += b; paid += p >= 1; n += 1
    if not n:
        return None
    a = np.array(outs)
    zomb = sum(1 for i, w in enumerate(outs) if w == 0) - bust
    return dict(n=n, mean_out=round(float(a.mean())), med_out=round(float(np.median(a))),
                pay_pct=round(100 * paid / n, 1), bust_pct=round(100 * bust / n, 1),
                dead_pct=round(100 * (n - paid) / n, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--months", type=int, default=5)
    ap.add_argument("--out", default="sc1.csv")
    args = ap.parse_args()

    d = load_1min(months=args.months)
    print(f"1-min bars {len(d):,}  {d.index[0]:%Y-%m-%d} -> {d.index[-1]:%Y-%m-%d} "
          f"({d['_day'].nunique()} sessions)", flush=True)
    sigs = signals(d)
    names = sorted(sigs)
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        names = names[i::k]

    TPS = (4, 8, 12, 16, 24)          # ticks
    SLS = (4, 8, 12, 16, 24)
    TMAX = (5, 10, 20, 40)            # minutes
    WINS = ((9.75, 15.5), (10.0, 13.0))
    SIZES = ((300, 5), (300, 10))
    RFS = (0.5, 1.0)

    rows, t0 = [], time.time()
    for nm in names:
        side = 1 if nm.endswith("_long") else -1
        for win in WINS:
            P = prep_ticks(d, sigs[nm], side, win)
            fires = sum(len(x[2]) for x in P["per"])
            if fires < 40:
                continue
            for tp_t, sl_t, tmax, (bud, mc), rf in itertools.product(
                    TPS, SLS, TMAX, SIZES, RFS):
                m = evaluate(P, tp_t, sl_t, tmax, bud, mc, rf)
                if not m or m["n"] < 10:
                    continue
                rows.append(dict(sig=nm, side=side, tp_ticks=tp_t, sl_ticks=sl_t,
                                 tmax_min=tmax, win=f"{win[0]:.2f}-{win[1]:.2f}",
                                 budget=bud, maxc=mc, rf=rf, fires=fires, **m))
        print(f"  {nm} -> {len(rows)} rows, {time.time()-t0:.0f}s", flush=True)
    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"{len(rows):,} scored -> {args.out}")


if __name__ == "__main__":
    main()
