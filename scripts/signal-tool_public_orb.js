// =============================================================
//  orb.js — Opening-Range Breakout v5 signal logic, ported 1:1 from
//  orb_v5.pine (the current KEEPER strategy). Framework-free so it is
//  shared by:
//    - the Discord watcher (watcher.js -> require/globalThis.ORB)
//    - the browser panel (public/app.js -> window.ORB)
//    - the future TopstepX extension content script
//
//  Edge (take only the STRONG NY-open break of the opening range):
//    LONG  = inside the entry window, a bar closes ABOVE orHigh+buffer,
//            WITH session VWAP (close>vwap), WITH a volume surge
//            (vol > volMult * SMA(vol,volLen)), and a strong close
//            (close in the top `bodyFrac` of the bar's range).
//    SHORT = mirror (below orLow-buffer).
//  Initial stop = opposite side of the OR. The live exit is a TRAILING
//  RUNNER (arm at +trailActR R, trail trailOffR R behind) — managed by
//  hand; the alert reports the entry, the initial stop, and a 1.5R
//  reference target.
//
//  IMPORTANT differences vs the Pine strategy (by necessity, documented):
//   - This is a *signal* detector, not a position manager. It fires on the
//     FIRST strong break of the day (either direction). Re-entries
//     (Pine maxTrades=2) are left to manual judgement.
//   - Session VWAP is anchored at the RTH open (09:30 ET) — the "opening
//     VWAP" the Pine comments describe — and accumulated cumulatively, so
//     it matches ta.vwap closely for the RTH session.
//
//  Consumes bars = [{ t, o, h, l, c, v }] with t = epoch SECONDS.
// =============================================================
(function (root) {
  "use strict";

  const I = root.Indicators;
  if (!I) throw new Error("orb.js requires indicators.js to load first");

  // v5 defaults — match orb_v5.pine input defaults exactly.
  const CONFIG = {
    orMinutes: 15,        // opening-range length (09:30-09:45 ET)
    openHHMM: 930,        // session open (ET)
    bufTicks: 2,          // breakout buffer past the range, in ticks
    entryEndHHMM: 1030,   // stop taking new breaks after this (ET)
    rthEndHHMM: 1600,     // RTH close (VWAP anchor window end)
    useTrendFilter: true, // only break WITH session VWAP
    useVolFilter: true,   // require a volume surge on the breakout bar
    volLen: 20,
    volMult: 1.2,
    useBodyFilter: true,  // require a strong close on the breakout bar
    bodyFrac: 0.5,
    useRangeFilter: false, // skip days with a junk-sized OR (live: turn ON)
    minRangePts: 8,        // ignore micro-ranges (no real range to break)
    maxRangePts: 70,       // ignore wild-wide opens (stop would be huge)
    useLong: true,
    useShort: true,
    trailActR: 1.0,       // (reporting) arm the trail at +1R
    trailOffR: 1.0,       // (reporting) trail 1R behind
    rMult: 1.5,           // (reporting) reference fixed target
    tick: 0.25,           // NQ/MNQ min tick
    pointValueNQ: 20,
    pointValueMNQ: 2,
  };

  function hhmmToMins(hhmm) {
    return Math.floor(hhmm / 100) * 60 + (hhmm % 100);
  }

  // ET wall-clock parts for an epoch-second timestamp.
  function etParts(epochSec) {
    const et = new Date(new Date(epochSec * 1000).toLocaleString("en-US", { timeZone: "America/New_York" }));
    return {
      day: et.getDay(),
      mins: et.getHours() * 60 + et.getMinutes(),
      dateKey: `${et.getFullYear()}-${et.getMonth()}-${et.getDate()}`,
    };
  }

  // Evaluate the ORB v5 signal at bar index `at` (default: last bar).
  // Pass the last CLOSED bar so a still-forming bar can't flicker it.
  function computeORB(bars, at, userOpts) {
    const cfg = Object.assign({}, CONFIG, userOpts || {});
    const n = bars.length;
    const i = at == null ? n - 1 : at;

    const tick = cfg.tick;
    const buf = cfg.bufTicks * tick;
    const openMins = hhmmToMins(cfg.openHHMM);
    const orEndMins = openMins + cfg.orMinutes;
    const entryEnd = hhmmToMins(cfg.entryEndHHMM);
    const rthEnd = hhmmToMins(cfg.rthEndHHMM);

    const vol = bars.map((b) => b.v || 0);
    const volAvg = I.sma(vol, cfg.volLen);

    const pI = etParts(bars[i].t);
    const dayKey = pI.dateKey;

    const blank = (signal, reason, extra) => Object.assign({
      signal, reason, dir: 0,
      price: bars[i].c, barTime: bars[i].t,
      orHigh: null, orLow: null, orRange: null, vwap: null,
    }, extra || {});

    if (i < 1) return blank("WAIT", "not enough history");

    // ----- One forward pass over today's bars (ET calendar day = RTH day) -----
    let orHigh = null, orLow = null;
    let vNum = 0, vDen = 0;            // cumulative session VWAP (anchored 09:30)
    let firstLong = -1, firstShort = -1;

    for (let k = 0; k <= i; k++) {
      const p = etParts(bars[k].t);
      if (p.dateKey !== dayKey) continue; // only this RTH day

      // Cumulative session VWAP over RTH bars.
      if (p.mins >= openMins && p.mins < rthEnd) {
        const hlc3 = (bars[k].h + bars[k].l + bars[k].c) / 3;
        const v = bars[k].v || 0;
        vNum += hlc3 * v;
        vDen += v;
      }

      // Build the opening range.
      if (p.mins >= openMins && p.mins < orEndMins) {
        orHigh = orHigh == null ? bars[k].h : Math.max(orHigh, bars[k].h);
        orLow = orLow == null ? bars[k].l : Math.min(orLow, bars[k].l);
        continue; // no breakout while the OR is still building
      }

      // Breakout evaluation, only inside the entry window and after OR is set.
      const inWin = p.mins >= orEndMins && p.mins < entryEnd;
      if (!inWin || orHigh == null || orLow == null) continue;

      const vwapK = vDen > 0 ? vNum / vDen : null;
      const ck = bars[k].c;
      const rng = bars[k].h - bars[k].l;
      const volOKk = !cfg.useVolFilter || (volAvg[k] != null && vol[k] > cfg.volMult * volAvg[k]);
      const bodyUpK = !cfg.useBodyFilter || (rng > 0 && (ck - bars[k].l) >= cfg.bodyFrac * rng);
      const bodyDnK = !cfg.useBodyFilter || (rng > 0 && (bars[k].h - ck) >= cfg.bodyFrac * rng);
      const upK = !cfg.useTrendFilter || (vwapK != null && ck > vwapK);
      const dnK = !cfg.useTrendFilter || (vwapK != null && ck < vwapK);

      const Lk = cfg.useLong && ck > orHigh + buf && upK && volOKk && bodyUpK;
      const Sk = cfg.useShort && ck < orLow - buf && dnK && volOKk && bodyDnK;
      if (Lk && firstLong < 0) firstLong = k;
      if (Sk && firstShort < 0) firstShort = k;
    }

    const vwap = vDen > 0 ? vNum / vDen : null;
    const orRange = (orHigh != null && orLow != null) ? orHigh - orLow : null;
    const base = { orHigh, orLow, orRange, vwap, price: bars[i].c, barTime: bars[i].t };

    // Range filter: a junk-sized OR (too tight or too wide) is no-trade.
    const rangeOK = !cfg.useRangeFilter ||
      (orRange != null && orRange >= cfg.minRangePts && orRange <= cfg.maxRangePts);

    // The day's first break (either direction), gated by range quality.
    const haveLong = rangeOK && firstLong >= 0;
    const haveShort = rangeOK && firstShort >= 0;
    const firstDir =
      haveLong && (!haveShort || firstLong <= firstShort) ? "L" :
      haveShort ? "S" : null;

    // ----- Build the signal for THIS bar -----
    const inOR = pI.mins >= openMins && pI.mins < orEndMins;
    const inEntryWindow = pI.mins >= orEndMins && pI.mins < entryEnd;

    // Fire only on the bar that IS the day's first strong break.
    if (firstDir === "L" && firstLong === i) {
      const entry = bars[i].c;
      const stop = orLow;            // opposite side of the OR
      const risk = entry - stop;
      if (risk > 0) {
        return Object.assign({}, base, {
          signal: "BUY", dir: 1, entry, stop, target: entry + cfg.rMult * risk,
          stopPts: risk, tgtPts: cfg.rMult * risk,
          reason: `STRONG break ABOVE the opening range (vol surge + strong close${cfg.useTrendFilter ? " + above VWAP" : ""}) -> LONG, trail the runner`,
        });
      }
    }
    if (firstDir === "S" && firstShort === i) {
      const entry = bars[i].c;
      const stop = orHigh;
      const risk = stop - entry;
      if (risk > 0) {
        return Object.assign({}, base, {
          signal: "SELL", dir: -1, entry, stop, target: entry - cfg.rMult * risk,
          stopPts: risk, tgtPts: cfg.rMult * risk,
          reason: `STRONG break BELOW the opening range (vol surge + strong close${cfg.useTrendFilter ? " + below VWAP" : ""}) -> SHORT, trail the runner`,
        });
      }
    }

    // ----- Status (no actionable signal on this bar) -----
    if (inOR) return Object.assign({}, base, { signal: "WAIT", dir: 0, reason: "OR building (09:30-09:45 ET)" });
    if (orHigh == null) return Object.assign({}, base, { signal: "WAIT", dir: 0, reason: "pre-open / no opening range yet today" });
    if (!rangeOK) return Object.assign({}, base, { signal: "WAIT", dir: 0, reason: `skip - OR ${orRange != null ? orRange.toFixed(1) : "?"}pt out of bounds (${cfg.minRangePts}-${cfg.maxRangePts}pt)` });
    if (firstDir && (firstLong < i && firstShort < i)) {
      return Object.assign({}, base, { signal: "WAIT", dir: 0, reason: "first break already fired today - manage it / re-entries are manual" });
    }
    if (inEntryWindow) return Object.assign({}, base, { signal: "ARMED", dir: 0, reason: "ARMED - waiting for a STRONG break of the range" });
    if (pI.mins >= entryEnd && pI.mins < rthEnd) return Object.assign({}, base, { signal: "WAIT", dir: 0, reason: "entry window closed (no strong break by 10:30 ET)" });
    return Object.assign({}, base, { signal: "WAIT", dir: 0, reason: "outside the morning entry window" });
  }

  root.ORB = { CONFIG, computeORB, hhmmToMins, etParts };
})(typeof window !== "undefined" ? window : globalThis);
