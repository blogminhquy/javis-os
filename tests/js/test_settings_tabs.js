/* Old navigation targets must select the right Settings tab, including while already
   on Settings. Moving between tabs must preserve the static controls and their handlers. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const src = fs.readFileSync(path.join(__dirname, "../../dashboard/console.js"), "utf8");
const railCtx = { ICON: {}, GICON: {}, t: k => k };
vm.createContext(railCtx);
vm.runInContext(src.slice(src.indexOf("  const RAIL_ITEMS ="), src.indexOf("  // Nhãn nhóm chứa")) + "\nglobalThis.groups = railGroups();", railCtx);
assert.deepEqual(Array.from(railCtx.groups.find(g => g.foot).items, i => i.id), ["settings", "share", "account"]);
assert.ok(!railCtx.groups.flatMap(g => g.items).some(i => ["pet", "usage", "logs", "chatbots"].includes(i.id)),
  "legacy targets must not reappear through the ungrouped-items fallback");
function fn(name) {
  const start = src.search(new RegExp("  (?:async )?function " + name + "\\("));
  assert.ok(start >= 0, "missing " + name);
  return src.slice(start, src.indexOf("\n  }", start) + 4);
}
const nav = { active: "home", settingsTab: "general" };
const rendered = [];
const ctx = {
  Alpine: { store: () => nav }, TRANG_GOP: { runtime: "usage" },
  TRANG_CUOI_KEY: "javis_last_page", localStorage: { setItem() {} },
  window: {}, document: { body: { classList: { toggle() {} } } },
  _pageLeave: null, renderPage: id => rendered.push([id, nav.settingsTab]),
  refreshModelUi() {}, parkQuickSet() {}, recomputeGraph() {},
};
vm.createContext(ctx);
vm.runInContext(fn("navigateTo"), ctx);
for (const [target, tab] of [["usage", "usage"], ["pet", "pet"], ["logs", "updates"], ["runtime", "usage"]]) {
  ctx.navigateTo(target);
  assert.equal(nav.active, "settings", target + " must highlight Settings in the sidebar");
  assert.equal(nav.settingsTab, tab);
  assert.deepEqual(rendered.at(-1), ["settings", tab]);
}
ctx.navigateTo("settings", true, "voice");
assert.equal(nav.settingsTab, "voice");
const count = rendered.length;
ctx.navigateTo("settings", true, "voice");
assert.equal(rendered.length, count, "clicking the current tab must not reset its form");
ctx.navigateTo("settings");
assert.equal(nav.settingsTab, "general", "sidebar Settings opens General");
ctx.navigateTo("settings", true, "invalid");
assert.equal(nav.settingsTab, "general", "unknown tab falls back to General");
for (const target of ["share", "account"]) {
  ctx.navigateTo(target);
  assert.equal(nav.active, target, target + " stays a separate page");
}

// Clone-and-replace of cviewBody must first return borrowed controls to their holder.
// Otherwise a same-page tab switch detaches #quickSet and future visits cannot find it.
const holder = { appendChild(node) { node.parentNode = this; } };
let oldBody;
const controls = { parentNode: null, value: "unchanged", onchange: () => "still wired" };
const parent = { replaceChild(fresh) {
  assert.equal(controls.parentNode, holder, "controls were detached before being parked");
  oldBody = fresh;
} };
oldBody = { cloneNode: () => ({ parentNode: parent }), parentNode: parent };
controls.parentNode = oldBody;
const renderCtx = {
  body: () => oldBody, _renderGen: 0, STUDIO_PAGES: [],
  document: { getElementById: id => id === "quickSet" ? controls : id === "quickSetHolder" ? holder : null },
  renderSettingsPage() {}, renderSettings() {},
};
vm.createContext(renderCtx);
vm.runInContext(fn("parkQuickSet") + "\n" + fn("renderPage"), renderCtx);
(async () => {
  await renderCtx.renderPage("settings");
  assert.equal(controls.value, "unchanged");
  assert.equal(controls.onchange(), "still wired");
  // The OpenAI key must be captured at click time, before an awaited save allows
  // another tab/visit to refresh the form. No real credentials or requests are used.
  const fields = Object.fromEntries(Object.entries({ vpOaVoice: "nova", vpElVoice: "", vpElKey: "", vpOaKey: "test-key", vpSave: "" })
    .map(([id, value]) => [id, { value }]));
  const writes = [];
  let finishVoice;
  const saveCtx = {
    document: { getElementById: id => fields[id] }, provSel: { value: "openai" }, st: {},
    t: x => x, esc: x => x, window: { t: x => x }, OK_ICON: "", WARN_ICON: "", _settings: {},
    saveSetting: (section, data) => {
      writes.push([section, data]);
      return section === "voice" ? new Promise(resolve => { finishVoice = resolve; }) : Promise.resolve({ ok: true });
    },
  };
  vm.createContext(saveCtx);
  const saveStart = src.indexOf('      document.getElementById("vpSave").onclick =');
  vm.runInContext(src.slice(saveStart, src.indexOf("\n      };", saveStart) + 9), saveCtx);
  const saving = fields.vpSave.onclick();
  fields.vpOaKey.value = "";
  finishVoice({ ok: true });
  await saving;
  assert.equal(writes[1]?.[0], "model", "key was lost while saving");
  assert.equal(writes[1][1].openai_api_key, "test-key");
  console.log("OK - settings aliases, same-page tab navigation, and preserved controls");
})().catch(e => { console.error(e); process.exitCode = 1; });
