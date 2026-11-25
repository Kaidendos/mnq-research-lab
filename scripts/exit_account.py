"""Does the wider-exit improvement SURVIVE POSITION SIZING? The gating question.

`exit_sweep.py` found every exit lever is monotonic, and all of them say do LESS:
    stop     1.5 -> 3.0 x ATR : mean ppt 6.77 -> 9.30   (wider is better)
    target   2.0 -> 5.0 x ATR : mean ppt 7.13 -> 8.80   (wider is better)
    time stop / breakeven / trailing : ALL reduce ppt. Best value is "off".
Best combo SL3.0/TP5.0 = +16.91 ppt vs the current SL2.0/TP3.0 at +12.25 (+38%),
positive in all 6 years.

BUT POINTS PER TRADE IS NOT DOLLARS. Size is `budget / (ATR * SL * $2)`, so moving
the stop from 2.0 to 3.0 ATR cuts contracts by a THIRD. A 38% gain in points against
a 33% cut in size is roughly a wash — and the daily cap `(cap - net)/(ATR*TP*$2)`
tightens too as TP widens. The account may see none of the improvement, or worse.

So this re-runs the leading exit variants through the full LucidPro simulator, where
sizing and the cap actually bite, and sweeps the loss budget alongside — because if
wider stops are genuinely better, the right response is a bigger budget to pay for
them, and that is a different question from "is the exit better".
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF
import sim_trace as ST

WIN = (9.75, 11.0)
LONG_SIG, SHORT_SIG = "sr_round100_break", "vol_lw_stretch_short"

# (sl, tp) pairs: the incumbent plus the leaders from the points sweep
BRACKETS = [(2.0, 3.0), (3.0, 3.0), (3.0, 4.0), (3.0, 5.0),
            (2.0, 4.0), (2.0, 5.0), (2.5, 4.0), (2.5, 5.0)]
SIZES = [(440, 300), (440, 400), (440, 500), (250, 400), (600, 500)]

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
cut = end - pd.DateOffset(months=5)
FRAMES = (("hold", df[df.index < cut]), ("recent", df[df.index >= cut]))


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


PREP = {w: LF.prep(f, resolve(f, LONG_SIG), resolve(f, SHORT_SIG), WIN)
        for w, f in FRAMES}

rows = []
for (sl, tp), (cap, bud) in itertools.product(BRACKETS, SIZES):
    row = dict(sl=sl, tp=tp, cap=cap, budget=bud)
    for wname in ("hold", "recent"):
        P = PREP[wname]
        res = [ST.trace(P, k, cap, bud, sl=sl, tp=tp)
               for k in range(0, len(P["per"]), 4) if len(P["per"]) - k >= 20]
        m = ST.summarise(res)
        for key in ("paid", "bust", "mean", "med", "days"):
            row[f"{wname}_{key}"] = m[key]
    rows.append(row)
    print(f"  SL{sl}/TP{tp} cap{cap}/bud{bud}", flush=True)

out = pd.DataFrame(rows)
out.to_csv("exit_account.csv", index=False)
pd.set_option("display.width", 210)

base = out[(out.sl == 2.0) & (out.tp == 3.0) & (out.cap == 440) & (out.budget == 300)].iloc[0]
print("\n" + "=" * 150)
print("EXIT VARIANTS AT ACCOUNT LEVEL — does the points gain turn into dollars?")
print(f"INCUMBENT SL2.0/TP3.0 cap440/bud300:  paid {base.hold_paid}%  "
      f"bust {base.hold_bust}%  mean ${base.hold_mean:,.0f}  med ${base.hold_med:,.0f}  "
      f"{base.hold_days}d   |  recent mean ${base.recent_mean:,.0f}")
print("=" * 150)
COLS = ["sl", "tp", "cap", "budget", "hold_paid", "hold_bust", "hold_mean",
        "hold_med", "hold_days", "recent_paid", "recent_mean"]
print(out.sort_values("hold_mean", ascending=False)[COLS].to_string(index=False))

print("\n" + "=" * 150)
print("BEATS THE INCUMBENT ON HOLDOUT MEAN *AND* MEDIAN, WITH BUST NO WORSE")
print("=" * 150)
w = out[(out.hold_mean > base.hold_mean) & (out.hold_med > base.hold_med)
        & (out.hold_bust <= base.hold_bust)]
print(w[COLS].sort_values("hold_mean", ascending=False).to_string(index=False)
      if len(w) else "  none")

print("\n" + "=" * 150)
print("SAME, BUT ALSO NOT WORSE IN THE RECENT 5 MONTHS")
print("=" * 150)
w2 = w[w.recent_mean >= base.recent_mean] if len(w) else w
print(w2[COLS].to_string(index=False) if len(w2) else "  none")
