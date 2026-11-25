"""asia_lab.py - search for an overnight (18:00 -> 08:25 ET) MNQ strategy, 2026 only.
Indicators computed from NIGHT bars only (18:00-08:25 ET, continuous across nights), session VWAP anchored 18:00.
Every trade is flat by 08:25 ET (before 08:30 releases; no USD red-folder events fall inside 18:00-08:25 normally).
TUNE Jan 2 - Apr 30, VALID May 1 - Aug 7. Costs 1.1 pts/contract. Trades saved for the merge test. Analysis only.
Families:
  drift        : long at the close of the first bar >= T_in, exit at T_out (no target), disaster stop k x ATR
  vwap_fade    : close beyond VWAP +/- k sigma then back inside -> fade, target VWAP
  bb_rev       : close back inside Bollinger(20, k) -> fade, bracket
  rsi_rev      : RSI14 crosses back above 30 / below 70, bracket
  range_fade   : 19:00-21:00 range set; later touch of its high/low with close back inside -> fade, target mid
  london_break : close beyond the 19:00-02:00 range between 02:00-05:00 -> follow, bracket
  ema_pb       : EMA21/50 pullback + ADX>=25 (night indicators), bracket
"""
import numpy as np, pandas as pd, itertools
raw = pd.read_csv(r'C:\Users\YOU\daytrading-automation\data\databento\mnq_2021-2026_5min.csv')
raw.index = pd.to_datetime(raw.ts_et, utc=True).dt.tz_convert('America/New_York'); raw = raw[raw.index >= '2025-11-01']
m = raw.index.hour * 60 + raw.index.minute
MW = np.where(m < 18 * 60, m + 1440, m)                      # minutes since prior-day midnight; night = 1080..1945
df = raw[(MW >= 1080) & (MW < 1440 + 8 * 60 + 25)].copy(); MW = MW[(MW >= 1080) & (MW < 1440 + 505)]
KEY = np.array((df.index.tz_localize(None) + pd.Timedelta(hours=6)).date)
O, H, L, C, V = [df[k].values.astype(float) for k in ('open', 'high', 'low', 'close', 'volume')]
def wilder(x, n): return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().values
pc = np.r_[C[0], C[:-1]]; ATR = wilder(np.maximum(H - L, np.maximum(abs(H - pc), abs(L - pc))), 14)
up = H - np.r_[H[0], H[:-1]]; dn = np.r_[L[0], L[:-1]] - L
pdi = 100 * wilder(np.where((up > dn) & (up > 0), up, 0.), 14) / np.maximum(ATR, 1e-9)
ndi = 100 * wilder(np.where((dn > up) & (dn > 0), dn, 0.), 14) / np.maximum(ATR, 1e-9)
ADX = wilder(100 * abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-9), 14)
E21 = pd.Series(C).ewm(span=21, adjust=False).mean().values; E50 = pd.Series(C).ewm(span=50, adjust=False).mean().values
g = pd.Series(KEY); vv = np.maximum(V, 1); tp = (H + L + C) / 3
cv = pd.Series(vv).groupby(g).cumsum().values; VW = pd.Series(tp * vv).groupby(g).cumsum().values / cv
VSD = np.sqrt(np.maximum(pd.Series(tp * tp * vv).groupby(g).cumsum().values / cv - VW ** 2, 0))
S20 = pd.Series(C).rolling(20).mean().values; SD20 = pd.Series(C).rolling(20).std().values
d1 = np.diff(C, prepend=C[0]); RSI = 100 - 100 / (1 + wilder(np.maximum(d1, 0), 14) / np.maximum(wilder(np.maximum(-d1, 0), 14), 1e-9))
LAST = np.r_[KEY[1:] != KEY[:-1], True] | (MW >= 1440 + 500)
# per-night ranges
R1 = {}; R2 = {}
for k_, idx in pd.Series(np.arange(len(C))).groupby(KEY):
    ii = idx.values; a = ii[(MW[ii] >= 1140) & (MW[ii] < 1260)]; b = ii[(MW[ii] >= 1140) & (MW[ii] < 1560)]
    R1[k_] = (H[a].max(), L[a].min()) if len(a) else (np.nan, np.nan); R2[k_] = (H[b].max(), L[b].min()) if len(b) else (np.nan, np.nan)
D0, D1_, SPLIT = pd.Timestamp('2026-01-02').date(), pd.Timestamp('2026-08-07').date(), pd.Timestamp('2026-05-01').date()

def sim(lo, sh, side, e0, e1, sl, tp, tgt_lvl=None, maxn=3):
    out, pos, cur, n = [], None, None, 0
    for i in range(60, len(C)):
        if KEY[i] != cur: cur, n = KEY[i], 0
        if pos:
            s = pos['s']; ex = None
            if (s > 0 and L[i] <= pos['sl']) or (s < 0 and H[i] >= pos['sl']): ex = pos['sl']
            elif pos['tp'] is not None and ((s > 0 and H[i] >= pos['tp']) or (s < 0 and L[i] <= pos['tp'])): ex = pos['tp']
            elif LAST[i]: ex = C[i]
            if ex is not None: out.append((KEY[i], (ex - pos['e']) * s - 1.1, pos['sd'])); pos = None
        if pos or LAST[i] or n >= maxn or not (e0 <= MW[i] <= e1) or not ATR[i] > 0: continue
        s = 1 if side in ('long', 'both') and lo[i] else -1 if side in ('short', 'both') and sh[i] else 0
        if not s: continue
        sd = sl * ATR[i]
        t = tgt_lvl[i] if tgt_lvl is not None else (C[i] + s * tp * ATR[i] if tp else None)
        if t is not None and (t - C[i]) * s <= 0.25: continue
        pos = dict(s=s, e=C[i], sl=C[i] - s * sd, tp=t, sd=sd); n += 1
    return [x for x in out if D0 <= x[0] <= D1_]

def drift(t_in, t_out, k, side):
    out, pos = [], None
    for i in range(60, len(C)):
        if pos:
            s = pos['s']; ex = None
            if (s > 0 and L[i] <= pos['sl']) or (s < 0 and H[i] >= pos['sl']): ex = pos['sl']
            elif MW[i] >= t_out - 5 or LAST[i]: ex = C[i]
            if ex is not None: out.append((KEY[i], (ex - pos['e']) * s - 1.1, pos['sd'])); pos = None
            continue
        if MW[i] == t_in - 5 and ATR[i] > 0:
            s = 1 if side == 'long' else -1; sd = k * ATR[i] if k else 1e9
            pos = dict(s=s, e=C[i], sl=C[i] - s * sd, sd=k * ATR[i] if k else 4 * ATR[i])
    return [x for x in out if D0 <= x[0] <= D1_]

prev = lambda x: np.r_[x[0], x[:-1]]
cands = {}
for t_in, t_out, k in itertools.product((1085, 1140, 1320, 1560), (1560, 1740, 1945), (0, 3, 6)):
    if t_out <= t_in + 30: continue
    for side in ('long', 'short'):
        cands[f'drift|{side}|in{(t_in//60)%24:02d}:{t_in%60:02d}|out{(t_out//60)%24:02d}:{t_out%60:02d}|stop{k}ATR'] = drift(t_in, t_out, k, side)
WINS = {'asia': (1140, 1530), 'night': (1110, 1900)}
for k in (1.5, 2.0, 2.5):
    lo = (prev(C) < prev(VW - k * VSD)) & (C > VW - k * VSD); sh = (prev(C) > prev(VW + k * VSD)) & (C < VW + k * VSD)
    for side, (wn, (a, b)), sl in itertools.product(('long', 'short', 'both'), WINS.items(), (1.0, 2.0)):
        cands[f'vwap_fade{k}|{side}|{wn}|sl{sl}|tgtVWAP'] = sim(lo, sh, side, a, b, sl, None, VW)
    lb, ub = S20 - k * SD20, S20 + k * SD20
    lo = (prev(C) < prev(lb)) & (C >= lb); sh = (prev(C) > prev(ub)) & (C <= ub)
    for side, (wn, (a, b)), (sl, tp) in itertools.product(('long', 'short', 'both'), WINS.items(), ((1, 0.5), (1, 1), (2, 1))):
        cands[f'bb_rev{k}|{side}|{wn}|{sl}/{tp}'] = sim(lo, sh, side, a, b, sl, tp)
for th in (25, 30):
    lo = (prev(RSI) < th) & (RSI >= th); sh = (prev(RSI) > 100 - th) & (RSI <= 100 - th)
    for side, (wn, (a, b)), (sl, tp) in itertools.product(('long', 'short', 'both'), WINS.items(), ((1, 0.5), (1, 1), (2, 1))):
        cands[f'rsi_rev{th}|{side}|{wn}|{sl}/{tp}'] = sim(lo, sh, side, a, b, sl, tp)
r1h = np.array([R1[k_][0] for k_ in KEY]); r1l = np.array([R1[k_][1] for k_ in KEY])
r2h = np.array([R2[k_][0] for k_ in KEY]); r2l = np.array([R2[k_][1] for k_ in KEY])
lo = (L <= r1l) & (C > r1l); sh = (H >= r1h) & (C < r1h); mid = (r1h + r1l) / 2
for side, sl in itertools.product(('long', 'short', 'both'), (1.0, 2.0)):
    cands[f'range_fade|{side}|sl{sl}|tgtMid'] = sim(lo, sh, side, 1265, 1530, sl, None, mid)
lo = (C > r2h) & (prev(C) <= r2h); sh = (C < r2l) & (prev(C) >= r2l)
for side, (sl, tp) in itertools.product(('long', 'short', 'both'), ((1, 1), (1, 2), (2, 2))):
    cands[f'london_break|{side}|{sl}/{tp}'] = sim(lo, sh, side, 1560, 1740, sl, tp, maxn=1)
e21p = prev(E21)
lo = (E21 > E50) & (E21 >= e21p) & (L <= E21) & (C > E21) & (ADX >= 25); sh = (E21 < E50) & (E21 <= e21p) & (H >= E21) & (C < E21) & (ADX >= 25)
for side, (wn, (a, b)), (sl, tp) in itertools.product(('long', 'short', 'both'), WINS.items(), ((1, 0.5), (1, 1), (1.5, 1.5), (2, 1))):
    cands[f'ema_pb|{side}|{wn}|{sl}/{tp}'] = sim(lo, sh, side, a, b, sl, tp)

nights = len({k_ for k_ in KEY if D0 <= k_ <= D1_})
rows = []
for nm, tr in cands.items():
    t_ = [p for d_, p, _ in tr if d_ < SPLIT]; v_ = [p for d_, p, _ in tr if d_ >= SPLIT]
    if len(t_) < 15 or len(v_) < 10: continue
    mo = pd.Series([p for _, p, _ in tr], index=[str(d_)[:7] for d_, _, _ in tr]).groupby(level=0).sum()
    rows.append(dict(strategy=nm, per_night=len(tr) / nights, win=100 * np.mean([p > 0 for _, p, _ in tr]),
                     tune_pts=np.mean(t_), valid_pts=np.mean(v_), usd_2026_3mnq=6 * sum(p for _, p, _ in tr),
                     months_pos=int((mo > 0).sum()), months=len(mo)))
X = pd.DataFrame(rows).sort_values('tune_pts', ascending=False)
X.to_csv(r'C:\Users\YOU\daytrading-automation\asia_lab.csv', index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 60)
print(f'overnight candidates tested: {len(X)} | positive both halves: {((X.tune_pts>0)&(X.valid_pts>0)).sum()} | '
      f'corr(Jan-Apr, May-Aug) {X[["tune_pts","valid_pts"]].corr().iloc[0,1]:+.2f}')
print('\nTOP 15 BY JAN-APR -> MAY-AUG:'); print(X.head(15).round(2).to_string(index=False))
print('\nBY FAMILY (mean pts/trade):')
X['family'] = X.strategy.str.split('|').str[0].str.replace(r'[\d.]+$', '', regex=True)
print(X.groupby('family')[['tune_pts', 'valid_pts', 'usd_2026_3mnq']].mean().round(2).sort_values('valid_pts', ascending=False).to_string())
DR = X[X.strategy.str.startswith('drift')]
print('\nDRIFT detail (long vs short = the control):'); print(DR.sort_values('tune_pts', ascending=False).head(12).round(2).to_string(index=False))
pick = X[(X.tune_pts > 0)].head(10).strategy.tolist()
rob = X[(X.tune_pts > 0) & (X.valid_pts > 0) & (X.months_pos >= 6)].strategy.tolist()
keep = list(dict.fromkeys(pick + rob))
pd.DataFrame([(nm, d_, p, sd) for nm in keep for d_, p, sd in cands[nm]], columns=['strategy', 'date', 'pts', 'sd']) \
  .to_csv(r'C:\Users\YOU\daytrading-automation\asia_lab_trades.csv', index=False)
print(f'\nsaved trades for {len(keep)} candidates (top-10 by Jan-Apr + robust ones) to asia_lab_trades.csv')
print('robust (positive both halves, >=6/8 months positive):'); print(X[X.strategy.isin(rob)].round(2).to_string(index=False) if rob else 'none')
