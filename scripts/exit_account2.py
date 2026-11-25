"""Broader account-level exit grid.

`exit_ext.py` found the POINTS optimum is SL 4.5-5.0 / TP 6.0 (~22 ppt), and that
TP 6.0 is a real interior peak — every SL row rises to it and falls after, so it is
not just the edge of the grid. But the first account-level pass only went to SL 3.0
and TP 5.0, and it chose SL3.0/TP3.0 — because sizing runs the other way: both
`budget/(ATR*SL*$2)` and `(cap-net)/(ATR*TP*$2)` shrink the position as the bracket
widens. Points and dollars therefore optimise in opposite directions, and the
account grid has to cover the points optimum before that trade-off is settled.

Also sweeps budget up to $600, since a wider stop needs a bigger budget to buy the
same exposure — testing the bracket at a fixed budget confounds the two.
"""
import itertools, pandas as pd
import funded_search as fs, funded_1yr as f1, lucid_fast as LF, sim_trace as ST
WIN = (9.75, 11.0)
df = fs.load_enriched(); pl = f1.load_plugins(df)
end = df.index[-1]; cut = end - pd.DateOffset(months=5)
FR = (("hold", df[df.index < cut]), ("recent", df[df.index >= cut]))
r = lambda fr, n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(fr.index).fillna(False).to_numpy(bool)
P = {w: LF.prep(f, r(f, "sr_round100_break"), r(f, "vol_lw_stretch_short"), WIN) for w, f in FR}
rows = []
for sl, tp, bud in itertools.product((2.0,2.5,3.0,3.5,4.0),(3.0,4.0,5.0,6.0),(300,400,500,600)):
    row = dict(sl=sl, tp=tp, cap=440, bud=bud)
    for w in ("hold","recent"):
        res = [ST.trace(P[w], k, 440, bud, sl=sl, tp=tp)
               for k in range(0, len(P[w]["per"]), 4) if len(P[w]["per"]) - k >= 20]
        m = ST.summarise(res)
        for k2 in ("paid","bust","mean","med","days"): row[f"{w}_{k2}"] = m[k2]
    rows.append(row); print(f"  {sl}/{tp} bud{bud}", flush=True)
o = pd.DataFrame(rows); o.to_csv("exit_account2.csv", index=False)
pd.set_option("display.width", 210)
b = o[(o.sl==2.0)&(o.tp==3.0)&(o.bud==300)].iloc[0]
print(f"\nINCUMBENT SL2/TP3 bud300: paid {b.hold_paid} bust {b.hold_bust} mean ${b.hold_mean:,.0f} med ${b.hold_med:,.0f} {b.hold_days}d | recent ${b.recent_mean:,.0f}")
print("\nTOP 20 BY HOLDOUT MEAN"); print(o.nlargest(20,"hold_mean").to_string(index=False))
print("\nBEATS INCUMBENT ON MEAN+MEDIAN, BUST NO WORSE, RECENT NO WORSE")
w = o[(o.hold_mean>b.hold_mean)&(o.hold_med>b.hold_med)&(o.hold_bust<=b.hold_bust)&(o.recent_mean>=b.recent_mean)]
print(w.sort_values("hold_mean",ascending=False).to_string(index=False) if len(w) else "  none")
print("\nMEAN BY BUDGET x SL (holdout mean $)"); print(o.pivot_table(index="sl",columns="bud",values="hold_mean").round(0).to_string())
