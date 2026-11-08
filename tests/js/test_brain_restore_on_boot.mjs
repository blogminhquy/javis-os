// The dashboard starts on the brain the owner picked, even when the brain list cannot be loaded at once.
//
// User report 08/11/2026: create team A, update Javis, team A is gone from the Teams page (Javis Core still knows it);
// create team B, update again, team B is gone and team A is back. The page had opened while the server restarted
// after the update: app.js could not select the saved brain (its option only comes with GET /brains), fell back to
// Brain Default, and brains-ui.js never retried the failed /brains, so the whole visit (Teams page included) ran on
// the other brain and team B was created there.
//
// Run: node tests/js/test_brain_restore_on_boot.mjs
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const read = (f) => fs.readFileSync(path.join(__dirname, "../../dashboard", f), "utf8");
const BRAINS_UI = read("brains-ui.js");
const APP = read("app.js");
const TEAMS = read("teams.js");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };
const realTimeout = setTimeout;
const settle = (ms = 30) => new Promise((r) => realTimeout(r, ms));

// ---- Minimal DOM: <select> with options and an optional optgroup ----
class Opt {
  constructor(value = "", text = "") { this.value = value; this.textContent = text; this.dataset = {}; this._parent = null; }
  remove() { const a = this._parent?._kids; if (a) { const i = a.indexOf(this); if (i >= 0) a.splice(i, 1); } this._parent = null; }
}
class Frag { constructor() { this._kids = []; } appendChild(o) { this._kids.push(o); return o; } }
class Select {
  constructor() { this._kids = []; this._value = "brain"; this.changes = []; }
  _match(o, sel) {
    if (sel === "option[data-brain]") return o.dataset.brain !== undefined;
    if (sel === "option[data-custom]") return o.dataset.custom !== undefined;
    if (sel === 'option[value="brain"]') return o.value === "brain";
    if (sel === "optgroup") return false;
    throw new Error("selector not mocked: " + sel);
  }
  querySelectorAll(sel) { return this._kids.filter((o) => this._match(o, sel)); }
  querySelector(sel) { return this._kids.find((o) => this._match(o, sel)) || null; }
  appendChild(node) {
    const kids = node instanceof Frag ? node._kids : [node];
    for (const k of kids) { k._parent = this; this._kids.push(k); }
    if (node instanceof Frag) node._kids = [];
    return node;
  }
  insertBefore(node, ref) {
    const kids = node instanceof Frag ? node._kids : [node];
    let idx = ref ? this._kids.indexOf(ref) : -1;
    if (idx < 0) idx = this._kids.length;
    for (const k of kids) k._parent = this;
    this._kids.splice(idx, 0, ...kids);
    if (node instanceof Frag) node._kids = [];
    return node;
  }
  get options() { return this._kids; }
  get selectedIndex() { return this._kids.findIndex((o) => o.value === this._value); }
  get value() { return this._value; }
  set value(v) { this._value = v; }
  dispatchEvent(e) { this.changes.push(this._value); return true; }
}

const DIR = "/brains";
const REAL = [
  { name: "Brain Default", path: DIR + "/Brain Default", notes: 3, is_default: true },
  { name: "Shop", path: DIR + "/Shop", notes: 40 },
];

function restoreGraphSourceSource() {
  const start = APP.indexOf("(function restoreGraphSource() {");
  if (start < 0) throw new Error("restoreGraphSource not found in app.js");
  const end = APP.indexOf("})();", start);
  return APP.slice(start, end + 5);
}

// Runs app.js's startup restore of the brain picker against `store`, like a fresh page load.
function bootApp(store) {
  const sel = new Select();
  sel.appendChild(new Opt("brain", "Brain Default"));
  const ctx = {
    graphSource: sel,
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
    document: { createElement: () => new Opt() },
    _lastBrain: "brain",
  };
  ctx.currentBrainPath = () => (sel.value.startsWith("path:") ? sel.value.slice(5) : "brain");
  vm.createContext(ctx);
  vm.runInContext(restoreGraphSourceSource(), ctx);
  return { sel, ctx };
}

// Loads brains-ui.js on `sel` with `fetchBrains` answering GET /brains. Retries run at once (no real 2-30 s waits).
function bootBrainsUi(sel, store, fetchBrains) {
  global.document = {
    getElementById: (id) => (id === "graphSource" ? sel : { addEventListener() {} }),
    createElement: () => new Opt(),
    createDocumentFragment: () => new Frag(),
  };
  global.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
  global.window = {};
  global.Event = class { constructor(t) { this.type = t; } };
  global.setTimeout = (fn) => realTimeout(fn, 1);
  global.clearTimeout = (t) => clearTimeout(t);
  global.fetch = async (url) => {
    if (url === "/brains") return fetchBrains();
    throw new Error("fetch not mocked: " + url);
  };
  eval(BRAINS_UI);
}

const ok = (brains) => ({ ok: true, status: 200, json: async () => ({ brains }) });
const badGateway = () => ({ ok: false, status: 502, json: async () => { throw new SyntaxError("HTML error page"); } });

// ---- 1. app.js selects the saved brain at once, before /brains answers ----
{
  const store = { "javis.graphSource": "path:" + DIR + "/Shop" };
  const { sel, ctx } = bootApp(store);
  const pending = sel.options.find((o) => o.dataset.pending);
  check("app.js: the saved brain is selected at startup, not Brain Default", sel.value === "path:" + DIR + "/Shop");
  check("app.js: under a provisional option named after its folder",
    !!pending && pending.dataset.brain === "1" && pending.textContent === "Shop" && pending.dataset.brainName === "Shop");
  check("app.js: the chat starts from the brain really in use", ctx._lastBrain === DIR + "/Shop");
  check("app.js: nothing is written back to the saved choice", store["javis.graphSource"] === "path:" + DIR + "/Shop");
}
{
  const { sel, ctx } = bootApp({ "javis.graphSource": "brain" });
  check("app.js: a saved Brain Default stays Brain Default, no extra option",
    sel.value === "brain" && sel.options.length === 1 && ctx._lastBrain === "brain");
}
{
  const { sel } = bootApp({});
  check("app.js: nothing saved means Brain Default", sel.value === "brain" && sel.options.length === 1);
}

// ---- 2. /brains fails while the server restarts, then answers: the saved brain is kept the whole time ----
{
  const store = { "javis.graphSource": "path:" + DIR + "/Shop" };
  const { sel } = bootApp(store);
  let calls = 0;
  bootBrainsUi(sel, store, async () => {
    calls += 1;
    if (calls === 1) return badGateway();
    if (calls === 2) throw new TypeError("Failed to fetch");
    return ok(REAL);
  });
  await settle(5);
  check("brains-ui: the brain stays the saved one while /brains fails", sel.value === "path:" + DIR + "/Shop");
  await settle(60);
  const real = sel.options.find((o) => o.value === "path:" + DIR + "/Shop");
  check("brains-ui: a failed first load is tried again until the list arrives", calls === 3);
  check("brains-ui: the provisional option is replaced by the real one",
    !sel.options.some((o) => o.dataset.pending) && !!real && real.textContent.includes("40"));
  check("brains-ui: the saved brain is still selected", sel.value === "path:" + DIR + "/Shop");
  check("brains-ui: no brain switch is announced (same brain, no page redraw)", sel.changes.length === 0);
  check("brains-ui: the saved choice is untouched", store["javis.graphSource"] === "path:" + DIR + "/Shop");
}

// ---- 3. The saved brain no longer exists: Brain Default, announced once ----
{
  const store = { "javis.graphSource": "path:" + DIR + "/Deleted" };
  const { sel } = bootApp(store);
  bootBrainsUi(sel, store, async () => ok(REAL));
  await settle(40);
  check("brains-ui: a saved brain that is gone falls back to Brain Default", sel.value === "brain");
  check("brains-ui: every page is told (one change event)", sel.changes.length === 1 && sel.changes[0] === "brain");
  check("brains-ui: the stale choice is forgotten", store["javis.graphSource"] === "brain");
  check("brains-ui: no provisional option is left", !sel.options.some((o) => o.dataset.pending));
}

// ---- 4. A later redraw of the list (rename, reload) is not a brain switch ----
{
  const store = { "javis.graphSource": "path:" + DIR + "/Shop" };
  const { sel } = bootApp(store);
  bootBrainsUi(sel, store, async () => ok(REAL));
  await settle(40);
  sel.changes.length = 0;
  await global.window.JavisBrains.reload();
  check("brains-ui: reloading the list keeps the selection and fires nothing",
    sel.value === "path:" + DIR + "/Shop" && sel.changes.length === 0);
}

// ---- 5. Teams page: a late list for an earlier draw or another brain is dropped ----
{
  const start = TEAMS.indexOf("function loadTeams(append) {");
  const body = TEAMS.slice(start, TEAMS.indexOf("\n  }\n", start));
  check("teams.js: loadTeams remembers which draw and brain asked", body.includes("var mine = S, forBrain = brain();"));
  check("teams.js: loadTeams ignores an answer for another draw or brain",
    body.includes("if (S !== mine || brain() !== forBrain) return;") &&
    body.indexOf("if (S !== mine || brain() !== forBrain) return;") < body.indexOf("S.teams ="));
}

global.setTimeout = realTimeout;
console.log();
if (fails.length) { console.log(`${fails.length} FAIL: ${fails.join(", ")}`); process.exit(1); }
console.log("ALL PASS");
