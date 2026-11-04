// My tasks get tags and subtasks (0.463.0): the pure helpers of dashboard/tasks.js.
// Run: node tests/js/test_tags_subtasks_0463.js
"use strict";
const path = require("path");
const fs = require("fs");
const M = require(path.join(__dirname, "..", "..", "dashboard", "tasks.js"));

let fails = 0;
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails++; }

// ---- tags ----
check("tags read as a list", JSON.stringify(M.tagsOf({ tags: ["a", "b", "a", ""] })) === '["a","b"]');
check("an old task with one project reads as that tag", JSON.stringify(M.tagsOf({ project: "p1" })) === '["p1"]');
check("no tags, no project: none", M.tagsOf({}).length === 0);

const store = { tasks: [
  { id: "m_1", title: "Post", tags: ["p_a", "p_b"], status: "open" },
  { id: "m_2", title: "Old one", project: "p_b", status: "open" },
  { id: "m_3", title: "Done", tags: ["p_a"], status: "done" },
] };
const me = M.mineModel(store, "2026-11-04", "10:00");
const inTag = (tag) => me.items.filter((i) => M.inList(i, "proj:" + tag, "2026-11-04")).map((i) => i.ref).sort().join(",");
check("a task shows in the list of every tag it carries", inTag("p_a") === "m_1" && inTag("p_b") === "m_1,m_2");
check("items carry their tags and the first one as proj", me.items.find((i) => i.ref === "m_1").proj === "p_a");

// ---- subtasks: open first in their own order, ticked ones sink to the bottom ----
const subs = [{ t: "a", done: true }, { t: "b", done: false }, { t: "c", done: true }, { t: "d", done: false }];
check("open subtasks first, ticked ones after, each keeps its index", M.subOrder(subs).join(",") === "1,3,0,2");
check("no subtasks, nothing to draw", M.subOrder([]).length === 0 && M.subOrder(undefined).length === 0);

// ---- links in the notes ----
const L = M.linksIn("Read [[wiki/Pricing]] and [[Funnel plan|the plan]], again [[wiki/Pricing]].\nSee https://example.com/a?b=1. and http://x.vn");
check("wikilinks found once each", L.filter((x) => x.wiki).map((x) => x.target).join("|") === "wiki/Pricing|Funnel plan");
check("a wikilink shows its alias, or the note name", L[0].label === "Pricing" && L[1].label === "the plan");
check("web links found, trailing punctuation dropped", L.filter((x) => !x.wiki).map((x) => x.url).join("|") === "https://example.com/a?b=1|http://x.vn");
check("plain notes have no links", M.linksIn("buy milk").length === 0 && M.linksIn("").length === 0);

// ---- the page: subtasks only on my tasks, no project select left, new keys in both languages ----
const src = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "tasks.js"), "utf8");
check("the old project select is gone", src.indexOf("projSelect") < 0 && src.indexOf("data-pproj") < 0);
check("subtasks are drawn only for my own tasks", /function subsLive\(it\) \{ return it\.src === "mine"/.test(src));
const vi = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "i18n", "en.json"), "utf8"));
const keys = (src.match(/tw\("(nv\.(?:t|sub|ln)\.[a-z_]+)"/g) || []).map((m) => m.slice(4, -1));
check("the new keys exist in vi.json and en.json", keys.length > 10 && keys.every((k) => vi[k] && en[k]));
check("the side column says Tags", vi["nv.projects"] === "Tags" && en["nv.projects"] === "Tags");

console.log(fails ? "\n" + fails + " failed" : "\nall ok");
process.exit(fails ? 1 : 0);
