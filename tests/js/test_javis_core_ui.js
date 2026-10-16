// 0.185.0: Javis Core on the Partners page (dashboard/workspace.js).
//
//     node tests/js/test_javis_core_ui.js
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");

global.window = { t: (k) => k, ic: () => "", addEventListener() {}, removeEventListener() {},
                  matchMedia: () => ({ matches: false }) };
global.document = { getElementById: () => null, createElement: () => ({ classList: { add() {}, remove() {} }, appendChild() {} }), body: { classList: { add() {}, remove() {} } } };
global.localStorage = { getItem: () => null, setItem() {} };
require(path.join(root, "dashboard", "workspace.js"));
const W = window.JavisWorkspace;
const src = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
const css = fs.readFileSync(path.join(root, "dashboard", "console.css"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

const core = { slug: "javis-core", name: "Javis Core", system: true, protected: true, pinned: true, last_chat_at: 0 };
const ags = [{ slug: "b", name: "Bống", pinned: true, last_chat_at: 99 }, { slug: "c", name: "Cam", last_chat_at: 500 }, core];
check("sorting: Javis Core first, even ahead of pinned and more recent ones",
  W.sapXep(ags, "last_chat_at").map(x => x.slug).join(",") === "javis-core,b,c");
const blocks = W.gomNhom(W.sapXep(ags, "last_chat_at"), "*", [], (x) => x.slug === "c");
check("blocks: Javis Core alone in the first block, above needs-you and pinned",
  blocks[0].he === true && blocks[0].items.map(x => x.slug).join() === "javis-core"
  && blocks[1].can === true && blocks[2].ghim === true
  && blocks.reduce((n, b) => n + b.items.length, 0) === 3, JSON.stringify(blocks.map(b => Object.keys(b))));
check("row: System badge, no Auto switch, no ... menu for the system assistant",
  /var he = laAgent && !!x\.system;/.test(src) && /\(he \? '<span class="ws-sys">' \+ esc\(t\("ws\.system_badge"\)\)/.test(src)
  && /\(!he && window\.JavisResonanceAgent/.test(src) && /\(he \? "" : '<button type="button" class="ws-item-more"/.test(src));
check("right column: a read-only card, no editor and no Delete button",
  /if \(S\.loai === "agent" && item\.system\) \{[\s\S]{0,700}ws-core-card[\s\S]{0,900}\} else if \(S\.loai === "agent"\)/.test(src));
check("opening it goes to the brain's default chat (where reports land)",
  /if \(!id && !moiHan && item\.system\) \{[\s\S]{0,300}api\("\/javis-core\/session", \{ method: "POST"/.test(src));
check("no Auto panel mounted for it", /!item \|\| item\.system\) return;/.test(src));
check("the list asks the server for it (system=1)", /\/agents\?brain=" \+ b \+ "&prompt=0&system=1"/.test(src));
check("0.190.0: the core card carries no memory list, one short line says to ask in chat",
  !/wsCoreMem|JavisCoreMemory/.test(src) && /chat/.test(vi["ws.core_note"]) && vi["ws.core_note"].length < 160);
check("0.190.0: an assistant's column opens on the settings form; the Auto block only while Auto is on",
  /host\.innerHTML = '<div class="ws-form" id="wsAgentForm"><\/div><div class="ws-auto-block" id="wsAuto"><\/div>'/.test(src)
  && /function veAuto\(item\) \{[\s\S]{0,300}!autoBat\(S\.rs, item\.slug\)\) \{ box\.innerHTML = ""; return; \}/.test(src)
  && (src.match(/veDanhSach\(\); veAuto\(dangChon\(\)\);/g) || []).length === 2);
check("i18n vi/en", vi["ws.system_badge"] === "Hệ thống" && en["ws.system_badge"] === "System"
  && !!vi["ws.core_note"] && !!en["ws.core_note"]);
check("CSS for the badge and card", css.includes(".ws-sys {") && css.includes(".ws-core-card {"));

if (fails) { console.log("\nFAIL " + fails); process.exit(1); }
console.log("\nOK test_javis_core_ui");
