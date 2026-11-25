// =============================================================
//  notify.js — Discord webhook poster (JSON + PNG attachment).
//
//  watcher.js already posts JSON-only embeds; this adds the missing piece for
//  the dry-run engine: uploading a rendered chart PNG via multipart/form-data so
//  every entry/exit "sends a screenshot of the chart" to Discord. Reuses the same
//  webhook resolution pattern as watcher.js (env var -> secrets.local.js).
//
//  Exports:
//    getWebhook()                          -> url string | null
//    postJSON(payload)                     -> POST an embed/content (no file)
//    postImage(payload, pngBuffer, name)   -> POST embed + attachment://name PNG
//  All functions no-op gracefully (warn, never throw) if no webhook is set, so
//  the trading loop is never taken down by a notification failure.
// =============================================================
"use strict";

function getWebhook() {
  if (process.env.DISCORD_WEBHOOK_URL) return process.env.DISCORD_WEBHOOK_URL;
  try { return require("./secrets.local.js").discordWebhook; } catch { return null; }
}

async function postJSON(payload) {
  const hook = getWebhook();
  if (!hook) { console.warn("[notify] no webhook configured — skipping JSON post."); return false; }
  try {
    const r = await fetch(hook, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!r.ok) throw new Error("discord " + r.status + " " + (await r.text()).slice(0, 200));
    return true;
  } catch (e) { console.error("[notify] postJSON failed:", e.message); return false; }
}

// multipart/form-data upload: payload_json field + one file field.
// The embed can show the image via { image: { url: "attachment://<name>" } }.
async function postImage(payload, png, name = "chart.png") {
  const hook = getWebhook();
  if (!hook) { console.warn("[notify] no webhook configured — skipping image post."); return false; }
  const boundary = "----nqbot" + Date.now().toString(16);
  const head = Buffer.from(
    `--${boundary}\r\n` +
    `Content-Disposition: form-data; name="payload_json"\r\n` +
    `Content-Type: application/json\r\n\r\n` +
    `${JSON.stringify(payload)}\r\n` +
    `--${boundary}\r\n` +
    `Content-Disposition: form-data; name="files[0]"; filename="${name}"\r\n` +
    `Content-Type: image/png\r\n\r\n`, "utf8");
  const tail = Buffer.from(`\r\n--${boundary}--\r\n`, "utf8");
  const body = Buffer.concat([head, png, tail]);
  try {
    const r = await fetch(hook, { method: "POST", headers: { "Content-Type": `multipart/form-data; boundary=${boundary}` }, body });
    if (!r.ok) throw new Error("discord " + r.status + " " + (await r.text()).slice(0, 200));
    return true;
  } catch (e) { console.error("[notify] postImage failed:", e.message); return false; }
}

module.exports = { getWebhook, postJSON, postImage };
