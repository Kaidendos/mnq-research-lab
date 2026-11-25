"""TIMEFRAME — the last untouched axis. Everything in this project is 5-minute bars.

Fifteen candidates have now been rejected on the 5-minute grid: three fold-in metrics,
708+ pairings, 576 exit configs, every signal constant, both structural knobs, a fade
family, an exhaustion family, long-only, short-only and short+short. The bar spacing
itself has never been varied, and it is not a cosmetic choice — it changes the signal
(a "close above a 100-pt level" on 15-min bars is a different event), the ATR the
brackets are sized from, and the number of decisions per session.

Two things are tested separately, because they are different claims:
  SIGNAL TF   generate entries on 15/30-min bars instead of 5
  ATR TF      keep 5-min entries but size the stop/target from a slower ATR, which
              is more stable and may be the real benefit without losing frequency

Clean-control edge and account outcome both reported, since a slower timeframe
trades less and the account punishes low frequency.
"""
import numpy as np, pandas as pd
import funded_search as fs, lucid_fast as LF, sim_trace as ST

def resample(d, rule):
    o = d.resample(rule).agg({"open":"first","high":"max","low":"min",
                              "close":"last","volume":"sum"}).dropna()
    return o

def enrich(d):
    """Minimal re-enrichment: only the columns the two signals and the sim need."""
    c,h,l = d["close"],d["high"],d["low"]
    pc=c.shift(1)
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    d=d.copy(); d["atr"]=tr.ewm(alpha=1/14,adjust=False).mean()
    d["eth"]=d.index.hour+d.index.minute/60.0
    d["_day"]=d.index.normalize()
    day=d["_day"]
    dh,dl=h.groupby(day).max(),l.groupby(day).min()
    dm=pd.Series(day,index=d.index)
    d["pdh"],d["pdl"]=dm.map(dh.shift(1)),dm.map(dl.shift(1))
    return d.dropna(subset=["atr"])

def build(d):
    c,o,v,atr,day=d["close"],d["open"],d["volume"],d["atr"],d["_day"]
    pc=c.shift(1); same=(day==day.shift(1)); lvl=np.floor(c/100.0)
    rvol=v/v.rolling(20).mean()
    el=(same&(lvl>np.floor(pc/100.0))&(c>=lvl*100.0+0.15*atr)&(c>o)&(rvol>1.0)).fillna(False).to_numpy(bool)
    so=o.groupby(day).transform("first"); pr=(d["pdh"]-d["pdl"]).abs()
    bod=d.groupby(day).cumcount(); hit=((c<so-0.5*pr)&(bod>0)).fillna(False)
    return el,(hit&(hit.groupby(day).cumsum()==1)).to_numpy(bool)

base=fs.load_enriched()
end=base.index[-1]; cut=end-pd.DateOffset(months=5)
raw=base[["open","high","low","close","volume"]]
print("="*112); print("SIGNAL TIMEFRAME — same two rules generated on slower bars"); print("="*112)
print(f"  {'tf':>6}{'bars':>9}{'long_n':>8}{'short_n':>8}{'paid':>7}{'bust':>7}{'mean':>9}{'med':>8}{'days':>6}{'rec_mean':>10}")
for rule,lbl in (("5min","5m"),("15min","15m"),("30min","30m")):
    d = enrich(raw if rule=="5min" else resample(raw,rule))
    d = d[(d["eth"]>=9.5)&(d["eth"]<16.0)]
    hold=d[d.index<cut]; rec=d[d.index>=cut]
    eh,es_=build(hold); er,esr=build(rec)
    Ph=LF.prep(hold,eh,es_,(9.75,11.0)); Pr=LF.prep(rec,er,esr,(9.75,11.0))
    oh=[ST.trace(Ph,k,440,300) for k in range(0,len(Ph["per"]),4) if len(Ph["per"])-k>=20]
    orr=[ST.trace(Pr,k,440,300) for k in range(0,len(Pr["per"]),4) if len(Pr["per"])-k>=20]
    h=ST.summarise(oh); rc=ST.summarise(orr) if orr else {"mean":0}
    print(f"  {lbl:>6}{len(d):>9,}{int(eh.sum()):>8}{int(es_.sum()):>8}"
          f"{h['paid']:>7.1f}{h['bust']:>7.1f}{h['mean']:>9,.0f}{h['med']:>8,.0f}{h['days']:>6}{rc['mean']:>10,.0f}",flush=True)
print("\n"+"="*112); print("ATR TIMEFRAME — 5-min entries, brackets sized from a SLOWER ATR"); print("="*112)
print(f"  {'atr_len':>8}{'~equiv':>9}{'paid':>7}{'bust':>7}{'mean':>9}{'med':>8}{'days':>6}{'rec_mean':>10}")
d5=fs.load_enriched()
for mult,lbl in ((1,"5m ATR14"),(3,"15m"),(6,"30m"),(12,"60m")):
    d=d5.copy()
    c,h_,l_=d["close"],d["high"],d["low"]; pc=c.shift(1)
    tr=pd.concat([h_-l_,(h_-pc).abs(),(l_-pc).abs()],axis=1).max(axis=1)
    d["atr"]=tr.ewm(alpha=1/(14*mult),adjust=False).mean()
    hold=d[d.index<cut]; rec=d[d.index>=cut]
    eh,es_=build(hold); er,esr=build(rec)
    Ph=LF.prep(hold,eh,es_,(9.75,11.0)); Pr=LF.prep(rec,er,esr,(9.75,11.0))
    oh=[ST.trace(Ph,k,440,300) for k in range(0,len(Ph["per"]),4) if len(Ph["per"])-k>=20]
    orr=[ST.trace(Pr,k,440,300) for k in range(0,len(Pr["per"]),4) if len(Pr["per"])-k>=20]
    hh=ST.summarise(oh); rc=ST.summarise(orr) if orr else {"mean":0}
    print(f"  {14*mult:>8}{lbl:>9}{hh['paid']:>7.1f}{hh['bust']:>7.1f}{hh['mean']:>9,.0f}"
          f"{hh['med']:>8,.0f}{hh['days']:>6}{rc['mean']:>10,.0f}",flush=True)
