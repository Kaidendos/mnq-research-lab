"""noise_lab2.py - round 2: fixed strategy settings, vary SIZING only, eval with no time limit.
Reuses noise_lab.py's data/strategy code (everything above its grid section).
Vol-target sizing: contracts = floor(budget / (expected full-day move in pts x $2)), min 1, max 40,
where expected move = 14-day mean |close-open| at 16:00 x today's open.
"""
import numpy as np, pandas as pd
src = open(r'C:\Users\YOU\daytrading-automation\noise_lab.py').read().split('# ---------------- grid')[0]
exec(src)

def account2(win, tl, sizing, cap, step, max_h):
    daily = []
    for d, tr in zip(win, tl):
        if sizing[0] == 'fixed': n = sizing[1]
        else: n = int(np.clip(sizing[1] // (d['sig'][-1] * d['o'][0] * 2), 1, 40))
        p = 0.
        for (_, _, _, g) in tr:
            if p <= -1200 or (cap and p >= cap): break
            p = max(-1200., p + (g - COST) * 2 * n)
        daily.append(p)
    daily = np.array(daily); res, dtp = [], []
    for s0 in range(0, len(daily) - 20, step):
        bal, floor, mx, best, out = 50000., 48000., 50000., 0., 'open'
        for q, p in enumerate(daily[s0:s0 + max_h]):
            bal += p
            if bal <= floor: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; dtp.append(q + 1); break
            mx = max(mx, bal); floor = 50100. if mx >= 52100 else max(floor, mx - 2000)
        res.append(out)
    n = len(res)
    return (100 * res.count('pass') / n, 100 * res.count('bust') / n, 100 * res.count('open') / n,
            float(np.median(dtp)) if dtp else np.nan, float(daily.sum()))

PARAMS = {'paper_default': (1.0, 30, 0, 'bandvwap', 930, 99, False),
          'tuned_family':  (1.25, 30, 0.005, 'vwap', 840, 2, False),
          'tuned_long':    (1.25, 30, 0.005, 'vwap', 840, 2, True)}
SIZES = [('fixed', 1), ('fixed', 2), ('fixed', 3), ('vol', 600), ('vol', 900), ('vol', 1200)]
rows = []
for pn, p in PARAMS.items():
    for sz in SIZES:
        for cap in (0, 600, 1000):
            r = dict(params=pn, sizing=f'{sz[0]}{sz[1]}', cap=cap)
            for wn, win, step, mh in (('y26', Y26, 2, 999), ('valid', VALID, 2, 999), ('old', OLD, 5, 250)):
                tl = [day_trades(d, *p) for d in win]
                ps, bs, op, dtp, usd = account2(win, tl, sz, cap, step, mh)
                r.update({f'{wn}_pass': ps, f'{wn}_bust': bs, f'{wn}_open': op, f'{wn}_days': dtp,
                          f'{wn}_usd': usd})
            rows.append(r)
            log(f"{pn:13s} {r['sizing']:8s} cap={cap:4d} | 2026 pass={r['y26_pass']:3.0f}% bust={r['y26_bust']:3.0f}% "
                f"days={r['y26_days']} ${r['y26_usd']:+7.0f} | May-Aug pass={r['valid_pass']:3.0f}% "
                f"bust={r['valid_bust']:3.0f}% | 2021-25 pass={r['old_pass']:3.0f}% bust={r['old_bust']:3.0f}% "
                f"days={r['old_days']}")
pd.DataFrame(rows).to_csv(BASE / 'noise_lab2.csv', index=False)
log('done')
