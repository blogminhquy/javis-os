// 0.274.0: webhook security on the Work page (webhook platform M4): a branch waiting for approval shows Approve and
// Reject in Details; the rules box carries the signature check as JSON (secret masked), and says when an adapter is
// not yet checked against a real account; both languages carry every new string.
const path = require("path");
const fs = require("fs");
const W = require(path.join(__dirname, "../../dashboard/webhooks.js"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const d = W.detailHtml({ id: "ev_9", status: "waiting", branches: [
  { action_id: "pos", kind: "tool", status: "approval", detail: "waiting for your approval", delivery_id: "dlv_1", receipt: {} },
  { action_id: "ai", kind: "ai", status: "completed", detail: "", delivery_id: "dlv_2", receipt: {} }] });
check("a branch waiting for approval has Approve and Reject for that event and action",
  d.includes('class="s-btn whApprove" data-ev="ev_9" data-act="pos" data-d="approve"') && d.includes('data-d="reject"')
  && d.includes("wh.br_approval"));
check("a finished branch has no approval buttons", (d.match(/whApprove/g) || []).length === 2);
const p = W.rulesPanelHtml({ rules: {}, actions: [], verify: { provider: "systeme_io", secret: "••••" }, adapter_status: "unverified" });
check("the panel shows the signature check, secret masked, and the unverified note",
  p.includes("whVerifyTxt") && p.includes("systeme_io") && p.includes("••••") && p.includes("wh.adapter_unverified"));
check("no provider: the box is empty", /class="whVerifyTxt"[^>]*><\/textarea>/.test(W.rulesPanelHtml({ rules: {}, actions: [], verify: { provider: "none" } })));
const keys = ["wh.br_approval", "wh.approve", "wh.reject", "wh.approved", "wh.rejected", "wh.err_not_waiting", "wh.verify_label",
  "wh.verify_hint", "wh.adapter_unverified"];
for (const lang of ["vi", "en"]) {
  const t = JSON.parse(fs.readFileSync(path.join(__dirname, `../../dashboard/i18n/${lang}.json`), "utf8"));
  check(`${lang}: every new string present, no long dashes`, keys.every(k => t[k] && t[k].length && !/[\u2013\u2014]/.test(t[k])));
}
const js = fs.readFileSync(path.join(__dirname, "../../dashboard/webhooks.js"), "utf8");
check("Approve/Reject call the approve route with the decision", js.includes('api("/webhooks/events/approve", { id: x.dataset.ev, action: x.dataset.act, decision: x.dataset.d })'));
check("Save sends the signature check too", js.includes("verify: rv.rules"));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
