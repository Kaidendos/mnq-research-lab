"""The last untouched structural knobs: trades-per-day cap and sub-windows.

Two settings have been fixed at their inherited values through every sweep in this
project and never questioned:

  MAX TRADES/DAY = 6   Never swept. It interacts directly with the daily loss
                       budget: a lower cap means the budget is spread over fewer,
                       earlier trades. Given that adding signals always HURT (three
                       fold-ins rejected, all 0-19%), the account clearly dislikes
                       trade volume — so the cap may already be too high.
  WINDOW 9:45-11:00    Established as better than later starts, but never split
                       INSIDE. If the edge is concentrated in the first 30 minutes,
                       a tighter window is free risk reduction.

Both tested paired against the incumbent across caps and budgets, with per-year
counts, because per-year consistency is where every weak candidate has died.
"""
import itertools, numpy as np, pandas as pd
import funded_search as fs, funded_1yr as f1, lucid_fast as LF, sim_trace as ST
LONG,SHORT="sr_round100_break","vol_lw_stretch_short"
CAPS=(440,250,600); BUDGETS=(300,400)
TRADE_CAPS=(1,2,3,4,6,8)
SUBWINS=[(9.75,10.25),(9.75,10.5),(9.75,10.75),(9.75,11.0),(9.75,11.5),(10.0,11.0)]
YRS=(2021,2022,2023,2024,2025,2026)
df=fs.load_enriched(); pl=f1.load_plugins(df)
end=df.index[-1]; cut=end-pd.DateOffset(months=5)
FR={"hold":df[df.index<cut],"recent":df[df.index>=cut]}
for y in YRS: FR[f"y{y}"]=df[df.index.year==y]
r=lambda fr,n: pd.Series((pl[n] if n in pl else fs.sig(df,n))[0]).reindex(fr.index).fillna(False).to_numpy(bool)
P={}
for fn,frame in FR.items():
    if len(frame)<4000 and fn.startswith("y"): continue
    el,es=r(frame,LONG),r(frame,SHORT)
    for w in SUBWINS: P[(fn,w)]=LF.prep(frame,el,es,w)
def sc(fn,w,cap,bud,mt,hz=365):
    Q=P.get((fn,w))
    if Q is None: return None
    res=[ST.trace(Q,k,cap,bud,maxdays=hz,max_trades=mt) for k in range(0,len(Q["per"]),4) if len(Q["per"])-k>=20]
    return ST.summarise(res) if res else None
print("="*112); print("A. MAX TRADES/DAY at 9:45-11:00 (incumbent = 6)"); print("="*112)
print(f"  {'max_tr':>7}{'paid':>8}{'bust':>7}{'mean':>9}{'med':>8}{'days':>6}{'rec_mean':>10}{'yrs>6':>8}")
b6={y:sc(f"y{y}",(9.75,11.0),440,300,6,180) for y in YRS}
for mt in TRADE_CAPS:
    h=sc("hold",(9.75,11.0),440,300,mt); rc=sc("recent",(9.75,11.0),440,300,mt)
    better=sum(1 for y in YRS if (sc(f"y{y}",(9.75,11.0),440,300,mt,180) or {}).get("mean",0)>(b6[y] or {}).get("mean",0))
    print(f"  {mt:>7}{h['paid']:>8.1f}{h['bust']:>7.1f}{h['mean']:>9,.0f}{h['med']:>8,.0f}{h['days']:>6}{rc['mean']:>10,.0f}{better:>7}/6")
print("\n"+"="*112); print("B. SUB-WINDOWS at max 6 trades (incumbent = 9:45-11:00)"); print("="*112)
print(f"  {'window':>13}{'paid':>8}{'bust':>7}{'mean':>9}{'med':>8}{'days':>6}{'rec_mean':>10}{'yrs>base':>10}")
bw={y:sc(f"y{y}",(9.75,11.0),440,300,6,180) for y in YRS}
for w in SUBWINS:
    h=sc("hold",w,440,300,6); rc=sc("recent",w,440,300,6)
    better=sum(1 for y in YRS if (sc(f"y{y}",w,440,300,6,180) or {}).get("mean",0)>(bw[y] or {}).get("mean",0))
    print(f"  {f'{w[0]}-{w[1]}':>13}{h['paid']:>8.1f}{h['bust']:>7.1f}{h['mean']:>9,.0f}{h['med']:>8,.0f}{h['days']:>6}{rc['mean']:>10,.0f}{better:>9}/6")
print("\n"+"="*112); print("C. PAIRED: each trade cap vs 6, across 6 cap/budget cells"); print("="*112)
cells=list(itertools.product(CAPS,BUDGETS))
base={c:sc("hold",(9.75,11.0),c[0],c[1],6) for c in cells}
for mt in TRADE_CAPS:
    if mt==6: continue
    w=0;dm=[]
    for c in cells:
        a=base[c]; x=sc("hold",(9.75,11.0),c[0],c[1],mt)
        if a and x: dm.append(x["mean"]-a["mean"]); w+= x["mean"]>a["mean"]
    print(f"  max_tr {mt}: wins {w}/{len(dm)}  d_mean ${np.median(dm):+,.0f}")
