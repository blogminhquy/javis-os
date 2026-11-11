/* Pinned folders and folders open by default in the Vault tree (user request, 2026-11-11).
   The rules live in dashboard/vault-pins.js (pure, run here for real); console.js draws them.

       node tests/js/test_vault_pins.js
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const D = path.join(__dirname, "../../dashboard");
const read = (f) => fs.readFileSync(path.join(D, f), "utf8");
const P = require(path.join(D, "vault-pins.js"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  if (!cond) fails++;
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ---- paths: the tree speaks "relative to the browse ceiling", the lists speak "relative to the brain root" ----
const HOME = "home/me/brains/A";   // a localhost ceiling above the brain
check("a tree path inside the brain becomes a brain path", P.toBrain(HOME + "/wiki/concepts", HOME) === "wiki/concepts");
check("the brain root itself and a path outside the brain are not folders of the brain",
  P.toBrain(HOME, HOME) === null && P.toBrain("home/me/other", HOME) === null);
check("with the ceiling at the brain root the two are the same path",
  P.toBrain("wiki", "") === "wiki" && P.toTree("wiki", "") === "wiki" && P.toBrain("", "") === null);
check("a brain path goes back to the tree path", P.toTree("wiki/concepts", HOME) === HOME + "/wiki/concepts");

// ---- the lists ----
let prefs = P.clean({ pinned: ["wiki", "/wiki/", "a\\b", "", null], open: "x" });
check("clean keeps each folder once, POSIX style, and always answers both lists", same(prefs, { pinned: ["wiki", "a/b"], open: [] }), prefs);
const before = { pinned: ["wiki"], open: [] };
let next = P.toggled(before, "pinned", "projects/shop");
check("toggled adds a folder at the end of the list", same(next, { pinned: ["wiki", "projects/shop"], open: [] }), next);
check("toggled does not touch the lists it was given", same(before, { pinned: ["wiki"], open: [] }));
next = P.toggled(next, "pinned", "wiki");
check("toggled takes a folder out when it is already there", same(next.pinned, ["projects/shop"]), next);
next = P.toggled(next, "open", "wiki");
check("the two lists are independent: a folder can be open by default without being pinned",
  same(next, { pinned: ["projects/shop"], open: ["wiki"] }), next);

// ---- the root listing: pinned folders first ----
const ROOT = [{ name: "01 - Daily", type: "dir" }, { name: "projects", type: "dir" }, { name: "wiki", type: "dir" },
  { name: "wiki", type: "file", ext: "" }, { name: "README.md", type: "file", ext: ".md" }];
let parts = P.splitRoot(ROOT, { pinned: ["wiki", "projects/shop/docs"], open: [] }, HOME);
check("pinned folders come in the order they were pinned, each under the folder that holds it",
  same(parts.pinned.map((p) => [p.parent, p.item.name, p.item.type]),
    [[HOME, "wiki", "dir"], [HOME + "/projects/shop", "docs", "dir"]]), parts.pinned);
check("a folder pinned from the brain root is not listed a second time below",
  same(parts.rest.map((it) => it.type + ":" + it.name), ["dir:01 - Daily", "dir:projects", "file:wiki", "file:README.md"]), parts.rest);
parts = P.splitRoot(ROOT, { pinned: [], open: ["wiki"] }, "");
check("nothing pinned: the root is listed as it is", parts.pinned.length === 0 && parts.rest.length === ROOT.length);
parts = P.splitRoot(ROOT, { pinned: ["wiki"], open: [] }, "");
check("with the ceiling at the brain root a pinned root folder sits under \"\"", parts.pinned[0].parent === "", parts.pinned);

// ---- what to unfold ----
check("a folder shows by unfolding every folder above it, parents first",
  same(P.chain("projects/shop/docs", { pinned: [], open: [] }, HOME),
    [HOME + "/projects", HOME + "/projects/shop", HOME + "/projects/shop/docs"]));
check("the walk starts at the nearest pinned folder: its row is at the top, nothing above it has to unfold",
  same(P.chain("projects/shop/docs/api", { pinned: ["projects", "projects/shop"], open: [] }, HOME),
    [HOME + "/projects/shop", HOME + "/projects/shop/docs", HOME + "/projects/shop/docs/api"]));
let plan = P.openPlan({ pinned: ["wiki"], open: ["wiki", "projects/shop", "projects/blog"] }, HOME);
check("the open-by-default plan unfolds parents before children, each folder once",
  same(plan, [HOME + "/wiki", HOME + "/projects", HOME + "/projects/shop", HOME + "/projects/blog"]), plan);
check("nothing open by default: nothing to unfold", P.openPlan({ pinned: ["wiki"], open: [] }, HOME).length === 0);

// ---- load / save against a fake server ----
function makeEnv() {
  const env = { calls: [], reply: { ok: true, pinned: ["wiki"], open: [] }, status: 200, down: false };
  const win = {};
  const ctx = {
    window: win,
    FormData: function () { this.data = {}; this.append = (k, v) => { this.data[k] = v; }; },
    fetch: (url, opt) => {
      env.calls.push({ url, body: opt && opt.body && opt.body.data });
      if (env.down) return Promise.reject(new Error("offline"));
      return Promise.resolve({ ok: env.status === 200, json: () => Promise.resolve(env.reply) });
    },
    encodeURIComponent, JSON, Promise, Array, String,
  };
  vm.createContext(ctx);
  vm.runInContext(read("vault-pins.js"), ctx);
  env.api = win.JavisVaultPins;
  return env;
}

(async () => {
  let e = makeEnv();
  check("before anything is read the lists are empty", same(e.api.current("A"), { pinned: [], open: [] }));
  const both = await Promise.all([e.api.load("A"), e.api.load("A")]);
  check("two draws of the same tree share one read", e.calls.length === 1 && same(both[0], { pinned: ["wiki"], open: [] }), e.calls);
  check("the read names the brain", e.calls[0].url === "/files/tree-prefs?brain=A");
  await e.api.load("A");
  check("a later draw reuses what was read", e.calls.length === 1);
  e.reply = { ok: true, pinned: ["wiki", "notes"], open: ["wiki"] };
  await e.api.load("A", true);
  check("a forced read (Refresh, after a rename) asks the server again",
    e.calls.length === 2 && same(e.api.current("A"), { pinned: ["wiki", "notes"], open: ["wiki"] }));
  await e.api.load("B");
  check("each brain has its own lists", e.calls[2].url === "/files/tree-prefs?brain=B");

  e.reply = { ok: true, pinned: ["notes"], open: ["wiki"] };
  const saving = e.api.save("A", { pinned: ["notes"], open: ["wiki"] });
  check("save shows the new lists at once, before the server answers", same(e.api.current("A"), { pinned: ["notes"], open: ["wiki"] }));
  const sent = e.calls[e.calls.length - 1];
  check("save posts both lists as JSON for that brain", sent.url === "/files/tree-prefs"
    && same(sent.body, { brain: "A", pinned: '["notes"]', open: '["wiki"]' }), sent);
  check("save resolves true when the server took it", (await saving) === true);

  e.status = 500;
  let ok = await e.api.save("A", { pinned: [], open: [] });
  check("a refused save resolves false and the lists go back", ok === false && same(e.api.current("A"), { pinned: ["notes"], open: ["wiki"] }));
  e.down = true;
  ok = await e.api.save("A", { pinned: [], open: [] });
  check("a save while offline resolves false and the lists go back", ok === false && same(e.api.current("A"), { pinned: ["notes"], open: ["wiki"] }));
  const offline = await e.api.load("C");
  check("a failed read still answers empty lists so the tree draws", same(offline, { pinned: [], open: [] }));
  const known = await e.api.load("A", true);
  check("a failed forced read keeps what was known", same(known, { pinned: ["notes"], open: ["wiki"] }));

  // ---- how console.js uses it ----
  const con = read("console.js");
  const html = read("index.html");
  const at = html.indexOf("/static/vault-pins.js?v=");
  check("vault-pins.js loads on the page, before console.js", at > 0 && at < html.indexOf("/static/console.js?v="));
  const fn = (name) => { const m = con.match(new RegExp("  (?:async )?function " + name + "\\([^)]*\\) \\{[\\s\\S]*?\\n  \\}")); return m ? m[0] : ""; };
  const render = fn("renderVaultTree");
  check("the tree waits for the lists together with the root listing, not one after the other",
    /Promise\.all\(\[_vtList\(null\), pins\.load\(fbrain\(\), fresh\)\]\)/.test(render));
  check("a fresh draw (page load, Refresh, another brain) asks the server for the lists again, a redraw does not",
    /fresh = !\(opts && opts\.keepState\)/.test(render));
  check("pinned folders are drawn in their own zone above the rest",
    /pins\.splitRoot\(items, prefs, home\)/.test(render) && /className = "vt-pins"/.test(render)
    && render.indexOf("parts.pinned.forEach") < render.indexOf("parts.rest.forEach"));
  check("a fresh draw unfolds the folders open by default, a redraw after an edit does not",
    /if \(fresh\) await _vtOpenPaths\(pins\.openPlan\(prefs, home\)\)/.test(render));
  const rebuild = fn("_vtRebuildReExpand");
  check("a redraw keeps exactly what was open (so a folder just closed by hand stays closed)",
    /await renderVaultTree\(\{ keepState: !fresh \}\)/.test(rebuild) && /const fresh = !tree\.querySelector\("\.vt-node"\)/.test(rebuild));
  check("a redraw remembers which copy of a pinned folder was open (top zone or its usual place)",
    /want\(node\.dataset\.rel, !!node\.closest\("\.vt-pins"\)\)/.test(rebuild));
  check("pinning redraws from the listings already loaded, without asking the server for every open folder",
    /if \(!keepCache\) \{ _vtCache\.clear\(\); _vtIndex = null; \}/.test(rebuild)
    && /await _vtRebuildReExpand\(field === "open" && turnedOn \? rel : null, true\)/.test(fn("_vtTogglePref")));
  const row = fn("_vtRowEl");
  check("only a folder of the brain gets the pin button", /brainPath \? `<button data-a="pin"/.test(row)
    && /const brainPath = isDir \? pins\.toBrain\(rel, _vtHome \|\| ""\) : null/.test(row));
  check("the pin button opens the menu", /else if \(a === "pin"\) _vtPinMenu\(b, rel\)/.test(row));
  const menu = fn("_vtPinMenu");
  check("the menu offers both switches, worded by their current state",
    /pinned \? "cs\.vt_unpin" : "cs\.vt_pin"/.test(menu) && /keptOpen \? "cs\.vt_open_off" : "cs\.vt_open_on"/.test(menu));
  const toggle = fn("_vtTogglePref");
  check("a save that fails says so and redraws the lists the server has",
    /if \(!\(await saving\)\) \{\s*alert\(window\.t\("app\.err_net"\)\);\s*await _vtRebuildReExpand\(null, true\);/.test(toggle));
  check("rename and delete read the lists again: the server moved or dropped the entries",
    /await _vtReloadPins\(\);\s*await _vtRebuildReExpand\(null\);/.test(fn("_vtRename"))
    && /await _vtReloadPins\(\);\s*await _vtRebuildReExpand\(null\);/.test(fn("_vtDelete")));

  const vi = JSON.parse(read("i18n/vi.json")), en = JSON.parse(read("i18n/en.json"));
  const keys = ["cs.vt_pin_title", "cs.vt_pin", "cs.vt_unpin", "cs.vt_open_on", "cs.vt_open_off", "cs.vt_pinned"];
  check("every label exists in Vietnamese and in English", keys.every((k) => vi[k] && en[k] && vi[k] !== en[k]),
    keys.filter((k) => !vi[k] || !en[k]));
  const css = read("style.css");
  check("the pinned zone, the lit button and the mark are styled", /\.vt-pins \{/.test(css) && /\.vt-act button\.on \{/.test(css) && /\.vt-pinmark \{/.test(css));

  if (fails) { console.log("\nFAIL - test_vault_pins: " + fails); process.exit(1); }
  console.log("\nOK - test_vault_pins");
})().catch((err) => { console.error(err); process.exit(1); });
