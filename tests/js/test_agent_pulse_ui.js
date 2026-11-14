// T3 (0.156.0): bảng Nhịp chủ động (agent-pulse.js) và sự kiện "đã xem" (pulse-seen.js).
//
//     python tests/run.py --js agent_pulse_ui -v
//
// Hàm thuần chạy dưới node: bảng theo từng ngữ cảnh (trạng thái, bậc, lần xem xét, lý do thức, đổi nhịp trước/sau và
// nguồn, phản hồi đã xử lý, nút), sổ đăng ký `JavisPulseParts` cho phần J/L, escape. Bộ đếm "đã xem" với đồng hồ giả:
// ≥ 1,5 giây trong khung nhìn khi tab hiển thị, gom lô, mỗi tin một lần, tab ẩn thì không tính, ngữ cảnh không phải của
// trợ lý thì thôi gửi. Cộng các chỗ nối: script, cột phải trang Cộng sự, dòng thành viên nhóm, khung tin nhóm, CSS, i18n.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const P = require(path.join(ROOT, "dashboard", "agent-pulse.js"));
const SEEN = require(path.join(ROOT, "dashboard", "pulse-seen.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const read = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}

const view = {
  ok: true, agent_key: "ag_1", resonance: true, tiers: [900, 3600, 14400, 86400],
  aggregate: { context_ref: "*", max_tier: 1, tier: 2 },
  contexts: [
    { context_ref: "dm:ag_1", state: "awake", tier: 3, next_due_at: 2000000000, last_eval_at: 1999990000,
      last_wake_why: "reaction", u: 0.123, confidence: 0.4, quota_wait: false },
    { context_ref: "team:tm_a", state: "active", tier: 2, next_due_at: 2000000100, last_eval_at: null, last_wake_why: "",
      u: 0.3, confidence: 0.6, quota_wait: true },
    { context_ref: "team:tm_b", state: "paused", tier: 5, next_due_at: null, last_eval_at: 1, u: -0.1, confidence: 0.2 }
  ],
  changes: [
    { id: 7, context_ref: "team:tm_a", kind: "tier_change", before: { tier: 3 }, after: { tier: 2 }, reason: "helpful",
      source: "schedule", reverted_by: null },
    { id: 6, context_ref: "dm:ag_1", kind: "tier_change", before: { tier: 3 }, after: { tier: 4 }, reason: "low_demand",
      source: "schedule", reverted_by: 9 }
  ],
  feedback: [
    { source_ref: "rx:team:1", context_ref: "team:tm_a", kind: "reaction", emoji: "love", share: 0.4, status: "live" },
    { source_ref: "rx:dm:2", context_ref: "dm:ag_1", kind: "reaction_reason", emoji: "sad", share: 1, status: "superseded" }
  ],
  parts: {}
};
const names = { tm_a: "Ra mắt <b>", tm_b: "Nội dung" };
let h = P.panelHtml(view, { teamNames: names, registry: [] });
check("bảng: mỗi ngữ cảnh một khối có tên (chat riêng, nhóm theo tên, escape)",
  h.includes(vi["pulse.ctx_dm"]) && h.includes("Ra mắt &lt;b&gt;") && !h.includes("<b>") &&
  (h.match(/class="pulse-ctx"/g) || []).length === 3, h);
check("bảng: trạng thái và bậc bằng chữ theo từng ngữ cảnh",
  h.includes(vi["pulse.state.awake"] + " · ") && h.includes(vi["pulse.tier_3"]) && h.includes(vi["pulse.state.active"])
  && h.includes(vi["pulse.tier_2"]) && h.includes(vi["pulse.state.paused"]));
check("bảng: lần xem xét gần nhất, lần dự kiến, không lịch", h.includes(vi["pulse.never"]) &&
  h.includes(vi["pulse.none_scheduled"]));
check("bảng: lý do thức gần nhất", h.includes(vi["pulse.why.reaction"]));
check("bảng: nhãn Chờ hạn mức khi máy chủ báo", h.includes(vi["pulse.quota"]));
check("bảng: nút Đánh thức, Tạm dừng/Tiếp, Đặt lại theo ngữ cảnh",
  /data-pulse-act="wake" data-ctx="dm:ag_1"/.test(h) && /data-pulse-act="pause" data-ctx="team:tm_a"/.test(h)
  && /data-pulse-act="resume" data-ctx="team:tm_b"/.test(h) && /data-pulse-act="reset" data-ctx="dm:ag_1"/.test(h));
check("bảng: ngữ cảnh tạm dừng thì nút Đánh thức khoá", /data-pulse-act="wake" data-ctx="team:tm_b" disabled/.test(h));
check("bảng: đổi nhịp gần đây có trước/sau, lý do, nguồn; chỉ lần chưa quay lại có nút Quay lại",
  h.includes(vi["pulse.tier_3"] + " → " + vi["pulse.tier_2"]) && h.includes(vi["pulse.reason.helpful"]) &&
  h.includes(vi["pulse.by_schedule"]) && /data-pulse-act="revert" data-ev="7"/.test(h) && !/data-ev="6"/.test(h));
check("bảng: phản hồi đã xử lý kèm trạng thái và phần chia", h.includes(vi["pulse.fb.status.live"]) &&
  h.includes(vi["pulse.fb.status.superseded"]) && h.includes("40%"), h);
check("bảng: chọn nhịp nhanh nhất (chủ), mặc định B1, có câu trưởng nhóm không nâng được",
  /<option value="1" selected>/.test(h) && h.includes(vi["pulse.max_tier_note"]));
check("bảng: Auto bật nói rõ", h.includes(vi["pulse.resonance_on"]));
// Review T3 P P3: chủ chọn được trần B0..B7 (không chỉ B0..B3), và quay lại một đổi chính sách đang quan sát.
check("bảng: chọn nhịp nhanh nhất có đủ B0 tới B7", [0, 1, 2, 3, 4, 5, 6, 7].every((n) =>
  h.includes('<option value="' + n + '"')) && !h.includes('<option value="8"'));
const pview = Object.assign({}, view, { policy_changes: [
  { id: 31, kind: "offset_set", context_ref: "dm:ag_1", status: "observing" },
  { id: 30, kind: "pulse_version", context_ref: "*", status: "kept" }] });
const hp = P.panelHtml(pview, { teamNames: names, registry: [] });
check("bảng: đổi chính sách đang quan sát có nút Quay lại (change_id), đã giữ thì không",
  hp.includes(vi["pulse.policy_title"]) && /data-pulse-act="revert_policy" data-change="31"/.test(hp)
  && !/data-change="30"/.test(hp) && hp.includes(vi["lessons.change.offset_set"]) && hp.includes(vi["pulse.policy.kind_other"])
  && hp.includes(vi["pulse.policy.status.kept"]), hp);
const only = P.panelHtml(view, { only: "team:tm_a", teamNames: names, registry: [] });
check("dòng thành viên nhóm: chỉ đúng ngữ cảnh của nhóm đó, không lộ chat riêng",
  (only.match(/class="pulse-ctx"/g) || []).length === 1 && !only.includes(vi["pulse.ctx_dm"]) &&
  !only.includes("pulse-max-sel"), only);
check("chưa có mã: câu hướng dẫn bật Auto", P.panelHtml({ agent_key: null, contexts: [] }, { registry: [] })
  .includes(vi["pulse.empty"]));
check("lỗi máy chủ: báo chưa lưu, không báo thành công", (function (x) {
  return x.includes(vi["pulse.error"].replace("{e}", "409")) && !x.includes(vi["pulse.done"]);
})(P.panelHtml(view, { err: "409", registry: [] })));
const reg = [{ name: "judge", render: function (v) { return "<div class=\"jx\">" + v.agent_key + "</div>"; } },
  { name: "broken", render: function () { throw new Error("x"); } }];
h = P.panelHtml(view, { registry: reg });
check("sổ đăng ký JavisPulseParts: mục của phần J/L hiện trong bảng, mục lỗi không làm hỏng bảng",
  h.includes('data-part="judge"') && h.includes("ag_1") && !h.includes('data-part="broken"'), h);
check("changeLine: sự kiện bật Auto, nguồn chủ", P.changeLine({ kind: "on", source: "owner" }).includes(vi["pulse.ev.on"])
  && P.changeLine({ kind: "on", source: "owner" }).includes(vi["pulse.by_owner"]));

// ═════ đã xem: đồng hồ giả ═════
function fakeTimers() {
  let now = 0, id = 0;
  const q = [];
  return {
    setTimeout: (fn, ms) => { q.push({ id: ++id, at: now + ms, fn }); return id; },
    clearTimeout: (x) => { const i = q.findIndex((t) => t.id === x); if (i >= 0) q.splice(i, 1); },
    advance: (ms) => {
      const end = now + ms;
      for (;;) {
        q.sort((a, b) => a.at - b.at);
        if (!q.length || q[0].at > end) break;
        const t = q.shift();
        now = t.at;
        t.fn();
      }
      now = end;
    }
  };
}

(async function () {
  let T = fakeTimers();
  let posts = [];
  let tr = SEEN.createTracker({ setTimeout: T.setTimeout, clearTimeout: T.clearTimeout, visible: true,
    post: (ctx, ids, sid) => { posts.push({ ctx, ids, sid }); return Promise.resolve({ ok: true, agent: true }); } });
  tr.enter("team:tm_a", 11, "");
  T.advance(1400);
  tr.leave("team:tm_a", 11);
  T.advance(5000);
  check("dưới 1,5 giây rồi ra khỏi khung: không báo", posts.length === 0, JSON.stringify(posts));
  tr.enter("team:tm_a", 12, "");
  tr.enter("team:tm_a", 13, "");
  tr.enter("session:s1", 5, "s1");
  T.advance(1500);
  check("đủ 1,5 giây: chưa gửi ngay (gom lô)", posts.length === 0);
  T.advance(SEEN.FLUSH_MS);
  await Promise.resolve();
  check("gom lô theo ngữ cảnh: một lần gửi mỗi ngữ cảnh, đủ tin, kèm mã phiên cho chat riêng",
    posts.length === 2 && JSON.stringify(posts.find((p) => p.ctx === "team:tm_a").ids) === "[12,13]" &&
    posts.find((p) => p.ctx === "session:s1").sid === "s1", JSON.stringify(posts));
  tr.leave("team:tm_a", 12);
  tr.enter("team:tm_a", 12, "");
  T.advance(10000);
  check("mỗi tin chỉ báo một lần", posts.length === 2, JSON.stringify(posts));

  T = fakeTimers(); posts = [];
  tr = SEEN.createTracker({ setTimeout: T.setTimeout, clearTimeout: T.clearTimeout, visible: false,
    post: (ctx, ids) => { posts.push({ ctx, ids }); return Promise.resolve({ agent: true }); } });
  tr.enter("team:tm_a", 21, "");
  T.advance(10000);
  check("tab đang ẩn: không tính thời gian, không báo", posts.length === 0);
  tr.setVisible(true);
  T.advance(1000);
  tr.setVisible(false);
  T.advance(10000);
  check("tab ẩn giữa chừng: hẹn giờ dừng, không báo", posts.length === 0);
  tr.setVisible(true);
  T.advance(1500 + SEEN.FLUSH_MS);
  await Promise.resolve();
  check("tab hiển thị lại đủ 1,5 giây liên tục: báo", posts.length === 1 && posts[0].ids[0] === 21, JSON.stringify(posts));

  T = fakeTimers(); posts = [];
  tr = SEEN.createTracker({ setTimeout: T.setTimeout, clearTimeout: T.clearTimeout, visible: true,
    post: (ctx, ids) => { posts.push({ ctx, ids }); return Promise.resolve({ agent: false }); } });
  tr.enter("session:main", 1, "main");
  T.advance(1500 + SEEN.FLUSH_MS);
  await Promise.resolve(); await Promise.resolve();
  tr.enter("session:main", 2, "main");
  T.advance(1500 + SEEN.FLUSH_MS);
  check("máy chủ nói không phải ngữ cảnh của trợ lý (trang Trò chuyện chính): thôi gửi cho ngữ cảnh đó",
    posts.length === 1 && tr.state().muted.indexOf("session:main") >= 0, JSON.stringify(posts));

  T = fakeTimers(); posts = [];
  let failOnce = true;
  tr = SEEN.createTracker({ setTimeout: T.setTimeout, clearTimeout: T.clearTimeout, visible: true,
    post: (ctx, ids) => { posts.push(ids); if (failOnce) { failOnce = false; return Promise.reject(new Error("net")); }
      return Promise.resolve({ agent: true }); } });
  tr.enter("team:tm_a", 31, "");
  T.advance(1500 + SEEN.FLUSH_MS);
  await Promise.resolve(); await Promise.resolve();
  tr.leave("team:tm_a", 31);
  tr.enter("team:tm_a", 31, "");
  T.advance(1500 + SEEN.FLUSH_MS);
  check("lỗi mạng: lần thấy sau báo lại (không mất sự kiện)", posts.length === 2, JSON.stringify(posts));

  // contextOf: chỉ tin của trợ lý trong nhóm (cần mã nhóm của khung) và bong bóng trả lời có mã phiên.
  function el(cls, attrs, box) {
    return { classList: { contains: (c) => cls.split(" ").indexOf(c) >= 0 },
      getAttribute: (k) => (attrs[k] == null ? null : String(attrs[k])),
      closest: () => box || null };
  }
  const box = { getAttribute: (k) => (k === "data-seen-team" ? "tm_a" : null) };
  check("contextOf: tin trợ lý trong khung nhóm", JSON.stringify(SEEN.contextOf(el("tm-msg tm-msg-agent", { "data-mid": 9 }, box)))
    === JSON.stringify({ ctx: "team:tm_a", mid: 9, sid: "" }));
  check("contextOf: tin của chủ trong nhóm không theo dõi", SEEN.contextOf(el("tm-msg tm-msg-owner", { "data-mid": 9 }, box))
    === null);
  check("contextOf: bong bóng trả lời chat riêng", SEEN.contextOf(el("msg-javis", { "data-mid": 4, "data-sid": "s9" })).ctx
    === "session:s9");
  check("contextOf: phần tử khác không theo dõi", SEEN.contextOf(el("msg-user", { "data-mid": 4, "data-sid": "s9" })) === null);

  // ═════ đề xuất: bảng Nhịp và thẻ trong nhóm ═════
  const pv = Object.assign({}, view, { proposals: [
    { id: 5, context_ref: "dm:ag_1", title: "Hỏi lại <mục tiêu>", brief: "chờ hai ngày", status: "pending" },
    { id: 4, context_ref: "team:tm_a", title: "Cập nhật việc", brief: "", status: "rejected" }] });
  const ph = P.panelHtml(pv, { teamNames: names, registry: [] });
  check("bảng: đề xuất chờ có nút Nhận thành việc và Bác, escape tiêu đề",
    /data-pulse-act="proposal_accept" data-pid="5"/.test(ph) && /data-pulse-act="proposal_reject" data-pid="5"/.test(ph)
    && ph.includes("Hỏi lại &lt;mục tiêu&gt;") && ph.includes(vi["pulse.btn.accept"]), ph);
  check("bảng: đề xuất đã bác chỉ còn trạng thái, không nút", !/data-pid="4"/.test(ph) && ph.includes(vi["pulse.prop.status.rejected"]));
  const TM = require(path.join(ROOT, "dashboard", "teams.js"));
  const mem = [{ agent_key: "ag_lan", slug: "lan", name: "Lan", role: "leader", status: "active" }];
  const cx = { members: mem, leaderKey: "ag_lan", taskTitles: {} };
  const card = (st) => TM.messageHtml({ id: 8, author_kind: "agent", author_ref: "ag_lan", content: "Đề xuất",
    meta: { role: "leader_reply", status: "done", proposal: { title: "Bản tin" }, proposal_status: st } }, cx);
  check("thẻ đề xuất nhóm còn chờ: Tạo việc và Bỏ qua", /data-accept="8"/.test(card(undefined)) && /data-skip="8"/.test(card(undefined)));
  check("thẻ đã bác: hết nút, nói rõ đã bác", !/data-skip="8"/.test(card("rejected")) && card("rejected").includes(vi["teams.proposal_rejected"]));
  check("thẻ đã thành việc: hết nút, nói rõ", !/data-accept="8"/.test(card("accepted")) && card("accepted").includes(vi["teams.proposal_accepted"]));
  const tsrc = read("teams.js");
  check("Bỏ qua gọi máy chủ bác đề xuất và chỉ vẽ lại sau 200", /if \(d\.skip\) \{\s*return call\("POST", teamUrl\("\/messages\/" \+ q\(d\.skip\) \+ "\/reject"\)\)\.then\(function \(r\) \{\s*if \(r\.code !== 200\) return fail\(r\);/.test(tsrc));
  check("bảng Nhịp: nút đề xuất gọi proposals/<id>/accept|reject", read("agent-pulse.js").includes('"proposals/" + encodeURIComponent(pid)'));

  // ═════ chỗ nối ═════
  const idx = read("index.html"), ws = read("workspace.js"), tm = read("teams.js"), css = read("console.css");
  check("index.html nạp agent-pulse.js và pulse-seen.js", idx.includes("/static/agent-pulse.js?v=") &&
    idx.includes("/static/pulse-seen.js?v="));
  check("trang Cộng sự: khung #wsPulse dưới Cộng hưởng và gắn JavisPulse.mount", ws.includes('id="wsPulse"') &&
    ws.includes("JavisPulse.mount(ph"));
  check("ngăn Nhóm: dòng thành viên mở ra có nhịp đúng nhóm (only: team:<id>)", tm.includes("data-pulse-ctx=\"team:") &&
    tm.includes("only: el.getAttribute(\"data-pulse-ctx\")"));
  check("khung tin nhóm mang mã nhóm cho sự kiện đã xem", tm.includes('setAttribute("data-seen-team"'));
  check("bảng giới hạn: dòng max_tier và dự trữ 20% có nhãn", tm.includes("max_tier: \"teams.limits.max_tier\"") &&
    tm.includes("autonomous_reserve: \"teams.limits.autonomous_reserve\""));
  check("CSS: chữ 16px, nút 44px, xuống dòng ở màn hẹp, màu theo token",
    /\.pulse-panel \{ font-size: 16px; \}/.test(css) && /\.pulse-acts \.ws-btn, \.pulse-list \.ws-btn \{ min-height: 44px/.test(css)
    && /\.pulse-acts \{ display: flex; flex-wrap: wrap/.test(css) && !/\.pulse-[a-z-]+ \{[^}]*#[0-9a-f]{3,6}/i.test(css));
  const pulseSrc = read("agent-pulse.js") + read("pulse-seen.js");
  const used = Array.from(new Set((pulseSrc.match(/tw\("([a-z_.0-9]+)"/g) || []).map((s) => s.slice(4, -1))))
    .filter((k) => !/[._]$/.test(k));   // tiền tố ghép động (pulse.tier_ + n) kiểm bằng danh sách `dyn`
  const dyn = ["pulse.state.active", "pulse.state.awake", "pulse.state.slowed", "pulse.state.hibernating",
    "pulse.state.waiting_owner", "pulse.state.paused", "pulse.state.off", "pulse.tier_0", "pulse.tier_8", "pulse.why.manual",
    "pulse.ev.tier_change", "pulse.ev.policy_revert", "pulse.reason.low_demand", "pulse.fb.kind.seen_ignored",
    "pulse.fb.status.void", "pulse.percent"];
  const miss = used.concat(dyn).filter((k) => !(k in vi) || !(k in en));
  check("mọi khoá i18n dùng tới có ở cả vi và en", miss.length === 0, miss.join(", "));
  check("chữ tiếng Việt có dấu (không chữ không dấu)", vi["pulse.btn.wake"] === "Đánh thức" && vi["pulse.state.slowed"] === "Giảm nhịp");
  const dashes = Object.entries(vi).concat(Object.entries(en)).filter(([k, v]) => k.startsWith("pulse.") &&
    /[\u2013\u2014]/.test(v));
  check("không em dash, en dash trong chữ mới", dashes.length === 0 && !/[\u2013\u2014]/.test(pulseSrc));

  // 2026-11-14 (Auto toàn quyền): mốc trợ lý tự hẹn hiện trên bảng đầy đủ và bản gọn, có escape, lọc theo ngữ cảnh.
  const fu = Object.assign({}, view, { followups: [
    { id: 1, context_ref: "dm:ag_1", due_at: 2000000000, note: "Kiểm bãi gửi xe <b>" },
    { id: 2, context_ref: "team:tm_a", due_at: 2000003600, note: "Hỏi tiến độ" }] });
  const full = P.panelHtml(fu, {});
  check("mốc tự hẹn: bảng đầy đủ có tiêu đề và ghi chú đã escape", full.includes(vi["pulse.followups_title"])
    && full.includes("Kiểm bãi gửi xe &lt;b&gt;") && !full.includes("<b>"));
  const only = P.panelHtml(fu, { only: "team:tm_a" });
  check("mốc tự hẹn: hàng một ngữ cảnh chỉ vẽ mốc của ngữ cảnh đó", only.includes("Hỏi tiến độ")
    && !only.includes("Kiểm bãi gửi xe"));
  check("mốc tự hẹn: bản gọn cũng hiện", P.compactHtml(fu, { registry: [] }).includes("Kiểm bãi gửi xe"));
  check("không có mốc: không vẽ mục", P.followupsHtml([], {}) === "" && !P.panelHtml(view, {}).includes(vi["pulse.followups_title"]));

  console.log(fails ? `\n${fails} FAIL` : "\nALL OK");
  process.exit(fails ? 1 : 0);
})();
