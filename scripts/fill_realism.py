"""Are the 5-minute fill assumptions honest? Replay every trade on 1-MINUTE bars.

Every result in this project comes from a 5-minute replay that resolves a bar by
checking the STOP first and then the target. When a 5-min bar's range spans both
levels, that choice is a guess: the real sequence inside those five minutes decides
which one actually filled. Taking the stop is the pessimistic guess, but "how often
does the guess even matter" has never been measured for THIS strategy.

The same check was run for StochReclaim30 and found only 1 of 899 trades ambiguous,
so the expectation is that it is small here too. But that was a different strategy
with much tighter brackets (0.75/0.5 ATR vs 2.0/3.0), and wider brackets should be
harder to straddle — worth confirming rather than assuming.

Method: take every entry the 5-min strategy generates, then walk the 1-minute series
forward from the entry bar and resolve the exit at 1-minute resolution. Compare
trade by trade. Reports the ambiguous count, the P&L difference, and whether the
5-min assumption has been flattering the results.
"""
import numpy as np, pandas as pd
import funded_search as fs, funded_1yr as f1, lucid_fast as LF
WIN=(9.75,11.0); SL,TP=2.0,3.0
df=fs.load_enriched(); pl=f1.load_plugins(df)
end=df.index[-1]; hold=df[df.index<end-pd.DateOffset(months=5)]
g=lambda n: pd.Series((pl[n] if n in pl else fs.sig(df,n))[0]).reindex(hold.index).fillna(False).to_numpy(bool)
P=LF.prep(hold,g("sr_round100_break"),g("vol_lw_stretch_short"),WIN)
print("loading 1-minute series...",flush=True)
m1=pd.read_csv("data/databento/mnq_2021-2026_1min.csv.gz")
m1["ts_et"]=pd.to_datetime(m1["ts_et"],utc=True).dt.tz_convert(fs.TZ)
m1=m1.set_index("ts_et").sort_index()
hrs=m1.index.hour+m1.index.minute/60.0
m1=m1[(hrs>=9.5)&(hrs<16.0)]
print(f"  {len(m1):,} 1-min bars {m1.index[0].date()} -> {m1.index[-1].date()}",flush=True)
mh,ml,mc=m1["high"].to_numpy(float),m1["low"].to_numpy(float),m1["close"].to_numpy(float)
midx=m1.index
hi,lo,cl,atr,eth,per,dates=P["hi"],P["lo"],P["cl"],P["atr"],P["eth"],P["per"],P["dates"]
hidx=hold.index
rows=[];amb=0
for si,(s,e,idxs,sides) in enumerate(per):
    j,today=0,0
    while j<len(idxs) and today<6:
        i,sd=idxs[j],int(sides[j]); a,entry=atr[i],cl[i]
        stop_px,targ_px=entry-sd*a*SL,entry+sd*a*TP
        # ---- 5-min resolution (stop checked first) ----
        px5,m,straddle=None,i+1,False
        while m<e:
            hit_s = lo[m]<=stop_px if sd>0 else hi[m]>=stop_px
            hit_t = hi[m]>=targ_px if sd>0 else lo[m]<=targ_px
            if hit_s and hit_t: straddle=True
            if hit_s: px5=stop_px; break
            if hit_t: px5=targ_px; break
            if eth[m]>=16.0 or m==e-1: px5=cl[m]; break
            m+=1
        if px5 is None: px5,m=cl[e-1],e-1
        # ---- 1-min resolution over the same span ----
        # 5-min timestamps are the bar START (verified: 400/400 bars match the
        # 1-min bars in [t, t+5), 4/400 match (t-5, t]). Entry is at the CLOSE
        # of bar i, i.e. hidx[i] + 5 min. Scanning from hidx[i] let the stop be
        # hit by the four 1-min bars INSIDE the entry bar - price action that
        # happened before the position existed. That produced a spurious -32%.
        t0=hidx[i]+pd.Timedelta(minutes=5)
        t1=hidx[min(m,len(hidx)-1)]+pd.Timedelta(minutes=5)
        k0,k1=midx.searchsorted(t0,"left"),midx.searchsorted(t1,"right")
        px1=None
        for k in range(k0,min(k1,len(mh))):
            hs = ml[k]<=stop_px if sd>0 else mh[k]>=stop_px
            ht = mh[k]>=targ_px if sd>0 else ml[k]<=targ_px
            if hs and ht: px1=stop_px; break     # still ambiguous at 1-min
            if hs: px1=stop_px; break
            if ht: px1=targ_px; break
        if px1 is None: px1=px5
        amb+=straddle
        rows.append(dict(r5=sd*(px5-entry),r1=sd*(px1-entry),straddle=straddle))
        today+=1
        while j<len(idxs) and idxs[j]<=m: j+=1
r=pd.DataFrame(rows)
print("\n"+"="*96); print("FILL REALISM — 5-minute assumption vs 1-minute replay"); print("="*96)
print(f"  trades                       : {len(r)}")
print(f"  5-min bars straddling BOTH levels : {amb} ({100*amb/len(r):.1f}%)")
print(f"  trades where the exit DIFFERS     : {int((r.r5!=r.r1).sum())} ({100*(r.r5!=r.r1).mean():.1f}%)")
print(f"\n  points/trade at 5-min : {r.r5.mean():+.2f}")
print(f"  points/trade at 1-min : {r.r1.mean():+.2f}")
print(f"  difference            : {r.r1.mean()-r.r5.mean():+.2f} pts/trade "
      f"({100*(r.r1.mean()-r.r5.mean())/abs(r.r5.mean()):+.1f}%)")
print(f"\n  total 5-min : {r.r5.sum():+,.0f} pts")
print(f"  total 1-min : {r.r1.sum():+,.0f} pts")
print("\n  A negative difference means the 5-minute replay was FLATTERING the strategy.")
r.to_csv("fill_realism.csv",index=False)
