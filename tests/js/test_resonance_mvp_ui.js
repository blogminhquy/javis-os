// Resonance M4: thẻ "Javis đang hướng tới" (dashboard/chat-resonance.js).
//
//     python tests/run.py --js resonance_mvp_ui -v
//
// Hàm thuần chạy dưới node: bóc khối JAVIS_RESONANCE, HTML của thẻ từ trạng thái GET /goals/{id}, và request của
// từng nút. Nút phải gửi revision, artifact_ref, criterion_id lấy TỪ TRẠNG THÁI ĐÃ TẢI, không tự điền.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const RS = require(path.join(ROOT, "dashboard", "chat-resonance.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// ───────────── bóc khối ─────────────
const raw = 'Javis đã lập mục tiêu.\n<!-- JAVIS_RESONANCE: {"goal_id": "g_abc", "revision": 2, "report": "outbox:7"} -->';
const t1 = RS.tach(raw);
check("bóc khối: chữ còn lại sạch, không lộ khối", t1.clean === "Javis đã lập mục tiêu." && !/JAVIS_RESONANCE/.test(t1.clean));
check("bóc khối: lấy đúng goal_id, revision, khoá báo cáo",
      t1.cards.length === 1 && t1.cards[0].goal_id === "g_abc" && t1.cards[0].revision === 2 && t1.cards[0].report === "outbox:7");
const t2 = RS.tach("Chữ <!-- JAVIS_RESONANCE: {hỏng -->");
check("khối JSON hỏng: vẫn bóc khỏi chữ, không tạo thẻ", t2.clean === "Chữ" && t2.cards.length === 0);
check("không có khối: giữ nguyên chữ", RS.tach("Chào bạn").clean === "Chào bạn" && RS.tach("Chào bạn").cards.length === 0);
const t3 = RS.tach('a <!-- JAVIS_VIEC: {"kind":"task"} --> <!-- JAVIS_RESONANCE: {"goal_id":"g1","revision":1} -->');
check("chỉ bóc khối của mình, khối khác (JAVIS_VIEC) để module của nó lo", /JAVIS_VIEC/.test(t3.clean) && t3.cards.length === 1);

// ───────────── HTML của thẻ ─────────────
const waiting = {
  goal_id: "g_abc", revision: 2, status: "active", run_state: "waiting", block_reason: "human_confirmation",
  paused: false, understanding: "Ghi chú <b>kế hoạch</b>", fit: "unknown", artifact_ref: "a".repeat(64),
  deliverable: "Inbox/ke-hoach.md", assumptions: ["Dùng thư mục Inbox"], calls_used: 1, budget_calls: 4,
  next_wake: null, timeline: [{ kind: "work", status: "succeeded", at: 1800000000 }],
  criteria: [
    { id: "c1", description: "Có đủ ba việc", evaluator: "artifact_contract", verdict: "met", reason: "đạt" },
    { id: "c2", description: "Bạn duyệt ghi chú", evaluator: "human_confirmation", verdict: "unknown", reason: "chờ" }],
};
const h = RS.viewHtml(waiting);
check("thẻ: có tiêu đề, tình trạng chờ duyệt, cách hiểu", h.includes(vi["resonance.card_title"])
      && h.includes(vi["resonance.st_human_confirmation"]) && h.includes("kế hoạch"));
check("thẻ: chống chèn HTML từ dữ liệu (cách hiểu do model viết)", !h.includes("<b>kế hoạch</b>") && h.includes("&lt;b&gt;"));
check("thẻ: nút Đạt yêu cầu / Cần chỉnh CHỈ cho tiêu chí người dùng duyệt (c2), không cho tiêu chí host kiểm (c1)",
      /data-act="out_ok" data-crit="c2"/.test(h) && /data-act="out_no" data-crit="c2"/.test(h) && !/data-crit="c1"/.test(h));
check("thẻ: nút Đúng ý / Chưa đúng ý tách riêng với nút sản phẩm",
      h.includes('data-act="fit_ok"') && h.includes('data-act="fit_no"'));
check("thẻ: có Tạm dừng và Huỷ, có sản phẩm, có lịch sử", h.includes('data-act="pause"') && h.includes('data-act="cancel"')
      && h.includes("Inbox/ke-hoach.md") && h.includes("rs-timeline"));
check("thẻ: không có phần trăm tiến độ giả", !/%/.test(h.replace(/&#\d+;/g, "")));
const noArtifact = RS.viewHtml(Object.assign({}, waiting, { artifact_ref: "" }));
check("chưa có sản phẩm: không có nút Đạt yêu cầu (không có gì để duyệt)", !noArtifact.includes('data-act="out_ok"'));
const done = RS.viewHtml(Object.assign({}, waiting, { status: "succeeded" }));
check("mục tiêu đã xong: không còn nút thao tác", !/class="rs-act/.test(done) && done.includes(vi["resonance.st_succeeded"]));
const paused = RS.viewHtml(Object.assign({}, waiting, { paused: true }));
check("đang tạm dừng: nút Tiếp tục thay cho Tạm dừng", paused.includes('data-act="resume"') && !paused.includes('data-act="pause"'));
const guard = RS.viewHtml(Object.assign({}, waiting, { block_reason: "guard" }));
check("dừng vì guard: có nút Đã sửa, chạy lại", guard.includes(vi["resonance.btn_reopen"]) && guard.includes(vi["resonance.st_guard"]));

// ───────────── request của từng nút ─────────────
const rOk = RS.requestFor("out_ok", waiting, "c2");
check("Đạt yêu cầu: gửi đúng revision, criterion, artifact_ref của bản ĐANG HIỆN",
      rOk.url === "/goals/g_abc/feedback" && rOk.body.kind === "outcome_accepted" && rOk.body.expected_revision === 2
      && rOk.body.criterion_id === "c2" && rOk.body.artifact_ref === "a".repeat(64) && rOk.body.idempotency_key);
const rFit = RS.requestFor("fit_no", waiting);
check("Chưa đúng ý: goal_fit_rejected với revision đang hiện, không mang criterion",
      rFit.body.kind === "goal_fit_rejected" && rFit.body.expected_revision === 2 && !("criterion_id" in rFit.body));
const rOld = RS.requestFor("fit_ok", Object.assign({}, waiting, { revision: 1 }));
check("thẻ cũ gửi đúng revision CŨ của nó (server sẽ trả 409), không tự nâng lên revision mới",
      rOld.body.expected_revision === 1);
const rCmd = RS.requestFor("pause", waiting);
check("Tạm dừng: gửi lệnh vào /commands", rCmd.url === "/goals/g_abc/commands" && rCmd.body.command === "pause");
check("khoá chống bấm trùng đổi theo bản sản phẩm (bản mới bấm lại được)",
      RS.requestFor("out_ok", waiting, "c2").body.idempotency_key
      !== RS.requestFor("out_ok", Object.assign({}, waiting, { artifact_ref: "b".repeat(64) }), "c2").body.idempotency_key);

// ───────────── từ điển: mọi khoá trạng thái đều có ở cả vi và en ─────────────
const states = ["human_confirmation", "fit_rejected", "guard", "guard_unknown", "budget", "discovery_done", "healthy",
  "scheduled", "feature_off", "engine_blocked"].map((r) => RS.stateKey({ status: "active", block_reason: r }))
  .concat(["succeeded", "cancelled", "failed"].map((s) => RS.stateKey({ status: s })),
          [RS.stateKey({ status: "active", paused: true }), RS.stateKey({ status: "active", run_state: "running" }),
           RS.stateKey({ status: "active", run_state: "blocked" }), RS.stateKey({ status: "active" })]);
check("mọi khoá trạng thái có trong vi.json và en.json", states.every((k) => k in vi && k in en),
      states.filter((k) => !(k in vi && k in en)).join(", "));
check("chuỗi giao diện không xưng anh/em với người dùng",
      Object.keys(vi).filter((k) => k.startsWith("resonance.")).every((k) => !/(^|\s)(anh|em)(\s|$)/i.test(vi[k])));

// ───────────── nối vào dashboard ─────────────
const app = fs.readFileSync(path.join(ROOT, "dashboard", "app.js"), "latin1");
check("app.js: bóc khối và vẽ thẻ trong appendJavisMessage",
      app.includes("window.JavisResonance.tach(tv.clean)") && app.includes("window.JavisResonance.ve(div, c)"));
check("app.js: giọng đọc bỏ khối thẻ (bóc trước dòng _doc, giữ nguyên dòng canary của chat-viec)",
      app.includes('if (window.JavisResonance) data.content = window.JavisResonance.tach(data.content || "").clean;'));
const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
check("index.html nạp chat-resonance.js sau chat-viec.js",
      html.indexOf("/static/chat-resonance.js") > html.indexOf("/static/chat-viec.js") && html.includes("/static/chat-resonance.js"));
check("index.html có công tắc bật theo brain, nhãn qua data-i18n", html.includes('id="resonanceEnabled"')
      && html.includes('data-i18n="resonance.settings_on"'));
const css = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
check("style.css có kiểu cho thẻ và dùng biến màu có thật", css.includes(".rs-card {") && !/var\(--surface\)/.test(css));

console.log(fails ? `\n${fails} FAIL` : "\nOK");
process.exit(fails ? 1 : 0);
