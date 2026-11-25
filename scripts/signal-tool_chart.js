// =============================================================
//  chart.js — zero-dependency candlestick PNG renderer.
//
//  Rasterizes the last N 5-min bars into an RGB pixel buffer and encodes it as
//  a PNG using ONLY Node built-ins (zlib for IDAT deflate, a hand-rolled CRC32).
//  Draws entry / stop / target as dashed lines and marks the trade bar, so the
//  bot can attach a real "chart screenshot of where it bought/closed" to Discord
//  while running fully headless in the background (no browser needed).
//
//  renderTradeChart(bars, opts) -> Buffer (PNG)
//    opts: { lookback, dir, entry, stop, target, entryT, exit, exitT }
//  All text (prices, P&L) lives in the Discord embed; the image is pure chart.
// =============================================================
"use strict";

const zlib = require("zlib");

const W = 860, H = 440, ML = 8, MR = 8, MT = 8, MB = 8;       // canvas + margins
const PW = W - ML - MR, PH = H - MT - MB;                      // plot area
const COL = {
  bg: [255, 255, 255], grid: [232, 235, 238],
  up: [38, 166, 154], down: [239, 83, 80],
  entry: [41, 128, 185], stop: [231, 76, 60], target: [39, 174, 96],
  mark: [41, 128, 185], exitMark: [142, 68, 173],
};

// ---- PNG encoding ----
function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xEDB88320 & -(c & 1));
  }
  return (~c) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length, 0);
  const tb = Buffer.from(type, "ascii");
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(Buffer.concat([tb, data])), 0);
  return Buffer.concat([len, tb, data, crc]);
}
function encodePNG(px) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4);
  ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0; // 8-bit RGB
  const stride = W * 3;
  const raw = Buffer.alloc((stride + 1) * H);
  for (let y = 0; y < H; y++) { raw[y * (stride + 1)] = 0; px.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride); }
  const idat = zlib.deflateSync(raw, { level: 6 });
  return Buffer.concat([sig, chunk("IHDR", ihdr), chunk("IDAT", idat), chunk("IEND", Buffer.alloc(0))]);
}

// ---- drawing primitives on an RGB Buffer ----
function makeCanvas() { const px = Buffer.alloc(W * H * 3); for (let i = 0; i < px.length; i += 3) { px[i] = COL.bg[0]; px[i + 1] = COL.bg[1]; px[i + 2] = COL.bg[2]; } return px; }
function set(px, x, y, c) { x |= 0; y |= 0; if (x < 0 || x >= W || y < 0 || y >= H) return; const i = (y * W + x) * 3; px[i] = c[0]; px[i + 1] = c[1]; px[i + 2] = c[2]; }
function vline(px, x, y0, y1, c) { if (y0 > y1) [y0, y1] = [y1, y0]; for (let y = y0; y <= y1; y++) set(px, x, y, c); }
function hline(px, y, x0, x1, c) { if (x0 > x1) [x0, x1] = [x1, x0]; for (let x = x0; x <= x1; x++) set(px, x, y, c); }
function rect(px, x0, y0, x1, y1, c) { if (y0 > y1) [y0, y1] = [y1, y0]; if (x0 > x1) [x0, x1] = [x1, x0]; for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) set(px, x, y, c); }
function dash(px, y, c) { for (let x = ML; x <= W - MR; x += 10) for (let k = 0; k < 6 && x + k <= W - MR; k++) set(px, x + k, y, c); }
function diamond(px, cx, cy, r, c) { for (let dy = -r; dy <= r; dy++) { const w = r - Math.abs(dy); for (let dx = -w; dx <= w; dx++) set(px, cx + dx, cy + dy, c); } }

// ---- main render ----
function renderTradeChart(bars, opts = {}) {
  const n = Math.min(opts.lookback || 70, bars.length);
  const view = bars.slice(bars.length - n);
  const px = makeCanvas();

  // price range across candles + the bracket levels, padded
  let lo = Infinity, hi = -Infinity;
  for (const b of view) { lo = Math.min(lo, b.l); hi = Math.max(hi, b.h); }
  for (const v of [opts.entry, opts.stop, opts.target, opts.exit]) if (v != null && isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  if (!isFinite(lo) || hi <= lo) { hi = lo + 1; }
  const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
  const yOf = (p) => MT + (1 - (p - lo) / (hi - lo)) * PH;
  const slot = PW / n;
  const xOf = (i) => ML + (i + 0.5) * slot;
  const halfBody = Math.max(1, Math.floor(slot * 0.3));

  // faint horizontal grid
  for (let g = 0; g <= 4; g++) hline(px, Math.round(MT + g / 4 * PH), ML, W - MR, COL.grid);

  // candles
  for (let i = 0; i < view.length; i++) {
    const b = view[i], x = Math.round(xOf(i)), up = b.c >= b.o, c = up ? COL.up : COL.down;
    vline(px, x, Math.round(yOf(b.h)), Math.round(yOf(b.l)), c);                          // wick
    rect(px, x - halfBody, Math.round(yOf(b.o)), x + halfBody, Math.round(yOf(b.c)), c);  // body
  }

  // bracket levels (dashed full-width)
  if (opts.stop != null) dash(px, Math.round(yOf(opts.stop)), COL.stop);
  if (opts.target != null) dash(px, Math.round(yOf(opts.target)), COL.target);
  if (opts.entry != null) dash(px, Math.round(yOf(opts.entry)), COL.entry);

  // markers on the entry / exit bars (matched by timestamp within the view)
  const findIdx = (t) => view.findIndex((b) => b.t === t);
  if (opts.entryT != null) { const ei = findIdx(opts.entryT); if (ei >= 0) { const x = Math.round(xOf(ei)); vline(px, x, MT, H - MB, COL.mark); if (opts.entry != null) diamond(px, x, Math.round(yOf(opts.entry)), 4, COL.mark); } }
  if (opts.exitT != null) { const xi = findIdx(opts.exitT); if (xi >= 0) { const x = Math.round(xOf(xi)); vline(px, x, MT, H - MB, COL.exitMark); if (opts.exit != null) diamond(px, x, Math.round(yOf(opts.exit)), 4, COL.exitMark); } }

  return encodePNG(px);
}

module.exports = { renderTradeChart };
