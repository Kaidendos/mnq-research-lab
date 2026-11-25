"""Best-of-grid random control for the TWO-SIDED pairing.

18,432 configs were searched. Testing the chosen winner against random is circular
— it was selected to maximise the real signals. The honest test runs the ENTIRE
search on random signals matched to each side's firing rate, keeps the best-of-grid
by the same rule, and repeats across seeds.

Kill criterion: if random seeds routinely produce pairings with comparable holdout
bust / payout counts / net, the real pairing is a selection artifact.
"""
from __future__ import annotations

import argparse
import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
from funded_longshort import replay_2s, SLS, TPS, WINS, GATES, SIZES

LONG, SHORT = "sr_round100_break", "vol_lw_stretch_short"


def sweep(sel, hold, el, es, sp_s, sp_h):
    best = []
    for sl, tp, win, gate, (cap, bud, mc) in itertools.product(
            SLS, TPS, WINS, GATES, SIZES):
        ds, tt, ww, nl, ns = replay_2s(sel, el.reindex(sel.index).fillna(False),
                                       es.reindex(sel.index).fillna(False),
                                       sl, tp, win, gate, cap, bud, maxc=mc)
        ms = f1.score(ds, sp_s)
        if ms["net"] <= 0:
            continue
        dh, tt2, ww2, nl2, ns2 = replay_2s(hold, el.reindex(hold.index).fillna(False),
                                           es.reindex(hold.index).fillna(False),
                                           sl, tp, win, gate, cap, bud, maxc=mc)
        mh = f1.score(dh, sp_h)
        best.append(dict(sel_net=ms["net"], sel_bust=ms["bust_pct"],
                         hold_net=mh["net"], hold_bust=mh["bust_pct"],
                         hold_pay=mh["payouts"], hold_cal=mh["cal_per_payout"]))
    return pd.DataFrame(best)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="-1")
    ap.add_argument("--out", default="bogls.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    plugins = f1.load_plugins(df)

    def get(n):
        e, s = plugins[n] if n in plugins else fs.sig(df, n)
        return pd.Series(e).reindex(df.index).fillna(False)

    L, S = get(LONG), get(SHORT)
    rl, rs = L.mean(), S.mean()
    end = df.index[-1]
    w5 = end - pd.DateOffset(months=5)
    sel, hold = df[df.index >= w5], df[df.index < w5]
    sp_s = (sel.index[-1] - sel.index[0]).days
    sp_h = (hold.index[-1] - hold.index[0]).days
    print(f"{LONG} {100*rl:.2f}%  |  {SHORT} {100*rs:.2f}%", flush=True)

    rows = []
    for sd in [int(x) for x in args.seeds.split(",")]:
        if sd < 0:
            el, es, lbl = L, S, "REAL"
        else:
            g = np.random.default_rng(sd)
            el = pd.Series(g.random(len(df)) < rl, index=df.index)
            es = pd.Series(g.random(len(df)) < rs, index=df.index)
            lbl = f"rand{sd}"
        r = sweep(sel, hold, el, es, sp_s, sp_h)
        good = r[(r.hold_net > 0) & (r.hold_pay >= 8)] if len(r) else r
        tgt = good[(good.hold_bust <= 46) & (good.hold_cal <= 40)] if len(good) else good
        rows.append(dict(label=lbl, grid_selpos=len(r),
                         hold_ok=len(good),
                         meets_bar=len(tgt),
                         best_hold_net=int(good.hold_net.max()) if len(good) else 0,
                         max_hold_pay=int(good.hold_pay.max()) if len(good) else 0,
                         min_hold_bust=float(good.hold_bust.min()) if len(good) else 100.0))
        print(f"  {lbl:<8} selpos {rows[-1]['grid_selpos']:>4} | hold_ok {rows[-1]['hold_ok']:>4} "
              f"| MEETS BAR {rows[-1]['meets_bar']:>3} | best net ${rows[-1]['best_hold_net']:>7,} "
              f"| max pay {rows[-1]['max_hold_pay']:>3} | min bust {rows[-1]['min_hold_bust']:.1f}%",
              flush=True)
    pd.DataFrame(rows).to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
