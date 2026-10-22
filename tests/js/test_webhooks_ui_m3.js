// 0.274.0: webhook actions on the Work page (webhook platform M3). Every event row has Details, which shows each
// action's branch (state in words, what the receiver said, its delivery id) and the rules' trace; the rules box also
// holds the actions as JSON; masked header values are sent back as they are (the server keeps the stored key).
const path = require("path");
const fs = require("fs");
const W = require(path.join(__dirname, "../../dashboard/webhooks.js"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

check("every event row with an id has Details", W.eventRowHtml({ id: "ev_1", status: "done" }).includes("whEvInfo")
  && W.eventRowHtml({ id: "ev_1", status: "done" }).includes("whEvDetail"));
const d = W.detailHtml({ status: "unknown", branches: [
  { action_id: "crm", kind: "http", status: "unknown", detail: "HTTP 500 <x>", delivery_id: "dlv_abc", receipt: {} },
  { action_id: "ship", kind: "plugin", status: "accepted", detail: "", delivery_id: "dlv_def", receipt: { ref: "VD-9" } }] });
check("details: each branch with its state in words, detail escaped, delivery id, receipt ref",
  d.includes("<b>crm</b> (http)") && d.includes("wh.br_unknown") && d.includes("HTTP 500 &lt;x&gt;")
  && d.includes("dlv_abc") && d.includes("VD-9") && d.includes("wh.br_accepted"));
check("details: a failed or unknown branch is marked", d.includes("wh-br-unknown") && d.includes("var(--warn-ink)"));
const tr = W.detailHtml({ status: "filtered", error: "filter did not match", branches: [],
  trace: { filter: [{ path: "event", op: "eq", value: "sale", actual: "refund", pass: false }] } });
check("details: the trace of a filtered event", tr.includes("wh.sim_filtered") && tr.includes("wh.sim_filter event eq sale"));
check("details: nothing to show", W.detailHtml({ branches: [], trace: {} }).includes("wh.no_detail"));
const panel = W.rulesPanelHtml({ rules: {}, actions: [{ id: "crm", kind: "http", url: "https://x", headers: { "X-Api-Key": "••••" } }] });
check("the panel has the actions box, prefilled with masked headers only", panel.includes("whActsTxt") && panel.includes("••••"));
check("actions text: empty -> none; not a list -> refused",
  W.readActions("").ok && W.readActions("").actions.length === 0 && !W.readActions('{"id":"a"}').ok && !W.readActions("[").ok
  && W.readActions('[{"id":"a","kind":"ai"}]').actions[0].id === "a");
const keys = ["wh.details", "wh.delivery", "wh.no_detail", "wh.br_completed", "wh.br_accepted", "wh.br_failed", "wh.br_unknown",
  "wh.br_pending", "wh.br_retry", "wh.br_running", "wh.br_silent", "wh.br_waiting", "wh.br_cancelled", "wh.actions_label", "wh.actions_hint"];
for (const lang of ["vi", "en"]) {
  const t = JSON.parse(fs.readFileSync(path.join(__dirname, `../../dashboard/i18n/${lang}.json`), "utf8"));
  check(`${lang}: every new string present, no long dashes`, keys.every(k => t[k] && t[k].length && !/[\u2013\u2014]/.test(t[k])));
}
const js = fs.readFileSync(path.join(__dirname, "../../dashboard/webhooks.js"), "utf8");
check("Save sends rules and actions together", js.includes('{ id: h.id, rules: rr.rules, actions: ra.actions, verify: rv.rules }'));
check("Details reads the event detail route", js.includes('api("/webhooks/events/" + encodeURIComponent(b.dataset.ev))'));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
