"""TURTLE entries — Richard Dennis / Bill Eckhardt's Turtle program, ported to MNQ 5-min.

SOURCE OF RULES (primary documents, not blog paraphrase):
  * "The Original Turtle Trading Rules", Curtis Faith / OriginalTurtles.org (free PDF).
    Mirror used: https://oxfordstrat.com/coasdfASD32/uploads/2016/01/turtle-rules.pdf
    Every rule below is quoted verbatim from that document in the comment above it.
  * Curtis Faith, "Way of the Turtle" (McGraw-Hill 2007) — the Donchian Trend and
    ATR Channel Breakout systems he benchmarks in the book. I did not have the book text
    itself; the parameters for those two are taken from published rule statements of
    Faith's systems at
      https://www.whselfinvest.com/en-lu/trading-platform/free-trading-strategies/tradingsystem/80-atr-channel-breakout-curtis-faith
      https://www.tradingcode.net/tradingview/donchian-trend-strategy/
    Rule summaries cross-checked against https://www.theturtletrader.com/turtle-trading-rules/
    and https://www.mql5.com/en/articles/23448

TRACK RECORD: this is about as documented as a track record gets. Dennis funded ~23
traders 1983-1985; the group's audited returns were reported around 80%/yr over the
program, and several (Jerry Parker/Chesapeake, Liz Cheval, Paul Rabar, Howard Seidler)
went on to run public CTA programs with filed performance. The rules are 100% mechanical
and were published in full by the participants themselves.

THE PORT — READ THIS BEFORE JUDGING ATTRIBUTION
The Turtles traded DAILY bars on futures. Every rule here is a strict BAR-FOR-BAR port:
wherever the document says "20 days" this file uses 20 five-minute bars, "55 days" ->
55 bars, "10 days" -> 10 bars, and N (the 20-day Wilder ATR) -> a 20-BAR Wilder ATR.
Nothing else is changed. Channels are continuous across the RTH session boundary, which
is faithful: the Turtles traded continuous contracts and had an explicit gap rule
("in the case of opening gaps, the Turtles would enter positions on the open if a market
opened through the price of the breakout").

Where the document is silent I have picked a concrete reading and said so at the point
of the choice, tagged READING. I have not invented any rule and attributed it to them.

CAUSALITY: channels are rolling(...).shift(1); the breakout-outcome state machine in
_turtle_state() is a strictly forward single pass that writes bar i's flag BEFORE
processing bar i's new breakout, so no bar ever sees its own or a later outcome.
Audited by lookahead_audit.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _b(s, idx) -> pd.Series:
    return pd.Series(s, index=idx).reindex(idx).fillna(False).astype(bool)


def _wilder_atr(h: pd.Series, l: pd.Series, c: pd.Series, n: int) -> pd.Series:
    """N, per the document: 'N is simply the 20-day exponential moving average of the
    True Range' with the Wilder recursion  N = (19 * PDN + TR) / 20."""
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


# ─────────────────────────────────────────────────────────────────────────────
# The System-1 breakout state machine.
#
# Doc, System 1 entry filter (verbatim):
#   "System 1 breakout entry signals would be ignored if the last breakout would have
#    resulted in a winning trade. NOTE: For the purposes of this test, the last breakout
#    was considered the last breakout in the particular commodity irrespective of whether
#    or not that particular breakout was actually taken, or was skipped because of this
#    rule. This breakout would be considered a losing breakout if the price subsequent to
#    the date of the breakout moved 2N against the position before a profitable 10-day
#    exit occurred. The direction of the last breakout was irrelevant to this rule."
#
# Doc, adding units (verbatim):
#   "Turtles entered single Unit long positions at the breakouts and added to those
#    positions at 1/2 N intervals following their initial entry."  ... "This would
#    continue right up to the maximum permitted number of units" (four).
#
# Doc, the Whipsaw alternate stop (verbatim):
#   "Instead of taking a 2% risk on each trade, the stops were placed at 1/2 N for 1/2%
#    account risk. If a given Unit was stopped out, the Unit would be re-entered if the
#    market reached the original entry price."
#
# READING 1 — the document never says what to do when the previous breakout has not yet
# resolved (no 2N adverse move yet, no 10-bar exit yet). Peeking at its eventual outcome
# would be lookahead. I resolve it the only causal way that is also the literal reading:
# a breakout counts as a winner only once a *profitable 10-bar exit has actually
# occurred*. Unresolved => not a winner => the new signal is taken.
#
# READING 2 — the document defines "loser" via the 2N adverse move. If instead the 10-bar
# exit fires first at or below the breakout price, no "profitable 10-day exit occurred",
# the trade is over, and I classify it a loser. Same partition, no third state.
#
# READING 3 — if a bar pokes through both the 20-bar high and the 20-bar low (an outside
# bar), I take the side the bar closed toward. The document does not contemplate this.
# ─────────────────────────────────────────────────────────────────────────────
_MAX_UNITS = 4          # doc: "a maximum of 4 Units in a single market"
_STOP_N = 2.0           # doc: "Turtle stops were set at 2 N below the entry"
_ADD_N = 0.5            # doc: "added to those positions at 1/2 N intervals"
_WHIP_N = 0.5           # doc: Whipsaw "stops were placed at 1/2 N"


def _turtle_machine(high, low, close, n_arr, ch_hi, ch_lo, ex_lo, ex_hi,
                    fs_hi=None, fs_lo=None):
    """One causal forward pass simulating a Turtle trading a single breakout system.

    Args are Python float lists. ch_hi/ch_lo are the PRIOR-M-bar Donchian entry bounds
    (already .shift(1)-ed); ex_lo/ex_hi are the PRIOR-K-bar exit bounds.

    A breakout is registered ONLY while the previous one is resolved. That is not an
    optimisation, it is the rule: a Turtle bought ONE Unit at the breakout and then added
    at 1/2 N — they did not re-enter on every subsequent new 20-day high. Without this
    guard a trending leg emits a signal on every bar of the run.

    Returns dict of bool arrays, each valid as of the CLOSE of bar i:
      new_up/new_dn a fresh breakout entry opportunity fired this bar
      prev_win      the last RESOLVED breakout was a winning trade (=> skip System 1)
      add_l/add_s   a 1/2 N pyramid add level was reached this bar (units 2-4)
      whip_l/whip_s the Whipsaw re-entry (return to the original breakout price after a
                    1/2 N stop-out) triggered this bar
      fs_up/fs_dn   the Failsafe Breakout: while the skip filter is armed (last resolved
                    breakout was a winner) price reached the fs_hi/fs_lo channel. Fires
                    once per armed episode. Empty unless fs_hi/fs_lo are supplied.
    """
    t = len(high)
    new_up = np.zeros(t, dtype=bool)
    new_dn = np.zeros(t, dtype=bool)
    prev_win = np.zeros(t, dtype=bool)
    add_l = np.zeros(t, dtype=bool)
    add_s = np.zeros(t, dtype=bool)
    whip_l = np.zeros(t, dtype=bool)
    whip_s = np.zeros(t, dtype=bool)
    fs_up = np.zeros(t, dtype=bool)
    fs_dn = np.zeros(t, dtype=bool)
    has_fs = fs_hi is not None
    fs_done = False     # the failsafe has already fired in the current armed episode

    side = 0            # side of the breakout currently being tracked (0 = none open)
    entry = 0.0         # its breakout price
    bn = 0.0            # N at the moment of that breakout
    units = 0
    next_add = 0.0
    whip_armed = False  # the 1/2 N Whipsaw stop has been hit, waiting for re-entry
    last_res = 0        # outcome of the last RESOLVED breakout: +1 win, -1 loss, 0 none

    nan = float("nan")
    for i in range(t):
        hi, lo = high[i], low[i]

        # ── 1. advance the open breakout with THIS bar, before emitting any flag.
        if side != 0:
            xl, xh = ex_lo[i], ex_hi[i]
            was = last_res
            if side > 0:
                if lo <= entry - _STOP_N * bn:
                    last_res, side = -1, 0                      # 2N against, first
                elif xl == xl and lo <= xl:                     # xl==xl -> not NaN
                    last_res, side = (1 if xl > entry else -1), 0
            else:
                if hi >= entry + _STOP_N * bn:
                    last_res, side = -1, 0
                elif xh == xh and hi >= xh:
                    last_res, side = (1 if xh < entry else -1), 0
            if side == 0 and last_res != was:
                fs_done = False                                 # new armed episode

        # ── 2. pyramid adds and Whipsaw re-entry, only while the trade is live.
        if side > 0:
            while units < _MAX_UNITS and hi >= next_add:
                add_l[i] = True
                units += 1
                next_add += _ADD_N * bn
            if whip_armed:
                if hi >= entry:
                    whip_l[i] = True
                    whip_armed = False
            elif lo <= entry - _WHIP_N * bn:
                whip_armed = True
        elif side < 0:
            while units < _MAX_UNITS and lo <= next_add:
                add_s[i] = True
                units += 1
                next_add -= _ADD_N * bn
            if whip_armed:
                if lo <= entry:
                    whip_s[i] = True
                    whip_armed = False
            elif hi >= entry + _WHIP_N * bn:
                whip_armed = True

        # ── 3. emit the state a trader sees at the close of bar i. This happens BEFORE
        # any new breakout on bar i is registered, so a breakout on bar i is filtered by
        # the PREVIOUS breakout's outcome — which is the rule.
        prev_win[i] = last_res == 1

        # ── 3b. THE FAILSAFE BREAKOUT. While the skip filter is armed the System 1
        # trader takes no 20-bar entry and instead waits for the wider channel. This is
        # evaluated on every bar of the armed episode, not only on ledger-registration
        # bars, because that is when the waiting trader would actually get filled.
        if has_fs and last_res == 1 and not fs_done:
            fh, fl = fs_hi[i], fs_lo[i]
            if fh == fh and hi > fh:
                fs_up[i] = True
                fs_done = True
            elif fl == fl and lo < fl:
                fs_dn[i] = True
                fs_done = True

        # ── 4. register a new breakout on bar i, only if flat.
        if side != 0:
            continue
        chi, clo, nn = ch_hi[i], ch_lo[i], n_arr[i]
        if chi != chi or clo != clo or nn != nn or nn <= 0:
            continue
        up, dn = hi > chi, lo < clo
        if not (up or dn):
            continue
        if up and dn:                                   # READING 3
            up = close[i] >= close[i - 1] if i else True
            dn = not up
        side = 1 if up else -1
        entry = chi if up else clo
        bn = nn
        units = 1
        next_add = entry + side * _ADD_N * bn
        whip_armed = False
        if up:
            new_up[i] = True
        else:
            new_dn[i] = True

    return dict(new_up=new_up, new_dn=new_dn, prev_win=prev_win, add_l=add_l,
                add_s=add_s, whip_l=whip_l, whip_s=whip_s, fs_up=fs_up, fs_dn=fs_dn)


def register(df: pd.DataFrame) -> dict:
    idx = df.index
    h, l, c = df["high"], df["low"], df["close"]

    # N = 20-bar Wilder ATR (doc: "the 20-day exponential moving average of the True Range")
    n20 = _wilder_atr(h, l, c, 20)

    # Doc: "A breakout is defined as the price exceeding the high or low of a particular
    # number of days ... a 20-day breakout would be defined as exceeding the high or low
    # of the PRECEDING 20 days."  -> the channel must exclude the current bar, hence
    # .shift(1). NOTE df["donch_hi20"] includes the current bar and is NOT the Turtle
    # channel; it is deliberately not used here.
    hi20 = h.rolling(20).max().shift(1)
    lo20 = l.rolling(20).min().shift(1)
    hi55 = h.rolling(55).max().shift(1)
    lo55 = l.rolling(55).min().shift(1)
    ex_lo10 = l.rolling(10).min().shift(1)
    ex_hi10 = h.rolling(10).max().shift(1)

    def _run(ch_hi, ch_lo, ex_lo, ex_hi, fs_hi=None, fs_lo=None):
        f = (lambda s: None if s is None else s.to_numpy(float).tolist())
        return _turtle_machine(
            h.to_numpy(float).tolist(), l.to_numpy(float).tolist(),
            c.to_numpy(float).tolist(), n20.to_numpy(float).tolist(),
            f(ch_hi), f(ch_lo), f(ex_lo), f(ex_hi), f(fs_hi), f(fs_lo))

    # Doc: "Turtles always traded at the breakout when it was exceeded during the day,
    # and did not wait until the daily close" -> the trigger is the bar's high/low
    # touching the channel, not its close. The harness fills at the bar close.
    # System 1 = 20-bar entry / 10-bar exit.  System 2 = 55-bar entry / 20-bar exit.
    s1 = _run(hi20, lo20, ex_lo10, ex_hi10, fs_hi=hi55, fs_lo=lo55)
    s2 = _run(hi55, lo55, l.rolling(20).min().shift(1), h.rolling(20).max().shift(1))

    def _s(machine, key):
        return pd.Series(machine[key], index=idx)

    bo20_up, bo20_dn = _s(s1, "new_up"), _s(s1, "new_dn")
    bo55_up, bo55_dn = _s(s2, "new_up"), _s(s2, "new_dn")
    prev_win = _s(s1, "prev_win")

    out: dict = {}

    # ── 1. SYSTEM 1 — 20-bar breakout, skipped when the last breakout won. ───────
    # "System 1 Entry - Turtles entered positions when the price exceeded by a single
    #  tick the high or low of the preceding 20 days ... signals would be ignored if the
    #  last breakout would have resulted in a winning trade."
    out["tt_turtle_s1_long"] = (_b(bo20_up & ~prev_win, idx), +1)
    out["tt_turtle_s1_short"] = (_b(bo20_dn & ~prev_win, idx), -1)

    # ── 2. SYSTEM 2 — 55-bar breakout, filter-free. ─────────────────────────────
    # "System 2 Entry - Entered when the price exceeded by a single tick the high or low
    #  of the preceding 55 days ... All breakouts for System 2 would be taken whether the
    #  previous breakout had been a winner or not."
    out["tt_turtle_s2_long"] = (_b(bo55_up, idx), +1)
    out["tt_turtle_s2_short"] = (_b(bo55_dn, idx), -1)

    # ── 3. THE FAILSAFE BREAKOUT — the 55-bar entry taken *because* S1 was skipped. ──
    # "However, in the event that a System 1 entry breakout was skipped because the
    #  previous trade had been a winner, an entry would be made at the 55-day breakout to
    #  avoid missing major moves. This 55-day breakout was considered the Failsafe
    #  Breakout point."
    # READING 5 — emitted from inside the System 1 machine: any bar of an armed-skip
    # episode on which price reaches the 55-bar channel, once per episode. This is a
    # different signal from System 2: System 2 fires when the S2 trader is flat, the
    # failsafe fires when the S1 trader is standing aside because of the skip rule.
    out["tt_turtle_failsafe_long"] = (_b(_s(s1, "fs_up"), idx), +1)
    out["tt_turtle_failsafe_short"] = (_b(_s(s1, "fs_dn"), idx), -1)

    # ── 4. THE 1/2 N PYRAMID ADD. ───────────────────────────────────────────────
    # "Turtles ... added to those positions at 1/2 N intervals following their initial
    #  entry", up to four units. Each add was itself a live order into the market, so each
    #  is a legitimate standalone entry to test. Unit 1 lands on the breakout bar and is
    #  already strategy 1, so this fires on units 2, 3 and 4 only.
    add_l, add_s = _s(s1, "add_l"), _s(s1, "add_s")
    first_unit = bo20_up | bo20_dn               # unit 1 lands on the breakout bar
    out["tt_turtle_addunit_long"] = (_b(add_l & ~first_unit, idx), +1)
    out["tt_turtle_addunit_short"] = (_b(add_s & ~first_unit, idx), -1)

    # ── 5. THE WHIPSAW RE-ENTRY. ────────────────────────────────────────────────
    # "the stops were placed at 1/2 N ... If a given Unit was stopped out, the Unit would
    #  be re-entered if the market reached the original entry price."  A pullback of 1/2 N
    #  from the breakout followed by a return to the breakout price. Fully mechanical.
    out["tt_turtle_whipsaw_long"] = (_b(_s(s1, "whip_l"), idx), +1)
    out["tt_turtle_whipsaw_short"] = (_b(_s(s1, "whip_s"), idx), -1)

    # ── 6. WAY OF THE TURTLE — "Donchian Trend". ────────────────────────────────
    # Curtis Faith's own benchmark system in Way of the Turtle: the 20-day Donchian entry
    # and 10-day exit of System 1 with NO skip filter, gated instead by a two-EMA trend
    # filter — longs only while the 25-period EMA is above the 350-period EMA.
    # Bar-for-bar port: EMA(25) and EMA(350) of the 5-min close.
    ema25 = c.ewm(span=25, adjust=False).mean()
    ema350 = c.ewm(span=350, adjust=False).mean()
    out["tt_turtle_wot_donch_long"] = (_b(bo20_up & (ema25 > ema350), idx), +1)
    out["tt_turtle_wot_donch_short"] = (_b(bo20_dn & (ema25 < ema350), idx), -1)

    # ── 7. WAY OF THE TURTLE — "ATR Channel Breakout". ──────────────────────────
    # Faith's other published benchmark system: a channel drawn a fixed number of ATRs
    # around a 350-period SMA of the close. Long when the close crosses ABOVE the upper
    # band (SMA350 + 7 ATR); short when it crosses BELOW the lower band (SMA350 - 3 ATR).
    # The asymmetry 7/3 is Faith's, not mine. Exit is a close back through the SMA — the
    # harness owns exits, so only the entry cross is returned.
    # Bar-for-bar port: 350 five-minute bars (~4.5 RTH sessions) and ATR(20) = the Turtle
    # N. READING 4 — the book does not pin the ATR lookback for this system; I use the
    # 20-period N the Turtles used everywhere else rather than inventing a new one.
    ma350 = c.rolling(350).mean()
    up_band = ma350 + 7.0 * n20
    dn_band = ma350 - 3.0 * n20
    out["tt_turtle_wot_atrchan_long"] = (
        _b((c > up_band) & (c.shift(1) <= up_band.shift(1)), idx), +1)
    out["tt_turtle_wot_atrchan_short"] = (
        _b((c < dn_band) & (c.shift(1) >= dn_band.shift(1)), idx), -1)

    return out
