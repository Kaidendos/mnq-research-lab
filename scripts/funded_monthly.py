"""Show the REAL monthly P&L of the best strategies over the last 5 months
(and the best single month each achieved in 5 years) so the $4k/month target
can be checked against reality. $440 cap, funded sizing, fees in."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3

MORNING = (9.75, 11.5833)


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def main():
    d = fl3.enrich3(fl2.enrich2(fl.load_enriched()))

    strats = {}
    strats["EMA12/26 runner"] = fl2.replay_runner(d, ema_cross(d, 12, 26), +1, 1.0, MORNING, "gate_ema50", mode="eod")[0]
    strats["EMA10/30 runner"] = fl2.replay_runner(d, ema_cross(d, 10, 30), +1, 1.0, MORNING, "gate_ema50", mode="eod")[0]
    strats["EMA20/50 champ 1/1"] = fl.replay_sessions(d, ema_cross(d, 20, 50), +1, 1.0, 1.0, MORNING, "gate_ema50")[0]
    strats["Keltner 1/1.5"] = fl.replay_sessions(d, fl2.sig2(d, "keltner_break_long")[0], +1, 1.0, 1.5, MORNING, "gate_ema50")[0]
    strats["Keltner runner nogate"] = fl2.replay_runner(d, fl2.sig2(d, "keltner_break_long")[0], +1, 1.0, MORNING, None, mode="eod")[0]
    strats["First-hour runner"] = fl2.replay_runner(d, fl3.sig3(d, "first_hour_break_long")[0], +1, 1.0, MORNING, "gate_ema50", mode="eod")[0]
    strats["ORB15 runner"] = fl2.replay_runner(d, fl.sig(d, "orb15_long")[0], +1, 1.0, MORNING, "gate_ema50", mode="eod")[0]

    months = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
    print("=" * 96)
    print("MONTHLY NET $ — LAST ~5 MONTHS  ($440/day cap, $300 loss budget, fees in)")
    print("=" * 96)
    hdr = f"{'strategy':24}" + "".join(f"{m[5:]:>8}" for m in months) + f"{'5mo tot':>9}{'bestMo*':>9}"
    print(hdr)
    print("-" * len(hdr))
    for name, daily in strats.items():
        mret = daily.groupby(daily.index.to_period("M")).sum()
        row = f"{name:24}"
        tot = 0.0
        for m in months:
            v = mret.get(pd.Period(m, "M"), 0.0)
            tot += v
            row += f"{v:>+8,.0f}"
        best_ever = mret.max()          # best single month in the full 5 years
        row += f"{tot:>+9,.0f}{best_ever:>+9,.0f}"
        print(row)
    print("-" * len(hdr))
    print("* bestMo = the single best month EACH strategy produced in the ENTIRE 5 years")
    print("\nReality check:")
    print("  target        : $4,000 / month")
    print("  theoretical max: ~$9,240 / month (21 days x $440 cap, 100% win, impossible)")
    print("  actual best mo : see 'bestMo' column — the most any of these made in one month, ever")


if __name__ == "__main__":
    main()
