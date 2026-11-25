"""Same data, same fill model, same account rules: the live bot vs the researched pair.

`rr_sweep.py` established that StochReclaim30 has no edge at ANY bracket — its win
rate tracks its own break-even within +/-1.7 points across 13 combinations, which is
the signature of an entry that carries zero information. So the useful question is no
longer "which bracket" but "is there anything better to run".

This puts both books through ONE harness so the comparison cannot be an artefact of
different fill assumptions, different fee treatment, or different account rules:

  A  StochReclaim30 as deployed   %K(14) reclaim 30 + upper-half close, long only,
                                  09:45-11:35, SL 0.75 / TP 0.50, StopWhenGreen
  B  the researched pair          sr_round100_break (long) + vol_lw_stretch_short,
                                  09:45-11:00, SL 2.0 / TP 3.0

Both: exits resolved on 1-MINUTE bars (stop assumed when a single 1-min bar spans
both levels), $1.22/contract round-turn fees, floor-aware sizing against the LucidPro
$25K rules, 6-trade day cap, flat 16:00.

B's headline from the original research was +12.25 pts/trade against a clean control
with 0/20 shuffled seeds beating it. That was a per-trade edge measurement; this is
the account-level consequence over the same 5 years.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_1yr as f1
import funded_search as fs
from rr_sweep import ONE_MIN, load_one_min, resolve_exit

PV, FEE, TICK = 2.0, 1.22, 0.25
DAY_MAX_TRADES = 6
MAXC = 10
CAP, BUDGET = 440.0, 300.0


def resolve_short(t1, h1, l1, start_ns, stop, target, deadline, fallback):
    """Mirror of resolve_exit for a short: stop ABOVE, target BELOW."""
    i = int(np.searchsorted(t1, start_ns, side="left"))
    n = len(t1)
    while i < n and t1[i] <= deadline:
        hit_sl = h1[i] >= stop
        hit_tp = l1[i] <= target
        if hit_sl and hit_tp:
            return stop, "both-1m", t1[i]
        if hit_sl:
            return stop, "stop", t1[i]
        if hit_tp:
            return target, "target", t1[i]
        i += 1
    return fallback, "flat", deadline


def run(df, one_min, entries_long, entries_short, bod_lo, bod_hi,
        sl_atr, tp_atr, stop_when_green: bool, budget_mode: str) -> dict:
    """One replay. `budget_mode` 'nt' = the bot's day-budget sizing, 'funded' = the
    researched config's fixed cap/budget."""
    t1, h1, l1 = one_min
    h = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    ts = df.index.values.astype("datetime64[ns]")
    yrs = df.index.year.to_numpy()
    bod = df.groupby("_day").cumcount().to_numpy()
    day_ids = pd.factorize(df["_day"])[0]
    starts = np.flatnonzero(np.r_[True, day_ids[1:] != day_ids[:-1]])
    ends = np.r_[starts[1:], len(day_ids)]

    trades = []
    for s, e in zip(starts, ends):
        day_pnl, day_trades, day_won = 0.0, 0, False
        busy = np.datetime64("1970-01-01", "ns")
        for i in range(s, e):
            if not (bod_lo <= bod[i] <= bod_hi):
                continue
            if day_trades >= DAY_MAX_TRADES or day_won:
                continue
            if ts[i] < busy:
                continue
            side = 1 if entries_long[i] else (-1 if entries_short[i] else 0)
            if side == 0:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue

            stop_usd = a * sl_atr * PV
            tp_usd = a * tp_atr * PV
            if budget_mode == "nt":
                n = min(MAXC, int((300.0 + day_pnl) // stop_usd))
                n = min(n, int((440.0 - day_pnl) // tp_usd))
            else:
                n = min(MAXC, int(min(BUDGET, CAP) // stop_usd))
            if n < 1:
                continue

            entry = c[i]
            sl_ticks = max(1, round(a * sl_atr / TICK))
            tp_ticks = max(1, round(a * tp_atr / TICK))
            start_ns = ts[i] + np.timedelta64(5, "m")
            deadline = ts[e - 1] + np.timedelta64(5, "m")
            if side > 0:
                px, why, xt = resolve_exit(
                    t1, h1, l1, start_ns, entry - sl_ticks * TICK,
                    entry + tp_ticks * TICK, deadline, c[e - 1])
            else:
                px, why, xt = resolve_short(
                    t1, h1, l1, start_ns, entry + sl_ticks * TICK,
                    entry - tp_ticks * TICK, deadline, c[e - 1])
            gross = (px - entry) * side * PV * n
            net = gross - FEE * n
            trades.append((yrs[i], net, gross, side, n))
            day_pnl += net
            day_trades += 1
            if stop_when_green and day_pnl > 0:
                day_won = True
            busy = xt

    arr = np.array([t[1] for t in trades])
    grs = np.array([t[2] for t in trades])
    yr = np.array([t[0] for t in trades])
    sides = np.array([t[3] for t in trades])
    return dict(
        n=len(trades), win=100.0 * (grs > 0).mean(),
        breakeven=100.0 * sl_atr / (sl_atr + tp_atr),
        net=arr.sum(), gross=grs.sum(), fees=grs.sum() - arr.sum(),
        per_year={int(y): float(arr[yr == y].sum()) for y in np.unique(yr)},
        avg_ct=float(np.mean([t[4] for t in trades])),
        longs=int((sides > 0).sum()), shorts=int((sides < 0).sum()),
        pts_per_trade=float((grs / (PV * np.array([t[4] for t in trades]))).mean()),
    )


def main() -> None:
    print("loading ...", flush=True)
    df = fs.load_enriched()
    one_min = load_one_min()
    print(f"  {len(df):,} RTH 5-min bars, {len(one_min[0]):,} 1-min bars", flush=True)

    # ── A: the live bot ──
    k = df["stochK"].to_numpy(float)
    kp = np.r_[np.nan, k[:-1]]
    upper = df["close"].to_numpy(float) > (df["high"].to_numpy(float)
                                           + df["low"].to_numpy(float)) / 2.0
    live_long = (kp <= 30.0) & (k > 30.0) & upper & np.isfinite(kp)
    none = np.zeros(len(df), bool)

    # ── B: the researched pair ──
    pl = f1.load_plugins(df)

    def sig(name):
        e, _ = pl[name] if name in pl else fs.sig(df, name)
        return pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)

    res_long = sig("sr_round100_break")
    res_short = sig("vol_lw_stretch_short")

    years = sorted({int(y) for y in df.index.year})
    print("\n" + "=" * 122)
    print("LIVE BOT vs RESEARCHED PAIR — same 5 years, same 1-min fills, same fees")
    print("=" * 122)
    print(f"  {'book':<34}{'trades':>7}{'win%':>7}{'need':>7}{'pts/tr':>8}"
          f"{'gross':>9}{'fees':>8}{'net $':>9}" + "".join(f"{y:>8}" for y in years))

    cfgs = [
        ("A live StochReclaim30 0.75/0.50", live_long, none, 2, 24, 0.75, 0.50,
         True, "nt"),
        ("B researched pair 2.0/3.0", res_long, res_short, 2, 18, 2.0, 3.0,
         False, "funded"),
        ("B' researched, NT day-rules", res_long, res_short, 2, 18, 2.0, 3.0,
         True, "nt"),
    ]
    out = {}
    for (label, el, es, blo, bhi, sl, tp, swg, mode) in cfgs:
        r = run(df, one_min, el, es, blo, bhi, sl, tp, swg, mode)
        out[label] = r
        print(f"  {label:<34}{r['n']:>7}{r['win']:>7.1f}{r['breakeven']:>7.1f}"
              f"{r['pts_per_trade']:>+8.2f}{r['gross']:>9,.0f}{-r['fees']:>8,.0f}"
              f"{r['net']:>9,.0f}"
              + "".join(f"{r['per_year'].get(y, 0):>8,.0f}" for y in years))

    print("\n  pts/tr = average points per contract, before fees. This is the number")
    print("  the original research measured (+12.25 vs +0.39 for a clean control).")

    print("\n" + "=" * 122)
    print("VERDICT")
    print("=" * 122)
    a = out["A live StochReclaim30 0.75/0.50"]
    b = out["B researched pair 2.0/3.0"]
    for label, r in out.items():
        pos = sum(1 for y in years if r["per_year"].get(y, 0) > 0)
        edge = r["win"] - r["breakeven"]
        print(f"  {label:<34} net ${r['net']:>9,.0f}   edge {edge:>+5.1f} pts   "
              f"profitable in {pos}/{len(years)} years")
    print(f"\n  Difference A -> B: ${b['net'] - a['net']:+,.0f} over 5 years "
          f"on the same bars.")
    print(f"  A trades {a['n']} times at {a['pts_per_trade']:+.2f} pts; "
          f"B trades {b['n']} times at {b['pts_per_trade']:+.2f} pts.")
    print(f"  B is {b['longs']} longs / {b['shorts']} shorts; A is long-only.")


if __name__ == "__main__":
    main()
