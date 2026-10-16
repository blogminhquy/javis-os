// 0.188.0: memory controls on the Javis Core card (dashboard/core-memory.js).
//
//     node tests/js/test_core_memory.js
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const CM = require(path.join(root, "dashboard", "core-memory.js"));
const src = fs.readFileSync(path.join(root, "dashboard", "core-memory.js"), "utf8");
const ws = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
const html = fs.readFileSync(path.join(root, "dashboard", "index.html"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "en.json"), "utf8"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}
check("meta line: type, origin, source, unconfirmed, date",
  CM.metaLine({ type: "preference", origin: "javis-learned", source: "chat 02/10", status: "inferred", updated: "2026-10-02" })
  === "preference · core.mem_learned · chat 02/10 · core.mem_inferred · 2026-10-02");
const h = CM.itemHtml({ slug: "a<b", title: "<i>x</i>", body: "y", type: "user" });
check("item text is escaped", !h.includes("<i>") && h.includes("&lt;i&gt;"));
check("forgetting asks first, with scope (brain, chats kept, git/backup limit)",
  /confirm\(tw\("core\.mem_forget_confirm", \{ title: m\.title \|\| slug, brain: data\.brain \|\| "" \}\)\)/.test(src)
  && /git/.test(vi["core.mem_forget_confirm"]) && /git/.test(en["core.mem_forget_confirm"])
  && /chat/.test(vi["core.mem_forget_confirm"]));
check("uses the server endpoints", ["/memory/items?brain=", "/memory/learning", "/memory/forget", "/memory/edit", "/profile"]
  .every(u => src.includes(u)));
check("mounted on the Javis Core card", /window\.JavisCoreMemory\.mount\(host\.querySelector\("#wsCoreMem"\), brain\(\)\)/.test(ws)
  && html.indexOf("/static/core-memory.js") > 0 && html.indexOf("/static/core-memory.js") < html.indexOf("/static/workspace.js"));
const keys = Object.keys(vi).filter(k => k.startsWith("core."));
check("i18n vi/en for every core.* key", keys.length >= 15 && keys.every(k => en[k]));
if (fails) { console.log("\nFAIL " + fails); process.exit(1); }
console.log("\nOK test_core_memory");
