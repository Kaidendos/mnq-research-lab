"""Optimise against the REAL LucidPro 25K rules, objective = dollars withdrawn.

Everything before this swept against a drawdown that trails forever and a payout
threshold of 26,100 (where you can actually withdraw nothing). Both were wrong.
This re-optimises with:

  * lucid_rules.simulate  — EOD trail, floor locks at 25,100 once 26,100 clears,
    withdraw only above 26,100, cap 1,000 first cycle / 1,500 after,
    40% consistency per cycle, 3-day minimum
  * OBJECTIVE = mean dollars withdrawn per account, over accounts started on
    many different days with a 1-year horizon. That is the real economic outcome:
    what one account cycle is worth, against what an account costs.

Secondary metrics kept so a high mean carried by one lucky account is visible:
share taking >=1 payout, median withdrawn, share busting.
"""
from __future__ import annotations

import argparse
import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_rules as LR
from funded_longshort import replay_2s

HORIZON = 365          # judge an account over one year
START_STRIDE = 3       # sample every 3rd start day (compute)
MIN_WITHDRAW = 1000    # wait for a full payout — shown to beat withdrawing ASAP

LONGS = ["sr_round100_break", "ema20_50_long", "so_k21_th30", "sr_pivot_s1_bounce",
         "rsi_bounce35_long", "so_combo_deep_rvol", "sr_ib60_break", "NONE"]
SHORTS = ["vol_lw_stretch_short", "pdh_fade_short", "mr_rsi2_short", "orb30_short",
          "engulf_bb_short", "hv_gapx_fade", "so_short_th75", "NONE"]

SLS = (0.75, 1.0, 1.5, 2.0)
TPS = (1.0, 1.5, 2.0, 3.0)
WINS = ((9.75, 15.5), (9.6667, 11.5), (10.0, 13.0))
GATES = (None, "split")
SIZES = ((440, 300, 10), (300, 300, 5), (600, 400, 10))


def score_account(daily: pd.Series) -> dict:
    """Mean/median dollars withdrawn per account, over staggered start days."""
    idx = daily.index
    outs, pays, busts = [], 0, 0
    n = 0
    for s in range(0, len(daily), START_STRIDE):
        sub = daily.iloc[s:]
        sub = sub[sub.index <= idx[s] + pd.Timedelta(days=HORIZON)]
        if len(sub) < LR.MIN_DAYS:
            continue
        r = LR.simulate(sub, min_withdraw=MIN_WITHDRAW)
        outs.append(r["withdrawn"])
        pays += 1 if r["payouts"] >= 1 else 0
        busts += 1 if r["busted"] else 0
        n += 1
    if not n:
        return dict(mean_out=0.0, med_out=0.0, p75_out=0.0, pay_pct=0.0,
                    bust_pct=100.0, n=0)
    a = np.array(outs)
    return dict(mean_out=round(float(a.mean())), med_out=round(float(np.median(a))),
                p75_out=round(float(np.percentile(a, 75))),
                pay_pct=round(100 * pays / n, 1), bust_pct=round(100 * busts / n, 1),
                n=n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", default=None)
    ap.add_argument("--out", default="opt.csv")
    args = ap.parse_args()

    df = fs.load_enriched()
    pl = f1.load_plugins(df)
    empty = pd.Series(False, index=df.index)

    def get(n):
        if n == "NONE":
            return empty
        e, _ = pl[n] if n in pl else fs.sig(df, n)
        return pd.Series(e).reindex(df.index).fillna(False)

    L = {n: get(n) for n in LONGS}
    S = {n: get(n) for n in SHORTS}

    pairs = [(a, b) for a, b in itertools.product(LONGS, SHORTS)
             if not (a == "NONE" and b == "NONE")]
    if args.slice:
        i, k = (int(x) for x in args.slice.split("/"))
        pairs = pairs[i::k]
    print(f"{len(pairs)} pairings x {len(SLS)*len(TPS)*len(WINS)*len(GATES)*len(SIZES)} configs",
          flush=True)

    rows = []
    for ln, sn in pairs:
        el, es = L[ln], S[sn]
        for sl, tp, win, gate, (cap, bud, mc) in itertools.product(
                SLS, TPS, WINS, GATES, SIZES):
            daily, tt, ww, nl, ns = replay_2s(df, el, es, sl, tp, win, gate,
                                              cap, bud, maxc=mc)
            if tt < 40 or len(daily) < 30:
                continue
            m = score_account(daily)
            rows.append(dict(long=ln, short=sn, sl=sl, tp=tp,
                             win=f"{win[0]:.2f}-{win[1]:.2f}", gate=gate or "-",
                             cap=cap, maxc=mc, trades=tt,
                             win_pct=round(100 * ww / tt, 1), nl=nl, ns=ns,
                             net=round(float(daily.sum())), **m))
        print(f"  done {ln} + {sn}", flush=True)

    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"\n{len(rows):,} scored -> {args.out}")


if __name__ == "__main__":
    main()
