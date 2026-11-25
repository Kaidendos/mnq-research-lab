"""size7.py - what happens at 7 MNQ fixed: news fade (steadiest version) and EMA pullback, 2026."""
import numpy as np, pandas as pd
src = open(r'C:\Users\YOU\daytrading-automation\news_v2.py').read().split('GRID = list(')[0]
exec(src)
print('=== NEWS FADE (T+5, stop 1x release-bar range, 50% retrace target, 60 min max), Feb 18 - Jul 15 ===')
tr = [(t, *r) for t in EVT for r in [trade(t, 5, 0, 'r1.0', 'half', 60)] if r]
for ncon in (3, 5, 7):
    by = {}
    for t, pts, sd in tr: by[t.date()] = max(-1200., by.get(t.date(), 0.) + pts * 2 * ncon)
    res = []
    for s0 in range(0, len(TDAYS) - 10):
        bal, fl, mx, best, out = 50000., 48000., 50000., 0., 'open'
        for x in TDAYS[s0:]:
            p = by.get(x, 0.); bal += p
            if bal <= fl: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
        res.append(out)
    v = np.array(list(by.values())); eq = np.cumsum([by.get(x, 0.) for x in TDAYS])
    big = sum(1 for _, _, sd in tr if sd * 2 * ncon > 1200)
    print(f'{ncon} MNQ: net ${v.sum():+,.0f} | worst trade ${v.min():+,.0f} | best ${v.max():+,.0f} | maxDD ${(eq-np.maximum.accumulate(eq)).min():,.0f} | '
          f'full-stop > $1,200 DLL on {big}/{len(tr)} trades | eval pass {100*res.count("pass")/len(res):.0f}% bust {100*res.count("bust")/len(res):.0f}%')
