"""Wave-10: calendar & time-of-day anomalies (no price indicators at all)."""

import numpy as np
import pandas as pd


def enrich9(d):
    d = d.copy()
    day = d["_day"]
    sess = pd.Series(sorted(pd.Series(day.values).unique()))
    sdf = pd.DataFrame({"date": sess})
    sdf["ym"] = sdf["date"].dt.to_period("M")
    sdf["tdom"] = sdf.groupby("ym").cumcount() + 1                 # trading day of month
    sdf["tdom_end"] = sdf.groupby("ym").cumcount(ascending=False) + 1
    sdf["dow"] = sdf["date"].dt.dayofweek
    sdf["dom"] = sdf["date"].dt.day
    third_fri = (sdf["dow"] == 4) & (sdf["dom"].between(15, 21))
    sdf["woy"] = sdf["date"].dt.isocalendar().week.values
    opex = set(zip(sdf.loc[third_fri, "ym"].astype(str), sdf.loc[third_fri, "woy"]))
    sdf["is_opex"] = [(str(ym), w) in opex for ym, w in zip(sdf["ym"], sdf["woy"])]
    m = sdf.set_index("date")
    dts = day  # tz-aware normalized per bar
    d["tdom"] = dts.map(m["tdom"])
    d["tdom_end"] = dts.map(m["tdom_end"])
    d["is_opex"] = dts.map(m["is_opex"]).astype(bool)
    # first bar of the day green? (first bar's close > its open, broadcast to the day)
    first_open = d["open"].groupby(day).transform("first")
    first_close = d["close"].groupby(day).transform("first")
    d["fbar_green"] = first_close > first_open
    return d


def sig9(df, name):
    c = df["close"]; up = c > (df["high"] + df["low"]) / 2.0
    if name == "turn_of_month_long":       # last 1 + first 3 trading days of month
        return (df["tdom_end"] == 1) | (df["tdom"] <= 3), +1
    if name == "month_end_long":
        return df["tdom_end"] <= 2, +1
    if name == "monday_long":
        return df.index.dayofweek == 0, +1
    if name == "friday_long":
        return df.index.dayofweek == 4, +1
    if name == "opex_week_long":
        return df["is_opex"], +1
    if name == "power_hour_long":          # last hour momentum (window handles time)
        return c > df["open"].groupby(df["_day"]).transform("first"), +1   # green on the day
    if name == "open_drive_long":          # first bar green -> ride the drive
        return df["fbar_green"], +1
    if name == "gap_up_follow_long":       # RTH open gaps up over prior close -> continue
        return df["day_open"] > df["pdc"] * 1.001, +1
    if name == "gap_down_fade_long":       # gap down then reclaim the open
        return (df["day_open"] < df["pdc"] * 0.999) & (c > df["day_open"]) & up, +1
    raise ValueError(name)


# (name, window)
FAMILIES9 = [
    ("turn_of_month_long", (9.75, 15.5)), ("month_end_long", (9.75, 15.5)),
    ("monday_long", (9.75, 15.5)), ("friday_long", (9.75, 15.5)),
    ("opex_week_long", (9.75, 15.5)), ("power_hour_long", (15.0, 15.75)),
    ("open_drive_long", (9.75, 11.5833)), ("gap_up_follow_long", (9.75, 15.5)),
    ("gap_down_fade_long", (9.75, 15.5)),
]
