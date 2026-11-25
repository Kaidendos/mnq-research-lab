"""Account-level test of the best two-sided FADE system that can actually be built.

The clean-edge ranking says the two sides behave completely differently:
  BUY THE LOW  — 4 of 11 families positive, best +3.71 (below the incumbent long's
                 +4.74). The most intuitive versions are the WORST: buying a
                 prior-day-low reclaim -10.67, a failed breakdown -9.69, RSI(2)
                 oversold -13.19, all beaten by 9-10 of 10 shuffles.
  SELL THE HIGH — 3 of 11 positive, best +22.56 (hi_rsi2_short), but on 56 trades.

So the best buildable fade pair is a weak long and a thin short. Tested anyway, at
account level, against the incumbent — because "it ranks badly per trade" and "it
loses money in an account" are different claims and the user asked for the strategy,
not the ranking.
"""
import itertools, numpy as np, pandas as pd
import funded_search as fs, funded_1yr as f1, lucid_fast as LF, sim_trace as ST
WIN=(9.75,11.0)
COMBOS=[("INCUMBENT (breakout)","sr_round100_break","vol_lw_stretch_short"),
        ("FADE both sides","lo_bb_reclaim_long","hi_rsi2_short"),
        ("FADE long + inc short","lo_bb_reclaim_long","vol_lw_stretch_short"),
        ("inc long + FADE short","sr_round100_break","hi_rsi2_short"),
        ("FADE long + blowoff","lo_bb_reclaim_long","hi_blowoff_short"),
        ("capitulation + inc short","lo_capitulation_long","vol_lw_stretch_short"),
        ("3bar rev + inc short","lo_3bar_reversal_long","vol_lw_stretch_short")]
df=fs.load_enriched(); pl=f1.load_plugins(df)
end=df.index[-1]; cut=end-pd.DateOffset(months=5)
FR=(("hold",df[df.index<cut]),("recent",df[df.index>=cut]))
for y in (2022,2023,2024,2025,2026): FR=FR+((f"y{y}",df[df.index.year==y]),)
r=lambda fr,n: pd.Series((pl[n] if n in pl else fs.sig(df,n))[0]).reindex(fr.index).fillna(False).to_numpy(bool)
print(f"  {'config':<26}{'paid':>7}{'bust':>7}{'mean':>9}{'med':>8}{'days':>6}{'rec_mean':>10}{'rec_paid':>10}")
res={}
for nm,ln,sn in COMBOS:
    row={}
    for fn,frame in FR:
        if len(frame)<4000 and fn.startswith("y"): continue
        P=LF.prep(frame,r(frame,ln),r(frame,sn),WIN)
        hz=180 if fn.startswith("y") else 365
        out=[ST.trace(P,k,440,300,maxdays=hz) for k in range(0,len(P["per"]),4) if len(P["per"])-k>=20]
        row[fn]=ST.summarise(out) if out else None
    res[nm]=row
    h,rc=row["hold"],row["recent"]
    print(f"  {nm:<26}{h['paid']:>7.1f}{h['bust']:>7.1f}{h['mean']:>9,.0f}{h['med']:>8,.0f}"
          f"{h['days']:>6}{rc['mean']:>10,.0f}{rc['paid']:>10.1f}",flush=True)
print("\n"+"="*104); print("PER YEAR (mean $ per account, 180-day horizon)"); print("="*104)
YRS=(2022,2023,2024,2025,2026)
print(f"  {'config':<26}"+"".join(f"{y:>10}" for y in YRS))
for nm,_,_ in COMBOS:
    print(f"  {nm:<26}"+"".join(f"{(res[nm].get(f'y{y}') or {}).get('mean',0):>10,.0f}" for y in YRS))
