// 0.142.0 (bổ sung sau review đầy đủ): tab Công việc của trợ lý.
// Lọc nguồn + phân trang, thẻ có thời gian cập nhật và bước kế tiếp, bốn vai, form Giao việc hai bước (tiêu chí, nơi
// nhận kết quả, kiểu Kiểm chứng), Giao kiểm chứng từ thẻ, Tiếp tục / Huỷ kèm revision, Ưu tiên của nhóm, đồng bộ trực
// tiếp (nghe sự kiện, gộp nhịp, gỡ khi rời), huy hiệu việc trên thẻ trợ lý.
//
//     python tests/run.py --js agent_jobs_0142 -v
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
// Khoá mới của bản này: lấy từ file i18n thật; khi chưa gộp thì đọc bản phủ ở scratchpad (biến môi trường).
const overlayPath = process.env.JAVIS_JOBS_I18N || "";
const overlay = overlayPath && fs.existsSync(overlayPath) ? JSON.parse(fs.readFileSync(overlayPath, "utf8")) : { vi: {}, en: {} };
const S = Object.assign({}, vi, overlay.vi);
const src = fs.readFileSync(path.join(ROOT, "dashboard", "agent-jobs.js"), "utf8");
const ws = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 600)));
  if (!cond) fails++;
}
function T(k, v) {
  let s = S[k] || k;
  if (v) s = s.replace(/\{(\w+)\}/g, (m, n) => (n in v ? String(v[n]) : m));
  return s;
}

// ───────────── môi trường giả: window, timer, fetch ─────────────
const winL = {};
global.window = {
  addEventListener(t, f) { (winL[t] = winL[t] || []).push(f); },
  removeEventListener(t, f) { winL[t] = (winL[t] || []).filter((x) => x !== f); },
  dispatchEvent(e) { (winL[e.type] || []).slice().forEach((f) => f(e)); return true; },
};
global.document = { activeElement: null, hidden: false };
global.confirm = () => true;
const timers = [];
let intervals = [];
global.setTimeout = (fn, ms) => { const h = { fn, ms, cleared: false }; timers.push(h); return h; };
global.clearTimeout = (h) => { if (h) h.cleared = true; };
global.setInterval = (fn, ms) => { const h = { fn, ms, cleared: false, unref() { this.unrefd = true; } }; intervals.push(h); return h; };
global.clearInterval = (h) => { if (h) h.cleared = true; };
function runTimers() { const due = timers.splice(0); due.forEach((h) => { if (!h.cleared) h.fn(); }); }
const flush = () => new Promise((r) => setImmediate(r));

let calls = [];
let respond = () => ({ ok: true });
global.fetch = function (url, o) {
  calls.push({ url, o: o || {} });
  const j = respond(url, o || {});
  return Promise.resolve({ ok: j.ok !== false, status: j.ok === false ? 400 : 200, json: () => Promise.resolve(j) });
};

const AJ = require(path.join(ROOT, "dashboard", "agent-jobs.js"));
AJ.setStrings(S);

// ───────────── vẽ thuần ─────────────
const now = 2_000_000_000;
const job = (o) => Object.assign({ id: "kanban:k1", source: "chat", title: "Email", bucket: "waiting", roles: ["worker"],
  open: { kind: "chat", session_id: "s1" }, updated_at: now - 300 }, o);
let h = AJ.jobHtml(job({}), { now });
check("thẻ có thời gian cập nhật tương đối (5 phút trước)", h.includes(T("ajobs.updated", { when: T("noti.ago_min", { count: 5 }) })), h);
check("relTime: vừa xong, giờ, ngày", AJ.relTime(now - 10, now) === T("noti.ago_now")
  && AJ.relTime(now - 7200, now) === T("noti.ago_hour", { count: 2 }) && AJ.relTime(now - 86400 * 3, now) === T("noti.ago_day", { count: 3 }));
const nexts = [
  [{ code: "queue", n: 2, team: "Ra mắt" }, T("ajobs.next.queue", { n: 2, team: "Ra mắt" })],
  [{ code: "busy", team: "Hậu cần" }, T("ajobs.next.busy", { team: "Hậu cần" })],
  [{ code: "needs_you", reason: "Thiếu số liệu" }, T("ajobs.next.needs_you", { reason: "Thiếu số liệu" })],
  [{ code: "board_off" }, T("ajobs.next.board_off")],
  [{ code: "agent_busy" }, T("ajobs.next.agent_busy")],
  [{ code: "resume" }, T("ajobs.next.resume")]];
check("bước kế tiếp đọc bằng lời cho mọi mã server trả", nexts.every(([n, txt]) => AJ.nextText({ next: n }) === txt && !/ajobs\./.test(txt)),
  JSON.stringify(nexts.map(([n]) => AJ.nextText({ next: n }))));
h = AJ.jobHtml(job({ bucket: "needs_you", reason: "Thiếu <b>", next: { code: "needs_you", reason: "Thiếu <b>" } }), {});
check("Cần bạn: 'Chờ bạn: lý do' (escape), không lặp dòng lý do", h.includes("aj-next") && h.includes("Thiếu &lt;b&gt;")
  && !h.includes("aj-reason"), h);
h = ["coordinator", "worker", "helper", "verifier", "verifier_legacy", "assignee", "owner", "reviewer"]
  .map((r) => AJ.jobHtml(job({ roles: [r] }), {})).join("");
check("vai: Điều phối, Thực hiện, Hỗ trợ, Kiểm chứng; mã cũ cũng ra nhãn mới",
  ["Điều phối", "Thực hiện", "Hỗ trợ", "Kiểm chứng", "Kiểm chứng (kiểu cũ)"].every((x) => h.includes(">" + x + "<"))
  && !/Được giao|Làm một phần|Tự làm \(Auto\)|Đang review/.test(h), h.match(/aj-role[^<]*<\/span>/g));
h = AJ.jobHtml(job({ kind: "verify", roles: ["verifier"], link: { id: "team:t9", title: "Bản <tổng hợp>",
  open: { kind: "team", team_id: "tm1", task_id: "t9" } } }), { canVerify: true });
check("việc kiểm chứng: hiện mục được kiểm (escape) và nút mở; không có Giao kiểm chứng cho chính nó",
  h.includes("Bản &lt;tổng hợp&gt;") && /data-aj-link="kanban:k1"/.test(h) && !/data-aj-verify=/.test(h), h);
h = AJ.jobHtml(job({ id: "goal:g1", source: "auto", resume: { goal_id: "g1", revision: 4 },
  cancel: { kind: "goal", goal_id: "g1", revision: 4 } }), { canVerify: true });
check("mục tiêu đang dừng: Tiếp tục, Huỷ, Giao kiểm chứng", /data-aj-resume="goal:g1"/.test(h) && /data-aj-cancel="goal:g1"/.test(h)
  && /data-aj-verify="goal:g1"/.test(h), h);
h = AJ.jobHtml(job({ id: "team:t1", source: "team", priority: { kind: "team", team_id: "tm1", task_id: "t1", on: true, version: 3 } }), {});
check("việc chờ trong nhóm: nút Ưu tiên", h.includes(T("ajobs.prio_on")) && /data-aj-prio="team:t1"/.test(h), h);

const data = { ok: true, board: "auto", max_workers: 2, errors: [], next: "30", total: 45,
  counts: { running: 1, waiting: 3, needs_you: 0, done: 41 }, counts_partial: { done: true },
  source_counts: { team: 10, chat: 30, auto: 5 }, teams: [{ team_id: "tm1", name: "Ra mắt <x>" }],
  jobs: [job({}), job({ id: "team:t1", source: "team", source_label: "Ra mắt", bucket: "running" })] };
h = AJ.html(data, { name: "Minh" });
check("source select: All sources, Teams, Private chat, Auto with counts",
  /<option value="" selected>[^<]*\(45\)<\/option>/.test(h) && /<option value="team">[^<]*\(10\)<\/option>/.test(h)
  && h.includes(T("ajobs.srcf.chat")) && /<option value="auto">/.test(h), h.slice(0, 1500));
check("Done count says '+' while more history exists (no fake number)", /<option value="done">[^<]*\(41\+\)<\/option>/.test(h), h);
check("còn trang sau: nút Xem thêm", h.includes("aj-more") && h.includes(T("ajobs.more")));
check("hết trang: không có Xem thêm", !AJ.html(Object.assign({}, data, { next: null }), {}).includes("aj-more"));

// Form Giao việc.
h = AJ.assignHtml({ assignOpen: true, name: "Minh", kind: "task", target: "chat" }, data);
check("form: Yêu cầu, Tiêu chí xong, Nơi nhận kết quả (chat riêng + nhóm của trợ lý), Việc thường / Kiểm chứng",
  h.includes(T("ajobs.req_label")) && h.includes("aj-crit") && h.includes(T("ajobs.dest_chat", { name: "Minh" }))
  && h.includes('value="team:tm1"') && h.includes("Ra mắt &lt;x&gt;") && /data-aj-kind="verify"/.test(h) && h.includes("aj-assign-next"), h);
h = AJ.assignHtml({ assignOpen: true, name: "Minh", kind: "verify", targets: [{ id: "goal:g2", title: "Báo cáo", name: "Lan" }] }, data);
check("Kiểm chứng: tiêu chí bắt buộc, chọn mục của trợ lý khác", h.includes(T("ajobs.crit_label_req")) && h.includes('value="goal:g2"')
  && h.includes(T("ajobs.link_option", { title: "Báo cáo", name: "Lan" })), h);
h = AJ.confirmHtml({ name: "Minh", kind: "task", draft: "Soạn <email>", criteria: "Đủ ý", target: "team:tm1" }, data);
check("bước xác nhận: giao cho ai, tiêu chí, kết quả về đâu; Xác nhận / Sửa",
  h.includes(T("ajobs.sum_to", { name: "Minh", text: "Soạn &lt;email&gt;" })) && h.includes(T("ajobs.sum_crit", { crit: "Đủ ý" }))
  && h.includes(T("ajobs.sum_dest", { dest: T("ajobs.dest_team", { name: "Ra mắt &lt;x&gt;" }) }))
  && h.includes("aj-assign-send") && h.includes("aj-assign-edit"), h);

// Huy hiệu việc trên thẻ trợ lý.
check("huy hiệu: không có việc thì rỗng", AJ.badgeHtml(null) === "" && AJ.badgeHtml({ running: 0, needs_you: 0 }) === "");
h = AJ.badgeHtml({ running: 2, needs_you: 1 });
check("huy hiệu: số Đang làm và Cần bạn, có nhãn đọc được", h.includes("ws-jb-run")
  && /ws-jb-run">[^<]*2</.test(h) && /ws-jb-need">[^<]*1</.test(h) && h.includes(T("ajobs.badge_aria", { running: 2, needs: 1 })), h);
check("thẻ trợ lý vẽ huy hiệu ở ô riêng, tách khỏi công tắc Auto",
  /badgeHtml\(S\.jc\[x\.slug\]\)/.test(ws) && ws.indexOf("badgeHtml(S.jc[x.slug])") < ws.indexOf("rowToggleHtml(S.rs[x.slug]"));
check("huy hiệu tải lại theo cùng sự kiện với tab Công việc", /\["javis:team-event", "javis:sessions-changed", "javis:agent-jobs-changed"\]/.test(ws)
  && /function henDemViec\(\)[\s\S]{0,800}800\)/.test(ws));
check("rời trang Cộng sự gỡ tab Công việc", /function roi\(\) \{[\s\S]{0,400}_congViec\.destroy\(\); _congViec = null;/.test(ws));

// ───────────── gắn thật: lọc, phân trang, thao tác, đồng bộ trực tiếp ─────────────
function fakeHost() {
  const L = {};
  return { innerHTML: "", isConnected: true, L,
    addEventListener(t, f) { (L[t] = L[t] || []).push(f); },
    querySelector() { return null; }, contains() { return true; },
    fire(t, target) { (L[t] || []).forEach((f) => f({ type: t, target })); } };
}
function btn(cls, dataset) {
  const b = { dataset: dataset || {}, classList: { contains: (c) => c === cls } };
  b.closest = () => b;
  return b;
}
function field(cls, value) { return { classList: { contains: (c) => c === cls }, value }; }

// Compact toolbar (0.158.0): two native selects instead of two scrolling chip rows.
{
  const data = { counts: { running: 1, waiting: 2, needs_you: 3, done: 4 }, source_counts: { team: 1, chat: 2, auto: 0 } };
  const tb = AJ.toolbarHtml(data, { source: "", filter: "" });
  check("toolbar has a source select and a status select",
    /<select class="aj-sel aj-tb-sel aj-src-sel"/.test(tb) && /<select class="aj-sel aj-tb-sel aj-status-sel"/.test(tb), tb);
  // draw() restores focus by id only: without ids a keyboard user loses focus after each change.
  check("both selects have stable ids so keyboard focus survives a redraw",
    /<select [^>]*id="ajSrcSel"/.test(tb) && /<select [^>]*id="ajStatusSel"/.test(tb), tb);
  check("options carry their counts (sources 3, statuses 10)", tb.indexOf("(3)</option>") !== -1 && tb.indexOf("(10)</option>") !== -1, tb);
  check("the selected option follows the ui state",
    /value="needs_you" selected/.test(AJ.toolbarHtml(data, { source: "", filter: "needs_you" })));
  check("amber dot when something needs you and the filter is elsewhere", tb.indexOf("aj-dot") !== -1);
  check("no amber dot once filtered to needs you", AJ.toolbarHtml(data, { source: "", filter: "needs_you" }).indexOf("aj-dot") === -1);
  check("no amber dot when nothing needs you", AJ.toolbarHtml({ counts: {}, source_counts: {} }, {}).indexOf("aj-dot") === -1);
  check("no chip rows left", tb.indexOf("aj-chip") === -1 && typeof AJ.filterHtml === "undefined");
}

(async function () {
  const pages = {
    "": { ok: true, jobs: [job({ id: "kanban:a" }), job({ id: "goal:g1", source: "auto", bucket: "needs_you",
      resume: { goal_id: "g1", revision: 7 }, cancel: { kind: "goal", goal_id: "g1", revision: 7 } }),
    job({ id: "team:t1", source: "team", priority: { kind: "team", team_id: "tm1", task_id: "t1", on: true, version: 5 } })],
    counts: {}, source_counts: { team: 1, chat: 2, auto: 1 }, next: "3", teams: [{ team_id: "tm1", name: "Ra mắt" }] },
    "3": { ok: true, jobs: [job({ id: "kanban:b" })], counts: {}, source_counts: {}, next: null },
  };
  respond = (url, o) => {
    if (o.method === "POST") return { ok: true, task_id: "t_new", board: "auto" };
    const m = /[?&]cursor=([^&]*)/.exec(url);
    return pages[m ? decodeURIComponent(m[1]) : ""];
  };
  const host = fakeHost();
  const opened = [];
  const opts = { slug: "minh", name: "Minh", brain: () => "brain",
    agents: () => [{ slug: "lan", name: "Lan" }],
    openTeam: (a, b) => opened.push(["team", a, b]), openChat: (s) => opened.push(["chat", s]) };
  calls = []; intervals = [];
  const m = AJ.mount(host, opts);
  await flush(); await flush();
  check("gắn: tải trang đầu với nguồn và ngăn ở server", calls.length === 1 && /source=all/.test(calls[0].url) && /limit=30/.test(calls[0].url),
    calls.map((c) => c.url).join(" | "));
  check("đồng bộ trực tiếp: nghe nhóm, mục tiêu, việc nền, việc vừa đổi ở tab",
    ["javis:team-event", "javis:resonance-agents-changed", "javis:sessions-changed", "javis:agent-jobs-changed"]
      .every((e) => (winL[e] || []).length === 1), Object.keys(winL).map((k) => k + ":" + winL[k].length).join(","));
  check("nhịp hỏi thưa cho Kanban (không giữ tiến trình node)", intervals.length === 1 && intervals[0].ms >= 10000 && intervals[0].unrefd);

  // Lọc nguồn: tải lại ở server với source=team, từ trang đầu.
  // Source filter is a select since 0.158.0: a select fires input AND change, it must load once.
  calls = [];
  host.fire("input", field("aj-src-sel", "team"));
  host.fire("change", field("aj-src-sel", "team"));
  await flush(); await flush();
  check("choosing Teams in the source select reloads once with source=team",
    calls.length === 1 && /source=team/.test(calls[0].url) && !/cursor=/.test(calls[0].url), calls.map((c) => c.url).join(" | "));
  host.fire("change", field("aj-src-sel", ""));
  await flush(); await flush();
  calls = [];
  host.fire("change", field("aj-status-sel", "needs_you"));
  await flush(); await flush();
  check("choosing a status reloads with that bucket", calls.length === 1 && /bucket=needs_you/.test(calls[0].url), calls.map((c) => c.url).join(" | "));
  host.fire("change", field("aj-status-sel", ""));
  await flush(); await flush();

  // Xem thêm: trang sau nối vào, không trùng.
  calls = [];
  host.fire("click", btn("aj-more"));
  await flush(); await flush();
  const ids = m.state().data.jobs.map((x) => x.id);
  check("Xem thêm: đọc trang sau bằng cursor, nối vào cuối", /cursor=3/.test(calls[0].url) && ids.join() === "kanban:a,goal:g1,team:t1,kanban:b"
    && m.state().data.next === null, ids.join());

  // Đồng bộ trực tiếp: nhiều sự kiện gộp một lần tải, sau 800ms, giữ số việc đang xem.
  calls = [];
  window.dispatchEvent({ type: "javis:team-event" });
  window.dispatchEvent({ type: "javis:sessions-changed" });
  window.dispatchEvent({ type: "javis:resonance-agents-changed" });
  check("sự kiện chưa tới hạn gộp nhịp: chưa tải", calls.length === 0 && timers.filter((t) => !t.cleared).length === 1
    && timers.filter((t) => !t.cleared)[0].ms === AJ.RELOAD_MS && AJ.RELOAD_MS === 800);
  runTimers(); await flush(); await flush();
  check("ba sự kiện: đúng một lần tải lại", calls.length === 1 && !/cursor=/.test(calls[0].url), calls.map((c) => c.url).join(" | "));

  // Tiếp tục mục tiêu: lệnh resume kèm revision đang hiện.
  respond = (url, o) => (o.method === "POST" ? { ok: true } : pages[""]);
  calls = [];
  host.fire("click", btn("aj-resume", { ajResume: "goal:g1" }));
  await flush(); await flush();
  const rp = calls.find((c) => c.o.method === "POST");
  check("Tiếp tục: POST /goals/g1/commands {resume, expected_revision}", rp && /\/goals\/g1\/commands/.test(rp.url)
    && JSON.parse(rp.o.body).command === "resume" && JSON.parse(rp.o.body).expected_revision === 7, rp && rp.o.body);
  calls = [];
  host.fire("click", btn("aj-cancel", { ajCancel: "goal:g1" }));
  await flush(); await flush();
  const cp = calls.find((c) => c.o.method === "POST");
  check("Huỷ mục tiêu gửi kèm expected_revision", cp && JSON.parse(cp.o.body).command === "cancel" && JSON.parse(cp.o.body).expected_revision === 7,
    cp && cp.o.body);
  calls = [];
  host.fire("click", btn("aj-prio", { ajPrio: "team:t1" }));
  await flush(); await flush();
  const pp = calls.find((c) => c.o.method === "POST");
  check("Ưu tiên: route gốc của nhóm, CAS phiên bản hàng", pp && /\/teams\/tm1\/queue\/t1\/priority/.test(pp.url)
    && JSON.parse(pp.o.body).on === true && JSON.parse(pp.o.body).expected_queue_version === 5, pp && pp.url);

  // Giao việc: hai bước, tiêu chí và nơi nhận kết quả đi kèm; gửi lại sau rớt mạng giữ nonce.
  respond = (url, o) => (o.method === "POST" ? { ok: true, task_id: "t_new", board: "auto" } : pages[""]);
  host.fire("click", btn("aj-assign-open"));
  host.fire("click", btn("aj-assign-next"));
  check("chưa nhập yêu cầu: không sang bước xác nhận, báo rõ", m.state().ui.step === "edit" && m.state().ui.assignError === T("ajobs.need_text"));
  host.fire("input", field("aj-text", "Tổng hợp phản hồi"));
  host.fire("input", field("aj-crit", "Có 5 ý"));
  host.fire("change", field("aj-target", "team:tm1"));
  host.fire("click", btn("aj-assign-next"));
  check("bước xác nhận hiện tóm tắt trước khi tạo", m.state().ui.step === "confirm" && host.innerHTML.includes("aj-confirm")
    && host.innerHTML.includes(T("ajobs.sum_crit", { crit: "Có 5 ý" })) && host.innerHTML.includes(T("ajobs.dest_team", { name: "Ra mắt" })));
  host.fire("click", btn("aj-assign-edit"));
  check("Sửa: quay lại form, giữ chữ", m.state().ui.step === "edit" && host.innerHTML.includes("Tổng hợp phản hồi"));
  host.fire("click", btn("aj-assign-next"));
  let netFail = true;
  const realFetch = global.fetch;
  global.fetch = function (url, o) {
    if (o && o.method === "POST" && netFail) { calls.push({ url, o }); return Promise.reject(new Error("net")); }
    return realFetch(url, o);
  };
  calls = [];
  host.fire("click", btn("aj-assign-send"));
  await flush(); await flush();
  netFail = false;
  host.fire("click", btn("aj-assign-send"));
  await flush(); await flush();
  global.fetch = realFetch;
  const posts = calls.filter((c) => c.o && c.o.method === "POST");
  const b1 = JSON.parse(posts[0].o.body), b2 = JSON.parse(posts[1].o.body);
  check("Xác nhận: gửi yêu cầu, tiêu chí, nơi nhận kết quả là nhóm, kiểu việc thường",
    /\/agents\/minh\/jobs/.test(posts[0].url) && b1.text === "Tổng hợp phản hồi" && b1.criteria === "Có 5 ý" && b1.target === "team:tm1"
    && b1.kind === "task", posts[0].o.body);
  check("gửi lại sau rớt mạng giữ cùng nonce (server trả đúng việc cũ)", b1.nonce && b1.nonce === b2.nonce);
  check("giao xong: đóng form, báo đã giao trong nhóm", !m.state().ui.assignOpen && m.state().ui.note === T("ajobs.assigned_team"));

  // Kiểu Kiểm chứng: tiêu chí bắt buộc; đổi kiểu đọc danh sách mục của trợ lý khác.
  respond = (url, o) => {
    if (/verify-targets/.test(url)) return { ok: true, items: [{ id: "kanban:k7", title: "Email của Lan", slug: "lan", name: "Lan" }] };
    return o.method === "POST" ? { ok: true, task_id: "t_v" } : pages[""];
  };
  host.fire("click", btn("aj-assign-open"));
  calls = [];
  host.fire("click", btn("aj-chip", { ajKind: "verify" }));
  await flush(); await flush();
  check("chọn Kiểm chứng: đọc mục của trợ lý khác", calls.some((c) => /\/agents\/minh\/jobs\/verify-targets/.test(c.url))
    && host.innerHTML.includes('value="kanban:k7"'));
  host.fire("input", field("aj-text", "Soát email"));
  host.fire("click", btn("aj-assign-next"));
  check("Kiểm chứng thiếu tiêu chí: không sang bước xác nhận", m.state().ui.step === "edit" && m.state().ui.assignError === T("ajobs.need_crit"));
  host.fire("input", field("aj-crit", "Đúng tên khách"));
  host.fire("change", field("aj-link-sel", "kanban:k7"));
  host.fire("click", btn("aj-assign-next"));
  check("xác nhận Kiểm chứng nêu mục được kiểm", host.innerHTML.includes(T("ajobs.sum_link", { title: "Email của Lan" })));
  calls = [];
  host.fire("click", btn("aj-assign-send"));
  await flush(); await flush();
  let vp = calls.find((c) => c.o.method === "POST");
  let vb = vp && JSON.parse(vp.o.body);
  check("gửi Kiểm chứng: kind verify, link là mục đã chọn", vb && vb.kind === "verify" && vb.link === "kanban:k7" && vb.criteria === "Đúng tên khách",
    vp && vp.o.body);

  // Giao kiểm chứng từ một thẻ: mục đã gắn, chọn trợ lý khác làm người kiểm, gửi tới trợ lý đó.
  host.fire("click", btn("aj-verify", { ajVerify: "goal:g1" }));
  check("Giao kiểm chứng từ thẻ: form kiểu Kiểm chứng, mục đã gắn, chọn người kiểm trong trợ lý khác",
    m.state().ui.kind === "verify" && m.state().ui.link === "goal:g1" && m.state().ui.verifier === "lan"
    && host.innerHTML.includes("aj-verifier") && host.innerHTML.includes(">Lan<"), host.innerHTML.slice(0, 600));
  host.fire("input", field("aj-text", "Soát mục tiêu"));
  host.fire("input", field("aj-crit", "Đạt tiêu chí cũ"));
  host.fire("click", btn("aj-assign-next"));
  calls = [];
  host.fire("click", btn("aj-assign-send"));
  await flush(); await flush();
  vp = calls.find((c) => c.o.method === "POST");
  vb = vp && JSON.parse(vp.o.body);
  check("gửi tới trợ lý kiểm chứng (Lan), kết quả về chat riêng của Lan, link là thẻ đó",
    vp && /\/agents\/lan\/jobs/.test(vp.url) && vb.kind === "verify" && vb.link === "goal:g1" && vb.target === "chat",
    vp && vp.url + " " + vp.o.body);
  check("báo đã giao cho người kiểm", m.state().ui.note === T("ajobs.assigned_other", { name: "Lan" }), m.state().ui.note);

  // Mở mục được kiểm từ thẻ việc kiểm chứng.
  m.state().data.jobs.push(job({ id: "kanban:v1", kind: "verify", link: { id: "team:t9", title: "X", open: { kind: "team", team_id: "tm9", task_id: "t9" } } }));
  host.fire("click", btn("aj-link-open", { ajLink: "kanban:v1" }));
  check("mở mục được kiểm đi đúng nhóm và việc", JSON.stringify(opened[opened.length - 1]) === JSON.stringify(["team", "tm9", "t9"]));

  // Rời tab: gỡ trình nghe, nhịp hỏi, hẹn tải lại; sự kiện sau đó không tải gì.
  window.dispatchEvent({ type: "javis:team-event" });
  m.destroy();
  check("destroy: gỡ hết trình nghe sự kiện của window", ["javis:team-event", "javis:resonance-agents-changed", "javis:sessions-changed",
    "javis:agent-jobs-changed"].every((e) => (winL[e] || []).length === 0));
  check("destroy: dừng nhịp hỏi và huỷ hẹn tải lại", intervals[0].cleared && timers.every((t) => t.cleared));
  calls = [];
  window.dispatchEvent({ type: "javis:team-event" });
  runTimers(); await flush();
  check("sau destroy: sự kiện không gây tải", calls.length === 0);

  // ───────────── chữ và kiểu ─────────────
  check("không có em dash hay en dash trong mã", !/[\u2013\u2014]/.test(src));
  const keys = Array.from(new Set((src.match(/"ajobs\.[a-z_.]+"/g) || []).map((k) => k.slice(1, -1))));
  const missing = keys.filter((k) => !S[k]);
  check("mọi khoá ajobs.* dùng trong file có chữ tiếng Việt", missing.length === 0 || !overlayPath, missing.join(", "));
  if (overlayPath) {
    const en = Object.assign({}, JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8")), overlay.en);
    const missEn = keys.filter((k) => !en[k]);
    check("mọi khoá ajobs.* có bản tiếng Anh", missEn.length === 0, missEn.join(", "));
    check("bản phủ i18n không có em dash hay en dash", !/[\u2013\u2014]/.test(JSON.stringify(overlay)));
  }
  const cssPath = process.env.JAVIS_JOBS_CSS || path.join(ROOT, "dashboard", "console.css");
  const css = fs.readFileSync(cssPath, "utf8");
  // Owner, 2026-10-15: the Work tab text was too big for the narrow column. Panel text is 12 to 14px now;
  // touch screens keep 44px targets through a pointer: coarse rule.
  const ajCss = css.split("\n").filter((l) => /^\.aj|^\.aj-|\.aj /.test(l)).join("\n");
  const sizes = (ajCss.match(/font-size:\s*(\d+(?:\.\d+)?)px/g) || []).map((x) => parseFloat(x.replace(/[^\d.]/g, "")));
  check("Work tab text sits between 11.5 and 14px", sizes.length > 0 && sizes.every((n) => n >= 11.5 && n <= 14), sizes.join(","));
  check("touch screens keep 44px targets in the Work tab", /@media \(pointer: coarse\)[\s\S]{0,400}\.aj-sel[\s\S]{0,200}min-height: 44px/.test(css));
  check("no horizontal chip rows left in the Work tab CSS", !/\.aj-filters/.test(css));

  console.log(fails ? "\nĐỎ " + fails + " mục" : "\nTất cả xanh.");
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
