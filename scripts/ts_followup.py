"""ts_followup.py - month-by-month + unseen-window check for the good_strategies survivors.
good_strategies.csv was picked by optimize_lab.py (~60 days of QQQ ending ~2026-07-07, i.e. ~Apr 10 - Jul 7),
so 2026-01-02..04-09 and 2026-07-08..08-07 were NEVER seen by that selection."""
src = open(r'C:\\Users\\kaide\\daytrading-automation\\ts_backtest.py').read().split("pd.set_option('display.width', 320)")[0]
exec(src)
import re
exec(open(r'C:\\Users\\kaide\\daytrading-automation\\ts_backtest.py').read().split('# good_strategies.csv configs with their own signal code')[1].split('for name in gs.name.head(12)')[0])
pd.set_option('display.width', 250)
UNSEEN = lambda x: x < pd.Timestamp('2026-04-10').date() or x > pd.Timestamp('2026-07-07').date()
for name in ['ema_pullback [1/0.5 adxgt25]', 'ema_pullback [1.25/0.5 adxgt25]', 'bb_rev-k2.0 [1.25/1 adxlt25] short',
             'keltner_rev-k1.0 [1/1.5 adxlt25] long']:
    t = gs_trades(name)
    t['month'] = [str(x)[:7] for x in t.day]; t['unseen'] = [UNSEEN(x) for x in t.day]
    print(f'\n##### {name}  (3 MNQ, net of costs)')
    mm = t.groupby('month').agg(trades=('net', 'size'), win=('net', lambda x: 100 * (x > 0).mean()), net=('net', 'sum'))
    dn = daily(t, 'net'); mm['worst_day'] = pd.Series(dn.values, index=[str(x)[:7] for x in dn.index]).groupby(level=0).min()
    print(mm.round(0).to_string())
    for lab, sub in (('UNSEEN by their selection', t[t.unseen]), ('INSIDE their selection window', t[~t.unseen])):
        gw, gl = sub.net[sub.net > 0].sum(), -sub.net[sub.net < 0].sum()
        print(f'  {lab:32s} trades={len(sub):4d} win={100*(sub.net>0).mean():5.1f}% net=${sub.net.sum():+8,.0f} PF={gw/gl if gl else np.inf:.2f}')
    dn = daily(t, 'net')
    res = eval_starts(dn)
    for lab, cond in (('eval starts in UNSEEN months', lambda x: UNSEEN(x)), ('eval starts inside window', lambda x: not UNSEEN(x))):
        sub = [r for r in res if cond(r[2])]; n = max(1, len(sub)); pas = [r for r in sub if r[0] == 'pass']
        print(f'  {lab:32s} starts={len(sub):3d} pass={100*len(pas)/n:5.1f}% bust={100*sum(r[0]=="bust" for r in sub)/n:5.1f}% '
              f'median days={np.median([r[1] for r in pas]) if pas else float("nan")}')
    for ncon in (2, 4, 5):
        tt = gs_trades(name, ncon); r_ = eval_starts(daily(tt, 'net')); n = len(r_)
        print(f'  size {ncon} MNQ: eval pass {100*sum(x[0]=="pass" for x in r_)/n:.0f}% bust {100*sum(x[0]=="bust" for x in r_)/n:.0f}% '
              f'net ${tt.net.sum():+,.0f}')
