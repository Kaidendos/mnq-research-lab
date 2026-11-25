"""asia_test2.py - same as asia_test.py but indicators are computed ONLY from the bars of the session being traded
(like a NinjaTrader chart with that session's trading-hours template). RTH row must reproduce the lab (~+4 pts/trade).
Sessions (ET): ASIA 18:00-02:00 (entries 19:00-01:30), LONDON 02:00-08:00 (entries 02:40-07:30), RTH 09:30-16:00
(entries 09:40-15:30). Flat at session end. Costs 1.1 pts/contract. Analysis only."""
import numpy as np, pandas as pd
raw = pd.read_csv(r'C:\Users\YOU\daytrading-automation\data\databento\mnq_2021-2026_5min.csv')
raw.index = pd.to_datetime(raw.ts_et, utc=True).dt.tz_convert('America/New_York'); raw = raw[raw.index >= '2025-11-01']
def wilder(x, n): return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().values
SPLIT, D0, D1 = pd.Timestamp('2026-05-01').date(), pd.Timestamp('2026-01-02').date(), pd.Timestamp('2026-08-07').date()
SESS = {'ASIA': (18 * 60, 26 * 60, 19 * 60, 25 * 60 + 30), 'LONDON': (2 * 60, 8 * 60, 2 * 60 + 40, 7 * 60 + 30),
        'RTH': (9 * 60 + 30, 16 * 60, 9 * 60 + 40, 15 * 60 + 30)}
def session(name):
    s0, s1, e0, e1 = SESS[name]
    m = raw.index.hour * 60 + raw.index.minute
    mw = np.where(m < 3 * 60, m + 1440, m) if name == 'ASIA' else m
    df = raw[(mw >= s0) & (mw < s1)].copy(); mw = mw[(mw >= s0) & (mw < s1)]
    key = (df.index.tz_localize(None) + pd.Timedelta(hours=6)).date if name == 'ASIA' else df.index.date
    return df, np.asarray(mw), np.array(key), e0, e1
def test(name):
    df, MW, KEY, e0, e1 = session(name)
    O, H, L, C, V = [df[k].values.astype(float) for k in ('open', 'high', 'low', 'close', 'volume')]
    pc = np.r_[C[0], C[:-1]]; TR = np.maximum(H - L, np.maximum(abs(H - pc), abs(L - pc))); ATR = wilder(TR, 14)
    up = H - np.r_[H[0], H[:-1]]; dn = np.r_[L[0], L[:-1]] - L
    pdm = np.where((up > dn) & (up > 0), up, 0.); ndm = np.where((dn > up) & (dn > 0), dn, 0.)
    pdi = 100 * wilder(pdm, 14) / np.maximum(ATR, 1e-9); ndi = 100 * wilder(ndm, 14) / np.maximum(ATR, 1e-9)
    ADX = wilder(100 * abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-9), 14)
    E21 = pd.Series(C).ewm(span=21, adjust=False).mean().values; E50 = pd.Series(C).ewm(span=50, adjust=False).mean().values
    g = pd.Series(KEY); vv = np.maximum(V, 1); tp = (H + L + C) / 3
    cv = pd.Series(vv).groupby(g).cumsum().values; VW = pd.Series(tp * vv).groupby(g).cumsum().values / cv
    VSD = np.sqrt(np.maximum(pd.Series(tp * tp * vv).groupby(g).cumsum().values / cv - VW ** 2, 0))
    e21p = np.r_[E21[0], E21[:-1]]
    EL = (E21 > E50) & (E21 >= e21p) & (L <= E21) & (C > E21) & (ADX >= 25)
    ES = (E21 < E50) & (E21 <= e21p) & (H >= E21) & (C < E21) & (ADX >= 25)
    VL = (L < VW - 3 * VSD) & (C > VW - 3 * VSD) & (VSD > 0)
    last = np.r_[KEY[1:] != KEY[:-1], True]
    nd = len({k for k in KEY if D0 <= k <= D1}); res = {}
    for strat in ('ema_pullback', 'vwap3_long'):
        out, pos = [], None
        for i in range(60, len(C)):
            if pos:
                s = pos['s']; ex = None
                if (s > 0 and L[i] <= pos['sl']) or (s < 0 and H[i] >= pos['sl']): ex = pos['sl']
                elif (s > 0 and H[i] >= pos['tp']) or (s < 0 and L[i] <= pos['tp']): ex = pos['tp']
                elif last[i]: ex = C[i]
                if ex is not None: out.append((KEY[i], (ex - pos['e']) * s - 1.1)); pos = None
            if pos or last[i] or not (e0 <= MW[i] <= e1) or not ATR[i] > 0: continue
            if strat == 'ema_pullback':
                s = 1 if EL[i] else -1 if ES[i] else 0
                if s: pos = dict(s=s, e=C[i], sl=C[i] - s * ATR[i], tp=C[i] + s * 0.5 * ATR[i])
            elif VL[i]:
                sd = min(2 * ATR[i], max(1.0, C[i] - L[i] + 0.25)); pos = dict(s=1, e=C[i], sl=C[i] - sd, tp=C[i] + 2 * sd)
        tr = [x for x in out if D0 <= x[0] <= D1]; x = np.array([p for _, p in tr])
        a_ = np.mean([p for d_, p in tr if d_ < SPLIT]); b_ = np.mean([p for d_, p in tr if d_ >= SPLIT])
        mo = pd.Series([p for _, p in tr], index=[str(d_)[:7] for d_, _ in tr]).groupby(level=0).sum()
        print(f'{strat:13s} {name:7s} tr/day {len(tr)/nd:4.2f}  win {100*(x>0).mean():4.1f}%  ATR {np.median(ATR[-5000:]):5.1f}  '
              f'pts/tr {x.mean():+6.2f}  Jan-Apr {a_:+6.2f}  May-Aug {b_:+6.2f}  2026 @3MNQ ${x.sum()*6:+8,.0f}  '
              f'months+ {int((mo>0).sum())}/{len(mo)}')
for nm in ('RTH', 'ASIA', 'LONDON'): test(nm)
