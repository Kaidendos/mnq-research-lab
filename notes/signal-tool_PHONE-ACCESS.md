# Viewing the dashboard from your phone

The dashboard is **read-only** — it shows trades, P&L, the Combine scoreboard,
and bot health. It never places or changes orders. So viewing it from your
phone is fine. Two ways:

---

## ⚠️ TopStep rule first (read this)

> "All trading activity must originate from your personal device. The use of
> VPS, VPNs, and remote servers is prohibited."

- The **trading bot** (`live-signal.js` / `start-bot.bat`) must keep running on
  **this PC**, on your normal home internet. Do **not** route the bot's traffic
  through a VPN/Tailscale, and do **not** run the bot on a phone or server.
- Tailscale below is **only** so your phone can *view* the dashboard page. It
  carries dashboard pixels, not orders. Keep it that way.

---

## Option A — same Wi‑Fi (simplest, nothing to install)

1. On the PC, start the dashboard bound to all interfaces:
   ```
   set DASH_HOST=0.0.0.0
   node dashboard.js
   ```
   (Or just run `run-dashboard-lan.bat`.)
2. Find the PC's LAN IP: `ipconfig` → IPv4 Address (e.g. `192.168.1.42`).
3. On your phone (same Wi‑Fi), open `http://192.168.1.42:8787`.
4. First time, Windows Firewall may prompt — allow Node on **Private** networks.

This only works while the phone is on the same Wi‑Fi as the PC.

## Option B — anywhere, via Tailscale (private, encrypted)

Tailscale is a private mesh; the dashboard stays invisible to the public internet.

1. Install Tailscale on the **PC**: https://tailscale.com/download → sign in.
2. Install Tailscale on your **phone**, sign in with the **same** account.
3. On the PC, note its Tailscale IP from the Tailscale tray menu
   (e.g. `100.x.y.z`).
4. Start the dashboard bound to all interfaces (`DASH_HOST=0.0.0.0`, as above).
5. On the phone, open `http://100.x.y.z:8787`.

Works from cellular/anywhere, only between your own devices.

> Reminder: keep the **bot** off Tailscale. Only the phone↔dashboard view uses it.

## Notes

- Port override: `set DASH_PORT=9000` before launching.
- The dashboard auto-opens a browser only when bound to `127.0.0.1`; with
  `DASH_HOST=0.0.0.0` it won't pop a window — open the URL yourself.
- Stopping the dashboard does **not** stop the bot (separate processes).
