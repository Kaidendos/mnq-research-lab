"""asia_test.py - would the plan's entries work overnight? MNQ 5-min Globex, 2026 (Jan 2 - Aug 7).
Indicators on the continuous 24h series: EMA21/50, Wilder ATR(14), Wilder ADX(14), session VWAP anchored 18:00 ET
with volume-weighted sigma. Same rules as the plan:
  ema_pullback : EMA21>EMA50 & rising, low<=EMA21<close, ADX>=25 (mirror short); stop 1.0 ATR, target 0.5 ATR
  vwap3_long   : low < VWAP-3sigma < close; stop below bar low (max 2 ATR), target 2R
Windows (ET, entries by bar start; flat at window end): ASIA 19:00-02:00, LONDON 02:00-08:00, RTH 09:40-15:30 (flat 16:00).
Costs 1.1 pts/contract. One position at a time per strategy per window. Analysis only."""
import numpy as np, pandas as pd
df = pd.read_csv(r'C:\Users\YOU\daytrading-automation\data\databento\mnq_2021-2026_5min.csv')
ts = pd.to_datetime(df.ts_et, utc=True).dt.tz_convert('America/New_York')
df.index = ts; df = df[df.index >= '2025-11-01']
O, H, L, C, V = [df[k].values.astype(float) for k in ('open', 'high', 'low', 'close', 'volume')]
M = (df.index.hour * 60 + df.index.minute).values
TDATE = np.array((df.index.tz_localize(None) + pd.Timedelta(hours=6)).date)
def wilder(x, n): return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().values
pc = np.r_[C[0], C[:-1]]; TR = np.maximum(H - L, np.maximum(abs(H - pc), abs(L - pc))); ATR = wilder(TR, 14)
up = H - np.r_[H[0], H[:-1]]; dn = np.r_[L[0], L[:-1]] - L
pdm = np.where((up > dn) & (up > 0), up, 0.); ndm = np.where((dn > up) & (dn > 0), dn, 0.)
pdi = 100 * wilder(pdm, 14) / np.maximum(ATR, 1e-9); ndi = 100 * wilder(ndm, 14) / np.maximum(ATR, 1e-9)
ADX = wilder(100 * abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-9), 14)
E21 = pd.Series(C).ewm(span=21, adjust=False).mean().values; E50 = pd.Series(C).ewm(span=50, adjust=False).mean().values
tp = (H + L + C) / 3; vv = np.maximum(V, 1); g = pd.Series(TDATE)
cv = pd.Series(vv).groupby(g).cumsum().values; VW = pd.Series(tp * vv).groupby(g).cumsum().values / cv
VSD = np.sqrt(np.maximum(pd.Series(tp * tp * vv).groupby(g).cumsum().values / cv - VW ** 2, 0))
EMA_L = (E21 > E50) & (E21 >= np.r_[E21[0], E21[:-1]]) & (L <= E21) & (C > E21) & (ADX >= 25)
EMA_S = (E21 < E50) & (E21 <= np.r_[E21[0], E21[:-1]]) & (H >= E21) & (C < E21) & (ADX >= 25)
VW_L = (L < VW - 3 * VSD) & (C > VW - 3 * VSD) & (VSD > 0)
WIN = {'ASIA 19:00-02:00': (19 * 60, 26 * 60), 'LONDON 02:00-08:00': (2 * 60, 8 * 60), 'RTH 09:40-15:30': (9 * 60 + 40, 15 * 60 + 30)}
END = {'ASIA 19:00-02:00': 26 * 60, 'LONDON 02:00-08:00': 8 * 60, 'RTH 09:40-15:30': 16 * 60}
def mm(i):  # minutes, Asia evening wraps past midnight
    x = M[i]; return x + 1440 if x < 18 * 60 and x < 3 * 60 else x
def run(strat, wname):
    a, b = WIN[wname]; end = END[wname]; out, pos = [], None
    for i in range(60, len(C) - 1):
        t = mm(i) if wname.startswith('ASIA') else M[i]
        if pos:
            s = pos['s']; ex = None
            if (s > 0 and L[i] <= pos['sl']) or (s < 0 and H[i] >= pos['sl']): ex = pos['sl']
            elif (s > 0 and H[i] >= pos['tp']) or (s < 0 and L[i] <= pos['tp']): ex = pos['tp']
            elif t + 5 >= end or TDATE[i + 1] != TDATE[i]: ex = C[i]
            if ex is not None: out.append((pos['d'], (ex - pos['e']) * s - 1.1, pos['sd'], pos['h'])); pos = None
            continue
        if not (a <= t <= b) or t + 5 >= end or not ATR[i] > 0: continue
        if strat == 'ema_pullback':
            s = 1 if EMA_L[i] else -1 if EMA_S[i] else 0
            if s: pos = dict(s=s, e=C[i], sl=C[i] - s * ATR[i], tp=C[i] + s * 0.5 * ATR[i], sd=ATR[i], d=TDATE[i], h=M[i])
        elif VW_L[i]:
            sd = min(2 * ATR[i], max(1.0, C[i] - L[i] + 0.25))
            pos = dict(s=1, e=C[i], sl=C[i] - sd, tp=C[i] + 2 * sd, sd=sd, d=TDATE[i], h=M[i])
    return [x for x in out if pd.Timestamp('2026-01-02').date() <= x[0] <= pd.Timestamp('2026-08-07').date()]
ndays = len({x for x in TDATE if pd.Timestamp('2026-01-02').date() <= x <= pd.Timestamp('2026-08-07').date()})
SPLIT = pd.Timestamp('2026-05-01').date()
print(f'{"strategy":14s} {"window":20s} {"tr/day":>6s} {"win%":>5s} {"avgATR":>6s} {"pts/tr":>7s} {"Jan-Apr":>8s} {"May-Aug":>8s} {"2026 $ @3MNQ":>12s}')
for strat in ('ema_pullback', 'vwap3_long'):
    for w in WIN:
        tr = run(strat, w); x = np.array([p for _, p, _, _ in tr])
        a_ = np.mean([p for d_, p, _, _ in tr if d_ < SPLIT]); b_ = np.mean([p for d_, p, _, _ in tr if d_ >= SPLIT])
        print(f'{strat:14s} {w:20s} {len(tr)/ndays:6.2f} {100*(x>0).mean():5.1f} {np.mean([s_ for _, _, s_, _ in tr]):6.1f} '
              f'{x.mean():+7.2f} {a_:+8.2f} {b_:+8.2f} {x.sum()*2*3:+12,.0f}')
print(f'\ntypical overnight vs day bar size: ATR median Asia {np.median(ATR[(M>=19*60)|(M<2*60)][-20000:]):.1f} pts, '
      f'London {np.median(ATR[(M>=2*60)&(M<8*60)][-20000:]):.1f}, RTH {np.median(ATR[(M>=9*60+30)&(M<16*60)][-20000:]):.1f}; cost = 1.1 pts')
