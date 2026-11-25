src = open(r'C:\Users\YOU\daytrading-automation\ts_followup.py').read().split("pd.set_option('display.width', 250)")[0]
exec(src)
UNSEEN = lambda x: x < pd.Timestamp('2026-04-10').date() or x > pd.Timestamp('2026-07-07').date()
for cost in (1.1, 1.6, 2.2):
    for ncon in (3, 4):
        t = gs_trades('ema_pullback [1/0.5 adxgt25]', ncon); t['net'] = t.gross - cost * 2 * ncon
        r_ = eval_starts(daily(t, 'net')); n = len(r_); u = t[[UNSEEN(x) for x in t.day]]
        print(f"cost {cost} pts/contract, {ncon} MNQ: 2026 net ${t.net.sum():+,.0f} | unseen months ${u.net.sum():+,.0f} | "
              f"eval pass {100*sum(x[0]=='pass' for x in r_)/n:.0f}% bust {100*sum(x[0]=='bust' for x in r_)/n:.0f}%")
