"""ict_lab.py - backtest ICT markings as mechanical setups on Databento 5-min data.

Usage:  python ict_lab.py mnq      (or: nq)

Setups (one trade per setup per day, NY window 09:30-11:30 ET unless noted):
  fvg_ny        first retrace (limit) into a fresh FVG formed in the window, stop beyond candle 1
  silver_bullet same, FVGs formed 10:00-11:00 only
  ifvg          FVG (formed from 09:00) inverted by a CLOSE through its far edge -> trade the new side
  sweep_*       wick through an untaken level + close back inside -> reverse. PD=prev Globex day
                H/L, ON=overnight H/L, AS=Asia 19:00-24:00, LN=London 02:00-05:00, all=any of them
  mss_close     sweep of a level, then a close through the last 2/2 swing pivot within 12 bars
  mss_fvg       same, but enter on a retrace into the FVG left by the displacement leg
Targets at 1R / 2R / 3R. Exits: stop, target, or the 15:55 bar close.

Method (from CONTINUE.md rules): bar stamps are bar START; entries at signal-bar close or at the
limit price; stop-first on ambiguous bars; limit fills are stopped out if the fill bar also hits
the stop and cannot hit target on the fill bar. Costs 1.1 pts/trade. Selection 2021-24 vs
HOLDOUT 2025-26. Clean random control (same side + risk, random day AND bar, 10 seeds).
Account: LucidDaily 50K eval (EOD trail $2k, lock $50,100, DLL $1,200, target $3k, 50% consistency),
$400 risk/trade in MNQ micros, cap 40. Analysis only - no order execution.
"""
import numpy as np, pandas as pd, sys, time
from pathlib import Path

BASE = Path(r'C:\Users\YOU\daytrading-automation')
SYM = sys.argv[1] if len(sys.argv) > 1 else 'mnq'
FILE = {'mnq': 'mnq_2021-2026_5min.csv', 'nq': 'nq_2021-2026_5min.csv'}[SYM]
COST, TICK, MING, MINR, MAXR = 1.1, 0.25, 1.0, 4.0, 100.0
START = pd.Timestamp(sys.argv[2] if len(sys.argv) > 2 else '2021-01-01').date()
SPLIT = pd.Timestamp(sys.argv[3] if len(sys.argv) > 3 else '2025-01-01').date()
HORIZON = int(sys.argv[4]) if len(sys.argv) > 4 else 120
TAG = sys.argv[5] if len(sys.argv) > 5 else ''
SEEDS = 10
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:5.0f}s]', *a, flush=True)

df = pd.read_csv(BASE / 'data/databento' / FILE)
log('symbols in file:', df.symbol.unique()[:5])
ts = pd.to_datetime(df.ts_et, utc=True).dt.tz_convert('America/New_York')
m = (ts.dt.hour * 60 + ts.dt.minute).values
td = (ts.dt.tz_localize(None) + pd.Timedelta(hours=6)).dt.date.values
O, H, L, C = [df[c].values.astype(float) for c in ('open', 'high', 'low', 'close')]
brk = np.r_[0, np.nonzero(td[1:] != td[:-1])[0] + 1, len(td)]

days, prevG = [], None
for a, b in zip(brk[:-1], brk[1:]):
    mm = m[a:b]
    rth = np.nonzero((mm >= 570) & (mm < 960))[0]
    if prevG is not None and len(rth) >= 70 and mm[rth[0]] == 570 and a >= 3:
        def rng(mask):
            ix = np.nonzero(mask)[0]
            if len(ix) == 0: return np.nan, np.nan, a
            return H[a + ix].max(), L[a + ix].min(), a + ix[-1] + 1
        onH, onL, onE = rng((mm >= 1080) | (mm < 570))
        asH, asL, asE = rng((mm >= 1140) & (mm < 1440))
        lnH, lnL, lnE = rng((mm >= 120) & (mm < 300))
        days.append(dict(date=td[a], a=a, b=b, mm=mm, last=a + rth[-1],
            hi={'PD': (prevG[0], a), 'ON': (onH, onE), 'AS': (asH, asE), 'LN': (lnH, lnE)},
            lo={'PD': (prevG[1], a), 'ON': (onL, onE), 'AS': (asL, asE), 'LN': (lnL, lnE)}))
    prevG = (H[a:b].max(), L[a:b].min())
days = [d for d in days if d['date'] >= START]
POOL = {False: [d for d in days if d['date'] < SPLIT], True: [d for d in days if d['date'] >= SPLIT]}
log('sessions', len(days), 'selection', len(POOL[False]), 'holdout', len(POOL[True]))

def widx(d, lo=570, hi=685):
    mm = d['mm']; return np.nonzero((mm >= lo) & (mm <= hi))[0] + d['a']

def run(j, side, entry, stop, tgt, last, limit=False):
    if limit:
        if side > 0 and L[j] <= stop: return stop - entry
        if side < 0 and H[j] >= stop: return entry - stop
    for k in range(j + 1, last + 1):
        if side > 0:
            if O[k] <= stop: return O[k] - entry
            if L[k] <= stop: return stop - entry
            if H[k] >= tgt: return tgt - entry
        else:
            if O[k] >= stop: return entry - O[k]
            if H[k] >= stop: return entry - stop
            if L[k] <= tgt: return entry - tgt
    return (C[last] - entry) * side

def mk(d, name, j, side, entry, stop, rr, limit=False):
    risk = abs(entry - stop)
    if risk < MINR or risk > MAXR or (stop - entry) * side >= 0: return None
    pnl = run(j, side, entry, stop, entry + side * rr * risk, d['last'], limit)
    return dict(date=d['date'], setup=name, side=side, risk=risk, pnl=pnl,
                net=pnl - COST, R=(pnl - COST) / risk, mins=int(m[j]))

def fvg_at(i):  # (side, entry_edge, far_edge, stop_ref)
    if L[i] >= H[i-2] + MING and C[i-1] > H[i-2]: return (1, L[i], H[i-2], L[i-2], i)
    if H[i] <= L[i-2] - MING and C[i-1] < L[i-2]: return (-1, H[i], L[i-2], H[i-2], i)
    return None

# ---------------- setups ----------------
def fvg_retest(d, rr, lo=570, hi=685, name='fvg_ny'):
    act = []
    for j in widx(d, lo, hi):
        keep = []
        for f in act:
            side, edge, far, sref, i = f
            if (side > 0 and L[j] <= edge) or (side < 0 and H[j] >= edge):
                t = mk(d, name, j, side, edge, sref - side * TICK, rr, limit=True)
                if t: return t
                continue                      # filled but filtered: drop it
            keep.append(f)
        act = keep
        f = fvg_at(j)
        if f: act.append(f)
    return None

def ifvg(d, rr, maxage=30):
    act = []
    for j in widx(d, 540, 685):
        if m[j] >= 570:
            keep = []
            for f in act:
                side, edge, far, sref, i = f
                if j - i > maxage: continue
                if (C[j] - far) * side < 0:   # close through the far edge -> inverted
                    t = mk(d, 'ifvg', j, -side, C[j], edge + side * TICK, rr)
                    if t: return t
                    continue
                keep.append(f)
            act = keep
        f = fvg_at(j)
        if f: act.append(f)
    return None

def untaken_hi(lev, e, j): return not np.isnan(lev) and e < j and H[e:j].max() < lev
def untaken_lo(lev, e, j): return not np.isnan(lev) and e < j and L[e:j].min() > lev

def sweep(d, rr, keys, name):
    for j in widx(d):
        for k in keys:
            lev, e = d['hi'][k]
            if untaken_hi(lev, e, j) and H[j] > lev and C[j] < lev:
                t = mk(d, name, j, -1, C[j], H[j] + TICK, rr)
                if t: return t
            lev, e = d['lo'][k]
            if untaken_lo(lev, e, j) and L[j] < lev and C[j] > lev:
                t = mk(d, name, j, 1, C[j], L[j] - TICK, rr)
                if t: return t
    return None

def pivot(j, a, side):  # last confirmed 2/2 pivot high (side=+1) or low (-1) known by bar j
    for k in range(j - 2, max(a + 2, j - 60) - 1, -1):
        if side > 0 and H[k] > max(H[k-2], H[k-1], H[k+1], H[k+2]): return H[k]
        if side < 0 and L[k] < min(L[k-2], L[k-1], L[k+1], L[k+2]): return L[k]
    return None

def mss(d, rr, mode):
    pend, keys, last = [], ['PD', 'ON', 'AS', 'LN'], d['last']
    for j in widx(d):
        newp = []
        for p in pend:
            if j - p['s'] > 12: continue
            s, side = p['s'], p['side']
            ext = min(p['ext'], L[j]) if side > 0 else max(p['ext'], H[j])
            if (C[j] - p['P']) * side > 0:
                stop = ext - side * TICK
                if mode == 'close':
                    t = mk(d, 'mss_close', j, side, C[j], stop, rr)
                    if t: return t
                else:
                    fv = [fvg_at(i) for i in range(s + 2, j + 1)]
                    fv = [f for f in fv if f and f[0] == side]
                    if fv:
                        edge = fv[-1][1]
                        for k in range(j + 1, min(j + 13, last + 1)):
                            if (side > 0 and L[k] <= stop) or (side < 0 and H[k] >= stop): break
                            if (side > 0 and L[k] <= edge) or (side < 0 and H[k] >= edge):
                                t = mk(d, 'mss_fvg', k, side, edge, stop, rr, limit=True)
                                if t: return t
                                break
                continue
            p['ext'] = ext
            newp.append(p)
        pend = newp
        sides = {p['side'] for p in pend if p['s'] == j}
        for k in keys:
            lev, e = d['lo'][k]
            if 1 not in sides and untaken_lo(lev, e, j) and L[j] < lev:
                P = pivot(j, d['a'], 1)
                if P is not None and P > C[j]:
                    pend.append(dict(s=j, side=1, P=P, ext=L[j])); sides.add(1)
            lev, e = d['hi'][k]
            if -1 not in sides and untaken_hi(lev, e, j) and H[j] > lev:
                P = pivot(j, d['a'], -1)
                if P is not None and P < C[j]:
                    pend.append(dict(s=j, side=-1, P=P, ext=H[j])); sides.add(-1)
    return None

SETUPS = [
    ('fvg_ny',        (570, 685), lambda d, rr: fvg_retest(d, rr)),
    ('silver_bullet', (600, 655), lambda d, rr: fvg_retest(d, rr, 600, 655, 'silver_bullet')),
    ('ifvg',          (570, 685), lambda d, rr: ifvg(d, rr)),
    ('sweep_pd',      (570, 685), lambda d, rr: sweep(d, rr, ['PD'], 'sweep_pd')),
    ('sweep_on',      (570, 685), lambda d, rr: sweep(d, rr, ['ON'], 'sweep_on')),
    ('sweep_asia',    (570, 685), lambda d, rr: sweep(d, rr, ['AS'], 'sweep_asia')),
    ('sweep_london',  (570, 685), lambda d, rr: sweep(d, rr, ['LN'], 'sweep_london')),
    ('sweep_all',     (570, 685), lambda d, rr: sweep(d, rr, ['PD', 'ON', 'AS', 'LN'], 'sweep_all')),
    ('mss_close',     (570, 685), lambda d, rr: mss(d, rr, 'close')),
    ('mss_fvg',       (570, 685), lambda d, rr: mss(d, rr, 'fvg')),
]

# ---------------- evaluation ----------------
def control(trades, rr, win, seed):
    g = np.random.default_rng(seed); out = []
    for t in trades:
        pool = POOL[t['date'] >= SPLIT]
        d = pool[g.integers(len(pool))]
        J = widx(d, *win); j = J[g.integers(len(J))]
        e, s, r = C[j], t['side'], t['risk']
        out.append((run(j, s, e, e - s * r, e + s * rr * r, d['last']) - COST) / r)
    return float(np.mean(out)) if out else np.nan

def account(trades, pool, risk_usd=400, horizon=HORIZON, step=2 if HORIZON < 120 else 5):
    by = {}
    for t in trades:
        n = min(40, int(risk_usd // (t['risk'] * 2)))
        if n >= 1: by[t['date']] = max(-1200.0, t['net'] * 2 * n)
    dates = [d['date'] for d in pool]; res = []
    for s0 in range(0, len(dates) - horizon, step):
        bal, floor, mx, best, out = 50000., 48000., 50000., 0., ('open', horizon)
        for k in range(s0, s0 + horizon):
            p = by.get(dates[k], 0.); bal += p
            if bal <= floor: out = ('bust', k - s0 + 1); break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = ('pass', k - s0 + 1); break
            mx = max(mx, bal); floor = 50100. if mx >= 52100 else max(floor, mx - 2000)
        res.append(out)
    n = len(res)
    if n == 0: return np.nan, np.nan, np.nan
    pd_ = [x[1] for x in res if x[0] == 'pass']
    return (100 * len(pd_) / n, 100 * sum(x[0] == 'bust' for x in res) / n,
            float(np.median(pd_)) if pd_ else np.nan)

rows, alltr = [], []
for name, win, fn in SETUPS:
    for rr in (1.0, 2.0, 3.0):
        tr = [t for t in (fn(d, rr) for d in days) if t]
        for t in tr: t['rr'] = rr
        alltr += tr
        row = dict(setup=name, rr=rr)
        for per, flag in (('sel', False), ('hold', True)):
            T = [t for t in tr if (t['date'] >= SPLIT) == flag]
            R = np.array([t['R'] for t in T]) if T else np.array([np.nan])
            ctl = [control(T, rr, win, s) for s in range(SEEDS)]
            p, b, dd = account(T, POOL[flag])
            row.update({f'{per}_n': len(T), f'{per}_win': 100 * np.mean(R > 0),
                        f'{per}_R': R.mean(), f'{per}_ctlR': float(np.nanmean(ctl)),
                        f'{per}_beat': int(sum(c >= R.mean() for c in ctl)),
                        f'{per}_pass': p, f'{per}_bust': b, f'{per}_days': dd})
            row[f'{per}_edge'] = row[f'{per}_R'] - row[f'{per}_ctlR']
        yrs = pd.DataFrame(tr)
        if len(yrs):
            yrs['y'] = [x.year for x in yrs.date]
            row['R_by_year'] = ' '.join(f"{y}:{v:+.2f}" for y, v in yrs.groupby('y').R.mean().items())
        rows.append(row)
        log(f"{name:14s} rr{rr:.0f} sel n={row['sel_n']:4d} R={row['sel_R']:+.3f} edge={row['sel_edge']:+.3f} | "
            f"hold n={row['hold_n']:3d} R={row['hold_R']:+.3f} edge={row['hold_edge']:+.3f} "
            f"beat={row['hold_beat']}/{SEEDS} pass={row['hold_pass']:.0f}% bust={row['hold_bust']:.0f}%")

out = pd.DataFrame(rows)
out.to_csv(BASE / f'ict_lab_{SYM}{TAG}.csv', index=False)
pd.DataFrame(alltr).to_csv(BASE / f'ict_lab_{SYM}{TAG}_trades.csv', index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
cols = ['setup', 'rr', 'sel_n', 'sel_win', 'sel_R', 'sel_edge', 'sel_beat', 'hold_n', 'hold_win',
        'hold_R', 'hold_edge', 'hold_beat', 'sel_pass', 'hold_pass', 'hold_bust', 'hold_days']
print(out[cols].round(3).sort_values('hold_edge', ascending=False).to_string(index=False))
log('done')
