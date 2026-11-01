// 0.274.0: webhook rules on the Work page (webhook platform M2). Each card opens a rules box (JSON) with a sample
// body and a Test button that shows what /webhooks/simulate decided, step by step; the three states decided at
// receipt have their own words; text from the payload is escaped; both languages carry every new string.
const path = require("path");
const fs = require("fs");
const W = require(path.join(__dirname, "../../dashboard/webhooks.js"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

for (const st of ["filtered", "invalid", "duplicate"]) {
  const r = W.eventRowHtml({ run_id: "ev_1", at: 1, status: st, error: "why" });
  check(`${st}: its own words and no Retry or Mark done`, r.includes("wh.st_" + st) && !r.includes("whEvRetry") && !r.includes("whEvDone"));
}
const card = (rules) => W.dialogHtml({ id: "wh_1", name: "Đơn", target: "task", text: "x", level: "full", brain: "/b",
  url: "/hooks/wh_1", enabled: true, history: [], rules: rules }, []);
check("every hook has a Rules button (the panel opens inside the popup)", card({}).includes("whRules"));
check("a card with rules marks the button", card({ filter: { path: "a", op: "exists" } }).includes("whRules has-rules")
  && !card({}).includes("has-rules"));
const panel = W.rulesPanelHtml({ rules: { filter: { path: "a", op: "eq", value: "</textarea><script>x</script>" } } });
check("the rules box is prefilled and escaped", panel.includes("whRulesTxt") && panel.includes("&lt;/textarea&gt;")
  && !panel.includes("<script>"));
check("an empty rules box is empty, not {}", !W.rulesPanelHtml({ rules: {} }).includes("{}"));
check("rules text: empty -> no rules, broken JSON -> refused before sending",
  W.readRules("").ok && JSON.stringify(W.readRules(" ").rules) === "{}" && !W.readRules("{nope").ok
  && W.readRules('{"filter":{"path":"a","op":"exists"}}').rules.filter.op === "exists");

const sim = W.simHtml({ ok: true, decision: "filtered", reason: "filter did not match", fields: {},
  trace: { schema: [{ path: "order.id", pass: true, why: "ok" }],
           filter: [{ path: "event", op: "eq", value: "sale", actual: "<b>refund</b>", pass: false }] } });
check("simulate view: decision, each schema and filter step with pass/fail, values escaped",
  sim.includes("wh.sim_filtered") && /wh-sim-step pass[^>]*> wh\.sim_schema order\.id: ok/.test(sim) && /wh-sim-step fail[^>]*> wh\.sim_filter event eq sale/.test(sim)
  && sim.includes("&lt;b&gt;refund") && !sim.includes("<b>refund"));
const ran = W.simHtml({ ok: true, decision: "run", fields: { order_id: "A1", total: 5 }, business_key: { scope: "shop", key: "order:A1" },
  trace: {}, prompt: "SỰ KIỆN <x>" });
check("simulate view: fields, business key and the prompt the run would get",
  ran.includes("wh.sim_run") && ran.includes("<code>order_id</code>: A1") && ran.includes("shop/order:A1")
  && ran.includes("SỰ KIỆN &lt;x&gt;"));
check("simulate view: an error is shown", W.simHtml({ ok: false, error: "Rules are not valid: x" }).includes("Rules are not valid"));

const keys = ["wh.st_filtered", "wh.st_invalid", "wh.st_duplicate", "wh.rules", "wh.rules_hint", "wh.rules_label",
  "wh.sample_label", "wh.simulate", "wh.rules_save", "wh.rules_saved", "wh.rules_bad_json", "wh.sim_run", "wh.sim_filtered",
  "wh.sim_invalid", "wh.sim_duplicate", "wh.sim_schema", "wh.sim_filter", "wh.sim_fields", "wh.sim_key", "wh.sim_prompt"];
for (const lang of ["vi", "en"]) {
  const d = JSON.parse(fs.readFileSync(path.join(__dirname, `../../dashboard/i18n/${lang}.json`), "utf8"));
  check(`${lang}: every new string present`, keys.every(k => d[k] && d[k].length));
  check(`${lang}: no long dashes`, keys.every(k => !/[\u2013\u2014]/.test(d[k])));
}
const js = fs.readFileSync(path.join(__dirname, "../../dashboard/webhooks.js"), "utf8");
check("Test calls the simulate route with the draft rules, Save goes through update",
  js.includes('api("/webhooks/simulate", { id: h.id, rules: rr.rules') && js.includes('api("/webhooks/update", Object.assign({ id: h.id, rules: rr.rules'));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
