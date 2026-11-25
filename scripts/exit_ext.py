"""Extend the exit grid: SL and TP both improved monotonically to the edge of the
tested range, so the optimum may lie outside it — or the trend may be an artifact
of running out of grid. Wider stops also mean smaller positions, so this is points
only; `exit_account.py` decides whether any of it survives sizing."""
import itertools, pandas as pd, funded_search as fs, funded_1yr as f1, lucid_fast as LF
from exit_sweep import walk
df = fs.load_enriched(); pl = f1.load_plugins(df)
end = df.index[-1]; hold = df[df.index < end - pd.DateOffset(months=5)]
g = lambda n: pd.Series((pl[n] if n in pl else fs.sig(df, n))[0]).reindex(hold.index).fillna(False).to_numpy(bool)
P = LF.prep(hold, g("sr_round100_break"), g("vol_lw_stretch_short"), (9.75, 11.0))
rows = []
for sl, tp in itertools.product((2.0,2.5,3.0,3.5,4.0,4.5,5.0), (3.0,4.0,5.0,6.0,7.0,8.0)):
    r = walk(P, sl, tp, None, None, None)
    if r: rows.append(dict(sl=sl, tp=tp, **r)); print(f"  {sl}/{tp}", flush=True)
o = pd.DataFrame(rows); o.to_csv("exit_ext.csv", index=False)
pd.set_option("display.width", 200)
print("\nEXTENDED EXIT GRID — points per trade, no time stop / breakeven / trail")
print(o.pivot(index="sl", columns="tp", values="ppt").to_string())
print("\nyears positive (of 6):")
print(o.pivot(index="sl", columns="tp", values="yrs_pos").to_string())
print("\nworst year ppt:")
print(o.pivot(index="sl", columns="tp", values="worst_yr").to_string())
print("\nTOP 10:"); print(o.nlargest(10, "ppt").to_string(index=False))
