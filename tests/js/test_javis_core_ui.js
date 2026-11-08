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
// 2026-11-05 (owner): "keep Javis Core exactly like the other agents; only it is the system one you cannot remove, it
// starts with my system prompt, and Auto is on and cannot be turned off".
check("row: System badge, Auto switch always on and locked, no ... menu",
  /var he = laAgent && !!x\.system;/.test(src) && /function cardSubInner\(x, he, max\) \{\s*return \(he \? '<span class="ws-sys">' \+ esc\(t\("ws\.system_badge"\)\)/.test(src)
  && /\(laAgent \? cardSubHtml\(x, he\) : ""\)/.test(src)
  && /rowToggleHtml\(he \? coreAutoRow\(x\) : S\.rs\[x\.slug\],\s*\{ saving: !he && !!S\.rsSaving\[x\.slug\], locked: he \}\)/.test(src)
  && /function coreAutoRow\(x\) \{[\s\S]{0,200}enabled: true, status: "active"/.test(src)
  && /\(he \? "" : '<button type="button" class="ws-item-more"/.test(src));
const RA = fs.readFileSync(path.join(root, "dashboard", "resonance-agent.js"), "utf8");
check("a locked switch cannot be clicked", /\(o\.saving \|\| o\.locked \? " disabled" : ""\)/.test(RA));
check("right column: the same agent editor as every assistant, without Export and Delete",
  !/ws-core-card|JavisCoreModel|wsCoreRename/.test(src)
  && /if \(S\.loai === "agent"\) \{[\s\S]{0,600}<div class="ws-form" id="wsAgentForm"><\/div><div class="ws-auto-block" id="wsAuto"><\/div>' \+\s*\(item\.system \? "" :/.test(src)
  && /if \(!item\.system\) \{\s*host\.querySelector\("#wsExport"\)/.test(src));
check("opening it goes to the brain's default chat (where reports land)",
  /if \(!id && !moiHan && item\.system\) \{[\s\S]{0,300}api\("\/javis-core\/session", \{ method: "POST"/.test(src));
check("its Auto panel always shows", /function veAuto\(item\) \{[\s\S]{0,300}!\(item\.system \|\| autoBat\(S\.rs, item\.slug\)\)\) \{ box\.innerHTML = ""; return; \}/.test(src)
  && !/!item \|\| item\.system\) return;/.test(src));
check("the list asks the server for it (system=1)", /\/agents\?brain=" \+ b \+ "&prompt=0&system=1"/.test(src));
check("i18n vi/en", vi["ws.system_badge"] === "Hệ thống" && en["ws.system_badge"] === "System");
check("CSS for the badge", css.includes(".ws-sys {") && !css.includes(".ws-core-card {"));
// 2026-11-08 (owner: "chữ Hệ thống nên cho xuống dòng bên dưới, bên trái, cạnh avatar"): the badge leaves the name's row
// and opens the line under it, before any tag chips.
const subSrc = src.slice(src.indexOf("  var CHIP_TOI_DA = 3;"), src.indexOf("  // HTML của MỘT hàng."));
const vm = require("vm");
const subCtx = vm.createContext({ t: (k) => k, esc: (s) => String(s), tagsCua: (x) => x.tags || [] });
vm.runInContext(subSrc + "\nglobalThis.cardSubHtml = cardSubHtml;", subCtx);
const coreSub = subCtx.cardSubHtml({ name: "Javis Core", tags: ["Ops"] }, true);
check("Javis Core card: System badge on the line under the name, then its tags",
  coreSub.startsWith('<span class="ws-item-sub"><span class="ws-sys">ws.system_badge</span><span class="ws-tags"')
  && coreSub.includes('title="Ops"') && subCtx.cardSubHtml({ name: "X" }, false) === ""
  && !/<\/strong>' \+\s*\(he \? '<span class="ws-sys">/.test(src), coreSub);
check("CSS: the sub line is one row, chips shrink, 14px on phones",
  /\.ws-item-sub \{ display: flex;[^}]*overflow: hidden; \}/.test(css)
  && /\.ws-item-sub \.ws-tags \{[^}]*flex-wrap: nowrap;/.test(css)
  && /@media \(max-width: 900px\) \{\s*\.ws-item-sub \.ws-sys, \.ws-item-sub \.ws-tag \{ font-size: 14px;/.test(css));
check("the separate Core card script is gone",!fs.existsSync(path.join(root, "dashboard", "core-model.js"))
  && !fs.readFileSync(path.join(root, "dashboard", "index.html"), "utf8").includes("core-model.js"));

if (fails) { console.log("\nFAIL " + fails); process.exit(1); }
console.log("\nOK test_javis_core_ui");
