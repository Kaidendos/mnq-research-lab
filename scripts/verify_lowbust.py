"""Two checks on the low-bust survivors, under the CORRECTED LucidPro rules.

1. MATCHED HORIZON. The sweep used 270 days; the earlier 75-81% bust numbers used
   365. Re-score the top configs at BOTH so the real gain from risk_frac is
   separated from the measurement artifact.

2. BEST-OF-GRID RANDOM CONTROL. 10,368 configs were searched. Testing the chosen
   winner against random is circular. Apply the WHOLE search to random signals
   matched to each side's firing rate and compare best-of-grid to best-of-grid.
"""
from __future__ import annotations

import argparse
import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

TOP = [  # (long, short, sl, tp, win, risk_frac, cushion, cap, maxc)
    ("sr_round100_break", "vol_lw_stretch_short", 2.0, 1.5, (9.75, 15.5), 1.00, 0.0, 440, 10),
    ("sr_round100_break", "vol_lw_stretch_short", 2.0, 3.0, (9.75, 15.5), 1.00, 0.0, 300, 5),
    ("rsi_bounce35_long", "vol_lw_stretch_short", 2.0, 3.0, (9.75, 15.5), 0.50, 0.0, 300, 5),
    ("ema20_50_long", "vol_lw_stretch_short", 1.0, 1.5, (10.0, 13.0), 0.35, 0.0, 300, 5),
    ("ema20_50_long", "vol_lw_stretch_short", 1.0, 1.5, (10.0, 13.0), 0.50, 500.0, 440, 10),
]
SLS, TPS = (1.0, 1.5, 2.0), (1.5, 2.0, 3.0)
RFS, CUS = (0.15, 0.25, 0.35, 0.50, 1.00), (0.0, 500.0, 1000.0)
SIZES = ((300, 300, 5), (440, 300, 10))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["horizon", "control"], default="horizon")
    ap.add_argument("--seeds", default="-1")
    ap.add_argument("--out", default="vlb.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)

    def get(n):
        e, _ = pl[n] if n in pl else fs.sig(df, n)
        return pd.Series(e).reindex(df.index).fillna(False).to_numpy(bool)

    if args.mode == "horizon":
        rows = []
        for ln, sn, sl, tp, win, rf, cu, cap, mc in TOP:
            P = LF.prep(df, get(ln), get(sn), win)
            for h in (180, 270, 365, 545):
                m = LF.evaluate(P, sl, tp, cap, 300, mc, rf, cu, horizon=h, stride=8)
                rows.append(dict(long=ln, short=sn, sl=sl, tp=tp, rf=rf, cushion=cu,
                                 cap=cap, horizon=h, **m))
                print(f"  {ln[:18]}+{sn[:16]} rf={rf} h={h}: bust {m['bust_pct']}% "
                      f"mean ${m['mean_out']} med ${m['med_out']} paid {m['pay_pct']}%",
                      flush=True)
        pd.DataFrame(rows).to_csv(args.out, index=False)
        return

    # ---- best-of-grid control ----
    ln, sn = "sr_round100_break", "vol_lw_stretch_short"
    L, S = get(ln), get(sn)
    rl, rs = L.mean(), S.mean()
    print(f"{ln} {100*rl:.2f}% | {sn} {100*rs:.2f}%", flush=True)
    rows = []
    for sd in [int(x) for x in args.seeds.split(",")]:
        if sd < 0:
            el, es, lbl = L, S, "REAL"
        else:
            g = np.random.default_rng(sd)
            el = (g.random(len(df)) < rl)
            es = (g.random(len(df)) < rs)
            lbl = f"rand{sd}"
        best = []
        for win in ((9.75, 15.5), (10.0, 13.0)):
            P = LF.prep(df, el, es, win)
            for sl, tp, rf, cu, (cap, bud, mc) in itertools.product(
                    SLS, TPS, RFS, CUS, SIZES):
                m = LF.evaluate(P, sl, tp, cap, bud, mc, rf, cu, horizon=270, stride=12)
                if m["n"] < 50:
                    continue
                best.append(m)
        b = pd.DataFrame(best)
        ok = b[(b.bust_pct < 30) & (b.med_out > 0)]
        rows.append(dict(label=lbl, grid=len(b), meets_bar=len(ok),
                         best_mean=int(b.mean_out.max()) if len(b) else 0,
                         best_med=int(b.med_out.max()) if len(b) else 0,
                         best_pay=float(b.pay_pct.max()) if len(b) else 0.0,
                         min_bust=float(b.bust_pct.min()) if len(b) else 100.0))
        print(f"  {lbl:<8} grid {rows[-1]['grid']:>4} | MEETS BAR {rows[-1]['meets_bar']:>4} "
              f"| best mean ${rows[-1]['best_mean']:>6,} | best med ${rows[-1]['best_med']:>6,} "
              f"| best paid {rows[-1]['best_pay']:.1f}%", flush=True)
    pd.DataFrame(rows).to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
