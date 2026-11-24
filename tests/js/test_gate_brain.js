// The Javis Gate card of the Connections page (#1726, owner 2026-11-24: "ô chọn brain cho Javis Gate anh đồng ý").
// Pure helpers of dashboard/gate-brain.js, plus where the card is mounted, loaded, styled and translated.
//   node tests/js/test_gate_brain.js
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = path.join(__dirname, "..", "..");
const G = require(path.join(ROOT, "dashboard", "gate-brain.js"));
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const VI = JSON.parse(read("dashboard/i18n/vi.json"));
const EN = JSON.parse(read("dashboard/i18n/en.json"));

let fails = 0;
function check(name, fn) {
  try { fn(); console.log("ok   " + name); } catch (e) { fails++; console.log("FAIL " + name + "  [" + e.message + "]"); }
}

const tr = (k, v) => k + (v && v.name ? ":" + v.name : "");
const H = { tr: tr, ic: (n) => "<i " + n + ">", infoBtn: () => '<button class="info-i"></button>',
            infoBody: (h) => '<div class="info-body" hidden>' + h + "</div>" };
const brains = [{ folder: "Brain Default", name: "Brain Default" }, { folder: "ca-nhan", name: "Cá Nhân" }];

check("'Brain used last' comes first and is the default when nothing is picked", () => {
  const o = G.options({ brains: brains, default: "" }, tr);
  assert.strictEqual(o[0].value, "");
  assert.strictEqual(o[0].label, "gate.brain_last");
  assert.ok(o[0].selected);
  assert.strictEqual(o.filter(x => x.selected).length, 1);
});
check("then every brain, by the name the owner sees, valued by its folder", () => {
  const o = G.options({ brains: brains, default: "" }, tr);
  assert.deepStrictEqual(o.slice(1).map(x => [x.value, x.label]), [["Brain Default", "Brain Default"], ["ca-nhan", "Cá Nhân"]]);
});
check("the saved default is the selected option", () => {
  const o = G.options({ brains: brains, default: "ca-nhan" }, tr);
  assert.deepStrictEqual(o.filter(x => x.selected).map(x => x.value), ["ca-nhan"]);
});
check("a saved default whose brain is gone stays listed, selected and marked deleted", () => {
  const o = G.options({ brains: brains, default: "Old", default_missing: true }, tr);
  const sel = o.filter(x => x.selected);
  assert.strictEqual(sel.length, 1);
  assert.strictEqual(sel[0].value, "Old");
  assert.strictEqual(sel[0].label, "gate.brain_gone:Old");
});

const html = G.cardHtml({ ok: true, installed: true, page: "/ext/javis-gate/", brains: brains, default: "ca-nhan" }, H);
check("the card is a Connections page card named Javis Gate", () => {
  assert.ok(html.includes('class="prov-card conn-card gate-card"'));
  assert.ok(html.includes(">Javis Gate<"));
});
check("one-line label tied to the select, explanation behind (i)", () => {
  assert.ok(/<label for="gateBrainSel">gate\.brain_label<\/label><button class="info-i">/.test(html));
  assert.ok(html.includes('<select id="gateBrainSel"'));
  assert.ok(/<div class="info-body" hidden>gate\.brain_info<\/div>/.test(html));
});
check("the selected option is drawn selected", () => {
  assert.ok(html.includes('<option value="ca-nhan" selected>Cá Nhân</option>'));
  assert.ok(html.includes('<option value="">gate.brain_last</option>'));
});
check("names are escaped", () => {
  const h = G.cardHtml({ brains: [{ folder: "x\"y", name: "<b>bad</b>" }], default: "" }, H);
  assert.ok(!h.includes("<b>bad</b>") && h.includes("&lt;b&gt;bad&lt;/b&gt;") && h.includes('value="x&quot;y"'));
});
check("the Gate page link shows only when the server gives one", () => {
  assert.ok(html.includes('href="/ext/javis-gate/"') && html.includes('target="_blank"'));
  assert.ok(!G.cardHtml({ brains: brains, default: "" }, H).includes("gate-open"));
});
check("a status line for the result of a change", () => {
  assert.ok(html.includes('role="status"') && html.includes("data-gate-msg"));
});

const CON = read("dashboard/console.js");
const IDX = read("dashboard/index.html");
const CSS = read("dashboard/console.css");
const SRC = read("dashboard/gate-brain.js");
check("the Connections page has a spot for the card and mounts it", () => {
  assert.ok(CON.includes('id="mcpGate"'));
  assert.ok(CON.includes('window.JavisGateBrain.mount(document.getElementById("mcpGate"))'));
});
check("the Connected tab search hides the card unless it matches", () => {
  assert.ok(/getElementById\("mcpGate"\)[\s\S]{0,200}gate\.textContent\.toLowerCase\(\)\.includes\(q\)/.test(CON));
});
check("loaded with the Connections page's lazy group", () => {
  const blk = /<script id="javis-lazy" type="application\/json">([\s\S]*?)<\/script>/.exec(IDX);
  const lazy = JSON.parse(blk[1]);
  assert.ok((lazy.packs || []).some(u => u.startsWith("/static/gate-brain.js?v=")));
});
check("the card reads and saves through the Gate endpoints", () => {
  assert.ok(SRC.includes('"/gate/brains"') && SRC.includes('"/gate/default-brain"'));
  assert.ok(SRC.includes("installed"), "no card without the Javis Gate package");
});
check("phone: 16px select, 44px tall, full width at 390px", () => {
  assert.ok(/\.gate-brain-sel \{[^}]*font-size: 16px;[^}]*min-height: 44px;/.test(CSS));
  assert.ok(/@media \(max-width: 600px\) \{\s*\.gate-brain-row \.gate-brain-sel \{ flex-basis: 100%; max-width: 100%; \}/.test(CSS));
});
check("every key exists in both dictionaries", () => {
  const keys = ["gate.card_desc", "gate.brain_label", "gate.brain_last", "gate.brain_gone", "gate.brain_info",
                "gate.open_page", "gate.saved", "gate.err_save"];
  keys.forEach(k => assert.ok(VI[k] && EN[k], k));
  assert.strictEqual(EN["gate.brain_label"], "Default brain for Javis Gate");
  assert.strictEqual(EN["gate.brain_last"], "Brain used last");
});
check("no em or en dash in the card's code and text", () => {
  const bad = /[\u2013\u2014]/;
  assert.ok(!bad.test(SRC));
  Object.keys(EN).filter(k => k.startsWith("gate.")).forEach(k => assert.ok(!bad.test(EN[k]) && !bad.test(VI[k]), k));
});

if (fails) { console.log(fails + " failed"); process.exit(1); }
console.log("all ok");
