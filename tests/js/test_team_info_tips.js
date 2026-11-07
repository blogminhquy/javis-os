// Team page: explanations fold into the (i) (owner, 2026-11-07: "gập nốt dòng giải thích và mô tả ở tên của nhóm ấy").
//
//     node tests/js/test_team_info_tips.js
//
// Renders the real functions of dashboard/teams.js. In Node there is no info-tip.js, so infoBody() draws its block open as
// <div class="info-body">; each explanation must sit in such a block and nowhere else as a visible line.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const src = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}
// The text of `key` as teams.js draws it in Node (tw falls back to the key itself when no dictionary is loaded).
// teams.js translates with the Vietnamese dictionary in Node; match the drawn text, escaped as teams.js escapes it.
function T(k) { return String(vi[k]).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
function inInfoBody(html, needle) {
  const re = /<div class="info-body"[^>]*>([\s\S]*?)<\/div>/g;
  let m;
  while ((m = re.exec(html))) if (m[1].includes(needle)) return true;
  return false;
}
function outsideInfoBody(html, needle) {
  return html.replace(/<div class="info-body"[^>]*>[\s\S]*?<\/div>/g, "").includes(needle);
}

const team = { id: "tm_x", name: "Shop", description: "Sells online", members: [], caps: {}, leader_key: "a",
  authority: { authority: true, caps: {} }, mandate: null };

// Reply log: the note on what counts sits in the (i).
const turns = TM.turnsHtml([], team);
check("reply log: note folded into (i)", inInfoBody(turns, T("teams.turns_note")) && !outsideInfoBody(turns, T("teams.turns_note")), turns);

// Authority: the scope sentence sits in the (i) by the title.
const auth = TM.authorityHtml(Object.assign({}, team, { members: [{ agent_key: "a", slug: "a", name: "A" }] }));
check("authority: scope folded into (i)", inInfoBody(auth, T("teams.auth.scope")) && !outsideInfoBody(auth, T("teams.auth.scope")), auth);

// Mandate form: how to write sources sits in the (i) by the Sources label, and the textarea stays the label's control.
const md = TM.mandateHtml({ mandate: null }, true);
check("mandate: sources help folded into (i)", inInfoBody(md, T("teams.md.sources_help")) && !outsideInfoBody(md, T("teams.md.sources_help")), md);
check("mandate: labels point at their textarea (the (i) button inside a label must not become its control)",
  /<label class="tm-field" for="tm-md-sources">/.test(md) && /<textarea id="tm-md-sources" name="tm-md-sources"/.test(md), md);

// Advanced section: the note sits in the (i) inside <summary>, not as a line under it.
const tab = TM.teamTabHtml(team, {});
check("advanced: note folded into (i)", inInfoBody(tab, T("teams.advanced_note")) && !outsideInfoBody(tab, T("teams.advanced_note")), tab);

// Info panel (not exported): the description goes in the (i) beside the name; files and links explain themselves there too.
const info = src.slice(src.indexOf("function infoTabHtml(t)"), src.indexOf("\n  function ", src.indexOf("function infoTabHtml(t)") + 10));
check("info panel: description in the (i) beside the team name, no line under it",
  info.includes('(t.description ? infoBtn() : "")') && info.includes("(t.description ? infoBody(esc(t.description)") &&
  !info.includes("'<span class=\"tm-sub\">' + esc(t.description)"));
check("info panel: files and links headings carry an (i) with their help",
  info.includes('infoBody(esc(tw("teams.info_files_help")))') && info.includes('infoBody(esc(tw("teams.info_links_help")))'));

// Dictionaries: the empty lines are short now, the help lives in its own key, both languages.
["teams.info_files_help", "teams.info_links_help", "teams.info_no_files", "teams.info_no_links"].forEach(function (k) {
  check("i18n vi+en have " + k, typeof vi[k] === "string" && typeof en[k] === "string");
});
check("empty files/links lines are one short sentence", vi["teams.info_no_files"].length <= 30 && vi["teams.info_no_links"].length <= 30
  && en["teams.info_no_files"].length <= 30 && en["teams.info_no_links"].length <= 30);

if (fails) { console.log("\n" + fails + " FAILED"); process.exit(1); }
console.log("\nOK - team page explanations live in the (i)");
