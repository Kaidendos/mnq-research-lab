"""Account-level paired test of the one survivor, plus the untested SHORT+SHORT book.

The exhaustion sweep gave two clean answers and one candidate.

ANSWER 1 - exhaustion shorts do not survive being made frequent. The edge was in
the extreme tail and dilutes the moment the threshold loosens:
    RSI(2) th=90  +22.56 on  56 trades   (from the earlier sweep)
    RSI(2) th=88   +7.54 on  81 trades
    RSI(5)         +2.15 on 113 trades
    RSI(9)         -4.70 on 155 trades
    RSI(14)        -5.37 on 196 trades
and the whole blow-off family is negative at every strictness (-1.99 to -4.29,
beaten 7-9/10), so `hi_blowoff_short`'s +14.80 on 48 trades was small-sample noise.

ANSWER 2 - the multi-day washout long fails too, and DEEPER IS WORSE AGAIN:
    3d -3.83  / deep -6.44      5d -9.58 / deep -11.43     10d -5.48 / deep -12.07
all beaten 6-9/10. Combined with the intraday sweep, "buy the low" now fails at
BOTH timescales and worsens monotonically with depth at both. That question is closed.

CANDIDATE - `ex_streak5_short`: five consecutive up-closes, then a down-close.
230 trades (the incumbent short has 225), edge +6.31, beaten 1/10, total edge 1,452.
It clears the stated bar, and only 2 of 26 rows did - the other being the incumbent.
Its per-trade edge also exceeds the incumbent LONG's (+4.74).

Also tested here: SHORT + SHORT with no long at all. Never tried. The shorts carry
the edge, every fold-in onto the long+short pair has failed, and a two-short book is
a different structure rather than another addition to the same one.
"""
import itertools, numpy as np, pandas as pd
import funded_search as fs, funded_1yr as f1, lucid_fast as LF, sim_trace as ST
WINDOWS=((9.75,11.0),(9.75,12.0),(9.75,15.5)); CAPS=(440,250,600); BUDGETS=(300,400,500)
YRS=(2022,2023,2024,2025,2026)
L,S="sr_round100_break","vol_lw_stretch_short"
CONF=[("PAIR (baseline)",[L],[S]),
      ("+S ex_streak5",[L],[S,"ex_streak5_short"]),
      ("+S ex_streak4",[L],[S,"ex_streak4_short"]),
      ("+S ex_rsi3",[L],[S,"ex_rsi3_short"]),
      ("replace S with streak5",[L],["ex_streak5_short"]),
      ("SHORT+SHORT (no long)",[],[S,"ex_streak5_short"]),
      ("SHORT+SHORT+SHORT",[],[S,"ex_streak5_short","ex_rsi3_short"])]
df=fs.load_enriched(); pl=f1.load_plugins(df)
end=df.index[-1]; cut=end-pd.DateOffset(months=5)
FR={"hold":df[df.index<cut],"recent":df[df.index>=cut]}
for y in YRS: FR[f"y{y}"]=df[df.index.year==y]
r=lambda fr,n: pd.Series((pl[n] if n in pl else fs.sig(df,n))[0]).reindex(fr.index).fillna(False).to_numpy(bool)
PREP={}
for nm,ls,ss in CONF:
    for fn,frame in FR.items():
        el=np.zeros(len(frame),bool); es=np.zeros(len(frame),bool)
        for x in ls: el|=r(frame,x)
        for x in ss: es|=r(frame,x)
        for w in WINDOWS: PREP[(nm,fn,w)]=LF.prep(frame,el,es,w)
def sc(nm,fn,w,cap,bud,hz=365):
    P=PREP[(nm,fn,w)]
    o=[ST.trace(P,k,cap,bud,maxdays=hz) for k in range(0,len(P["per"]),4) if len(P["per"])-k>=20]
    return ST.summarise(o) if o else None
print("="*118); print("1. HEADLINE at 9:45-11:00 / cap440 / bud300"); print("="*118)
print(f"  {'config':<26}{'paid':>7}{'bust':>7}{'mean':>9}{'med':>8}{'days':>6}{'rec_mean':>10}{'rec_paid':>10}")
for nm,_,_ in CONF:
    h=sc(nm,"hold",(9.75,11.0),440,300); rc=sc(nm,"recent",(9.75,11.0),440,300)
    print(f"  {nm:<26}{h['paid']:>7.1f}{h['bust']:>7.1f}{h['mean']:>9,.0f}{h['med']:>8,.0f}{h['days']:>6}{rc['mean']:>10,.0f}{rc['paid']:>10.1f}")
print("\n"+"="*118); print("2. PAIRED ACROSS 27 CELLS vs the baseline pair"); print("="*118)
cells=list(itertools.product(WINDOWS,CAPS,BUDGETS))
base={c:sc("PAIR (baseline)","hold",*c) for c in cells}
for nm,_,_ in CONF[1:]:
    dm=[];w=0;wb=0
    for c in cells:
        a=base[c]; b=sc(nm,"hold",*c)
        if a and b: dm.append(b["mean"]-a["mean"]); w+= b["mean"]>a["mean"]; wb+= b["bust"]<=a["bust"]
    print(f"  {nm:<26} mean wins {w:>2}/{len(dm)} ({100*w/len(dm):>3.0f}%)  d_mean ${np.median(dm):>+7,.0f}  bust no worse {wb}/{len(dm)}")
print("\n"+"="*118); print("3. PER YEAR mean $ (180d horizon)"); print("="*118)
print(f"  {'config':<26}"+"".join(f"{y:>11}" for y in YRS))
for nm,_,_ in CONF:
    print(f"  {nm:<26}"+"".join(f"{(sc(nm,f'y{y}',(9.75,11.0),440,300,180) or {}).get('mean',0):>11,.0f}" for y in YRS))
