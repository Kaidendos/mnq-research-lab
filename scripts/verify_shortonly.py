"""Put SHORT-ONLY through the battery that killed nine other candidates.

`long_only.py` produced the session's most surprising result: the short side alone
beat both the long side alone AND the full pair on payout rate, with zero busts.

    long only    paid 38.1%  bust 1.0%  mean $973    med $0    36d
    SHORT only   paid 60.5%  bust 0.0%  mean $1,304  med $526  88d
    the pair     paid 56.0%  bust 2.1%  mean $2,352  med $334  27d

It also carried 2024 alone ($1,019 when the pair made $228). But that is ONE
observation at ONE cell, which is exactly the evidence standard that produced nine
false positives today. Before it becomes a recommendation:

  1. PAIRED ACROSS CELLS — short-only vs the pair over 27 cells. A real structural
     advantage should hold across caps, budgets and windows, not just one.
  2. PER YEAR — the pair wins on mean; the question is whether short-only wins on
     PAYOUT RATE and BUST consistently, which is what it appeared to do.
  3. BOOTSTRAP — the 0.0% bust needs an error bar. "Zero across 291 overlapping
     accounts on one path" is not the same as "zero risk", and the fresh-account
     bootstrap already showed the bust tail reaching 17% at the 95th percentile.
"""
import itertools, numpy as np, pandas as pd
import funded_search as fs, funded_1yr as f1, lucid_fast as LF, sim_trace as ST
WINDOWS=((9.75,11.0),(9.75,12.0),(9.75,15.5)); CAPS=(440,250,600); BUDGETS=(300,400,500)
YRS=(2021,2022,2023,2024,2025,2026)
df=fs.load_enriched(); pl=f1.load_plugins(df)
end=df.index[-1]; cut=end-pd.DateOffset(months=5)
FR={"hold":df[df.index<cut],"recent":df[df.index>=cut]}
for y in YRS: FR[f"y{y}"]=df[df.index.year==y]
r=lambda fr,n: pd.Series((pl[n] if n in pl else fs.sig(df,n))[0]).reindex(fr.index).fillna(False).to_numpy(bool)
CONF=[("PAIR",["sr_round100_break"],["vol_lw_stretch_short"]),
      ("SHORT ONLY",[],["vol_lw_stretch_short"])]
PREP={}
for nm,ls,ss in CONF:
    for fn,frame in FR.items():
        if len(frame)<4000 and fn.startswith("y"): continue
        el=np.zeros(len(frame),bool); es=np.zeros(len(frame),bool)
        for x in ls: el|=r(frame,x)
        for x in ss: es|=r(frame,x)
        for w in WINDOWS: PREP[(nm,fn,w)]=LF.prep(frame,el,es,w)
def sc(nm,fn,w,cap,bud,hz=365):
    P=PREP.get((nm,fn,w))
    if P is None: return None
    o=[ST.trace(P,k,cap,bud,maxdays=hz) for k in range(0,len(P["per"]),4) if len(P["per"])-k>=20]
    return ST.summarise(o) if o else None
cells=list(itertools.product(WINDOWS,CAPS,BUDGETS))
print("="*104); print("1. SHORT-ONLY vs THE PAIR ACROSS 27 CELLS (holdout)"); print("="*104)
wp=wb=wm=wmd=n=0
for c in cells:
    a=sc("PAIR","hold",*c); b=sc("SHORT ONLY","hold",*c)
    if not a or not b: continue
    n+=1; wp+= b["paid"]>a["paid"]; wb+= b["bust"]<a["bust"]
    wm+= b["mean"]>a["mean"]; wmd+= b["med"]>a["med"]
print(f"  short-only has HIGHER payout rate in : {wp}/{n} cells ({100*wp/n:.0f}%)")
print(f"  short-only has LOWER bust in         : {wb}/{n} cells ({100*wb/n:.0f}%)")
print(f"  short-only has HIGHER mean in        : {wm}/{n} cells ({100*wm/n:.0f}%)")
print(f"  short-only has HIGHER median in      : {wmd}/{n} cells ({100*wmd/n:.0f}%)")
print("\n"+"="*104); print("2. PER YEAR at 9:45-11:00 / cap440 / bud300"); print("="*104)
print(f"  {'metric':<22}"+"".join(f"{y:>11}" for y in YRS))
for lbl,key in (("PAIR paid%","paid"),("SHORT-ONLY paid%","paid"),
                ("PAIR bust%","bust"),("SHORT-ONLY bust%","bust"),
                ("PAIR mean $","mean"),("SHORT-ONLY mean $","mean")):
    nm="SHORT ONLY" if "SHORT" in lbl else "PAIR"
    vals=[(sc(nm,f"y{y}",(9.75,11.0),440,300,180) or {}).get(key,0) for y in YRS]
    print(f"  {lbl:<22}"+"".join(f"{v:>11,.1f}" for v in vals))
print("\n"+"="*104); print("3. BOOTSTRAP — error bar on short-only's 0.0% bust"); print("="*104)
from bootstrap_ci import PER as _unused_per
import bootstrap_ci as B
frame=FR["hold"]; el=np.zeros(len(frame),bool); es=r(frame,"vol_lw_stretch_short")
Pso=LF.prep(frame,el,es,(9.75,11.0))
B.PER=Pso["per"]; B.HI,B.LO,B.CL,B.ATR,B.ETH=Pso["hi"],Pso["lo"],Pso["cl"],Pso["atr"],Pso["eth"]
NS=len(Pso["per"]); rng=np.random.default_rng(3); rows=[]
for _ in range(250):
    fates=[];wds=[]
    for _ in range(12):
        st=rng.integers(0,NS-10,size=25)
        order=np.concatenate([np.arange(s,s+10) for s in st])
        f,w,_p=B.run_path(order); fates.append(f); wds.append(w)
    rows.append(dict(paid=100*np.mean([f=="PAID" for f in fates]),
                     bust=100*np.mean([f=="BUST" for f in fates]),mean=np.mean(wds)))
bb=pd.DataFrame(rows)
for col in ("paid","bust","mean"):
    p=np.percentile(bb[col],[5,50,95])
    print(f"  {col:<8} 5th {p[0]:>8.1f}   median {p[1]:>8.1f}   95th {p[2]:>8.1f}")
print(f"\n  paths with bust >10%: {100*(bb.bust>10).mean():.1f}%   "
      f"paths where nobody paid: {100*(bb.paid==0).mean():.1f}%")
