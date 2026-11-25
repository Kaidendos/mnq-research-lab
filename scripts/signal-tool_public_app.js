// =============================================================
//  app.js — fetches 5-min bars, runs the v1.1 mean-reversion signal
//  (window.MeanRev) on the last CLOSED bar, and paints a plain-language
//  "should I buy?" verdict. The panel == the watcher == the Pine, because
//  they all share meanrev.js, so the web answer matches the Discord alert.
//
//  Refreshes every REFRESH_MS.
// =============================================================
(function () {
  "use strict";

  const REFRESH_MS = 30000;
  const PT = 2; // price decimals

  const $ = (id) => document.getElementById(id);
  const fmt = (v, d = PT) =>
    v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(d);

  // Map a v1.1 signal to the verdict block: css class, badge, instruction.
  function verdictFor(sig) {
    switch (sig.signal) {
      case "BUY":
        return {
          cls: "v-buy", badge: "BUY",
          say: "✅ FADE LONG — take the buy",
          sub: "Enter near the entry price below. Hard stop is mandatory.",
        };
      case "SELL":
        return {
          cls: "v-sell", badge: "SELL",
          say: "✅ FADE SHORT — take the sell",
          sub: "Enter near the entry price below. Hard stop is mandatory.",
        };
      case "CLOSED":
        return {
          cls: "v-closed", badge: "CLOSED",
          say: "💤 Market closed — don't trade",
          sub: "Setups only count during RTH (09:30–16:00 ET).",
        };
      default: // WAIT
        return {
          cls: "v-wait", badge: "WAIT",
          say: "🚫 DON'T BUY — no setup yet",
          sub: "Stay flat. Wait for a clean reclaim signal.",
        };
    }
  }

  function setVerdict(v) {
    const box = $("verdict");
    box.className = "verdict " + v.cls;
    $("badge").textContent = v.badge;
    $("say").textContent = v.say;
    $("sub").textContent = v.sub;
  }

  function render(sig) {
    setVerdict(verdictFor(sig));
    $("reason").textContent = sig.reason || "—";

    const live = sig.signal === "BUY" || sig.signal === "SELL";
    $("entry").textContent = live ? fmt(sig.entry) : "—";
    $("stop").textContent = live ? fmt(sig.stop) : "—";
    $("target").textContent = live ? fmt(sig.target) : "—";

    $("price").textContent = fmt(sig.price);
    $("trend").textContent = sig.trend === "UP" ? "UP (above EMA200)"
      : sig.trend === "DOWN" ? "DOWN (below EMA200)" : "—";
    $("rsi").textContent = fmt(sig.rsi, 0);
    $("adx").textContent = sig.adx == null ? "—"
      : fmt(sig.adx, 0) + (sig.ranging ? " — ranging ✓" : " — trending ✗");
    $("session").textContent = sig.inSession ? "OPEN (RTH)" : "closed";

    if (live) {
      const C = window.MeanRev.CONFIG;
      const riskMNQ = sig.stopPts * C.pointValueMNQ;
      const riskNQ = sig.stopPts * C.pointValueNQ;
      const rewMNQ = sig.tgtPts * C.pointValueMNQ;
      const rewNQ = sig.tgtPts * C.pointValueNQ;
      $("risk").textContent =
        `${fmt(sig.stopPts, 1)} pt · $${fmt(riskMNQ, 0)}/MNQ · $${fmt(riskNQ, 0)}/NQ`;
      $("reward").textContent =
        `${fmt(sig.tgtPts, 1)} pt · $${fmt(rewMNQ, 0)}/MNQ · $${fmt(rewNQ, 0)}/NQ`;
    } else {
      $("risk").textContent = "—";
      $("reward").textContent = "—";
    }

    if (sig.barTime) {
      $("bartime").textContent = new Date(sig.barTime * 1000).toLocaleString("en-US", {
        timeZone: "America/New_York", hour: "2-digit", minute: "2-digit",
        month: "short", day: "numeric",
      }) + " ET";
    }
    $("updated").textContent = new Date().toLocaleTimeString();
  }

  function showError(msg) {
    setVerdict({ cls: "v-error", badge: "ERROR", say: "⚠️ Data problem", sub: "" });
    $("reason").textContent = msg;
  }

  async function getJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(url + " -> " + r.status);
    return r.json();
  }

  async function tick() {
    try {
      // 1mo of 5-min bars so EMA200 (200-bar) is well seeded, matching the watcher.
      const m5 = await getJSON("/api/bars?interval=5m&range=1mo");
      const bars = m5.bars || [];
      if (bars.length < 210) {
        showError(`Only ${bars.length} bars loaded — need 200+ to seed EMA200. Warming up…`);
        $("barsloaded").textContent = bars.length + " bars";
        return;
      }
      // Evaluate the last CLOSED bar (the final bar may still be forming).
      const sig = window.MeanRev.computeMeanRev(bars, bars.length - 2);
      render(sig);
      $("barsloaded").textContent = bars.length + " bars";
    } catch (e) {
      showError("Data fetch failed: " + e.message);
    }
  }

  tick();
  setInterval(tick, REFRESH_MS);
})();
