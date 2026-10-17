// 0.209.0: acceptance criteria editor, parser and the owner's acceptance card (teams.js).
//
//     node tests/js/test_team_acceptance_ui_0209.js
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}
const p = TM.parseCriteria("file: a.md\ncontains: b.md | 300 | giá, liên hệ\njson: d.json | x, y\ncmd: pytest -q | tail\nconfirm: a.md\nbừa bãi");
check("parser reads each kind", p.criteria.length === 5 && p.criteria[1].min_chars === 300
  && p.criteria[1].must_contain.join() === "giá,liên hệ" && p.criteria[2].keys.join() === "x,y"
  && p.criteria[3].command === "pytest -q | tail" && p.criteria[4].kind === "owner_confirm", JSON.stringify(p));
check("parser reports a line it cannot read", p.bad.length === 1 && p.bad[0] === "bừa bãi");
const card = { task_id: "t_1", status: "review", stale: [], criteria: [{ kind: "file_exists", path: "a<b>.md" }],
  last: [{ idx: 0, kind: "file_exists", verdict: "pass", evidence: { path: "a<b>.md", sha256: "abcdef1234567890" } }] };
let h = TM.messageHtml({ id: 9, author_kind: "system", content: "x", meta: { kind: "acceptance_review", acceptance: card } }, {});
check("review card: escaped, verdict, short hash, Accept and Send back", h.includes("a&lt;b&gt;.md") && h.includes(vi["teams.acc.v.pass"])
  && h.includes("abcdef123456") && h.includes('data-acc-decide="accept"') && h.includes('data-acc-decide="reject"'), h);
h = TM.acceptanceCardHtml({ id: 9, meta: { acceptance: Object.assign({}, card, { status: "accepted", stale: ["a.md"] }) } });
check("decided card: no buttons, says accepted and stale", !h.includes("data-acc-decide") && h.includes(vi["teams.acc.st.accepted"])
  && h.includes(vi["teams.acc.stale"]), h);
check("blocked kinds: review shows the card, failed edits the job",
  TM.blockedAction("acceptance_review").act === "view" && TM.blockedAction("acceptance_failed").act === "amend");
const q = TM.queueHtml({ waiting: [{ id: "t_2", title: "Viết" }] }, { accEdit: "t_2" });
check("queue: a waiting job has an Acceptance button and its editor opens inline",
  q.includes('data-acc-edit="t_2"') && q.includes("tm-acc-form") && q.includes('data-acc-task="t_2"'), q);
const keys = Object.keys(vi).filter(function (k) { return k.indexOf("teams.acc.") === 0; });
check("acceptance strings exist in both languages", keys.length >= 16 && keys.every(function (k) { return en[k]; }));
if (fails) { console.log("\nFAILED " + fails); process.exit(1); }
console.log("\nALL OK");
