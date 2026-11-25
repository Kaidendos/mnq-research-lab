"""What does handing the stop to a fixed-tick ATM template COST, at account level?

A NinjaTrader ATM template holds a FIXED stop distance in ticks. The researched stop is
2.0 x ATR. So automating the stop means snapping each trade to the nearest pre-built
template, which perturbs two things at once:

  1. the STOP itself moves a few ticks, changing which trades stop out
  2. the SIZE must move with it. n = floor(175 / (stop_ticks x $0.50)). A snapped-WIDER
     stop that keeps the old contract count silently breaches the $175 budget, and on a
     $1,000 trailing drawdown a silent breach is the whole ballgame. So size is always
     recomputed from the stop actually used.

Per-trade edge has never predicted account survival in this project — the gold book had
four positive-edge signals and busted 86% of accounts. So the answer here is the
account-level one: paid %, bust %, median sessions. Per-trade numbers are printed only
as a sanity check.

FILL RESOLUTION. The RTH pair was measured against 1-MINUTE bars and is replayed that
way. The Asia break was measured on the 24-hour 5-minute series and is replayed that
way. Each arm keeps the resolution it was validated at; mixing them in would change the
baseline and make the comparison meaningless. The bucketed and exact arms use identical
resolution, so the DIFFERENCE is honest even where the absolute level is optimistic.

Accounts are sampled SEQUENTIALLY and NON-OVERLAPPING. 5 years holds ~23 independent
lifetimes, not 600 — overlapping starts inflate n ~25x and invent precision. With n that
small, treat anything under ~10 points of paid% as noise; the bootstrap band is printed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_1yr as f1
import funded_search as fs
import live_vs_researched as LR
import overnight_hunt as OH
from rr_sweep import load_one_min

TICK, PV, FEE = 0.25, 2.0, 1.22
SL_ATR, TP_ATR = 2.0, 3.0
BUDGET, MAXC, MAXTR = 175.0, 10, 6
MAX_HOLD = 24                     # Asia: 24 bars of 5-min = 2h, as measured
START, TRAIL, LOCK, PAYOUT = 25000.0, 1000.0, 25100.0, 1100.0
MIN_PROFIT_DAYS, CONSISTENCY = 5, 0.40


# ── stop policy ────────────────────────────────────────────────────────────────
def exact_ticks(atr: float) -> int:
    return max(1, int(round(atr * SL_ATR / TICK)))


def make_buckets(k: int, lo: int, hi: int) -> np.ndarray:
    """Geometric spacing: a 12-tick miss is severe on an 80-tick stop and trivial on
    a 340-tick one, so equal RATIO steps fit the error that actually matters."""
    return np.unique(np.round(np.geomspace(lo, hi, k)).astype(int))


def snap(t: int, buckets):
    """Nearest template, or None when NO template covers the stop.

    ⚠ The None case is load-bearing and the first version of this file got it wrong.
    A $175 budget cannot take one contract once the stop exceeds 350 ticks
    ($175 / $0.50), so those setups are SKIPS — and skipping is most of why $175
    works (measured: skip+size 78.3% vs skip-only 58.3% vs size-only 53.2%).
    Snapping an over-wide stop DOWN to the largest template turns every one of those
    skips into a live trade at n=1, which silently deletes the mechanism and makes
    bucketing look far worse than it is. Above the top template there is no template,
    so there is no trade."""
    if buckets is None:
        return t
    if t > buckets.max():
        return None
    return int(buckets[np.abs(buckets - t).argmin()])


def size_for(stop_ticks: int, force_qty: int = 0) -> int:
    """Risk-honest sizing: always derived from the stop ACTUALLY used.

    force_qty pins the contract count to a constant — the "never pick a quantity"
    variant. The SKIP is still evaluated first at ONE contract, because a stop the
    budget cannot carry even once is not tradeable no matter what quantity is typed.
    Pinning the size without keeping that skip would be the same mistake as capping
    the stop at the top rung."""
    per = stop_ticks * TICK * PV
    if per <= 0 or BUDGET // per < 1:
        return 0
    return force_qty if force_qty else min(MAXC, int(BUDGET // per))


# ── the two arms ───────────────────────────────────────────────────────────────
def rth_days(df, one_min, buckets, force_qty=0):
    """RTH pair, 09:45-11:00 ET, 1-minute fills, flat at the session close."""
    pl = f1.load_plugins(df)

    def sig(name):
        e, _ = pl[name] if name in pl else fs.sig(df, name)
        return pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)

    el, es = sig("sr_round100_break"), sig("vol_lw_stretch_short")
    t1, h1, l1 = one_min
    c = df["close"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    ts = df.index.values.astype("datetime64[ns]")
    hr = df.index.hour + df.index.minute / 60.0
    win = (hr >= 9.75) & (hr < 11.0)
    ids = pd.factorize(df["_day"])[0]
    dates = pd.to_datetime(df["_day"]).dt.strftime("%Y-%m-%d").to_numpy()
    st = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    en = np.r_[st[1:], len(ids)]

    out, taken, skipped, pts = {}, 0, 0, []
    for s, e in zip(st, en):
        net, ntr = 0.0, 0
        busy = np.datetime64("1970-01-01", "ns")
        for i in range(s, e):
            if not win[i] or ntr >= MAXTR or ts[i] < busy:
                continue
            side = 1 if el[i] else (-1 if es[i] else 0)
            if side == 0:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            stk = snap(exact_ticks(a), buckets)
            n = 0 if stk is None else size_for(stk, force_qty)
            if n < 1:
                skipped += 1
                continue
            # target keeps its 3.0-ATR definition; only the STOP is bucketed, because
            # only the stop is the thing being automated.
            entry = c[i]
            slp = stk * TICK
            tpp = max(1, round(a * TP_ATR / TICK)) * TICK
            s_ns = ts[i] + np.timedelta64(5, "m")
            dl = ts[e - 1] + np.timedelta64(5, "m")
            fn = LR.resolve_exit if side > 0 else LR.resolve_short
            if side > 0:
                px, _, xt = fn(t1, h1, l1, s_ns, entry - slp, entry + tpp, dl, c[e - 1])
            else:
                px, _, xt = fn(t1, h1, l1, s_ns, entry + slp, entry - tpp, dl, c[e - 1])
            r = (px - entry) * side
            net += r * PV * n - FEE * n
            pts.append(r)
            ntr += 1
            taken += 1
            busy = xt
        out[dates[s]] = out.get(dates[s], 0.0) + net
    return out, taken, skipped, pts


def asia_days(d, sigs, buckets, force_qty=0):
    """Asia round-100 break long, 18:00-03:00 ET, 5-min fills, 2h time exit."""
    mask, side = sigs["ASIA|round100_long"]
    c = d["close"].to_numpy(float)
    h = d["high"].to_numpy(float)
    l = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    dates = pd.to_datetime(d["_day"]).dt.strftime("%Y-%m-%d").to_numpy()
    nb = len(c)

    out, taken, skipped, pts = {}, 0, 0, []
    busy, per_day = -1, {}
    for i in np.flatnonzero(mask):
        if i <= busy or i + 1 >= nb:
            continue
        day = dates[i]
        if per_day.get(day, 0) >= MAXTR:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        stk = snap(exact_ticks(a), buckets)
        n = 0 if stk is None else size_for(stk, force_qty)
        if n < 1:
            skipped += 1
            continue
        entry = c[i]
        stop = entry - stk * TICK * side
        targ = entry + max(1, round(a * TP_ATR / TICK)) * TICK * side
        r, xi = None, min(i + MAX_HOLD, nb - 1)
        for j in range(i + 1, xi + 1):
            hit_s = (l[j] <= stop) if side > 0 else (h[j] >= stop)
            hit_t = (h[j] >= targ) if side > 0 else (l[j] <= targ)
            if hit_s:
                r, xi = (stop - entry) * side, j
                break
            if hit_t:
                r, xi = (targ - entry) * side, j
                break
        if r is None:
            r = (c[xi] - entry) * side
        out[day] = out.get(day, 0.0) + r * PV * n - FEE * n
        pts.append(r)
        per_day[day] = per_day.get(day, 0) + 1
        taken += 1
        busy = xi
    return out, taken, skipped, pts


# ── account model: verified LucidPro $25K ──────────────────────────────────────
def accounts(m):
    days = sorted(m.items())
    res, s = [], 0
    while s < len(days) - MIN_PROFIT_DAYS:
        bal = peak = START
        best, qd, got = 0.0, 0, None
        for k in range(s, min(s + 250, len(days))):
            p = days[k][1]
            bal += p
            if p > 0:
                qd += 1
            if p != 0:
                best = max(best, p)
            if bal <= min(peak, START + PAYOUT) - TRAIL:
                got = ("bust", k - s + 1)
                break
            peak = max(peak, bal)
            pr = bal - START
            if pr >= PAYOUT and qd >= MIN_PROFIT_DAYS and best <= CONSISTENCY * pr:
                got = ("paid", k - s + 1)
                break
        res.append(got or ("never", 250))
        s += (got or ("never", 250))[1]
    n = len(res)
    paid = [d for o, d in res if o == "paid"]
    return dict(n=n, paid=100.0 * len(paid) / n,
                bust=100.0 * sum(1 for o, _ in res if o == "bust") / n,
                never=100.0 * sum(1 for o, _ in res if o == "never") / n,
                med=int(np.median(paid)) if paid else 0)


def boot_ci(m, iters=400, seed=0):
    """Resample DAYS to bound how much of any gap is just ~23 accounts of noise."""
    rng = np.random.default_rng(seed)
    days = sorted(m.items())
    vals = np.array([v for _, v in days])
    outs = []
    for _ in range(iters):
        idx = rng.integers(0, len(vals), len(vals))
        outs.append(accounts({f"{j:05d}": vals[i] for j, i in enumerate(idx)})["paid"])
    return float(np.percentile(outs, 5)), float(np.percentile(outs, 95))


def main() -> None:
    print("loading ...", flush=True)
    df = fs.load_enriched()
    one_min = load_one_min()
    d = OH.load_full()
    sigs = OH.build_signals(d)

    # 22 ticks is the smallest stop either arm has ever demanded; 350 is the widest a
    # $175 budget can take at one contract. Anything wider has no template BY DESIGN.
    lad = make_buckets(12, 22, 350)
    modes = [("EXACT ATR stop (baseline)", None, 0)]
    for k in (3, 5, 8, 12, 16):
        modes.append((f"{k:>2} ATM templates", make_buckets(k, 22, 350), 0))
    modes.append(("ONE template @ 200 tk", np.array([200]), 0))
    # The "never pick a quantity" variants: the ladder still chooses the STOP, but the
    # contract count is pinned so there is nothing to type at 2am.
    for q in (1, 2, 3):
        modes.append((f"12 templates, ALWAYS {q} ct", lad, q))

    print("\n" + "=" * 106)
    print("COST OF A FIXED-TICK ATM STOP — pair + Asia, $175, sequential accounts")
    print("=" * 106)
    print(f"  {'stop policy':<28}{'trades':>8}{'skip':>7}{'net $':>11}"
          f"{'accts':>7}{'paid%':>8}{'bust%':>8}{'never%':>8}{'med d':>7}"
          f"{'paid 90% band':>17}")
    base = None
    for label, buckets, fq in modes:
        rm, rt, rs, rp = rth_days(df, one_min, buckets, fq)
        am, at, asx, ap = asia_days(d, sigs, buckets, fq)
        m = dict(rm)
        for k2, v in am.items():
            m[k2] = m.get(k2, 0.0) + v
        r = accounts(m)
        lo, hi = boot_ci(m)
        if base is None:
            base = r
        print(f"  {label:<28}{rt + at:>8}{rs + asx:>7}{sum(m.values()):>11,.0f}"
              f"{r['n']:>7}{r['paid']:>8.1f}{r['bust']:>8.1f}"
              f"{r['never']:>8.1f}{r['med']:>7}{f'{lo:.0f}-{hi:.0f}':>17}")

    print(f"\n  Read every row against the baseline's 90% band. A template set whose")
    print(f"  paid% sits inside that band is indistinguishable from the exact stop at")
    print(f"  this sample size, and is therefore safe to use.")


if __name__ == "__main__":
    main()
