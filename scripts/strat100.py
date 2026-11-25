"""strat100.py - 20 entry signals x 5 fixed ATR brackets = 100 strategies, 2026 only.
TUNE  = 2026-01-02..2026-04-30 (choose risk size here)   VALID = 2026-05-01..2026-08-07 (never used to choose)
Lessons applied: fixed stops sized in $ (risk/trade), eval with no time limit, luck baseline from random
entries with the same brackets (how often does RANDOM pass an eval in <=5 days?).
Account: LucidDaily 50K eval - EOD trail $2,000 (lock $50,100), DLL $1,200, target $3,000, 50% consistency.
Entries at 5-min bar close (stamps = bar start), stop-first, exit by 15:55 bar close, 1 trade/day/strategy,
costs 1.1 pts/trade, min stop 4 pts. Analysis only - no order execution.
"""
import numpy as np, pandas as pd, time
from pathlib import Path
BASE = Path(r'C:\Users\YOU\daytrading-automation')
COST, TICK = 1.1, 0.25
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:5.0f}s]', *a, flush=True)

df = pd.read_csv(BASE / 'data/databento/mnq_2021-2026_5min.csv')
ts = pd.to_datetime(df.ts_et, utc=True).dt.tz_convert('America/New_York')
m = (ts.dt.hour * 60 + ts.dt.minute).values
td = (ts.dt.tz_localize(None) + pd.Timedelta(hours=6)).dt.date.values
O, H, L, C, V = [df[k].values.astype(float) for k in ('open', 'high', 'low', 'close', 'volume')]
rth = (m >= 570) & (m < 960)
# RTH-only indicators
ri = np.nonzero(rth)[0]
rc, rh, rl = C[ri], H[ri], L[ri]
pc = np.r_[rc[0], rc[:-1]]
tr = np.maximum(rh - rl, np.maximum(abs(rh - pc), abs(rl - pc)))
ATR = np.full(len(C), np.nan); ATR[ri] = pd.Series(tr).rolling(14).mean().values
E9 = np.full(len(C), np.nan); E9[ri] = pd.Series(rc).ewm(span=9, adjust=False).mean().values
E21 = np.full(len(C), np.nan); E21[ri] = pd.Series(rc).ewm(span=21, adjust=False).mean().values
dlt = np.diff(rc, prepend=rc[0]); up = pd.Series(np.maximum(dlt, 0)).ewm(alpha=.5).mean()
dn = pd.Series(np.maximum(-dlt, 0)).ewm(alpha=.5).mean()
RSI2 = np.full(len(C), np.nan); RSI2[ri] = (100 - 100 / (1 + up / dn.replace(0, 1e-9))).values

brk = np.r_[0, np.nonzero(td[1:] != td[:-1])[0] + 1, len(td)]
days, prev = [], None
for a, b in zip(brk[:-1], brk[1:]):
    mm = m[a:b]; r = np.nonzero((mm >= 570) & (mm < 960))[0]
    if prev is not None and len(r) == 78 and mm[r[0]] == 570:
        s = a + r[0]; on = np.nonzero((mm >= 1080) | (mm < 570))[0]
        cc = C[s:s + 78]; vv = np.maximum(V[s:s + 78], 1); tp = (H[s:s+78] + L[s:s+78] + cc) / 3
        days.append(dict(date=td[a], s=s, vw=np.cumsum(tp * vv) / np.cumsum(vv),
                         PDH=prev[0], PDL=prev[1], PDC=prev[2],
                         ONH=H[a + on].max() if len(on) else np.nan, ONL=L[a + on].min() if len(on) else np.nan,
                         mv=np.abs(cc / O[s] - 1)))
    if len(r) >= 20: prev = (H[a + r].max(), L[a + r].min(), C[a + r[-1]])
for i, d in enumerate(days):
    d['sig'] = np.mean([days[i-q]['mv'] for q in range(1, 15)], axis=0) if i >= 14 else None
log('RTH days', len(days))

# ---------------- 20 entry signals: return (k, side) or (k, side, limit_price) ----------------
W = range(1, 24)                                  # bars starting 09:35..11:25
def cl(d, k): return C[d['s'] + k]
def orb_break(n):
    def f(d):
        s = d['s']; hi, lo = H[s:s+n].max(), L[s:s+n].min()
        for k in range(n, 24):
            if cl(d, k) > hi: return k, 1
            if cl(d, k) < lo: return k, -1
    return f
def orb_fade(n):
    def f(d):
        s = d['s']; hi, lo = H[s:s+n].max(), L[s:s+n].min()
        for k in range(n, 24):
            j = s + k
            if H[j] > hi and C[j] < hi: return k, -1
            if L[j] < lo and C[j] > lo: return k, 1
    return f
def vwap_cross(d):
    for k in range(6, 24):
        j = d['s'] + k; vw = d['vw']
        if C[j] > vw[k] and C[j-1] <= vw[k-1]: return k, 1
        if C[j] < vw[k] and C[j-1] >= vw[k-1]: return k, -1
def vwap_pull(d):
    for k in range(7, 24):
        j = d['s'] + k; vw = d['vw']; prior = C[j-6:j] - vw[k-6:k]
        if (prior > 0).all() and L[j] <= vw[k] < C[j]: return k, 1
        if (prior < 0).all() and H[j] >= vw[k] > C[j]: return k, -1
def ema_cross(d):
    for k in W:
        j = d['s'] + k
        if E9[j] > E21[j] and E9[j-1] <= E21[j-1]: return k, 1
        if E9[j] < E21[j] and E9[j-1] >= E21[j-1]: return k, -1
def lvl_break(hk, lk):
    def f(d):
        for k in W:
            j = d['s'] + k
            if C[j] > d[hk] >= C[j-1]: return k, 1
            if C[j] < d[lk] <= C[j-1]: return k, -1
    return f
def lvl_reject(hk, lk):
    def f(d):
        s = d['s']
        for k in W:
            j = s + k
            if H[j] > d[hk] > C[j] and H[s:j].max() < d[hk]: return k, -1
            if L[j] < d[lk] < C[j] and L[s:j].min() > d[lk]: return k, 1
    return f
def fvg_retest(d):
    s, act = d['s'], []
    for k in W:
        j = s + k
        for side, edge in act:
            if (side > 0 and L[j] <= edge) or (side < 0 and H[j] >= edge): return k, side, edge
        if k >= 2:
            if L[j] >= H[j-2] + 1 and C[j-1] > H[j-2]: act.append((1, L[j]))
            elif H[j] <= L[j-2] - 1 and C[j-1] < L[j-2]: act.append((-1, H[j]))
def first_hour(d):
    mv = cl(d, 11) - O[d['s']]
    return (11, 1 if mv > 0 else -1) if mv else None
def gap_go(d):
    g = O[d['s']] - d['PDC']
    if abs(g) / d['PDC'] < 0.002: return None
    side = 1 if g > 0 else -1
    return (2, side) if (cl(d, 2) - O[d['s']]) * side > 0 else None
def rsi2_trend(d):
    for k in range(3, 24):
        j = d['s'] + k
        if C[j] > d['vw'][k] and RSI2[j] < 10: return k, 1
        if C[j] < d['vw'][k] and RSI2[j] > 90: return k, -1
def mom3(d):
    for k in range(3, 24):
        j = d['s'] + k; seg = slice(j-2, j+1)
        rng_ok = ((H[seg] - L[seg]) > 0.8 * ATR[j]).all()
        if rng_ok and (C[seg] > O[seg]).all(): return k, 1
        if rng_ok and (C[seg] < O[seg]).all(): return k, -1
def round100(d):
    for k in W:
        j = d['s'] + k; lv = np.floor(C[j] / 100) * 100
        if C[j-1] < lv <= C[j] and C[j] > O[j]: return k, 1
        lv2 = np.ceil(C[j] / 100) * 100
        if C[j-1] > lv2 >= C[j] and C[j] < O[j]: return k, -1
def ib_break(d):
    s = d['s']; hi, lo = H[s:s+12].max(), L[s:s+12].min()
    for k in range(12, 42):
        if cl(d, k) > hi: return k, 1
        if cl(d, k) < lo: return k, -1
def noise_break(d):
    if d['sig'] is None: return None
    o0 = O[d['s']]; up = max(o0, d['PDC']) * (1 + d['sig']); dn = min(o0, d['PDC']) * (1 - d['sig'])
    for k in (5, 11, 17, 23, 29, 35):          # 10:00 .. 12:30 closes
        if cl(d, k) > up[k]: return k, 1
        if cl(d, k) < dn[k]: return k, -1

SIGNALS = {'orb5_break': orb_break(1), 'orb15_break': orb_break(3), 'orb30_break': orb_break(6),
           'orb15_fade': orb_fade(3), 'orb30_fade': orb_fade(6), 'vwap_cross': vwap_cross,
           'vwap_pullback': vwap_pull, 'ema9_21': ema_cross, 'pdhl_break': lvl_break('PDH', 'PDL'),
           'pdhl_reject': lvl_reject('PDH', 'PDL'), 'onhl_break': lvl_break('ONH', 'ONL'),
           'onhl_reject': lvl_reject('ONH', 'ONL'), 'fvg_retest': fvg_retest, 'first_hour': first_hour,
           'gap_and_go': gap_go, 'rsi2_trend': rsi2_trend, 'momentum3': mom3, 'round100': round100,
           'ib_break': ib_break, 'noise_break': noise_break}
BRACKETS = [(0.75, 1.0), (0.75, 2.0), (1.25, 1.0), (1.25, 2.0), (2.0, 1.5)]   # (stop x ATR, reward:risk)

# ---------------- simulation ----------------
def sim(d, k, side, entry, sd, td, limit=False):
    s = d['s']; j0 = s + k; stop, tgt = entry - side * sd, entry + side * td
    if limit and ((side > 0 and L[j0] <= stop) or (side < 0 and H[j0] >= stop)): return -sd
    for j in range(j0 + 1, s + 78):
        if side > 0:
            if O[j] <= stop: return O[j] - entry
            if L[j] <= stop: return -sd
            if H[j] >= tgt: return td
        else:
            if O[j] >= stop: return entry - O[j]
            if H[j] >= stop: return -sd
            if L[j] <= tgt: return td
    return (C[s + 77] - entry) * side

def trades_for(sig, sl, rr, win, rng=None):
    out = []
    for d in win:
        r = sig(d)
        if not r: continue
        if rng is not None:                               # random twin: same day, random bar + side
            k = int(rng.integers(1, 24)); r = (k, int(rng.choice([-1, 1])))
        k, side = r[0], r[1]; j = d['s'] + k
        entry = r[2] if len(r) > 2 else C[j]
        sd = max(4.0, sl * ATR[j]); td = rr * sd
        if not np.isfinite(sd): continue
        g = sim(d, k, side, entry, sd, td, limit=len(r) > 2)
        out.append(dict(date=d['date'], sd=sd, pts=g - COST, R=(g - COST) / sd))
    return out

def evalsim(tr, win, risk):
    by = {}
    for t in tr:
        n = min(40, int(risk // (t['sd'] * 2)))
        if n >= 1: by[t['date']] = max(-1200., t['pts'] * 2 * n)
    ds = [d['date'] for d in win]; res = []
    for s0 in range(0, len(ds) - 10):
        bal, fl, mx, best, out, nd, wins, ntr = 50000., 48000., 50000., 0., 'open', 0, 0, 0
        for x in ds[s0:]:
            p = by.get(x, 0.); bal += p; nd += 1
            if x in by: ntr += 1; wins += p > 0
            if bal <= fl: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
        res.append((out, nd, out == 'pass' and wins == ntr))
    n = len(res); pas = [r for r in res if r[0] == 'pass']
    return dict(pass_=100 * len(pas) / n, bust=100 * sum(r[0] == 'bust' for r in res) / n,
                days=float(np.median([r[1] for r in pas])) if pas else np.nan,
                fastest=min([r[1] for r in pas]) if pas else np.nan,
                fast5=sum(r[1] <= 5 for r in pas), allwin_fast=sum(r[1] <= 5 and r[2] for r in pas))

pick = lambda a, b: [d for d in days if pd.Timestamp(a).date() <= d['date'] <= pd.Timestamp(b).date()]
TUNE, VALID, OLD = pick('2026-01-01', '2026-04-30'), pick('2026-05-01', '2026-08-07'), pick('2021-09-01', '2025-12-31')
RISKS = [200, 300, 400, 600]
log('tune days', len(TUNE), 'valid days', len(VALID))

rows = []
for sn, sig in SIGNALS.items():
    for sl, rr in BRACKETS:
        name = f'{sn}|sl{sl}|rr{rr}'
        tt, tv, to = (trades_for(sig, sl, rr, w) for w in (TUNE, VALID, OLD))
        if len(tt) < 10: continue
        best = max(RISKS, key=lambda r: (lambda e: (e['pass_'] - e['bust'], e['pass_']))(evalsim(tt, TUNE, r)))
        et, ev = evalsim(tt, TUNE, best), evalsim(tv, VALID, best)
        R = lambda t: np.mean([x['R'] for x in t]) if t else np.nan
        W_ = lambda t: 100 * np.mean([x['R'] > 0 for x in t]) if t else np.nan
        # luck baseline: 5 random twins on the same days, same bracket and risk
        lk = [evalsim(trades_for(sig, sl, rr, TUNE, np.random.default_rng(q)), TUNE, best) for q in range(5)]
        lkv = [evalsim(trades_for(sig, sl, rr, VALID, np.random.default_rng(q + 50)), VALID, best) for q in range(5)]
        rows.append(dict(strategy=name, risk=best,
            tune_n=len(tt), tune_win=W_(tt), tune_R=R(tt), tune_pass=et['pass_'], tune_bust=et['bust'],
            tune_days=et['days'], tune_fastest=et['fastest'], tune_fast5=et['fast5'], tune_allwin5=et['allwin_fast'],
            valid_n=len(tv), valid_win=W_(tv), valid_R=R(tv), valid_pass=ev['pass_'], valid_bust=ev['bust'],
            valid_days=ev['days'], valid_fastest=ev['fastest'], valid_fast5=ev['fast5'], valid_allwin5=ev['allwin_fast'],
            y2021_25_R=R(to), y2021_25_n=len(to),
            rand_tune_pass=np.mean([x['pass_'] for x in lk]), rand_tune_bust=np.mean([x['bust'] for x in lk]),
            rand_any_fast5=np.mean([x['fast5'] > 0 for x in lk + lkv]),
            rand_any_allwin5=np.mean([x['allwin_fast'] > 0 for x in lk + lkv])))
    log('done', sn)

X = pd.DataFrame(rows); X['tune_score'] = X.tune_pass - X.tune_bust
X.to_csv(BASE / 'strat100_2026.csv', index=False)
pd.set_option('display.width', 300); pd.set_option('display.max_columns', 40)
print('\nSTRATEGIES TESTED:', len(X))
print('\nTOP 15 BY TUNE (Jan-Apr) score, with VALID (May-Aug, unseen):')
c = ['strategy', 'risk', 'tune_n', 'tune_win', 'tune_R', 'tune_pass', 'tune_bust', 'tune_fastest',
     'valid_n', 'valid_win', 'valid_R', 'valid_pass', 'valid_bust', 'valid_fastest', 'y2021_25_R']
print(X.sort_values(['tune_score', 'tune_R'], ascending=False).head(15)[c].round(2).to_string(index=False))
print('\nSURVIVORS (tune_R>0 AND valid_R>0 AND 2021-25 R>0 AND valid bust<30):')
S = X[(X.tune_R > 0) & (X.valid_R > 0) & (X.y2021_25_R > 0) & (X.valid_bust < 30)]
print(S[c].round(2).to_string(index=False) if len(S) else 'none')
print('\nFAST PASSES (<=5 trading days) - real strategies vs random twins:')
print(f"  real strategies with a <=5-day pass somewhere in 2026: {((X.tune_fast5 + X.valid_fast5) > 0).mean()*100:.0f}%")
print(f"  ... with an ALL-WINS <=5-day pass:                   {((X.tune_allwin5 + X.valid_allwin5) > 0).mean()*100:.0f}%")
print(f"  RANDOM twins with a <=5-day pass:                    {X.rand_any_fast5.mean()*100:.0f}%")
print(f"  RANDOM twins with an ALL-WINS <=5-day pass:          {X.rand_any_allwin5.mean()*100:.0f}%")
print(f"\n  mean tune pass/bust real {X.tune_pass.mean():.0f}%/{X.tune_bust.mean():.0f}%  "
      f"random {X.rand_tune_pass.mean():.0f}%/{X.rand_tune_bust.mean():.0f}%")
print(f"  strategies with tune_R>0: {(X.tune_R>0).sum()}  valid_R>0: {(X.valid_R>0).sum()}  both: {((X.tune_R>0)&(X.valid_R>0)).sum()}")
print(f"  corr(tune_R, valid_R) = {X[['tune_R','valid_R']].corr().iloc[0,1]:+.2f}")
log('finished')
