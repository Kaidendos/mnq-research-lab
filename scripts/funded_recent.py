"""Recent-months detail for the #1 validated config:
EMA 20/50 cross, runner-to-EOD, cap $300 / budget $200, EMA50 gate, morning."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
from funded_backtest import payout_sim


def main():
    d = fl3.enrich3(fl2.enrich2(fl.load_enriched()))
    ef = d["close"].ewm(span=20, adjust=False).mean()
    es = d["close"].ewm(span=50, adjust=False).mean()
    entry = (ef > es) & (ef.shift(1) <= es.shift(1))
    daily, nt, nw = fl2.replay_runner(d, entry, +1, 1.0, (9.75, 11.5833),
                                      "gate_ema50", mode="eod", cap=300, budget=200)

    print("EMA 20/50 runner, cap $300 / budget $200, gated — MONTHLY NET (recent):")
    mret = daily.groupby(daily.index.to_period("M")).sum()
    for m in ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
              "2026-04", "2026-05", "2026-06", "2026-07"]:
        v = mret.get(pd.Period(m, "M"), None)
        tag = f"{v:>+8,.0f}" if v is not None else f"{'(no trades)':>11}"
        print(f"  {m}: {tag}")

    def pw(sub, label):
        att, dtp, bust, _ = payout_sim(sub)
        if att == 0:
            print(f"  {label}: no attempts"); return
        print(f"  {label}: reach payout {100*len(dtp)/att:.0f}%, "
              f"median {int(np.median(dtp)) if dtp else -1} trade-days, "
              f"net ${sub.sum():+,.0f} ({len(sub)} active days)")

    print("\nPayout reliability by window:")
    pw(daily[daily.index >= "2026-02-16"], "last 5 months")
    pw(daily[daily.index >= "2025-01-01"], "test window (Jan25-Jul26, 18mo)")
    pw(daily, "full 5 years")

    print("\nLast 2 weeks, day by day:")
    for dt, v in daily[daily.index >= "2026-07-02"].items():
        print(f"  {dt.date()}: {v:+,.0f}")


if __name__ == "__main__":
    main()
