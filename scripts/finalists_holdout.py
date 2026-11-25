"""Holdout the selection-year finalists on the prior 4 years they were NOT fitted to."""
import glob
import pandas as pd

import funded_search as fs
import funded_1yr as f1

d = pd.concat([pd.read_csv(x) for x in sorted(glob.glob("y1_*.csv"))], ignore_index=True)
g = d[(d.sel_net > 0) & (d.sel_payouts >= 2)]
fin = g[g.sel_cal_per_payout <= 30].copy()
# plus near-misses so we can see the shape of the frontier
near = g[(g.sel_cal_per_payout > 30) & (g.sel_cal_per_payout <= 40)]
near = near.sort_values("sel_bust_pct").head(15)
cand = pd.concat([fin, near], ignore_index=True)
print(f"{len(fin)} goal-meeting + {len(near)} near-miss = {len(cand)} to hold out\n")

df = fs.load_enriched()
plugins = f1.load_plugins(df)
df_sel = df[df.index >= f1.SEL_START]
df_hold = df[df.index < f1.HOLD_END]
span_sel = (df_sel.index[-1] - df_sel.index[0]).days
span_hold = (df_hold.index[-1] - df_hold.index[0]).days

rows = []
for _, r in cand.iterrows():
    nm = r["family"]
    entry, side = plugins[nm] if nm in plugins else fs.sig(df, nm)
    win = tuple(float(x) for x in str(r["win"]).split("-"))
    gate = None if r["gate"] in ("-", "") or pd.isna(r["gate"]) else r["gate"]
    e = pd.Series(entry).reindex(df_hold.index).fillna(False)
    daily, ntr, nwin = fs.replay(df_hold, e, side, r["sl"], r["tp"], win, gate,
                                 int(r["cap"]), int(r["budget"]))
    m = f1.score(daily, span_hold)
    rows.append(dict(
        family=nm, sl=r["sl"], tp=r["tp"], win=r["win"], gate=r["gate"], cap=r["cap"],
        sel_net=r["sel_net"], sel_cal=r["sel_cal_per_payout"], sel_bust=r["sel_bust_pct"],
        sel_payouts=r["sel_payouts"],
        hold_net=m["net"], hold_cal=m["cal_per_payout"], hold_bust=m["bust_pct"],
        hold_payouts=m["payouts"], hold_busts=m["busts"], hold_trades=ntr,
        hold_win=round(100 * nwin / ntr, 1) if ntr else 0.0))

out = pd.DataFrame(rows).sort_values("sel_cal")
out.to_csv("finalists_holdout.csv", index=False)
pd.set_option("display.width", 250)
print("=" * 130)
print("SELECTION YEAR (fitted)  vs  PRIOR 4 YEARS (never fitted)")
print("=" * 130)
print(out.to_string(index=False))

print("\n" + "=" * 70)
surv = out[(out.hold_net > 0) & (out.hold_cal > 0) & (out.hold_cal <= 60)]
print(f"finalists still net-POSITIVE on the holdout      : {(out.hold_net > 0).sum()} / {len(out)}")
print(f"finalists net-positive AND <=60 cal-days on hold : {len(surv)} / {len(out)}")
print("=" * 70)
if len(surv):
    print(surv.to_string(index=False))
