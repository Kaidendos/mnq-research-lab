"""Base rates: what did the LIVE config earn in the 30 calendar days after
each EMA50 gate flip (ON->OFF, like 2026-07-16), across 5 years? Fees in."""

import numpy as np
import pandas as pd

import improve_lab as il

def main():
    d = il.load()
    t = il.run(d.loc[il.START:])
    daily = t.groupby("date")["pnl"].sum()
    daily.index = daily.index.tz_localize(None)

    dc = d["close"].groupby(d.index.normalize()).last()
    ema50 = dc.ewm(span=50, adjust=False).mean()
    on = (dc > ema50)
    on.index = on.index.tz_localize(None)
    flips_off = on.index[(~on) & on.shift(1).fillna(False)]
    flips_on = on.index[on & (~on.shift(1).fillna(True).astype(bool))]

    def fwd(flips, label):
        outs = []
        for f in flips:
            w = daily[(daily.index > f) & (daily.index <= f + pd.Timedelta(days=30))]
            if len(w):
                outs.append(w.sum())
        o = np.array(outs)
        print(f"{label}: {len(o)} flips | next-30-cal-days live-config P&L: "
              f"mean ${o.mean():+,.0f}, median ${np.median(o):+,.0f}, "
              f"negative {100*(o<0).mean():.0f}% of the time, "
              f"best ${o.max():+,.0f}, worst ${o.min():+,.0f}")

    fwd(flips_off, "gate ON->OFF (like Jul 16)")
    fwd(flips_on, "gate OFF->ON            ")
    n_off = (~on).sum()
    print(f"(gate OFF {100*n_off/len(on):.0f}% of days; "
          f"median OFF spell {int(np.median([len(list(g)) for k, g in __import__('itertools').groupby(on) if not k]))} sessions)")

if __name__ == "__main__":
    main()
