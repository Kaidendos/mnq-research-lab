"""Is the recent 5 months genuinely broken, or is `sel_paid = 0.0%` an artifact?

`foldin_combo.py` reported 0.0% paid on the selection window for EVERY cap-$250
config, including ones that pay 87% on holdout. Two very different explanations:

  (a) REAL — the last 5 months are hostile and the slow config cannot reach the
      $26,100 buffer in current conditions. That would matter enormously; it is
      exactly the complaint that started this project.
  (b) ARTIFACT — the median time to a first payout on cap $250 is 92 CALENDAR
      days. The selection window is ~150 calendar days total, and accounts are
      started every 4 sessions right up to the end, so most of them are cut off
      long before day 92. They did not fail; they ran out of runway.

The test: require a minimum remaining runway and see whether the number moves.
If (b), payout rate climbs steeply as the runway requirement rises. If (a), it
stays near zero however much runway is granted.

The holdout gets the identical sweep, so both windows are asked the same question.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import sim_trace as ST

BASE_L, BASE_S = "sr_round100_break", "vol_lw_stretch_short"
WIN = (9.75, 11.0)
CONFIGS = [
    ("BASE 1L+1S", [BASE_L], [BASE_S]),
    ("3L2S ema+fisher+oops",
     [BASE_L, "ema20_50_long", "mf_wkpiv_long"], [BASE_S, "lw_oops_short"]),
]

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
cut = end - pd.DateOffset(months=5)
SEL, HOLD = df[df.index >= cut], df[df.index < cut]
print(f"selection: {SEL.index[0].date()} -> {SEL.index[-1].date()}  ({len(SEL)} bars)")
print(f"holdout  : {HOLD.index[0].date()} -> {HOLD.index[-1].date()}  ({len(HOLD)} bars)")


def resolve(frame, name):
    e, _ = pl[name] if name in pl else fs.sig(df, name)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


rows = []
for wname, frame in (("sel", SEL), ("hold", HOLD)):
    for label, longs, shorts in CONFIGS:
        P = ST.build(frame, longs, shorts, WIN, resolve)
        nsess = len(P["per"])
        for cap, bud in ((250, 400), (440, 300)):
            for runway in (20, 40, 60, 80, 100):
                starts = [k for k in range(0, nsess, 4) if nsess - k >= runway]
                if len(starts) < 8:
                    continue
                res = [ST.trace(P, k, cap, bud) for k in starts]
                rows.append(dict(window=wname, config=label, cap=cap,
                                 runway=runway, **ST.summarise(res)))
        print(f"  {wname} | {label} | {nsess} sessions", flush=True)

out = pd.DataFrame(rows)
out.to_csv("runway_check.csv", index=False)
pd.set_option("display.width", 200)
print("\n" + "=" * 120)
print("PAYOUT RATE vs MINIMUM RUNWAY — does giving accounts more time rescue them?")
print("runway = sessions of data remaining after the account starts")
print("=" * 120)
for (w, cfg), grp in out.groupby(["window", "config"], sort=False):
    print(f"\n  ### {w}  |  {cfg}")
    print(grp[["cap", "runway", "n", "paid", "stalled", "bust", "mean", "med", "days"]]
          .to_string(index=False))
