"""size_opt.py - optimal MNQ sizes for day plan + London breakout, Feb 18 - Jul 15 2026 (news-legal).
Grid: EMA base {2,3,4,5}; EMA step-up {+0,+1,+2} once eval profit >= {1000,1500}; news fade {0,2,3,4,5};
VWAP3 {0,1,2,3}; London breakout (both, 2/2 ATR) {0,2,3,4}. Max 40 MNQ total respected (never close).
Scores: Feb-Apr (TUNE), May-Jul (VALID), whole window with >=60 days runway (ALL), and STRESS = ALL with double
slippage (+1.1 pts per contract per trade). Ranked on TUNE only; robust = 0% bust in TUNE, VALID, ALL and STRESS."""
import numpy as np, pandas as pd, itertools
src = open(r'C:\Users\YOU\daytrading-automation\merge_night.py').read().split("print('=== DAY PLAN + NIGHT ===')")[0]
exec(src)
LBN = night('london_break|both|2/2')
COMP = {'ema': base_news, 'fade': NEWSFADE, 'vw': VW3, 'lb': LBN}
def arrays(days, extra_cost=0.0):
    out = {}
    for k_, trs in COMP.items():
        by = {}
        for dd_, pts, sd in trs: by[dd_] = by.get(dd_, 0.) + (pts - extra_cost) * 2
        out[k_] = np.array([by.get(x, 0.) for x in days])
    return out
WIN = {'TUNE': (TD, 0, 0.0), 'VALID': (VD, 0, 0.0), 'ALL': (DAYS, 60, 0.0), 'STRESS': (DAYS, 60, 1.1)}
ARR = {k_: arrays(v[0], v[2]) for k_, v in WIN.items()}
def ev(comps, days, rule, runway):
    res = []
    for s0 in range(0, len(days) - 5):
        if len(days) - s0 < runway: break
        bal, fl, mx, best, out, nd, worst_dd = 50000., 48000., 50000., 0., 'open', 0, 0.
        for k in range(s0, len(days)):
            nd += 1; sz = rule(bal - 50000)
            p = max(-1200., sum(sz[n] * comps[n][k] for n in sz)); bal += p
            if bal <= fl: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
        res.append((out, nd))
    n = max(1, len(res)); pas = [r[1] for r in res if r[0] == 'pass']
    return 100 * len(pas) / n, 100 * sum(r[0] == 'bust' for r in res) / n, (float(np.median(pas)) if pas else np.nan)
rows = []
for eb, up, at, fd, vw, lb in itertools.product((2, 3, 4, 5), (0, 1, 2), (1000, 1500), (0, 2, 3, 4, 5), (0, 1, 2, 3), (0, 2, 3, 4)):
    if up == 0 and at == 1500: continue
    rule = lambda p, eb=eb, up=up, at=at, fd=fd, vw=vw, lb=lb: {'ema': eb + (up if p >= at else 0), 'fade': fd, 'vw': vw, 'lb': lb}
    r = dict(ema=eb, step=f'+{up}@{at}' if up else 'none', fade=fd, vwap3=vw, london=lb)
    for wn, (days, rw, _) in WIN.items():
        p, b, md = ev(ARR[wn], days, rule, rw); r[f'{wn}_pass'], r[f'{wn}_bust'], r[f'{wn}_days'] = p, b, md
    eq = np.cumsum(sum(rule(0)[k_] * ARR['ALL'][k_] for k_ in COMP)); r['maxDD_base'] = float((eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min())
    r['worst_day'] = float(min(max(-1200, x) for x in sum(rule(5000)[k_] * ARR['ALL'][k_] for k_ in COMP)))
    rows.append(r)
X = pd.DataFrame(rows); X.to_csv(BASE + r'\size_opt.csv', index=False)
X['tscore'] = X.TUNE_pass - 3 * X.TUNE_bust
pd.set_option('display.width', 320); pd.set_option('display.max_columns', 30)
c = ['ema', 'step', 'fade', 'vwap3', 'london', 'TUNE_pass', 'TUNE_bust', 'TUNE_days', 'VALID_pass', 'VALID_bust', 'VALID_days',
     'ALL_pass', 'ALL_bust', 'ALL_days', 'STRESS_pass', 'STRESS_bust', 'STRESS_days', 'maxDD_base', 'worst_day']
cur = X[(X.ema == 3) & (X.step == '+1@1000') & (X.fade == 3) & (X.vwap3 == 1) & (X.london == 0)]
print('CURRENT PLAN:'); print(cur[c].round(1).to_string(index=False))
print(f'\n{len(X)} size combinations. TOP 12 BY FEB-APR (pass - 3x bust):')
print(X.sort_values(['tscore', 'TUNE_days'], ascending=[False, True]).head(12)[c].round(1).to_string(index=False))
R = X[(X.TUNE_bust == 0) & (X.VALID_bust == 0) & (X.ALL_bust == 0) & (X.STRESS_bust == 0)]
print(f'\nROBUST (0% bust in Feb-Apr, May-Jul, all, AND double slippage): {len(R)} of {len(X)}. Fastest 15 by ALL median days:')
print(R.sort_values(['ALL_days', 'STRESS_days']).head(15)[c].round(1).to_string(index=False))
X['total_base'] = X.ema + X.fade + X.vwap3 + X.london
print('\nBUST RATE vs TOTAL BASE SIZE (mean over combos, ALL / STRESS):')
print(X.groupby('total_base')[['ALL_bust', 'STRESS_bust', 'ALL_days']].mean().round(1).to_string())
