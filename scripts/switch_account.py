"""The ATR switcher at ACCOUNT level. The gate where per-trade edge keeps dying.

    ATR < 44     sr_round100_break + vol_lw_stretch_short   SL 2.0 / TP 3.0
    ATR >= 55    stretch_short_1.5                          SL 1.25 / TP 2.0
    44 - 55      stand aside — never tested, so not traded

The high-ATR arm cleared its per-trade gates: clean control +13.03 beaten 0/20, and it
was STRONGER out-of-sample (edge +6.5, n=89) than in (+5.1, n=39). That is the pattern
nothing else today managed.

None of which has ever predicted account survival. The gold book had four signals with
positive per-trade edge and returned 86% bust. The 4-signal overnight book had the
strongest single signal in the project and returned 61.6% bust. Per-trade edge and
getting paid on a $1,000 trailing limit are different questions, and only the second
one pays.

Sampling: SEQUENTIAL, non-overlapping accounts. Starting one every 2 sessions inflates
the sample ~25x and manufactures precision that is not there — 5 years contains about
23 independent account lifetimes, not 643.

Rules are the verified LucidPro set: MLL $1,000 trailing END-OF-DAY closes, floor locks
permanently at $25,100, payout at $26,100, 5 PROFITABLE days, 40% consistency, no DLL.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import atr_switch as AS
import funded_search as fs
import live_vs_researched as LR
from rr_sweep import load_one_min

PV, FEE, TICK = 2.0, 1.22, 0.25
BUDGET, MAXC, MAXTR = 175.0, 10, 6
LOW_MAX, HIGH_MIN = 44.0, 55.0


def replay(df, one_min, mode: str, budget=BUDGET):
    """mode: 'pair' | 'switch' | 'high_only'."""
    sigs = AS.get_signals(df)
    el, _ = sigs["sr_round100_break"]
    es, _ = sigs["vol_lw_stretch_short"]
    hs, _ = sigs["stretch_short_1.5"]

    t1, h1, l1 = one_min
    c = df["close"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    ts = df.index.values.astype("datetime64[ns]")
    bod = df.groupby("_day").cumcount().to_numpy()
    ids = pd.factorize(df["_day"])[0]
    dates = pd.to_datetime(df["_day"]).dt.strftime("%Y-%m-%d").to_numpy()
    st = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    en = np.r_[st[1:], len(ids)]

    out, n_low, n_high = {}, 0, 0
    for s, e in zip(st, en):
        net, ntr = 0.0, 0
        busy = np.datetime64("1970-01-01", "ns")
        for i in range(s, e):
            if not (2 <= bod[i] <= 18) or ntr >= MAXTR or ts[i] < busy:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue

            side = sl = tp = None
            low_ok = a < LOW_MAX
            high_ok = a >= HIGH_MIN
            if mode in ("pair", "switch") and low_ok:
                if el[i]:
                    side, sl, tp = +1, 2.0, 3.0
                elif es[i]:
                    side, sl, tp = -1, 2.0, 3.0
            if side is None and mode in ("switch", "high_only") and high_ok and hs[i]:
                side, sl, tp = -1, 1.25, 2.0
            # 'pair' mode with no ATR ceiling would still skip on size; keep the
            # ceiling explicit so the two arms differ only by the high-ATR rule
            if side is None:
                continue

            n = min(MAXC, int(budget // (a * sl * PV)))
            if n < 1:
                continue
            entry = c[i]
            slp = max(1, round(a * sl / TICK)) * TICK
            tpp = max(1, round(a * tp / TICK)) * TICK
            s_ns = ts[i] + np.timedelta64(5, "m")
            dl = ts[e - 1] + np.timedelta64(5, "m")
            fn = LR.resolve_exit if side > 0 else LR.resolve_short
            if side > 0:
                px, _, xt = fn(t1, h1, l1, s_ns, entry - slp, entry + tpp, dl, c[e - 1])
            else:
                px, _, xt = fn(t1, h1, l1, s_ns, entry + slp, entry - tpp, dl, c[e - 1])
            net += (px - entry) * side * PV * n - FEE * n
            ntr += 1
            busy = xt
            if sl == 2.0:
                n_low += 1
            else:
                n_high += 1
        out[dates[s]] = out.get(dates[s], 0.0) + net
    return out, n_low, n_high


def accounts(m):
    """Sequential, non-overlapping. Verified LucidPro rules."""
    days = [(k, v) for k, v in sorted(m.items())]
    res, s = [], 0
    while s < len(days) - 5:
        bal = peak = 25000.0
        best, qd = 0.0, 0
        got = None
        for k in range(s, min(s + 250, len(days))):
            p = days[k][1]
            bal += p
            if p > 0:
                qd += 1
            if p != 0:
                best = max(best, p)
            floor = min(peak, 26100.0) - 1000.0
            if bal <= floor:
                got = ("bust", k - s + 1); break
            peak = max(peak, bal)
            pr = bal - 25000.0
            if pr >= 1100.0 and qd >= 5 and best <= 0.40 * pr:
                got = ("paid", k - s + 1); break
        if got is None:
            got = ("never", 250)
        res.append(got)
        s += got[1]
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
    oos = np.asarray(df.index >= AS.OOS)

    print("\n" + "=" * 100)
    print(f"ATR SWITCHER AT ACCOUNT LEVEL — ${BUDGET:.0f} budget, sequential accounts")
    print("=" * 100)
    print(f"  {'arm':<28}{'lowATR tr':>11}{'highATR tr':>12}{'net $':>10}"
          f"{'accts':>7}{'paid%':>8}{'bust%':>8}{'never%':>8}{'med d':>7}")
    store = {}
    for mode, label in (("pair", "pair only (ATR<44)"),
                        ("high_only", "high-ATR arm only"),
                        ("switch", "SWITCHER (both)")):
        m, nl, nh = replay(df, one_min, mode)
        r = accounts(m)
        store[mode] = (m, r)
        print(f"  {label:<28}{nl:>11}{nh:>12}{sum(m.values()):>10,.0f}"
              f"{r['n']:>7}{r['paid']:>8.1f}{r['bust']:>8.1f}"
              f"{r['never']:>8.1f}{r['med']:>7}")

    print("\n" + "=" * 100)
    print("OUT-OF-SAMPLE AT ACCOUNT LEVEL — fit 2021-24 vs test 2025-26")
    print("=" * 100)
    print(f"  {'arm':<28}{'period':<10}{'accts':>7}{'paid%':>8}{'bust%':>8}{'med d':>7}")
    for mode, label in (("pair", "pair only"), ("switch", "SWITCHER")):
        for per, sel in (("FIT", ~oos), ("TEST", oos)):
            sub = df[sel]
            m, _, _ = replay(sub, one_min, mode)
            r = accounts(m)
            print(f"  {label:<28}{per:<10}{r['n']:>7}{r['paid']:>8.1f}"
                  f"{r['bust']:>8.1f}{r['med']:>7}")

    p, sw = store["pair"][1], store["switch"][1]
    print(f"\n  pair -> switcher:  paid {p['paid']:.1f}% -> {sw['paid']:.1f}% "
          f"({sw['paid']-p['paid']:+.1f})   bust {p['bust']:.1f}% -> {sw['bust']:.1f}% "
          f"({sw['bust']-p['bust']:+.1f})   never {p['never']:.1f}% -> {sw['never']:.1f}%"
          f"   med {p['med']} -> {sw['med']} sessions")


if __name__ == "__main__":
    main()
