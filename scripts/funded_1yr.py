"""MNQ payout-speed search, SELECTED ON THE LAST YEAR ONLY (user's instruction).

Honest metrics from the start — the two defects that invalidated the first search
are fixed here, not bolted on afterwards:

  * CALENDAR days, not "active days". A config trading 20% of sessions and showing
    "15 days to payout" really means ~75 calendar days.
  * SEQUENTIAL non-overlapping episodes. A real single funded account starts, runs
    to payout or bust, then restarts. Overlapping starts inflate payout rate ~19x.

Selection window is the last year. The prior four years are reported as a HOLDOUT
purely for information — never used to filter — so you can see whether an edge
existed before the window it was tuned in.

Strategy plug-ins: drop a file in strategies_web/ exposing
    def register(df) -> dict[str, tuple[pd.Series, int]]      # name -> (entry, side)
They are auto-discovered. side = +1 long, -1 short.

Usage:
    python funded_1yr.py list
    python funded_1yr.py sweep --families orb15_long,vwap_reclaim_long --out x.csv
    python funded_1yr.py sweep --plugins-only --out web.csv
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import itertools
import os
from pathlib import Path

import numpy as np
import pandas as pd

import funded_search as fs

DIR = Path(__file__).parent
PLUGIN_DIR = DIR / "strategies_web"

# selection window (last year) and holdout (everything before it)
SEL_START = "2025-08-08"
HOLD_END = "2025-08-08"

CAL_PER_YEAR = 365.0


# ───────────────────────── honest metrics ─────────────────────────
def sequential_episodes(daily: pd.Series):
    """Non-overlapping: start -> payout or bust -> restart next day."""
    vals, idx = daily.values, daily.index
    out, s = [], 0
    while s < len(vals):
        cum = peak = biggest = 0.0
        res = None
        for j in range(s, len(vals)):
            cum += vals[j]
            peak = max(peak, cum)
            biggest = max(biggest, vals[j])
            if peak - cum >= fs.TRAIL_DD:
                res = ("bust", j); break
            if (j - s + 1) >= fs.MIN_DAYS and cum >= fs.BUFFER and biggest <= fs.CONSISTENCY * cum:
                res = ("payout", j); break
        if res is None:
            break
        out.append((res[0], idx[s], idx[res[1]]))
        s = res[1] + 1
    return out


def score(daily: pd.Series, span_days: float) -> dict:
    """The metrics that actually answer 'a payout every 30 calendar days?'"""
    if len(daily) < 8:
        return dict(days=len(daily), net=0.0, eps=0, payouts=0, busts=0,
                    bust_pct=100.0, cal_per_payout=-1, payouts_per_yr=0.0,
                    med_cal=-1)
    eps = sequential_episodes(daily)
    pays = [e for e in eps if e[0] == "payout"]
    busts = [e for e in eps if e[0] == "bust"]
    resolved = len(pays) + len(busts)
    cal = [(e[2] - e[1]).days for e in pays]
    return dict(
        days=len(daily), net=round(float(daily.sum())),
        eps=len(eps), payouts=len(pays), busts=len(busts),
        bust_pct=round(100 * len(busts) / resolved, 1) if resolved else 100.0,
        cal_per_payout=round(span_days / len(pays)) if pays else -1,
        payouts_per_yr=round(CAL_PER_YEAR * len(pays) / span_days, 2) if pays else 0.0,
        med_cal=int(np.median(cal)) if cal else -1,
    )


def bootstrap_payouts(daily: pd.Series, span_days: float, reps: int = 300,
                      block: int = 5, seed: int = 11):
    """Block-bootstrap payouts/yr — one year is a small sample; show the spread."""
    rng = np.random.default_rng(seed)
    v = daily.values
    n = len(v)
    if n < 20:
        return (-1, -1)
    nb = max(1, n // block)
    outs = []
    for _ in range(reps):
        starts = rng.integers(0, max(1, n - block), size=nb)
        samp = np.concatenate([v[s:s + block] for s in starts])[:n]
        s = pd.Series(samp, index=daily.index[:len(samp)])
        eps = sequential_episodes(s)
        outs.append(CAL_PER_YEAR * sum(1 for e in eps if e[0] == "payout") / span_days)
    return (round(float(np.percentile(outs, 5)), 2), round(float(np.percentile(outs, 95)), 2))


# ───────────────────────── plug-ins ─────────────────────────
def load_plugins(df) -> dict:
    sigs = {}
    if not PLUGIN_DIR.exists():
        return sigs
    for f in sorted(glob.glob(str(PLUGIN_DIR / "*.py"))):
        if os.path.basename(f).startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(Path(f).stem, f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            got = mod.register(df)
            for k, v in got.items():
                sigs[k] = v
        except Exception as exc:
            print(f"  !! plugin {Path(f).name} failed: {type(exc).__name__}: {exc}")
    return sigs


# ───────────────────────── sweep ─────────────────────────
SLS = (0.5, 0.75, 1.0, 1.25, 1.5)
TPS = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
WINS = ((9.75, 11.5), (9.75, 15.5), (10.0, 12.0), (13.0, 15.5), (9.75, 12.5))
GATES = (None, "gate_ema50")
SIZES = ((440, 300), (600, 400), (300, 300))


def evaluate(df_sel, df_hold, name, entry_full, side, sl, tp, win, gate, cap, bud,
             span_sel, span_hold, skip_holdout=False):
    """Score on the selection year; report the holdout for information only."""
    row = dict(family=name, sl=sl, tp=tp, win=f"{win[0]}-{win[1]}",
               gate=gate or "-", cap=cap, budget=bud)
    stages = [("sel", df_sel, span_sel)]
    if not skip_holdout:
        stages.append(("hold", df_hold, span_hold))
    for tag, d, span in stages:
        e = entry_full.reindex(d.index).fillna(False)
        daily, ntr, nwin = fs.replay(d, e, side, sl, tp, win, gate, cap, bud)
        m = score(daily, span)
        row[f"{tag}_trades"] = ntr
        row[f"{tag}_win"] = round(100 * nwin / ntr, 1) if ntr else 0.0
        for k in ("net", "payouts", "busts", "bust_pct", "cal_per_payout",
                  "payouts_per_yr", "med_cal", "days"):
            row[f"{tag}_{k}"] = m[k]
        if tag == "sel" and len(daily) >= 20:
            lo, hi = bootstrap_payouts(daily, span)
            row["sel_pyr_lo"], row["sel_pyr_hi"] = lo, hi
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["list", "sweep"])
    ap.add_argument("--families", default=None)
    ap.add_argument("--plugins-only", action="store_true")
    ap.add_argument("--prefix", default=None, help="only families starting with this")
    ap.add_argument("--slice", default=None)
    ap.add_argument("--skip-holdout", action="store_true",
                    help="stage 1: selection year only (~5x faster); add holdout later")
    ap.add_argument("--out", default="onefyr.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    plugins = load_plugins(df)
    builtin = fs.FAMILIES

    if args.mode == "list":
        print("BUILT-IN:"); print("  " + "\n  ".join(builtin))
        print(f"PLUG-IN ({len(plugins)}):"); print("  " + "\n  ".join(plugins) if plugins else "  (none)")
        return

    df_sel = df[df.index >= SEL_START]
    df_hold = df[df.index < HOLD_END]
    span_sel = (df_sel.index[-1] - df_sel.index[0]).days
    span_hold = (df_hold.index[-1] - df_hold.index[0]).days
    print(f"SELECTION : {df_sel.index[0]:%Y-%m-%d} -> {df_sel.index[-1]:%Y-%m-%d} "
          f"({span_sel} cal days, {df_sel['_day'].nunique()} sessions)")
    print(f"HOLDOUT   : {df_hold.index[0]:%Y-%m-%d} -> {df_hold.index[-1]:%Y-%m-%d} "
          f"({span_hold} cal days, {df_hold['_day'].nunique()} sessions)  [info only]")

    names = []
    if args.prefix:
        names = [n for n in (builtin + list(plugins)) if n.startswith(args.prefix)]
    elif args.plugins_only:
        names = list(plugins)
    elif args.families:
        names = args.families.split(",")
    else:
        names = builtin + list(plugins)
    if args.slice:
        i, n = (int(x) for x in args.slice.split("/"))
        names = names[i::n]
    print(f"testing {len(names)} signal families\n")

    rows = []
    for nm in names:
        try:
            entry, side = plugins[nm] if nm in plugins else fs.sig(df, nm)
        except Exception as exc:
            print(f"  !! {nm}: {exc}"); continue
        for sl, tp, win, gate, (cap, bud) in itertools.product(SLS, TPS, WINS, GATES, SIZES):
            if tp < sl * 0.5:
                continue
            rows.append(evaluate(df_sel, df_hold, nm, entry, side, sl, tp, win,
                                 gate, cap, bud, span_sel, span_hold,
                                 skip_holdout=args.skip_holdout))
        print(f"  done {nm}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(DIR / args.out, index=False)

    good = out[(out["sel_net"] > 0) & (out["sel_payouts"] >= 2)].copy()
    good = good.sort_values("sel_cal_per_payout")
    cols = ["family", "sl", "tp", "win", "gate", "cap", "sel_trades", "sel_win",
            "sel_net", "sel_payouts", "sel_busts", "sel_bust_pct",
            "sel_cal_per_payout", "sel_pyr_lo", "sel_pyr_hi",
            "hold_net", "hold_cal_per_payout", "hold_bust_pct"]
    cols = [c for c in cols if c in good.columns]
    pd.set_option("display.width", 250)
    print("\n" + "=" * 118)
    print("RANKED BY CALENDAR DAYS PER PAYOUT — SELECTION YEAR  (goal: <= 30)")
    print("hold_* = prior 4 years, INFORMATION ONLY, not used to filter")
    print("=" * 118)
    print(good[cols].head(30).to_string(index=False) if len(good)
          else "(nothing net-positive with >=2 sequential payouts in the year)")
    hit = good[good["sel_cal_per_payout"] <= 30]
    print(f"\nMEETING THE 30-DAY GOAL: {len(hit)}")
    if len(hit):
        print(hit[cols].to_string(index=False))


if __name__ == "__main__":
    main()
