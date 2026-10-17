// 0.207.0: the approval card in the team chat and the team's outside-action switch (teams.js).
//
//     node tests/js/test_team_approval_ui_0207.js
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const teamsJs = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}

const ap = { approval_id: "ap_1", team_rev: 2, kind: "action", title: "Gửi tin <b>ưu đãi</b>", action: "Gửi 1 tin",
  scope: "Khách cũ", impact: "200 tin", evidence: ["khach.csv"], status: "pending",
  actions: [{ label: "Zalo: send_message", call: 'zalo_send_message {"message":"<x>"}', used: false }] };
const msg = { id: 41, author_kind: "system", content: "Xin duyệt", meta: { kind: "approval_request", approval: ap } };
let h = TM.messageHtml(msg, {});
check("a pending card renders as an approval card, not a plain system line", h.includes("tm-ap ") && !h.includes("tm-sys"), h);
check("card text is escaped", h.includes("Gửi tin &lt;b&gt;ưu đãi&lt;/b&gt;") && !h.includes("<b>ưu đãi"), h);
check("card shows the exact call and the evidence", h.includes("zalo_send_message") && h.includes("khach.csv"), h);
check("pending card has Approve, Ask for changes, Reject bound to the request and its revision",
  ["approve", "changes", "reject"].every(function (d) { return h.includes('data-ap-decide="' + d + '"'); })
  && h.includes('data-ap="ap_1"') && h.includes('data-ap-rev="2"'), h);
const states = ["approved", "consumed", "rejected", "changes_requested", "expired", "superseded", "cancelled", "revoked"];
const bad = states.filter(function (st) {
  const x = TM.approvalCardHtml({ id: 1, meta: { approval: Object.assign({}, ap, { status: st }) } });
  return x.includes('data-ap-decide="approve"') || !x.includes(vi["teams.ap.st." + st] || "@@");
});
check("a decided card has no decision buttons and says its server state", bad.length === 0, bad);
check("only an approved, unused card offers Revoke",
  TM.approvalCardHtml({ id: 1, meta: { approval: Object.assign({}, ap, { status: "approved" }) } }).includes('data-ap-decide="revoke"')
  && !TM.approvalCardHtml({ id: 1, meta: { approval: Object.assign({}, ap, { status: "consumed" }) } }).includes("revoke"));
const q = TM.approvalCardHtml({ id: 1, meta: { approval: Object.assign({}, ap, { kind: "question", actions: [] }) } });
check("a prose question says the assistant asked in words", q.includes(vi["teams.ap.prose"]), q);
const wm = TM.workModeHtml({ work_mode: "gated" });
check("work mode switch: gated checked by default, both choices explained",
  /value="gated"[^>]*checked/.test(wm) && wm.includes(vi["teams.wm.full_desc"]), wm);
check("work mode switch: full checked when the team is full", /value="full"[^>]*checked/.test(TM.workModeHtml({ work_mode: "full" })));
const keys = Object.keys(vi).filter(function (k) { return k.indexOf("teams.ap.") === 0 || k.indexOf("teams.wm.") === 0; });
check("every new key exists in both languages", keys.length > 20 && keys.every(function (k) { return en[k] && vi[k]; }),
  keys.filter(function (k) { return !en[k]; }));
check("no em or en dash in the new strings", keys.every(function (k) { return !/[\u2013\u2014]/.test(vi[k] + en[k]); }));
check("each decision click carries its own key (retry replays, second tab is told)",
  /decision_key: dkey/.test(teamsJs) && /\/approvals\/" \+ q\(d\.ap\) \+ "\/decide"/.test(teamsJs));
check("reject and changes ask for a reason before sending", /dec === "reject" \|\| dec === "changes"/.test(teamsJs));
check("card text is 16px for phones", /\.tm-ap \{[^}]*font-size: 16px/.test(css));

if (fails) { console.log("\nFAILED " + fails); process.exit(1); }
console.log("\nALL OK");
