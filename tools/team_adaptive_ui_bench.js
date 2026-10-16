// Đo chi phí vẽ thuần của trang Nhóm dưới node (T4, 0.170.0). KHÔNG phải số đo trình duyệt: không có layout, paint hay
// DOM thật; chỉ là thời gian dựng chuỗi HTML của các hàm vẽ trong dashboard/teams.js và dashboard/reactions.js.
// Playwright cho Python không có trong .venv nên bench Python gọi script này thay thế và ghi rõ giới hạn.
//
//     node tools/team_adaptive_ui_bench.js --teams 12 --messages 200 --runs 10
//
// In MỘT dòng JSON cuối cùng.
"use strict";
const path = require("path");
const ROOT = path.join(__dirname, "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const RX = require(path.join(ROOT, "dashboard", "reactions.js"));

function arg(name, dflt) {
  const i = process.argv.indexOf("--" + name);
  return i > 0 ? Number(process.argv[i + 1]) : dflt;
}
const N_TEAMS = arg("teams", 12);
const N_MSGS = arg("messages", 200);
const RUNS = arg("runs", 10);

function stats(xs) {
  const s = xs.slice().sort((a, b) => a - b);
  const q = (p) => s[Math.min(s.length - 1, Math.max(0, Math.round(p * (s.length - 1))))];
  return { p50_ms: +q(0.5).toFixed(3), p95_ms: +q(0.95).toFixed(3), max_ms: +s[s.length - 1].toFixed(3), runs: s.length };
}
function time(fn) {
  const t = process.hrtime.bigint();
  fn();
  return Number(process.hrtime.bigint() - t) / 1e6;
}

const members = [0, 1, 2, 3].map((i) => ({ agent_key: "ag_" + i, slug: "tro-ly-" + i, name: "Trợ lý " + i,
  role: i ? "member" : "leader", status: "active", resonance_enabled: i % 2 === 0, agent_status: "active" }));
const teams = [];
for (let i = 0; i < N_TEAMS; i++) {
  teams.push({ team_id: "tm_" + i, name: "Nhóm " + i, description: "", leader_key: "ag_0", status: "active",
    caps: { mentions: 3, daily_turns: 100, task_turns: 12, task_steps: 8 }, members: members,
    counts: { running: i % 2, waiting: i % 3, blocked: i % 4 === 0 ? 1 : 0 }, running: [], busy: {},
    last: { content: "Tin cuối của nhóm " + i, ts: 1760500000 + i } });
}
const vals = ["like", "love", "haha", "wow", "sad", "angry"];
function makeMsgs(n) {
  const out = [];
  for (let k = 0; k < n; k++) {
    const agent = k % 2 === 1;
    out.push({ id: k + 1, author_kind: agent ? "agent" : "owner", author_ref: agent ? "ag_" + (k % 4) : "",
      content: (agent ? "Trả lời số " : "Câu hỏi số ") + k + ": doanh thu, kế hoạch, việc cần làm. ".repeat(3),
      ts: 1760500000 + k, meta: {}, content_sha: "x" + k,
      reaction: agent && k % 3 === 0 ? { value: vals[k % 6], reasons: [], axis: "", comment: "", stale: false,
        status: "pending_review", status_reason: "", source_kind: "owner", revision: 1, updated_at: 1760500000 } : null,
      agent_reactions: agent && k % 5 === 0 ? [{ agent_key: "ag_0", name: "Trợ lý 0", source_kind: "leader",
        value: "like", reasons: [], comment: "" }] : [] });
  }
  return out;
}
const ctx = { members: members, authors: {}, picker: null, jumped: null };

const out = { available: true, kind: "pure_render_node_no_browser",
  note: "Thời gian dựng chuỗi HTML bằng hàm vẽ thật của dashboard dưới node; KHÔNG gồm layout, paint, DOM thật.",
  node: process.version, teams: N_TEAMS, messages_rendered: N_MSGS };

// Danh sách nhóm.
const listT = [];
for (let r = 0; r < RUNS; r++) listT.push(time(() => TM.teamListHtml(teams, "tm_0", 1760600000)));
out.team_list = stats(listT);

// Trang tin (một khung N tin, như drawMsgs vẽ lại cả khung).
const msgs = makeMsgs(N_MSGS);
const pageT = [];
let html = "";
for (let r = 0; r < RUNS; r++) pageT.push(time(() => { html = msgs.map((m) => TM.messageHtml(m, ctx)).join(""); }));
out.message_page = stats(pageT);
out.message_page_html_kb = Math.round(html.length / 1024);

// MÔ PHỎNG hai tab nhận cùng chuỗi gói reaction qua WS: vòng lặp này làm lại đúng việc teams.js onTeamEvent làm (thay tin
// trong danh sách rồi drawMsgs vẽ lại cả khung) bằng hàm vẽ thật messageHtml; KHÔNG gọi onTeamEvent (cần DOM thật). Số lần vẽ
// lại là của vòng mô phỏng, không phải đo từ dashboard.
const tabs = [makeMsgs(N_MSGS), makeMsgs(N_MSGS)];
const EVENTS = 20;
const evT = [];
let redraws = 0;
for (let r = 0; r < RUNS; r++) {
  evT.push(time(() => {
    for (let e = 0; e < EVENTS; e++) {
      const mid = 2 * ((e * 7) % (N_MSGS / 2)) + 2;
      for (const tab of tabs) {
        const i = tab.findIndex((m) => Number(m.id) === mid);
        if (i >= 0) {
          tab[i] = Object.assign({}, tab[i], { reaction: { value: vals[e % 6], reasons: [], axis: "", comment: "",
            stale: false, status: "received", status_reason: "", source_kind: "owner", revision: e, updated_at: 1 } });
          tab.map((m) => TM.messageHtml(m, ctx)).join("");
          redraws++;
        }
      }
    }
  }));
}
out.two_tabs_ws_reactions_simulated = Object.assign(stats(evT), { events_per_run: EVENTS, tabs: 2,
  simulated_full_list_redraws: redraws / RUNS,
  note: "mô phỏng, không gọi onTeamEvent: theo mã teams.js mỗi gói team_message vẽ lại cả khung tin của mỗi tab (O(số tin đang hiện)), cộng một lần đọc lại danh sách, hàng đợi, nhóm sau 300 ms (gộp)" });

// Reaction corner and six-emoji pill (reactions.js, 0.177.0: replaces the old chip and reasons picker).
const chipT = [];
for (let r = 0; r < RUNS; r++) chipT.push(time(() => {
  for (let k = 0; k < 500; k++) { RX.cornerHtml(k, { value: vals[k % 6] }, { prefix: "tm", last: k === 499 }); RX.barHtml(k, "", { prefix: "jr" }); }
}));
out.reaction_corner_and_bar_x500 = stats(chipT);
console.log(JSON.stringify(out));
