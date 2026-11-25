"""MNQ alone vs GOLD alone vs BOTH — at account level, which one actually gets paid.

The binding constraint on a LucidPro $25K is not per-trade edge, it is reaching
$26,100 before a $1,000 trailing limit catches you. The MNQ pair is +9.77 pts/trade
and still only pays 52.7% of the time, because at ~0.65 trades a session it takes
15-46 trades to get there and three or four consecutive losers ends it.

Two books on uncorrelated instruments roughly double the trade rate without doubling
the drawdown, IF their losing days do not coincide. That is the whole hypothesis and
it is measurable, so this measures it rather than assuming diversification helps.

  MNQ    sr_round100_break + vol_lw_stretch_short, 5-min, 09:45-11:00, SL2/TP3 ATR
  GOLD   the four survivors from gold_research.py, hourly, SL1.5/TP2 ATR, on MGC
         ($10/point — the micro, because GC at $100/point cannot be sized into a
         $300 budget without the stop alone exceeding it)

Common window is set by the gold data: 2024-03 .. 2026-08. MNQ is restricted to match,
so every comparison is over identical calendar days.

BUDGET SPLIT is tested both ways, because it is the real decision:
  FULL    each book sizes to the whole $300 — more edge per day, but a day where both
          lose is -$600 against $1,000 of room
  SPLIT   $150 each — halves the bad-day tail and halves the good-day gain
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import account_outlook as AO
import funded_1yr as f1
import funded_search as fs
import gold_research as GR
import live_vs_researched as LR
import preopen_test as PT
from rr_sweep import load_one_min

MNQ_PV, GOLD_PV = 2.0, 10.0        # MNQ $2/pt, MGC $10/pt
FEE = 1.22
TICK_NQ = 0.25
MAXC, MAXTR = 10, 6
GOLD_SIGS = ["gd_round50_break_short", "gd_asia_break_short",
             "gd_london_break_long", "gd_stretch_long"]


def mnq_days(budget: float) -> dict:
    """Per-day net P&L for the MNQ pair, floor-agnostic (sizing off a fixed budget)."""
    df = fs.load_enriched()
    one_min = load_one_min()
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
    starts = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    ends = np.r_[starts[1:], len(ids)]

    out = {}
    for s, e in zip(starts, ends):
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
            n = min(MAXC, int(budget // (a * 2.0 * MNQ_PV)))
            if n < 1:
                continue
            entry = c[i]
            slp = max(1, round(a * 2.0 / TICK_NQ)) * TICK_NQ
            tpp = max(1, round(a * 3.0 / TICK_NQ)) * TICK_NQ
            s_ns = ts[i] + np.timedelta64(5, "m")
            dl = ts[e - 1] + np.timedelta64(5, "m")
            fn = LR.resolve_exit if side > 0 else LR.resolve_short
            if side > 0:
                px, _, xt = fn(t1, h1, l1, s_ns, entry - slp, entry + tpp, dl, c[e - 1])
            else:
                px, _, xt = fn(t1, h1, l1, s_ns, entry + slp, entry - tpp, dl, c[e - 1])
            net += (px - entry) * side * MNQ_PV * n - FEE * n
            ntr += 1
            busy = xt
        out[dates[s]] = out.get(dates[s], 0.0) + net
    return out


def gold_days(budget: float) -> dict:
    """Per-day net P&L for the four surviving gold signals, sized on MGC."""
    d = GR.enrich(GR.fetch("GC%3DF", "1h", "730d"))
    sigs = GR.signals(d)
    c = d["close"].to_numpy(float)
    h = d["high"].to_numpy(float)
    l = d["low"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    dates = d.index.normalize().strftime("%Y-%m-%d").to_numpy()
    n_bars = len(c)

    fires = {}
    for name in GOLD_SIGS:
        mask, side = sigs[name]
        for i in np.flatnonzero(mask):
            fires.setdefault(i, []).append(side)

    out, busy, day_tr = {}, -1, {}
    for i in sorted(fires):
        if i <= busy or i + 1 >= n_bars:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        side = fires[i][0]
        day = dates[i]
        if day_tr.get(day, 0) >= MAXTR:
            continue
        n = min(MAXC, int(budget // (a * GR.SL_ATR * GOLD_PV)))
        if n < 1:
            continue
        entry = c[i]
        stop = entry - GR.SL_ATR * a * side
        targ = entry + GR.TP_ATR * a * side
        r, exit_i = None, min(i + GR.MAX_HOLD, n_bars - 1)
        for j in range(i + 1, exit_i + 1):
            sl_hit = (l[j] <= stop) if side > 0 else (h[j] >= stop)
            tp_hit = (h[j] >= targ) if side > 0 else (l[j] <= targ)
            if sl_hit:
                r, exit_i = (stop - entry) * side, j; break
            if tp_hit:
                r, exit_i = (targ - entry) * side, j; break
        if r is None:
            r = (c[exit_i] - entry) * side
        out[day] = out.get(day, 0.0) + r * GOLD_PV * n - FEE * n
        day_tr[day] = day_tr.get(day, 0) + 1
        busy = exit_i
    return out


def sim(days_map: dict, label: str) -> dict:
    days = [(d, days_map.get(d, 0.0)) for d in sorted(days_map)]
    res = [AO.simulate(days, i)
           for i in range(0, max(1, len(days) - AO.MIN_DAYS), 2)]
    n = len(res)
    pay = [r for r in res if r["outcome"] == "payout"]
    return dict(label=label, n=n,
                payout=100.0 * len(pay) / n,
                bust=100.0 * sum(1 for r in res if r["outcome"] == "bust") / n,
                med_days=int(np.median([r["days"] for r in pay])) if pay else 0,
                net=sum(v for _, v in days),
                active=sum(1 for _, v in days if v != 0))


def main() -> None:
    print("building MNQ ...", flush=True)
    mnq_full = mnq_days(300.0)
    mnq_half = mnq_days(150.0)
    print("building GOLD ...", flush=True)
    gld_full = gold_days(300.0)
    gld_half = gold_days(150.0)

    # common window is whatever gold covers
    lo, hi = min(gld_full), max(gld_full)
    print(f"  common window {lo} .. {hi}")

    def clip(m):
        return {d: v for d, v in m.items() if lo <= d <= hi}

    mnq_full, mnq_half = clip(mnq_full), clip(mnq_half)
    gld_full, gld_half = clip(gld_full), clip(gld_half)

    all_days = sorted(set(mnq_full) | set(gld_full))
    both_full = {d: mnq_full.get(d, 0.0) + gld_full.get(d, 0.0) for d in all_days}
    both_split = {d: mnq_half.get(d, 0.0) + gld_half.get(d, 0.0) for d in all_days}

    # do their losing days coincide? that is what decides whether this works
    ov = [(mnq_full.get(d, 0.0), gld_full.get(d, 0.0)) for d in all_days
          if mnq_full.get(d, 0.0) != 0 and gld_full.get(d, 0.0) != 0]
    if len(ov) > 10:
        a = np.array([x[0] for x in ov]); b = np.array([x[1] for x in ov])
        corr = float(np.corrcoef(a, b)[0, 1])
        both_red = int(((a < 0) & (b < 0)).sum())
        print(f"  {len(ov)} days both books traded; daily P&L correlation "
              f"{corr:+.3f}; both red on {both_red} ({100.0*both_red/len(ov):.0f}%)")

    print("\n" + "=" * 100)
    print("ACCOUNT OUTCOMES — LucidPro $25K, same calendar days")
    print("=" * 100)
    print(f"  {'book':<34}{'days active':>12}{'net $':>10}{'payout%':>10}"
          f"{'bust%':>8}{'med days':>10}")
    for m, lab in ((mnq_full, "MNQ pair only ($300)"),
                   (gld_full, "GOLD 4-signal book ($300)"),
                   (both_full, "BOTH, each full $300"),
                   (both_split, "BOTH, $150 each")):
        r = sim(m, lab)
        print(f"  {r['label']:<34}{r['active']:>12}{r['net']:>10,.0f}"
              f"{r['payout']:>10.1f}{r['bust']:>8.1f}{r['med_days']:>10}")

    print("\n  med days = median trading days to reach the payout threshold.")
    print("  Fewer days at the same payout rate means less time exposed to the floor.")


if __name__ == "__main__":
    main()
