// 2026-11-12: the Team tab keeps in view only what an owner decides for a team (dashboard/teams.js teamTabHtml).
//
//     node tests/js/test_team_settings_simple.js
//
// A customer: "cái phần cài đặt của team khá phức tạp, nhiều thông số quá, cần đơn giản hơn, tập trung vào mục tiêu
// thôi". Acceptance, usage figures, limits, detailed rights and the reply log now sit in
// Advanced, closed by default. Nothing was removed.
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const vi = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "en.json"), "utf8"));
const TM = require(path.join(root, "dashboard", "teams.js"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + String(extra).slice(0, 500)));
  if (!cond) fails++;
}
function T(k) { return String(vi[k]).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }

const team = { id: "tm_x", team_id: "tm_x", name: "Shop", description: "Sells online", status: "active", leader_key: "a",
  members: [{ agent_key: "a", slug: "a", name: "A", status: "active" }, { agent_key: "b", slug: "b", name: "B", status: "active" }],
  caps: { task_turns: null, task_steps: null, help_depth: 2, daily_turns: 100, mentions: 3, busy_wait_s: 1800, judge_daily: 40,
    volunteer_k: 1, judge_off_batch: 1, reply_parallel: 1, auto_jobs: 5, running_jobs: 3, no_progress: 2 },
  usage: { today: 7, cap: 100 }, authority: { authority: null, caps: {}, effective_caps: {}, limits: [] }, mandate: null,
  work_mode: "gated", quality_policy: { enabled: false, limit_migration: "retain" },
  quality_usage: { attempts: 0, money: {}, coverage: {} } };

const html = TM.teamTabHtml(team, [], {});
const cut = html.indexOf('<details class="tm-adv"');
const shown = html.slice(0, cut), advanced = html.slice(cut);
const count = (h, re) => (h.match(re) || []).length;

check("Advanced is there and closed by default", cut > 0 && !/<details class="tm-adv" open/.test(html));
check("in view: members, the goal, how far the coordinator decides, outside actions, name and status",
  shown.includes(T("teams.tab_members")) && shown.includes(T("teams.md.title")) && shown.includes(T("teams.level_title"))
  && shown.includes(T("teams.tab_team")) && /class="tm-pin-toggle"/.test(shown), shown.slice(0, 300));
check("the goal comes right after the members, before the other choices",
  shown.indexOf(T("teams.tab_members")) < shown.indexOf(T("teams.md.title"))
  && shown.indexOf(T("teams.md.title")) < shown.indexOf(T("teams.level_title"))
  && shown.indexOf(T("teams.level_title")) < shown.indexOf(T("teams.tab_team")));
check("today's use stays in view as one line", shown.includes('class="tm-usage"'));
check("acceptance and the usage figures are in Advanced, not in view",
  !shown.includes(T("teams.quality.title")) && !shown.includes(T("teams.quality.usage"))
  && advanced.includes(T("teams.quality.title")) && advanced.includes(T("teams.quality.usage")));
check("limits and the detailed rights are in Advanced, as before", !shown.includes(T("teams.caps")) && advanced.includes(T("teams.caps"))
  && !shown.includes(T("teams.auth.title")) && advanced.includes(T("teams.auth.title")));
// The two switches on each member row grow with the team, so they are counted apart from the team's own choices.
const perMember = count(shown, /class="tm-(rs|managed)-toggle"/g);
const inView = count(shown, /<(input|select|textarea)\b/g) - perMember, all = count(html, /<(input|select|textarea)\b/g);
check("11 inputs of the team's own in view (3 levels, 2 outside-action choices, pin, name, description, 3 states); the rest behind Advanced",
  inView === 11 && all - inView - perMember >= 40, inView + " + " + perMember + " per member, of " + all);
check("the acceptance form that left the view carried 4 inputs", count(TM.qualityPolicyHtml(team), /<(input|select|textarea)\b/g) === 4);
check("nothing was removed: the forms the handlers look for are all still drawn",
  ["tm-quality-form", "tm-template-form", "tm-quality-save", "tm-pin-toggle"].every((c) => html.includes(c))
  && html.includes("tm-cap-task_turns"));
check("with Advanced open it is drawn open", /<details class="tm-adv" open>/.test(TM.teamTabHtml(team, [], { advOpen: true })));
check("the (i) of Advanced says what is inside, in both languages", vi["teams.advanced_note"].indexOf("Nghiệm thu") === 0
  && /^Acceptance, usage figures/.test(en["teams.advanced_note"]));
check("a new team's per-job limits read Unlimited in the limits form", (() => {
  const f = TM.capsFormHtml(team);
  return /tm-cap-task_turns[\s\S]{0,400}checked/.test(f) || /tm-unl-task_turns[^>]*checked/.test(f) || /data-unl="task_turns"[^>]*checked/.test(f);
})(), TM.capsFormHtml(team).slice(0, 600));

process.exit(fails ? 1 : 0);
