"""srlive_2026.py - StochReclaim30 exactly as the live .cs (2026-08-08_pnl-fix), backtested on 2026 MNQ.
Entry: raw %K(14) prev <= 30 < now, signal bar closes in upper half, bar CLOSE 09:45-11:35 ET (= open 09:40-11:30),
fill at NEXT bar open (NT OnBarClose market order), bracket from the fill: SL 0.75 x ATR(14 Wilder), TP 0.5 x ATR.
Size: n = min(MaxContracts, floor((DayMaxLoss + dayPnl)/stop$), floor((DayMaxProfit - dayPnl)/tp$)); n<1 -> no trade.
Day: max 6 trades, StopWhenGreen (lock once day net > 0), news guard (calendar Feb 18 - Jul 15 only), flat at close.
Costs 1.1 pts/contract. Account: LucidDaily 50K eval, every 2026 start day. Analysis only.
"""
src = open(r'C:\Users\YOU\daytrading-automation\ts_backtest.py').read().split("pd.set_option('display.width', 320)")[0]
exec(src)

def srlive(maxloss=300, maxprof=440, maxct=10, maxtr=6, green=True, news=True):
    out, pos, cur = [], None, None
    dpnl, dtr, locked = 0.0, 0, False
    for i in range(1, len(d) - 1):
        if DAY[i] != cur: cur, dpnl, dtr, locked = DAY[i], 0.0, 0, False
        if pos and i >= pos['i0']:
            ex = None
            if O[i] <= pos['sl']: ex = O[i]
            elif L[i] <= pos['sl']: ex = pos['sl']
            elif H[i] >= pos['tp']: ex = pos['tp']
            elif LAST[i]: ex = Cc[i]
            if ex is not None:
                g = (ex - pos['e']) * 2 * pos['n']
                out.append(dict(day=cur, n=pos['n'], gross=g, net=g - COST * 2 * pos['n']))
                dpnl += g - COST * 2 * pos['n']; dtr += 1; pos = None
                if dtr >= maxtr or (green and dpnl > 0): locked = True
        if pos or locked or LAST[i] or DAY[i+1] != cur: continue
        if not (9 + 40/60 - 1e-9 <= EH[i] <= 11.5 + 1e-9): continue            # bar open 09:40-11:30
        if not (K[i-1] <= 30 < K[i]) or not UH[i] or not ATR[i] > 0: continue
        if news and CAL_START.date() <= cur <= CAL_END.date() and not NEWS[i]: continue
        stop_usd, tp_usd = ATR[i] * 0.75 * 2, ATR[i] * 0.5 * 2
        n = min(maxct, int((maxloss + dpnl) // stop_usd), int((maxprof - dpnl) // tp_usd) if maxprof else 99)
        if n < 1: continue
        e = O[i + 1]
        sl_t = max(1, round(ATR[i] * 0.75 / 0.25)) * 0.25; tp_t = max(1, round(ATR[i] * 0.5 / 0.25)) * 0.25
        pos = dict(e=e, sl=e - sl_t, tp=e + tp_t, n=n, i0=i + 1)
        if L[i+1] <= pos['sl']:                                                # fill bar hits stop (stop-first)
            g = -sl_t * 2 * n
            out.append(dict(day=cur, n=n, gross=g, net=g - COST * 2 * n)); dpnl += g - COST * 2 * n; dtr += 1; pos = None
            if dtr >= maxtr: locked = True
        elif H[i+1] >= pos['tp']:
            g = tp_t * 2 * n
            out.append(dict(day=cur, n=n, gross=g, net=g - COST * 2 * n)); dpnl += g - COST * 2 * n; dtr += 1; pos = None
            if dtr >= maxtr or (green and dpnl > 0): locked = True
        else: pos['i0'] = i + 2
    return pd.DataFrame(out)

pd.set_option('display.width', 300); pd.set_option('display.max_columns', 30)
VARIANTS = [('LIVE .cs settings: -$300/+$440, 10ct, stop-green', dict()),
            ('live, no news guard', dict(news=False)),
            ('live, stop-green OFF', dict(green=False)),
            ('50K-sized: -$500/+$1,500, stop-green OFF (Claude 2 eval mode)', dict(maxloss=500, maxprof=1500, green=False)),
            ('bigger: -$600/+$900, 20ct, stop-green', dict(maxloss=600, maxprof=900, maxct=20)),
            ('max: -$1,000/+$1,500, 20ct, stop-green OFF', dict(maxloss=1000, maxprof=1500, maxct=20, green=False))]
rows, TRS = [], {}
for lab, kw in VARIANTS:
    t = srlive(**kw); TRS[lab] = t; rows.append(summarize(t, lab))
R = pd.DataFrame(rows); R.to_csv(r'C:\Users\YOU\daytrading-automation\srlive_2026.csv', index=False)
cols = ['strategy', 'trades', 'win%', 'gross_usd', 'net_usd', 'net_pf', 'worst_day', 'best_day', 'maxDD',
        'eval_pass%', 'eval_bust%', 'eval_open%', 'median_days_to_pass', 'JanApr_pass%', 'JanApr_bust%', 'MayAug_pass%', 'MayAug_bust%']
print(R[cols].round(1).to_string(index=False))
t = TRS[VARIANTS[0][0]].copy(); t['month'] = [str(x)[:7] for x in t.day]
print('\nLIVE settings by month (net):')
print(t.groupby('month').agg(trades=('net', 'size'), win_pct=('net', lambda x: 100 * (x > 0).mean()),
                             avg_size=('n', 'mean'), net=('net', 'sum')).round(1).to_string())
w = t[t.net > 0].net; l = t[t.net <= 0].net
print(f'\navg win ${w.mean():.0f} | avg loss ${l.mean():.0f} | breakeven win rate needed {100*abs(l.mean())/(w.mean()+abs(l.mean())):.1f}% '
      f'| actual {100*len(w)/len(t):.1f}%')
