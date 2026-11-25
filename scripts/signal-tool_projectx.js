// =============================================================
//  projectx.js — ProjectX (TopstepX) Gateway API client.
//
//  *** DATA ONLY, BY DESIGN. ***
//  This module authenticates, looks up contracts, pulls historical bars,
//  and reads account info. It contains NO order-placement endpoints and
//  never will. Execution stays 100% manual in the TopstepX platform —
//  that is the TopStep-compliance line (API order automation is barred on
//  Live funded accounts), and it keeps this code clean when you get funded.
//
//  Credentials (NEVER hardcode, NEVER commit):
//    - secrets.local.js  ->  { projectXUsername, projectXApiKey }   (gitignored)
//    - or env vars       ->  PROJECTX_USERNAME, PROJECTX_API_KEY
//
//  Self-test (verifies your key before we wire anything else):
//    node projectx.js --test
//      -> authenticates, lists your accounts, resolves the NQ contract,
//         and prints the last few 5-min bars. No orders, read-only.
//
//  Docs: https://gateway.docs.projectx.com  (base https://api.topstepx.com)
// =============================================================
"use strict";

const BASE = process.env.PROJECTX_BASE || "https://api.topstepx.com";

// `live`: false = sim/practice data subscription, true = live data subscription.
// Practice / Combine accounts use sim data, so default false.
const LIVE = (process.env.PROJECTX_LIVE || "false").toLowerCase() === "true";

// Which instrument to pull. NQ = full E-mini (symbol ENQ), MNQ = micro.
const CONTRACT_SEARCH = process.env.PROJECTX_CONTRACT || "NQ";

function creds() {
  const user = process.env.PROJECTX_USERNAME;
  const key = process.env.PROJECTX_API_KEY;
  if (user && key) return { user, key };
  try {
    const s = require("./secrets.local.js");
    return { user: s.projectXUsername, key: s.projectXApiKey };
  } catch {
    return {};
  }
}

let cachedToken = null;
let tokenAt = 0;
const TOKEN_TTL_MS = 20 * 60 * 60 * 1000; // re-auth well within the ~24h token life

async function authToken() {
  if (cachedToken && Date.now() - tokenAt < TOKEN_TTL_MS) return cachedToken;
  const { user, key } = creds();
  if (!user || !key) {
    throw new Error(
      "ProjectX creds missing — set projectXUsername/projectXApiKey in secrets.local.js " +
      "or PROJECTX_USERNAME/PROJECTX_API_KEY env vars."
    );
  }
  const r = await fetch(`${BASE}/api/Auth/loginKey`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ userName: user, apiKey: key }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.success || !j.token) {
    throw new Error(`ProjectX auth failed: HTTP ${r.status} errorCode=${j.errorCode} ${j.errorMessage || ""}`);
  }
  cachedToken = j.token;
  tokenAt = Date.now();
  return cachedToken;
}

async function api(pathName, body) {
  const token = await authToken();
  const r = await fetch(`${BASE}${pathName}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (r.status === 401) cachedToken = null; // force re-auth on next call
  const j = await r.json().catch(() => ({}));
  if (!r.ok || j.success === false) {
    throw new Error(`ProjectX ${pathName} failed: HTTP ${r.status} errorCode=${j.errorCode} ${j.errorMessage || ""}`);
  }
  return j;
}

let cachedContractId = null;
async function resolveContract(searchText = CONTRACT_SEARCH, live = LIVE) {
  if (cachedContractId) return cachedContractId;
  const j = await api("/api/Contract/search", { searchText, live });
  const list = j.contracts || [];
  if (!list.length) throw new Error(`ProjectX: no contract found for "${searchText}"`);
  // Prefer an exact-ish front-month match; otherwise take the first result.
  cachedContractId = list[0].id;
  return cachedContractId;
}

// Pull historical bars. Returns ASCENDING {t:unixSec, o,h,l,c,v} to match watcher.js.
async function fetchBars({ unitNumber = 5, lookbackDays = 5, live = LIVE, contract = CONTRACT_SEARCH } = {}) {
  const contractId = await resolveContract(contract, live);
  const end = new Date();
  const start = new Date(end.getTime() - lookbackDays * 24 * 60 * 60 * 1000);
  const j = await api("/api/History/retrieveBars", {
    contractId,
    live,
    startTime: start.toISOString(),
    endTime: end.toISOString(),
    unit: 2, // 2 = Minute
    unitNumber, // e.g. 5 -> 5-minute bars
    limit: 20000,
    includePartialBar: false,
  });
  const bars = (j.bars || []).map((b) => ({
    t: Math.floor(new Date(b.t).getTime() / 1000),
    o: b.o, h: b.h, l: b.l, c: b.c, v: b.v ?? 0,
  }));
  bars.sort((a, b) => a.t - b.t);
  return bars;
}

async function getAccounts() {
  const j = await api("/api/Account/search", { onlyActiveAccounts: true });
  return j.accounts || [];
}

module.exports = { authToken, resolveContract, fetchBars, getAccounts, BASE, LIVE, CONTRACT_SEARCH };

// ---- CLI self-test: node projectx.js --test ----
if (require.main === module && process.argv[2] === "--test") {
  (async () => {
    try {
      process.stdout.write("Authenticating with ProjectX... ");
      await authToken();
      console.log("OK ✅");

      const accts = await getAccounts();
      console.log(`\nAccounts (${accts.length}):`);
      for (const a of accts) {
        console.log(`  • ${a.name}  id=${a.id}  balance=$${a.balance}  canTrade=${a.canTrade}`);
      }

      process.stdout.write(`\nResolving "${CONTRACT_SEARCH}" contract... `);
      const cid = await resolveContract();
      console.log(cid);

      const bars = await fetchBars({ unitNumber: 5 });
      console.log(`\nGot ${bars.length} 5-min bars. Last 3:`);
      for (const b of bars.slice(-3)) {
        const et = new Date(b.t * 1000).toLocaleString("en-US", { timeZone: "America/New_York" });
        console.log(`  ${et}  O ${b.o}  H ${b.h}  L ${b.l}  C ${b.c}  V ${b.v}`);
      }
      console.log("\nData-only self-test passed. No orders were placed (this module can't).");
    } catch (e) {
      console.error("\nSelf-test FAILED:", e.message);
      process.exit(1);
    }
  })();
}
