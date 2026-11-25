"""Random-entry control for pdh_fade_short 1.25/1.0 9.75-15.5 gate_ema50 cap440."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\YOU\daytrading-automation")
from funded_search import load_enriched, replay, payout_sim, sig, evaluate, SPLIT

CFG = dict(family="pdh_fade_short", sl=1.25, tp=1.0, win=(9.75, 15.5),
           gate="gate_ema50", cap=440, budget=300)
WS, WE = CFG["win"]

df = load_enriched()
ent, side = sig(df, CFG["family"])
ent = np.asarray(ent, bool)
print("side =", side)

eth = df["eth"].values
gate_day = df[CFG["gate"]].values.astype(bool)
dayid = df["_day"].values

# bars that could ever host an entry under this config
elig = gate_day & (eth >= WS) & (eth <= WE)
n_elig = int(elig.sum())
n_fire = int((ent & elig).sum())
print(f"eligible bars {n_elig:,}   real signal fires on eligible bars {n_fire:,}"
      f"   rate {n_fire/n_elig:.5f}")


def score(entry_arr):
    daily, ntr, nwin = replay(df, entry_arr, side, CFG["sl"], CFG["tp"], CFG["win"],
                              CFG["gate"], CFG["cap"], CFG["budget"])
    if len(daily) < 20:
        return dict(days=len(daily), trades=ntr, win_pct=0.0, net=float(daily.sum()),
                    payout=0.0, bust=100.0, med=-1)
    att, dtp, busts, _ = payout_sim(daily)
    return dict(days=len(daily), trades=ntr,
                win_pct=round(100*nwin/ntr, 1) if ntr else 0.0,
                net=round(float(daily.sum())),
                payout=round(100*len(dtp)/att, 1) if att else 0.0,
                bust=round(100*busts/att, 1) if att else 100.0,
                med=int(np.median(dtp)) if dtp else -1,
                att=att)


real = score(ent)
print("\nREAL:", real)

elig_idx = np.flatnonzero(elig)

# ---- Control A: uniform random over ALL eligible bars, same fire count ----
print("\n--- CONTROL A: uniform random entries over all eligible bars, n matched ---")
A = []
for seed in range(12):
    rng = np.random.default_rng(seed)
    pick = rng.choice(elig_idx, size=n_fire, replace=False)
    e = np.zeros(len(df), bool); e[pick] = True
    r = score(e); A.append(r)
    print(f"seed {seed:2d}  {r}")

# ---- Control B: day-matched — same days, same #signals/day, random bar in window ----
print("\n--- CONTROL B: same days & same signals-per-day, random bar times ---")
real_fire_idx = np.flatnonzero(ent & elig)
per_day = pd.Series(dayid[real_fire_idx]).value_counts()
elig_by_day = {}
for d, idxs in pd.Series(elig_idx).groupby(dayid[elig_idx]):
    elig_by_day[d] = idxs.values
B = []
for seed in range(12):
    rng = np.random.default_rng(1000 + seed)
    e = np.zeros(len(df), bool)
    for d, k in per_day.items():
        pool = elig_by_day.get(d)
        if pool is None or len(pool) == 0:
            continue
        e[rng.choice(pool, size=min(k, len(pool)), replace=False)] = True
    r = score(e); B.append(r)
    print(f"seed {seed:2d}  {r}")


def summ(tag, rows):
    for k in ("trades", "win_pct", "net", "payout", "bust", "med"):
        v = np.array([r[k] for r in rows], float)
        print(f"{tag} {k:8s} min {v.min():9.1f}  med {np.median(v):9.1f}  "
              f"max {v.max():9.1f}   REAL {real[k]:9.1f}")


print()
summ("A", A)
print()
summ("B", B)

pa = np.array([r["payout"] for r in A]); pb = np.array([r["payout"] for r in B])
print(f"\nreal payout {real['payout']} ; A beats-real count {(pa>=real['payout']).sum()}/{len(pa)}"
      f" ; B beats-real count {(pb>=real['payout']).sum()}/{len(pb)}")
na = np.array([r["net"] for r in A]); nb = np.array([r["net"] for r in B])
print(f"real net {real['net']} ; A net>=real {(na>=real['net']).sum()}/{len(na)}"
      f" ; B net>=real {(nb>=real['net']).sum()}/{len(nb)}")
