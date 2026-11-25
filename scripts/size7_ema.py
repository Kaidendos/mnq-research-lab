"""size7_ema.py - EMA pullback [1/0.5 adxgt25] at 3..7 MNQ, all of 2026 (Jan 2 - Aug 7)."""
src = open(r'C:\Users\YOU\daytrading-automation\ts_followup.py').read().split("pd.set_option('display.width', 250)")[0]
exec(src)
print('=== EMA PULLBACK [1/0.5 adxgt25], all 2026, cost 1.1 pts/contract ===')
for ncon in (3, 4, 5, 6, 7):
    for cost in (1.1, 2.2):
        t = gs_trades('ema_pullback [1/0.5 adxgt25]', ncon); t['net'] = t.gross - cost * 2 * ncon
        dn = daily(t, 'net'); eq = dn.cumsum(); r_ = eval_starts(dn); n = len(r_)
        print(f'{ncon} MNQ (cost {cost}): net ${t.net.sum():+,.0f} | worst day ${dn.min():+,.0f} | maxDD ${(eq-eq.cummax()).min():,.0f} | '
              f'eval pass {100*sum(x[0]=="pass" for x in r_)/n:.0f}% bust {100*sum(x[0]=="bust" for x in r_)/n:.0f}%')
