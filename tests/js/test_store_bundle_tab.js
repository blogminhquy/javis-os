// Javis Store: a `bundle` pack (several kinds in one, e.g. javis.crm) has a tab of its own (2026-11-11).
//
//     node tests/js/test_store_bundle_tab.js
//
// Before, no tab listed kind `bundle` and the search box only looks inside the open tab, so the one bundle of the
// Store could not be found, installed, updated or removed from this page. The tab shows only while the catalog has
// such a pack. Draws the real grid (`veKho`), does not scan the source.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..", "..");
let fails = 0;
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails++;
}

const doc = {
  activeElement: null, getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
  createElement: () => ({ style: {}, classList: { add() {}, remove() {} }, querySelectorAll: () => [], appendChild() {} }),
  body: { appendChild() {} },
};
const host = { innerHTML: "", querySelector: () => null, querySelectorAll: () => [] };
const pack = (o) => Object.assign({
  id: "javis.x", kind: "skill", name: { vi: "X" }, description: { vi: "mo ta" }, tier: "data", verified: true,
  nguon: "kho", author: { name: "Javis" }, version: "1.0.0", installed: false,
  download: { url: "https://x/y.zip", sha256: "a" }, nhom: "Ban hang", upstream: {},
}, o);
const CRM = pack({ id: "javis.crm", kind: "bundle", tier: "code", name: { vi: "Quan ly khach hang (CRM)" } });
const SKILL = pack({ id: "javis.skill-a" });
const TOOL = pack({ id: "javis.tool-a", kind: "tool" });

let catalog = { ok: true, fetched_at: Math.floor(Date.now() / 1000), packs: [SKILL, TOOL, CRM] };
const win = { ic: (t) => "<svg data-ic=\"" + t + "\"></svg>", Alpine: { store: () => ({ go() {} }) } };
const alpineBefore = globalThis.Alpine;
globalThis.Alpine = win.Alpine;
new Function("window", "document", "fetch", fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8"))(
  win, doc, () => Promise.resolve({ json: () => Promise.resolve(catalog) }));
const P = win.JavisPacks || {};

(async () => {
  await P.veKho({}, host, false, "skill");
  const h = host.innerHTML;
  check("a catalog with a bundle draws the Bundle tab", h.includes('data-kho-loai="bundle"'));
  check("the Bundle tab comes last, after Connector", h.indexOf('data-kho-loai="bundle"') > h.indexOf('data-kho-loai="connector"'));
  check("the phone dropdown lists Bundle too", h.includes('<option value="bundle"'));
  check("another tab does not show the bundle pack", !h.includes("javis.crm") && h.includes("javis.skill-a"));

  await P.veKho({}, host, false, "bundle");
  const hb = host.innerHTML;
  check("the Bundle tab opens and is the active one", /class="kho-tab on" data-kho-loai="bundle"/.test(hb));
  check("the Bundle tab lists the CRM pack and nothing of another kind",
    hb.includes("javis.crm") && !hb.includes("javis.skill-a") && !hb.includes("javis.tool-a"));

  // A bundle with a newer version: the update strip has a chip that jumps to its tab.
  catalog = { ok: true, fetched_at: Math.floor(Date.now() / 1000),
    packs: [SKILL, Object.assign({}, CRM, { installed: true, installed_version: "1.0.0", version: "1.1.0" })] };
  await P.veKho({}, host, false, "skill");
  const hu = host.innerHTML;
  check("an installed bundle is counted on its tab", /data-kho-loai="bundle">[^<]*<span class="kho-dem">1<\/span>/.test(hu));
  check("a bundle with a new version gets its chip in the update strip", hu.includes('data-kho-moi="bundle"'));

  // No bundle in the catalog: no tab, and asking for it falls back to Skill.
  catalog = { ok: true, fetched_at: Math.floor(Date.now() / 1000), packs: [SKILL, TOOL] };
  await P.veKho({}, host, false, "bundle");
  const hn = host.innerHTML;
  check("a catalog without a bundle draws no Bundle tab", !hn.includes('data-kho-loai="bundle"'));
  check("opening the Bundle tab then falls back to Skill", /class="kho-tab on" data-kho-loai="skill"/.test(hn));

  // A pack that declares no kind lands in Bundle rather than vanishing.
  catalog = { ok: true, fetched_at: Math.floor(Date.now() / 1000), packs: [SKILL, pack({ id: "javis.no-kind", kind: "" })] };
  await P.veKho({}, host, false, "bundle");
  check("a pack without a kind shows on the Bundle tab", host.innerHTML.includes("javis.no-kind"));

  globalThis.Alpine = alpineBefore;
  if (fails) { console.log("\nFAIL - test_store_bundle_tab: " + fails); process.exit(1); }
  console.log("\nOK - test_store_bundle_tab");
})();
