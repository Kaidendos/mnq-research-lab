"""ts_backtest.py - backtest the systems in C:\\trading_system on Databento MNQ, 2026 only.

1) Claude 2 (MNQ-Signal-System/BEST_STRATEGY.md) versions v1..v6, rules as documented:
   %K(14) = 100*(C-LL14)/(HH14-LL14) crosses UP through 30, long only, SL 0.75 x ATR(14 Wilder),
   TP 0.5 x ATR, one position at a time, entry at signal-bar close, flat by 16:00, entries 09:40-15:30.
   v1 baseline 5 MNQ, lock at day P&L <= -$500 or 6 trades
   v2 + morning only (<=11:30) + signal bar closes in upper half
   v3 v2 at 1 NQ (10 MNQ fixed)
   v4/v6 v2 + vol-fitted size: n = min(10, (500+dayPnL)/stop$, (1500-dayPnL)/target$)  (live eval mode)
   v5 v4 + stop after first win
   News guard (their rule): no entries 30 min before -> 10 min after high-impact USD events; pre-open
   event (07:00-09:30) pauses entries until 10:30. Calendar file covers 2026-02-18..2026-07-15 only.
2) good_strategies.csv configs, using THEIR signal code (backtest_lab.fam / add_indicators), 3 MNQ as in
   their lab, their entry window 09:40-15:30, one position at a time, SL-first, flat at close.
Costs: gross AND net (1.1 pts per contract per round trip). Account: LucidDaily 50K eval
(EOD trail $2,000 -> lock $50,100, DLL $1,200, target $3,000, 50% consistency), every 2026 start day.
Analysis only - imports their code read-only, places no orders.
"""
import sys, os, re, numpy as np, pandas as pd
TS = r'C:\trading_system\MNQ-Signal-System'
BASE = r'C:\Users\YOU\daytrading-automation'
os.chdir(TS); sys.path.insert(0, TS)
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    import indicators, backtest_lab
COST = 1.1

df = pd.read_csv(os.path.join(BASE, 'data/databento/mnq_2021-2026_5min.csv'))
idx = pd.to_datetime(df.ts_et, utc=True)
df = df.set_index(idx)[['open', 'high', 'low', 'close', 'volume']].astype(float)
et = df.index.tz_convert('America/New_York'); hr = et.hour + et.minute / 60
df = df[(hr >= 9.5) & (hr < 16.0) & (df.volume > 0)]
df = df[df.index >= pd.Timestamp('2025-11-01', tz='UTC')]
d = backtest_lab.add_indicators(df)
ll, hh = d['low'].rolling(14).min(), d['high'].rolling(14).max()
d['stochK'] = 100 * (d['close'] - ll) / (hh - ll).replace(0, np.nan)
d['upper_half'] = d['close'] > (d['high'] + d['low']) / 2
d = d[d.index >= pd.Timestamp('2026-01-01', tz='UTC')]
print('bars', len(d), d.index[0], '->', d.index[-1])

ev = pd.read_csv(os.path.join(BASE, 'data/databento/ff_high_usd_events_2026.csv'))
ev_t = pd.to_datetime(ev.epoch, unit='s', utc=True).dt.tz_convert('America/New_York')
CAL_START, CAL_END = ev_t.min().normalize(), ev_t.max().normalize() + pd.Timedelta(days=1)
blk = {}
for t in ev_t:
    blk.setdefault(t.date(), []).append(t)
def news_ok(ts):
    e = ts.tz_convert('America/New_York')
    for t in blk.get(e.date(), []):
        h = t.hour + t.minute / 60
        if 7.0 <= h < 9.5 and e.hour + e.minute / 60 < 10.5: return False
        if t - pd.Timedelta(minutes=30) <= e <= t + pd.Timedelta(minutes=10): return False
    return True

O, H, L, Cc = d.open.values, d.high.values, d.low.values, d.close.values
ATR, K, UH, EH = d.atr.values, d.stochK.values, d.upper_half.values, d.ethour.values
DAY = np.array([x.date() for x in d.index.tz_convert('America/New_York')])
NEWS = np.array([news_ok(t) for t in d.index])

LAST = np.r_[DAY[1:] != DAY[:-1], True]
def claude2(v):
    morning, svol = v != 'v1', v != 'v1'
    fixed = {'v1': 5, 'v2': 5, 'v3': 10}.get(v)
    stop_after_win = v == 'v5'
    trades, pos = [], None
    dpnl, dtr, locked, cur = 0.0, 0, False, None
    for i in range(1, len(d)):
        if DAY[i] != cur: cur, dpnl, dtr, locked = DAY[i], 0.0, 0, False
        if pos:
            ex = pos['sl'] if L[i] <= pos['sl'] else pos['tp'] if H[i] >= pos['tp'] else (Cc[i] if LAST[i] else None)
            if ex is not None:
                g = (ex - pos['e']) * 2 * pos['n']; nt = g - COST * 2 * pos['n']
                trades.append(dict(day=cur, n=pos['n'], gross=g, net=nt, win=g > 0))
                dpnl += g; dtr += 1; pos = None
                if dtr >= 6 or (fixed and dpnl <= -500) or (stop_after_win and g > 0): locked = True
        if pos or locked or LAST[i]: continue
        h = EH[i]
        if not (9.6667 <= h <= (11.5 if morning else 15.5)): continue
        if not (K[i-1] <= 30 < K[i]) or not np.isfinite(ATR[i]) or ATR[i] <= 0: continue
        if svol and not UH[i]: continue
        if CAL_START.date() <= cur <= CAL_END.date() and not NEWS[i]: continue
        if fixed: n = fixed
        else:
            n = min(10, int((500 + dpnl) / (ATR[i] * 0.75 * 2)), int((1500 - dpnl) / (ATR[i] * 0.5 * 2)))
            if n < 1: locked = True; continue
        pos = dict(e=Cc[i], sl=Cc[i] - 0.75 * ATR[i], tp=Cc[i] + 0.5 * ATR[i], n=n)
    return pd.DataFrame(trades)

ALLDAYS = sorted(set(DAY))
def daily(tr, col):
    s = tr.groupby('day')[col].sum() if len(tr) else pd.Series(dtype=float)
    return pd.Series([max(-1200.0, s.get(x, 0.0)) for x in ALLDAYS], index=ALLDAYS)

def eval_starts(ds):
    vals, res = ds.values, []
    for s0 in range(0, len(vals) - 10):
        bal, fl, mx, best, out, nd = 50000., 48000., 50000., 0., 'open', 0
        for p in vals[s0:]:
            nd += 1; bal += p
            if bal <= fl: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
        res.append((out, nd, ds.index[s0]))
    return res

def summarize(tr, label):
    r = dict(strategy=label, trades=len(tr))
    if not len(tr): return r
    for col in ('gross', 'net'):
        x = tr[col]; gw, gl = x[x > 0].sum(), -x[x < 0].sum()
        r[f'{col}_usd'] = x.sum(); r[f'{col}_pf'] = gw / gl if gl else np.inf
    r['win%'] = 100 * (tr.gross > 0).mean()
    dn = daily(tr, 'net'); eq = dn.cumsum()
    r['worst_day'] = dn.min(); r['best_day'] = dn.max(); r['maxDD'] = (eq - eq.cummax()).min()
    res = eval_starts(dn); n = len(res); pas = [x for x in res if x[0] == 'pass']
    r['eval_pass%'] = 100 * len(pas) / n; r['eval_bust%'] = 100 * sum(x[0] == 'bust' for x in res) / n
    r['eval_open%'] = 100 - r['eval_pass%'] - r['eval_bust%']
    r['median_days_to_pass'] = float(np.median([x[1] for x in pas])) if pas else np.nan
    for half, a, b in (('JanApr', '2026-01-01', '2026-04-30'), ('MayAug', '2026-05-01', '2026-08-31')):
        sub = [x for x in res if pd.Timestamp(a).date() <= x[2] <= pd.Timestamp(b).date()]
        r[f'{half}_pass%'] = 100 * sum(x[0] == 'pass' for x in sub) / max(1, len(sub))
        r[f'{half}_bust%'] = 100 * sum(x[0] == 'bust' for x in sub) / max(1, len(sub))
    return r

pd.set_option('display.width', 320); pd.set_option('display.max_columns', 40)
rows, TR = [], {}
for v, lab in (('v1', 'Claude2 v1 baseline (all day, 5 MNQ)'), ('v2', 'Claude2 v2 morning+upper-half (5 MNQ)'),
               ('v3', 'Claude2 v3 = v2 at 1 NQ'), ('v4', 'Claude2 v4/v6 vol-fitted -$500/+$1,500 (LIVE EVAL MODE)'),
               ('v5', 'Claude2 v5 = v4 + stop after first win')):
    tr = claude2(v); TR[v] = tr; rows.append(summarize(tr, lab))

# replication check on the window their docs used (gross, as they reported it)
print('\n=== REPLICATION: their documented window ===')
for v, a, b, claim in (('v1', '2026-06-08', '2026-07-06', '+$9,958, 70% win, PF 2.31 (gross, 21d)'),
                       ('v4', '2026-06-08', '2026-07-09', '+$6,495, 91% win, 22 trades (gross, 23d)')):
    t = TR[v]; t = t[(t.day >= pd.Timestamp(a).date()) & (t.day <= pd.Timestamp(b).date())]
    gw, gl = t.gross[t.gross > 0].sum(), -t.gross[t.gross < 0].sum()
    print(f"  {v} {a}..{b}: mine {len(t)} trades, gross ${t.gross.sum():+,.0f}, win {100*(t.gross>0).mean():.0f}%, "
          f"PF {gw/gl if gl else np.inf:.2f}, net ${t.net.sum():+,.0f}  | their doc: {claim}")

# good_strategies.csv configs with their own signal code
gs = pd.read_csv(os.path.join(TS, 'good_strategies.csv'))
def parse(name):
    fam_ = name.split(' ')[0].split('-')[0]
    p = {}
    m = re.search(r'-(k|th)([\d.]+)', name.split(' ')[0])
    if m: p[m.group(1)] = float(m.group(2)) if m.group(1) == 'k' else int(float(m.group(2)))
    sl, tp = map(float, re.search(r'\[([\d.]+)/([\d.]+)', name).groups())
    g = re.search(r'adx(gt|lt)(\d+)', name); gate = (g.group(1), int(g.group(2))) if g else None
    side = name.rsplit(']', 1)[-1].strip() or 'both'
    return fam_, p, sl, tp, gate, side
ADX = d.adx.values
def gs_trades(name, ncon=3):
    fam_, p, sl, tp, gate, side = parse(name)
    lo, sh = backtest_lab.fam(d, fam_, p); lo, sh = lo.fillna(False).values, sh.fillna(False).values
    out, pos = [], None
    for i in range(len(d)):
        if pos:
            if pos['s'] > 0: ex = pos['sl'] if L[i] <= pos['sl'] else pos['tp'] if H[i] >= pos['tp'] else None
            else: ex = pos['sl'] if H[i] >= pos['sl'] else pos['tp'] if L[i] <= pos['tp'] else None
            if ex is None and LAST[i]: ex = Cc[i]
            if ex is not None:
                g = (ex - pos['e']) * pos['s'] * 2 * ncon
                out.append(dict(day=DAY[i], gross=g, net=g - COST * 2 * ncon)); pos = None
        if pos or LAST[i] or not (9.6667 <= EH[i] <= 15.5) or not (ATR[i] > 0): continue
        if gate and ((gate[0] == 'gt' and not ADX[i] >= gate[1]) or (gate[0] == 'lt' and not ADX[i] < gate[1])): continue
        s = 1 if side in ('both', 'long') and lo[i] else -1 if side in ('both', 'short') and sh[i] else 0
        if s: pos = dict(s=s, e=Cc[i], sl=Cc[i] - s * sl * ATR[i], tp=Cc[i] + s * tp * ATR[i])
    return pd.DataFrame(out)
for name in gs.name.head(12):
    rows.append(summarize(gs_trades(name), f'good_strategies: {name} (3 MNQ)'))

R = pd.DataFrame(rows); R.to_csv(os.path.join(BASE, 'ts_backtest_2026.csv'), index=False)
print('\n=== ALL OF 2026 (Jan 2 - Aug 7), NET of costs unless noted; eval = LucidDaily 50K, every start day ===')
cols = ['strategy', 'trades', 'win%', 'gross_usd', 'net_usd', 'net_pf', 'worst_day', 'maxDD',
        'eval_pass%', 'eval_bust%', 'median_days_to_pass', 'JanApr_pass%', 'JanApr_bust%', 'MayAug_pass%', 'MayAug_bust%']
print(R[cols].round(1).to_string(index=False))

print('\n=== Claude2 LIVE EVAL MODE (v4/v6) by month, net ===')
t = TR['v4'].copy(); t['month'] = [str(x)[:7] for x in t.day]
mm = t.groupby('month').agg(trades=('net', 'size'), win_pct=('win', lambda x: 100 * x.mean()), net=('net', 'sum'))
dn = daily(t, 'net'); dn.index = [str(x)[:7] for x in dn.index]
mm['worst_day'] = dn.groupby(level=0).min(); print(mm.round(0).to_string())
