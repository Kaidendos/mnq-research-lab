"""Fine 2-D verification of the two parameter changes that survived at 81%.

From the 27-cell paired toggle:
    rvol 1.0 -> 0.8    81% of cells, d_mean +$274, d_bust -0.4
    vol_look 20 -> 40  81% of cells, d_mean +$641, d_bust  0.0
    buf 0.15 -> 0.10   52%  - coin flip, rejected
    LW_K 0.50 -> 0.35   4%  - decisively rejected (total edge said it was better;
                              the account says no, because the cap and budget bind)

81% sits between the 67% that was rejected and the 96% that was trusted, so it needs
more than one grid point. Two things settle it:

  1. Is there a SMOOTH optimum, or is 0.8/40 an isolated spike? A real parameter
     effect varies gradually; a fitted one does not. Hence the finer 2-D grid.
  2. Do the two changes COMBINE? They both loosen the same RVOL filter (its
     threshold and its baseline window), so they may be redundant rather than additive.

Win% is against the DEFAULT (rvol 1.0, vol_look 20) on the identical 27 cells.
"""
import argparse, itertools, numpy as np, pandas as pd
import funded_search as fs, lucid_fast as LF, sim_trace as ST
WINDOWS=((9.75,11.0),(9.75,12.0),(9.75,15.5)); CAPS=(440,250,600); BUDGETS=(300,400,500)
ap=argparse.ArgumentParser(); ap.add_argument("--slice"); ap.add_argument("--out",required=True)
a=ap.parse_args()
df=fs.load_enriched(); end=df.index[-1]; cut=end-pd.DateOffset(months=5)
FR={"hold":df[df.index<cut],"recent":df[df.index>=cut]}
def build(frame, rvol_th, vol_look):
    c,o=frame["close"],frame["open"]; v,atr,day=frame["volume"],frame["atr"],frame["_day"]
    pc=c.shift(1); same=(day==day.shift(1)); lvl=np.floor(c/100.0)
    rvol=v/v.rolling(vol_look).mean()
    el=(same&(lvl>np.floor(pc/100.0))&(c>=lvl*100.0+0.15*atr)&(c>o)&(rvol>rvol_th)).fillna(False).to_numpy(bool)
    so=o.groupby(day).transform("first"); pr=(frame["pdh"]-frame["pdl"]).abs()
    bod=frame.groupby(day).cumcount(); hit=((c<so-0.5*pr)&(bod>0)).fillna(False)
    return el,(hit&(hit.groupby(day).cumsum()==1)).to_numpy(bool)
combos=list(itertools.product((0.7,0.8,0.9,1.0),(20,30,40,50,60)))
if a.slice:
    i,k=(int(x) for x in a.slice.split("/")); combos=combos[i::k]
cells=list(itertools.product(WINDOWS,CAPS,BUDGETS))
def prep_all(rv,vl):
    out={}
    for w,f in FR.items():
        el,es=build(f,rv,vl)
        for win in WINDOWS: out[(w,win)]=LF.prep(f,el,es,win)
    return out
def sc(P,w,win,cap,bud,hz=365):
    Q=P[(w,win)]
    r=[ST.trace(Q,k,cap,bud,maxdays=hz) for k in range(0,len(Q["per"]),6) if len(Q["per"])-k>=20]
    return ST.summarise(r) if r else None
BASE=prep_all(1.0,20)
base={c: sc(BASE,"hold",*c) for c in cells}
base_rec=sc(BASE,"recent",(9.75,11.0),440,300)
rows=[]
for rv,vl in combos:
    P=prep_all(rv,vl)
    dm=[];wins=0
    for c in cells:
        b=sc(P,"hold",*c); x=base[c]
        if b and x: dm.append(b["mean"]-x["mean"]); wins+=b["mean"]>x["mean"]
    rec=sc(P,"recent",(9.75,11.0),440,300)
    rows.append(dict(rvol=rv,vol_look=vl,cells=len(dm),mean_wins=wins,
        win_pct=round(100*wins/max(len(dm),1)),d_mean=round(float(np.median(dm))),
        rec_mean=rec["mean"] if rec else 0,rec_paid=rec["paid"] if rec else 0))
    pd.DataFrame(rows).to_csv(a.out,index=False)
    print(f"  rvol{rv} vl{vl}: {wins}/{len(dm)} ({100*wins/max(len(dm),1):.0f}%) d_mean {np.median(dm):+.0f} rec ${rec['mean'] if rec else 0}",flush=True)
print(f"\nBASE recent mean ${base_rec['mean'] if base_rec else 0}, paid {base_rec['paid'] if base_rec else 0}%")
