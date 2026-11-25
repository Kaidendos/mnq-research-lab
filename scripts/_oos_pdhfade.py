import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\YOU\daytrading-automation")
from funded_search import load_enriched, replay, payout_sim, sig

CFG = dict(family="pdh_fade_short", sl=1.25, tp=1.0, win=(9.75, 15.5),
           gate="gate_ema50", cap=440, budget=300)
WS, WE = CFG["win"]
df = load_enriched()
ent, side = sig(df, CFG["family"])
ent = np.asarray(ent, bool)
daily, ntr, nwin = replay(df, ent, side, CFG["sl"], CFG["tp"], CFG["win"],
                          CFG["gate"], CFG["cap"], CFG["budget"])
print("total days %d trades %d net %.0f" % (len(daily), ntr, daily.sum()))

print("\n=== NET / ACTIVE DAYS BY YEAR ===")
g = daily.groupby(daily.index.year)
tbl = pd.DataFrame({"days": g.size(), "net": g.sum().round(0),
                    "greendays": g.apply(lambda s: (s > 0).sum())})
print(tbl.to_string())

print("\n=== NET BY HALF-YEAR ===")
hy = daily.groupby([daily.index.year, (daily.index.month > 6).astype(int)])
print(hy.sum().round(0).to_string())

print("\n=== TOP 10 SINGLE DAYS (share of total net) ===")
tot = daily.sum()
top = daily.sort_values(ascending=False).head(10)
print(top.round(0).to_string())
print("top1 = %.1f%% of net ; top5 = %.1f%% ; top10 = %.1f%%"
      % (100*top.iloc[0]/tot, 100*top.head(5).sum()/tot, 100*top.sum()/tot))
print("net excluding top 5 days: %.0f" % (tot - top.head(5).sum()))
print("net excluding top 10 days: %.0f" % (tot - top.sum()))

SPLIT = "2025-02-01"
for tag, s in (("TRAIN <2025-02", daily[daily.index < SPLIT]),
               ("TEST  >=2025-02", daily[daily.index >= SPLIT])):
    att, dtp, busts, unres = payout_sim(s)
    print(f"\n=== {tag}: {len(s)} days, net {s.sum():.0f} ===")
    print(f"  attempts {att}  payouts {len(dtp)} ({100*len(dtp)/att if att else 0:.1f}%)"
          f"  busts {busts} ({100*busts/att if att else 0:.1f}%)  unresolved {unres}"
          f"  median {np.median(dtp) if dtp else -1}")

# non-overlapping sequential attempts (independent-ish sample size)
print("\n=== NON-OVERLAPPING SEQUENTIAL ATTEMPTS (real account behaviour) ===")
vals = daily.values; idx = daily.index
i = 0; res = []
while i < len(vals):
    cum = peak = biggest = 0.0; out = None; d = 0
    for j in range(i, len(vals)):
        cum += vals[j]; d += 1
        peak = max(peak, cum); biggest = max(biggest, vals[j])
        if peak - cum >= 1000.0:
            out = ("BUST", d); break
        if d >= 3 and cum >= 1100.0 and biggest <= 0.40 * cum:
            out = ("PAYOUT", d); break
    if out is None:
        print(f"  start {idx[i].date()}  UNRESOLVED after {len(vals)-i} days"); break
    res.append(out)
    print(f"  start {idx[i].date()}  {out[0]:6s} in {out[1]:3d} active days")
    i += out[1]
p = sum(1 for o in res if o[0] == "PAYOUT")
print(f"  -> {p} payouts / {len(res)} sequential attempts = {100*p/len(res):.0f}%")
