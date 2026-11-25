"""merge_night.py - day plan (EMA pullback 3->4 + news fade 3 + VWAP 3sd long 1) + overnight drift, Feb 18 - Jul 15 2026.
Also: how much of NQ's 2026 move happened overnight vs in the day session (is the drift just 2026's bull market?)."""
import numpy as np, pandas as pd
src = open(r'C:\Users\YOU\daytrading-automation\bottom_lab.py').read().split("NAMES = [")[0]
exec(src)
S = sigs('vwap_band_3'); VW3 = [(a, b, c) for a, b, c, _ in run(*S, 'long', '2R', 'ext')]
A = pd.read_csv(r'C:\Users\YOU\daytrading-automation\asia_lab_trades.csv'); A['date'] = pd.to_datetime(A.date).dt.date
ROLL_NIGHTS = {pd.Timestamp('2026-03-19').date(), pd.Timestamp('2026-06-17').date()}   # contract-roll jumps in MNQ.v.0
def night(nm): return [(r.date, r.pts, r.sd) for r in A[A.strategy == nm].itertuples() if r.date not in ROLL_NIGHTS]
_all = A[A.strategy == 'drift|long|in18:05|out08:25|stop6ATR']
print(f"drift 2026 with roll nights: {_all.pts.sum():+,.0f} pts/contract | removed roll nights: "
      f"{_all[_all.date.isin(ROLL_NIGHTS)].pts.sum():+,.0f} | clean: {_all[~_all.date.isin(ROLL_NIGHTS)].pts.sum():+,.0f}")
def run_eval(comps, days, rule, need_runway=0):
    res = []
    for s0 in range(0, len(days) - 5):
        if len(days) - s0 < need_runway: break
        bal, fl, mx, best, out, nd = 50000., 48000., 50000., 0., 'open', 0
        for k in range(s0, len(days)):
            nd += 1; sz = rule(bal - 50000)
            p = max(-1200., sum(sz[n] * comps[n][k] for n in sz)); bal += p
            if bal <= fl: out = 'bust'; break
            best = max(best, p); prof = bal - 50000
            if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
            mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
        res.append((out, nd))
    n = max(1, len(res)); pas = [r[1] for r in res if r[0] == 'pass']
    return 100 * len(pas) / n, 100 * sum(r[0] == 'bust' for r in res) / n, (np.median(pas) if pas else np.nan), (min(pas) if pas else np.nan)
DRIFT = 'drift|long|in18:05|out08:25|stop6ATR'
LB = 'london_break|both|2/2'
def report(label, extra):
    out = [f'{label:46s}']
    for nm_, days, rw in (('Feb-Apr', TD, 0), ('May-Jul', VD, 0), ('ALL, runway>=60d', DAYS, 60)):
        comps = {'ema': perday(base_news, days), 'fade': perday(NEWSFADE, days), 'vw': perday(VW3, days)}
        for k_, (trs, _) in extra.items(): comps[k_] = perday(trs, days)
        rule = lambda p: dict({'ema': 4 if p >= 1000 else 3, 'fade': 3, 'vw': 1}, **{k_: n for k_, (_, n) in extra.items()})
        p, b, md, mn = run_eval(comps, days, rule, rw)
        out.append(f'{nm_}: pass {p:3.0f}% bust {b:3.0f}% median {md} fastest {mn}')
    print(' | '.join(out))
print('=== DAY PLAN + NIGHT ===')
report('day plan only', {})
for n in (1, 2, 3):
    report(f'+ overnight drift long @{n} MNQ', {'night': (night(DRIFT), n)})
report('+ London breakout of Asia range @2', {'lb': (night(LB), 2)})
report('+ drift @2 + London breakout @2', {'night': (night(DRIFT), 2), 'lb': (night(LB), 2)})
# night-only worst cases
dr = night(DRIFT); x = np.array([p for _, p, _ in dr])
print(f'\nOVERNIGHT DRIFT (18:05 -> 08:25, long, 6 ATR disaster stop): {len(x)} nights 2026, win {100*(x>0).mean():.0f}%, '
      f'avg {x.mean():+.1f} pts, worst night {x.min():+.0f} pts (= ${x.min()*2*2:+,.0f} at 2 MNQ), best {x.max():+.0f}')
# is it just the bull market? split NQ's 2026 move into overnight vs day session
raw = pd.read_csv(r'C:\Users\YOU\daytrading-automation\data\databento\mnq_2021-2026_5min.csv')
raw.index = pd.to_datetime(raw.ts_et, utc=True).dt.tz_convert('America/New_York'); r = raw[raw.index >= '2025-12-31 18:00']
mm = r.index.hour * 60 + r.index.minute
day_moves = [(g.close[(g.index.hour*60+g.index.minute) == 955].values, g.open[(g.index.hour*60+g.index.minute) == 570].values) for _, g in r.groupby(r.index.date)]
day = sum(c[0] - o[0] for c, o in day_moves if len(c) and len(o))
total = r.close.iloc[-1] - r.open.iloc[0]
print(f'NQ 2026 (Jan 1 - Aug 7): total move {total:+,.0f} pts | regular session 09:30-16:00 sum {day:+,.0f} | everything outside it {total-day:+,.0f}')
for yr in (2022, 2023, 2024, 2025):
    rr = raw[(raw.index >= f'{yr}-01-01') & (raw.index < f'{yr+1}-01-01')]
    dm = sum(g.close[(g.index.hour*60+g.index.minute) == 955].values[0] - g.open[(g.index.hour*60+g.index.minute) == 570].values[0]
             for _, g in rr.groupby(rr.index.date) if ((g.index.hour*60+g.index.minute) == 955).any() and ((g.index.hour*60+g.index.minute) == 570).any())
    tt = rr.close.iloc[-1] - rr.open.iloc[0]
    print(f'NQ {yr}: total {tt:+,.0f} | day session {dm:+,.0f} | outside day session {tt-dm:+,.0f}')
