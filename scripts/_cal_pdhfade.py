import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\YOU\daytrading-automation")
from funded_search import load_enriched, replay, sig

df = load_enriched()
all_sessions = pd.Index(sorted(pd.unique(df["_day"])))
print("total RTH sessions in data:", len(all_sessions))

def run(cfg):
    ent, side = sig(df, cfg["family"])
    daily, ntr, nwin = replay(df, np.asarray(ent, bool), side, cfg["sl"], cfg["tp"],
                              cfg["win"], cfg.get("gate"), cfg.get("cap", 440),
                              cfg.get("budget", 300))
    return daily

CAND = dict(family="pdh_fade_short", sl=1.25, tp=1.0, win=(9.75, 15.5),
            gate="gate_ema50", cap=440, budget=300)
BASE = dict(family="stoch30_long", sl=0.75, tp=0.5, win=(9.75, 11.5),
            gate=None, cap=440, budget=300)

for tag, cfg in (("CANDIDATE pdh_fade_short", CAND), ("BASELINE stoch30_long", BASE)):
    daily = run(cfg)
    frac = len(daily) / len(all_sessions)
    print(f"\n=== {tag} ===")
    print(f"active days {len(daily)} / {len(all_sessions)} sessions = {100*frac:.1f}% "
          f"-> 1 active day per {1/frac:.2f} sessions")
    # calendar-aware payout walk from every active start
    vals = daily.values; idx = daily.index
    cal, act = [], []
    busts = att = 0
    for s in range(len(vals)):
        cum = peak = big = 0.0; out = None; d = 0
        for j in range(s, len(vals)):
            cum += vals[j]; d += 1
            peak = max(peak, cum); big = max(big, vals[j])
            if peak - cum >= 1000.0: out = "bust"; break
            if d >= 3 and cum >= 1100.0 and big <= 0.40*cum:
                out = d; break
        if out is None: continue
        att += 1
        if out == "bust": busts += 1
        else:
            act.append(out)
            cal.append((idx[j] - idx[s]).days)
    print(f"attempts {att}  payout {100*len(act)/att:.1f}%  bust {100*busts/att:.1f}%")
    print(f"  ACTIVE-day  median {np.median(act):.0f}   p90 {np.percentile(act,90):.0f}")
    print(f"  CALENDAR-day median {np.median(cal):.0f}   p25 {np.percentile(cal,25):.0f}"
          f"   p90 {np.percentile(cal,90):.0f}   max {max(cal)}")
    print(f"  share of payouts within 30 calendar days: "
          f"{100*np.mean(np.array(cal)<=30):.1f}%")
    print(f"  share within 60 calendar days: {100*np.mean(np.array(cal)<=60):.1f}%")

# sequential non-overlapping, calendar
print("\n=== CANDIDATE sequential non-overlapping attempts, CALENDAR dates ===")
daily = run(CAND); vals = daily.values; idx = daily.index
i = 0; nres = []
while i < len(vals):
    cum = peak = big = 0.0; out = None; d = 0
    for j in range(i, len(vals)):
        cum += vals[j]; d += 1
        peak = max(peak, cum); big = max(big, vals[j])
        if peak - cum >= 1000.0: out = ("BUST", d, j); break
        if d >= 3 and cum >= 1100.0 and big <= 0.40*cum: out = ("PAYOUT", d, j); break
    if out is None:
        print(f"  {idx[i].date()} -> (end) UNRESOLVED"); break
    print(f"  {idx[i].date()} -> {idx[out[2]].date()}  {out[0]:6s}  "
          f"{out[1]:3d} active days = {(idx[out[2]]-idx[i]).days:4d} CALENDAR days")
    nres.append(out); i = out[1] + i
span = (idx[-1] - idx[0]).days
p = sum(1 for o in nres if o[0]=="PAYOUT")
print(f"  -> {p} payouts over {span} calendar days = 1 payout per {span/p:.0f} calendar days")
print(f"  -> user target is 1 per 30 calendar days")
