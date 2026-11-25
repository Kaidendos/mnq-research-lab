@echo off
title NQ Dashboard (LAN / phone access)
cd /d "C:\Users\YOU\daytrading-automation\signal-tool"
set DASH_HOST=0.0.0.0
echo Dashboard is now reachable from other devices on your network / Tailscale.
echo See PHONE-ACCESS.md. Find this PC's IP with: ipconfig
echo Then open http://THAT-IP:8787 on your phone.
echo (The trading bot must stay on THIS PC -- do not route it through a VPN.)
node dashboard.js
pause
