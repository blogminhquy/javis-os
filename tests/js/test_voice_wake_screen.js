/* Im lâu thì ngắt, nói là nối lại; giữ màn hình sáng khi gọi (0.65.22).

   Hai lỗi chủ dự án báo 01/10: (1) gọi "Javis" sau khi cuộc gọi ChatGPT Live ngắt vì im thì không
   nối lại được, vì trình duyệt chép tên thành "David"; (2) trên iPhone (app mở từ màn hình chính),
   màn hình tắt giữa cuộc gọi là Javis không nghe, không đáp. Chủ chốt: bỏ công tắc Tập trung, im 30
   giây thì ngắt, câu nói thật là nối lại (không cần tên, không dùng Groq), và giữ màn hình sáng.

   Chạy: node tests/js/test_voice_wake_screen.js
   Ghi chú: KHÔNG dùng ký tự em dash. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const { create } = require("../../dashboard/screen-awake.js");

(async () => {
  // ---- 1. Giữ màn hình sáng ----
  const calls = [];
  let listeners = {};
  class Lock {
    constructor() { this.released = false; this.on = {}; }
    addEventListener(name, fn) { this.on[name] = fn; }
    release() { this.released = true; calls.push("release"); if (this.on.release) this.on.release(); }
  }
  let current = null;
  const nav = { wakeLock: { request: async (type) => { calls.push("request:" + type); current = new Lock(); return current; } } };
  const doc = { visibilityState: "visible", addEventListener: (n, fn) => { listeners[n] = fn; } };
  const awake = create({ navigator: nav, document: doc });
  assert.equal(await awake.hold(), true);
  assert.deepEqual(calls, ["request:screen"]);
  assert.equal(awake.active(), true);
  assert.equal(await awake.hold(), true, "holding twice does not stack locks");
  assert.equal(calls.length, 1);
  // Trình duyệt tự nhả khoá khi trang bị ẩn; mở lại trang mà vẫn đang gọi thì xin lại.
  current.release(); calls.length = 0;
  assert.equal(awake.active(), false);
  doc.visibilityState = "hidden"; listeners.visibilitychange();
  assert.deepEqual(calls, [], "no request while hidden");
  doc.visibilityState = "visible"; listeners.visibilitychange();
  await new Promise(setImmediate);
  assert.deepEqual(calls, ["request:screen"], "re-acquired when the page is visible again");
  awake.release();
  assert.equal(awake.active(), false);
  calls.length = 0; listeners.visibilitychange(); await new Promise(setImmediate);
  assert.deepEqual(calls, [], "after hang up, coming back does not grab the screen");
  // Cúp máy trong lúc đang xin khoá: khoá về sau phải nhả ngay.
  let resolveLock;
  const slow = create({ navigator: { wakeLock: { request: () => new Promise(r => { resolveLock = r; }) } }, document: doc });
  const pending = slow.hold();
  slow.release();
  const late = new Lock();
  resolveLock(late);
  assert.equal(await pending, false);
  assert.equal(late.released, true, "a lock granted after hang up is released at once");
  // Máy không hỗ trợ: không lỗi, chỉ trả false.
  const none = create({ navigator: {}, document: doc });
  assert.equal(none.supported(), false);
  assert.equal(await none.hold(), false);
  const denied = create({ navigator: { wakeLock: { request: async () => { throw new Error("NotAllowedError"); } } }, document: doc });
  assert.equal(await denied.hold(), false, "a refused lock does not break the call");

  // ---- 2. Dây nối ----
  const app = read("dashboard/app.js");
  const html = read("dashboard/index.html");
  const con = read("dashboard/console.js");
  const vi = JSON.parse(read("dashboard/i18n/vi.json"));
  const en = JSON.parse(read("dashboard/i18n/en.json"));
  assert.match(html, /screen-awake\.js\?v=\d+"><\/script>[\s\S]{0,200}<script src="\/static\/app\.js/, "screen-awake.js loads before app.js");
  assert.match(app, /window\.JavisScreenAwake\.hold\(\)/, "opening a call keeps the screen on");
  assert.match(app, /window\.JavisScreenAwake\.release\(\)/, "hanging up lets the screen sleep");
  assert.match(app, /attention\.wakes\(text\)/, "the waiting listener wakes on real speech");
  assert.ok(!/!attention\.accept\(text\)\) return;\s*\n\s*resumeVoiceFocus/.test(app), "the old name-only rule is gone");
  assert.match(app, /function datCheDoGiong\(mode\) \{\s*\n\s*voiceMode = mode;\s*\n\s*attention\.enabled = mode === "live";/,
    "the idle gate is on for Live only");
  assert.ok(!/voiceMode = _callInfo/.test(app) && !/voiceMode = mode;\s*\n\s*voice\.sttUpload/.test(app),
    "every voiceMode change goes through datCheDoGiong");
  assert.ok(!/focus_mode/.test(app), "app.js no longer reads the removed Focus setting");
  assert.match(app, /else if \(!nghe\) batNgheAmLuong\(\);/, "no browser recogniser: fall back to the level detector");
  assert.match(app, /_liveWaitingWake = false;\s*\n\s*tatNgheAmLuong\(\);/, "the level detector releases the mic before Live reopens");
  assert.match(app, /tatNgheAmLuong\(\);\s*\n\s*if \(window\.JavisScreenAwake\) window\.JavisScreenAwake\.release\(\);/,
    "hang up stops the level detector and the screen lock");
  assert.ok(!/id="vcFocus"/.test(html) && !/vcFocus/.test(con), "the Focus switch is gone from Settings");
  assert.ok(!("settings.vc_focus" in vi) && !("settings.vc_focus_hint" in en));
  assert.ok(!/gọi/i.test(vi["call.waiting_wake"]) && /nói/.test(vi["call.waiting_wake"]), "the call bar says: just speak");
  assert.ok(!/say "?Javis/i.test(en["call.waiting_wake"]));
  console.log("OK - im lâu thì ngắt, nói là nối lại, giữ màn hình sáng");
})().catch(e => { console.error(e); process.exitCode = 1; });
