// Resonance A1: khối Cộng hưởng theo trợ lý (dashboard/resonance-agent.js) và chỗ nối ở trang Cộng sự, Cài đặt.
//
//     python tests/run.py --js resonance_a1_ui -v
//
// Hàm thuần chạy dưới node: khối của một trợ lý theo trạng thái GET /resonance/agents và phiên đang mở, danh sách
// trên trang Cài đặt, và dây nối trong workspace.js, index.html. Trọng tâm là P2 của review vòng 2: bật trong phiên
// mở trước lúc cấp mã thì phải nói rõ và có nút mở cuộc trò chuyện mới, không báo "dùng được".
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const RA = require(path.join(ROOT, "dashboard", "resonance-agent.js"));
const RS = require(path.join(ROOT, "dashboard", "chat-resonance.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const WS = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
const CR = fs.readFileSync(path.join(ROOT, "dashboard", "chat-resonance.js"), "utf8");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "resonance-agent.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

const on = { slug: "viet-bai", name: "Viết bài", agent_key: "ag_1", enabled: true, status: "active",
  support: { goal: true, chat_output: true, background: true } };
const off = Object.assign({}, on, { enabled: false });

// ───────────── khối của một trợ lý ─────────────
let h = RA.panelHtml(off, null, []);
check("tắt: công tắc chưa chọn, ghi chú trợ lý vẫn trò chuyện như thường",
      !/rsa-toggle" checked/.test(h) && h.includes(vi["resonance.a1_off_note"]));
check("chưa có mục tiêu: nói rõ", h.includes(vi["resonance.a1_no_goals"]));
h = RA.panelHtml(on, "ready", []);
check("bật, phiên dùng được: công tắc chọn, không có nút mở phiên mới",
      /class="rsa-toggle" checked/.test(h) && h.includes(vi["resonance.a1_on_note"]) && !h.includes("rsa-new-session"));
h = RA.panelHtml(on, "needs_new_session", []);
check("P2: bật trong phiên mở trước lúc cấp mã: nói rõ và có nút Mở cuộc trò chuyện mới",
      h.includes(vi["resonance.a1_needs_new_session"]) && h.includes("rsa-new-session")
      && h.includes(vi["resonance.a1_open_new"]) && !h.includes(vi["resonance.a1_on_note"]));
check("P2: phiên cần mở mới nhưng công tắc tắt thì không đưa nút (chưa có gì để dùng)",
      !RA.panelHtml(off, "needs_new_session", []).includes("rsa-new-session"));
h = RA.panelHtml(Object.assign({}, on, { status: "missing" }), null, []);
check("file trợ lý mất: công tắc khoá, hai nút xác nhận (đúng trợ lý cũ / trợ lý mới)",
      /rsa-toggle"[^>]*disabled/.test(h) && h.includes(vi["resonance.a1_missing"])
      && /data-same="1"/.test(h) && /data-same="0"/.test(h));
h = RA.panelHtml(Object.assign({}, on, { support: { goal: false, chat_output: false } }), "ready", []);
check("engine chưa mang khoá lượt (Grok, Antigravity): cảnh báo rõ", h.includes(vi["resonance.a1_engine_no_goal"]));
h = RA.panelHtml(Object.assign({}, on, { support: { goal: true, chat_output: false } }), "ready", []);
check("engine lập được nhưng chưa nhận bản chat (Codex, API): ghi chú tương ứng",
      h.includes(vi["resonance.a1_engine_no_chat_output"]) && !h.includes(vi["resonance.a1_engine_no_goal"]));
h = RA.panelHtml(null, null, []);
check("chưa tải được hay chưa đăng ký: công tắc tắt, không lỗi", !/rsa-toggle" checked/.test(h)
      && h.includes(vi["resonance.a1_off_note"]));
h = RA.panelHtml(on, "ready", [{ goal_id: "g_1" }, { goal_id: 'g"><b>x' }, null]);
check("khung Mục tiêu của trợ lý: mỗi mục tiêu một thẻ (thẻ của chat-resonance), id được thoát ký tự",
      h.includes(vi["resonance.a1_goals_title"]) && /class="rs-card rsa-card" data-goal="g_1"/.test(h)
      && !h.includes('<b>x') && (h.match(/rsa-card/g) || []).length === 2);
check("không có phần trăm tiến độ giả trong khối", !/%/.test(RA.panelHtml(on, "ready", [])));

// ───────────── trang Cài đặt ─────────────
const data = {
  agents: [on, Object.assign({}, off, { slug: "kiem-tra", name: "Kiểm <tra>", agent_key: "ag_2", goals_open: 2 }),
    { slug: "moi", name: "Mới", status: "unregistered", enabled: false, agent_key: null, support: { goal: false } },
    Object.assign({}, on, { slug: "mat", name: "Mất", agent_key: "ag_3", status: "missing" })],
  orphans: [{ slug: "da-doi-ten", agent_key: "ag_9", status: "missing", goals_open: 1 }],
  unassigned: 1, legacy_brain_switch: true,
};
const goals = [{ goal_id: "g_old", revision: 3, understanding: "Mục tiêu <cũ>" }];
const s = RA.settingsHtml(data, goals);
check("cài đặt: mỗi trợ lý một công tắc đúng trạng thái",
      /data-slug="viet-bai" checked/.test(s) && /data-slug="kiem-tra">/.test(s) && /data-slug="moi">/.test(s)
      && /data-slug="mat"[^>]*disabled/.test(s));
check("cài đặt: chống chèn HTML từ tên trợ lý và cách hiểu", !s.includes("<tra>") && !s.includes("<cũ>"));
check("cài đặt: số mục tiêu đang mở, cảnh báo engine và mất file",
      s.includes("2 mục tiêu đang mở") && s.includes(vi["resonance.a1_engine_short"]) && s.includes(vi["resonance.a1_missing_short"]));
check("cài đặt: trợ lý mất file vẫn hiện để thấy mục tiêu bị kẹt", s.includes("da-doi-ten"));
check("Chờ gán: mỗi mục tiêu một ô chọn, chỉ liệt kê trợ lý đang hoạt động có mã, mang đúng revision",
      s.includes(vi["resonance.a1_unassigned_title"]) && /data-goal="g_old" data-rev="3"/.test(s)
      && /value="ag_1"/.test(s) && /value="ag_2"/.test(s) && !/value="ag_3"/.test(s) && !/value="null"/.test(s));
check("cài đặt: ghi chú công tắc brain cũ không còn dùng", s.includes(vi["resonance.a1_legacy_note"]));
check("cài đặt: không có mục tiêu chờ gán thì không vẽ mục đó",
      !RA.settingsHtml(data, []).includes(vi["resonance.a1_unassigned_title"]));
check("brain chưa có trợ lý: chỉ đường tạo ở trang Cộng sự", RA.settingsHtml({ agents: [] }, []).includes(vi["resonance.a1_settings_empty"]));

// ───────────── dây nối ─────────────
check("API công tắc đi đúng route chủ dự án, kèm phiên đang mở",
      SRC.includes("/resonance/agents/toggle") && /session_id: currentSession()/.test(SRC) && SRC.includes("/goals/\" + q("));
check("không còn đọc hay ghi công tắc brain cũ ở giao diện", !CR.includes("/resonance/settings") && !SRC.includes("/resonance/settings")
      && !HTML.includes('id="resonanceEnabled"'));
check("trang Cài đặt có chỗ cho danh sách trợ lý, nạp resonance-agent.js sau chat-resonance.js",
      HTML.includes('id="resonanceAgents"') && HTML.indexOf("/static/chat-resonance.js") > 0
      && HTML.indexOf("/static/chat-resonance.js") < HTML.indexOf("/static/resonance-agent.js"));
check("trang Cộng sự: khối Cộng hưởng đứng đầu cột phải của trợ lý, gắn lại khi mở phiên",
      WS.includes('id="wsResonance"') && (WS.match(/ganCongHuong\(/g) || []).length >= 3
      && /onNewSession: function \(\) \{ var x = dangChon\(\); return x \? moPhien\(x, true\)/.test(WS));
check("thẻ mục tiêu biết các lý do chặn mới của A1",
      ["unassigned", "agent_off", "agent_missing", "agent_retired", "agent_changed"].every(function (r) {
        return RS.stateKey({ status: "active", block_reason: r }) === "resonance.st_" + r; }));

// ───────────── từ điển ─────────────
const keys = Object.keys(vi).filter(function (k) { return /^resonance\.(a1_|st_agent|st_unassigned)/.test(k); });
check("có khoá A1 trong từ điển", keys.length >= 30);
check("mọi khoá A1 có cả tiếng Anh", keys.every(function (k) { return typeof en[k] === "string" && en[k].length; }),
      keys.filter(function (k) { return !en[k]; }).join(","));
const used = (SRC.match(/resonance\.[a-z0-9_]+/g) || []).filter(function (k) { return !/\.js$/.test(k); });
check("mọi khoá resonance-agent.js dùng đều có trong vi.json", used.every(function (k) { return k in vi; }),
      used.filter(function (k) { return !(k in vi); }).join(","));
check("không có em dash trong chuỗi mới", keys.every(function (k) { return !/\u2014/.test(vi[k] + en[k]); })
      && !/\u2014/.test(SRC));

// ───────────── P2 review tích hợp: trạng thái phiên đọc từ host mỗi lần mở, tải lại, đổi phiên ─────────────
// fetch giả trả lời như host: phiên "cu" (mở trước lúc cấp mã) là needs_new_session, phiên "moi" là ready.
const calls = [];
let current = "cu";
global.window = { JavisSessions: { brain: function () { return "brain"; }, current: function () { return current; } } };
global.fetch = function (url) {
  calls.push(url);
  const m = /session_id=([^&]+)/.exec(url);
  const body = url.indexOf("/resonance/agents") === 0
    ? { agents: [{ slug: "viet-bai", agent_key: "ag_moi", enabled: true, status: "active", support: { goal: true } }],
        session: m ? (m[1] === "moi" ? "ready" : "needs_new_session") : null }
    : { goals: [] };
  return Promise.resolve({ status: 200, json: function () { return Promise.resolve(body); } });
};
const host = { innerHTML: "", isConnected: true, querySelector: function () { return null; },
  querySelectorAll: function () { return []; } };

(async function () {
  await RA.mount(host, { slug: "viet-bai", sessionId: "cu" });
  check("P2 mở trang ở phiên cũ: hỏi host kèm đúng trợ lý và phiên", calls.some(function (u) {
    return u.indexOf("/resonance/agents?") === 0 && u.indexOf("slug=viet-bai") > 0 && u.indexOf("session_id=cu") > 0; }));
  check("P2 phiên cũ: có câu giải thích và nút mở cuộc mới", host.innerHTML.includes("rsa-new-session")
        && host.innerHTML.includes(vi["resonance.a1_needs_new_session"]));
  await RA.mount(host, { slug: "viet-bai", sessionId: "cu" });              // F5 / gắn lại khối
  check("P2 tải lại trang: vẫn còn nút (không mất theo biến tạm)", host.innerHTML.includes("rsa-new-session"));
  current = "moi";
  await RA.refresh();                                                       // người dùng mở cuộc mới
  check("P2 đổi sang phiên mới: host nói dùng được, hết nút, hiện trạng thái bật",
        !host.innerHTML.includes("rsa-new-session") && host.innerHTML.includes(vi["resonance.a1_on_note"]));
  current = "cu";
  await RA.mount(host, { slug: "viet-bai", sessionId: "cu" });              // bật ở Cài đặt rồi quay lại phiên cũ
  check("P2 quay lại phiên cũ: nút trở lại", host.innerHTML.includes("rsa-new-session"));
  check("P2 không tự gán ready ở phía trình duyệt", !/refresh\("ready"\)/.test(SRC) && !/S\.session\b/.test(SRC));

  if (fails) { console.log("\n" + fails + " FAIL"); process.exit(1); }
  console.log("\nOK");
})();
