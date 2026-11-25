"""Definitive per-year verification of the RVOL loosening.

The 2-D grid produced an unusually clean result: 19 of 19 alternatives to the
default (rvol 1.0, vol_look 20) beat it, at 74-96% of 27 cells each, with median
d_mean between +$290 and +$664. A SMOOTH surface that is positive everywhere is a
very different object from the isolated spikes that killed eight candidates today —
it says the default setting is simply bad, not that one lucky cell was found.

Recent 5-month means (untouched, default $324) rise monotonically as the filter
loosens: $311 -> $839 -> $1,316, paid 46.7% -> 60.0%.

What is still missing is per-year consistency, which is where every weak candidate
has died. Four representative points are tested across 9 cells per year:

  (1.0, 40)  only the baseline WINDOW changes - the simplest possible edit, and the
             best holdout d_mean at +$664
  (0.9, 40)  central on both axes
  (0.7, 40)  best combination of holdout win% (85) and recent mean ($1,316)
  (0.9, 20)  the single best holdout win% (96%) but the WORST recent mean ($311),
             which is exactly the signature of a holdout artifact - included so that
             suspicion is tested rather than assumed
"""
import itertools, numpy as np, pandas as pd
import funded_search as fs, lucid_fast as LF, sim_trace as ST
WINDOWS=((9.75,11.0),(9.75,12.0),(9.75,15.5)); CAPS=(440,250,600)
POINTS=[("DEFAULT 1.0/20",1.0,20),("1.0/40",1.0,40),("0.9/40",0.9,40),
        ("0.7/40",0.7,40),("0.9/20",0.9,20)]
YRS=(2021,2022,2023,2024,2025,2026)
df=fs.load_enriched()
def build(frame,rv,vl):
    c,o=frame["close"],frame["open"]; v,atr,day=frame["volume"],frame["atr"],frame["_day"]
    pc=c.shift(1); same=(day==day.shift(1)); lvl=np.floor(c/100.0)
    rvol=v/v.rolling(vl).mean()
    el=(same&(lvl>np.floor(pc/100.0))&(c>=lvl*100.0+0.15*atr)&(c>o)&(rvol>rv)).fillna(False).to_numpy(bool)
    so=o.groupby(day).transform("first"); pr=(frame["pdh"]-frame["pdl"]).abs()
    bod=frame.groupby(day).cumcount(); hit=((c<so-0.5*pr)&(bod>0)).fillna(False)
    return el,(hit&(hit.groupby(day).cumsum()==1)).to_numpy(bool)
FR={f"y{y}":df[df.index.year==y] for y in YRS}
res={}
for nm,rv,vl in POINTS:
    for fn,frame in FR.items():
        if len(frame)<4000: continue
        el,es=build(frame,rv,vl)
        for win in WINDOWS:
            P=LF.prep(frame,el,es,win)
            for cap in CAPS:
                r=[ST.trace(P,k,cap,300,maxdays=180) for k in range(0,len(P["per"]),4) if len(P["per"])-k>=20]
                res[(nm,fn,win,cap)]=ST.summarise(r) if r else None
    print(f"  done {nm}",flush=True)
print("\n"+"="*112)
print("PER YEAR — cells won vs DEFAULT (9 cells per year: 3 windows x 3 caps, bud 300)")
print("="*112)
print(f"  {'variant':<16}"+"".join(f"{y:>10}"for y in YRS)+f"{'total':>9}")
for nm,rv,vl in POINTS[1:]:
    row=[];tot=0;totn=0
    for y in YRS:
        fn=f"y{y}";w=n=0
        for win,cap in itertools.product(WINDOWS,CAPS):
            a=res.get(("DEFAULT 1.0/20",fn,win,cap)); b=res.get((nm,fn,win,cap))
            if a and b: n+=1; w+= b["mean"]>a["mean"]
        row.append(f"{w}/{n}" if n else "-"); tot+=w; totn+=n
    print(f"  {nm:<16}"+"".join(f"{x:>10}"for x in row)+f"{f'{tot}/{totn}':>9}")
print("\n"+"="*112)
print("MEAN $ PER YEAR at 9:45-11:00 / cap440 / bud300")
print("="*112)
print(f"  {'variant':<16}"+"".join(f"{y:>10}"for y in YRS))
for nm,rv,vl in POINTS:
    vals=[res.get((nm,f"y{y}",(9.75,11.0),440)) for y in YRS]
    print(f"  {nm:<16}"+"".join(f"{(v['mean'] if v else 0):>10,.0f}"for v in vals))
print("\n"+"="*112); print("YEARS WITH A HIGHER MEAN THAN DEFAULT (at 9:45-11:00/cap440)"); print("="*112)
for nm,rv,vl in POINTS[1:]:
    b=sum(1 for y in YRS if (res.get((nm,f"y{y}",(9.75,11.0),440)) or {}).get("mean",0)
          > (res.get(("DEFAULT 1.0/20",f"y{y}",(9.75,11.0),440)) or {}).get("mean",0))
    print(f"  {nm:<16} {b}/{len(YRS)}")
