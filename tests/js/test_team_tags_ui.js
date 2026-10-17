// 0.195.0: project tags on teams (filter row, tags under the name, tag editor) and opening the team worked in last
// (dashboard/teams.js).
//
//     node tests/js/test_team_tags_ui.js
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");
const vi = JSON.parse(read("i18n/vi.json"));
const en = JSON.parse(read("i18n/en.json"));
const TM = require(path.join(root, "dashboard", "teams.js"));
const css = read("console.css");
const src = read("teams.js");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}

const teams = [
  { team_id: "a", name: "Nội dung Web", tags: ["Web bán hàng"], last: { ts: 100 }, updated_at: 100 },
  { team_id: "b", name: "Quảng cáo Web", tags: ["web bán hàng", "Q4"], last: { ts: 300 }, updated_at: 300 },
  { team_id: "c", name: "Game", tags: [], last: { ts: 200 }, updated_at: 200 },
];

const tags = TM.allTags(teams);
check("allTags: one entry per tag (case folded), with how many teams carry it, sorted",
  JSON.stringify(tags) === JSON.stringify([{ tag: "Q4", n: 1 }, { tag: "Web bán hàng", n: 2 }]), JSON.stringify(tags));
check("filterTeams: a tag keeps only its teams (any case); no tag keeps all",
  TM.filterTeams(teams, "WEB BÁN HÀNG").map((t) => t.team_id).join() === "a,b" && TM.filterTeams(teams, "").length === 3);

let h = TM.tagBarHtml(teams, "Q4");
check("tag bar: All first, then each tag with its count; the chosen one is pressed",
  /data-tag-filter="" aria-pressed="false"/.test(h) && /data-tag-filter="Q4" aria-pressed="true"/.test(h) &&
  /Web bán hàng<\/span><span class="tm-tagf-n">2</.test(h), h);
check("tag bar is empty (hidden) while no team has a tag", TM.tagBarHtml([{ team_id: "x", tags: [] }], "") === "");

h = TM.teamListHtml([teams[1]], "", 400, null, "");
check("a team row shows its tags under the name", h.includes('<span class="tm-team-tags"><span class="tm-tag-chip">web bán hàng</span>' +
  '<span class="tm-tag-chip">Q4</span></span>'), h);
check("a row without tags adds nothing", !TM.teamListHtml([teams[2]], "", 400, null, "").includes("tm-team-tags"));

h = TM.tagEditorHtml(teams[0], teams);
check("editor: the team's tags with a remove button each, a box to add one",
  /data-tag-remove="Web bán hàng"/.test(h) && h.includes('class="tm-tag-input"') && h.includes('maxlength="32"'), h);
check("editor suggests the tags other teams use (and not the ones this team has)",
  /data-tag-add="Q4"/.test(h) && !/data-tag-add="Web bán hàng"/.test(h) && /<option value="Q4">/.test(h), h);
check("the settings form carries the tag editor", TM.settingsFormHtml(Object.assign({ status: "active", description: "" }, teams[0]))
  .includes("tm-tags-edit"));

check("last worked team: the highest owner time wins over newer messages elsewhere",
  TM.lastWorkedTeam([Object.assign({}, teams[0], { owner_at: 50 }), teams[1], teams[2]]).team_id === "a");
check("last worked team: with no owner time yet, the team with the newest message",
  TM.lastWorkedTeam(teams).team_id === "b");
check("last worked team: nothing when there is no team", TM.lastWorkedTeam([]) === null);

check("the page opens it once per visit, after the list arrives, unless a team was asked for",
  /else if \(!append && !S\.autoOpened && !S\.activeId\)/.test(src) && src.includes("openTeam(lastT.team_id)"));
check("opening a team tells the server (any device opens it next time)", src.includes('call("POST", "/teams/" + q(id) + "/opened", {})'));
check("Enter or comma in the tag box adds the tag; a tag change redraws only the tag box",
  src.includes('contains("tm-tag-input") && (e.key === "Enter" || e.key === ",")') &&
  src.includes('box.outerHTML = tagEditorHtml(S.team, S.teams)'));
check("the chosen filter is remembered per device and survives a blocked storage",
  src.includes('var TAG_FILTER_KEY = "javis.teams.tagFilter"') && /try \{ return \(typeof localStorage/.test(src));
check("tag input is 16px (no zoom on a phone) and chips are styled",
  /\.tm-tag-input \{[^}]*font-size: 16px/.test(css) && /\.tm-tagf\.is-on \{/.test(css) && /\.tm-team-tags \{/.test(css));
["teams.tags", "teams.tags_all", "teams.tags_none", "teams.tag_add", "teams.tag_remove", "teams.tags_hint"].forEach((k) =>
  check("i18n " + k + " in vi and en", !!vi[k] && !!en[k]));

process.exit(fails ? 1 : 0);
