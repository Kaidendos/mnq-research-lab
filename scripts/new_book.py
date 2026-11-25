"""Do the NEW signals form a book that gets paid faster? Account level, the real test.

`overnight_hunt.py` found seven survivors on ground this project had never looked at.
Four are worth building with:

    ASIA|round100_long        edge +3.95, OOS +8.52 on 560 trades, fires on 3x the
                              Asia session's own median volume, tolerates 16 ticks
                              of slippage before the edge dies
    RTH|overnight_hi_break    edge +2.24, n=2961, OOS +3.03  (break the ONH in RTH)
    RTH|stretch_long          edge +2.36, n=3406, OOS +3.51
    RTH|stretch_short         edge +2.23, n=3311, OOS +3.96

Per-trade edge is not the question — the gold book had four positive signals and still
returned 11.5% payout / 86% bust, because they overlapped and competed. So this asks
the only question that matters: at the account level, with the $175 budget that
survived its own OOS split, does a book of these reach $26,100 FASTER than the
incumbent pair, and at what bust rate?

Three books, identical account rules:
    OLD    sr_round100_break + vol_lw_stretch_short          (the incumbent)
    NEW    the four above
    ALL    both, sharing one account and one day-loss budget
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import account_outlook as AO
import overnight_hunt as OH
import funded_1yr as f1
import funded_search as fs

PV, FEE, TICK = 2.0, 1.22, 0.25
BUDGET = 175.0                    # the OOS-validated size
MAXC, MAXTR = 10, 6
NEW = ["ASIA|round100_long", "RTH|overnight_hi_break",
       "RTH|stretch_long", "RTH|stretch_short"]


def old_days(budget: float) -> dict:
    """Incumbent pair, per-day net P&L, via the existing verified machinery.

    Reusing combined_book.mnq_days rather than re-deriving it: the plug-in registry
    needs the fully-enriched RTH frame (stochK, rsi, bb...) that load_full() does not
    build, and re-implementing the pair here would risk drifting from the version
    every other result in this project was measured with.
    """
    import combined_book as CB
    return CB.mnq_days(budget)


def run_book(d, entries: dict, budget: float) -> dict:
    """Replay a set of signals sharing ONE account. Returns per-day net P&L."""
    c = d["close"].to_numpy(float)
    h = d["high"].to_numpy(float)
    l = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    dates = pd.to_datetime(d["_day"]).dt.strftime("%Y-%m-%d").to_numpy()
    n = len(c)

    fires = {}
    for name, (mask, side) in entries.items():
        for i in np.flatnonzero(mask):
            fires.setdefault(i, []).append(side)

    out, day_tr, busy = {}, {}, -1
    for i in sorted(fires):
        if i <= busy or i + 1 >= n:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        day = dates[i]
        if day_tr.get(day, 0) >= MAXTR:
            continue
        side = fires[i][0]
        nq = min(MAXC, int(budget // (a * OH.SL_ATR * PV)))
        if nq < 1:
            continue
        entry = c[i]
        slp = max(1, round(a * OH.SL_ATR / TICK)) * TICK
        tpp = max(1, round(a * OH.TP_ATR / TICK)) * TICK
        stop, targ = entry - slp * side, entry + tpp * side
        r, xi = None, min(i + OH.MAX_HOLD, n - 1)
        for j in range(i + 1, xi + 1):
            sl = (l[j] <= stop) if side > 0 else (h[j] >= stop)
            tp = (h[j] >= targ) if side > 0 else (l[j] <= targ)
            if sl:
                r, xi = (stop - entry) * side, j; break
            if tp:
                r, xi = (targ - entry) * side, j; break
        if r is None:
            r = (c[xi] - entry) * side
        out[day] = out.get(day, 0.0) + r * PV * nq - FEE * nq
        day_tr[day] = day_tr.get(day, 0) + 1
        busy = xi
    return out


def outcomes(days_map, deadline=21):
    days = [(k, v) for k, v in sorted(days_map.items())]
    fast = dead = late = never = 0
    tt = []
    for s in range(0, max(1, len(days) - 5), 2):
        bal, peak, best, td = 25000.0, 25000.0, 0.0, 0
        got = None
        for k in range(s, min(s + 250, len(days))):
            p = days[k][1]
            bal += p
            if p != 0:
                td += 1
                best = max(best, p)
            floor = min(peak, 26100.0) - 1000.0
            if bal <= floor:
                dead += 1; got = 'd'; break
            peak = max(peak, bal)
            prof = bal - 25000.0
            if prof >= 1100.0 and td >= 3 and best <= 0.40 * prof:
                got = 'f' if (k - s + 1) <= deadline else 'l'
                tt.append(k - s + 1)
                (globals().__setitem__('_x', 0))
                if got == 'f':
                    fast += 1
                else:
                    late += 1
                break
        if got is None:
            never += 1
    n = fast + dead + late + never
    return dict(fast=100.0 * fast / n, late=100.0 * late / n,
                bust=100.0 * dead / n, never=100.0 * never / n,
                med=int(np.median(tt)) if tt else 0,
                paid=100.0 * (fast + late) / n,
                active=sum(1 for _, v in days if v != 0), n=n,
                net=sum(v for _, v in days))


def main() -> None:
    print("loading full session frame ...", flush=True)
    d = OH.load_full()
    sigs = OH.build_signals(d)
    new = {k: sigs[k] for k in NEW}
    print(f"  {len(d):,} bars")
    old_m = old_days(BUDGET)
    new_m = run_book(d, new, BUDGET)
    # combined at DAY level. Caveat: the 6-trade day cap is enforced per book, so the
    # combined arm can take up to 12 in a day. Reported rather than hidden.
    all_m = {k: old_m.get(k, 0.0) + new_m.get(k, 0.0)
             for k in set(old_m) | set(new_m)}

    print("\n" + "=" * 104)
    print(f"BOOK COMPARISON — LucidPro $25K, ${BUDGET:.0f} budget, 5 years")
    print("=" * 104)
    print(f"  {'book':<26}{'days active':>12}{'net $':>10}{'PAID<=21d':>11}"
          f"{'paid later':>12}{'bust%':>8}{'med days':>10}")
    res = {}
    for label, m in (("OLD incumbent pair", old_m),
                     ("NEW 4 signals", new_m),
                     ("ALL six", all_m)):
        r = outcomes(m)
        res[label] = r
        print(f"  {label:<26}{r['active']:>12}{r['net']:>10,.0f}{r['fast']:>11.1f}"
              f"{r['late']:>12.1f}{r['bust']:>8.1f}{r['med']:>10}")

    print("\n  PAID<=21d = payout inside ~1 month, consistency rule enforced.")
    o, nw, a = res["OLD incumbent pair"], res["NEW 4 signals"], res["ALL six"]
    print(f"\n  incumbent -> ALL:  sub-month payout {o['fast']:.1f}% -> {a['fast']:.1f}% "
          f"({a['fast']-o['fast']:+.1f} pts)")
    print(f"                     total paid      {o['paid']:.1f}% -> {a['paid']:.1f}% "
          f"({a['paid']-o['paid']:+.1f} pts)")
    print(f"                     bust            {o['bust']:.1f}% -> {a['bust']:.1f}% "
          f"({a['bust']-o['bust']:+.1f} pts)")
    print(f"                     median days     {o['med']} -> {a['med']}")


if __name__ == "__main__":
    main()
