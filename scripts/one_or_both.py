"""Long only vs short only vs BOTH — under the verified LucidPro 25K rules.

An earlier version of this comparison ran under the OLD (wrong) payout model and
before the evaluate() bugfix, so its numbers do not carry. This redoes it properly
with lucid_fast, ranking on mean/median withdrawn, pay% and dead% (busted OR never
paid) rather than bust%, which floor-aware sizing can drive to zero artificially.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

import funded_search as fs
import funded_1yr as f1
import lucid_fast as LF

PAIRS = [
    ("tt_turtle_s2_long", "vol_lw_stretch_short", (9.75, 12.0), 2.0, 3.0, 1.0, 440, 10),
    ("sr_round100_break", "vol_lw_stretch_short", (9.75, 15.5), 2.0, 3.0, 1.0, 440, 10),
    ("mf_wkpiv_long", "vol_lw_stretch_short", (9.75, 11.0), 1.0, 1.5, 1.0, 440, 10),
    ("mf_wkpiv_long", "bb_break_short", (9.75, 15.5), 2.0, 3.0, 1.0, 440, 10),
]

df = fs.load_enriched()
pl = f1.load_plugins(df)
end = df.index[-1]
w5 = end - pd.DateOffset(months=5)
sel, hold = df[df.index >= w5], df[df.index < w5]


def get(frame, n):
    e, _ = pl[n] if n in pl else fs.sig(df, n)
    return pd.Series(e).reindex(frame.index).fillna(False).to_numpy(bool)


pd.set_option("display.width", 200)
print("=" * 118)
print("LONG ONLY  vs  SHORT ONLY  vs  BOTH        (verified LucidPro 25K rules)")
print("=" * 118)

rows = []
for ln, sn, win, sl, tp, rf, cap, mc in PAIRS:
    print(f"\n### {ln}  +  {sn}")
    print(f"    {win[0]}-{win[1]}, SL {sl} / TP {tp}, rf {rf}, cap ${cap}, {mc} ct")
    print(f"    {'mode':<12}{'period':<8}{'mean':>9}{'median':>9}{'paid':>8}{'dead':>8}")
    for mode in ("long only", "short only", "BOTH"):
        for tag, frame, stride in (("sel", sel, 2), ("hold", hold, 10)):
            el = get(frame, ln) if mode != "short only" else np.zeros(len(frame), bool)
            es = get(frame, sn) if mode != "long only" else np.zeros(len(frame), bool)
            P = LF.prep(frame, el, es, win)
            m = LF.evaluate(P, sl, tp, cap, 300, mc, rf, 0.0, horizon=150, stride=stride)
            print(f"    {mode:<12}{tag:<8}{m['mean_out']:>9,}{m['med_out']:>9,}"
                  f"{m['pay_pct']:>7.1f}%{m['dead_pct']:>7.1f}%")
            rows.append(dict(long=ln, short=sn, mode=mode, period=tag, **m))
    print()

out = pd.DataFrame(rows)
out.to_csv("one_or_both.csv", index=False)

print("=" * 118)
print("SUMMARY — averaged across the four pairings, HOLDOUT only (the honest period)")
print("=" * 118)
h = out[out.period == "hold"]
print(h.groupby("mode").agg(mean_out=("mean_out", "mean"), med_out=("med_out", "mean"),
                            pay_pct=("pay_pct", "mean"),
                            dead_pct=("dead_pct", "mean")).round(1).to_string())
print("\nSELECTION period:")
s = out[out.period == "sel"]
print(s.groupby("mode").agg(mean_out=("mean_out", "mean"), med_out=("med_out", "mean"),
                            pay_pct=("pay_pct", "mean"),
                            dead_pct=("dead_pct", "mean")).round(1).to_string())
