// 0.208.0: the department mandate section and the opportunity card (teams.js).
//
//     node tests/js/test_team_mandate_ui_0208.js
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
let h = TM.mandateHtml({ mandate: null });
check("no mandate: a hint and a Set button", h.includes(vi["teams.md.none"]) && h.includes('data-mandate-edit="1"'), h);
const m = { version: 3, status: "active", outcome: "Báo cáo <đúng>", metrics: ["đúng hạn"], sources: ["folder:bao-cao", "mcp:x"],
  autonomy: { act: ["file_changed"], propose: ["job_failed"] }, budget: {}, stop: {},
  sources_state: [{ source: "folder:bao-cao", state: "ok" }, { source: "mcp:x", state: "missing", missing: "chưa có kết nối 'x'" }] };
h = TM.mandateHtml({ mandate: m });
check("active mandate: escaped outcome, version, pause and revoke buttons",
  h.includes("Báo cáo &lt;đúng&gt;") && h.includes(vi["teams.md.st.active"]) && h.includes('data-mandate-status="paused"')
  && h.includes('data-mandate-status="revoked"'), h);
check("a missing source is shown with what is missing", h.includes(vi["teams.md.src.missing"]) && h.includes("chưa có kết nối"), h);
check("levels are listed per kind", h.includes(vi["teams.md.level.act"]) && h.includes(vi["teams.md.level.propose"]), h);
check("a revoked mandate has no switch buttons", !TM.mandateHtml({ mandate: Object.assign({}, m, { status: "revoked" }) })
  .includes("data-mandate-status"));
const f = TM.mandateHtml({ mandate: m }, true);
check("edit form carries the current values and one level per kind", f.includes("tm-md-form") && f.includes("folder:bao-cao")
  && (f.match(/name="tm-md-lvl-/g) || []).length === 4, f);
const o = { opp_id: "op_1", status: "proposed", reason: "tài liệu <x> đổi", benefit: "kịp", evidence: ["bao-cao/a.md"],
  source: "folder", ref: "bao-cao", version_key: "abc" };
h = TM.messageHtml({ id: 5, author_kind: "system", content: "x", meta: { kind: "mandate_opportunity", opportunity: o } }, {});
check("proposal card: escaped reason, evidence, version and two buttons", h.includes("tài liệu &lt;x&gt; đổi")
  && h.includes("bao-cao/a.md") && h.includes("abc") && h.includes('data-opp-decide="accept"') && h.includes('data-opp-decide="reject"'), h);
check("a decided proposal shows its state, no buttons",
  !TM.opportunityCardHtml({ id: 1, meta: { opportunity: Object.assign({}, o, { status: "rejected" }) } }).includes("data-opp-decide"));
const keys = Object.keys(vi).filter(function (k) { return k.indexOf("teams.md.") === 0; });
check("all mandate strings exist in both languages", keys.length > 30 && keys.every(function (k) { return en[k]; }));
if (fails) { console.log("\nFAILED " + fails); process.exit(1); }
console.log("\nALL OK");
