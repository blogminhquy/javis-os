// 0.181.0: the assistant page. A tag-menu filter for agents whose Auto is on, answers no longer run up to the outline bar
// (and the chat has no sideways scroll), and the Settings column uses the same smaller text scale as the team panel.
//
//     node tests/js/test_assistant_page_0181.js
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const D = path.join(root, "dashboard");

global.window = { t: (k) => k, ic: () => "", addEventListener() {}, removeEventListener() {},
                  matchMedia: () => ({ matches: false }) };
global.document = { getElementById: () => null, createElement: () => ({ classList: { add() {}, remove() {} }, appendChild() {} }), body: { classList: { add() {}, remove() {} } } };
global.localStorage = { getItem: () => null, setItem() {} };
require(path.join(D, "workspace.js"));
const W = window.JavisWorkspace;
const src = fs.readFileSync(path.join(D, "workspace.js"), "utf8");
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
const ccss = fs.readFileSync(path.join(D, "console.css"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(D, "i18n", "en.json"), "utf8"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

const ds = [{ slug: "a", name: "Alpha", tags: ["Sales"] }, { slug: "b", name: "Beta", tags: [] }, { slug: "c", name: "Gamma", tags: ["Sales"] },
  { slug: "d", name: "Delta", tags: [] }];
const rs = { a: { enabled: true, status: "active" }, b: { enabled: true, status: "active" }, c: { enabled: false, status: "active" },
  d: { enabled: true, status: "retired" } };
check("filter value for Auto on starts with a space, so it never clashes with a real tag", W.TAG_AUTO === " auto" && W.TAG_AUTO !== W.TAG_NONE);
check("Auto on: only agents whose Auto is enabled AND active", W.loc(ds, "", W.TAG_AUTO, true, rs).map((x) => x.slug).join() === "a,b");
check("Auto on combines with the search box", W.loc(ds, "beta", W.TAG_AUTO, true, rs).map((x) => x.slug).join() === "b");
check("no Auto data yet: the Auto filter shows nobody instead of everybody", W.loc(ds, "", W.TAG_AUTO, true, undefined).length === 0);
check("the other filters are unchanged", W.loc(ds, "", W.TAG_NONE, true, rs).map((x) => x.slug).join() === "b,d"
  && W.loc(ds, "", "", true, rs).length === 4);
check("the list passes the Auto map to the filter", /loc\(danhSach\(\), S\.q, S\.nhom, laTag, S\.rs\)/.test(src));
check("the pseudo filters are never turned into a tag key or reset as a missing tag",
  /S\.nhom && !laLocGia\(S\.nhom\)\) S\.nhom = laKhoa/.test(src) && /if \(S\.nhom && !laLocGia\(S\.nhom\)\) \{\s*var kLoc/.test(src));
check("tag menu row: Auto on with its count and a bolt icon, only when the Auto module is loaded",
  /if \(window\.JavisResonanceAgent\) \{\s*var soAuto = danhSach\(\)\.filter\(function \(x\) \{ return autoBat\(S\.rs, x\.slug\); \}\)\.length;/.test(src)
  && /label: t\("ws\.tag_auto"\), icon: "zap", right: String\(soAuto\)/.test(src) && /S\.nhom === TAG_AUTO \? "zap"/.test(src));
check("label in vi and en", vi["ws.tag_auto"] === "Đang bật Auto" && en["ws.tag_auto"] === "Auto on");

check("answers on the assistant page keep the main chat's 72ch measure (no 120ch widening)",
  !/max-width: min\(120ch/.test(ccss));
check("the chat has no sideways scroll from the outline bar's negative margin",
  css.includes(".transcript.cm-co-thanh { padding-right: 34px; overflow-x: hidden; }"));
check("assistant Settings column: Auto block, goal card and pulse use 13.5px text and 14.5px headings, like the team panel",
  /\.ws-right \.rsa-panel, \.ws-right \.rsa-state,[\s\S]*?\.ws-right \.rs-card, \.tm-side \.rs-card[^{]*\{ font-size: 13\.5px; \}/.test(ccss)
  && /\.ws-right \.rsa-title, \.ws-right \.pulse-title[\s\S]*?\{ font-size: 14\.5px; \}/.test(ccss));
check("touch screens keep 16px selects in the side panels (iOS zooms in on smaller ones)",
  /@media \(pointer: coarse\) \{\s*\.ws-right select, \.tm-side select \{ font-size: 16px; \}/.test(ccss));
const dash = String.fromCharCode(0x2014), en2 = String.fromCharCode(0x2013);
check("no em or en dash in workspace.js", !src.includes(dash) && !src.includes(en2));
process.exit(fails ? 1 : 0);
