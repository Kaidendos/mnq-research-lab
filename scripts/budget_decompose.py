"""WHY does the $175 budget work? Two mechanisms are tangled and they imply opposite tweaks.

A $175 budget does two things at once:

  (a) SIZE   fewer contracts on the trades it does take
  (b) SKIP   declines any setup where one contract already exceeds the budget.
             At $175 with a 2.0-ATR stop that is ATR > 43.75 — which in 2026 is
             84% of in-window signals, and 98% of the last six weeks.

Those imply opposite fixes for the current high-volatility regime:

  if SKIP is doing the work  -> keep the filter, it is a volatility gate and the
                                config is *correctly* standing aside right now
  if SIZE is doing the work  -> scale the budget with ATR so it keeps trading

So this decomposes them. The decisive arm is "SMALL, NEVER SKIP": a $175-equivalent
size that always takes at least one contract. If that performs like $300, the skip was
the mechanism. If it performs like $175, size was.

Everything else held identical: same signals, same window, same 1-minute fill
resolution, same fees, same verified LucidPro rules (5 profitable days, 40%
consistency, floor locking at $25,100).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_1yr as f1
import funded_search as fs
import live_vs_researched as LR
from rr_sweep import load_one_min

PV, FEE, TICK = 2.0, 1.22, 0.25
SL_ATR, TP_ATR = 2.0, 3.0
MAXC, MAXTR = 10, 6
ATR_CAP_175 = 175.0 / (SL_ATR * PV)      # 43.75 — the ATR the $175 budget implies


def replay(df, one_min, budget, atr_cap=None, min_one=False, force_ct=None):
    """One arm.

    budget    dollars of risk per trade
    atr_cap   skip the setup when ATR exceeds this (None = no explicit cap)
    min_one   always take at least 1 contract, i.e. never skip for size
    force_ct  hard contract count, overriding the budget
    """
    pl = f1.load_plugins(df)

    def sig(name):
        e, _ = pl[name] if name in pl else fs.sig(df, name)
        return pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)

    el, es = sig("sr_round100_break"), sig("vol_lw_stretch_short")
    t1, h1, l1 = one_min
    c = df["close"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    ts = df.index.values.astype("datetime64[ns]")
    bod = df.groupby("_day").cumcount().to_numpy()
    ids = pd.factorize(df["_day"])[0]
    dates = pd.to_datetime(df["_day"]).dt.strftime("%Y-%m-%d").to_numpy()
    st = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    en = np.r_[st[1:], len(ids)]

    out, taken, skipped = {}, 0, 0
    for s, e in zip(st, en):
        net, ntr = 0.0, 0
        busy = np.datetime64("1970-01-01", "ns")
        for i in range(s, e):
            if not (2 <= bod[i] <= 18) or ntr >= MAXTR or ts[i] < busy:
                continue
            side = 1 if el[i] else (-1 if es[i] else 0)
            if side == 0:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            if atr_cap is not None and a > atr_cap:
                skipped += 1
                continue
            if force_ct is not None:
                n = force_ct
            else:
                n = min(MAXC, int(budget // (a * SL_ATR * PV)))
                if n < 1:
                    if min_one:
                        n = 1
                    else:
                        skipped += 1
                        continue
            entry = c[i]
            slp = max(1, round(a * SL_ATR / TICK)) * TICK
            tpp = max(1, round(a * TP_ATR / TICK)) * TICK
            s_ns = ts[i] + np.timedelta64(5, "m")
            dl = ts[e - 1] + np.timedelta64(5, "m")
            fn = LR.resolve_exit if side > 0 else LR.resolve_short
            if side > 0:
                px, _, xt = fn(t1, h1, l1, s_ns, entry - slp, entry + tpp, dl, c[e - 1])
            else:
                px, _, xt = fn(t1, h1, l1, s_ns, entry + slp, entry - tpp, dl, c[e - 1])
            net += (px - entry) * side * PV * n - FEE * n
            ntr += 1
            taken += 1
            busy = xt
        out[dates[s]] = out.get(dates[s], 0.0) + net
    return out, taken, skipped


def account(m):
    """Verified LucidPro rules. Sequential, NON-overlapping accounts only —
    overlapping starts inflate the sample 25x and manufacture false precision."""
    days = [(k, v) for k, v in sorted(m.items())]
    res, s = [], 0
    while s < len(days) - 5:
        bal = peak = 25000.0
        best, qd = 0.0, 0
        out = None
        for k in range(s, min(s + 250, len(days))):
            p = days[k][1]
            bal += p
            if p > 0:
                qd += 1
            if p != 0:
                best = max(best, p)
            floor = min(peak, 26100.0) - 1000.0
            if bal <= floor:
                out = ("bust", k - s + 1); break
            peak = max(peak, bal)
            pr = bal - 25000.0
            if pr >= 1100.0 and qd >= 5 and best <= 0.40 * pr:
                out = ("paid", k - s + 1); break
        if out is None:
            out = ("never", 250)
        res.append(out)
        s += out[1]
    n = len(res)
    paid = [d for o, d in res if o == "paid"]
    return dict(n=n, paid=100.0 * len(paid) / n,
                bust=100.0 * sum(1 for o, _ in res if o == "bust") / n,
                never=100.0 * sum(1 for o, _ in res if o == "never") / n,
                med=int(np.median(paid)) if paid else 0)


def main() -> None:
    print("loading ...", flush=True)
    df = fs.load_enriched()
    one_min = load_one_min()
    print(f"  ATR cap implied by a $175 budget: {ATR_CAP_175:.2f} points\n")

    arms = [
        ("$300 flat (the old default)",      dict(budget=300.0)),
        ("$175 flat (current pick)",         dict(budget=175.0)),
        ("SKIP only: $300 + ATR<=43.75",     dict(budget=300.0, atr_cap=ATR_CAP_175)),
        ("SIZE only: $175, NEVER skip",      dict(budget=175.0, min_one=True)),
        ("SIZE only: always exactly 1 ct",   dict(budget=175.0, force_ct=1)),
        ("BOTH, harder: $175 + ATR<=35",     dict(budget=175.0, atr_cap=35.0)),
    ]
    print("=" * 104)
    print("DECOMPOSING THE $175 EFFECT — sequential accounts, verified LucidPro rules")
    print("=" * 104)
    print(f"  {'arm':<34}{'taken':>7}{'skipped':>9}{'net $':>10}"
          f"{'accts':>7}{'paid%':>8}{'bust%':>8}{'never%':>8}{'med d':>7}")
    for label, kw in arms:
        m, taken, skipped = replay(df, one_min, **kw)
        r = account(m)
        print(f"  {label:<34}{taken:>7}{skipped:>9}{sum(m.values()):>10,.0f}"
              f"{r['n']:>7}{r['paid']:>8.1f}{r['bust']:>8.1f}"
              f"{r['never']:>8.1f}{r['med']:>7}")

    print("\n  Read the two 'SIZE only' rows against '$175 flat'. If they hold up,")
    print("  size is the mechanism and the budget can be scaled to volatility.")
    print("  If they collapse toward '$300 flat', the SKIP was doing the work and")
    print("  standing aside in high-ATR regimes is the strategy, not a bug.")


if __name__ == "__main__":
    main()
