"""The same bootstrap, but for the user's ACTUAL position: $500 down.

The fresh-account bootstrap gave paid 25-75%, bust 0-16.7% at the 95th percentile.
The live account is already down, which halves the room to the floor ($500 instead of
$1,000) while leaving the payout buffer fixed at $26,100 — so the climb is $1,600
from half the cushion. The point estimate for that case was 34.7% paid / 0.0% bust,
but a point estimate is exactly what the fresh-account bootstrap just showed to be
untrustworthy, and the tail is what matters when the cushion is already half gone.

Run for -$0, -$250 and -$500 so the shape of the penalty is visible rather than a
single number.
"""
import numpy as np, pandas as pd
import funded_search as fs, funded_1yr as f1, lucid_fast as LF
from bootstrap_ci import day_net, PER, NS, BLOCK, SESSIONS_PER_ACCOUNT
N_PATHS, ACCOUNTS = 300, 12
def run(order, deficit):
    bal=LF.START-deficit; floor=LF.START-LF.MLL; locked=False
    cyc_d=cyc_p=cyc_b=0.0; cyc_d=0; wd=0.0; npay=0
    for k in order:
        net,ntr=day_net(k,bal,floor)
        if ntr==0: continue
        bal+=net; cyc_d+=1; cyc_p+=net; cyc_b=max(cyc_b,net)
        if bal<=floor: return "BUST",wd,npay
        if not locked:
            floor=max(floor,bal-LF.MLL)
            if bal>=LF.BUFFER: floor,locked=LF.LOCK_FLOOR,True
        if bal>LF.BUFFER and cyc_d>=LF.MIN_DAYS and cyc_p>0 and cyc_b<=LF.CONSISTENCY*cyc_p:
            amt=min(bal-LF.BUFFER, LF.CAP_FIRST if npay==0 else LF.CAP_AFTER)
            if amt>=250:
                bal-=amt; wd+=amt; npay+=1; cyc_d,cyc_p,cyc_b=0,0.0,0.0
    return ("PAID" if npay else "STALLED"),wd,npay
nb=SESSIONS_PER_ACCOUNT//BLOCK
print("="*100); print(f"BLOCK BOOTSTRAP BY STARTING DEFICIT — {N_PATHS} paths x {ACCOUNTS} accounts"); print("="*100)
print(f"  {'deficit':>9}{'room':>8}   {'paid 5/50/95':>22}{'bust 5/50/95':>22}{'mean 5/50/95':>26}")
for deficit in (0.0,250.0,500.0):
    rng=np.random.default_rng(7); rows=[]
    for _ in range(N_PATHS):
        fates=[];wds=[]
        for _ in range(ACCOUNTS):
            st=rng.integers(0,NS-BLOCK,size=nb)
            order=np.concatenate([np.arange(s,s+BLOCK) for s in st])
            f,w,_=run(order,deficit); fates.append(f); wds.append(w)
        wa=np.array(wds)
        rows.append(dict(paid=100*np.mean([f=="PAID" for f in fates]),
                         bust=100*np.mean([f=="BUST" for f in fates]),mean=wa.mean()))
    b=pd.DataFrame(rows)
    p=np.percentile(b.paid,[5,50,95]); bu=np.percentile(b.bust,[5,50,95]); m=np.percentile(b["mean"],[5,50,95])
    print(f"  {'-$'+str(int(deficit)):>9}{'$'+str(int(1000-deficit)):>8}   "
          f"{f'{p[0]:.0f} / {p[1]:.0f} / {p[2]:.0f}%':>22}"
          f"{f'{bu[0]:.0f} / {bu[1]:.0f} / {bu[2]:.0f}%':>22}"
          f"{f'${m[0]:,.0f} / ${m[1]:,.0f} / ${m[2]:,.0f}':>26}")
    b.to_csv(f"bootstrap_down_{int(deficit)}.csv",index=False)
    print(f"            paths with bust >10%: {100*(b.bust>10).mean():.1f}%   "
          f"paths where nobody paid: {100*(b.paid==0).mean():.1f}%",flush=True)
