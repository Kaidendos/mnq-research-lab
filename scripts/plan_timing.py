"""plan_timing.py - when the 3-part plan trades and how long passing takes (Feb 18 - Jul 15 2026, news-legal)."""
import numpy as np, pandas as pd
src = open(r'C:\Users\YOU\daytrading-automation\bottom_lab.py').read().split("NAMES = [")[0]
exec(src)
# entry times: re-run the EMA pullback and VWAP-3sigma logic recording entry bar hours (ET, bar close)
def entries_ema():
    lo, sh = backtest_lab.fam(d, 'ema_pullback', {}); lo, sh = lo.fillna(False).values, sh.fillna(False).values
    out, pos_until = [], -1
    tr = comp_trades('ema_pullback', {}, 'both', 1.0, 0.5, 'adx>25')
    hrs = []
    for i in range(len(d)):
        if not (W0 <= DAY[i] <= W1) or LAST[i] or not (9.6667 <= EH[i] <= 15.5) or NOENT[i] or FORCEX[i]: continue
        if ADX[i] >= 25 and (lo[i] or sh[i]): hrs.append(EH[i] + 5 / 60)
    return hrs, tr
ema_sig_hrs, ema_tr = entries_ema()
S = sigs('vwap_band_3'); vw_tr = run(*S, 'long', '2R', 'ext')
vw_hrs = [EH[i] + 5 / 60 for i in range(N) if S[0][i] and W0 <= DAY[i] <= W1 and 9.6667 <= EH[i] <= 15.5 and not NOENT[i]]
fade_hrs = [t.hour + t.minute / 60 + 5 / 60 for t in ns['EVT'] if ns['trade'](t, 5, 0, 'r1.0', 'half', 60)]
def hist(h, label):
    b = pd.cut(pd.Series(h), [8, 9.5, 10, 10.5, 11, 12, 13, 14, 15, 16], right=False,
               labels=['8:00-9:30', '9:30-10', '10-10:30', '10:30-11', '11-12', '12-1', '1-2', '2-3', '3-4']).value_counts(sort=False)
    print(f'{label:28s} ' + '  '.join(f'{k}:{100*v/max(1,len(h)):.0f}%' for k, v in b.items() if v))
print('ENTRY TIME (ET, signal-bar close) share of signals:')
hist(ema_sig_hrs, 'EMA pullback signals'); hist(fade_hrs, 'news fade trades'); hist(vw_hrs, 'VWAP 3-sigma signals')
nd = len(DAYS)
print(f'\nTRADES PER DAY: EMA {len(ema_tr)/nd:.2f} | news fade {len(NEWSFADE)/nd:.2f} | VWAP 3-sigma {len(vw_tr)/nd:.2f} | '
      f'days with zero trades: {100*np.mean([sum(1 for x in ema_tr+NEWSFADE+[(a,b,c) for a,b,c,_ in vw_tr] if x[0]==dd)==0 for dd in DAYS]):.0f}%')

# days to pass, whole window, every start day
vw3 = [(a, b, c) for a, b, c, _ in vw_tr]
comps = {'ema': perday(ema_tr, DAYS), 'fade': perday(NEWSFADE, DAYS), 'x': perday(vw3, DAYS)}
rule = lambda p, dd: {'ema': 4 if p >= 1000 else 3, 'fade': 3, 'x': 1}
res = []
for s0 in range(0, len(DAYS) - 5):
    bal, fl, mx, best, out, nd_ = 50000., 48000., 50000., 0., 'open', 0
    for k in range(s0, len(DAYS)):
        nd_ += 1; sz = rule(bal - 50000, 0)
        p = max(-1200., sum(sz[n] * comps[n][k] for n in sz)); bal += p
        if bal <= fl: out = 'bust'; break
        best = max(best, p); prof = bal - 50000
        if prof >= 3000 and best <= 0.5 * prof: out = 'pass'; break
        mx = max(mx, bal); fl = 50100. if mx >= 52100 else max(fl, mx - 2000)
    res.append((DAYS[s0], out, nd_, len(DAYS) - s0))
R = pd.DataFrame(res, columns=['start', 'out', 'days', 'runway'])
F = R[R.runway >= 60]                                    # starts with >= 60 trading days of data left
P = F[F.out == 'pass'].days
print(f'\nDAYS TO PASS (trading days, starts with >= 60 days of data after them: {len(F)} starts)')
print(f'  passed {100*(F.out=="pass").mean():.0f}% | busted {100*(F.out=="bust").mean():.0f}% | not done after 60+ days {100*(F.out=="open").mean():.0f}%')
print(f'  fastest {P.min()} | 25% passed by {P.quantile(.25):.0f} | median {P.median():.0f} | 75% by {P.quantile(.75):.0f} | slowest {P.max()}')
print('  by start month (median days, pass%):')
R['m'] = [str(x)[:7] for x in R.start]
print(R[R.runway >= 60].groupby('m').apply(lambda g: pd.Series({'starts': len(g), 'pass%': 100*(g.out=='pass').mean(),
      'median_days': g[g.out=='pass'].days.median()})).round(0).to_string())
eq = np.cumsum([sum(rule(0, 0)[n] * comps[n][k] for n in comps) for k in range(len(DAYS))])
print(f'\nAVERAGE $ PER TRADING DAY at base size: ${eq[-1]/len(DAYS):.0f}  (=> $3,000 target needs ~{3000/(eq[-1]/len(DAYS)):.0f} trading days on average)')
