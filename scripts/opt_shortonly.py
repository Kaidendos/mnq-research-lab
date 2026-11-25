"""Optimise the SHORT-ONLY book on its own terms — it has never been tuned alone.

Every window, bracket, cap and budget in this project was chosen for the two-sided
pair. A short-only book is a different animal: it trades a third as often (225 vs
799), it has ~4x the per-trade edge (+20.90 vs +4.74), and its weakness is speed
(88 days to a first payout vs 27), not risk (0.0% bust vs 2.1%).

So the levers should be pushed the opposite way from the pair. For the pair, a
bigger cap traded speed for bust. Here there is bust headroom to spend, so a larger
cap and budget may buy back the speed without the usual cost. Never tested.

Swept: window x bracket x cap x budget, ranked on payout rate and days rather than
mean, because a short-only book's problem is reaching the buffer at all.
"""
import itertools, numpy as np, pandas as pd
import funded_search as fs, funded_1yr as f1, lucid_fast as LF, sim_trace as ST
df=fs.load_enriched(); pl=f1.load_plugins(df)
end=df.index[-1]; cut=end-pd.DateOffset(months=5)
HOLD, REC = df[df.index<cut], df[df.index>=cut]
r=lambda fr,n: pd.Series((pl[n] if n in pl else fs.sig(df,n))[0]).reindex(fr.index).fillna(False).to_numpy(bool)
WINDOWS=((9.75,11.0),(9.75,12.0),(9.75,13.5),(9.75,15.5))
BRACKETS=((2.0,3.0),(2.0,1.5),(1.5,2.0),(2.5,3.0))
SIZES=((440,300),(440,500),(600,500),(600,700),(900,700))
rows=[]
PH={w:LF.prep(HOLD,np.zeros(len(HOLD),bool),r(HOLD,"vol_lw_stretch_short"),w) for w in WINDOWS}
PR={w:LF.prep(REC,np.zeros(len(REC),bool),r(REC,"vol_lw_stretch_short"),w) for w in WINDOWS}
for w,(sl,tp),(cap,bud) in itertools.product(WINDOWS,BRACKETS,SIZES):
    o=[ST.trace(PH[w],k,cap,bud,sl=sl,tp=tp) for k in range(0,len(PH[w]["per"]),4) if len(PH[w]["per"])-k>=20]
    h=ST.summarise(o)
    o2=[ST.trace(PR[w],k,cap,bud,sl=sl,tp=tp) for k in range(0,len(PR[w]["per"]),4) if len(PR[w]["per"])-k>=20]
    rc=ST.summarise(o2) if o2 else {"mean":0,"paid":0}
    rows.append(dict(win=f"{w[1]}",sl=sl,tp=tp,cap=cap,bud=bud,
        paid=h["paid"],bust=h["bust"],mean=h["mean"],med=h["med"],days=h["days"],
        rec_mean=rc["mean"],rec_paid=rc["paid"]))
o=pd.DataFrame(rows); o.to_csv("opt_shortonly.csv",index=False)
pd.set_option("display.width",200)
base=o[(o.win=="11.0")&(o.sl==2.0)&(o.tp==3.0)&(o.cap==440)&(o.bud==300)].iloc[0]
print(f"BASELINE short-only 9:45-11:00 SL2/TP3 cap440/bud300:")
print(f"  paid {base.paid}%  bust {base.bust}%  mean ${base["mean"]:,.0f}  med ${base["med"]:,.0f}  {base.days}d  recent ${base["rec_mean"]:,.0f}")
print("\n"+"="*128); print("TOP 15 BY PAYOUT RATE (a short-only book's binding problem is reaching the buffer)"); print("="*128)
print(o.nlargest(15,"paid").to_string(index=False))
print("\n"+"="*128); print("TOP 15 BY SPEED among configs with paid>=55% and bust<=3%"); print("="*128)
g=o[(o.paid>=55)&(o.bust<=3)].nsmallest(15,"days")
print(g.to_string(index=False) if len(g) else "  none")
print("\n"+"="*128); print("BEATS BASELINE ON PAYOUT *AND* SPEED, BUST NO WORSE"); print("="*128)
w2=o[(o.paid>base["paid"])&(o.days<base["days"])&(o.bust<=base["bust"])]
print(w2.sort_values("paid",ascending=False).to_string(index=False) if len(w2) else "  none")
