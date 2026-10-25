// Plugins page "Install from .zip" (owner request 2026-10-25), the dashboard half.
//
//     node tests/js/test_plugin_zip_ui.js
//
// What must hold:
//   1. `pluginZipView` (pure) draws only from the /plugins/inspect result: tools with their
//      min_mode (unknown -> readonly), the notes to show, the file overflow count.
//   2. Nothing is installed before the Install click, and the install sends the INSPECTED sha256.
//   3. Over an existing plugin, Install stays disabled until "Replace the installed version" is on,
//      and only then does the request carry `replace: true`.
//   4. A full store pack zip opens the PACK confirmation and installs through /packs/install.
//   5. A file that is not a .zip never reaches the server.
//
// Style: load the module and CALL it with a fake DOM, like test_cai_goi_di_kem.js.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : ""));
  if (!cond) fails.push(name);
}

function env() {
  const els = {};
  const box = {
    id: "packModal", className: "", onclick: null, _html: "",
    set innerHTML(v) { this._html = v; for (const k of Object.keys(els)) delete els[k]; },
    get innerHTML() { return this._html; },
    classList: { add() {}, remove() {}, contains: () => false },
    querySelectorAll: () => [], querySelector: () => null, addEventListener() {}, style: {},
  };
  function el(id) {
    const m = box._html.match(new RegExp('id="' + id + '"[^>]*aria-pressed="(\\w+)"'));
    return {
      id, onclick: null, onchange: null, textContent: "", files: null, _pressed: m ? m[1] : "false",
      disabled: new RegExp('id="' + id + '"[^>]*\\sdisabled[\\s>]').test(box._html),
      focus() {}, setAttribute(k, v) { if (k === "aria-pressed") this._pressed = v; },
      getAttribute(k) { return k === "aria-pressed" ? this._pressed : null; },
      classList: { add() {}, remove() {}, contains: () => false },
      querySelectorAll: () => [], addEventListener() {}, appendChild() {}, style: {},
    };
  }
  const doc = {
    getElementById(id) {
      if (id === "packModal") return box;
      if (!box._html.includes('id="' + id + '"')) return null;
      els[id] = els[id] || el(id);
      return els[id];
    },
    querySelector: () => null, querySelectorAll: () => [],
    createElement: () => ({ innerHTML: "", appendChild() {} }),
    body: { appendChild() {} },
  };
  return { doc, box };
}

const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8");
const SHA = "c".repeat(64);
const INSPECT = (extra) => Object.assign({
  ok: true, kind: "plugin", staging_id: SHA, sha256: SHA, filename: "demo.zip", size: 900,
  unpacked: 2048, slug: "zip-demo", name: "Zip demo", version: "1.2.0", author: "Test",
  description: "Echo tool.", tools: [{ name: "zip_demo_echo", min_mode: "safe" }], hooks: [],
  files: [{ path: "plugin.py", size: 100 }, { path: "plugin.yaml", size: 80 }], file_count: 2,
  py_files: ["plugin.py"], enabled_in_zip: true, existing: null, vault_shadow: false,
  user_gate: true, target: "/state/plugins/zip-demo",
}, extra || {});

function load(inspectResult) {
  const { doc, box } = env();
  const calls = [];
  const win = { ic: () => "", Alpine: { store: () => ({ go() {} }) } };
  const fakeFetch = (url, opt) => {
    let body = {};
    try { body = JSON.parse((opt && typeof opt.body === "string" && opt.body) || "{}"); } catch (e) { body = {}; }
    calls.push({ url, body });
    let r = { ok: true };
    if (url === "/plugins/inspect") r = inspectResult;
    else if (url === "/plugins/install") r = { ok: true, slug: "zip-demo", enabled: false, replaced: !!body.replace };
    else if (url === "/packs/install") r = { ok: true, id: "acme.pz" };
    return Promise.resolve({ json: () => Promise.resolve(r) });
  };
  const oldAlpine = globalThis.Alpine;
  globalThis.Alpine = win.Alpine;
  new Function("window", "document", "fetch", SRC)(win, doc, fakeFetch);
  globalThis.Alpine = oldAlpine;
  return { P: win.JavisPacks || {}, calls, box, doc };
}
const tick = () => new Promise(r => setTimeout(r, 0));

async function pick(t, name, opts) {
  let done = null;
  t.P.caiPluginZip(Object.assign({ brain: "brain-a", xong: (r) => { done = r; } }, opts || {}));
  const inp = t.doc.getElementById("pkTepHop");
  inp.files = [{ name: name }];
  inp.onchange();
  await tick(); await tick(); await tick();
  return () => done;
}

(async () => {
  // ---- 1. pure view ----
  const P0 = load(INSPECT()).P;
  check("packs.js exposes caiPluginZip + pluginZipView", typeof P0.caiPluginZip === "function" && typeof P0.pluginZipView === "function");
  const v = P0.pluginZipView(INSPECT({
    tools: [{ name: "a", min_mode: "full" }, { name: "b", min_mode: "weird" }],
    existing: { version: "1.0.0" }, vault_shadow: true, user_gate: false,
    files: Array.from({ length: 15 }, (_, i) => ({ path: "f" + i + ".py", size: 1 })), file_count: 15,
  }));
  check("view: tool min_mode kept, unknown becomes readonly",
    JSON.stringify(v.tools) === JSON.stringify([{ name: "a", mm: "full" }, { name: "b", mm: "readonly" }]), JSON.stringify(v.tools));
  check("view: notes off, exists, vault, gate", JSON.stringify(v.notes) === JSON.stringify(["off", "exists", "vault", "gate"]), JSON.stringify(v.notes));
  check("view: 12 files shown, 3 more", v.files.length === 12 && v.moreFiles === 3);
  check("view: replace needed over an existing plugin", v.needsReplace === true);
  check("view: plain plugin needs no replace, only the off note",
    P0.pluginZipView(INSPECT()).needsReplace === false && JSON.stringify(P0.pluginZipView(INSPECT()).notes) === '["off"]');

  // ---- 2. fresh install ----
  const a = load(INSPECT());
  const doneA = await pick(a, "demo.zip");
  check("inspect called with the brain", a.calls.some(c => c.url === "/plugins/inspect"));
  check("nothing installed before the click", !a.calls.some(c => c.url === "/plugins/install"));
  check("confirmation shows the red code warning", a.box.innerHTML.includes("pkm-canh do"));
  check("confirmation shows tool + min_mode", a.box.innerHTML.includes("zip_demo_echo") && a.box.innerHTML.includes("ghi (safe)"));
  check("confirmation shows the forced-off note", a.box.innerHTML.includes("enabled: true"));
  const btn = a.doc.getElementById("pzCai");
  check("install button enabled for a new plugin", btn && !btn.disabled);
  await btn.onclick(); await tick();
  const inst = a.calls.find(c => c.url === "/plugins/install");
  check("install sends the inspected sha256, no replace", inst && inst.body.consent_sha256 === SHA
    && inst.body.staging_id === SHA && inst.body.replace === false && inst.body.brain === "brain-a", JSON.stringify(inst && inst.body));
  check("page told about the install", doneA() && doneA().kind === "plugin" && doneA().slug === "zip-demo");

  // ---- 3. replace an existing plugin ----
  const b = load(INSPECT({ existing: { version: "1.0.0", enabled: true } }));
  await pick(b, "demo.zip");
  const bBtn = b.doc.getElementById("pzCai");
  check("over an existing plugin: install disabled", bBtn && bBtn.disabled === true);
  await bBtn.onclick(); await tick();
  check("disabled click sends nothing", !b.calls.some(c => c.url === "/plugins/install"));
  b.doc.getElementById("pzThay").onclick();
  check("replace toggle enables install", bBtn.disabled === false);
  await bBtn.onclick(); await tick();
  const binst = b.calls.find(c => c.url === "/plugins/install");
  check("install carries replace: true", binst && binst.body.replace === true, JSON.stringify(binst && binst.body));

  // ---- 4. full pack zip goes to the pack screen ----
  const c = load({ ok: true, kind: "pack", tier: "code", id: "acme.pz", name: { en: "Pz" }, staging_id: SHA,
                   sha256: SHA, py_files: ["plugins/pz/plugin.py"], plugins: ["pz"] });
  const doneC = await pick(c, "pack.zip");
  check("pack zip: pack confirmation drawn", c.box.innerHTML.includes('id="pkCai"') && !c.box.innerHTML.includes('id="pzCai"'));
  c.doc.getElementById("pkCai").onclick();
  await tick(); await tick();
  const pinst = c.calls.find(c2 => c2.url === "/packs/install");
  check("pack zip installs through /packs/install with the inspected sha", pinst && pinst.body.consent_sha256 === SHA);
  check("pack zip never posts /plugins/install", !c.calls.some(c2 => c2.url === "/plugins/install"));
  check("page told about the pack install", doneC() && doneC().kind === "pack");

  // ---- 5. not a zip ----
  const d = load(INSPECT());
  await pick(d, "plugin.tar.gz");
  check("non-zip never reaches the server", !d.calls.length);

  if (fails.length) {
    console.log("\nFAIL - test_plugin_zip_ui: " + fails.length);
    process.exit(1);
  }
  console.log("\nOK - test_plugin_zip_ui");
})();
