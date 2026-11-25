"""Switch STRATEGY by ATR regime, rather than standing aside in high volatility.

Regime has been tested here as a FILTER (rejected — no predictive information) but
never as a SWITCHER. Those are different claims. "Volatility does not tell you whether
today is good" can be true at the same time as "volatility tells you which RULE to use".

Two things must both hold before a switcher is worth building:

  1. something must have EDGE in the high-ATR regime specifically
  2. it must be SIZEABLE there. At ATR 70 a 2.0-ATR stop costs $280/contract, which a
     $175 budget cannot take at all — so any high-ATR rule needs a tighter multiple:
     SL <= 1.25 ATR, or it is unsizeable no matter how good the signal is.

So this sweeps every signal x every bracket, SPLIT BY ATR TERCILE, and asks where the
edge actually lives. If nothing clears its own break-even in the top tercile, there is
nothing to switch TO and the answer is that standing aside is correct.

Break-even for a bracket is SL/(SL+TP) — printed alongside, because a tighter stop
raises the bar it has to clear and that trade-off is the whole question.

Clean control on the winner, then an OOS split. 19 candidates have died today; this
one gets the same treatment.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_1yr as f1
import funded_search as fs
import live_vs_researched as LR
import overnight_hunt as OH
from rr_sweep import load_one_min

PV, FEE, TICK = 2.0, 1.22, 0.25
BUDGET, MAXC = 175.0, 10
OOS = pd.Timestamp("2025-01-01", tz=fs.TZ)
BRACKETS = [(2.0, 3.0), (1.5, 2.5), (1.25, 2.0), (1.0, 2.0), (1.0, 1.5), (0.75, 1.5)]


def get_signals(df):
    """The pair plus the overnight survivors, all on the RTH-enriched frame."""
    pl = f1.load_plugins(df)

    def sig(name):
        e, _ = pl[name] if name in pl else fs.sig(df, name)
        return pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)

    c, o = df["close"], df["open"]
    atr = df["atr"]
    day = df["_day"]
    bod = df.groupby(day).cumcount()
    sess_open = df.groupby(day)["open"].transform("first")
    ext = (c - sess_open) / atr.replace(0, np.nan)

    out = {
        "sr_round100_break": (sig("sr_round100_break"), +1),
        "vol_lw_stretch_short": (sig("vol_lw_stretch_short"), -1),
        "stretch_long_1.5": (((ext >= 1.5) & (c > o) & (bod > 3))
                             .fillna(False).to_numpy(bool), +1),
        "stretch_short_1.5": (((ext <= -1.5) & (c < o) & (bod > 3))
                              .fillna(False).to_numpy(bool), -1),
    }
    return out


def bt(df, one_min, mask, side, sl, tp, regime=None):
    """Backtest one signal/bracket, optionally restricted to an ATR regime mask."""
    t1, h1, l1 = one_min
    c = df["close"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    ts = df.index.values.astype("datetime64[ns]")
    bod = df.groupby("_day").cumcount().to_numpy()
    ids = pd.factorize(df["_day"])[0]
    st = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    en = np.r_[st[1:], len(ids)]

    pts, wins, sized = [], 0, 0
    for s, e in zip(st, en):
        busy = np.datetime64("1970-01-01", "ns")
        ntr = 0
        for i in range(s, e):
            if not (2 <= bod[i] <= 18) or ntr >= 6 or ts[i] < busy or not mask[i]:
                continue
            if regime is not None and not regime[i]:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            n = min(MAXC, int(BUDGET // (a * sl * PV)))
            if n < 1:
                continue
            sized += 1
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
            r = (px - entry) * side
            pts.append(r)
            wins += r > 0
            ntr += 1
            busy = xt
    if not pts:
        return None
    arr = np.array(pts)
    return dict(n=len(arr), win=100.0 * wins / len(arr), ppt=float(arr.mean()),
                be=100.0 * sl / (sl + tp), total=float(arr.sum()))


def main() -> None:
    print("loading ...", flush=True)
    df = fs.load_enriched()
    one_min = load_one_min()
    sigs = get_signals(df)

    atr = df["atr"].to_numpy(float)
    lo_t, hi_t = np.nanpercentile(atr, 33), np.nanpercentile(atr, 67)
    regimes = {
        f"LOW  (<{lo_t:.0f})": atr < lo_t,
        f"MID  ({lo_t:.0f}-{hi_t:.0f})": (atr >= lo_t) & (atr < hi_t),
        f"HIGH (>{hi_t:.0f})": atr >= hi_t,
    }
    print(f"  ATR terciles: <{lo_t:.1f} / {lo_t:.1f}-{hi_t:.1f} / >{hi_t:.1f}")
    print(f"  current regime is HIGH (recent median ~73)\n")

    print("=" * 112)
    print("WHERE DOES EDGE LIVE? every signal x bracket, split by ATR regime")
    print("=" * 112)
    best_high = []
    for name, (mask, side) in sigs.items():
        print(f"\n  ### {name}")
        print(f"    {'bracket':<12}{'need':>7}" +
              "".join(f"{k:>26}" for k in regimes))
        for sl, tp in BRACKETS:
            be = 100.0 * sl / (sl + tp)
            cells = []
            for rname, rmask in regimes.items():
                r = bt(df, one_min, mask, side, sl, tp, rmask)
                if not r or r["n"] < 25:
                    cells.append(f"{'—':>26}")
                    continue
                edge = r["win"] - r["be"]
                cells.append(f"{r['n']:>6} {r['win']:>5.1f}% {edge:>+5.1f} "
                             f"{r['ppt']:>+6.2f}")
                if rname.startswith("HIGH") and edge > 0 and r["ppt"] > 0:
                    best_high.append((name, sl, tp, r, edge))
            print(f"    SL{sl}/TP{tp:<6}{be:>6.1f}%" + "".join(cells))

    print("\n" + "=" * 112)
    print("CANDIDATES FOR THE HIGH-ATR ARM (positive edge AND positive points)")
    print("=" * 112)
    if not best_high:
        print("  NONE. Nothing clears its own break-even in the top ATR tercile at any")
        print("  bracket tested. There is nothing to switch TO — standing aside in high")
        print("  volatility is not a gap in the plan, it IS the plan.")
        return
    for name, sl, tp, r, edge in sorted(best_high, key=lambda x: -x[4]):
        print(f"  {name:<24} SL{sl}/TP{tp}  n={r['n']:>4}  win {r['win']:.1f}% vs "
              f"need {r['be']:.1f}%  edge {edge:+.1f}  {r['ppt']:+.2f} pts  "
              f"total {r['total']:+,.0f}")

    print("\n  Next gate for any of these: clean control, then an OOS split.")
    print("  19 candidates have died today, most of them at exactly that step.")


if __name__ == "__main__":
    main()
