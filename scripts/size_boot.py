"""size_boot.py - block-bootstrap stress test of size choices (2,000 synthetic paths built from 5-day blocks of
the real Feb 18 - Jul 15 2026 daily P&L per contract), eval AND the funded phase after it.
Eval: EOD trail $2,000 -> lock $50,100, DLL $1,200, $3,000 target, 50% consistency, max 80 days.
Funded (after a pass, 60 trading days): fresh $50,000, INTRADAY trail $2,000 approximated with each day's worst
intraday point = min(0, day P&L) - 50% of that day's |losing trades| (conservative proxy), lock at $50,100; payouts
= anything above $52,100. Same sizes in funded. Analysis only."""
import numpy as np, pandas as pd
src = open(r'C:\Users\YOU\daytrading-automation\size_opt.py').read().split('rows = []')[0]
exec(src)
A_ = arrays(DAYS); A2 = arrays(DAYS, 1.1)
# per-day sum of losing trades per contract (for intraday dip proxy)
LOSS = {}
for k_, trs in COMP.items():
    by = {}
    for dd_, pts, sd in trs:
        if pts < 0: by[dd_] = by.get(dd_, 0.) + pts * 2
    LOSS[k_] = np.array([by.get(x, 0.) for x in DAYS])
CONFIGS = {'current 3(+1@1000)/3/1/0': (3, 1, 1000, 3, 1, 0), 'mid 4(+1@1500)/3/2/2': (4, 1, 1500, 3, 2, 2),
           'mid+ 4(+1@1500)/4/2/3': (4, 1, 1500, 4, 2, 3), 'high 5(+1@1500)/4/3/3': (5, 1, 1500, 4, 3, 3),
           'top 5(+2@1500)/5/3/4': (5, 2, 1500, 5, 3, 4), 'EMA-only 5': (5, 0, 1000, 0, 0, 0)}
rng = np.random.default_rng(42); ND = len(DAYS); NP = 2000
paths = [np.concatenate([np.arange(s, min(s + 5, ND)) for s in rng.integers(0, ND - 5, 30)])[:140] for _ in range(NP)]
def sizes(cfg, prof):
    eb, up, at, fd, vw, lb = cfg
    return {'ema': eb + (up if prof >= at else 0), 'fade': fd, 'vw': vw, 'lb': lb}
def sim(cfg, A, path):
    bal, fl, mx, best, k = 50000., 48000., 50000., 0., 0
    for k, ix in enumerate(path[:80]):
        sz = sizes(cfg, bal - 50000); p = max(-1200., sum(sz[n] * A[n][ix] for n in sz)); bal += p
        if bal <= fl: return 'bust', k + 1, None
        best = max(best, p); prof = bal - 50000
        if prof >= 3000 and best <= 0.5 * prof: break
        mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
    else: return 'open', 80, None
    # funded phase
    bal, fl, mx, start = 50000., 48000., 50000., k + 1
    for ix in path[start:start + 60]:
        sz = sizes(cfg, 0)
        p = max(-1200., sum(sz[n] * A[n][ix] for n in sz)); dip = min(0., p) + 0.5 * sum(sz[n] * LOSS[n][ix] for n in sz)
        if bal + min(dip, p) <= fl: return 'pass', start, ('bust', bal - 50000)
        bal += p; mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
    return 'pass', start, ('ok', max(0., bal - 52100))
rows = []
for nm, cfg in CONFIGS.items():
    for lab, A in (('normal slippage', A_), ('double slippage', A2)):
        R = [sim(cfg, A, p) for p in paths]
        pas = [r for r in R if r[0] == 'pass']; fb = [r for r in pas if r[2] and r[2][0] == 'bust']
        rows.append(dict(config=nm, costs=lab, eval_pass=100 * len(pas) / NP, eval_bust=100 * sum(r[0] == 'bust' for r in R) / NP,
                         median_days=np.median([r[1] for r in pas]) if pas else np.nan,
                         funded_bust_60d=100 * len(fb) / max(1, len(pas)),
                         funded_avg_withdrawable=np.mean([r[2][1] for r in pas if r[2][0] == 'ok']) if pas else np.nan))
pd.set_option('display.width', 250)
print(pd.DataFrame(rows).round(1).to_string(index=False))
