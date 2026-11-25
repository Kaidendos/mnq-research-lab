"""Rank the fade family by CLEAN-CONTROL edge, with the incumbents as benchmarks.

Raw P&L on a long-biased book in a rising index is not evidence — that lesson cost
three attempts to learn earlier. So these are scored the only way that separates the
rule from the drift: real points per trade minus the median of shuffled controls that
trade the same number of times, on permuted sessions, at random bars.

Reported alongside TOTAL edge (edge x trades), because the account needs frequency
as well as quality — a rule that fires 40 times cannot climb $1,100 to the buffer.
"""
import argparse, numpy as np, pandas as pd, os
import funded_search as fs, funded_1yr as f1, lucid_fast as LF
SL,TP=2.0,3.0; WIN=(9.75,11.0); SEEDS=10; MIN_TR=30
ap=argparse.ArgumentParser(); ap.add_argument("--slice"); ap.add_argument("--out",required=True)
a=ap.parse_args()
df=fs.load_enriched(); pl=f1.load_plugins(df)
end=df.index[-1]; hold=df[df.index<end-pd.DateOffset(months=5)]
d_ids=pd.factorize(hold["_day"])[0]
starts=np.flatnonzero(np.r_[True,d_ids[1:]!=d_ids[:-1]]); ends=np.r_[starts[1:],len(d_ids)]
eth=hold["eth"].to_numpy(float); ok=(eth>=WIN[0])&(eth<=WIN[1])&(hold["atr"].to_numpy(float)>0)
def points(el,es):
    P=LF.prep(hold,el,es,WIN); hi,lo,cl,atr,ev=P["hi"],P["lo"],P["cl"],P["atr"],P["eth"]
    tot=0.0;n=0;w=0
    for s,e,idxs,sides in P["per"]:
        j=t=0
        while j<len(idxs) and t<6:
            i,sd=idxs[j],int(sides[j]); aa,en=atr[i],cl[i]
            sp,tp_=en-sd*aa*SL,en+sd*aa*TP; px=None;m=i+1
            while m<e:
                if sd>0:
                    if lo[m]<=sp: px=sp;break
                    if hi[m]>=tp_: px=tp_;break
                else:
                    if hi[m]>=sp: px=sp;break
                    if lo[m]<=tp_: px=tp_;break
                if ev[m]>=16.0 or m==e-1: px=cl[m];break
                m+=1
            if px is None: px,m=cl[e-1],e-1
            r=sd*(px-en); tot+=r;n+=1;w+=r>0;t+=1
            while j<len(idxs) and idxs[j]<=m: j+=1
    return tot,n,w
def shuf(mask,rng):
    prof=[int((mask[s:e]&ok[s:e]).sum()) for s,e in zip(starts,ends)]
    order=rng.permutation(len(prof)); out=np.zeros(len(mask),bool)
    for pos,(s,e) in enumerate(zip(starts,ends)):
        k=prof[order[pos]]
        if not k: continue
        slot=np.flatnonzero(ok[s:e])
        if len(slot): out[s+rng.choice(slot,size=min(k,len(slot)),replace=False)]=True
    return out
names=[n for n in pl if n.startswith(("ex_",))]+["sr_round100_break","vol_lw_stretch_short"]
if a.slice:
    i,k=(int(x) for x in a.slice.split("/")); names=names[i::k]
first=not os.path.exists(a.out)
for nm in names:
    e_,side=pl[nm] if nm in pl else fs.sig(df,nm)
    mask=pd.Series(e_).reindex(hold.index).fillna(False).to_numpy(bool)
    zero=np.zeros(len(mask),bool)
    el,es=(mask,zero) if side>0 else (zero,mask)
    tot,n,w=points(el,es)
    if n<MIN_TR: print(f"  skip {nm} ({n} trades)",flush=True); continue
    ctl=[]
    for s_ in range(SEEDS):
        sh=shuf(mask,np.random.default_rng(s_))
        a2,b2=(sh,zero) if side>0 else (zero,sh)
        t2,n2,_=points(a2,b2)
        if n2: ctl.append(t2/n2)
    edge=tot/n-float(np.median(ctl))
    pd.DataFrame([dict(family=nm,side=side,trades=n,win=round(100*w/n,1),
        ppt=round(tot/n,2),ctl=round(float(np.median(ctl)),2),edge=round(edge,2),
        total_edge=round(edge*n),beaten=int((np.array(ctl)>=tot/n).sum()))]).to_csv(
        a.out,mode="a",header=first,index=False)
    first=False
    print(f"  {nm:<30} n={n:>4} edge {edge:>+7.2f} total {edge*n:>+8.0f} beaten {int((np.array(ctl)>=tot/n).sum())}/{SEEDS}",flush=True)
