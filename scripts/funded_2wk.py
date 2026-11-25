"""Can a MORNING multi-signal ensemble reach payout in ~2 weeks at $440 cap
WITHOUT going negative long-run? More morning signals = more green days/week =
faster, while avoiding the afternoon chop that sank the all-day versions."""

import numpy as np
import pandas as pd

import funded_lib as fl
import funded_lib2 as fl2
import funded_lib3 as fl3
import funded_lib6 as fl6

FIVE_MO = "2026-02-16"
BUFFER, TRAIL = 1100, 1000
MORN = (9.75, 11.5833)


def ema_cross(df, f, s):
    ef = df["close"].ewm(span=f, adjust=False).mean()
    es = df["close"].ewm(span=s, adjust=False).mean()
    return (ef > es) & (ef.shift(1) <= es.shift(1))


def cal(sub):
    v = sub.values; days = []; bust = att = 0
    for s in range(len(v)):
        cum = peak = 0.0; out = None
        for j in range(s, len(v)):
            cum += v[j]; peak = max(peak, cum)
            if peak - cum >= TRAIL: out = "bust"; break
            if cum >= BUFFER: out = j - s + 1; break
        if out is None: continue
        att += 1; bust += (out == "bust")
        if out != "bust": days.append(out)
    return (100*len(days)/att if att else 0, 100*bust/att if att else 0,
            int(np.median(days)) if days else -1)


def main():
    d = fl6.enrich6(fl3.enrich3(fl2.enrich2(fl.load_enriched())))
    sess = d.index.normalize().unique().sort_values()
    e = ema_cross(d, 12, 26)
    k = fl2.sig2(d, "keltner_break_long")[0]
    orb = fl.sig(d, "orb15_long")[0]
    fh = fl3.sig3(d, "first_hour_break_long")[0]
    dn = fl.sig(d, "donch20_long")[0]
    st = fl6.sig6(d, "supertrend_long")[0]

    ens = {
        "E2: EMA|Kelt": e | k,
        "E3: +ORB": e | k | orb,
        "E4: +FirstHour": e | k | orb | fh,
        "E5: +Donch": e | k | orb | fh | dn,
        "E6: +SuperT": e | k | orb | fh | dn | st,
    }
    print("=" * 104)
    print("MORNING ensembles @ $440 cap — WITH stop-when-green (safe) vs WITHOUT (fill $440/day, fast)")
    print("=" * 104)
    print(f"{'ensemble (morning)':22}{'stopGrn':>9}{'reach%':>8}{'bust%':>7}"
          f"{'cal-days':>10}{'~weeks':>8}{'net5mo':>9}{'net5yr':>9}")
    print("-" * 104)
    for name, sig in ens.items():
        for sg in (True, False):
            daily, nt, nw = fl2.replay_runner(d, sig, +1, 1.0, MORN, "gate_ema50",
                                              "eod", 440, 300, stop_green=sg)
            full = daily.reindex(sess).fillna(0.0)
            reach, bust, med = cal(full[full.index >= FIVE_MO])
            n5 = int(daily[daily.index >= FIVE_MO].sum()); ny = int(daily.sum())
            flag = "OK" if ny > 3000 else ("weak" if ny > 0 else "LOSES 5yr")
            print(f"{name:22}{('yes' if sg else 'NO'):>9}{reach:>7.0f}%{bust:>6.0f}%"
                  f"{med:>10}{med/5:>8.1f}{n5:>+9,d}{ny:>+9,d}  {flag}")
        print()


if __name__ == "__main__":
    main()
