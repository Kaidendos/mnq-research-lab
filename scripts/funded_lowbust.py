"""SURVIVAL-FIRST search: minimise BUST RATE, then take whatever cadence follows.

Every previous sweep ranked by speed and reported bust as a footnote. The user's
constraint is the opposite: a 59% bust rate is unacceptable at any speed.

Two levers never swept before:
  * SIZE, downward. Earlier grids bottomed out at cap 300 / budget 300 / 10 contracts.
    Position size is the direct control on drawdown, so this goes down to cap 100 /
    budget 100 / 2 contracts.
  * REGIME-INFORMED WINDOWS. The last 3 months invert the historical clock: the
    14:00 hour runs -0.2661 ATR (vs +0.1170 historically) and the 09:00 open is
    negative, while 10:00-13:00 is stronger than usual. Windows here concentrate
    on that morning band instead of spanning the bad hours.

Reports three periods so nothing is judged on the fitted window alone:
    RECENT  last 3 months   (what the user asked to bend toward)
    SEL     last year
    HOLD    the prior 4 years
"""
from __future__ import annotations

import argparse
import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1

# ── survival-first grids ──
SLS = (0.75, 1.0, 1.25, 1.5, 2.0)
TPS = (0.75, 1.0, 1.5, 2.0, 3.0)
# regime-informed: concentrate on 10:00-13:00, avoid the 14:00 hour and the open
WINS = ((10.0, 13.0), (10.0, 12.0), (10.0, 11.5), (11.0, 13.0),
        (10.0, 13.5), (9.75, 12.5), (9.75, 15.5))
GATES = (None, "gate_ema50")
# cap / budget / max-contracts — the lever that was never pushed down
SIZES = ((100, 100, 2), (150, 150, 3), (200, 200, 3), (200, 150, 4),
         (250, 250, 4), (300, 200, 5), (300, 300, 5), (440, 300, 10))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="so_")
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", default="lb.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    plugins = f1.load_plugins(df)
    names = [n for n in (fs.FAMILIES + list(plugins)) if n.startswith(args.prefix)]
    if args.slice:
        i, n = (int(x) for x in args.slice.split("/"))
        names = names[i::n]

    end = df.index[-1]
    w3 = end - pd.Timedelta(days=90)
    periods = {
        "rec": df[df.index >= w3],
        "sel": df[df.index >= f1.SEL_START],
        "hold": df[df.index < f1.HOLD_END],
    }
    spans = {k: (v.index[-1] - v.index[0]).days for k, v in periods.items()}
    print(f"testing {len(names)} families | "
          + " | ".join(f"{k} {v['_day'].nunique()}d" for k, v in periods.items()), flush=True)

    rows = []
    for nm in names:
        entry, side = plugins[nm] if nm in plugins else fs.sig(df, nm)
        entry = pd.Series(entry).reindex(df.index).fillna(False)
        for sl, tp, win, gate, (cap, bud, mc) in itertools.product(
                SLS, TPS, WINS, GATES, SIZES):
            if tp < sl * 0.5:
                continue
            r = dict(family=nm, sl=sl, tp=tp, win=f"{win[0]}-{win[1]}",
                     gate=gate or "-", cap=cap, budget=bud, maxc=mc)
            for tag, d in periods.items():
                e = entry.reindex(d.index).fillna(False)
                daily, ntr, nwin = fs.replay(d, e, side, sl, tp, win, gate, cap, bud,
                                             maxc=mc)
                m = f1.score(daily, spans[tag])
                r[f"{tag}_net"] = m["net"]
                r[f"{tag}_pay"] = m["payouts"]
                r[f"{tag}_bust"] = m["bust_pct"]
                r[f"{tag}_cal"] = m["cal_per_payout"]
                r[f"{tag}_tr"] = ntr
                r[f"{tag}_win"] = round(100 * nwin / ntr, 1) if ntr else 0.0
            rows.append(r)
        print(f"  done {nm}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)

    cols = ["family", "sl", "tp", "win", "gate", "cap", "budget", "maxc",
            "sel_tr", "sel_win", "sel_net", "sel_pay", "sel_bust", "sel_cal",
            "hold_net", "hold_pay", "hold_bust", "hold_cal", "rec_net", "rec_bust"]
    pd.set_option("display.width", 260)
    real = out[(out.sel_pay >= 3) & (out.hold_pay >= 5)]
    print("\n" + "=" * 125)
    print("LOWEST BUST RATE (selection year), requiring >=3 sel payouts and >=5 hold payouts")
    print("=" * 125)
    print(real.sort_values("sel_bust")[cols].head(25).to_string(index=False)
          if len(real) else "(none)")

    surv = real[(real.sel_bust <= 40) & (real.hold_bust <= 45) & (real.hold_net > 0)]
    print(f"\n{'='*125}\nBUST <=40% (sel) AND <=45% (hold) AND holdout net>0 : {len(surv)}\n{'='*125}")
    print(surv.sort_values("sel_cal")[cols].head(25).to_string(index=False)
          if len(surv) else "(NONE)")


if __name__ == "__main__":
    main()
