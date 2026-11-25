"""news_test.py - post-news REACTION strategy, 2026, LucidDaily-legal (no position from T-1min to T+1min).
For each high-impact USD event (ff_high_usd_events_2026.csv: Feb 18 - Jul 15 2026; one trade per release time):
  release bar = the 5-min bar starting at the event minute (T..T+5). Its direction = the market's verdict
  ("good" or "bad" news as priced). Entry at that bar's CLOSE (T+5 min), MNQ Globex data (8:30 events trade too).
  momentum = trade WITH the release bar, fade = AGAINST it.
  exits: hold 15/30/60 min, or bracket stop = release-bar range x s, target = r x stop.
Costs 2.0 pts/contract (news slippage). Points per contract reported; analysis only.
"""
import numpy as np, pandas as pd
BASE = r'C:\Users\YOU\daytrading-automation'
df = pd.read_csv(BASE + r'\data\databento\mnq_2021-2026_5min.csv')
ts = pd.to_datetime(df.ts_et, utc=True).dt.tz_convert('America/New_York')
df.index = ts; df = df[df.index >= '2026-01-01']
O, H, L, C = [df[k].values for k in ('open', 'high', 'low', 'close')]
pos = {t: i for i, t in enumerate(df.index)}
ev = pd.read_csv(BASE + r'\data\databento\ff_high_usd_events_2026.csv')
ev['t'] = pd.to_datetime(ev.epoch, unit='s', utc=True).dt.tz_convert('America/New_York')
g = ev.groupby('t').name.apply(lambda s: ' + '.join(sorted(set(s)))).reset_index()
COST = 2.0
rows = []
for _, e in g.iterrows():
    t = e.t.floor('5min')
    if t not in pos: continue
    i = pos[t]; rng = H[i] - L[i]; side = np.sign(C[i] - O[i])
    if side == 0 or i + 13 >= len(C): continue
    entry = C[i]; r = dict(time=e.t, event=e['name'], move=C[i] - O[i], rng=rng)
    for hold in (3, 6, 12):
        r[f'mom_hold{hold*5}'] = (C[i + hold] - entry) * side - COST
        r[f'fade_hold{hold*5}'] = -(C[i + hold] - entry) * side - COST
    for s_, rr in ((0.5, 1.0), (0.5, 2.0), (1.0, 1.0)):
        for nm, sd_ in (('mom', side), ('fade', -side)):
            stop, tgt = entry - sd_ * s_ * rng, entry + sd_ * rr * s_ * rng; res = None
            for j in range(i + 1, min(i + 25, len(C))):          # max 2 hours
                if (sd_ > 0 and L[j] <= stop) or (sd_ < 0 and H[j] >= stop): res = -s_ * rng; break
                if (sd_ > 0 and H[j] >= tgt) or (sd_ < 0 and L[j] <= tgt): res = rr * s_ * rng; break
            if res is None: res = (C[min(i + 24, len(C) - 1)] - entry) * sd_
            r[f'{nm}_br{s_}x{rr}R'] = res - COST
    rows.append(r)
R = pd.DataFrame(rows); R.to_csv(BASE + r'\news_test_2026.csv', index=False)
print(f'release times traded: {len(R)}  ({R.time.min():%Y-%m-%d} .. {R.time.max():%Y-%m-%d}), median release-bar range {R.rng.median():.0f} pts')
cols = [c for c in R.columns if c.startswith(('mom', 'fade'))]
rng_ = np.random.default_rng(1)
out = []
for c in cols:
    x = R[c].values
    # random-direction control: same entry/exit timing, coin-flip side (holds only)
    out.append(dict(variant=c, trades=len(x), win_pct=100 * (x > 0).mean(), avg_pts=x.mean(), total_pts=x.sum(),
                    usd_3MNQ=x.sum() * 2 * 3, worst_pts=x.min(), best_pts=x.max()))
print(pd.DataFrame(out).round(1).sort_values('avg_pts', ascending=False).to_string(index=False))
R['month'] = R.time.dt.strftime('%Y-%m')
best = pd.DataFrame(out).sort_values('avg_pts', ascending=False).variant.iloc[0]
print(f'\nbest variant "{best}" by month (pts/contract):'); print(R.groupby('month')[best].agg(['count', 'sum', 'mean']).round(1).to_string())
R['type'] = R.event.str.extract(r'(CPI|PPI|Non-Farm|Unemployment Claims|FOMC|Federal Funds|GDP|PCE|Retail Sales|ISM|JOLTS|Fed Chair)', expand=False).fillna('other')
print(f'\n"{best}" by event type:'); print(R.groupby('type')[best].agg(['count', 'sum', 'mean']).round(1).sort_values('sum').to_string())
