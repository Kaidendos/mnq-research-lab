"""Hunt for the FASTEST payout: maximize frequency (ensembles + all-day) and
green-day size (higher caps) to minimize CALENDAR days to $1,100. Past 5 months.
Reports the speed/reliability tradeoff — weekly payout needs BOTH."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib6 as fl6

FIVE_MO = "2026-02-16"
BUFFER, TRAIL = 1100, 1000
MORNING = (9.75, 11.5833)
ALLDAY = (9.75, 15.5)


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def calendar_sim(sub):
    v = sub.values
    days = []; bust = 0; att = 0
    for s in range(len(v)):
        cum = peak = 0.0; out = None
        for j in range(s, len(v)):
            cum += v[j]; peak = max(peak, cum)
            if peak - cum >= TRAIL:
                out = "bust"; break
            if cum >= BUFFER:
                out = j - s + 1; break
        if out is None:
            continue
        att += 1
        bust += (out == "bust")
        if out != "bust":
            days.append(out)
    return att, days, bust


def main():
    d = fl6.enrich6(fl3.enrich3(fl2.enrich2(fl.load_enriched())))
    sessions = d.index.normalize().unique().sort_values()
    kelt = fl2.sig2(d, "keltner_break_long")[0]
    e1226 = ema_cross(d, 12, 26)
    orb = fl.sig(d, "orb15_long")[0]
    donch = fl.sig(d, "donch20_long")[0]
    st = fl6.sig6(d, "supertrend_long")[0]

    ens2 = e1226 | kelt
    ens3 = e1226 | kelt | orb
    ens4 = e1226 | kelt | orb | donch
    ens5 = e1226 | kelt | orb | donch | st

    cands = []
    for nm, sig in [("Ens2 EMA|Kelt", ens2), ("Ens3 +ORB", ens3),
                    ("Ens4 +Donch", ens4), ("Ens5 +SuperT", ens5),
                    ("Keltner", kelt)]:
        for win, wl in ((MORNING, "morn"), (ALLDAY, "all")):
            for cap, bud in ((440, 300), (660, 450), (880, 600), (1100, 750)):
                cands.append((f"{nm} {wl} cap{cap}", sig, win, cap, bud))

    rows = []
    for name, sig, win, cap, bud in cands:
        daily = fl2.replay_runner(d, sig, +1, 1.0, win, "gate_ema50", "eod", cap, bud)[0]
        if len(daily) < 20:
            continue
        full = daily.reindex(sessions).fillna(0.0)
        sub = full[full.index >= FIVE_MO]
        att, days, bust = calendar_sim(sub)
        if att == 0 or not days:
            continue
        rows.append(dict(config=name, reach=round(100*len(days)/att),
                         bust=round(100*bust/att), med_days=int(np.median(days)),
                         weeks=round(np.median(days)/5, 1),
                         net5mo=int(sub[sub != 0].sum())))

    res = pd.DataFrame(rows).sort_values("med_days")
    pd.set_option("display.width", 200)
    print("=" * 92)
    print("FASTEST PAYOUT SEARCH — past 5 months, ranked by calendar days to $1,100")
    print("(cap>440 raises green-day size for speed but also red-day size -> more bust)")
    print("=" * 92)
    print(res.to_string(index=False))
    wk = res[(res["weeks"] <= 1.4) & (res["reach"] >= 55)]
    print("\n" + "=" * 92)
    print("WEEKLY (<= ~1.4 weeks to payout AND >= 55% reach it):")
    print("=" * 92)
    print(wk.to_string(index=False) if len(wk) else "(none reach payout weekly at >=55% reliability)")


if __name__ == "__main__":
    main()
