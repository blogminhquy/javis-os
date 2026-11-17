// 2026-11-12: the Team tab keeps in view only what an owner decides for a team (dashboard/teams.js teamTabHtml).
//
//     node tests/js/test_team_settings_simple.js
//
// A customer: "cái phần cài đặt của team khá phức tạp, nhiều thông số quá, cần đơn giản hơn, tập trung vào mục tiêu
// thôi". Acceptance, usage figures, limits, detailed rights and the reply log now sit in
// Advanced, closed by default. Nothing was removed.
//
// 17/11/2026, the owner: "quá nhiều cài đặt, phần trang cài đặt bị quá phức tạp anh muốn lược bỏ hết để tự động thôi tối
// giản lại vì không ai động vào đâu, các nút lưu bố trí cũng không hợp lý". Advanced is gone from the tab (the server keeps
// its automatic defaults), every field saves itself (no Save button), Archive and Delete stand apart at the end.
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
const count = (h, re) => (h.match(re) || []).length;

check("no Advanced section any more", !html.includes("tm-adv") && !html.includes(T("teams.advanced")));
check("in view: members, the goal, how far the deputy decides, outside actions, the team",
  html.includes(T("teams.tab_members")) && html.includes(T("teams.md.title")) && html.includes(T("teams.level_title"))
  && html.includes(T("teams.tab_team")) && /class="tm-pin-toggle"/.test(html), html.slice(0, 300));
check("the goal comes right after the members, before the other choices",
  html.indexOf(T("teams.tab_members")) < html.indexOf(T("teams.md.title"))
  && html.indexOf(T("teams.md.title")) < html.indexOf(T("teams.level_title"))
  && html.indexOf(T("teams.level_title")) < html.indexOf(T("teams.tab_team")));
check("no usage line, no limit numbers, no acceptance form, no detailed rights, no reply log",
  !html.includes('class="tm-usage"') && !html.includes("tm-cap-") && !html.includes("tm-quality-form")
  && !html.includes(T("teams.auth.title")) && !html.includes(T("teams.caps")));
// The two switches on each member row grow with the team, so they are counted apart from the team's own choices.
const perMember = count(html, /class="tm-(rs|managed)-toggle"/g);
const own = count(html, /<(input|select|textarea)\b/g) - perMember;
check("9 inputs of the team's own (3 levels, 2 outside-action choices, pin, name, description, pause)", own === 9,
  own + " + " + perMember + " per member");
check("no Save button: name and description save themselves", !html.includes("tm-save")
  && /name="tm-set-name" data-team-field="name"/.test(html) && /name="tm-set-desc" data-team-field="description"/.test(html));
check("pause is one switch that reads the team's state", /class="tm-pause-toggle"/.test(html)
  && /class="tm-pause-toggle" checked/.test(TM.teamTabHtml(Object.assign({}, team, { status: "paused" }), [], {}))
  && !html.includes('name="tm-status"'));
const zone = html.indexOf("tm-danger-zone");
check("Archive and Delete stand apart at the very end, in the danger zone", zone > html.indexOf(T("teams.tab_team"))
  && html.slice(zone).includes("data-team-archive") && html.slice(zone).includes("data-delete-team")
  && html.indexOf("data-delete-team") > zone);
const arch = TM.teamTabHtml(Object.assign({}, team, { status: "archived" }), [], {});
check("an archived team offers Restore instead of Archive, and its fields are read only",
  arch.includes("data-team-unarchive") && !arch.includes("data-team-archive")
  && /name="tm-set-name"[^>]*disabled/.test(arch) && /class="tm-pause-toggle"[^>]*disabled/.test(arch));
check("the new words exist in both languages", ["teams.pause_team", "teams.danger_zone", "teams.archive_team",
  "teams.unarchive_team"].every((k) => vi[k] && en[k]));
const capped = TM.replyStatusHtml({ replies: [{ agent_key: "b", status: "error", reason: "cap" }] }, { members: team.members });
check("a blocked reply no longer offers to open limit numbers that are gone, Try again stays",
  capped.includes("tm-replies") && !/data-reply-act="limits"/.test(capped), capped.slice(0, 400));

process.exit(fails ? 1 : 0);
