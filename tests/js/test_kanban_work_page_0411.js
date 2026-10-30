/* Work page upgrade (0.411.0): lighter polling, newest history, follow-up notes, check again, repeat-job hints.

       node tests/js/test_kanban_work_page_0411.js

   Owner, 30/10/2026: the Work page was "not very useful and often broken". See
   tests/python/test_kanban_work_page_0411.py for the server side. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

const kanban = (JS.match(/\n  async function renderKanban\(el\) \{[\s\S]*?\n  \}\n/) || [""])[0];
check("renderKanban found", kanban.length > 2000);

// ---------------------------------------------------------------- polling
check("the poll sends the last rev", /&rev=\$\{encodeURIComponent\(since\)\}/.test(kanban));
check("an unchanged board stops there", /if \(d\.unchanged\) return;/.test(kanban));
check("a hidden tab does not poll", /if \(fromPoll === true && document\.hidden\) return;/.test(kanban));
check("the interval polls with fromPoll", /else load\(true\);\s*\}, 3000\);/.test(kanban));
check("coming back to the tab refreshes", /function onVisible\(\) \{ if \(!document\.hidden\) load\(true\); \}/.test(kanban)
  && /removeEventListener\("visibilitychange", onVisible\)/.test(kanban));
check("history is not cut to the first 20 any more", !/history\.slice\(0, ?20\)/.test(kanban));
check("Show more asks the server for more history", /histLimit \+= 20; load\(\);/.test(kanban) && /&history=\$\{histLimit\}/.test(kanban));
check("Show more is not a Wipe button (that class gets the wipe handler)", !/class="kn-wipe kn-more"/.test(kanban));

// ---------------------------------------------------------------- actions
check("Run now calls /kanban/run", /act === "run"\) result = await post\("\/kanban\/run"/.test(kanban));
check("Check again calls /kanban/task/verify", /act === "verify"\) result = await post\("\/kanban\/task\/verify"/.test(kanban));
check("a note goes to /kanban/task/followup", /post\("\/kanban\/task\/followup", \{ id: box\.dataset\.follow, text \}\)/.test(kanban));
check("the drawer shows the note box", /\$\{followBox\(t\)\}/.test(kanban) && /bindFollowBoxes\(drawerBody\);/.test(kanban));
check("the open drawer follows its job unless the owner is typing",
  /refreshDrawer\(\[\.\.\.active, \.\.\.attention, \.\.\.handled, \.\.\.queue, \.\.\.history\]\)/.test(kanban)
  && /if \(typing\) return;\s*showTask\(openTaskId, \{ silent: true \}\);/.test(kanban));
check("a hint is dismissed then handed to Javis in chat",
  /post\("\/kanban\/hint\/dismiss", \{ key: h\.key \}\)/.test(kanban) && /window\.JavisSend\(msg\)/.test(kanban));

// ---------------------------------------------------------------- badges and who may get a note
function grab(name) {
  const m = kanban.match(new RegExp("\\n    function " + name + "\\([^)]*\\) \\{[\\s\\S]*?\\n    \\}\\n"));
  return m ? m[0] : "";
}
const pending = grab("pendingQuestion");
const src = [grab("taskBadges"), grab("canVerify"), pending, grab("canFollow")].join("\n");
check("helpers found", src.split("function").length > 4);
const fns = new Function("window", "esc",
  "const FOLLOW_STATUS = [\"blocked\", \"review\", \"done\", \"cancelled\", \"triage\", \"todo\", \"ready\"];\n" + src +
  "\nreturn { taskBadges, canVerify, canFollow };")({ t: (k, v) => k + (v && v.name ? ":" + v.name : "") }, s => s);
const crit = { acceptance: ["a"] };
check("checked job says Checked", /badge_checked/.test(fns.taskBadges({ status: "done", metadata: { ...crit, acceptance_check: "ai" } })));
check("unchecked job says Not checked", /badge_unchecked/.test(fns.taskBadges({ status: "done", metadata: { ...crit, acceptance_check: "unverified" } })));
check("a job with no criteria gets no check badge", fns.taskBadges({ status: "done", metadata: { acceptance_check: "none" } }) === "");
check("routed job names its assistant", /badge_agent:Viết email/.test(fns.taskBadges({ status: "ready", metadata: { agent: { name: "Viết email" } } })));
check("a finished job shows how long it took",
  /badge_time/.test(fns.taskBadges({ status: "done", metadata: { run_seconds: 125 } }))
  && !/badge_time/.test(fns.taskBadges({ status: "running", metadata: { run_seconds: 125 } })));
check("Check again only for an unchecked finished job with criteria",
  fns.canVerify({ status: "done", metadata: { ...crit, acceptance_check: "unverified" } })
  && !fns.canVerify({ status: "done", metadata: { ...crit, acceptance_check: "ai" } })
  && !fns.canVerify({ status: "done", metadata: { acceptance_check: "unverified" } }));
check("a note can go to a done, stopped or queued job",
  ["done", "cancelled", "review", "ready"].every(s => fns.canFollow({ status: s, metadata: {} })));
check("but not to a running job, nor one waiting for an answer (that has its own box)",
  !fns.canFollow({ status: "running", metadata: {} })
  && !fns.canFollow({ status: "blocked", block_kind: "needs_input", block_reason: "Which file?", metadata: {} }));

// ---------------------------------------------------------------- calm wording (owner, 30/10/2026)
check("a stopped job shows the calm sentence, never the raw error in red",
  /const reason = !ask && t\.calm \? `<div class="kn-task-result kn-task-calm">/.test(kanban)
  && !/esc\(t\.block_reason\)\}<\/div>` : ""/.test(kanban.split("function taskHtml")[1] || ""));
check("the pill says who is on it", /window\.t\(t\.waits_for_owner \? "kanban\.st_waiting_you" : "kanban\.st_handled"\)/.test(kanban));
check("the drawer folds the raw error under Technical detail", /<details class="kn-tech"><summary>\$\{esc\(window\.t\("kanban\.tech_detail"\)\)\}/.test(kanban));
check("a separate area lists what Javis handles itself", /id="knHandled"/.test(kanban) && /fillList\(el\.querySelector\("#knHandled"\), handled, "handled"\)/.test(kanban));
check("the asking area is named for what it holds", VI["kanban.kpi_attention"] === "Javis đang hỏi bạn" && !/xử lý/.test(VI["kanban.kpi_attention"]));
check("the handled area says there is nothing to do", /không cần làm gì/.test(VI["kanban.p_handled_sub"]));

// ---------------------------------------------------------------- every kanban.* text exists in both languages
const keys = new Set([...JS.matchAll(/\bt\("(kanban\.[a-z0-9_]+)"/g)].map(m => m[1]));
const missing = [...keys].filter(k => !(k in VI) || !(k in EN));
check("every kanban.* key used by console.js is in vi.json and en.json", missing.length === 0, missing.join(", "));
check("new texts carry no long dash", ![...keys].some(k => /[–—]/.test((VI[k] || "") + (EN[k] || ""))));

if (fails.length) { console.log(`\nFAIL ${fails.length}: ${fails.join(", ")}`); process.exit(1); }
console.log("\nOK - test_kanban_work_page_0411");
