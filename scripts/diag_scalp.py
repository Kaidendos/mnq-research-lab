"""Why did scalp_1min produce 0 rows? Check firing rates and the gates."""
import numpy as np
import scalp_1min as S

d = S.load_1min(months=5)
sigs = S.signals(d)
eth = d["eth"].to_numpy()
inw = (eth >= 9.75) & (eth <= 15.5)

print(f"bars {len(d):,}   sessions {d['_day'].nunique()}\n")
print(f"{'signal':<20}{'fires':>7}{'fire%':>9}{'in-window':>11}")
print("-" * 48)
for k in sorted(sigs):
    a = sigs[k]
    print(f"{k:<20}{int(a.sum()):>7}{100*a.mean():>8.3f}%{int((a & inw).sum()):>11}")

print("\nGATE CHECK — harness skips a signal when in-window fires < 40")
for k in sorted(sigs):
    n = int((sigs[k] & inw).sum())
    print(f"  {k:<20}{n:>6}  {'SKIPPED' if n < 40 else 'ok'}")

print("\nEVALUATE CHECK on the best-firing signal")
best = max(sigs, key=lambda k: (sigs[k] & inw).sum())
side = 1 if best.endswith("_long") else -1
P = S.prep_ticks(d, sigs[best], side, (9.75, 15.5))
fires = sum(len(x[2]) for x in P["per"])
print(f"  {best}: prep fires={fires}, sessions={len(P['per'])}")
m = S.evaluate(P, 8, 8, 20, 300, 5, 1.0)
print(f"  evaluate -> {m}")
print("\n  NOTE: evaluate needs n >= 15 accounts; with stride=6 over "
      f"{len(P['per'])} sessions and a 25-session tail cut, "
      f"n ~= {max(0,(len(P['per'])-25)//6)}")
