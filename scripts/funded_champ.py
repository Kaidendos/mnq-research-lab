"""Validate the hunt champion (EMA20/50 cross, gated, morning, 1/1 ATR) before
trusting it: year-by-year P&L (is it every-year profitable or one lucky year?),
plus a refinement sweep around the EMA-cross family."""

import numpy as np
import pandas as pd

import funded_lib as fl
from funded_backtest import payout_sim

MORNING = (9.75, 11.5833)


def ema_cross_signal(df, fast, slow):
    ef = df["close"].ewm(span=fast, adjust=False).mean()
    es = df["close"].ewm(span=slow, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1)), +1


def run(df, fast, slow, sl, tp, gate):
    entry, side = ema_cross_signal(df, fast, slow)
    return fl.replay_sessions(df, entry, side, sl, tp, MORNING, gate)


def payout(daily):
    att, dtp, bust, _ = payout_sim(daily)
    if att == 0:
        return (0.0, 0.0, -1, 0)
    return (100*len(dtp)/att, 100*bust/att, int(np.median(dtp)) if dtp else -1, att)


def main():
    d = fl.load_enriched()

    print("=" * 78)
    print("CHAMPION year-by-year: EMA20/50 cross, morning, EMA50 gate, 1.0/1.0 ATR")
    print("=" * 78)
    daily, ntr, nwin = run(d, 20, 50, 1.0, 1.0, "gate_ema50")
    yr = daily.groupby(daily.index.year)
    print(f"{'year':6}{'net$':>9}{'days':>6}{'best':>7}{'worst':>7}")
    for y, s in yr:
        print(f"{y:<6}{s.sum():>+9,.0f}{len(s):>6}{s.max():>+7,.0f}{s.min():>+7,.0f}")
    print(f"{'ALL':6}{daily.sum():>+9,.0f}{len(daily):>6}   trades {ntr}  win {100*nwin/ntr:.0f}%")
    p18 = payout(daily[daily.index >= "2025-01-23"]); p5 = payout(daily)
    print(f"payout(18mo): {p18[0]:.0f}% pay / {p18[1]:.0f}% bust / med {p18[2]}d (n={p18[3]})")
    print(f"payout(5yr) : {p5[0]:.0f}% pay / {p5[1]:.0f}% bust / med {p5[2]}d (n={p5[3]})")

    print("\n" + "=" * 78)
    print("no-gate sibling year-by-year (does the gate matter?)")
    print("=" * 78)
    daily2, ntr2, nwin2 = run(d, 20, 50, 1.0, 1.0, None)
    for y, s in daily2.groupby(daily2.index.year):
        print(f"{y:<6}{s.sum():>+9,.0f}{len(s):>6}")
    print(f"{'ALL':6}{daily2.sum():>+9,.0f}  trades {ntr2}  win {100*nwin2/ntr2:.0f}%")

    print("\n" + "=" * 78)
    print("EMA-CROSS REFINEMENT SWEEP (all morning + EMA50 gate)")
    print("fast/slow x SL/TP -> net5 | 18mo pay/bust | 5yr pay/bust | robust")
    print("=" * 78)
    best = []
    for fast, slow in ((9, 21), (10, 30), (20, 40), (20, 50), (10, 50), (15, 40), (20, 60)):
        for sl, tp in ((1.0, 1.0), (1.0, 1.5), (1.25, 1.25), (0.75, 1.0), (1.5, 1.5)):
            dl, nt, nw = run(d, fast, slow, sl, tp, "gate_ema50")
            if len(dl) < 20:
                continue
            a18 = payout(dl[dl.index >= "2025-01-23"]); a5 = payout(dl)
            rob = min(a18[0], a5[0]) if (a18[3] >= 25 and a5[3] >= 25) else -1
            best.append((rob, fast, slow, sl, tp, int(dl.sum()), nt,
                         round(100*nw/nt, 0), a18[0], a18[1], a5[0], a5[1], a5[2]))
    best.sort(reverse=True)
    print(f"{'f/s':>7} {'sl/tp':>9} {'net5':>7} {'tr':>4} {'wr':>4} "
          f"{'p18':>5} {'b18':>5} {'p5':>5} {'b5':>5} {'med5':>5} {'robust':>6}")
    for rob, f, s, sl, tp, net, nt, wr, p18, b18, p5, b5, m5 in best[:14]:
        print(f"{f:>3}/{s:<3} {sl:>4.2f}/{tp:<4.2f} {net:>+7,d} {nt:>4} {wr:>3.0f}% "
              f"{p18:>5.0f} {b18:>5.0f} {p5:>5.0f} {b5:>5.0f} {m5:>5} {rob:>6.0f}")


if __name__ == "__main__":
    main()
