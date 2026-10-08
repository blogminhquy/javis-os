// Resonance A2: thẻ mục tiêu hiện nhịp thức (dashboard/chat-resonance.js).
//
//     python tests/run.py --js resonance_a2_ui -v
//
// Lần thức tới hiện nhãn DỊCH ĐƯỢC theo mã lý do (không còn câu tiếng Việt thô trên giao diện tiếng Anh), sổ các lần
// thức gần đây, trạng thái theo dõi điều kiện bảo vệ (đã ngừng thì nói rõ, không hiện như đang an toàn), và dòng báo
// file bị sửa ngoài Javis. Chạy dưới node, hàm thuần.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const RS = require(path.join(ROOT, "dashboard", "chat-resonance.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "chat-resonance.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

const base = {
  goal_id: "g_a2", revision: 1, status: "active", run_state: "waiting", block_reason: "scheduled", paused: false,
  understanding: "Ghi chú tổng hợp", fit: "unknown", criteria: [], calls_used: 1, budget_calls: 6, timeline: [],
  next_wake: { at: 1800000000, reason: "kiểm lại file bị sửa ngoài Javis", code: "drift_recheck" },
  observe: { state: "none", next_at: null, lost_reason: "" }, wakes_recent: [], source_drift: null,
};

const h1 = RS.viewHtml(base);
check("lần thức tới hiện nhãn theo mã, không hiện câu thô của máy chủ",
  h1.includes(vi["resonance.wake.drift_recheck"]) && !h1.includes("kiểm lại file bị sửa ngoài Javis"));
const h2 = RS.viewHtml(Object.assign({}, base, { next_wake: { at: 1800000000, reason: "x", code: "ma_moi_chua_biet" } }));
check("mã lạ hiện như xem lại định kỳ, không lộ mã thô",
  h2.includes(vi["resonance.wake.review"]) && !h2.includes("ma_moi_chua_biet"));

const lost = RS.viewHtml(Object.assign({}, base, { observe: { state: "lost", next_at: null, lost_reason: "agent_off" } }));
check("ngừng theo dõi guard: có dòng cảnh báo rõ", lost.includes(vi["resonance.observe_lost"]) && lost.includes("rs-warn"));
const on = RS.viewHtml(Object.assign({}, base, { observe: { state: "on", next_at: 1800003600, lost_reason: "" } }));
check("đang theo dõi guard: có dòng lần kiểm tới, không cảnh báo",
  on.includes(vi["resonance.observe_on"].split("{at}")[0]) && !on.includes(vi["resonance.observe_lost"]));

const drift = RS.viewHtml(Object.assign({}, base, { block_reason: "source_drift",
  source_drift: { path: "Inbox/a.md", since: 1800000000 } }));
check("sửa ngoài luồng: nói rõ file nào, không ghi đè, giờ tự kiểm lại",
  drift.includes("Inbox/a.md") && drift.includes(vi["resonance.st_source_drift"]));

const wk = RS.viewHtml(Object.assign({}, base, { wakes_recent: [
  { at: 1800000000, codes: ["feedback"], decision: "work", kind: "work", model_calls: 1 },
  { at: 1800021600, codes: ["review"], decision: "evaluate", kind: "work", model_calls: 0 },
  { at: 1800025200, codes: [], decision: "observe", kind: "observe", model_calls: 0 }] }));
check("sổ thức gần đây: nhãn lý do và có gọi model hay không",
  wk.includes(vi["resonance.wakes_recent"]) && wk.includes(vi["resonance.wake.feedback"]) &&
  wk.includes(vi["resonance.wake_model"]) && wk.includes(vi["resonance.wake_no_model"]) &&
  wk.includes(vi["resonance.wake.guard_observe"]));

check("trạng thái mới có nhãn: stalled, source_drift, handoff",
  ["stalled", "source_drift", "handoff"].every((r) => RS.stateKey({ status: "active", block_reason: r }) === "resonance.st_" + r));

const keys = Object.keys(vi).filter((k) => k.startsWith("resonance.wake") || ["resonance.st_stalled",
  "resonance.st_source_drift", "resonance.st_handoff", "resonance.drift", "resonance.observe_lost",
  "resonance.observe_on"].includes(k));
check(`chuỗi A2 có đủ hai thứ tiếng (${keys.length} khoá)`, keys.length >= 28 && keys.every((k) => en[k] && vi[k]));
const wakeKeys = SRC.match(/var WAKE_KEYS = \{([\s\S]*?)\};/)[1].match(/"(resonance\.wake\.\w+)"/g) || [];
check("mọi mã lý do trong thẻ có nhãn (" + wakeKeys.length + ")", wakeKeys.length === 19 &&
  wakeKeys.map((s) => s.replace(/"/g, "")).every((k) => vi[k] && en[k]));
check("không có ký tự gạch dài trong chuỗi A2", keys.every((k) => !/\u2014/.test(vi[k] + en[k])));

if (fails) {
  console.log(`\n${fails} FAIL`);
  process.exit(1);
}
console.log("\nOK");
