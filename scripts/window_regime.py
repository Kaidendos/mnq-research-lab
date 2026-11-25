"""Has the edge MOVED later in the session? Narrow 9:45-11:00 vs wide 9:45-15:30.

`tp_*.csv` shows the same pairing, same brackets, same cap $440, differing only in
session window:

    9:45-11:00   sel_mean $344   hold_mean $1,380  hold_med $292
    9:45-15:30   sel_mean $961   hold_mean $1,355  hold_med $0

Nearly 3x the recent-window mean for a statistically indistinguishable holdout
mean. That is the single largest recent-regime difference found anywhere in this
project, and it bears directly on the live complaint — the narrow window was
chosen on 4.5 years of holdout, and the last 5 months may simply not be
distributing their moves the same way.

The counter-evidence is already on record and must not be ignored: harvest sweep
#4 found EVERY window starting at 9:45 beats every later start by 3-7x, and the
narrow window carries a much better holdout MEDIAN. A higher mean with a zero
median means a few accounts carry everything.

So this tests all four intermediate windows on both cap configs and both windows
of time, reporting mean AND median AND bust together, because mean alone is
exactly the metric that hides this failure mode.
"""
from __future__ import annotations

import itertools

import pandas as pd

import funded_search as fs
import funded_1yr as f1
import sim_trace as ST

BASE_L, BASE_S = "sr_round100_break", "vol_lw_stretch_short"
WINS = [(9.75, 11.0), (9.75, 12.0), (9.75, 13.5), (9.75, 15.5),
        (11.0, 15.5)]           # the complement: is the afternoon good on its own?

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
cut = end - pd.DateOffset(months=5)
FRAMES = (("hold", df[df.index < cut]), ("sel", df[df.index >= cut]))


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


rows = []
for (wname, frame), win, (cap, bud) in itertools.product(
        FRAMES, WINS, ((440, 300), (250, 400))):
    P = ST.build(frame, [BASE_L], [BASE_S], win, resolve)
    res = [ST.trace(P, k, cap, bud) for k in range(0, len(P["per"]), 4)
           if len(P["per"]) - k >= 20]
    rows.append(dict(window=wname, session=f"{win[0]}-{win[1]}", cap=cap,
                     **ST.summarise(res)))
    print(f"  {wname} {win} cap{cap}", flush=True)

out = pd.DataFrame(rows)
out.to_csv("window_regime.csv", index=False)
pd.set_option("display.width", 200)
print("\n" + "=" * 120)
print("SESSION WINDOW x REGIME — same signals, same brackets, only the clock differs")
print("=" * 120)
for (w, cap), grp in out.groupby(["window", "cap"], sort=False):
    print(f"\n  ### {w}  |  cap ${cap}")
    print(grp[["session", "n", "paid", "stalled", "bust", "mean", "med", "p75",
               "avg_pays", "days"]].to_string(index=False))
