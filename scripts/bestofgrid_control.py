"""BEST-OF-GRID random control — the decisive multiple-comparisons test.

68,880 configs were searched against ~12 sequential payout episodes in one year.
With that many draws the best-looking survivor is close to guaranteed even if every
signal is worthless. Testing a chosen config against random entries is CIRCULAR,
because that config was selected to maximise the real signal.

The honest test applies the ENTIRE search procedure to random signals:
  for each seed: random entry at the real firing rate -> sweep the same 840-config
  grid -> keep the best-of-grid by the same rule (net>0 in BOTH periods) -> record.
If random seeds routinely produce survivors as good as the real one, the real one
is noise.

Usage:  python bestofgrid_control.py --family sr_round100_break --seeds 0,1,2
"""
from __future__ import annotations

import argparse
import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1


def sweep(df_sel, df_hold, entry, side, span_sel, span_hold):
    """Run the full parameter grid; return survivors (net>0 in both periods)."""
    best = []
    for sl, tp, win, gate, (cap, bud) in itertools.product(
            f1.SLS, f1.TPS, f1.WINS, f1.GATES, f1.SIZES):
        if tp < sl * 0.5:
            continue
        e_s = entry.reindex(df_sel.index).fillna(False)
        ds, _, _ = fs.replay(df_sel, e_s, side, sl, tp, win, gate, cap, bud)
        ms = f1.score(ds, span_sel)
        if ms["net"] <= 0 or ms["payouts"] < 2:
            continue
        e_h = entry.reindex(df_hold.index).fillna(False)
        dh, _, _ = fs.replay(df_hold, e_h, side, sl, tp, win, gate, cap, bud)
        mh = f1.score(dh, span_hold)
        best.append(dict(sl=sl, tp=tp, win=f"{win[0]}-{win[1]}", gate=gate or "-",
                         cap=cap, sel_net=ms["net"], sel_cal=ms["cal_per_payout"],
                         sel_bust=ms["bust_pct"], hold_net=mh["net"],
                         hold_cal=mh["cal_per_payout"], hold_bust=mh["bust_pct"]))
    return pd.DataFrame(best)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="sr_round100_break")
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--out", default="bog.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    plugins = f1.load_plugins(df)
    entry, side = plugins[args.family] if args.family in plugins else fs.sig(df, args.family)
    entry = pd.Series(entry).reindex(df.index).fillna(False)

    df_sel = df[df.index >= f1.SEL_START]
    df_hold = df[df.index < f1.HOLD_END]
    span_sel = (df_sel.index[-1] - df_sel.index[0]).days
    span_hold = (df_hold.index[-1] - df_hold.index[0]).days

    n_fire = int(entry.sum())
    rate = n_fire / len(entry)
    print(f"{args.family}: {n_fire} fires ({100*rate:.2f}% of bars), side={side}",
          flush=True)

    rows = []
    for sd in [int(x) for x in args.seeds.split(",")]:
        if sd < 0:                                   # -1 = the REAL signal
            e, lbl = entry, "REAL"
        else:
            rng = np.random.default_rng(sd)
            e = pd.Series(rng.random(len(df)) < rate, index=df.index)
            lbl = f"rand{sd}"
        res = sweep(df_sel, df_hold, e, side, span_sel, span_hold)
        surv = res[(res.hold_net > 0)] if len(res) else res
        fast = res[(res.sel_cal <= 30)] if len(res) else res
        rows.append(dict(
            label=lbl, grid_net_pos=len(res),
            sel_goal_configs=len(fast),
            holdout_survivors=len(surv),
            best_hold_net=int(surv.hold_net.max()) if len(surv) else 0,
            best_sel_net=int(res.sel_net.max()) if len(res) else 0,
            min_sel_cal=int(res.sel_cal.min()) if len(res) else -1,
        ))
        print(f"  {lbl:<8} net>0 in grid {rows[-1]['grid_net_pos']:>4} | "
              f"<=30d {rows[-1]['sel_goal_configs']:>3} | "
              f"holdout survivors {rows[-1]['holdout_survivors']:>4} | "
              f"best hold_net ${rows[-1]['best_hold_net']:>7,}", flush=True)

    pd.DataFrame(rows).to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
