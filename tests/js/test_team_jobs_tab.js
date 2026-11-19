// Team Jobs tab redesign (owner, 16/11/2026).
//
//     python tests/run.py --js team_jobs_tab -v
//
// Owner: "cải tiến phần việc của team giống trải nghiệm của trang nhiệm vụ, anh cần biết các agent đang có những nhiệm
// vụ gì và ux ui có nhiều icon ít button", "có nhiệm vụ chính, và các thành viên đang làm gì sẽ hiện bên dưới", "menu
// thông tin, việc team cũng nên có icon", "phân trang những việc đã hoàn thành nếu nhiều quá", "click vào việc đã hoàn
// thành thì phải có 1 tóm tắt những gì đã làm", "lưu trữ ... cũng có phân trang". Pure functions of teams.js under node.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const teamsJs = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 900)));
  if (!cond) fails++;
}
const count = (s, needle) => s.split(needle).length - 1;
const buttons = (s) => (s.match(/<button\b[^>]*>/g) || []);

const members = [{ agent_key: "ag_an", slug: "an", name: "An", role: "leader" }, { agent_key: "ag_duy", slug: "duy", name: "Duy <b>" },
  { agent_key: "ag_mai", slug: "mai", name: "Mai" }];
const view = { members: members, leaderKey: "ag_an" };
const steps = [{ agent_key: "ag_an", kind: "plan", status: "done", brief: "Chia việc" },
  { agent_key: "ag_duy", kind: "work", status: "running", brief: "Tìm <ảnh> minh hoạ" },
  { agent_key: "ag_mai", kind: "work", status: "queued", brief: "Viết bài" }];

// ───────────── a running job: the main job, then every member under it ─────────────
let h = TM.queueHtml({ running: [{ id: "t_1", title: "Làm <blog>", steps: steps, created_at: 1 }] }, view);
check("running job: one card, the title opens the job's messages", count(h, 'class="tm-jb ') === 1 && /class="tm-jb-title" data-view-task="t_1"/.test(h)
  && h.includes("Làm &lt;blog&gt;"), h);
check("running job: no 'Doing:' prefix, the spinner says it", !h.includes(vi["teams.doing"].replace("{title}", "Làm")) && h.includes("tm-jb-s-run"), h);
check("running job: every member is listed with name, role and what they were asked to do (escaped)",
  count(h, 'class="tm-jb-step ') === 3 && h.includes("Duy &lt;b&gt;") && h.includes("Tìm &lt;ảnh&gt; minh hoạ")
  && h.includes(vi["teams.role.plan"]) && h.includes(vi["teams.role.work"]), h);
check("running job: each step shows where it stands (done, running, waiting its turn)",
  h.includes("tm-jb-step-done") && h.includes("tm-jb-step-run") && h.includes("tm-jb-step-wait"), h);
check("running job: the fold button counts done steps and starts open", /data-job-fold="t_1"[^>]*aria-expanded="true"/.test(h) && h.includes(">1/3<"), h);
check("running job: three icon buttons, no text button", (function () {
  const acts = h.slice(h.indexOf('class="tm-jb-acts"'), h.indexOf('class="tm-jb-meta"'));
  return buttons(acts).length === 3 && /data-amend="t_1"/.test(acts) && /data-acc-edit="t_1"/.test(acts) && /data-cancel="t_1"/.test(acts)
    && buttons(acts).every((b) => /aria-label="[^"]+"/.test(b) && /title="[^"]+"/.test(b)) && !h.includes("ws-btn");
})(), h);
h = TM.queueHtml({ running: [{ id: "t_1", title: "Làm blog", steps: steps }] }, Object.assign({ fold: { t_1: false } }, view));
check("running job folded: the members are hidden, the count stays", !h.includes("tm-jb-step ") && /data-job-fold="t_1"[^>]*aria-expanded="false"/.test(h)
  && h.includes(">1/3<"), h);
h = TM.queueHtml({ running: [{ id: "t_1", title: "Mới giao" }] }, view);
check("a job with no step yet has no fold button and no empty list", !h.includes("data-job-fold") && !h.includes("tm-jb-steps"), h);

// ───────────── waiting for the owner comes first, with one text button ─────────────
const q = { blocked: [{ id: "t_4", title: "Đo tốc độ", block_kind: "cap_reached", block_reason: "Hết <6> lượt", steps: steps.slice(0, 2) }],
  running: [{ id: "t_1", title: "Làm blog", steps: steps }],
  waiting: [{ id: "t_3", title: "Bảng giá", team_prio: 1, created_at: 1 }, { id: "t_2", title: "Ảnh bìa", team_prio: null }] };
h = TM.queueHtml(q, view);
check("order: waiting for you, then running, then up next", h.indexOf(vi["teams.queue_blocked"]) < h.indexOf(vi["teams.queue_running"])
  && h.indexOf(vi["teams.queue_running"]) < h.indexOf(vi["teams.queue_waiting"]), h);
check("each group title carries its count", />1<\/span>/.test(h) && />2<\/span>/.test(h) && !vi["teams.queue_waiting"].includes("("), h);
const ask = h.slice(h.indexOf("tm-jb-ask"), h.indexOf(vi["teams.queue_running"]));
check("waiting for you: the reason in words, ONE text button (the way out), the rest are icons",
  ask.includes("Hết &lt;6&gt; lượt") && count(ask, "ws-btn") === 1 && /data-extend="t_4"/.test(ask) && ask.includes(vi["teams.act.extend"])
  && /class="tm-jb-ic[^"]*" data-acc-edit="t_4"/.test(ask) && /class="tm-jb-ic[^"]*" data-cancel="t_4"/.test(ask), ask);
check("waiting for you: the members are folded until asked for", /data-job-fold="t_4"[^>]*aria-expanded="false"/.test(ask) && !ask.includes("tm-jb-step "), ask);
const wait = h.slice(h.indexOf(vi["teams.queue_waiting"]));
check("up next: numbered in run order, the star is the priority button and sits last",
  wait.indexOf('tm-jb-pos">1<') < wait.indexOf("Bảng giá") && wait.indexOf("Bảng giá") < wait.indexOf('tm-jb-pos">2<')
  && /class="tm-jb-ic tm-jb-star is-on" data-prio="t_3" data-on="0" aria-pressed="true"/.test(wait)
  && /class="tm-jb-ic tm-jb-star" data-prio="t_2" data-on="1" aria-pressed="false"/.test(wait) && !wait.includes("ws-btn"), wait);
check("review case: an acceptance being checked has no criteria button", !TM.queueHtml({ blocked: [{ id: "t_9", title: "x",
  block_kind: "acceptance_review" }] }, view).includes('data-acc-edit="t_9"'));

// ───────────── the job pill above the composer (17/11/2026) ─────────────
// Owner: "các thông tin này có thể co gọn lại và để xuống dưới giống như việc kanban nền chạy", "khi đã nhắn ở khung chat
// xử lý vấn đề thông báo rồi thì phải tự tắt cái thông báo đó đi".
h = TM.jobStripHtml(q, members);
const pill = h.slice(0, h.indexOf('class="bg-pop"'));
check("pill: ONE line, the main chat's background pill, folded until pressed",
  count(h, 'class="bg-pill"') === 1 && /data-strip="1"[^>]*aria-expanded="false"/.test(h) && /class="bg-pop"[^>]*hidden>/.test(h), h);
check("pill: a job waiting for you comes first, in words, and the rest is a count",
  pill.includes(vi["teams.strip.ask"].replace("{title}", "Đo tốc độ")) && pill.includes(">+1<") && !pill.includes("Hết &lt;6&gt;"), pill);
check("pill: the long reason, the button and the icons wait in the details", !pill.includes("ws-btn") && !pill.includes("tm-jb-ic"), pill);
const pop = h.slice(h.indexOf('class="bg-pop"'));
check("details: the job waiting for you with its reason, ONE text button and a cancel icon",
  pop.includes("Hết &lt;6&gt; lượt") && /data-extend="t_4"/.test(pop) && count(pop, "ws-btn") === 1
  && /class="tm-jb-ic[^"]*" data-cancel="t_4"/.test(pop), pop);
check("details: the running job with who works now, the step count, edit and cancel icons",
  pop.includes("Làm blog") && pop.includes("1/3") && pop.includes("Duy &lt;b&gt;") && !/tm-sr-meta[^]*Mai/.test(pop)
  && /class="tm-jb-ic[^"]*" data-amend="t_1"/.test(pop) && /class="tm-jb-ic[^"]*" data-cancel="t_1"/.test(pop), pop);
check("details: a title shows the job's messages, and a button opens the Jobs tab",
  /class="tm-sr-title" data-view-task="t_4"/.test(pop) && /class="bg-open" data-open-jobs="1"/.test(pop) && pop.includes(vi["teams.strip.open"]), pop);
check("pill open: the details show", /class="bg-pop"[^>]*role="dialog"[^>]*">/.test(TM.jobStripHtml(q, members, { open: true }))
  && !/class="bg-pop"[^>]*hidden/.test(TM.jobStripHtml(q, members, { open: true })));
check("tone: amber while a job waits for you, green while jobs only run",
  TM.stripState(q).tone === "ask" && TM.stripState({ running: q.running }).tone === "run" && TM.stripState({ waiting: q.waiting }).tone === "");
check("nothing running and nothing waiting for you: no pill", TM.jobStripHtml({ waiting: q.waiting }, members) === "");
// The owner wrote in the chat after the job stopped: its notice goes away.
const stopped = { blocked: [Object.assign({}, q.blocked[0], { updated_at: 1000 })], running: [] };
const said = (ts) => [{ author_kind: "agent", ts: 5000 }, { author_kind: "owner", ts: ts }];
check("a waiting job leaves the pill once the owner has written after it stopped", TM.jobStripHtml(stopped, members,
  { seenAt: TM.ownerSaidAt(said(1200)) }) === "" && TM.stripState(stopped, 1200).tone === "");
check("an owner's message from BEFORE the stop does not count, nor does an assistant's",
  TM.jobStripHtml(stopped, members, { seenAt: TM.ownerSaidAt(said(900)) }).includes("Đo tốc độ") && TM.ownerSaidAt(said(900)) === 900);
check("a message that hands the team a new job does not count as an answer",
  TM.ownerSaidAt([{ author_kind: "owner", ts: 1200, meta: { as_job: true } }, { author_kind: "owner", ts: 900 }]) === 900);
check("the owner's time is read in seconds or milliseconds", TM.ownerSaidAt([{ author_kind: "owner", ts: 1200000 }]) === 1200000 / 1000
  || TM.ownerSaidAt([{ author_kind: "owner", ts: 1200000 }]) === 1200000);
check("with a running job too, the pill turns green and shows the running job",
  TM.jobStripHtml({ blocked: stopped.blocked, running: q.running }, members, { seenAt: 1200 }).includes("Làm blog")
  && TM.stripState({ blocked: stopped.blocked, running: q.running }, 1200).tone === "run");
check("a job that stops again after the owner's message comes back", TM.stripState({ blocked: [Object.assign({}, stopped.blocked[0],
  { updated_at: 1300 })] }, 1200).tone === "ask");
check("page code: the pill sits right above the composer, its details close on an outside press and on Esc",
  teamsJs.includes(`'<div class="tm-jobs bg-strip" hidden></div><div class="tm-composer"></div>'`)
  && teamsJs.includes('if (S.stripOpen && !inside(".tm-jobs")) setStrip(false);') && teamsJs.includes('if (e.key === "Escape" && S.stripOpen)')
  && teamsJs.includes("var seenAt = S.seenAt = Math.max(S.seenAt || 0, ownerSaidAt(S.msgs));") && teamsJs.includes("S.seenAt = 0;"));
check("while one job's messages show, the owner's answer elsewhere in the chat still counts, and the empty chat says it is that job's",
  teamsJs.includes('tw(S.filterTask ? "teams.chat_empty_job" : "teams.chat_empty")') && vi["teams.chat_empty_job"] && en["teams.chat_empty_job"]);
// 17/11/2026: pressing a job's title in the details did nothing, the details were drawn again before the press was handled.
check("a press on a job or on 'Open the Jobs tab' in the details is handled first, the details close after",
  /\(t\.dataset\.openJobs \|\| t\.dataset\.viewTask(?: \|\| t\.dataset\.jrOpen)?\) && inside\("\.tm-jobs"\)\) \{\s*S\.stripOpen = false;\s*setTimeout\(drawJobs, 0\);/.test(teamsJs));

// ───────────── the tabs carry icons ─────────────
h = TM.sideTabsHtml("jobs", q);
check("tabs: three tabs, still tm-tab with data-tab, the open one selected", count(h, 'class="tm-tab"') === 3
  && /data-tab="jobs" aria-selected="true"/.test(h) && /data-tab="info" aria-selected="false"/.test(h) && /data-tab="team"/.test(h), h);
check("tabs: each has its label; Jobs shows how many jobs are open", [vi["teams.tab_info"], vi["teams.tab_jobs"], vi["teams.tab_team"]]
  .every((x) => h.includes(">" + x + "<")) && h.includes('<span class="tm-tab-n">4</span>'), h);
check("tabs: no count when nothing is open", !TM.sideTabsHtml("info", {}).includes("tm-tab-n"));
check("tabs: in the order Jobs, Info, Team", h.indexOf('data-tab="jobs"') < h.indexOf('data-tab="info"') && h.indexOf('data-tab="info"') < h.indexOf('data-tab="team"'), h);
check("a team opens on Jobs when it has any job, on Info when it has none",
  TM.defaultTab(q) === "jobs" && TM.defaultTab({ finished: [{ id: "f" }] }) === "jobs" && TM.defaultTab({ archived: [{ id: "a" }] }) === "info"
  && TM.defaultTab({}) === "info" && TM.defaultTab(null, { running: 0, waiting: 2, blocked: 0 }) === "jobs" && TM.defaultTab(null, {}) === "info");
check("the owner's own pick of a tab is kept: the choice is made once the jobs have loaded, only if no tab was pressed",
  teamsJs.includes("if (S.tabAuto && S.side) S.tab = defaultTab(S.queue);") && teamsJs.includes("S.tab = d.tab; S.tabAuto = false;"));
// 18/11/2026 (owner, screenshot): a team that opened on Jobs showed "Loading..." for good under the Info tab, because
// pressing that tab only redrew the panel and never read the team's files and links.
check("pressing the Info tab reads the team's files, links and folder, like opening the panel on it",
  /if \(d\.tab === "info"\) \{ loadInfo\(\); loadFolder\(\); \}/.test(teamsJs.slice(teamsJs.indexOf("S.tab = d.tab; S.tabAuto = false;"))
    .slice(0, 400)));
// 18/11/2026 (owner): "trong team nhìn được model của các thành viên, như vậy sẽ dễ kiểm soát hơn".
check("member model: engine and model, 'Main model:' FIRST when it follows the main model (a cut line keeps it), nothing when unknown",
  vi["teams.model_main"].indexOf("{model}") > 0 && en["teams.model_main"].indexOf("{model}") > 0 &&
  TM.memberModelText({ model: { label: "Claude Code", model: "claude-opus-5-5", main: false } }) === "Claude Code · claude-opus-5-5"
  && TM.memberModelText({ model: { label: "ChatGPT", model: "gpt-5.5", main: true } }) === vi["teams.model_main"].replace("{model}", "ChatGPT · gpt-5.5")
  && TM.memberModelText({ model: { label: "Claude Code", model: "", main: true } }) === vi["teams.model_main"].replace("{model}", "Claude Code")
  && TM.memberModelText({ model: null }) === "" && TM.memberModelText({}) === "" && en["teams.model_main"].includes("{model}"));
h = TM.membersHtml({ leader_key: "ag_an", members: [{ agent_key: "ag_an", slug: "an", name: "An",
  model: { label: "Claude Code", model: "<opus>", main: false } }, { agent_key: "ag_mai", slug: "mai", name: "Mai", model: null }] }, [], null);
check("member rows: the model line sits under the role, escaped, and only on members that have one",
  count(h, 'class="tm-mmodel"') === 1 && h.includes("Claude Code · &lt;opus&gt;") && !h.includes("<opus>")
  && h.indexOf('class="tm-mrole"') < h.indexOf('class="tm-mmodel"'), h);
check("CSS: the model line is cut to one line on a narrow panel",
  /\.tm-mmodel span \{[^}]*text-overflow: ellipsis;[^}]*white-space: nowrap;/.test(css));
check("tabs: an icon per tab in the page code", /TAB_ICON = \{ info: "info", jobs: "list-checks", team: "users" \}/.test(teamsJs));

// ───────────── finished jobs: five a page, a summary on a press ─────────────
const fin = [];
for (let i = 1; i <= 12; i++) fin.push({ id: "team:" + i, task_id: String(i), title: "Xong " + i, result: i === 1 ? "Dòng <1>\n" + "Rất dài. ".repeat(60) : "kq",
  created_at: 1000, updated_at: 1000 + 18 * 60, steps: [{ agent_key: "ag_an", kind: "plan", status: "done", brief: "Chia hai phần" },
    { agent_key: "ag_duy", kind: "work", status: "done", brief: "Chuyển bài" }] });
h = TM.queueHtml({ finished: fin }, view);
check("finished: five jobs a page, the pager on the group title", count(h, 'data-fin-open="team:') === 10 && h.includes("Xong 5") && !h.includes("Xong 6")
  && h.includes(">1/3<") && /data-job-page="fin" data-dir="-1"[^>]*disabled/.test(h) && /data-job-page="fin" data-dir="1"/.test(h)
  && !/data-job-page="fin" data-dir="1"[^>]*disabled/.test(h), h);
h = TM.queueHtml({ finished: fin }, Object.assign({ finPage: 2 }, view));
check("finished: the last page holds the rest and cannot go further", h.includes("Xong 11") && h.includes("Xong 12") && !h.includes("Xong 10<")
  && h.includes(">3/3<") && /data-job-page="fin" data-dir="1"[^>]*disabled/.test(h), h);
check("finished: a page number past the end falls back to the last page", TM.queueHtml({ finished: fin }, Object.assign({ finPage: 9 }, view)).includes(">3/3<"));
check("finished: five or fewer jobs show no pager", !TM.queueHtml({ finished: fin.slice(0, 5) }, view).includes("data-job-page"));
check("finished: who worked on it shows on the row, and one icon moves it to the archive",
  /class="tm-jb-ic[^"]*" data-job-archive="team:1"/.test(h = TM.queueHtml({ finished: fin }, view)) && h.includes("An") && h.includes("Duy &lt;b&gt;")
  && !h.includes("ws-btn"), h);
h = TM.queueHtml({ finished: fin }, Object.assign({ openFin: "team:1" }, view));
check("finished, opened: when it ended, how long after it was given, the result cut short with Show more",
  h.includes("tm-report") && h.includes(vi["teams.jb.took"].replace("{n}", "18")) && h.includes("Dòng &lt;1&gt;") && h.includes("tm-report-body is-clamped")
  && /data-rep-more="team:1"/.test(h) && h.includes(vi["teams.jb.more"]), h);
check("finished, opened: who did what, one line per step with its brief", h.includes(vi["teams.jb.who"]) && count(h, 'class="tm-jb-step ') === 2
  && h.includes("Chia hai phần") && h.includes("Chuyển bài") && h.includes(vi["teams.role.plan"]), h);
check("finished, opened: an icon leads to the job's messages", /class="tm-jb-ic[^"]*" data-view-task="1"/.test(h), h);
h = TM.queueHtml({ finished: fin }, Object.assign({ openFin: "team:1", fullReport: { "team:1": true } }, view));
check("finished, opened in full: not cut, the button folds it back", !h.includes("is-clamped") && h.includes(vi["teams.fin_close"]), h);
h = TM.queueHtml({ finished: fin }, Object.assign({ openFin: "team:2" }, view));
check("a short result has no Show more", h.includes("tm-report") && !h.includes("data-rep-more"), h);

// ───────────── the archive: folded, paged, searchable, its report read on demand ─────────────
const arch = [];
for (let i = 1; i <= 48; i++) arch.push({ id: "team:a" + i, task_id: "a" + i, title: (i === 7 ? "Tối ưu ảnh" : "Cũ " + i), agents: ["ag_mai"],
  updated_at: 1000, cancelled: i === 3 });
h = TM.queueHtml({ archived: arch }, view);
check("archive: folded by default, only its count shows", h.includes("tm-arch-toggle") && h.includes(">48<") && !h.includes("data-job-delete")
  && !h.includes("tm-jb-q") && !h.includes('data-job-page="arch"'), h);
h = TM.queueHtml({ archived: arch }, Object.assign({ archOpen: true }, view));
check("archive open: five a page with the pager, a search box, restore and delete as icons",
  count(h, "data-job-unarchive=") === 5 && h.includes(">1/10<") && h.includes('class="tm-jb-q"') && h.includes(vi["teams.jb.search"])
  && /class="tm-jb-ic[^"]*" data-job-unarchive="team:a1"/.test(h) && /class="tm-jb-ic tm-jb-bad" data-job-delete="team:a1"/.test(h), h);
check("archive open: Delete all stands alone at the end, after every row", h.indexOf('data-job-delete-all="1"') > h.lastIndexOf("data-job-delete=")
  && h.includes("tm-jb-danger"), h);
check("archive open: a cancelled job says so", h.includes(vi["teams.jb.cancelled"]), h);
h = TM.queueHtml({ archived: arch }, Object.assign({ archOpen: true, archQuery: "toi uu" }, view));
check("archive search: no accents needed, the pager follows the matches", count(h, "data-job-unarchive=") === 1 && h.includes("Tối ưu ảnh")
  && !h.includes('data-job-page="arch"') && h.includes('value="toi uu"'), h);
check("archive search with no match says so", TM.queueHtml({ archived: arch }, Object.assign({ archOpen: true, archQuery: "zzz" }, view))
  .includes(vi["teams.jb.no_match"]));
check("a short archive has no search box", !TM.queueHtml({ archived: arch.slice(0, 4) }, Object.assign({ archOpen: true }, view)).includes("tm-jb-q"));
h = TM.queueHtml({ archived: arch }, Object.assign({ archOpen: true, openFin: "team:a1" }, view));
check("archive: an opened job waits for its report", h.includes("tm-report") && h.includes(vi["teams.jb.loading"]), h);
h = TM.queueHtml({ archived: arch }, Object.assign({ archOpen: true, openFin: "team:a1",
  details: { a1: { result: "Kết quả cũ", steps: [{ agent_key: "ag_mai", kind: "work", status: "done", brief: "Viết" }], created_at: 1, updated_at: 61 } } }, view));
check("archive: the report shows once it is read", h.includes("Kết quả cũ") && count(h, 'class="tm-jb-step ') === 1 && !h.includes(vi["teams.jb.loading"]), h);
check("archive: a report that failed to load says so", TM.queueHtml({ archived: arch }, Object.assign({ archOpen: true, openFin: "team:a1",
  details: { a1: "error" } }, view)).includes(vi["teams.jb.load_err"]));
check("the page reads one job's report from the job endpoint and searches as the owner types",
  teamsJs.includes('teamUrl("/tasks/" + q(job.task_id))') && /classList\.contains\("tm-jb-q"\)/.test(teamsJs));

// ───────────── the bar over one job's messages: one line (17/11/2026) ─────────────
// Owner, a phone screenshot: "rối như tơ vò ... không thể nào mà thao tác với đọc hiểu dữ liệu đc".
h = TM.filterbarHtml("Triển khai <UI>", '<details class="tm-task-quality"><summary>x</summary>y</details>', false);
check("filter bar: the job's name in one cut line, an icon for usage, an X for all messages, no text button",
  h.includes(vi["teams.filter_short"].replace("{title}", "Triển khai &lt;UI&gt;")) && /class="tm-jb-ic tm-fb-q" data-fb-quality="1" aria-expanded="false"/.test(h)
  && /class="tm-jb-ic tm-filter-clear"/.test(h) && !h.includes("ws-btn") && !h.includes("tm-task-quality"), h);
h = TM.filterbarHtml("Việc", '<details class="tm-task-quality"><summary>x</summary>y</details>', true);
check("filter bar: the usage icon opens the panel under the line, already unfolded", h.includes('<div class="tm-fb-panel"><details class="tm-task-quality" open>')
  && /aria-expanded="true"/.test(h), h);
check("filter bar: no usage yet, no icon for it", !TM.filterbarHtml("Việc", "", false).includes("data-fb-quality"));
check("CSS: the bar keeps to one line, its name cut to fit", css.includes(".tm-fb-text { flex: 1 1 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }"));

// ───────────── wiring, CSS, words ─────────────
check("page code: fold, page, Show more and the lazy report are handled", ["d.jobFold", "d.jobPage", "d.repMore", "loadJobDetail("]
  .every((x) => teamsJs.includes(x)));
check("CSS: the new card, its steps, the pager, the strip line and the icon tabs",
  [".tm-jb {", ".tm-jb-step {", ".tm-jb-ic {", ".tm-jb-pg {", ".tm-jb-search {", ".tm-sr {", ".tm-tab-n {", ".tm-report-body.is-clamped {"]
    .every((x) => css.includes(x)), [".tm-jb {", ".tm-jb-step {", ".tm-jb-ic {", ".tm-jb-pg {", ".tm-jb-search {", ".tm-sr {", ".tm-tab-n {",
    ".tm-report-body.is-clamped {"].filter((x) => !css.includes(x)).join(" | "));
check("CSS: the old strip rules are gone, the pill is not clipped (no scroll box around it)", !css.includes(".tm-js")
  && !/\.tm-jobs \{[^}]*overflow-y: auto/.test(css));
check("roles: the owner is the team lead, the assistant who leads is the deputy, on one line",
  vi["teams.leader_badge"] === "Phó nhóm" && vi["teams.lead_badge"] === "Trưởng nhóm" && vi["teams.pick.owner_badge"] === "Trưởng nhóm"
  && css.includes(".tm-info-members .tm-info-badge { flex: none; white-space: nowrap; }")
  && teamsJs.includes('<span class="tm-info-badge tm-info-lead">'));
check("CSS: icon buttons are 44px tall on a phone", /@media \(max-width: 760px\) \{[^@]*\.tm-jb-ic \{[^}]*height: 44px/.test(css));
const keys = Object.keys(vi).filter((k) => k.indexOf("teams.jb.") === 0);
check("the new words exist in both languages", keys.length >= 16 && keys.every((k) => en[k]), keys.filter((k) => !en[k]).join(","));
check("no long dash in the new words", keys.every((k) => !/[\u2013\u2014]/.test(vi[k] + en[k])));

if (fails) { console.log("\nFAILED " + fails); process.exit(1); }
console.log("\nALL OK");
