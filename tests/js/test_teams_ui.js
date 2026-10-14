// Nhóm chat team T1, nhiệm vụ 7: trang Nhóm (spec 2026-10-13-team-chat-design mục 16, wireframe docs/dev/team-chat-wireframes.md).
//
//     python tests/run.py --js teams_ui -v
//
// Hàm thuần của teams.js chạy dưới node: danh sách nhóm, tin có người gửi và trạng thái bằng chữ, hàng đợi đánh số đúng
// thứ tự chạy, khung soạn (@ có cấu trúc, Giao việc), cài đặt một cột. Cộng các chỗ nối: thanh bên, script, CSS, i18n.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const consoleJs = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const indexHtml = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const appJs = fs.readFileSync(path.join(ROOT, "dashboard", "app.js"), "latin1");
const teamsJs = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

const members = [
  { agent_key: "ag_lan", slug: "lan", name: "Lan", role: "leader", status: "active", resonance_enabled: true, agent_status: "active" },
  { agent_key: "ag_minh", slug: "minh", name: "Minh <b>", role: "member", status: "active", resonance_enabled: false, agent_status: "active" },
];
const team = { team_id: "tm_1", name: "Ra mắt <i>", description: "", leader_key: "ag_lan", status: "active",
  caps: { mentions: 3, daily_turns: 100, task_turns: 12, task_steps: 8 }, members: members,
  counts: { running: 1, waiting: 2, blocked: 1 }, running: [{ id: "t_1", title: "Soạn kế hoạch" }], busy: {} };

// ───────────── danh sách nhóm ─────────────
let h = TM.teamListHtml([team, Object.assign({}, team, { team_id: "tm_2", name: "Nội dung", counts: { running: 0, waiting: 0, blocked: 0 } })], "tm_1");
check("danh sách: tên nhóm được escape", h.includes("Ra mắt &lt;i&gt;") && !h.includes("<i>"), h);
check("danh sách: nhóm đang mở được đánh dấu", /data-team="tm_1"[^>]*aria-current="true"/.test(h), h);
check("T5 danh sách: nhóm có việc chờ chủ mang nhãn Cần bạn", h.includes(vi["teams.needs_you"]), h);
check("T5 danh sách rỗng: thẻ hướng dẫn ba bước kèm nút Tạo nhóm", (function (g) {
  return g.includes(vi["teams.guide_title"]) && ["teams.guide_1", "teams.guide_2", "teams.guide_3"].every(function (k) {
    return g.includes(vi[k]); }) && g.includes("tm-new");
})(TM.teamListHtml([], "")));

// ───────────── tin ─────────────
const ctx = { members: members, leaderKey: "ag_lan", taskTitles: { t_1: "Soạn kế hoạch" } };
h = TM.messageHtml({ id: 1, author_kind: "owner", content: "Giao <b>việc</b>", meta: { as_job: true, mentions: ["ag_minh"] } }, ctx);
check("T5 tin của chủ: bong bóng bên phải, không tên, không ảnh, nội dung escape, nhãn Giao việc",
      h.includes("tm-msg-owner") && !h.includes(vi["teams.owner"]) && !h.includes("tm-ava") && h.includes("&lt;b&gt;việc")
      && h.includes(vi["teams.as_job"]), h);
h = TM.messageHtml({ id: 2, author_kind: "agent", author_ref: "ag_minh", content: "Bài viết", task_id: "t_1", step_id: "st_1",
  meta: { role: "work", status: "done", applied: true } }, ctx);
check("T5 tin agent: ảnh, tên, vai, nhãn việc bấm được; trạng thái Xong (bình thường) không hiện",
      h.includes("tm-ava") && h.includes("Minh &lt;b&gt;") && h.includes(vi["teams.role.work"]) && /data-task="t_1"/.test(h)
      && !h.includes(">" + vi["teams.status.done"] + "<"), h);
check("T5 câu trả lời trò chuyện không mang nhãn vai", !TM.messageHtml({ id: 9, author_kind: "agent", author_ref: "ag_lan",
  content: "Chào", meta: { role: "leader_reply", status: "done" } }, ctx).includes("tm-role"));
h = TM.messageHtml({ id: 10, author_kind: "system", content: "Chủ nhóm đã <b>bật</b>", meta: { kind: "x" } }, ctx);
check("T5 tin hệ thống: dòng xám ở giữa, escape, không bong bóng", h.includes('class="tm-sys"') && h.includes("&lt;b&gt;bật")
      && !h.includes("tm-bubble"), h);
h = TM.messageHtml({ id: 3, author_kind: "agent", author_ref: "ag_lan", content: "Tổng hợp", task_id: "t_1",
  meta: { role: "synthesize", status: "done", applied: true, job_result: true } }, ctx);
check("bản tổng hợp cuối: nhãn Kết quả việc", h.includes(vi["teams.job_result"]), h);
for (const st of ["late_cancelled", "old_revision", "member_left", "leader_changed"]) {
  h = TM.messageHtml({ id: 4, author_kind: "agent", author_ref: "ag_minh", content: "x", task_id: "t_1",
    meta: { role: "work", status: st, applied: false } }, ctx);
  check("tin không áp dụng có nhãn bằng chữ: " + st, h.includes(vi["teams.status." + st]) && h.includes("tm-msg-late"), h);
}
h = TM.messageHtml({ id: 5, author_kind: "agent", author_ref: "ag_lan", content: "Nên làm",
  meta: { role: "leader_reply", status: "done", applied: true, proposal: { title: "Bảng <giá>", brief: "x" } } }, ctx);
check("thẻ đề xuất: tiêu đề escape, hai nút Tạo việc và Bỏ qua", h.includes("Bảng &lt;giá&gt;") && /data-accept="5"/.test(h)
      && h.includes(vi["teams.proposal_create"]) && h.includes(vi["teams.proposal_skip"]), h);
h = TM.messageHtml({ id: 6, author_kind: "agent", author_ref: "ag_lan", content: "x", meta: { role: "plan", notes: ["Lệnh 'fly' <x>"] } }, ctx);
check("ghi chú của host hiện dưới tin, escape", h.includes("Lệnh &#39;fly&#39; &lt;x&gt;"), h);
h = TM.messageHtml({ id: 7, author_kind: "owner", content: "Chốt giá 99k", meta: { decision: true } }, ctx);
check("tin đã ghim quyết định: có nhãn và nút bỏ ghim", h.includes(vi["teams.decision_pinned"]) && /data-decision="7"[^>]*data-on="0"/.test(h), h);
h = TM.messageHtml({ id: 8, author_kind: "agent", author_ref: "ag_cu", content: "x", meta: {} }, ctx);
check("tác giả đã rời nhóm vẫn hiện được (mã)", h.includes("ag_cu"), h);

// ───────────── hàng đợi ─────────────
const queue = { version: 7,
  running: [{ id: "t_1", title: "Soạn kế hoạch", team_rev: 1 }],
  waiting: [{ id: "t_3", title: "Bảng giá", team_prio: 1 }, { id: "t_2", title: "Ảnh <bìa>", team_prio: null }],
  blocked: [{ id: "t_4", title: "Video", block_kind: "failed", block_reason: "Lượt lỗi: hết giờ" },
            { id: "t_5", title: "Số liệu", block_kind: "cap_reached", block_reason: "Đã chạm trần lượt mỗi việc" }] };
h = TM.queueHtml(queue);
check("đang làm: nút Sửa yêu cầu và Huỷ", /data-amend="t_1"/.test(h) && /data-cancel="t_1"/.test(h), h);
check("hàng chờ đánh số đúng thứ tự chạy", h.indexOf("Bảng giá") < h.indexOf("Ảnh &lt;bìa&gt;") && h.includes(">1<") && h.includes(">2<"), h);
check("việc ưu tiên: dấu sao kèm chữ, nút Bỏ ưu tiên", /data-prio="t_3"[^>]*data-on="0"/.test(h) && h.includes(vi["teams.unprioritize"])
      && h.includes(vi["teams.prioritized"]), h);
check("việc thường: nút Ưu tiên có chữ", /data-prio="t_2"[^>]*data-on="1"/.test(h) && h.includes(vi["teams.prioritize"]), h);
check("T5 chờ bạn: lý do bằng chữ; lỗi thì Thử lại; hết lượt thì Cho thêm lượt (một nút giải quyết)",
      h.includes("Lượt lỗi: hết giờ") && /data-unblock="t_4"[^>]*data-action="retry"/.test(h)
      && /data-extend="t_5"/.test(h) && h.includes(vi["teams.act.extend"]) && !/data-unblock="t_5"/.test(h), h);
h = TM.queueHtml({ version: 1, running: [], waiting: [], blocked: [{ id: "t_6", title: "Lặp", block_kind: "no_progress", block_reason: "x" }] });
check("không tiến triển: nút Thử lại (chạy lại bước, không phải cho chạy tiếp ra kết quả lặp)",
      /data-unblock="t_6"[^>]*data-action="retry"/.test(h), h);
check("đổi công tắc Giao việc thì gửi lại là tin MỚI (không trả nhầm tin cũ khác loại)",
      /tm-asjob[\s\S]{0,260}S\.pending = null/.test(teamsJs));
check("mọi lớp đặt display có luật [hidden] riêng", [".tm-job", ".tm-sug-item", ".tm-radio", ".tm-check", ".tm-ava"]
  .every(function (c) { return css.includes(c + "[hidden]"); }));
check("hàng rỗng: có chữ", TM.queueHtml({ version: 0, running: [], waiting: [], blocked: [] }).includes(vi["teams.queue_empty"]));

// ───────────── khung soạn ─────────────
const sug = TM.mentionMatches(members, "mi", []);
check("@ gợi ý theo tên hay slug, chỉ thành viên đang hoạt động", sug.length === 1 && sug[0].agent_key === "ag_minh");
check("@ đã chọn thì không gợi ý lại", TM.mentionMatches(members, "", ["ag_minh"]).every(function (m) { return m.agent_key !== "ag_minh"; }));
let hint = TM.composerHint({ mentions: ["ag_minh"], asJob: true, cap: 3, waiting: 2, members: members });
check("T5 Giao việc: một dòng nói rõ tạo việc cho ai (không còn vị trí hàng)", hint.text.includes("Minh") && !hint.text.includes("3")
      && hint.ok, hint.text);
check("T5 không Giao việc: không có dòng gợi ý", TM.composerHint({ mentions: [], asJob: false, cap: 3, members: members }).text === "");
hint = TM.composerHint({ mentions: ["a", "b", "c", "d"], asJob: false, cap: 3, waiting: 0, members: members });
check("quá trần @: tắt nút Gửi, nói rõ trần", !hint.ok && hint.text.includes("3"), hint.text);
hint = TM.composerHint({ mentions: [], asJob: true, cap: 3, waiting: 0, members: members, leaderKey: "ag_lan" });
check("Giao việc không @: giao chung cho trưởng nhóm", hint.text.includes("Lan") && hint.ok, hint.text);
check("mã tin client mới mỗi lần, dạng chuỗi", TM.newClientId() !== TM.newClientId() && typeof TM.newClientId() === "string");

// ───────────── cài đặt nhóm ─────────────
h = TM.membersHtml(team, [{ slug: "hoa", name: "Hoa", agent_key: null, status: "unregistered" }, { slug: "lan", name: "Lan" }]);
check("thành viên: vai bằng chữ, trạng thái Cộng hưởng bằng chữ", h.includes(vi["teams.leader"]) && h.includes(vi["teams.member"])
      && h.includes(vi["resonance.t0_state_on"]) && h.includes(vi["resonance.t0_state_off"]), h);
check("thành viên: nút Đặt làm trưởng nhóm, Bỏ khỏi nhóm", /data-leader="ag_minh"/.test(h) && /data-remove="ag_minh"/.test(h), h);
check("thêm thành viên: một nút mở hộp chọn (0.142.0; hộp chọn loại người đã trong nhóm, test ở test_team_chat_0142.js)",
      h.includes("tm-add-open") && !h.includes("tm-add-pick"), h);
h = TM.settingsFormHtml(team);
check("T5 tên, mô tả, trạng thái một cột, nút Lưu ở cuối, không có số giới hạn", h.lastIndexOf("tm-save") > h.lastIndexOf("tm-status")
      && !h.includes("tm-cap") && !h.includes("<table"), h);
check("ba trạng thái nhóm bằng chữ", h.includes(vi["teams.status_active"]) && h.includes(vi["teams.status_paused"])
      && h.includes(vi["teams.status_archived"]), h);
h = TM.capsFormHtml(team);
check("T5 số giới hạn riêng một form, nút Lưu ở cuối", h.lastIndexOf("tm-caps-save") > h.lastIndexOf("tm-cap-") && !h.includes("<table"), h);
h = TM.turnsHtml([{ agent_key: "ag_lan", role: "plan", status: "ok", created_at: Date.now() / 1000, tokens_in: 10, tokens_out: 2 },
                  { agent_key: "ag_minh", role: "work", status: "refunded", created_at: Date.now() / 1000 }], team);
check("lượt: lượt hoàn không tính, theo agent và vai", h.includes(vi["teams.turns_today"].replace("{n}", "1").replace("{cap}", "100"))
      && h.includes("Lan") && h.includes(vi["teams.role.plan"]), h);
// Tạo nhóm từ 0.142.0 là hộp chọn kiểu Zalo (team-picker.js, test riêng ở test_team_chat_0142.js).
check("tạo nhóm và thêm người mở hộp chọn kiểu Zalo", teamsJs.includes('openPicker("create"') && teamsJs.includes('openPicker("add"')
      && !teamsJs.includes("createFormHtml"));
h = TM.bannersHtml(Object.assign({}, team, { leader_key: null }));
check("T5 băng nhóm chưa có trưởng nhóm kèm nút Chọn", h.includes(vi["teams.no_leader"]) && /data-open-team="1"/.test(h), h);
h = TM.bannersHtml(Object.assign({}, team, { status: "paused" }));
check("T5 băng tạm dừng kèm nút Bật lại", h.includes(vi["teams.paused_banner"]) && /data-team-resume="1"/.test(h)
      && h.includes(vi["teams.resume_team"]), h);
check("băng rôn thành viên bận ở nhóm khác", TM.bannersHtml(Object.assign({}, team, { busy: { ag_minh: "tm_9" } }), { tm_9: "Nhóm Y" })
      .includes("Nhóm Y"));

// ───────────── chỗ nối ─────────────
const rail = (consoleJs.match(/const RAIL_ITEMS = \[\s*([\s\S]*?)\]\.map/) || [])[1] || "";
check("thanh bên có mục teams ngay sau workspace", /"workspace", "teams"/.test(rail), rail);
check("nhóm Năng lực chứa teams", /ids: \["workspace", "teams"/.test(consoleJs));
check("icon và tiêu đề trang teams", /teams: "users"/.test(consoleJs) && consoleJs.includes('"teams"') && /id === "teams"/.test(consoleJs));
check("index.html nạp teams.js", /<script src="\/static\/teams\.js\?v=\d+"><\/script>/.test(indexHtml));
check("app.js chuyển gói team_message, team_state thành sự kiện trang", appJs.includes('"team_message"') && appJs.includes("javis:team-event"));
check("lớp flex của trang có luật [hidden]", /\.tm-page\[hidden\]\{display:none\}|\.tm-[a-z-]+\[hidden\]\s*\{\s*display:\s*none/.test(css)
      && css.includes(".tm-"), "");
check("nút .ws-btn bị hidden thật sự ẩn (smoke: nút Trang sau vẫn hiện)", /\.tm-page \.ws-btn\[hidden\]\s*\{\s*display:\s*none/.test(css));
check("ngăn đóng: không chừa cột trống", /\.tm-page\[data-side="0"\]\s*\{\s*grid-template-columns/.test(css)
      && teamsJs.includes('setAttribute("data-side"'));
check("T5 đầu khung chat một hàng; điện thoại bỏ ảnh nhóm và chữ của chip việc để tên còn chỗ",
      /\.tm-chat-head \{[^}]*flex-wrap: nowrap/.test(css) && /\.tm-chip-label \{ display: none; \}/.test(css));
check("ngăn kéo cài đặt có nền đặc (smoke 375px: nhìn xuyên thấy tin)",
      /\.tm-side \{ position: fixed;[^}]*background: var\(--bg\)/.test(css));
check("màn hẹp: nút tối thiểu 44px", /@media[^{]*max-width[^{]*\{[\s\S]*\.tm-[\s\S]*min-height:\s*44px/.test(css));
const keys = Object.keys(vi).filter(function (k) { return k.indexOf("teams.") === 0 || k === "page.teams.label"; });
check("đủ khoá tiếng Anh cho mọi chữ của trang", keys.length >= 40 && keys.every(function (k) { return typeof en[k] === "string" && en[k]; }),
      keys.filter(function (k) { return !en[k]; }).join(","));
check("en.json không có chữ Việt ở khoá teams", keys.every(function (k) { return !/[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]/i.test(en[k]); }));
check("không em dash trong teams.js và chuỗi mới", teamsJs.indexOf(String.fromCharCode(0x2014)) < 0
      && keys.every(function (k) { return (vi[k] + en[k]).indexOf(String.fromCharCode(0x2014)) < 0; }));
// Chỉ khoá viết trọn (`tw("teams.x")` hay `tw("teams.x", {...})`); khoá ghép động kiểm riêng ở dưới.
const used = Array.from(new Set((teamsJs.match(/tw\("(teams\.[a-z0-9_.]+)"[,)]/g) || []).map(function (m) { return m.slice(4, -2); })));
const dynamic = ["teams.status_active", "teams.status_paused", "teams.status_archived", "teams.tab_members", "teams.tab_jobs",
  "teams.tab_team", "teams.cap.task_turns", "teams.cap.task_steps", "teams.cap.daily_turns", "teams.cap.mentions"]
  .concat(["failed", "interrupted", "no_leader", "assignee_removed", "no_progress", "cap_reached", "agent_busy_long", "waiting_user"]
    .map(function (k) { return "teams.block." + k; }))
  .concat(["done", "late_cancelled", "late", "old_revision", "member_left", "leader_changed"].map(function (k) { return "teams.status." + k; }));
check("khoá ghép động đều có trong vi.json", dynamic.every(function (k) { return vi[k]; }), dynamic.filter(function (k) { return !vi[k]; }).join(","));
check("mọi khoá teams.js dùng đều có trong vi.json", used.length > 20 && used.every(function (k) { return vi[k]; }),
      used.filter(function (k) { return !vi[k]; }).join(","));

// ───────────── T2: sáu reaction, lý do, góp ý (spec mục 14) ─────────────
check("đúng sáu reaction theo thứ tự, giữ nguyên giá trị", TM.REACTIONS.map(function (r) { return r.value; }).join(",") ===
      "like,love,haha,wow,sad,angry");
check("sáu emoji gốc 👍 ❤️ 😂 😮 😢 😡", TM.REACTIONS.map(function (r) { return r.emoji; }).join("") ===
      "\u{1F44D}❤️\u{1F602}\u{1F62E}\u{1F622}\u{1F621}");
const rkeys = TM.REACTIONS.map(function (r) { return r.key; }).concat(["on_point", "wrong_facts", "missing", "too_long",
  "unclear", "off_topic"].map(function (k) { return "teams.reason." + k; }));
check("nhãn sáu reaction và sáu lý do có ở cả vi và en", rkeys.every(function (k) { return vi[k] && en[k]; }),
      rkeys.filter(function (k) { return !vi[k] || !en[k]; }).join(","));
check("chọn lại cái đang chọn là bỏ; chọn cái khác là đổi", TM.nextReaction("sad", "sad") === "none"
      && TM.nextReaction("sad", "wow") === "wow" && TM.nextReaction(undefined, "like") === "like");
const am = { id: 7, author_kind: "agent", author_ref: "ag_lan", content: "Chuyện buồn", meta: { status: "done" } };
let mh = TM.messageHtml(am, { members: members });
check("tin của trợ lý có nút thả cảm xúc, chưa mở bộ chọn", mh.includes('class="tm-react-btn"') && mh.includes('data-react-open="7"')
      && !mh.includes("tm-react-panel"), mh);
check("tin của chủ không có nút thả cảm xúc", !TM.messageHtml({ id: 8, author_kind: "owner", content: "x", meta: {} },
  { members: members }).includes("tm-react-btn"));
mh = TM.messageHtml(am, { members: members, picker: 7 });
check("mở bộ chọn ngay tại tin: sáu nút, lý do, ô góp ý tối đa 500", (mh.match(/class="tm-react-pick"/g) || []).length === 6
      && (mh.match(/name="tm-reason"/g) || []).length === 6 && mh.includes('maxlength="500"') && mh.includes(vi["teams.react_note"]), mh);
const withR = Object.assign({}, am, { reaction: { value: "sad", reasons: ["too_long"], comment: "Gọn <b>hơn</b>" } });
mh = TM.messageHtml(withR, { members: members, picker: 7 });
check("emoji đã chọn hiện dưới tin, bấm để đổi", /class="tm-react-chip" data-react-open="7"/.test(mh) && mh.includes("\u{1F622}")
      && mh.includes(vi["teams.react.sad"]), mh);
check("bộ chọn đánh dấu emoji đang chọn và lý do đã chọn", /data-react="sad"[^>]*aria-pressed="true"/.test(mh)
      && /value="too_long" checked/.test(mh), mh);
check("góp ý được escape", mh.includes("Gọn &lt;b&gt;hơn&lt;/b&gt;") && !mh.includes("<b>hơn"), mh);
const draft = TM.reactionPickerHtml(am, { value: "like", reasons: [], comment: "" }, { reasons: ["missing"], comment: "đang gõ" });
check("bản nháp đang soạn giữ qua lần vẽ lại", /value="missing" checked/.test(draft) && draft.includes("đang gõ")
      && /data-react="like"[^>]*aria-pressed="true"/.test(draft), draft);
check("chỉ có lý do/góp ý (bỏ emoji): chip vẫn hiện", TM.reactionChipHtml(am, { value: null, reasons: ["missing"], comment: "" })
      .includes(vi["teams.react_reasons_n"].replace("{n}", "1")));
check("không có phản hồi: không chip", TM.reactionChipHtml(am, null) === "");
check("thả cảm xúc gửi nonce mới mỗi lần, không mở lượt", /\/reaction"\)[\s\S]{0,120}nonce: newClientId\(\)/.test(teamsJs));
check("điện thoại: nhấn giữ tin mở bộ chọn, có ngưỡng rung tay", teamsJs.includes('"pointerdown"') && /> 10/.test(teamsJs));
check("gói WS không mang phản hồi thì giữ phản hồi đang có", teamsJs.includes('!("reaction" in nm)'));
check("CSS: nút mặt cười hiện khi rê chuột, luôn hiện trên máy chạm, tắt menu nhấn giữ của máy",
      /\.tm-msg-agent:hover \.tm-react-btn/.test(css)
      && /@media \(hover: none\) \{ \.tm-react-btn \{ opacity: 1; \} \.tm-msg-agent \{ -webkit-touch-callout: none; \} \}/.test(css));
// Review T2 #4 tới #6
check("đang soạn góp ý thì vẽ lại giữ con trỏ, chỗ cuộn, không kéo xuống cuối",
      /typing = S\.picker !== null && act && act\.classList/.test(teamsJs) && /ta\.setSelectionRange\(typing\.start, typing\.end\)/.test(teamsJs)
      && /\(stick \|\| atEnd\) && S\.picker === null/.test(teamsJs));
check("mở bộ chọn đưa focus vào emoji đầu (bảng của tin chủ: nút đầu); đóng trả focus về nút đã mở",
      /S\.focusPicker = true/.test(teamsJs)
      && /\.tm-react-panel \.tm-react-pick"\) \|\| box\.querySelector\("\.tm-react-panel button"\);\s*if \(first\) first\.focus\(\)/.test(teamsJs)
      && /\.tm-react-btn\[data-react-open="' \+ S\.focusBack/.test(teamsJs) && /\.tm-more-btn\[data-react-open="' \+ S\.focusBack/.test(teamsJs));
check("nhấn giữ chỉ cho chạm và bút, không cho chuột; chặn menu ngữ cảnh của lần giữ đó",
      teamsJs.includes('if (e.pointerType === "mouse") return;') && /"contextmenu"[\s\S]{0,80}if \(held\) \{ e\.preventDefault\(\)/.test(teamsJs));
check("CSS: điện thoại hàng ngang lớn, vùng chạm >= 44px", /\.tm-react-pick \{ flex: 1 1 0; min-width: 44px; min-height: 48px/.test(css));
check("CSS 375px: sáu nút 44px lọt bề ngang (khe 4px, đệm 6px; smoke T2 thấy 😡 tràn mép)",
      /\.tm-react-panel \{ padding: 8px 6px; \}/.test(css) && /\.tm-react-row \{ flex-wrap: nowrap; justify-content: space-between; gap: 4px; \}/.test(css));
check("CSS: bảng chọn display:flex có luật [hidden] riêng", /\.tm-react-panel\[hidden\] \{ display: none; \}/.test(css));

// ───────────── T3: hộp cấp Toàn quyền, công tắc Nhóm quản lý (spec mục 13) ─────────────
const limitedTeam = Object.assign({}, team, { authority: { authority: null,
  effective_caps: { task_turns: 12, task_steps: 8, help_depth: 2, daily_turns: 100 }, fixed_limits: {} } });
let ah = TM.authorityHtml(limitedTeam);
check("Quyền giới hạn: nói rõ trưởng nhóm chỉ đề xuất, có nút Bật, không có nút Thu hồi",
      ah.includes(vi["teams.auth.off"]) && ah.includes(vi["teams.auth.grant"]) && !ah.includes("tm-auth-revoke"), ah);
check("hộp cấp quyền đủ dòng của 13.1: phạm vi, agent do nhóm quản lý, provider, thanh toán, trần, ngắt việc, trần không bỏ được",
      ah.includes(vi["teams.auth.scope"]) && ah.includes(vi["teams.auth.managed_none"]) && ah.includes(vi["teams.auth.providers"])
      && ah.includes(vi["teams.auth.billing"]) && (ah.match(/name="tm-auth-ceil-[a-z_]+" value/g) || []).length === 4
      && ah.includes(vi["teams.auth.interrupt"]) && ["teams.auth.fixed_server", "teams.auth.fixed_provider",
        "teams.auth.fixed_account", "teams.auth.fixed_technical"].every(function (k) { return ah.includes(vi[k]); }), ah);
const fullTeam = Object.assign({}, team, { members: [Object.assign({}, members[0]), Object.assign({}, members[1], { managed: true })],
  authority: { authority: { leader_key: "ag_lan", granted_at: 1791900000,
    grant: { caps: { task_turns: { unlimited: true } }, ceilings: { task_turns: { unlimited: true }, daily_turns: 150 },
      providers_unlimited: ["openai-oauth"], can_interrupt: true, billing: "api" } },
    effective_caps: { task_turns: null, task_steps: 8, help_depth: 2, daily_turns: 100 } } });
ah = TM.authorityHtml(fullTeam);
check("Toàn quyền bật: trạng thái nêu trưởng nhóm, có Lưu và Thu hồi", ah.includes("tm-auth-on") && ah.includes("Lan")
      && ah.includes(vi["teams.auth.update"]) && ah.includes("tm-auth-revoke"), ah);
check("Không giới hạn hiện bằng chữ, ô số tắt, ô tích bật (null + cờ, không phải số lớn)",
      ah.includes(vi["teams.cap.task_turns"] + ": " + vi["teams.auth.unlimited"])
      && /name="tm-auth-cap-task_turns" value="" disabled/.test(ah) && /name="tm-auth-cap-task_turns-unl" checked/.test(ah), ah);
check("trần trần số hiện đúng, provider và quyền ngắt việc đã chọn được đánh dấu",
      /name="tm-auth-ceil-daily_turns" value="150"/.test(ah) && /value="openai-oauth" checked/.test(ah)
      && /name="tm-auth-interrupt" checked/.test(ah) && /value="api" checked/.test(ah), ah);
check("agent do nhóm quản lý được liệt kê", ah.includes(vi["teams.auth.managed"].replace("{names}", "Minh &lt;b&gt;")), ah);
check("chưa có trưởng nhóm: chỉ nhắc chọn trưởng nhóm", TM.authorityHtml(Object.assign({}, limitedTeam, { leader_key: null }))
      .includes(vi["teams.auth.need_leader"]));
const mh3 = TM.membersHtml(fullTeam, []);
check("tab Thành viên có công tắc Nhóm quản lý theo trạng thái", (mh3.match(/class="tm-managed-toggle"/g) || []).length === 2
      && /data-key="ag_minh" checked/.test(mh3) && mh3.includes(vi["teams.managed"]), mh3);
check("review T3 #6: Toàn quyền bật thì form trần báo trần lấy theo mục Toàn quyền; giới hạn thì không",
      TM.capsFormHtml(fullTeam).includes(vi["teams.caps_full_note"]) && !TM.capsFormHtml(limitedTeam).includes(vi["teams.caps_full_note"]));
// ───────────── T4: tìm trong nhóm, nhảy tới tin cũ ─────────────
const hits = [{ id: 41, ts: 100.5, author_kind: "agent", author_ref: "ag_lan", snippet: "Kế hoạch <script>" },
  { id: 12, ts: 50, author_kind: "owner", author_ref: "", snippet: "Ra mắt" }];
const sh = TM.searchResultsHtml(hits, members, "ke hoach");
check("kết quả tìm: đếm, người gửi, đoạn trích escape, nút nhảy kèm id và ts",
      sh.includes(vi["teams.search_results"].replace("{n}", "2")) && sh.includes("Lan") && sh.includes("Kế hoạch &lt;script&gt;")
      && !sh.includes("<script>") && /data-jump="41" data-ts="100.5"/.test(sh), sh);
check("không có kết quả: nói rõ câu đã tìm, escape", TM.searchResultsHtml([], members, "<b>x").includes("&lt;b&gt;x")
      && TM.searchResultsHtml(null, members, "") === "");
check("tin được nhảy tới được tô sáng", TM.messageHtml(am, { members: members, jumped: 7 }).includes("tm-msg-hit")
      && !TM.messageHtml(am, { members: members, jumped: 8 }).includes("tm-msg-hit"));
check("nhảy tới tin: tải trang kết thúc ở đúng tin đó, có nút về tin mới nhất",
      /before_ts=" \+ q\(ts\) \+ "&before_id=" \+ q\(Number\(mid\) \+ 1\)/.test(teamsJs) && teamsJs.includes("tm-jump-back"));
check("đang xem tin cũ: tin mới tới không chèn vào giữa khúc cũ",
      teamsJs.includes("else if (S.jumped === null || S.jumped === undefined) S.msgs.push(nm);"));
check("CSS: lớp flex mới của tìm có [hidden], vùng chạm 44px trên điện thoại",
      /\.tm-search\[hidden\]/.test(css) && /\.tm-search-row\[hidden\]/.test(css) && /\.tm-jumped\[hidden\]/.test(css)
      && /\.tm-search-btn, \.tm-search-go, \.tm-search-input, \.tm-search-hit, \.tm-jump-back \{ min-height: 44px; \}/.test(css));
// Review T4
check("review #1: tải lại trang tin mới nhất (gửi tin, lọc việc) thì thoát chế độ xem tin cũ",
      /function loadMsgs\(older\) \{[\s\S]{0,200}if \(!older\) S\.jumped = null;/.test(teamsJs));
// review #5 cũ (form tạo nhóm thay khung chat nên phải đóng ô tìm) hết hiệu lực từ 0.142.0: hộp tạo nhóm là lớp phủ,
// không đụng nhóm đang mở hay ô tìm.
check("0.142.0: hộp tạo nhóm là lớp phủ, không đổi nhóm đang mở", /function openPicker\(mode, opener\) \{(?:(?!S\.activeId =)[\s\S]){0,1400}\n  \}/.test(teamsJs));
check("review #6: băng xem tin cũ dính ở đầu khung", /\.tm-jumped \{[^}]*position: sticky; top: 0;/.test(css));
check("review #7: nút tìm đủ 44px bề ngang trên điện thoại", /\.tm-back, \.tm-close, \.tm-search-btn \{ min-width: 44px;/.test(css));
check("review #8: kết quả tìm, nhảy tới về muộn sau khi đổi nhóm thì bỏ",
      /var forTeam = S\.activeId;[\s\S]{0,200}if \(S\.activeId !== forTeam\) return;/.test(teamsJs)
      && (teamsJs.match(/if \(S\.activeId !== forTeam\) return;/g) || []).length >= 2);
const authKeys = ["teams.cap.help_depth", "teams.auth.provider_aux", "teams.auth.provider_claude", "teams.auth.billing_sub",
  "teams.auth.billing_api", "teams.auth.fixed_server", "teams.auth.fixed_provider", "teams.auth.fixed_account",
  "teams.auth.fixed_technical"];
check("khoá Toàn quyền tra qua bảng có ở cả vi và en", authKeys.every(function (k) { return vi[k] && en[k]; }));
check("CSS: lớp flex mới của Toàn quyền có luật [hidden] riêng", /\.tm-auth\[hidden\]/.test(css) && /\.tm-auth-pair\[hidden\]/.test(css)
      && /\.tm-unl\[hidden\]/.test(css));

// ───────────── T5: trang Nhóm gọn như app chat ─────────────
// Danh sách kiểu app chat: ảnh, tên, giờ, dòng xem trước (ai nói gì), nhãn trạng thái.
const now = new Date(2026, 9, 14, 18, 0, 0).getTime() / 1000;
const at = new Date(2026, 9, 14, 9, 5, 0).getTime() / 1000;
h = TM.teamListHtml([Object.assign({}, team, { counts: { running: 1, waiting: 0, blocked: 0 },
  last: { author_kind: "agent", author: "Lan", text: "Kế hoạch <xong>", ts: at } })], "", now);
check("T5 dòng nhóm: ảnh, giờ hôm nay, xem trước 'Lan: ...' escape, nhãn Đang làm", h.includes("tm-ava") && h.includes("09:05")
      && h.includes("Lan: Kế hoạch &lt;xong&gt;") && h.includes(vi["teams.badge_running"]), h);
h = TM.teamListHtml([Object.assign({}, team, { counts: {}, status: "paused", last: { author_kind: "owner", text: "Chào", ts: at - 86400 } })], "", now);
check("T5 tin của chủ xem trước là 'Bạn: ...', ngày khác hiện ngày/tháng, nhãn Tạm dừng",
      h.includes(vi["teams.you"] + ": Chào") && h.includes("13/10") && h.includes(vi["teams.status_paused"]), h);
check("T5 nhóm chưa có tin: nói rõ", TM.teamListHtml([Object.assign({}, team, { last: null })], "", now).includes(vi["teams.no_messages"]));
check("T5 giờ ngắn: hôm nay HH:MM, ngày khác dd/mm, rỗng khi không có", TM.timeShort(at, now) === "09:05"
      && TM.timeShort(at - 86400, now) === "13/10" && TM.timeShort(0, now) === "");

// @ theo chữ: người được gọi là các "@Tên" còn trong chữ.
const mem3 = members.concat([{ agent_key: "ag_la", slug: "la", name: "Lan Anh", status: "active" },
  { agent_key: "ag_cu", slug: "cu", name: "Cũ", status: "left" }]);
check("T5 @ lấy từ chữ theo thứ tự xuất hiện, theo tên hay slug, không phân biệt hoa thường",
      TM.mentionsFromText("@minh <b> làm, @LAN xem", mem3).join() === "ag_minh,ag_lan"
      && TM.mentionsFromText("nhờ @minh nhé", mem3).join() === "ag_minh");
check("T5 @ tên dài hơn thắng ('@Lan Anh' không gọi nhầm Lan)", TM.mentionsFromText("@Lan Anh làm giúp", mem3).join() === "ag_la");
check("T5 @ phải hết tên ('@Lanx' không gọi Lan); người đã rời không được gọi; xoá chữ là bỏ gọi",
      TM.mentionsFromText("@Lanx", mem3).length === 0 && TM.mentionsFromText("@Cũ", mem3).length === 0
      && TM.mentionsFromText("không gọi ai", mem3).length === 0);
// 0.142.0 (đối chiếu goal-claude-v2 mục 3): người được gọi là TOKEN riêng ở hàng "Gọi:" (tm-calls), bấm x là bỏ gọi và
// xoá token trong chữ. Hàng chip @ cũ của T5 (tm-chips, lặp lại chữ) vẫn không quay lại.
check("T5 gửi tin lấy người được gọi từ chữ, không còn hàng chip @ trùng chữ; 0.142.0 có hàng token Gọi",
      /var scan = mentionScan\(text, S\.team\.members, S\.picked\);/.test(teamsJs) && !teamsJs.includes("tm-chips")
      && teamsJs.includes("data-unmention") && teamsJs.includes("tm-calls"));

// Một nút giải quyết cho việc bị chặn.
const BA = TM.blockedAction;
check("T5 nút giải quyết theo lý do chặn", BA("cap_reached").act === "extend" && BA("failed").act === "retry"
      && BA("no_progress").act === "retry" && BA("interrupted").key === "teams.act.continue" && BA("no_leader").act === "leader"
      && BA("agent_busy_long").act === "resume" && BA("waiting_user").act === "resume" && BA("assignee_removed") === null);
h = TM.jobStripHtml({ running: [{ id: "t_1", title: "Soạn <kế>" }], waiting: [{ id: "t_9", title: "x" }],
  blocked: [{ id: "a", title: "A", block_kind: "cap_reached", block_reason: "Nhóm đã dùng hết số lần trả lời hôm nay" },
    { id: "b", title: "B", block_kind: "no_leader", block_reason: "" }, { id: "c", title: "C", block_kind: "failed" }] });
check("T5 dải việc đầu khung chat: đang làm một dòng (Sửa, Huỷ), tối đa hai thẻ chờ bạn có nút giải quyết, còn lại gom một nút",
      h.includes("Soạn &lt;kế&gt;") && /data-amend="t_1"/.test(h) && /data-extend="a"/.test(h) && /data-open-team="1"/.test(h)
      && !h.includes('data-cancel="c"') && h.includes(vi["teams.blocked_more"].replace("{n}", "1")) && !h.includes("t_9"), h);
check("T5 lý do trống thì dùng nhãn lý do bằng chữ", h.includes(vi["teams.block.no_leader"]), h);
check("T5 dải việc trống khi không có việc chạy hay chờ bạn", TM.jobStripHtml({ running: [], waiting: [{ id: "x", title: "x" }], blocked: [] }) === "");
check("T5 chip việc: ẩn khi không có việc; có việc chờ bạn thì Cần bạn N (cảnh báo); không thì Việc N",
      TM.jobsChip({}) === null && TM.jobsChip({ blocked: [1, 2], running: [1] }).warn === true
      && TM.jobsChip({ blocked: [1, 2] }).n === 2 && TM.jobsChip({ running: [1], waiting: [1, 2] }).n === 3
      && TM.jobsChip({ running: [1] }).warn === false);
check("T5 chip việc tách chữ và số (điện thoại chỉ hiện icon kèm số)", /tm-chip-label[\s\S]*tm-chip-n/.test(TM.jobsChipHtml({ running: [1] })));
check("T5 Cho thêm lượt gọi route extend rồi báo đã cho thêm; nhóm tạm dừng thì nhắc Bật lại",
      /"\/extend"\)\)\.then[\s\S]{0,300}"teams\.extended_paused" : "teams\.extended"/.test(teamsJs)
      && vi["teams.extended_paused"].includes(vi["teams.resume_team"]));

// Ba mức tự quyết đặt lên Toàn quyền.
check("T5 mức 1 = chưa bật Toàn quyền", TM.levelOf(limitedTeam) === 1);
const withGrant = function (g) { return Object.assign({}, team, { authority: { authority: { leader_key: "ag_lan", grant: g } } }); };
const g2 = TM.grantFor(2), g3 = TM.grantFor(3);
check("T5 hộp quyền mức 2: trần tối đa vừa phải, không ngắt việc, không provider Không giới hạn, gói thuê bao",
      g2.ceilings.task_turns === 24 && g2.ceilings.daily_turns === 200 && g2.can_interrupt === false
      && g2.providers_unlimited.length === 0 && g2.billing === "subscription" && Object.keys(g2.caps).length === 0);
check("T5 hộp quyền mức 3: trần tối đa không giới hạn, được ngắt việc, vẫn không provider Không giới hạn",
      ["task_turns", "task_steps", "help_depth", "daily_turns"].every(function (k) { return g3.ceilings[k].unlimited === true; })
      && g3.can_interrupt === true && g3.providers_unlimited.length === 0);
check("T5 đọc lại đúng mức 2, 3; trưởng nhóm tự chỉnh số trong khoảng cho phép vẫn là mức đó",
      TM.levelOf(withGrant(g2)) === 2 && TM.levelOf(withGrant(g3)) === 3
      && TM.levelOf(withGrant(Object.assign({}, g2, { caps: { task_turns: 20 } }))) === 2);
check("T5 hộp quyền đặt tay khác ba mức: Tuỳ chỉnh", TM.levelOf(withGrant(Object.assign({}, g2, { can_interrupt: true }))) === "custom"
      && TM.levelOf(withGrant(Object.assign({}, g3, { providers_unlimited: ["aux"] }))) === "custom");
check("T5 mức 1 không có hộp quyền (là thu hồi)", TM.grantFor(1) === null);
h = TM.teamTabHtml(Object.assign({}, withGrant(g2), { usage: { today: 7, cap: 100 } }), [], {});
check("T5 tab Nhóm: thành viên, câu hỏi tự quyết, ba lựa chọn có mô tả (mức 2 được chọn), số đã dùng hôm nay",
      h.includes(vi["teams.level_title"]) && (h.match(/name="tm-level"/g) || []).length === 3 && /value="2" checked/.test(h)
      && ["teams.level_1", "teams.level_2", "teams.level_3", "teams.level_1_desc", "teams.level_3_desc"].every(function (k) {
        return h.includes(vi[k]); }) && h.includes(vi["teams.usage_today"].replace("{n}", "7").replace("{cap}", "100")), h);
check("T5 tab Nhóm: mọi con số và quyền chi tiết trong Nâng cao, đóng sẵn",
      /<details class="tm-adv">/.test(h) && h.indexOf("tm-adv") < h.indexOf("tm-caps-form") && h.indexOf("tm-adv") < h.indexOf("tm-auth")
      && h.indexOf("tm-adv") < h.indexOf("tm-turns") && h.indexOf("tm-adv") > h.indexOf("tm-level"), h);
check("T5 Nâng cao đã mở thì vẽ lại vẫn mở", /<details class="tm-adv" open>/.test(TM.teamTabHtml(team, [], { advOpen: true })));
check("T5 chưa có trưởng nhóm: không chọn mức được, nhắc chọn trưởng nhóm",
      TM.levelsHtml(Object.assign({}, team, { leader_key: null })).includes(vi["teams.level_need_leader"])
      && !TM.levelsHtml(Object.assign({}, team, { leader_key: null })).includes("tm-level\""));
check("T5 không giới hạn số lần trả lời: nói rõ", TM.teamTabHtml(Object.assign({}, team, { usage: { today: 3, cap: null } }), [], {})
      .includes(vi["teams.usage_today_unl"].replace("{n}", "3")));
check("T5 mức 3 hỏi lại trước khi bật; mức 1 là thu hồi", /n === 3 && typeof confirm === "function" && !confirm\(tw\("teams\.level_3_confirm"\)\)/.test(teamsJs)
      && /n === 1 \? \{ mode: "limited"/.test(teamsJs));

// Thành viên: một dòng, chạm mở thao tác.
h = TM.membersHtml(team, [], null);
check("T5 thành viên: tên đủ trong dòng riêng, vai ở dòng dưới, thao tác ẩn tới khi chạm",
      h.includes('class="tm-mname">Minh &lt;b&gt;') && (h.match(/class="tm-mact" hidden/g) || []).length === 2
      && /data-expand="ag_minh" aria-expanded="false"/.test(h), h);
h = TM.membersHtml(team, [], "ag_minh");
check("T5 chạm một thành viên mở thao tác của người đó", /data-expand="ag_minh" aria-expanded="true"/.test(h)
      && (h.match(/class="tm-mact" hidden/g) || []).length === 1, h);

// Bảng của tin: tin trợ lý có cảm xúc kèm Ghim; tin của chủ chỉ Ghim.
h = TM.messageHtml({ id: 20, author_kind: "owner", content: "Chốt", meta: {} }, { members: members, picker: 20 });
check("T5 tin của chủ: bảng chỉ có Ghim làm quyết định", h.includes("tm-owner-panel") && /data-decision="20" data-on="1"/.test(h)
      && !h.includes("tm-react-pick"), h);
h = TM.messageHtml({ id: 21, author_kind: "agent", author_ref: "ag_lan", content: "x", meta: {} }, { members: members, picker: 21 });
check("T5 tin trợ lý: bảng cảm xúc kèm Ghim; tin đã ghim thì không lặp nút Ghim", /data-decision="21" data-on="1"/.test(h)
      && !/data-on="1"/.test(TM.messageHtml({ id: 22, author_kind: "agent", author_ref: "ag_lan", content: "x", meta: { decision: true } },
        { members: members, picker: 22 })), h);
check("T5 nút mở bảng nằm cạnh bong bóng, không thêm hàng dưới tin", (function (x) {
  return x.indexOf("tm-bubble") < x.indexOf("tm-react-btn") && !/tm-foot[^>]*>[^<]*<button type="button" class="tm-react-btn"/.test(x);
})(TM.messageHtml(am, { members: members })));
check("T5 nhấn giữ mở bảng cho mọi tin (cả tin của chủ)", teamsJs.includes('e.target.closest(".tm-msg")'));

// Trang chiếm trọn chiều cao, khung soạn một hàng ở đáy.
check("T5 console.js: trang Nhóm dùng cview-flush, body.on-teams; rời trang gỡ cả hai và báo teams.js",
      /id === "teams"[\s\S]{0,700}el\.classList\.add\("cview-flush"\);\s*document\.body\.classList\.add\("on-teams"\);/.test(consoleJs)
      && /_pageLeave = \(\) => \{\s*el\.classList\.remove\("cview-flush"\);\s*document\.body\.classList\.remove\("on-teams"\);/.test(consoleJs));
check("T5 điện thoại: bỏ đầu trang chung và linh vật trên trang Nhóm",
      /@media \(max-width: 760px\) \{[\s\S]*body\.on-teams \.cview-head \{ display: none; \}[\s\S]*body\.on-teams #javisPet \{ display: none; \}/.test(css));
check("T5 khung soạn một hàng: công tắc Giao việc, ô chữ, nút gửi; ô chữ không còn chiếm trọn hàng",
      /class="tm-mode tm-asjob" aria-pressed=/.test(teamsJs) && /textarea class="tm-input" rows="1"/.test(teamsJs)
      && !/\.tm-input \{ flex-basis: 100%; \}/.test(css) && /\.tm-row \{ display: flex; align-items: flex-end;/.test(css));
check("T5 ô chữ tự cao tới khoảng năm dòng", /Math\.min\(input\.scrollHeight \|\| 0, INPUT_MAX_PX\)/.test(teamsJs)
      && /\.tm-input \{[^}]*max-height: 132px/.test(css));
check("T5 khung soạn chừa vùng an toàn đáy máy", /\.tm-composer \{[^}]*env\(safe-area-inset-bottom/.test(css));
check("T5 lọc tin theo việc là một băng có nút Xem tất cả (bỏ ô chọn)", !teamsJs.includes("tm-filter\"") && teamsJs.includes("tm-filter-clear")
      && !teamsJs.includes('"teams.filter_all"'));
check("T5 ngăn Việc | Nhóm đóng sẵn, mở từ chip việc hay nút ba chấm; Escape và nền mờ đóng được",
      /side: false/.test(teamsJs) && /d\.openJobs/.test(teamsJs) && /tm-gear/.test(teamsJs) && /e\.key === "Escape" && S\.side/.test(teamsJs)
      && /\.tm-scrim \{ display: block; position: fixed;/.test(css));
const t5Hidden = [".tm-jobs", ".tm-jcard", ".tm-filterbar", ".tm-mact", ".tm-mrow", ".tm-level", ".tm-guide", ".tm-banner",
  ".tm-late", ".tm-radios", ".tm-mode", ".tm-composer", ".tm-jobs-chip", ".tm-scrim", ".tm-hint", ".tm-foot", ".tm-msg"];
check("T5 CSS: mọi lớp flex mới có luật [hidden] riêng", t5Hidden.every(function (c) { return css.includes(c + "[hidden]"); }),
      t5Hidden.filter(function (c) { return !css.includes(c + "[hidden]"); }).join(","));
check("T5 điện thoại: vùng chạm 44px cho nút mới", /\.tm-jobs-chip,\s*\.tm-filter-clear, \.tm-banner \.ws-btn, \.tm-adv-sum, \.tm-decision, \.tm-jmore \{ min-height: 44px; \}/.test(css)
      && /\.tm-send \{ width: 44px; height: 44px; \}/.test(css));
const t5keys = ["teams.needs_you", "teams.guide_title", "teams.act.extend", "teams.level_title", "teams.level_2_desc", "teams.advanced",
  "teams.tab_team", "teams.usage_today", "teams.filter_on", "teams.extended"];
check("T5 khoá mới có ở cả vi và en", t5keys.every(function (k) { return vi[k] && en[k]; }));
check("T5 chữ hiện ra không còn 'trần', 'lượt model', 'Toàn quyền' ở phần chính (Nâng cao thì được)",
      ["teams.block.cap_reached", "teams.queue_empty", "teams.cap.task_turns", "teams.cap.daily_turns", "teams.daily_cap",
        "teams.level_1_desc", "teams.level_2_desc", "teams.level_3_desc", "teams.auth.title", "teams.caps"].every(function (k) {
        return !/trần|lượt model|Toàn quyền/i.test(vi[k]); }));

// ───────────── Review T5 ─────────────
check("review T5: địa chỉ email không thành @ (tốn một lượt model); @ phải đứng đầu chữ hay sau ký tự không phải chữ",
      TM.mentionsFromText("gửi ho@lan.vn nhé", mem3).length === 0 && TM.mentionsFromText("(@Lan) xem", mem3).join() === "ag_lan"
      && TM.mentionsFromText("@lan", mem3).join() === "ag_lan");
check("review T5: chữ gõ tổ hợp (NFD) vẫn so đúng, dấu rời không bị coi là hết tên",
      TM.mentionsFromText("@Cũ ơi", [{ agent_key: "ag_x", slug: "x", name: "Cũ", status: "active" }]).join() === "ag_x"
      && TM.mentionsFromText("@Lañ", mem3).length === 0);
h = TM.messageHtml({ id: 30, author_kind: "owner", content: "Chốt", meta: { decision: true } }, { members: members, picker: 30 });
check("review T5 I5: tin của chủ đã ghim không có nút ba chấm (bảng của nó trống)", !h.includes("tm-more-btn"), h);
check("review T5 I5: nhấn giữ tin của chủ đã ghim không mở bảng; bảng không còn thì bỏ trạng thái mở để tin mới vẫn tự cuộn",
      /tm-msg-owner"\) && msg\.querySelector\("\.tm-decision"\)\) return;/.test(teamsJs)
      && /if \(S\.picker !== null && !box\.querySelector\('\[data-panel="' \+ S\.picker \+ '"\]'\)\) S\.picker = null;/.test(teamsJs));
check("review T5 I4: mô tả mức 3 không hứa bỏ giới hạn", !/không bị chặn|without number limits/i.test(vi["teams.level_3_desc"] + en["teams.level_3_desc"])
      && vi["teams.level_3_desc"].includes("tự nâng"));
check("review T5 I3: ngăn kéo bắt đầu dưới thanh trên toàn cục; trang trượt lên theo chiều cao khung nhìn thật",
      /\.tm-side \{ position: fixed; top: var\(--topbar-h\);/.test(css) && /height: min\(88vh, calc\(var\(--vv-h, 100dvh\) - var\(--topbar-h\) - 12px\)\)/.test(css));
check("review T5: đang gõ trong ô chữ của ngăn thì sự kiện nhóm không vẽ lại ngăn (mất chữ đang gõ)",
      /function drawSide\(force\) \{[\s\S]{0,400}if \(!force && S\.side && !side\.hidden && typingIn\(side\)\) return;/.test(teamsJs)
      && /a\.tagName === "INPUT" && !\/\^\(radio\|checkbox\|button\|submit\)\$\/i\.test/.test(teamsJs));
check("review T5: Cho thêm lượt lỗi thì vẽ lại dải việc (nút không kẹt tắt); đổi mức lỗi thì vẽ lại lựa chọn",
      /"\/extend"\)\)\.then\(function \(r\) \{\s*if \(r\.code !== 200\) \{ fail\(r\); drawJobs\(\); loadQueue\(\); return; \}/.test(teamsJs)
      && /if \(r\.code !== 200\) \{ fail\(r\); drawSide\(true\); return; \}/.test(teamsJs));
check("review T5: sổ lượt về muộn sau khi đổi nhóm thì bỏ", /function loadTurns\(\) \{[\s\S]{0,200}var forTeam = S\.activeId;[\s\S]{0,200}S\.activeId !== forTeam/.test(teamsJs));
h = TM.levelsHtml(Object.assign({}, team));
check("review T5: ba mức là một nhóm lựa chọn có tên (fieldset, legend)", /<fieldset class="tm-levels"><legend class="tm-qhead">/.test(h), h);
check("review T5: nút mở ngăn có aria-expanded; đóng ngăn trả focus về đúng nút đã mở", /tm-gear" aria-expanded=/.test(teamsJs)
      && /data-open-jobs="1" aria-expanded=/.test(teamsJs) && /S\.sideOpener/.test(teamsJs) && /role="tabpanel"/.test(teamsJs));
check("review T5: nhãn việc dài cắt bằng dấu ba chấm ở phần chữ", /class="tm-tag-text"/.test(TM.messageHtml({ id: 31, author_kind: "agent",
  author_ref: "ag_lan", content: "x", task_id: "t_1", meta: {} }, ctx)) && /\.tm-tag-text \{[^}]*text-overflow: ellipsis/.test(css));
check("review T5: công tắc thành viên và nút chọn trạng thái đủ 44px trên điện thoại", /\.tm-rs, \.tm-radio \{ min-height: 44px; \}/.test(css));
const dead = ["teams.empty", "teams.waiting_owner", "teams.running_n", "teams.waiting_n", "teams.retry", "teams.cap_hint",
  "teams.tab_turns", "teams.tab_settings", "teams.filter_all"];
check("review T5: bỏ khoá chữ không còn dùng", dead.every(function (k) { return !(k in vi) && !(k in en); }),
      dead.filter(function (k) { return k in vi || k in en; }).join(","));

// ───────────── Ảnh đại diện đúng ảnh trợ lý, ảnh nhóm ghép, ghim nhóm ─────────────
global.window = { JavisAvatar: { html: function (a, size) {
  return '<i class="fake-ava" data-slug="' + a.slug + '" data-shape="' + ((a.avatar || {}).shape || "") + '" data-size="' + size + '"></i>';
} } };
const fz = function (n) {
  return Array.from({ length: n }, function (_, i) { return { slug: "a" + i, name: "A" + i, avatar: { shape: "s" + i, palette: "p" } }; });
};
h = TM.teamAvatarHtml({ name: "Nhóm", faces: fz(1), member_count: 1 });
check("ảnh nhóm một người: đúng ảnh trợ lý đó", /tm-gava tm-gava-1/.test(h) && /data-slug="a0" data-shape="s0"/.test(h), h);
h = TM.teamAvatarHtml({ name: "Nhóm", faces: fz(2), member_count: 2 });
check("ảnh nhóm hai người: hai ảnh chéo nhau", /tm-gava tm-gava-2/.test(h) && (h.match(/fake-ava/g) || []).length === 2, h);
h = TM.teamAvatarHtml({ name: "Nhóm", faces: fz(3), member_count: 3 });
check("ảnh nhóm ba người: ba ảnh (kiểu tam giác)", /tm-gava tm-gava-3/.test(h) && (h.match(/fake-ava/g) || []).length === 3, h);
h = TM.teamAvatarHtml({ name: "Nhóm", faces: fz(4), member_count: 4 });
check("ảnh nhóm bốn người: lưới 2x2 đủ bốn ảnh, không ô đếm", /tm-gava tm-gava-4/.test(h) && (h.match(/fake-ava/g) || []).length === 4
      && !h.includes("tm-gava-more"), h);
h = TM.teamAvatarHtml({ name: "Nhóm", faces: fz(4), member_count: 9 });
check("ảnh nhóm hơn bốn người: ba ảnh và ô '+6' (như Zalo)", (h.match(/fake-ava/g) || []).length === 3
      && /class="tm-gava-more">\+6</.test(h), h);
check("hơn 102 người: ô đếm ghi 99+", /tm-gava-more">99\+</.test(TM.teamAvatarHtml({ name: "N", faces: fz(4), member_count: 150 })));
check("nhóm chưa có ai: chữ đầu của tên nhóm", /tm-ava tm-ava-c\d" aria-hidden="true">N</.test(TM.teamAvatarHtml({ name: "Nhóm", faces: [], member_count: 0 })));
check("ảnh nhóm suy từ thành viên khi dòng không kèm gương mặt (đầu khung chat): trưởng nhóm trước, bỏ người đã rời",
      (function (x) { return x.indexOf('data-slug="minh"') > x.indexOf('data-slug="lan"') && x.includes('data-slug="minh"'); })(
        TM.teamAvatarHtml(Object.assign({}, team, { members: [Object.assign({}, members[1]), Object.assign({}, members[0]),
          { agent_key: "ag_cu", slug: "cu", name: "Cũ", status: "left" }] }))) &&
      !TM.teamAvatarHtml(Object.assign({}, team, { members: [{ agent_key: "ag_cu", slug: "cu", name: "Cũ", status: "left" }] })).includes("cu\""));
h = TM.messageHtml({ id: 40, author_kind: "agent", author_ref: "ag_lan", content: "x", meta: {} },
  { members: [Object.assign({}, members[0], { avatar: { shape: "meo", palette: "cam" } })] });
check("tin của trợ lý dùng đúng ảnh trợ lý đang dùng", /data-slug="lan" data-shape="meo"/.test(h), h);
h = TM.membersHtml(Object.assign({}, team, { members: [Object.assign({}, members[0], { avatar: { shape: "meo", palette: "cam" } })] }), []);
check("danh sách thành viên dùng đúng ảnh trợ lý", /data-slug="lan" data-shape="meo"/.test(h), h);
h = TM.teamListHtml([Object.assign({}, team, { faces: fz(2), member_count: 2, pinned_at: 1791900000 })], "", now);
check("dòng nhóm: ảnh nhóm ghép và dấu ghim", /tm-gava tm-gava-2/.test(h) && /class="tm-pinned"/.test(h)
      && h.includes(vi["teams.pinned"]), h);
check("dòng nhóm chưa ghim: không dấu ghim", !/tm-pinned/.test(TM.teamListHtml([Object.assign({}, team, { faces: fz(1) })], "", now)));
h = TM.teamTabHtml(Object.assign({}, team, { pinned_at: 1791900000 }), [], {});
check("tab Nhóm có công tắc Ghim lên đầu danh sách, đang bật", /class="tm-pin-toggle" checked/.test(h) && h.includes(vi["teams.pin_top"]), h);
check("bật tắt ghim gọi POST /pin rồi tải lại danh sách", /tm-pin-toggle[\s\S]{0,400}teamUrl\("\/pin"\)/.test(teamsJs));
check("CSS: ảnh nhóm ghép có luật cho 1 tới 4 ảnh và ô đếm, mọi lớp flex mới có [hidden]",
      [".tm-gava-1", ".tm-gava-2", ".tm-gava-3", ".tm-gava-4", ".tm-gava-more"].every(function (c) { return css.includes(c); })
      && css.includes(".tm-gava[hidden]") && css.includes(".tm-face[hidden]"));
// Review b93c46bd #2: tin cũ của trợ lý đã rời nhóm giữ đúng ảnh và tên (sổ tác giả theo agent_key)
const ctxLeft = { members: [members[0]], authors: { ag_old: { slug: "old", name: "Người <cũ>", avatar: { shape: "sao", palette: "cam" } } } };
h = TM.messageHtml({ id: 50, author_kind: "agent", author_ref: "ag_old", content: "Tin cũ", meta: {} }, ctxLeft);
check("#2 tác giả đã rời nhóm: tin cũ vẫn đúng ảnh trợ lý và tên (escape)", /data-slug="old" data-shape="sao"/.test(h)
      && h.includes("Người &lt;cũ&gt;") && !/tm-ava tm-ava-c/.test(h), h);
check("#2 ảnh nhóm và gợi ý @ vẫn chỉ lấy thành viên đang hoạt động (không đọc sổ tác giả)",
      !TM.teamAvatarHtml(Object.assign({}, team, { members: [members[0]], authors: ctxLeft.authors })).includes('data-slug="old"')
      && TM.mentionMatches([members[0]], "", []).every(function (m) { return m.agent_key !== "ag_old"; })
      && /authors: S\.team \? S\.team\.authors/.test(teamsJs));
h = TM.messageHtml({ id: 51, author_kind: "agent", author_ref: "ag_x", content: "Tin cũ", meta: {} },
  { members: [], authors: { ag_x: { slug: "minh", name: "minh", avatar: null, avatar_seed: "ag_x" } } });
check("4f6268bd #1 tác giả cũ chưa có ảnh chụp: ảnh suy từ chính mã (không trùng ảnh mặc định của trợ lý mới cùng slug)",
      /data-slug="ag_x"/.test(h) && !/data-slug="minh"/.test(h), h);
delete global.window;

// Review 4f6268bd #2: lỗi ghim từ danh sách phải NHÌN THẤY ở danh sách trên điện thoại (khung chat bị ẩn), kèm Thử lại
const shellSrc = teamsJs.slice(teamsJs.indexOf("function shell()"), teamsJs.indexOf("function drawList()"));
check("4f6268bd #2 vùng thông báo nằm ngoài khung chat (con trực tiếp của trang), là vùng đọc cho trình đọc màn hình",
      /<div class="tm-scrim" hidden><\/div><div class="tm-note" role="status" aria-live="polite" hidden><\/div><\/div>/.test(shellSrc)
      && (shellSrc.match(/tm-note/g) || []).length === 1, shellSrc);
check("4f6268bd #2 CSS: thông báo là lớp nổi trên cả trang (không bị ẩn cùng khung chat ở danh sách điện thoại), có [hidden]",
      /\.tm-page > \.tm-note \{[^}]*position: absolute;[^}]*z-index: 45/.test(css) && css.includes(".tm-note[hidden]")
      && !/data-view="list"\][^{]*\.tm-note/.test(css));
check("thông báo kèm nút Thử lại và nút đóng, chữ được escape", (function (x) {
  return x.includes("Lỗi &lt;b&gt;") && /class="ws-btn tm-note-retry"/.test(x) && /class="tm-note-close"/.test(x) && x.includes(vi["teams.retry_action"]);
})(TM.noteHtml("Lỗi <b>", true)) && !TM.noteHtml("Đã lưu", false).includes("tm-note-retry"));
check("4f6268bd #2 pinTeam của trang dùng pinTeamWith với setNote (vùng thông báo chung)",
      /function pinTeam\(id, on, btn\) \{\s*return pinTeamWith\(id, on, btn,/.test(teamsJs));

// Review tích hợp 0.140.0: bấm thư về việc nhóm (kênh team:<id>) phải mở ĐÚNG nhóm ở trang Nhóm, không đổ vào khung chat
// của bộ não chính (gõ ở đó sẽ ghi tin không tác giả vào phiên nhóm).
const notiJs = fs.readFileSync(path.join(ROOT, "dashboard", "notifications.js"), "utf8");
check("hộp thư nhận ra thư của nhóm (kênh team:) và mở nhóm đó ở trang Nhóm, trước nhánh mở khung chat chính",
      /\/\^team:\(\.\+\)\$\/\.exec/.test(notiJs) && /window\.JavisTeams\.open\(nhom\)/.test(notiJs)
      && notiJs.indexOf("JavisTeams.open(") < notiJs.indexOf("window.JavisSessions.open(item.session_id)"));
check("JavisTeams.open: đang ở trang Nhóm thì mở ngay; chưa thì ghi nhớ, sang trang Nhóm, mở sau khi tải danh sách",
      typeof TM.open === "function" && /function open\(teamId, taskId\) \{[\s\S]{0,600}pendingOpen = /.test(teamsJs)
      && /JavisNav\.go\("teams"\)/.test(teamsJs) && /if \(pendingOpen\) \{[\s\S]{0,200}openTeam\(/.test(teamsJs));
check("console.js không còn nhãn số giữ chỗ 0.111.0", !consoleJs.includes("0.111.0"));

// Ghim ngay trên danh sách: máy tính rê chuột hiện nút ghim, chuột phải hay nhấn giữ (điện thoại) mở menu Ghim / Bỏ ghim
const tPin = Object.assign({}, team, { pinned_at: 1791900000 }), tPlain = Object.assign({}, team, { team_id: "tm_2", pinned_at: null });
h = TM.teamListHtml([tPin, tPlain], "tm_1", now);
check("dòng nhóm vẫn là nút mở nhóm (đánh dấu nhóm đang mở) và có nút ghim riêng bên cạnh, không lồng nút",
      /data-team="tm_1"[^>]*aria-current="true"/.test(h) && /<div class="tm-team-wrap">/.test(h)
      && /<\/button><button type="button" class="tm-row-pin" data-pin-team="tm_1" data-on="0" aria-label="[^"]+"/.test(h)
      && /class="tm-row-pin" data-pin-team="tm_2" data-on="1"/.test(h), h);
check("nút ghim ghi đúng việc sẽ làm: Bỏ ghim cho nhóm đã ghim, Ghim nhóm cho nhóm chưa ghim",
      h.includes('data-on="0" aria-label="' + vi["teams.unpin_team"]) && h.includes('data-on="1" aria-label="' + vi["teams.pin_team"]), h);
check("chưa mở menu: không có menu", !h.includes("tm-row-menu"));
h = TM.teamListHtml([tPin, tPlain], "", now, "tm_2");
check("mở menu của một nhóm: đúng một menu, một mục Ghim nhóm", (h.match(/class="tm-row-menu"/g) || []).length === 1
      && /role="menu"[\s\S]*role="menuitem" data-pin-team="tm_2" data-on="1"/.test(h) && h.includes(vi["teams.pin_team"]), h);
check("nhấn giữ dòng nhóm mở menu, chặn cú bấm mở nhóm ngay sau đó; chuột phải mở menu; Escape đóng menu",
      /var row = e\.target\.closest && e\.target\.closest\("\.tm-team"\);[\s\S]{0,400}S\.swallowClick = true;\s*openRowMenu\(row\.getAttribute\("data-team"\)\)/.test(teamsJs)
      && /if \(d\.team && S\.swallowClick\) \{ S\.swallowClick = false; return; \}/.test(teamsJs)
      && /"contextmenu"[\s\S]{0,500}\.tm-team"\);\s*if \(row\) \{ e\.preventDefault\(\); openRowMenu/.test(teamsJs)
      && /e\.key === "Escape" && S\.rowMenu/.test(teamsJs) && /function openRowMenu\(id\) \{\s*S\.rowMenu = id;/.test(teamsJs));
check("ghim từ danh sách dùng cùng cách lưu (lỗi thì báo, không kẹt)", /function pinTeamWith\(id, on, btn, deps\)[\s\S]{0,500}savePin\(/.test(teamsJs)
      && /\/teams\/" \+ q\(id\) \+ "\/pin"/.test(teamsJs));
check("CSS: nút ghim hiện khi rê chuột hay focus, máy chạm ẩn (dùng nhấn giữ); menu có [hidden], mục menu 44px",
      /\.tm-team-wrap:hover \.tm-row-pin, \.tm-row-pin:focus-visible \{ opacity: 1; \}/.test(css)
      && /@media \(hover: none\) \{ \.tm-row-pin \{ display: none; \}/.test(css) && css.includes(".tm-row-menu[hidden]")
      && css.includes(".tm-team-wrap[hidden]") && /\.tm-row-menu button \{[^}]*min-height: 44px/.test(css));
check("khoá chữ ghim có ở vi và en", ["teams.pin_team", "teams.unpin_team", "teams.row_menu"].every(function (k) { return vi[k] && en[k]; }));

// Review b93c46bd #1: công tắc ghim lưu lỗi (HTTP khác 200, lỗi mạng) thì về trạng thái đã lưu, bật lại, báo lỗi
(async function () {
  const box = function (checked) { return { checked: checked, disabled: false }; };
  let b = box(true), done = 0, failed = [];
  await TM.savePin(b, function () { return Promise.resolve({ code: 500, j: { error: "hỏng" } }); },
    function () { done++; }, function (r) { failed.push(r); });
  check("#1 HTTP 500: công tắc về chưa ghim, bật lại, báo lỗi", b.checked === false && b.disabled === false && done === 0
        && failed.length === 1 && failed[0].code === 500, JSON.stringify([b, failed]));
  b = box(false); failed = [];
  let unhandled = null;
  const onUnh = function (e) { unhandled = e; };
  process.on("unhandledRejection", onUnh);
  await TM.savePin(b, function () { return Promise.reject(new Error("offline")); }, function () { done++; },
    function (r) { failed.push(r); });
  await new Promise(function (res) { setTimeout(res, 20); });
  process.removeListener("unhandledRejection", onUnh);
  check("#1 lỗi mạng: công tắc về đã ghim, bật lại, báo lỗi mạng, không có lỗi bỏ sót", b.checked === true && b.disabled === false
        && failed.length === 1 && failed[0].network === true && unhandled === null && done === 0, JSON.stringify([b, failed, String(unhandled)]));
  b = box(true); failed = [];
  let seen = null;
  const p = TM.savePin(b, function (want) { seen = { want: want, disabled: b.disabled }; return Promise.resolve({ code: 200, j: {} }); },
    function () { done++; }, function (r) { failed.push(r); });
  await p;
  check("#1 lưu được: gửi đúng giá trị, khoá trong lúc lưu, xong thì bật lại", seen && seen.want === true && seen.disabled === true
        && b.checked === true && b.disabled === false && done === 1 && failed.length === 0, JSON.stringify([seen, b]));
  check("#1 trình xử lý công tắc dùng savePin và báo lỗi qua fail/setNote", /tm-pin-toggle[\s\S]{0,600}savePin\(/.test(teamsJs));

  // 4f6268bd #2: ghim từ danh sách (chế độ danh sách trên điện thoại) lỗi thì báo nhìn thấy kèm Thử lại
  const notes = [];
  const deps = function (resp) {
    return { post: function () { return typeof resp === "function" ? resp() : Promise.resolve(resp); },
      notify: function (text, retry) { notes.push({ text: text, retry: retry }); }, reload: function () { notes.push({ reloaded: true }); } };
  };
  await TM.pinTeamWith("tm_1", true, null, deps({ code: 500, j: { error: "Máy chủ lỗi" } }));
  check("4f6268bd #2 HTTP 500: báo lỗi nhìn thấy kèm Thử lại, không tải lại như đã ghim", notes.length === 1
        && notes[0].text.includes("Máy chủ lỗi") && typeof notes[0].retry === "function", JSON.stringify(notes));
  notes.length = 0;
  let unh = null;
  const onU = function (e) { unh = e; };
  process.on("unhandledRejection", onU);
  await TM.pinTeamWith("tm_1", true, null, deps(function () { return Promise.reject(new Error("offline")); }));
  await new Promise(function (res) { setTimeout(res, 20); });
  process.removeListener("unhandledRejection", onU);
  check("4f6268bd #2 mất mạng: báo lỗi mạng kèm Thử lại, không có lỗi bị bỏ sót", notes.length === 1 && unh === null
        && notes[0].text === vi["teams.err_network"] && typeof notes[0].retry === "function", JSON.stringify(notes));
  let calls = 0;
  const d2 = deps(function () { calls++; return Promise.resolve(calls === 1 ? { code: 503, j: {} } : { code: 200, j: {} }); });
  notes.length = 0;
  await TM.pinTeamWith("tm_1", true, null, d2);
  await notes[0].retry();
  check("4f6268bd #2 bấm Thử lại gửi lại đúng thao tác; lần sau lưu được thì tải lại danh sách", calls === 2
        && notes.some(function (n) { return n.reloaded; }), JSON.stringify(notes));
  process.exit(fails ? 1 : 0);
})();
