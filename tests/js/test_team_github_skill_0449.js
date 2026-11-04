// 0.449.0: GitHub repos and /skill commands in a team chat (teams.js, team-github.js).
//
//     node tests/js/test_team_github_skill_0449.js
"use strict";
const fs = require("fs");
const path = require("path");
const { napTruoc } = require("./_thu_tu_nap");
const ROOT = path.join(__dirname, "..", "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const TG = require(path.join(ROOT, "dashboard", "team-github.js"));
const SL = require(path.join(ROOT, "dashboard", "chat-slash.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const teamsJs = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// ───────────── /skill: which skill a typed message calls ─────────────
const known = ["viet-email", "seo-audit"];
let c = TM.skillCall("/viet-email gửi khách sỉ", known);
check("/skill at the start: the skill, and the words without the address",
  c && c.cmd === "viet-email" && c.rest === "gửi khách sỉ" && !c.mid, JSON.stringify(c));
c = TM.skillCall("Dùng /viet-email cho khách sỉ", known);
check("/skill inside a sentence keeps the name in the words", c && c.cmd === "viet-email" && c.rest === "Dùng viet-email cho khách sỉ" && c.mid,
  JSON.stringify(c));
check("an unknown /word is plain text", TM.skillCall("/khong-co làm gì đó", known) === null);
check("a path or a link is never a skill", TM.skillCall("xem https://a.vn/viet-email và /home/user/x", known) === null);
check("the last skill named in a sentence wins", (TM.skillCall("Dùng /seo-audit rồi /viet-email nhé", known) || {}).cmd === "viet-email");
check("like the main chat, a skill at the start wins", (TM.skillCall("/seo-audit rồi /viet-email nhé", known) || {}).cmd === "seo-audit");
check("no skills known: nothing is a skill", TM.skillCall("/viet-email", []) === null);

// The message carries the main chat's block, and the chat shows the owner's own words.
const sent = SL.buildSkillInvocation("viet-email", "gửi khách sỉ", false);
const sp = TM.skillSplit(sent);
check("the block of the main chat splits back into the skill and the words", sp.slug === "viet-email" && sp.rest === "gửi khách sỉ",
  JSON.stringify(sp));
check("a message without a block is untouched", TM.skillSplit("chào cả nhóm").slug === "" && TM.skillSplit("chào cả nhóm").rest === "chào cả nhóm");
const html = TM.bodyHtml({ content: sent, meta: {}, ts: 1 }, true);
check("the owner's bubble shows a /skill chip and the words, not the block",
  html.indexOf("tm-skill-chip") >= 0 && html.indexOf("/viet-email") >= 0 && html.indexOf("[SKILL") < 0 && html.indexOf("gửi khách sỉ") >= 0, html);
check("a preview never shows the block", TM.plainPreview(sent, 80).indexOf("SKILL") < 0);
check("copying the message copies the words", TM.copyTextOf({ author_kind: "owner", content: sent }) === "gửi khách sỉ");
check("the server reads the same block (team_runner.SKILL_BLOCK_RE)",
  /\[SKILL:\\s\*\(\[A-Za-z0-9_-\]\+\)/.test(fs.readFileSync(path.join(ROOT, "server", "team_runner.py"), "utf8")));

// ───────────── composer wiring ─────────────
check("the + menu has GitHub repo", teamsJs.indexOf('data-plus-github="1"') >= 0);
check("the composer lists skills when typing /", teamsJs.indexOf("skillSuggest(input, box, tok)") >= 0 && teamsJs.indexOf('data-skill="') >= 0);
check("a /skill message is sent as the skill block", teamsJs.indexOf("X.buildSkillInvocation(call.cmd, text, call.mid)") >= 0);
check("team-github.js runs before teams.js", napTruoc("team-github.js", ["teams.js"]));
check("team-github.js is cache-busted in the lazy group", /"\/static\/team-github\.js\?v=\d+"/.test(fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8")));
["teams.gh_attach", "teams.gh_how", "teams.skill_used"].forEach(function (k) {
  check("key " + k + " in vi and en", !!vi[k] && !!en[k]);
});
check("the chip and the picker have styles", css.indexOf(".tm-chip-gh") >= 0 && css.indexOf(".tm-skill-chip") >= 0 && css.indexOf(".tm-gh-pop") >= 0);

// ───────────── team-github.js pure helpers ─────────────
check("chip text: first repo's short name, +N for the rest", TG.chipText(["a/web", "a/api"], 18) === "web +1");
check("chip text is cut on a narrow screen", TG.chipText(["a/a-very-long-repository-name"], 10).length === 10);
check("no repo: no chip text", TG.chipText([], 18) === "");
check("toggle adds and removes", TG.toggle(["a/x"], "a/y").join() === "a/x,a/y" && TG.toggle(["a/x", "a/y"], "a/x").join() === "a/y");
check("sameSet ignores order", TG.sameSet(["a", "b"], ["b", "a"]) && !TG.sameSet(["a"], ["a", "b"]));
let v = TG.split([{ full_name: "a/x" }, { full_name: "a/y" }], ["a/y"], "");
check("chosen repos come first", v.all.map(function (r) { return r.full_name; }).join() === "a/y,a/x" && v.selected.length === 1);
v = TG.split([{ full_name: "a/x" }], ["a/z"], "");
check("a chosen repo the list lacks stays listed so it can be unticked", v.selected.length === 1 && v.selected[0].full_name === "a/z");
v = TG.split([{ full_name: "a/x" }], ["a/z"], "x");
check("while searching, only what matches", v.all.length === 1 && v.all[0].full_name === "a/x");

[["team-github.js", fs.readFileSync(path.join(ROOT, "dashboard", "team-github.js"), "utf8")]].forEach(function (f) {
  check(f[0] + " has no em dash", f[1].indexOf("—") < 0);
});

console.log(fails ? "\nĐỎ: " + fails : "\nXANH");
process.exit(fails ? 1 : 0);
