// 0.142.0: chat nhóm không im lặng (trạng thái từng lượt, Thử lại) và @ đúng người theo agent_key kể cả trùng tên.
//
//     python tests/run.py --js team_chat_0142 -v
"use strict";
const fs = require("fs");
const { napTruoc, coNap } = require("./_thu_tu_nap");   // load order that understands lazy groups (0.417.0)
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const appJs = fs.readFileSync(path.join(ROOT, "dashboard", "app.js"), "latin1");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// ───────────── @ theo agent_key, kể cả trùng tên ─────────────
const mem = [
  { agent_key: "ag_one", slug: "one", name: "One", status: "active" },
  { agent_key: "ag_one2", slug: "one-2", name: "One", status: "active" },
  { agent_key: "ag_lan", slug: "lan", name: "Lan", status: "active" },
];
let sc = TM.mentionScan("@One giúp với", mem, []);
check("trùng tên, gõ tay không chọn: không gọi ai, báo mơ hồ", sc.keys.length === 0 && sc.ambiguous.join() === "One",
  JSON.stringify(sc));
sc = TM.mentionScan("@One giúp với", mem, ["ag_one2"]);
check("trùng tên, đã chọn trong gợi ý: gọi đúng agent_key đã chọn", sc.keys.join() === "ag_one2" && !sc.ambiguous.length,
  JSON.stringify(sc));
sc = TM.mentionScan("@One và @One cùng xem", mem, ["ag_one2", "ag_one"]);
check("hai @ trùng tên, chọn cả hai: đủ hai người theo thứ tự chọn", sc.keys.join() === "ag_one2,ag_one", JSON.stringify(sc));
sc = TM.mentionScan("@one-2 xem", mem, []);
check("gõ slug riêng: không mơ hồ", sc.keys.join() === "ag_one2" && !sc.ambiguous.length, JSON.stringify(sc));
sc = TM.mentionScan("@Lan ơi", mem, []);
check("tên không trùng: như cũ", sc.keys.join() === "ag_lan");
const hint = TM.composerHint({ mentions: [], ambiguous: ["One"], cap: 3 });
check("khung soạn chặn gửi khi @ mơ hồ, nói rõ tên", hint.ok === false && hint.text.includes("One"), JSON.stringify(hint));

// ───────────── trạng thái lượt trả lời ─────────────
const team = [{ agent_key: "ag_lan", slug: "lan", name: "Lan", status: "active" },
  { agent_key: "ag_minh", slug: "minh", name: "Minh <b>", status: "active" }];
const ctx = { members: team, authors: {}, retrying: {} };
const msg = { id: 7, author_kind: "owner", content: "Chào", meta: {}, replies: [
  { agent_key: "ag_lan", status: "queued", reason: "" },
  { agent_key: "ag_minh", status: "error", reason: "engine_unavailable", detail: "model việc nền <x>" }] };
let h = TM.messageHtml(msg, ctx);
check("tin của chủ hiện trạng thái từng người: đang chờ", h.includes("tm-reply-queued") && h.includes(vi["teams.reply.queued"]), h);
check("lỗi hiện lý do bằng lời thường và chi tiết đã escape", h.includes(vi["teams.reply.why.engine_unavailable"])
  && h.includes("model việc nền &lt;x&gt;") && h.includes("Minh &lt;b&gt;") && !h.includes("<x>"), h);
check("lỗi có nút Thử lại gắn đúng tin và agent_key", /data-retry="7" data-retry-key="ag_minh"/.test(h), h);
h = TM.replyStatusHtml({ id: 7, replies: [{ agent_key: "ag_lan", status: "running", reason: "answering" }] }, ctx);
check("đang trả lời", h.includes("tm-reply-answering") && h.includes(vi["teams.reply.answering"]), h);
h = TM.replyStatusHtml({ id: 7, replies: [{ agent_key: "ag_lan", status: "done", result_msg_id: 9 }] }, ctx);
check("đã xong thì không thêm dòng (câu trả lời nằm ngay dưới)", h === "", h);
h = TM.replyStatusHtml({ id: 7, replies: [{ agent_key: "ag_lan", status: "error", reason: "member_left" }] }, ctx);
check("trợ lý đã rời: không có Thử lại", h.includes(vi["teams.reply.why.member_left"]) && !h.includes("data-retry"), h);
h = TM.replyStatusHtml({ id: 7, replies: [{ agent_key: "ag_lan", status: "error", reason: "restart" }] },
  Object.assign({}, ctx, { retrying: { "7|ag_lan": true } }));
check("đang gửi Thử lại: nút khoá, chữ đổi", /data-retry-key="ag_lan" disabled/.test(h) && h.includes(vi["teams.reply.retrying"]), h);
h = TM.replyStatusHtml({ id: 7, replies: [{ agent_key: "ag_lan", status: "error", reason: "lạ" }] }, ctx);
check("lý do lạ: Không rõ lý do", h.includes(vi["teams.reply.why.unknown"]), h);
check("tin của trợ lý không vẽ trạng thái lượt", !TM.messageHtml({ id: 8, author_kind: "agent", author_ref: "ag_lan",
  content: "x", meta: {}, replies: msg.replies }, ctx).includes("tm-replies"));

// ───────────── hộp chọn thành viên kiểu Zalo ─────────────
const TP = require(path.join(ROOT, "dashboard", "team-picker.js"));
TP.setStrings(vi);
const roster = [
  { slug: "ban-hang", name: "Javis Vũ Zalo", role: "Trợ lý chăm khách", tags: ["Bán hàng"], tag_keys: ["bán hàng"] },
  { slug: "coach", name: "Coach Mục Tiêu & Kỷ Luật", role: "Huấn luyện", tags: ["Cá nhân"], tag_keys: ["cá nhân"] },
  { slug: "viet", name: "Người Viết <i>", role: "Viết bài", tags: ["Bán hàng", "Nội dung"], tag_keys: ["bán hàng", "nội dung"] },
  { slug: "cu", name: "Đã nghỉ", status: "retired", tags: ["Bán hàng"] },
];
check("bỏ dấu: 'muc tieu' tìm ra 'Mục Tiêu', 'đ' thành 'd'", TP.fold("Mục Tiêu Đạt") === "muc tieu dat");
let st = { mode: "create", query: "muc tieu", tag: "", selected: [], leader: "", leaderTouched: false };
check("tìm không dấu theo tên", TP.visible(roster, st).map(function (a) { return a.slug; }).join() === "coach");
st.query = "viet bai";
check("tìm không dấu theo vai", TP.visible(roster, st).map(function (a) { return a.slug; }).join() === "viet");
const tags = TP.tagsOf(roster);
check("chip tag lấy từ tag của trợ lý (trợ lý đã nghỉ không tính), đếm đúng",
  tags[0].label === "Bán hàng" && tags[0].count === 2 && tags.length === 3, JSON.stringify(tags));
st = TP.toggle({ mode: "create", query: "", tag: "", selected: [], leader: "", leaderTouched: false }, "coach");
st = TP.toggle(st, "viet");
check("chọn người đầu tiên: tự thành Điều phối", st.leader === "coach" && st.selected.join() === "coach,viet");
st = Object.assign({}, st, { tag: "bán hàng" });
check("đổi bộ lọc tag không mất người đã chọn", st.selected.join() === "coach,viet"
  && TP.visible(roster, st).map(function (a) { return a.slug; }).join() === "ban-hang,viet");
let html = TP.html(st, roster);
check("người đã chọn vẫn hiện thành chip dù bị lọc khỏi danh sách", html.includes("Coach Mục Tiêu &amp; Kỷ Luật")
  && /tmp-sel[\s\S]*data-pick-toggle="coach"/.test(html), html);
// Đối chiếu goal-claude-v2: Điều phối chọn NGAY trên chip người đã chọn (không còn ô select riêng dưới danh sách).
check("Điều phối chỉ có người đã chọn, chọn ngay trên chip", /data-pick-leader="coach" aria-pressed="true"/.test(html)
  && /data-pick-leader="viet" aria-pressed="false"/.test(html) && !/data-pick-leader="ban-hang"/.test(html)
  && !html.includes("tmp-leader-pick"), html);
check("người tạo hiện 'Bạn · Người tạo nhóm/quản lý', tách khỏi Điều phối", html.includes("tmp-owner")
  && html.includes(vi["teams.pick.you_role"]) && !/tmp-owner[^>]*data-pick/.test(html)
  && !/data-pick-leader="[^"]*"[^>]*>[^<]*Bạn/.test(html));
check("tên, vai escape; trợ lý đã nghỉ không hiện", html.includes("Người Viết &lt;i&gt;") && !html.includes("Đã nghỉ"));
check("footer cố định có số đã chọn, Huỷ, Tạo nhóm", /tmp-foot-box[\s\S]*Đã chọn 2[\s\S]*tmp-cancel[\s\S]*tmp-submit/.test(html), html);
st = TP.toggle(st, "coach");
check("còn đúng một người: người đó là Điều phối (mặc định rõ ràng)", st.leader === "viet" && st.selected.join() === "viet");
check("tên trống: ghép tên thành viên như Zalo", TP.autoName({ selected: ["coach", "viet"] }, roster) === "Coach Mục Tiêu & Kỷ Luật, Người Viết <i>");
check("chưa chọn ai: không bấm Tạo được", !TP.canSubmit({ selected: [] }) && TP.canSubmit({ selected: ["coach"] })
  && !TP.canSubmit({ selected: ["coach"], saving: true }));
html = TP.html({ mode: "add", query: "", tag: "", selected: [], exclude: ["coach"] }, roster);
// Đối chiếu goal-claude-v2: người đã trong nhóm HIỆN với nhãn "Đã tham gia" (ô chọn khoá), không bị ẩn.
check("thêm thành viên: không có ô tên, không có 'Bạn', người đã trong nhóm hiện Đã tham gia và khoá", !html.includes("tmp-name-input")
  && !html.includes("tmp-owner") && /data-pick-slug="coach" checked disabled/.test(html) && html.includes(vi["teams.pick.joined"])
  && html.includes('data-pick-slug="viet"'));
html = TP.html({ mode: "create", query: "", tag: "", selected: ["coach"], leader: "coach", name: "Nhóm <x>", error: "Thiếu <b>" }, roster);
check("lỗi khi tạo: form giữ nguyên tên và lựa chọn, lỗi hiện trong hộp", html.includes('value="Nhóm &lt;x&gt;"')
  && html.includes("tmp-error") && html.includes("Thiếu &lt;b&gt;") && /data-pick-slug="coach" checked/.test(html));
check("hộp là dialog có nhãn, đóng được bằng nút có nhãn", /role="dialog" aria-modal="true" aria-labelledby="tmp-title"/.test(html)
  && html.includes('aria-label="' + vi["teams.pick.close"] + '"'));
check("điện thoại: hộp thành màn đầy đủ, footer chừa vùng an toàn", /@media \(max-width: 640px\) \{[\s\S]*\.tmp-dialog \{[^}]*height: 100dvh/.test(css)
  && /\.tmp-foot \{ padding-bottom: calc\(12px \+ env\(safe-area-inset-bottom/.test(css));
check("chữ hộp chọn 16px, vùng chạm 44px", /\.tmp-dialog \{[^}]*font-size: 16px/.test(css) && /\.tmp-foot \.ws-btn \{ min-height: 44px/.test(css));
const indexHtml = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
check("team-picker.js nạp trước teams.js", napTruoc("team-picker.js", "teams.js", indexHtml));

// ───────────── tab Công việc ở trang Cộng sự ─────────────
const AJ = require(path.join(ROOT, "dashboard", "agent-jobs.js"));
AJ.setStrings(vi);
const data = { ok: true, board: "off", max_workers: 2, errors: [],
  counts: { running: 1, waiting: 2, needs_you: 1, done: 1 },
  jobs: [
    { id: "team:t1", source: "team", source_label: "Ra mắt <x>", title: "Viết thông cáo", bucket: "needs_you", roles: ["helper"],
      progress: { done: 1, total: 3 }, reason: "Trợ lý gặp lỗi <b>", open: { kind: "team", team_id: "tm_1", task_id: "t1" },
      cancel: { kind: "team", team_id: "tm_1", task_id: "t1" } },
    { id: "team:t2", source: "team", source_label: "Ra mắt", title: "Việc chung", bucket: "running", roles: ["coordinator"],
      progress: { done: 0, total: 2 }, open: { kind: "team", team_id: "tm_1", task_id: "t2" }, cancel: null },
    { id: "team:t3", source: "team", source_label: "Ra mắt", title: "Chờ", bucket: "waiting", roles: ["assignee"], queue_pos: 2,
      open: { kind: "team", team_id: "tm_1", task_id: "t3" }, cancel: { kind: "team", team_id: "tm_1", task_id: "t3" } },
    { id: "kanban:k1", source: "chat", title: "Email", bucket: "waiting", roles: ["assignee"], board_off: true,
      open: { kind: "chat", session_id: "s1" }, cancel: { kind: "kanban", task_id: "k1" } },
    { id: "goal:g1", source: "auto", title: "Bản tóm tắt", bucket: "done", roles: ["owner"], result: "", failed: true,
      open: { kind: "chat", session_id: "s2", goal_id: "g1" }, cancel: null }] };
let jh = AJ.html(data, { name: "Minh" });
check("bốn trạng thái có chip đếm: Đang làm, Đang chờ, Cần bạn, Đã xong", ["ajobs.b.running", "ajobs.b.waiting",
  "ajobs.b.needs_you", "ajobs.b.done"].every(function (k) { return jh.includes(vi[k]); }) && /<option value="waiting">[^<]*\(2\)<\/option>/.test(jh), jh);
check("có nút Giao việc", jh.includes("aj-assign-open") && jh.includes(vi["ajobs.assign"]));
check("Cần bạn đứng đầu, lý do hiện và đã escape", jh.indexOf('aj-sec-h">' + vi["ajobs.b.needs_you"]) < jh.indexOf('aj-sec-h">' + vi["ajobs.b.running"])
  && jh.includes("Trợ lý gặp lỗi &lt;b&gt;"), jh);
check("nguồn nhóm có tên nhóm, vai trợ lý trong việc", jh.includes("Team Ra mắt &lt;x&gt;") && jh.includes(vi["ajobs.role.helper"])
  && jh.includes(vi["ajobs.role.coordinator"]));
check("tiến độ là số bước thật, vị trí trong hàng nhóm, hàng chờ trung thực khi AI tự vận hành tắt",
  jh.includes("1/3") && jh.includes(vi["ajobs.queue_pos"].replace("{n}", "2")) && jh.includes(vi["ajobs.board_off"]));
check("mỗi việc có Mở; chỉ việc huỷ được mới có Huỷ", /data-aj-open="team:t2"/.test(jh) && !/data-aj-cancel="team:t2"/.test(jh)
  && /data-aj-cancel="kanban:k1"/.test(jh));
check("chân trang nói rõ trần chạy và AI tự vận hành tắt", jh.includes(vi["ajobs.foot_off"]));
jh = AJ.html(data, { filter: "waiting" });
check("lọc theo trạng thái chỉ còn đúng ngăn", jh.includes("Chờ") && jh.includes("Email") && !jh.includes("Viết thông cáo"));
jh = AJ.html(data, { assignOpen: true, name: "Minh <i>", draft: "Soạn <b>", assignError: "Lỗi" });
check("form Giao việc giữ chữ đang gõ, tên trợ lý escape, lỗi hiện rõ", jh.includes("Soạn &lt;b&gt;") && jh.includes("Minh &lt;i&gt;")
  && jh.includes("aj-err") && jh.includes("aj-assign-next"));
check("chưa có việc: lời gợi ý", AJ.html({ jobs: [], counts: {}, errors: [] }, {}).includes(vi["ajobs.empty"]));
check("lỗi tải: có Thử lại", AJ.html(null, { error: true }).includes("aj-reload"));
const ws = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");
check("trang Cộng sự: Lịch sử, Công việc, Cài đặt; tài liệu vẫn có nút riêng", /var TAB_PHAI = \["lichsu", "viec", "cai"\]/.test(ws)
  && ws.includes('id="wsFiles"') && ws.includes("JavisAgentJobs.mount"));
check("mở việc nhóm đi đúng nhóm và lọc đúng việc", /JavisTeams\.open\(teamId, taskId\)/.test(ws)
  && /function open\(teamId, taskId\)/.test(fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8")));
// Owner, 2026-10-15: 16px was too big for the narrow column; 13px text, 44px buttons on touch screens.
check("Work tab text 13px, buttons 44px on touch screens", /\.aj \{[^}]*font-size: 13px/.test(css)
  && /@media \(pointer: coarse\) \{[^}]*\.aj \.aj-acts \.ws-btn[^}]*min-height: 44px/.test(css));

// ───────────── Auto (trước là Cộng hưởng) ─────────────
const RAX = require(path.join(ROOT, "dashboard", "resonance-agent.js"));
check("tên hiển thị là Auto ở cả hai thứ tiếng, mô tả đúng câu chủ chốt",
  vi["resonance.a1_title"] === "Auto" && en["resonance.a1_title"] === "Auto" && vi["resonance.t0_state_on"] === "Auto: Bật"
  && vi["resonance.auto_desc"] === "Tự làm tiếp mục tiêu được giao và báo kết quả.");
check("không còn chữ 'Cộng hưởng' ở nhãn hiển thị resonance.* / teams.*",
  Object.keys(vi).filter(function (k) { return /^(resonance|teams|ws|ajobs)\./.test(k) && /Cộng hưởng/.test(vi[k]); }).length === 0);
const wsJs = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");
check("menu ba chấm có mục Auto dùng chung hàm bật tắt với công tắc trên thẻ",
  /nutMenu\("zap", t\(autoOn \? "resonance\.auto_menu_on" : "resonance\.auto_menu_off"\)/.test(wsJs)
  && /ma\.onclick = function \(\) \{ dongMenu\(\); doiAuto\(item\.slug, !autoOn\); \}/.test(wsJs)
  && /box\.checked = !wantOn;[\s\S]{0,160}doiAuto\(box\.dataset\.rs, wantOn\)/.test(wsJs));
// 0.175.0 (chủ repo 16/10/2026: "nút Auto quá to che mất hết các thông tin khác"): Auto TẮT không vẽ trên thẻ (bật ở menu ba
// chấm); Auto BẬT là nhãn nhỏ góc dưới phải, cùng dòng trạng thái; vẫn bật cam, tắt xám; vùng chạm 44px trên cảm ứng bằng lớp
// trong suốt chứ không phóng to nhãn.
// 0.190.0 (chủ repo 16/10/2026: "mất nút bật tắt auto của anh rồi, thời gian phải cùng hàng với nút bật tắt auto và nhỏ
// thôi"): công tắc có lại trên MỌI thẻ (tắt xám, bật cam), chung một cụm nhỏ với giờ ở góc dưới phải; ba chấm lên góc trên.
check("0.190.0: Auto trên mọi thẻ, cùng cụm với giờ ở góc dưới phải, chạm 44px trên điện thoại",
  !/\.ws-auto:not\(\.is-on\):not\(\.is-saving\) \{ display: none; \}/.test(css)
  && /\.ws-item-end \{ position: absolute; right: 8px; bottom: 8px; display: flex;/.test(css)
  && /\.ws-item-wrap\.has-end > \.ws-item-more \{ top: 6px; transform: none; \}/.test(css)
  && /\.ws-item-end > \.ws-auto\.is-on \{ color: var\(--accent-ink/.test(css)
  && /\.ws-auto \.toggle-sm input:checked \+ span \{ background: var\(--accent\)/.test(css)
  && /\.ws-auto \.toggle-sm span \{ background: var\(--bg3\)/.test(css)
  && /\.ws-item-end > \.ws-auto::after, \.ws-item-end > \.ws-rs-confirm::after \{ content: ""; position: absolute; inset: -12px -6px; \}/.test(css));
const ph = RAX.panelHtml({ slug: "a", status: "active", enabled: true }, "ready", [], []);
check("bảng trợ lý: mô tả Auto và câu Auto không phải Toàn quyền", ph.includes(vi["resonance.auto_desc"])
  && ph.includes(vi["resonance.auto_not_full"]));
check("hỏi lại khi tắt: nói rõ không huỷ việc, vẫn chat và nhận việc trực tiếp",
  /không bị huỷ/.test(vi["resonance.t0_off_confirm"]) && /nhận việc trực tiếp/.test(vi["resonance.t0_off_confirm"]));

// review #1: gắn lại tab Công việc trên cùng một khung không chồng trình nghe (một lần Giao chỉ gửi một việc).
(function () {
  const listeners = {};
  const host = { innerHTML: "", isConnected: true, addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
    querySelector() { return null; }, contains() { return true; } };
  global.document = { activeElement: null };
  let posts = 0;
  global.fetch = function (url, o) {
    if (o && o.method === "POST") posts++;
    return Promise.resolve({ json: function () { return Promise.resolve({ ok: true, jobs: [], counts: {}, errors: [] }); } });
  };
  const opts = { slug: "minh", name: "Minh", brain: function () { return "brain"; } };
  const a = AJ.mount(host, opts); a.destroy();
  const b = AJ.mount(host, opts); b.destroy();
  AJ.mount(host, opts);
  const fire = function (type, target) { (listeners[type] || []).forEach(function (f) { f({ target: target }); }); };
  const cls = function (c) { return { contains: function (x) { return x === c; } }; };
  fire("input", { classList: cls("aj-text"), value: "Soạn email" });
  const btn = { classList: cls("aj-assign-send"), dataset: {} };
  btn.closest = function () { return btn; };
  fire("click", Object.assign({}, btn, { closest: function () { return btn; } }));
  check("review #1: gắn ba lần, mỗi loại sự kiện chỉ một trình nghe, một lần Giao chỉ một POST",
    (listeners.input || []).length === 1 && (listeners.click || []).length === 1 && posts === 1, JSON.stringify({ posts: posts }));
})();
// review #4: lượt nằm "đang chờ" quá lâu có nút Thử lại.
h = TM.replyStatusHtml({ id: 9, replies: [{ agent_key: "ag_lan", status: "queued", reason: "", updated_at: Date.now() / 1000 - 3600 }] }, ctx);
check("review #4: chờ quá lâu thì có Thử lại", h.includes(vi["teams.reply.stuck"]) && /data-retry="9"/.test(h), h);
h = TM.replyStatusHtml({ id: 9, replies: [{ agent_key: "ag_lan", status: "queued", reason: "", updated_at: Date.now() / 1000 }] }, ctx);
check("vừa gửi thì chỉ là đang chờ", !h.includes("data-retry") && h.includes(vi["teams.reply.queued"]), h);
h = TM.replyStatusHtml({ id: 9, replies: [{ agent_key: "ag_lan", status: "error", reason: "leader_changed" }] }, ctx);
check("review #5: lý do Trưởng nhóm vừa đổi có nhãn", h.includes(vi["teams.reply.why.leader_changed"]), h);

// ───────────── nối dây ─────────────
check("app.js chuyển gói team_replies cho trang Nhóm", /data\.type === "team_replies"/.test(appJs));
check("chữ của dòng trạng thái tối thiểu 16px, nút Thử lại cao 44px", /\.tm-reply \{[^}]*font-size: 16px/.test(css)
  && /\.tm-reply-retry \{[^}]*min-height: 44px/.test(css));
const keys = Object.keys(vi).filter(function (k) { return k.indexOf("teams.reply.") === 0; });
check("khoá teams.reply.* có đủ hai thứ tiếng", keys.length >= 14 && keys.every(function (k) { return en[k]; }));

console.log(fails ? "\nĐỎ " + fails + " mục" : "\nTất cả xanh.");
process.exit(fails ? 1 : 0);
