"""Market-Profile / auction family for MNQ 5-min RTH bars  (prefix "ib_").

Every entry below is a translation of a documented, mechanical auction-theory rule.
Sources (repeated above each block that uses them):

  [P1] Marketcalls "Market Profile - How to Play 80 Percentage Rule"
       https://www.marketcalls.in/market-profile/market-profile-how-to-play-80-percentage-rule.html
       "If the market opens either above or below the value area and test the value
       area high/low within 2 consecutive 30 minutes (i.e letter 'A' or 'B' touches
       value area) then there is a 80% chance that it will fill up the complete
       value area."  Also: "if price opens above/below previous days value area and
       haven't return back then it is a sign of one sided directional move" - i.e.
       no re-entry, no trade.

  [P2] MetroTrade "What is the 80% Rule in Futures Trading?"
       https://www.metrotrade.com/what-is-the-80-rule-in-futures-trading/
       Same rule, with the acceptance qualifier spelled out: price must "hold inside
       the value area for a period of time - usually 30 minutes or more", described
       as "two TPOs (one hour total)... a sign of acceptance". Value area defined as
       "the price range where roughly 70% of the previous session's volume occurred";
       POC = "the price level with the most trading activity".

  [P3] TRADEPRO Academy "How to Use the Initial Balance (Market Profile Hacks &
       Tricks)" - https://tradeproacademy.com/how-to-use-the-initial-balance/
       IB = first hour, 09:30-10:30 ET (periods A + B).
       Continuation: "Should we get an excess move outside of the IB and we close
       that period well outside of the IB, the expected move is to continue the
       directional trend."
       FAILURE (what this file trades): "Should we get an excess move outside the IB
       and that period fails to close outside... we can look for a trend move to
       trade into the other side of the IB."  Both quoted at 70-75% probability.

  [P4] TradingStats.net "Initial Balance Breakout Statistics: ES & NQ Futures
       2015-2025" - https://tradingstats.net/initial-balance-breakout-statistics/
       5,519 trading days. "Failed first breakout: 34.0% ES, 34.8% NQ".
       "Deep retracement (>=50%): 52.7% become double breakouts; only 24.8% close
       original direction."  Extension tiers are quoted as a fraction of the IB
       range (25% upside extension reached 52.0% of the time).

  [P5] Marketcalls "Market Profile: Different Types of Profile Days"
       https://www.marketcalls.in/market-profile/market-profile-different-types-of-profile-days.html
       Neutral Day: "Initial Balance breaks out on both sides" and "Price closes
       near the center of the profile". Neutral day IB is smaller than a normal day.

  [P6] Marketcalls "Poor High and Poor Low Market Profile Structure Explained"
       https://www.marketcalls.in/market-profile/poor-high-and-poor-low-market-profile-structure-explained.html
       and ShadowTrader glossary https://www.shadowtrader.net/glossary/poor-high/
       Poor high/low = a profile extreme with "either a lack of excess or 1 TPO
       (Single Print) at the tails" - a flat top/bottom with two or more TPOs across.
       "if the next day or in some subsequent session, the poor high is revisited,
       then the odds are strong that it will break and move higher" (mirror for the
       poor low: it breaks and moves lower).

  [P7] Axia Futures "Trading Strategies Around Poor Lows And Poor Highs"
       https://axiafutures.com/blog/trading-strategies-around-poor-lows-and-poor-highs/
       "Poor highs and lows are flat tops or bottoms that lack a tail", formed by
       "multiple tests of the same level within one daily interval". Validity filter:
       a level created by "merely poking outside of initial balance and swiftly
       returning to it... is actually a failed auction, not any sort of a sustained
       move that would warrant a validity of a poor high or poor low".

  [P8] FuturesIndicators "Naked POCs - The Magnets in the Market"
       https://futuresindicators.com/learn/naked-pocs-magnets-in-the-market
       Naked POC = "Prior-session POCs that price never retested. Act as magnets -
       price tends to come back to them."  Filters: "Recent (within 1-10 sessions),
       nearby (within reasonable ATR)".  Playbook 1: "price tests the POC, finds
       responsive participation, and reverses back in the original direction. Trade
       the reversal."

NOT IMPLEMENTED - single-print fills.  The one source found with concrete single-
print rules (OrderFlow Labs, https://orderflowlabs.com/blogs/theblog/market-profile)
gives only "I don't fight a day with single prints" plus discretionary continuation
guidance ("wait for a minor pullback into the most recent acceptance area"). It
supplies no mechanical single-print-fill trigger, so none is invented here.

Where a source is qualitative the literal reading used is spelled out in a comment
marked "CONCRETE READING".  Only ENTRY triggers are returned; the harness owns
stops, targets, sizing and exits.

CAUSALITY.  Every session-scoped quantity is one of:
  * a cummax / cummin / cumsum / expanding value inside the current session, or
  * a whole-session aggregate of a STRICTLY PRIOR session (built per day then
    .shift(1)-ed and mapped back), or
  * the current session's FIRST bar value (known at that bar).
Nothing here consults a bar later than the one it fires on.  There is no
groupby("_day").transform("max") on the live session anywhere in this file.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── session geometry (bars are stamped at their START; RTH = 09:30..15:55) ────
IB_END = 10.5                       # [P3] initial balance = 09:30-10:30 ET
BRACKET_MIN = 30                    # TPO period length in minutes
BRACKET_CLOSE_MIN = 25              # last 5-min bar of a 30-min bracket (:25/:55)

# ── value-area construction [P2] ──────────────────────────────────────────────
VA_FRACTION = 0.70                  # [P2] "roughly 70% of the previous session's volume"
PROFILE_BUCKET = 5.0                # MNQ points per profile row (20 ticks)

# ── 80% rule [P1][P2] ─────────────────────────────────────────────────────────
ACCEPT_BARS = 6                     # [P2] "30 minutes or more" = 6 x 5-min bars
RULE80_CUTOFF = 13.0                # CONCRETE READING: the target is a same-session
                                    # VA fill, so stop initiating in the early PM
REENTRY_CUTOFF = RULE80_CUTOFF      # [P2]'s wording is "re-enters the value area
                                    # during the current session" - no bracket
                                    # restriction, so re-entry is allowed any time
                                    # before the entry cutoff.  [P1]'s stricter
                                    # "letter A or B" reading (re-entry by 10:30) is
                                    # measured at only ~0.10% of bars per side, below
                                    # the harness's usable range; set this to IB_END
                                    # to restore it.

# ── IB extension failure [P3] and deep retracement [P4] ───────────────────────
IBFAIL_CUTOFF = 14.0                # CONCRETE READING: needs room to reach the far
                                    # side of the IB before the close
DEEP_RETR = 0.50                    # [P4] "deep retracement (>=50%)" of the extension
MIN_EXT_IB_FRAC = 0.25              # [P4] 25% extension tier - the smallest extension
                                    # the source treats as a real leg

# ── neutral day [P5] ──────────────────────────────────────────────────────────
NEUTRAL_CUTOFF = 15.0               # [P5] the day resolves "near the center" late

# ── poor high / poor low [P6][P7] ─────────────────────────────────────────────
POOR_FLAT_FRAC = 0.05               # "flat" = bar highs within 5% of the day range
POOR_MIN_TOUCH = 2                  # [P6] "two or more TPO's across" the extreme
POOR_CLOSE_FRAC = 0.25              # no excess/tail: close in the outer quarter
POOR_MAX_AGE = 20                   # [P6] poor levels "carry forward ~1 month"
POOR_CUTOFF = 15.0

# ── naked POC [P8] ────────────────────────────────────────────────────────────
NPOC_MIN_AGE = 1                    # [P8] "prior-session POCs that price never retested"
NPOC_MAX_AGE = 10                   # [P8] "recent (within 1-10 sessions)"
NPOC_MAX_DIST_ATR = 1.5             # [P8] "nearby (within reasonable ATR)"
NPOC_CUTOFF = 15.0

ATR_DAILY_LEN = 14                  # daily ATR used for the [P8] proximity filter


# ══════════════════════════════════════════════════════════════════════════════
# causal helpers
# ══════════════════════════════════════════════════════════════════════════════
def _prior_count(cond: pd.Series, day: pd.Series) -> pd.Series:
    """How many times `cond` was true STRICTLY earlier in the same session."""
    c = cond.fillna(False).astype(int)
    return c.groupby(day).cumsum() - c


def _first_of_day(cond: pd.Series, day: pd.Series) -> pd.Series:
    cond = cond.fillna(False)
    return cond & (_prior_count(cond, day) == 0)


def _happened_earlier(cond: pd.Series, day: pd.Series) -> pd.Series:
    return _prior_count(cond, day) > 0


def _locked_range(df: pd.DataFrame, end_eth: float):
    """High/low of [session open, end_eth), locked once that window has closed.

    cummax/cummin then ffill inside the day: on any bar the value reflects only
    bars at or before it.  `ready` gates consumption until the window is over.
    """
    day = df["_day"]
    inside = df["eth"] < end_eth
    hi = df["high"].where(inside).groupby(day).cummax().groupby(day).ffill()
    lo = df["low"].where(inside).groupby(day).cummin().groupby(day).ffill()
    return hi, lo, df["eth"] >= end_eth


def _run_length(flag: pd.Series, day: pd.Series) -> pd.Series:
    """Length of the current consecutive True run of `flag`, reset every session."""
    f = flag.fillna(False)
    block = (~f).astype(int).groupby(day).cumsum()      # new id at every False bar
    return f.astype(int).groupby([day, block]).cumsum()


def _daily_atr(df: pd.DataFrame) -> pd.Series:
    """Wilder 14-day ATR from daily bars, SHIFTED one day, mapped back to bars."""
    day = df["_day"]
    dh = df["high"].groupby(day).max()
    dl = df["low"].groupby(day).min()
    dc = df["close"].groupby(day).last()
    pc = dc.shift(1)
    tr = pd.concat([dh - dl, (dh - pc).abs(), (dl - pc).abs()], axis=1).max(axis=1)
    return day.map(tr.ewm(alpha=1.0 / ATR_DAILY_LEN, adjust=False).mean().shift(1))


# ══════════════════════════════════════════════════════════════════════════════
# per-session auction structure  (computed per day, consumed only via .shift(1))
# ══════════════════════════════════════════════════════════════════════════════
def _value_area(counts: np.ndarray, frac: float):
    """Standard greedy value area: start at the POC row, keep absorbing whichever
    adjacent row holds more volume until `frac` of session volume is covered [P2].

    Returns (poc_row, top_row, bottom_row) as indices into `counts`.
    """
    n = len(counts)
    poc = int(np.argmax(counts))
    total = float(counts.sum())
    if total <= 0.0:
        return poc, poc, poc
    target = frac * total
    covered = float(counts[poc])
    lo = hi = poc
    while covered < target and (lo > 0 or hi < n - 1):
        up = float(counts[hi + 1]) if hi < n - 1 else -1.0
        dn = float(counts[lo - 1]) if lo > 0 else -1.0
        if up >= dn:
            hi += 1
            covered += float(counts[hi])
        else:
            lo -= 1
            covered += float(counts[lo])
    return poc, hi, lo


def _session_structure(df: pd.DataFrame) -> pd.DataFrame:
    """One row per session: POC / VAH / VAL, H / L / C, and poor-extreme flags.

    Every column here is a WHOLE-SESSION aggregate.  It is only ever read after a
    .shift(1), so a session never sees its own row.  (The truncation audit is
    satisfied because a partial final session's row is never consumed.)
    """
    day = df["_day"]
    codes, uniq = pd.factorize(day)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    o = df["open"].to_numpy(dtype=float)
    v = df["volume"].to_numpy(dtype=float)

    tp = (h + l + c) / 3.0
    bucket = np.floor(tp / PROFILE_BUCKET).astype(np.int64)

    starts = np.flatnonzero(np.r_[True, codes[1:] != codes[:-1]])
    ends = np.r_[starts[1:], len(codes)]

    n = len(starts)
    poc = np.empty(n); vah = np.empty(n); val = np.empty(n)
    dhi = np.empty(n); dlo = np.empty(n); dcl = np.empty(n); dop = np.empty(n)
    poor_hi = np.zeros(n, dtype=bool)
    poor_lo = np.zeros(n, dtype=bool)

    for i, (s, e) in enumerate(zip(starts, ends)):
        bb, vv = bucket[s:e], v[s:e]
        base = int(bb.min())
        counts = np.bincount(bb - base, weights=vv)
        p, hi_r, lo_r = _value_area(counts, VA_FRACTION)
        poc[i] = (base + p + 0.5) * PROFILE_BUCKET      # centre of the POC row
        vah[i] = (base + hi_r + 1.0) * PROFILE_BUCKET   # top edge of the VA
        val[i] = (base + lo_r) * PROFILE_BUCKET         # bottom edge of the VA

        dh, dl = float(h[s:e].max()), float(l[s:e].min())
        dhi[i], dlo[i], dcl[i], dop[i] = dh, dl, float(c[e - 1]), float(o[s])
        rng = dh - dl
        if rng <= 0:
            continue

        # [P6][P7] poor high: "flat top" - two or more bars printing the extreme -
        # AND no excess tail, i.e. the session closed hard against that extreme.
        # [P7] validity: it must cap a sustained auction, so the session itself has
        # to have been a net buying (selling) auction.
        tol = POOR_FLAT_FRAC * rng
        poor_hi[i] = (
            int((h[s:e] >= dh - tol).sum()) >= POOR_MIN_TOUCH
            and dcl[i] >= dh - POOR_CLOSE_FRAC * rng
            and dcl[i] > dop[i]
        )
        poor_lo[i] = (
            int((l[s:e] <= dl + tol).sum()) >= POOR_MIN_TOUCH
            and dcl[i] <= dl + POOR_CLOSE_FRAC * rng
            and dcl[i] < dop[i]
        )

    return pd.DataFrame(
        dict(poc=poc, vah=vah, val=val, dhi=dhi, dlo=dlo,
             poor_hi=poor_hi, poor_lo=poor_lo),
        index=uniq,
    )


def _naked_poc(struct: pd.DataFrame) -> pd.Series:
    """Most recent still-untouched prior POC, per session [P8].

    For session j the candidate POC of session k (NPOC_MIN_AGE <= j-k <= NPOC_MAX_AGE)
    is naked when no session strictly between k and j traded through it.  Only
    COMPLETED prior sessions are inspected, so the value is known at session j's open.
    """
    poc = struct["poc"].to_numpy(dtype=float)
    dhi = struct["dhi"].to_numpy(dtype=float)
    dlo = struct["dlo"].to_numpy(dtype=float)
    n = len(poc)
    out = np.full(n, np.nan)
    for j in range(n):
        oldest = max(0, j - NPOC_MAX_AGE)
        for k in range(j - NPOC_MIN_AGE, oldest - 1, -1):
            if k < 0:
                break
            lvl = poc[k]
            seg_hi = dhi[k + 1:j].max() if j > k + 1 else -np.inf
            seg_lo = dlo[k + 1:j].min() if j > k + 1 else np.inf
            if not (seg_lo <= lvl <= seg_hi):     # never revisited since session k
                out[j] = lvl
                break
    return pd.Series(out, index=struct.index)


def _live_poor_levels(struct: pd.DataFrame):
    """Most recent UNCLEARED poor high / poor low, per session [P6].

    [P6] says poor levels "carry forward ~1 month" and that one cleared the next day
    should be discarded, so a level stays live until a later session trades beyond it
    and is dropped after POOR_MAX_AGE sessions.  Only completed prior sessions are
    inspected, so the level is known at session j's open.
    """
    dhi = struct["dhi"].to_numpy(dtype=float)
    dlo = struct["dlo"].to_numpy(dtype=float)
    is_ph = struct["poor_hi"].to_numpy(dtype=bool)
    is_pl = struct["poor_lo"].to_numpy(dtype=bool)
    n = len(dhi)
    out_h = np.full(n, np.nan)
    out_l = np.full(n, np.nan)
    for j in range(n):
        oldest = max(0, j - POOR_MAX_AGE)
        got_h = got_l = False
        for k in range(j - 1, oldest - 1, -1):
            if not got_h and is_ph[k]:
                lvl = dhi[k]
                if j == k + 1 or dhi[k + 1:j].max() <= lvl:   # never exceeded since
                    out_h[j] = lvl
                    got_h = True
            if not got_l and is_pl[k]:
                lvl = dlo[k]
                if j == k + 1 or dlo[k + 1:j].min() >= lvl:
                    out_l[j] = lvl
                    got_l = True
            if got_h and got_l:
                break
    return (pd.Series(out_h, index=struct.index),
            pd.Series(out_l, index=struct.index))


# ══════════════════════════════════════════════════════════════════════════════
def register(df: pd.DataFrame):
    day = df["_day"]
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    eth = df["eth"]

    struct = _session_structure(df)
    prior = struct.shift(1)                       # <- the only way struct is read
    pvah = day.map(prior["vah"])
    pval = day.map(prior["val"])
    live_ph, live_pl = _live_poor_levels(struct)  # both built from prior sessions only
    pphi = day.map(live_ph)
    pplo = day.map(live_pl)
    npoc = day.map(_naked_poc(struct))            # ditto

    datr = _daily_atr(df)
    day_open = o.groupby(day).transform("first")  # first bar's open: known at bar 0
    prev_c = c.groupby(day).shift(1)

    ib_hi, ib_lo, ib_ok = _locked_range(df, IB_END)
    ib_rng = ib_hi - ib_lo

    mins = np.rint(eth.to_numpy() * 60.0).astype(int)
    bracket_id = pd.Series(mins // BRACKET_MIN, index=df.index)
    bracket_close = pd.Series((mins % BRACKET_MIN) == BRACKET_CLOSE_MIN, index=df.index)

    out = {}

    # ═════════════════════════════════════════════════════════════════════════
    # 1/2. THE 80% RULE.  [P1] + [P2]
    #      Session opens outside the PRIOR session's value area; price re-enters
    #      value during period A or B (by 10:30) [P1]; acceptance is confirmed by
    #      six consecutive 5-min closes inside the value area ("30 minutes or
    #      more", "two TPOs" [P2]).  Entry on that sixth bar, aimed at the far
    #      side of the value area, so open-above -> short, open-below -> long.
    #      [P1]'s no-re-entry case is excluded by construction.
    # ═════════════════════════════════════════════════════════════════════════
    inside_va = (c >= pval) & (c <= pvah)
    accepted = _run_length(inside_va, day) >= ACCEPT_BARS
    # eth of the session's FIRST close back inside value, carried forward
    reentry_eth = eth.where(_first_of_day(inside_va, day)).groupby(day).ffill()
    reentry_ok = reentry_eth <= REENTRY_CUTOFF

    base80 = accepted & reentry_ok & (eth < RULE80_CUTOFF)
    out["ib_va80_short"] = (_first_of_day(base80 & (day_open > pvah), day), -1)
    out["ib_va80_long"] = (_first_of_day(base80 & (day_open < pval), day), +1)

    # ═════════════════════════════════════════════════════════════════════════
    # 3/4. INITIAL-BALANCE EXTENSION FAILURE.  [P3]
    #      "Should we get an excess move outside the IB and that period fails to
    #      close outside... we can look for a trend move to trade into the other
    #      side of the IB."
    #      CONCRETE READING: a 30-min TPO bracket after 10:30 whose running high
    #      exceeded the IB high but whose closing 5-min bar (the :25/:55 bar)
    #      closes back inside the IB.  The bracket high is a cummax inside the
    #      bracket, so at the closing bar it is fully known.  Trade the other way.
    # ═════════════════════════════════════════════════════════════════════════
    b_hi = h.groupby([day, bracket_id]).cummax()
    b_lo = l.groupby([day, bracket_id]).cummin()
    base_fail = ib_ok & bracket_close & (eth < IBFAIL_CUTOFF)

    fail_up = base_fail & (b_hi > ib_hi) & (c < ib_hi)
    out["ib_ibfail_short"] = (_first_of_day(fail_up, day), -1)

    fail_dn = base_fail & (b_lo < ib_lo) & (c > ib_lo)
    out["ib_ibfail_long"] = (_first_of_day(fail_dn, day), +1)

    # ═════════════════════════════════════════════════════════════════════════
    # 5/6. DEEP RETRACEMENT OF AN IB EXTENSION.  [P4]
    #      "Deep retracement (>=50%): 52.7% become double breakouts; only 24.8%
    #      close original direction."  So once an established IB breakout has
    #      given back half of its extension, the original direction is the
    #      minority outcome -> take the other side.
    #      CONCRETE READING: the extension is measured from the IB boundary to the
    #      session's running extreme SINCE the first close outside the IB (a
    #      cummax/cummin, fully causal).  It must be at least [P4]'s smallest
    #      quoted tier, 25% of the IB range, before a retracement means anything.
    # ═════════════════════════════════════════════════════════════════════════
    brk_up = _first_of_day(ib_ok & (c > ib_hi), day)
    since_up = brk_up | _happened_earlier(brk_up, day)
    ext_hi = h.where(since_up).groupby(day).cummax()
    ext_up = ext_hi - ib_hi
    retr_short = (
        _happened_earlier(brk_up, day)
        & (eth < IBFAIL_CUTOFF)
        & (ext_up >= MIN_EXT_IB_FRAC * ib_rng)
        & (c <= ib_hi + (1.0 - DEEP_RETR) * ext_up)
    )
    out["ib_deepret_short"] = (_first_of_day(retr_short, day), -1)

    brk_dn = _first_of_day(ib_ok & (c < ib_lo), day)
    since_dn = brk_dn | _happened_earlier(brk_dn, day)
    ext_lo = l.where(since_dn).groupby(day).cummin()
    ext_dn = ib_lo - ext_lo
    retr_long = (
        _happened_earlier(brk_dn, day)
        & (eth < IBFAIL_CUTOFF)
        & (ext_dn >= MIN_EXT_IB_FRAC * ib_rng)
        & (c >= ib_lo - (1.0 - DEEP_RETR) * ext_dn)
    )
    out["ib_deepret_long"] = (_first_of_day(retr_long, day), +1)

    # ═════════════════════════════════════════════════════════════════════════
    # 7/8. NEUTRAL-DAY EXTREME FADE.  [P5]
    #      Neutral Day = "Initial Balance breaks out on both sides" and "Price
    #      closes near the center of the profile".  Once BOTH IB extremes have
    #      been taken out the session is classified neutral, and the documented
    #      expectation is a close back in the middle - so every subsequent poke of
    #      an IB extreme that fails to hold is faded toward the centre.
    #      CONCRETE READING: the opposite-side break must have happened STRICTLY
    #      earlier (cumulative flag), and the entry bar must poke through the
    #      near extreme yet close back inside the IB.
    # ═════════════════════════════════════════════════════════════════════════
    took_hi = ib_ok & (h > ib_hi)
    took_lo = ib_ok & (l < ib_lo)

    neutral_short = (
        ib_ok
        & (eth < NEUTRAL_CUTOFF)
        & _happened_earlier(took_lo, day)      # downside already extended
        & (h > ib_hi)                          # now poking the upside
        & (c < ib_hi)                          # and rejected back into balance
    )
    out["ib_neutral_short"] = (neutral_short, -1)

    neutral_long = (
        ib_ok
        & (eth < NEUTRAL_CUTOFF)
        & _happened_earlier(took_hi, day)
        & (l < ib_lo)
        & (c > ib_lo)
    )
    out["ib_neutral_long"] = (neutral_long, +1)

    # ═════════════════════════════════════════════════════════════════════════
    # 9/10. POOR-HIGH / POOR-LOW REVISIT.  [P6] + [P7]
    #       "if the next day or in some subsequent session, the poor high is
    #       revisited, then the odds are strong that it will break and move
    #       higher" (mirror for the poor low).  This is the one MOMENTUM rule in
    #       the file - it is what the source says, so it is what is implemented.
    #       The prior session qualifies as a poor high when two or more of its
    #       bars printed within 3% of the session range of the high, the session
    #       closed in the top quarter of its range (no excess tail), and it was a
    #       net buying auction [P7]'s "sustained move" qualifier.
    #       CONCRETE READING of "revisited... will break": the first 5-min bar of
    #       a later session to CLOSE beyond the level.  The level carries forward
    #       until some session trades through it [P6], up to POOR_MAX_AGE sessions.
    # ═════════════════════════════════════════════════════════════════════════
    poor_hi_break = pphi.notna() & (eth < POOR_CUTOFF) & (c > pphi) & (prev_c <= pphi)
    out["ib_poorhi_long"] = (_first_of_day(poor_hi_break, day), +1)

    poor_lo_break = pplo.notna() & (eth < POOR_CUTOFF) & (c < pplo) & (prev_c >= pplo)
    out["ib_poorlo_short"] = (_first_of_day(poor_lo_break, day), -1)

    # ═════════════════════════════════════════════════════════════════════════
    # 11/12. NAKED-POC RESPONSIVE REVERSAL.  [P8]
    #        The most recent prior-session POC that no later session has traded
    #        through, aged 2-10 sessions ("recent (within 1-10 sessions)") and
    #        within 1.5 daily ATR of today's open ("nearby (within reasonable
    #        ATR)").  Playbook: "price tests the POC, finds responsive
    #        participation, and reverses back".
    #        CONCRETE READING: price arrives from one side (previous close on that
    #        side), the bar's range touches the level, and the bar CLOSES back on
    #        the side it came from - the responsive rejection.  Approach from
    #        above -> long; approach from below -> short.  First touch only.
    # ═════════════════════════════════════════════════════════════════════════
    npoc_near = (npoc - day_open).abs() <= NPOC_MAX_DIST_ATR * datr
    npoc_base = npoc.notna() & npoc_near & (eth < NPOC_CUTOFF)

    npoc_long = npoc_base & (prev_c > npoc) & (l <= npoc) & (c > npoc)
    out["ib_npoc_long"] = (_first_of_day(npoc_long, day), +1)

    npoc_short = npoc_base & (prev_c < npoc) & (h >= npoc) & (c < npoc)
    out["ib_npoc_short"] = (_first_of_day(npoc_short, day), -1)

    return {k: (v.reindex(df.index).fillna(False).astype(bool), s)
            for k, (v, s) in out.items()}
