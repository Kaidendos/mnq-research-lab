"""strat_lab2m.py - new strategies from published research, scored on the LAST 2 MONTHS
(2026-06-08..2026-08-07, end of Databento data) with Jan-Jun 2026 and 2021-2025 shown alongside.

Strategies
  gao_last30      Gao/Han/Li/Zhou (JFE 2018): sign(prevClose->10:00 return) held 15:30->15:55 close
  gao_last60      same signal, held 15:00->close
  noise_k1/k15    Zarattini/Aziz/Barbon (2024) Noise Area: bands = max/min(open,prevC) x (1 +/- k*sigma_t),
                  sigma_t = 14-day mean |move from open| at that time; checks every 30 min; trailing
                  stop max(band,VWAP) for longs / min for shorts; flat at close
  vwap_30m        Zarattini/Aziz (2023) VWAP trend, evaluated every 30 min, flat at close
  vwap_5m         same, every 5-min bar (high turnover - cost test)
  gap_fill        fade a 0.15-0.8% RTH gap toward prior close, stop = gap size, time exit 12:00
  dalton80        open outside prior RTH value area, 2 consecutive 30-min closes back inside ->
                  target far side of value, stop beyond session extreme, entries before 13:00
  nr7_orb30       after an NR7 day: close outside the 9:30-10:00 range, stop other side, 2R
  orb15_1r        15-min ORB, close outside 9:30-9:45 range, stop other side, 1R, entries to 11:30
Costs 1.1 pts/trade. Control: same trades with RANDOM DIRECTION (500 perms), same geometry.
Analysis only - no order execution.
"""
import numpy as np, pandas as pd, sys, time
from pathlib import Path
BASE = Path(r'C:\Users\YOU\daytrading-automation')
SYM = sys.argv[1] if len(sys.argv) > 1 else 'mnq'
FILE = {'mnq': 'mnq_2021-2026_5min.csv', 'nq': 'nq_2021-2026_5min.csv'}[SYM]
COST, TICK = 1.1, 0.25
WINDOWS = {'last2m': ('2026-06-08', '2026-08-07'), 'jan-jun26': ('2026-01-01', '2026-06-05'),
           '2021-25': ('2021-08-01', '2025-12-31')}
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:5.0f}s]', *a, flush=True)

df = pd.read_csv(BASE / 'data/databento' / FILE)
ts = pd.to_datetime(df.ts_et, utc=True).dt.tz_convert('America/New_York')
df['mins'] = (ts.dt.hour * 60 + ts.dt.minute).values
df['date'] = ts.dt.date.values
R = df[(df.mins >= 570) & (df.mins < 960)]
days = []
for dt, g in R.groupby('date', sort=True):
    if len(g) != 78 or g.mins.values[0] != 570: continue
    o, h, l, c, v = [g[k].values.astype(float) for k in ('open', 'high', 'low', 'close', 'volume')]
    tp = (h + l + c) / 3; vv = np.maximum(v, 1)
    days.append(dict(date=dt, o=o, h=h, l=l, c=c, v=vv, mins=g.mins.values,
                     vw=np.cumsum(tp * vv) / np.cumsum(vv)))
for i, d in enumerate(days):
    d['prevC'] = days[i-1]['c'][-1] if i else np.nan
    d['rng'] = d['h'].max() - d['l'].min()
    d['mv'] = np.abs(d['c'] / d['o'][0] - 1)            # |move from open| at each bar close
    # value area (70%) from 5-pt volume profile at typical price
    tp = (d['h'] + d['l'] + d['c']) / 3; b = np.floor(tp / 5).astype(int)
    u, inv = np.unique(b, return_inverse=True); vol = np.bincount(inv, weights=d['v'])
    k = int(np.argmax(vol)); lo = hi = k; tot = vol[k]
    while tot < 0.7 * vol.sum():
        up = vol[hi + 1] if hi + 1 < len(vol) else -1; dn = vol[lo - 1] if lo > 0 else -1
        if up >= dn: hi += 1; tot += up
        else: lo -= 1; tot += dn
    d['VAL'], d['VAH'] = u[lo] * 5.0, u[hi] * 5.0 + 5.0
CK = [i for i in range(78) if (570 + 5 * i + 5) % 30 == 0 and 600 <= 570 + 5 * i + 5 <= 930]  # 10:00..15:30 closes
log('RTH sessions', len(days), days[0]['date'], '->', days[-1]['date'])

def sim(d, j, side, entry, sd, td, xj, limit=False):
    """bracket from bar j+1 to xj (inclusive, exit at close of xj). sd/td = stop/target distance (inf ok)"""
    h, l, c, o = d['h'], d['l'], d['c'], d['o']
    stop, tgt = entry - side * sd, entry + side * td
    for k in range(j + 1, xj + 1):
        if side > 0:
            if o[k] <= stop: return o[k] - entry
            if l[k] <= stop: return stop - entry
            if h[k] >= tgt: return tgt - entry
        else:
            if o[k] >= stop: return entry - o[k]
            if h[k] >= stop: return entry - stop
            if l[k] <= tgt: return entry - tgt
    return (c[xj] - entry) * side

def T(d, name, j, side, entry, sd, td, xj, gross=None):
    g = sim(d, j, side, entry, sd, td, xj) if gross is None else gross
    return dict(date=d['date'], strat=name, side=side, j=j, entry=entry, sd=sd, td=td, xj=xj,
                gross=g, net=g - COST, path=gross is not None)

# ---------------- strategies ----------------
def gao(d, i, entry_bar, name):
    if i < 1 or np.isnan(d['prevC']): return []
    r1 = d['c'][5] / d['prevC'] - 1
    if r1 == 0: return []
    s = 1 if r1 > 0 else -1
    return [T(d, name, entry_bar, s, d['c'][entry_bar], np.inf, np.inf, 77)]

def noise(d, i, k, name):
    if i < 14 or np.isnan(d['prevC']): return []
    sig = np.mean([days[i - q]['mv'] for q in range(1, 15)], axis=0)
    o0, pc, c, vw = d['o'][0], d['prevC'], d['c'], d['vw']
    up, dn = max(o0, pc) * (1 + k * sig), min(o0, pc) * (1 - k * sig)
    out, pos, ent, ej = [], 0, 0.0, 0
    for t in CK:
        if pos > 0 and c[t] < max(up[t], vw[t]):
            out.append(T(d, name, ej, 1, ent, 0, 0, t, gross=c[t] - ent)); pos = 0
        elif pos < 0 and c[t] > min(dn[t], vw[t]):
            out.append(T(d, name, ej, -1, ent, 0, 0, t, gross=ent - c[t])); pos = 0
        if pos == 0:
            if c[t] > up[t]: pos, ent, ej = 1, c[t], t
            elif c[t] < dn[t]: pos, ent, ej = -1, c[t], t
    if pos: out.append(T(d, name, ej, pos, ent, 0, 0, 77, gross=(c[77] - ent) * pos))
    return out

def vwap_trend(d, i, bars, name):
    c, vw, out, pos, ent, ej = d['c'], d['vw'], [], 0, 0.0, 0
    for t in bars:
        s = 1 if c[t] > vw[t] else -1 if c[t] < vw[t] else pos
        if s != pos:
            if pos: out.append(T(d, name, ej, pos, ent, 0, 0, t, gross=(c[t] - ent) * pos))
            pos, ent, ej = s, c[t], t
    if pos: out.append(T(d, name, ej, pos, ent, 0, 0, 77, gross=(c[77] - ent) * pos))
    return out

def gap_fill(d, i):
    pc = d['prevC']
    if np.isnan(pc): return []
    gap = d['o'][0] - pc; pct = abs(gap) / pc
    if not (0.0015 <= pct <= 0.008): return []
    s = -1 if gap > 0 else 1; e = d['c'][0]; td = (pc - e) * s
    if td < 4: return []
    return [T(d, 'gap_fill', 0, s, e, abs(gap), td, 29)]

def dalton80(d, i):
    if i < 1: return []
    p = days[i - 1]; VAL, VAH = p['VAL'], p['VAH']; o0, c, h, l = d['o'][0], d['c'], d['h'], d['l']
    if VAL < o0 < VAH: return []
    s = -1 if o0 >= VAH else 1; inside = 0
    for t in [t for t in CK if 575 + 5 * t <= 780]:
        inside = inside + 1 if VAL < c[t] < VAH else 0
        if inside >= 2:
            e = c[t]
            sd = (h[:t + 1].max() + TICK - e) if s < 0 else (e - l[:t + 1].min() + TICK)
            td = (e - VAL) if s < 0 else (VAH - e)
            if 4 <= td and 4 <= sd <= 0.006 * e: return [T(d, 'dalton80', t, s, e, sd, td, 77)]
            return []
    return []

def orb(d, i, nbars, last_entry, rr, name, need_nr7=False):
    if need_nr7:
        if i < 7 or days[i - 1]['rng'] > min(days[i - q]['rng'] for q in range(1, 8)): return []
    H_, L_ = d['h'][:nbars].max(), d['l'][:nbars].min(); c = d['c']
    for t in range(nbars, last_entry + 1):
        s = 1 if c[t] > H_ else -1 if c[t] < L_ else 0
        if s:
            e = c[t]; sd = (e - L_ + TICK) if s > 0 else (H_ + TICK - e)
            if 4 <= sd <= 0.004 * e: return [T(d, name, t, s, e, sd, rr * sd, 77)]
            return []
    return []

STRATS = [
    ('gao_last30', lambda d, i: gao(d, i, 71, 'gao_last30')),
    ('gao_last60', lambda d, i: gao(d, i, 65, 'gao_last60')),
    ('noise_k1',   lambda d, i: noise(d, i, 1.0, 'noise_k1')),
    ('noise_k15',  lambda d, i: noise(d, i, 1.5, 'noise_k15')),
    ('vwap_30m',   lambda d, i: vwap_trend(d, i, [5] + CK, 'vwap_30m')),
    ('vwap_5m',    lambda d, i: vwap_trend(d, i, list(range(0, 77)), 'vwap_5m')),
    ('gap_fill',   gap_fill),
    ('dalton80',   dalton80),
    ('nr7_orb30',  lambda d, i: orb(d, i, 6, 23, 2.0, 'nr7_orb30', need_nr7=True)),
    ('orb15_1r',   lambda d, i: orb(d, i, 3, 23, 1.0, 'orb15_1r')),
]

# ---------------- evaluation ----------------
DAY = {d['date']: d for d in days}
def flip_gross(t):
    if t['path']: return -t['gross']
    return sim(DAY[t['date']], t['j'], -t['side'], t['entry'], t['sd'], t['td'], t['xj'])

def contracts(t):
    if t['path'] or not np.isfinite(t['sd']): return 2            # time/trailing exits: fixed 2 MNQ
    return max(0, min(40, int(400 // (t['sd'] * 2))))             # $400 risk per trade

def eval_starts(tr, wdays, min_h=15):
    by = {}
    for t in sorted(tr, key=lambda t: (t['date'], t['j'])):       # intraday DLL: stop at -$1,200
        cur = by.get(t['date'], 0.)
        if cur <= -1200: continue
        by[t['date']] = max(-1200.0, cur + t['net'] * 2 * contracts(t))
    ds = [d['date'] for d in wdays]; res = []
    for s0 in range(0, len(ds) - min_h + 1):
        bal, floor, mx, best, out = 50000., 48000., 50000., 0., 'open'
        for k in range(s0, len(ds)):
            p = max(-1200.0, by.get(ds[k], 0.)); bal += p
            if bal <= floor: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); floor = 50100. if mx >= 52100 else max(floor, mx - 2000)
        res.append(out)
    daily = np.array([max(-1200.0, by.get(x, 0.)) for x in ds])
    eq = np.cumsum(daily); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min() if len(eq) else 0
    return res, daily.sum(), daily.min(), dd

rng = np.random.default_rng(11)
rows, alltr = [], []
for name, fn in STRATS:
    tr = []
    for i, d in enumerate(days): tr += fn(d, i)
    for t in tr: t['flip'] = flip_gross(t) - COST
    alltr += tr
    row = dict(strat=name)
    for w, (a, b) in WINDOWS.items():
        a, b = pd.Timestamp(a).date(), pd.Timestamp(b).date()
        W = [t for t in tr if a <= t['date'] <= b]
        n = len(W); net = np.array([t['net'] for t in W]); fl = np.array([t['flip'] for t in W])
        if n:
            pick = rng.random((500, n)) < 0.5
            perm = np.where(pick, net, fl).sum(axis=1)
            p = float((perm >= net.sum()).mean())
        else: p = np.nan
        row.update({f'{w}_n': n, f'{w}_win': 100 * (net > 0).mean() if n else np.nan,
                    f'{w}_pts': net.mean() if n else np.nan, f'{w}_tot': net.sum() if n else 0.0,
                    f'{w}_p': p})
        if w == 'last2m':
            wd = [d for d in days if a <= d['date'] <= b]
            res, tot, worst, dd = eval_starts(W, wd)
            row.update(l2_usd=tot, l2_worst=worst, l2_maxdd=dd,
                       l2_pass=sum(r == 'pass' for r in res), l2_bust=sum(r == 'bust' for r in res),
                       l2_open=sum(r == 'open' for r in res))
    rows.append(row)
    log(f"{name:11s} last2m n={row['last2m_n']:3d} pts/tr={row['last2m_pts']:+7.2f} p={row['last2m_p']:.2f} "
        f"${row['l2_usd']:+8.0f} | jan-jun26 {row['jan-jun26_pts']:+7.2f} p={row['jan-jun26_p']:.2f} | "
        f"2021-25 {row['2021-25_pts']:+7.2f} p={row['2021-25_p']:.2f} n={row['2021-25_n']}")

out = pd.DataFrame(rows)
out.to_csv(BASE / f'strat_lab2m_{SYM}.csv', index=False)
pd.DataFrame(alltr).to_csv(BASE / f'strat_lab2m_{SYM}_trades.csv', index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40)
print(out.round(2).sort_values('last2m_tot', ascending=False).to_string(index=False))
log('done')
