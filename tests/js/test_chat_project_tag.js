/* Project tag on each chat row of the history list (2026-11-09): a small folder chip with the project name.

       node tests/js/test_chat_project_tag.js

   Checks the row template, the late fill once /projects answers, the i18n keys and the CSS that lets a long name
   shrink instead of pushing the time and message count off a narrow column. */
const fs = require("fs");
const path = require("path");
const R = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(R, f), "utf8");
const SRC = read("dashboard/sessions-ui.js");
const STYLE = read("dashboard/style.css");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const rl = SRC.slice(SRC.indexOf("function renderList(items, hasMore)"), SRC.indexOf("async function doSearch(q)"));
check("row shows the tag only in the owner's list and not for the project being filtered",
  rl.includes("var pid = (!kenhLoc && s.project_id && s.project_id !== curProject()) ? String(s.project_id) : \"\";"));
check("tag sits in the meta line with the project id", /'<span class="ci-proj" data-pid="' \+ esc\(pid\) \+ '"'/.test(rl));
check("tag content comes from projTagHtml", rl.includes("projTagHtml(pid) + '</span>'"));
check("project name is escaped", /projIcon\(p\) \+ '<span class="ci-proj-name">' \+ esc\(p\.name \|\| ""\) \+ '<\/span>'/.test(SRC));

const lp = SRC.slice(SRC.indexOf("async function loadProjects()"), SRC.indexOf("function renderProjBar()"));
check("loading projects fills the tags drawn before /projects answered", lp.includes("fillProjTags();"));

// Run fillProjTags for real on a fake list.
const fStart = SRC.indexOf("  function projTagHtml(pid) {");
const fEnd = SRC.indexOf("  function renderProjBar() {");
const helpers = SRC.slice(fStart, fEnd);
const tags = [{ pid: "p1" }, { pid: "gone" }].map(function (o) {
  return { innerHTML: "x", title: "x", getAttribute: (k) => (k === "data-pid" ? o.pid : null) };
});
const env = {
  listEl: { querySelectorAll: (q) => (q === ".ci-proj[data-pid]" ? tags : []) },
  projById: (id) => (id === "p1" ? { id: "p1", name: "Kho <DISON>" } : null),
  projIcon: () => "<svg></svg>",
  esc: (s) => String(s).replace(/</g, "&lt;").replace(/>/g, "&gt;"),
  window: { t: (k, v) => k + ":" + (v && v.ten) },
};
const run = new Function(...Object.keys(env), helpers + "\nfillProjTags();");
run(...Object.values(env));
check("known project gets icon and escaped name", tags[0].innerHTML === '<svg></svg><span class="ci-proj-name">Kho &lt;DISON&gt;</span>');
check("known project gets a tooltip", tags[0].title === "sess.proj_tag_title:Kho <DISON>");
check("deleted project empties the tag (hidden by CSS)", tags[1].innerHTML === "" && tags[1].title === "");

check("tooltip key in vi and en", !!vi["sess.proj_tag_title"] && !!en["sess.proj_tag_title"] &&
  vi["sess.proj_tag_title"].includes("{ten}") && en["sess.proj_tag_title"].includes("{ten}"));
check("empty tag takes no room", STYLE.includes(".ci-proj:empty { display: none; }"));
check("long project name ends in ellipsis", /\.ci-proj-name \{[^}]*text-overflow: ellipsis/.test(STYLE));
check("the tag is the meta item that shrinks", /\.ci-meta > \.ci-proj \{ flex: 0 1 auto; min-width: 0;/.test(STYLE));

if (fails) { console.log("\n" + fails + " FAIL"); process.exit(1); }
console.log("\nOK - chat_project_tag");
