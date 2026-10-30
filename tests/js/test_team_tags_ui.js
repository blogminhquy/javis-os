// 0.195.0: project tags on teams (filter row, tags under the name, tag editor) and opening the team worked in last
// (dashboard/teams.js).
//
//     node tests/js/test_team_tags_ui.js
"use strict";
const fs = require("fs");
const { napTruoc, coNap } = require("./_thu_tu_nap");   // load order that understands lazy groups (0.417.0)
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

const TP = require(path.join(root, "dashboard", "tag-picker.js"));
const ws = read("workspace.js");
const teams = [
  { team_id: "a", name: "Nội dung Web", tags: ["Web bán hàng"], last: { ts: 100 }, updated_at: 100 },
  { team_id: "b", name: "Quảng cáo Web", tags: ["web bán hàng", "Q4"], last: { ts: 300 }, updated_at: 300 },
  { team_id: "c", name: "Game", tags: [], last: { ts: 200 }, updated_at: 200 },
];

// ---- one implementation, two pages (owner: "cái gì mà có rồi thì tái sử dụng") ----
check("the Partners page draws its filter bar and its tag picker with the shared module",
  ws.includes("window.JavisTagPicker.barHtml({") && ws.includes("m.innerHTML = TP.pickerHtml(dongChonTag(item, danhSach()))") &&
  ws.includes("TP.bind(m, {") && !ws.includes('class="ws-tag-new"'));
check("the Teams page uses the same module and the shared dropdown (JavisChatSide.menu)",
  src.includes("TP.barHtml({") && src.includes("picker.pickerHtml(tagPickRows(") && src.includes("TP.bind(m, {") &&
  src.includes("cs.menu(t, tagMenuRows(") && !src.includes("tm-tagf") && !src.includes("tm-tag-input"));
check("tag-picker.js loads before workspace.js and teams.js",
  napTruoc("tag-picker.js", ["workspace.js", "teams.js"], read("index.html")));

const tags = TM.allTags(teams);
check("allTags: one entry per tag (case folded key), with how many teams carry it, sorted",
  JSON.stringify(tags.map((g) => [g.ten, g.key, g.n])) === JSON.stringify([["Q4", "q4", 1], ["Web bán hàng", "web bán hàng", 2]]),
  JSON.stringify(tags));
check("filterTeams: a tag key keeps only its teams; 'no tag yet' keeps untagged; none keeps all",
  TM.filterTeams(teams, "web bán hàng").map((t) => t.team_id).join() === "a,b" &&
  TM.filterTeams(teams, TM.TAG_NONE).map((t) => t.team_id).join() === "c" && TM.filterTeams(teams, "").length === 3);

let h = TM.tagBarHtml(teams, "q4");
check("filter bar: the Partners bar (cs-proj-cur) with the chosen tag and the clear button",
  h.includes('class="cs-proj-cur"') && h.includes("Q4") && h.includes('class="cs-proj-x"'), h);
check("filter bar with no filter: All teams, no clear button", TM.tagBarHtml(teams, "").includes(vi["teams.tags_all"]) &&
  !TM.tagBarHtml(teams, "").includes("cs-proj-x"));
const picked = [];
const rows = TM.tagMenuRows(teams, "", (k) => picked.push(k));
check("dropdown rows: All teams, No tag yet, a line, then each tag with its count (like the Partners dropdown)",
  rows[0].right === "3" && rows[0].on && rows[1].right === "1" && rows[2].sep &&
  rows.slice(3).map((r) => r.label + ":" + r.right).join() === "Q4:1,Web bán hàng:2", JSON.stringify(rows));
rows[4].run();
check("picking a tag in the dropdown filters by its key", picked[0] === "web bán hàng");

const pr = TM.tagPickRows(teams[0], teams);
check("picker rows: every tag in the list, checked when the team has it",
  JSON.stringify(pr.map((r) => r.ten + ":" + r.on)) === JSON.stringify(["Q4:false", "Web bán hàng:true"]), JSON.stringify(pr));
h = TM.teamListHtml([teams[0]], "", 400, "a", "", "a");
check("row menu in tag mode shows the Partners picker (back, new tag box, check rows)",
  h.includes("tm-tag-menu") && h.includes('data-act="quay"') && h.includes('class="ws-tag-new"') &&
  /role="menuitemcheckbox" aria-checked="true"[^>]*data-tag="Web bán hàng"/.test(h), h);
h = TM.teamListHtml([teams[0]], "", 400, "a", "");
check("row menu has a Tag item next to Pin, Rename, Delete", /data-tag-team="a"/.test(h) && h.includes(vi["ws.tag_menu"]));
check("a team's tags show in its row tooltip, no chips drawn (like a partner card)",
  TM.teamListHtml([teams[0]], "", 400, null, "").includes('title="Nội dung Web\n' + vi["teams.tags_title"] + ': Web bán hàng"') &&
  !TM.teamListHtml([teams[0]], "", 400, null, "").includes("tm-tag-chip"));
check("the team settings no longer carry a separate tag editor",
  !TM.settingsFormHtml(Object.assign({ status: "active", description: "" }, teams[0])).includes("tag"));
check("tag picker: shared markup escapes names", TP.pickerHtml([{ ten: "<b>x</b>", key: "k", on: false }]).includes("&lt;b&gt;"));

check("last worked team: the highest owner time wins over newer messages elsewhere",
  TM.lastWorkedTeam([Object.assign({}, teams[0], { owner_at: 50 }), teams[1], teams[2]]).team_id === "a");
check("last worked team: with no owner time yet, the team with the newest message",
  TM.lastWorkedTeam(teams).team_id === "b");
check("last worked team: nothing when there is no team", TM.lastWorkedTeam([]) === null);

check("the page opens it once per visit, after the list arrives, unless a team was asked for",
  /else if \(!append && !S\.autoOpened && !S\.activeId\)/.test(src) && src.includes("openTeam(lastT.team_id)"));
check("opening a team tells the server (any device opens it next time)", src.includes('call("POST", "/teams/" + q(id) + "/opened", {})'));
check("the chosen filter is remembered per device and survives a blocked storage",
  src.includes('var TAG_FILTER_KEY = "javis.teams.tagFilter"') && /try \{ return \(typeof localStorage/.test(src));
["teams.tags_all", "teams.tags_none", "teams.tag_pick_title", "teams.tags_title", "ws.tag_menu", "ws.tag_none"].forEach((k) =>
  check("i18n " + k + " in vi and en", !!vi[k] && !!en[k]));

process.exit(fails ? 1 : 0);
