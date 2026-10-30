/* 0.426.0: review pass after the Tasks page phases. What the old Kanban and Scheduled pages had and the Tasks page
   lacked comes back, and the old renderers leave console.js.

       node tests/js/test_tasks_review_0426.js */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const js = read("dashboard/tasks.js");
const cons = read("dashboard/console.js");
const uia = read("dashboard/ui-actions.js");
const css = read("dashboard/tasks.css");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

// ---- loops: Edit opens a form with the loop's own fields and saves through POST /loops
check("loops get Edit in the menu", /\|\| src === "loop"\) out\.push\(\["edit", "pencil", "nv\.a\.edit"\]\)/.test(js));
check("the form starts from the loop's name, body, level and interval",
  /S\.form = \{ loop: it\.ref, name: lp\.name \|\| it\.ref, text: lp\.body \|\| "", lmode: lp\.mode \|\| "full", iv: String\(lp\.interval_min \|\| 60\) \}/.test(js));
check("the form has name, body, level and interval fields",
  js.includes('id="nvLn"') && js.includes('seg("lmode"') && js.includes('id="nvIv" type="number" min="5"'));
check("save posts the loop by its slug with mode and an interval of at least 5",
  /postForm\("\/loops", \{ brain: b, slug: f\.loop,[\s\S]{0,120}mode: f\.lmode \|\| "full",\s*interval_min: String\(Math\.max\(5, Number\(f\.iv\) \|\| 60\)\)/.test(js));
check("typed name and interval survive a re-render", /S\.form\.name = g\("#nvLn"\)\.value/.test(js) && /S\.form\.iv = g\("#nvIv"\)\.value/.test(js));

// ---- reminder options
check("options only when it will be a reminder", /if \(f\.script \|\| \(!f\.edit && !f\.date && !f\.rule && f\.mode !== "remind"\)\) return "";/.test(js));
check("create sends level, call, read aloud and remember last",
  /createReminder\(txt, f\.mode, f\.date, f\.time, f\.rule, \{ muc_quyen: f\.mq \|\| "full", call: !!f\.call, speak: !!f\.speak, remember_last: f\.mode === "do" && !!f\.last \}\)/.test(js));
check("createReminder merges the options before the schedule", /opts \|\| \{\}, javisSchedule\(rule/.test(js));
check("edit loads the stored options", /mq: raw\.muc_quyen \|\| "full", call: raw\.call \? "1" : "", speak: raw\.speak \? "1" : "", last: raw\.remember_last \? "1" : ""/.test(js));

// ---- Javis shows a job on screen
check("tasks.js exports show() and ready()", /window\.JavisTasks = \{ mount: mount, unmount: unmount, show: show, ready:/.test(js));
check("open_task goes to the Tasks page and waits for its data", /JavisNav\.go\("tasks"\)/.test(uia) && /nv\.ready\(\)/.test(uia));
check("a job that is not there says so", /tw\("ui\.err_task_missing"\)/.test(uia) && vi["ui.err_task_missing"] && en["ui.err_task_missing"]);

// ---- what the old pages also had
check("a job queued now keeps 'review the result when done', explanation behind (i)",
  /needs_approval: f\.appr \? "1" : "0"/.test(js) && /J\.body\(esc\(tw\("kanban\.need_approve_info"\)\)\)/.test(js));
check("details show the level a reminder or loop runs at", /kv\(tw\("nv\.lp\.mode"\), '<span class="nv-lvl'/.test(js));
check("editing a script job sends no type or options", /var fields = f\.script \? \{ id: f\.edit, brain: b, text: txt \} :/.test(js));
check("no report channel: the Javis tab says results reach no one, with a way to Channels",
  /var nt = S\.notify \|\| \{\}, bad = nt\.ok === false/.test(js) && /case "gochan":/.test(js) && /S\.notify = \(res\[2\] && res\[2\]\.notify\)/.test(js));

// ---- granting real actions asks first
check("grant asks before acting", /case "grant":\s*if \(!window\.confirm\(tw\("kanban\.confirm_grant"\)\)\) return;/.test(js) && vi["kanban.confirm_grant"]);

// ---- the form's buttons stay in reach
check("Cancel and Save stick to the bottom of the form", /\.nv-modal \.nv-acts\.end \{ position: sticky; bottom: -18px;/.test(css));

// ---- old renderers are gone
check("renderKanban and renderSelfImprove left console.js", !/function renderKanban|function renderSelfImprove|JavisKanbanShow/.test(cons + uia));
check("old ids still open the Tasks page", /kanban: "tasks", selfimprove: "tasks"/.test(cons));

const keys = ["nv.lp.edit", "nv.lp.name", "nv.lp.body", "nv.lp.mode", "nv.lp.m_suggest", "nv.lp.m_auto", "nv.lp.m_full", "nv.lp.every",
  "nv.f.call", "nv.f.speak", "nv.f.last", "nv.nochan.head", "nv.nochan.body", "nv.chanerr.head", "nv.nochan.go", "cs.si_level_note_full", "cs.si_level_note_auto", "cs.si_level_note_suggest"];
check("strings in both languages", keys.every((k) => vi[k] && en[k]));
check("no long dashes in them", keys.every((k) => !/[–—]/.test(vi[k] + en[k])));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
