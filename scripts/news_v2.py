"""news_v2.py - improve the post-news FADE, LucidDaily-legal, 2026.
Legal rules built in: never in a position from 1 min before to 1 min after ANY high-impact USD event; trades must
exit at the close of the last 5-min bar ending >= 2 min before the next red-folder event that day.
Grid (tuned on Feb 18 - Apr 30, validated on May 1 - Jul 15):
  delay      : enter at close of release bar (T+5) or next bar (T+10)
  min_move   : fade only if |release-bar move| >= x * ATR14(5m) before the event, x in {0, 1, 2}
  stop       : 'ext' = beyond the release-bar extreme (+2 pts) | 'r0.5' / 'r1.0' = 0.5 / 1.0 x release-bar range
  target     : 'none' (time exit) | 'open' = back to release-bar open (full retrace) | 'half' = 50% retrace
  hold       : max 30 or 60 min
Sizing: $400 risk per trade on the stop, max 40 MNQ. Costs 2.0 pts/contract.
Control: identical rules at the same clock times on days with NO red-folder event at that time.
Account: LucidDaily 50K eval (EOD trail $2k, DLL $1,200, $3k target, 50% consistency) over Feb 18 - Jul 15.
Analysis only.
"""
import numpy as np, pandas as pd, itertools
BASE = r'C:\Users\YOU\daytrading-automation'
df = pd.read_csv(BASE + r'\data\databento\mnq_2021-2026_5min.csv')
df.index = pd.to_datetime(df.ts_et, utc=True).dt.tz_convert('America/New_York')
df = df[df.index >= '2025-12-01']
O, H, L, C = [df[k].values for k in ('open', 'high', 'low', 'close')]
pc = np.r_[C[0], C[:-1]]; tr = np.maximum(H - L, np.maximum(abs(H - pc), abs(L - pc)))
ATR = pd.Series(tr).rolling(14).mean().values
POS = {t: i for i, t in enumerate(df.index)}
ev = pd.read_csv(BASE + r'\data\databento\ff_high_usd_events_2026.csv')
ev['t'] = pd.to_datetime(ev.epoch, unit='s', utc=True).dt.tz_convert('America/New_York')
EV = ev.groupby('t').name.apply(lambda s: ' + '.join(sorted(set(s)))).reset_index().sort_values('t')
EVT = list(EV.t)
CAL0, CAL1 = EV.t.min().normalize(), EV.t.max().normalize() + pd.Timedelta(days=1)
COST, SPLIT = 2.0, pd.Timestamp('2026-05-01', tz='America/New_York')

BYDAY = {}
for x in EVT: BYDAY.setdefault(x.date(), []).append(x)
def next_event_after(t):
    later = [x for x in BYDAY.get(t.date(), []) if x > t]
    return later[0] if later else None

def trade(t, delay, min_move, stop_m, tgt_m, hold):
    b = t.floor('5min')
    if b not in POS: return None
    i = POS[b]
    if i < 20 or i + 14 >= len(C): return None
    mv = C[i] - O[i]; rng = H[i] - L[i]
    if mv == 0 or abs(mv) < min_move * ATR[i - 1]: return None
    side = -np.sign(mv)                                      # FADE the first reaction
    ie = i + (delay // 5 - 1)                                 # entry bar index (close)
    t_entry = df.index[ie] + pd.Timedelta(minutes=5)
    nxt = next_event_after(t)
    if nxt is not None and t_entry >= nxt - pd.Timedelta(minutes=1): return None
    e = C[ie]
    if stop_m == 'ext': sd = (max(H[i:ie + 1]) + 2 - e) if side < 0 else (e - min(L[i:ie + 1]) + 2)
    else: sd = float(stop_m[1:]) * rng
    if sd < 4: sd = 4.0
    stop = e - side * sd
    tgt = None
    if tgt_m == 'open': tgt = O[i]
    elif tgt_m == 'half': tgt = O[i] + 0.5 * (C[i] - O[i])
    if tgt is not None and (tgt - e) * side <= 0: tgt = None
    last = ie + hold // 5
    if nxt is not None:                                        # must be flat >= 2 min before next event
        while last > ie and df.index[last] + pd.Timedelta(minutes=5) > nxt - pd.Timedelta(minutes=2): last -= 1
        if last <= ie: return None
    last = min(last, len(C) - 1)
    for j in range(ie + 1, last + 1):
        if (side > 0 and L[j] <= stop) or (side < 0 and H[j] >= stop):
            ex = O[j] if (side > 0 and O[j] <= stop) or (side < 0 and O[j] >= stop) else stop
            return (ex - e) * side - COST, sd
        if tgt is not None and ((side > 0 and H[j] >= tgt) or (side < 0 and L[j] <= tgt)):
            return (tgt - e) * side - COST, sd
    return (C[last] - e) * side - COST, sd

TDAYS = sorted({x.date() for x in df.index if CAL0 <= x < CAL1 and x.weekday() < 5})
def evals(trs):
    by = {}
    for t, pts, sd in trs:
        n = min(40, int(400 // (sd * 2)))
        if n >= 1: by[t.date()] = max(-1200., by.get(t.date(), 0.) + pts * 2 * n)
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
    usd = sum(by.values()); eq = np.cumsum([by.get(x, 0.) for x in TDAYS])
    return 100 * res.count('pass') / len(res), 100 * res.count('bust') / len(res), usd, (eq - np.maximum.accumulate(eq)).min()

def stats(xs):
    x = np.array([p for _, p, _ in xs]) if xs else np.array([np.nan])
    return len(xs), 100 * np.nanmean(x > 0), np.nanmean(x)

# control clock times: same time-of-day on weekdays with no red-folder event within 60 min
evset = set(EVT)
def is_quiet(t): return all(abs((x - t).total_seconds()) > 3600 for x in EVT if x.date() == t.date())
CTRL = []
for clk in sorted({(x.hour, x.minute) for x in EVT}):
    for dd in TDAYS:
        t = pd.Timestamp(dd).tz_localize('America/New_York') + pd.Timedelta(hours=clk[0], minutes=clk[1])
        if is_quiet(t): CTRL.append(t)

GRID = list(itertools.product([5, 10], [0, 1, 2], ['ext', 'r0.5', 'r1.0'], ['none', 'open', 'half'], [30, 60]))
rows = []
for g in GRID:
    tr = [(t, *r) for t in EVT for r in [trade(t, *g)] if r]
    tu = [x for x in tr if x[0] < SPLIT]; va = [x for x in tr if x[0] >= SPLIT]
    ct = [(t, *r) for t in CTRL for r in [trade(t, *g)] if r]
    nt, wt, at = stats(tu); nv, wv, av = stats(va); nc, wc, ac = stats(ct)
    p, b, usd, dd = evals(tr)
    rows.append(dict(delay=g[0], min_move=g[1], stop=g[2], target=g[3], hold=g[4],
                     tune_n=nt, tune_win=wt, tune_pts=at, valid_n=nv, valid_win=wv, valid_pts=av,
                     ctrl_n=nc, ctrl_win=wc, ctrl_pts=ac, all_n=len(tr), usd_400risk=usd, maxDD=dd,
                     eval_pass=p, eval_bust=b))
X = pd.DataFrame(rows); X.to_csv(BASE + r'\news_v2_grid.csv', index=False)
pd.set_option('display.width', 300); pd.set_option('display.max_columns', 30)
base = X[(X.delay == 5) & (X.min_move == 0) & (X.stop == 'r1.0') & (X.target == 'none') & (X.hold == 30)]
print('BASELINE (fade, T+5, no filter, 1x range stop, 30-min hold, legal exits):'); print(base.round(1).to_string(index=False))
print(f'\nGRID {len(X)} variants. Control (same clock times, no news) average pts/trade across grid: {X.ctrl_pts.mean():+.2f}')
print('\nTOP 15 BY FEB-APR pts/trade (min 15 trades) -> MAY-JUL unseen:')
T = X[X.tune_n >= 15].sort_values('tune_pts', ascending=False)
print(T.head(15).round(1).to_string(index=False))
print(f"\ncorr(tune_pts, valid_pts) = {X[X.tune_n>=15][['tune_pts','valid_pts']].corr().iloc[0,1]:+.2f}")
print(f"variants positive in BOTH halves: {((X.tune_pts > 0) & (X.valid_pts > 0)).sum()} of {len(X)}; "
      f"and beating control in both: {((X.tune_pts > X.ctrl_pts) & (X.valid_pts > X.ctrl_pts) & (X.tune_pts > 0) & (X.valid_pts > 0)).sum()}")
for col in ('delay', 'min_move', 'stop', 'target', 'hold'):
    print(f'\nBY {col}:'); print(X.groupby(col)[['tune_pts', 'valid_pts', 'ctrl_pts', 'eval_pass', 'eval_bust']].mean().round(2).to_string())
