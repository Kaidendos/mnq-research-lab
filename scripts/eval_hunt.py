"""Eval-shape hunt: books built like the LIVE config (tight brackets, exact
live cap-fitted sizing incl. profit-room fit, high day-win-rate) but with a
regime-matched short sleeve so gate-OFF periods stop bleeding.

Sleeves (all tight-bracket, entries at close, SL-first, fees $1.22):
  Lstoch : live exact — %K14 reclaim 30, svol>0, 9:40-11:30, SL .75A TP .5A
  Lvwap  : VWAP bounce — low tags VWAP, closes above, svol>0, 9:40-13:00,
           SL .75A TP .5A
  Sbd    : 20-bar-low break short, SL 1.5A TP 1.0A (Sbd- = SL 1.25 TP .75)
  S70    : %K14 drop through 70, svol<0, 9:40-14:00, SL .75A TP .5A
Config axes: gate routing, stop-after-first-win, day profit cap.
Benchmarks to beat: live 5-mo realistic sim 52% pass; B3 book 42%.
"""

import numpy as np
import pandas as pd

from strat_search_5y import load, day_ctx, FEE, PT
from eval_1yr import attempt_spans

MAX_LOTS = 10
BUDGET = 500.0
MAXPD = 6
YEAR = "2025-07-17"


def sleeves(x, i, cfg):
    gate = x["gate"][i]
    if gate:
        if ("Lstoch" in cfg and 9.6667 <= x["eth"][i] <= 11.5
                and x["K"][i-1] <= 30 and x["K"][i] > 30 and x["sv"][i] > 0):
            return dict(dir=1, slm=0.75, tpm=0.5)
        if ("Lvwap" in cfg and 9.6667 <= x["eth"][i] <= 13.0
                and x["l"][i] <= x["vwap"][i] and x["c"][i] > x["vwap"][i]
                and x["sv"][i] > 0):
            return dict(dir=1, slm=0.75, tpm=0.5)
    else:
        if ("Sbd" in cfg and 9.5833 <= x["eth"][i] <= 15.0
                and not np.isnan(x["ll20"][i]) and x["c"][i] < x["ll20"][i]):
            m = cfg["Sbd"]
            return dict(dir=-1, slm=m[0], tpm=m[1])
        if ("S70" in cfg and 9.6667 <= x["eth"][i] <= 14.0
                and x["K"][i-1] >= 70 and x["K"][i] < 70 and x["sv"][i] < 0):
            return dict(dir=-1, slm=0.75, tpm=0.5)
    if not gate and "LstochAll" in cfg:      # live-as-is: longs even gate OFF
        if (9.6667 <= x["eth"][i] <= 11.5 and x["K"][i-1] <= 30
                and x["K"][i] > 30 and x["sv"][i] > 0):
            return dict(dir=1, slm=0.75, tpm=0.5)
    return None


def size_for(atr_val, day_pnl, slm, tpm, cap):
    stop_usd = atr_val * slm * PT
    tp_usd = atr_val * tpm * PT
    n = min(MAX_LOTS, int((BUDGET + day_pnl) / stop_usd))
    if cap is not None:
        n = min(n, int((cap - day_pnl) / tp_usd))
    return max(n, 0)


def run(d, cfg, cap=1500.0, saw=False):
    rows = []
    for dnorm, day in d.groupby(d.index.normalize(), sort=True):
        if len(day) < 25:
            continue
        x = day_ctx(day)
        n = len(day)
        pos = None
        net = 0.0
        taken = 0
        day_won = False
        for i in range(1, n):
            last = i == n - 1
            if pos is not None:
                ex = None
                if pos["dir"] > 0:
                    if x["l"][i] <= pos["sl"]: ex = pos["sl"]
                    elif x["h"][i] >= pos["tp"]: ex = pos["tp"]
                else:
                    if x["h"][i] >= pos["sl"]: ex = pos["sl"]
                    elif x["l"][i] <= pos["tp"]: ex = pos["tp"]
                if ex is None and last:
                    ex = x["c"][i]
                if ex is not None:
                    pts = (ex - pos["entry"]) * pos["dir"]
                    pnl = pts * PT * pos["n"] - FEE * pos["n"]
                    net += pnl
                    if pnl > 0:
                        day_won = True
                    rows.append({"date": dnorm, "pnl": pnl, "win": pnl > 0,
                                 "n": pos["n"]})
                    pos = None
            if (pos is None and not last and taken < MAXPD
                    and not (saw and day_won)
                    and x["atr"][i] > 0 and not np.isnan(x["atr"][i])):
                sig = sleeves(x, i, cfg)
                if sig is None:
                    continue
                lots = size_for(x["atr"][i], net, sig["slm"], sig["tpm"], cap)
                if lots < 1:
                    continue
                a = x["atr"][i]; c = x["c"][i]; dr = sig["dir"]
                pos = dict(dir=dr, entry=c, n=lots,
                           sl=c - dr * sig["slm"] * a, tp=c + dr * sig["tpm"] * a)
                taken += 1
    return pd.DataFrame(rows)


def report(tag, t):
    if t.empty:
        print(f"{tag}: no trades")
        return
    daily = t.groupby("date")["pnl"].sum()
    y = t[t["date"] >= YEAR]
    dy = y.groupby("date")["pnl"].sum()
    yr = daily.groupby(daily.index.year).sum()
    posyrs = int((yr > 0).sum())
    gw = dy[dy > 0].sum(); gl = -dy[dy <= 0].sum()
    pfd = gw / gl if gl else float("inf")
    green = 100 * (dy > 0).mean() if len(dy) else 0
    p2, b2, _ = attempt_spans(dy, mll=2000.0)
    r2 = 100 * len(p2) / (len(p2) + len(b2)) if (p2 or b2) else float("nan")
    m2 = int(np.median([p[0] for p in p2])) if p2 else -1
    p5, b5, _ = attempt_spans(daily, mll=2000.0)
    r5 = 100 * len(p5) / (len(p5) + len(b5)) if (p5 or b5) else float("nan")
    print(f"{tag:30s} 1y ${dy.sum():+8,.0f} dayPF {pfd:4.2f} grn {green:3.0f}% "
          f"wd ${dy.min():+6,.0f} | pass1y {r2:3.0f}%/m{m2:<3d} pass5y {r5:3.0f}% "
          f"| 5y ${daily.sum():+9,.0f} +yr{posyrs}")


def main():
    d = load()
    configs = [
        ("H1 live gateON only", dict(Lstoch=1), 1500, False),
        ("H2 live/Sbd 1.5-1.0", dict(Lstoch=1, Sbd=(1.5, 1.0)), 1500, False),
        ("H3 H2 + stop-after-win", dict(Lstoch=1, Sbd=(1.5, 1.0)), 1500, True),
        ("H4 H2 cap750", dict(Lstoch=1, Sbd=(1.5, 1.0)), 750, False),
        ("H5 liveALL + Sbd", dict(Lstoch=1, LstochAll=1, Sbd=(1.5, 1.0)), 1500, False),
        ("H6 live/Sbd 1.25-0.75", dict(Lstoch=1, Sbd=(1.25, 0.75)), 1500, False),
        ("H7 live/S70", dict(Lstoch=1, S70=1), 1500, False),
        ("H8 live+Lvwap/Sbd", dict(Lstoch=1, Lvwap=1, Sbd=(1.5, 1.0)), 1500, False),
        ("H9 H8 + stop-after-win", dict(Lstoch=1, Lvwap=1, Sbd=(1.5, 1.0)), 1500, True),
        ("H10 Lvwap only gateON", dict(Lvwap=1), 1500, False),
    ]
    for tag, cfg, cap, saw in configs:
        report(tag, run(d, cfg, cap, saw))


if __name__ == "__main__":
    main()
