"""noise_lab.py - optimise Zarattini/Aziz/Barbon Noise Area momentum for the LucidDaily 50K eval.

Tune on 2026-01..04 (TUNE), validate on 2026-05..08-07 (VALID, never used for selection),
report all of 2026, and re-check finalists on 2021-2025 with a random-direction control.

Grid: k (band width), checkpoint spacing, hard stop (% of entry), exit rule, last entry time,
max trades/day, long-only vs both, contracts (MNQ), daily profit cap.
Account: EOD trail $2,000 (lock $50,100), DLL $1,200 intraday soft stop, $3,000 target,
50% consistency. Costs 1.1 pts/trade. Analysis only - no order execution.
"""
import numpy as np, pandas as pd, itertools, time
from pathlib import Path
BASE = Path(r'C:\Users\YOU\daytrading-automation')
COST = 1.1
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:5.0f}s]', *a, flush=True)

df = pd.read_csv(BASE / 'data/databento/mnq_2021-2026_5min.csv')
ts = pd.to_datetime(df.ts_et, utc=True).dt.tz_convert('America/New_York')
df['mins'] = (ts.dt.hour * 60 + ts.dt.minute).values; df['date'] = ts.dt.date.values
R = df[(df.mins >= 570) & (df.mins < 960)]
days = []
for dt, g in R.groupby('date', sort=True):
    if len(g) != 78 or g.mins.values[0] != 570: continue
    o, h, l, c, v = [g[k].values.astype(float) for k in ('open', 'high', 'low', 'close', 'volume')]
    vv = np.maximum(v, 1); tp = (h + l + c) / 3
    days.append(dict(date=dt, o=o, h=h, l=l, c=c, vw=np.cumsum(tp * vv) / np.cumsum(vv),
                     mv=np.abs(c / o[0] - 1)))
for i, d in enumerate(days):
    d['prevC'] = days[i-1]['c'][-1] if i else np.nan
    d['sig'] = np.mean([days[i-q]['mv'] for q in range(1, 15)], axis=0) if i >= 14 else None
D = lambda a, b: [d for d in days if pd.Timestamp(a).date() <= d['date'] <= pd.Timestamp(b).date()
                  and d['sig'] is not None]
TUNE, VALID, Y26, OLD = D('2026-01-01', '2026-04-30'), D('2026-05-01', '2026-08-07'), \
                        D('2026-01-01', '2026-08-07'), D('2021-09-01', '2025-12-31')
log('days: tune', len(TUNE), 'valid', len(VALID), '2026', len(Y26), '2021-25', len(OLD))
CKS = {30: [t for t in range(78) if (575 + 5 * t) % 30 == 0 and 600 <= 575 + 5 * t <= 930],
       15: [t for t in range(78) if (575 + 5 * t) % 15 == 0 and 600 <= 575 + 5 * t <= 930]}

def day_trades(d, k, ck, hs, ex, last_min, maxtr, longonly):
    o, h, l, c, vw = d['o'], d['h'], d['l'], d['c'], d['vw']
    up = max(o[0], d['prevC']) * (1 + k * d['sig']); dn = min(o[0], d['prevC']) * (1 - k * d['sig'])
    ckset = set(CKS[ck]); first = CKS[ck][0]
    out, pos, ent, ej, n = [], 0, 0., 0, 0
    for t in range(first, 78):
        if pos and hs:
            stp = ent * (1 - hs) if pos > 0 else ent * (1 + hs)
            if pos > 0 and l[t] <= stp:
                out.append((ej, t, pos, min(o[t], stp) - ent)); pos = 0; continue
            if pos < 0 and h[t] >= stp:
                out.append((ej, t, pos, ent - max(o[t], stp))); pos = 0; continue
        if t not in ckset: continue
        if pos:
            if ex == 'bandvwap': lvl = max(up[t], vw[t]) if pos > 0 else min(dn[t], vw[t])
            elif ex == 'vwap': lvl = vw[t]
            else: lvl = up[t] if pos > 0 else dn[t]
            if (c[t] - lvl) * pos < 0:
                out.append((ej, t, pos, (c[t] - ent) * pos)); pos = 0
        if not pos and n < maxtr and 575 + 5 * t <= last_min:
            if c[t] > up[t]: pos, ent, ej, n = 1, c[t], t, n + 1
            elif c[t] < dn[t] and not longonly: pos, ent, ej, n = -1, c[t], t, n + 1
    if pos: out.append((ej, 77, pos, (c[77] - ent) * pos))
    return out

def account(daylists, ncon, cap, horizon=40, step=2):
    """daylists: list of trade-lists aligned to a window's days. returns pass%, bust%, $total, maxDD"""
    daily = []
    for tr in daylists:
        p = 0.
        for (_, _, _, g) in tr:
            if p <= -1200 or (cap and p >= cap): break
            p = max(-1200., p + (g - COST) * 2 * ncon)
        daily.append(p)
    daily = np.array(daily); res = []
    for s0 in range(0, max(1, len(daily) - horizon + 1), step):
        bal, floor, mx, best, out = 50000., 48000., 50000., 0., 'open'
        for p in daily[s0:s0 + horizon]:
            bal += p
            if bal <= floor: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); floor = 50100. if mx >= 52100 else max(floor, mx - 2000)
        res.append(out)
    eq = np.cumsum(daily); dd = float((eq - np.maximum.accumulate(np.r_[0., eq])[1:]).min()) if len(eq) else 0.
    n = len(res)
    return 100 * res.count('pass') / n, 100 * res.count('bust') / n, float(daily.sum()), dd

# ---------------- grid ----------------
GRID = list(itertools.product([0.75, 1.0, 1.25, 1.5], [30, 15], [0, 0.003, 0.005],
                              ['bandvwap', 'vwap', 'band'], [720, 840, 930], [1, 2, 99], [False, True]))
ACCT = list(itertools.product([1, 2, 3], [0, 600, 1000]))
log('strategy configs', len(GRID), 'x account configs', len(ACCT))

def stats(win, p):
    tl = [day_trades(d, *p) for d in win]
    g = np.array([x[3] - COST for tr in tl for x in tr])
    return tl, g

rows = []
for gi, p in enumerate(GRID):
    tl, g = stats(TUNE, p)
    if len(g) < 20: continue
    best = None
    for ncon, cap in ACCT:
        ps, bs, usd, dd = account(tl, ncon, cap)
        score = ps - bs
        if best is None or (score, usd) > (best[0], best[3]): best = (score, ps, bs, usd, dd, ncon, cap)
    rows.append(dict(k=p[0], ck=p[1], hs=p[2], ex=p[3], last=p[4], maxtr=p[5], longonly=p[6],
                     tune_n=len(g), tune_pts=g.mean(), tune_score=best[0], tune_pass=best[1],
                     tune_bust=best[2], tune_usd=best[3], tune_dd=best[4], ncon=best[5], cap=best[6]))
    if gi % 200 == 0: log('grid', gi)
G = pd.DataFrame(rows).sort_values(['tune_score', 'tune_usd'], ascending=False)
G.to_csv(BASE / 'noise_lab_grid.csv', index=False)
log('grid done', len(G))

def full_report(p, ncon, cap):
    r = {}
    for nm, win, hz, st in (('valid', VALID, 40, 2), ('y26', Y26, 40, 2), ('old', OLD, 40, 5)):
        tl, g = stats(win, p)
        ps, bs, usd, dd = account(tl, ncon, cap, hz, st)
        r.update({f'{nm}_n': len(g), f'{nm}_pts': g.mean() if len(g) else np.nan,
                  f'{nm}_pass': ps, f'{nm}_bust': bs, f'{nm}_usd': usd, f'{nm}_dd': dd})
        if nm == 'old' and len(g):
            raw = g + COST; rng = np.random.default_rng(3)
            perm = (np.where(rng.random((500, len(raw))) < .5, raw, -raw) - COST).sum(axis=1)
            r['old_p'] = float((perm >= g.sum()).mean())
    return r

out = []
base = (1.0, 30, 0, 'bandvwap', 930, 99, False)
cands = [(base, 1, 0, 'PAPER DEFAULT')] + \
        [(tuple(x[c] for c in ('k', 'ck', 'hs', 'ex', 'last', 'maxtr', 'longonly')), int(x['ncon']),
          int(x['cap']), 'tuned') for _, x in G.head(20).iterrows()]
for p, ncon, cap, tag in cands:
    r = dict(tag=tag, k=p[0], ck=p[1], hs=p[2], ex=p[3], last=p[4], maxtr=p[5], longonly=p[6],
             ncon=ncon, cap=cap)
    tl, g = stats(TUNE, p); ps, bs, usd, dd = account(tl, ncon, cap)
    r.update(tune_n=len(g), tune_pts=g.mean(), tune_pass=ps, tune_bust=bs, tune_usd=usd)
    r.update(full_report(p, ncon, cap)); out.append(r)
    log(f"{tag:13s} k={p[0]} ck={p[1]} hs={p[2]} ex={p[3]:8s} last={p[4]} max={p[5]} long={p[6]} "
        f"{ncon}ct cap={cap} | TUNE pass={ps:.0f}% bust={bs:.0f}% ${usd:+.0f} | "
        f"VALID pass={r['valid_pass']:.0f}% bust={r['valid_bust']:.0f}% ${r['valid_usd']:+.0f} "
        f"| 2026 ${r['y26_usd']:+.0f} dd={r['y26_dd']:.0f} | 2021-25 pts={r['old_pts']:+.2f} "
        f"p={r['old_p']:.2f} pass={r['old_pass']:.0f}% bust={r['old_bust']:.0f}%")
pd.DataFrame(out).to_csv(BASE / 'noise_lab_finalists.csv', index=False)
log('done')
