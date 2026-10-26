/* Pinned folder flow, run against the REAL composer-folder.js with a small fake DOM (0.159.0).
   Covers what source canaries could not: held pin, claim, brain switch, in-brain tooltip,
   failed claim, extra folders and the panel rows.

       node tests/js/test_pinned_folder_flow.js
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const SRC = fs.readFileSync(path.join(__dirname, "../../dashboard/composer-folder.js"), "utf8");
let fails = [];
function check(name, cond, extra) { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  " + extra : "")); if (!cond) fails.push(name); }

function makeEnv() {
  const elems = {};
  function el(id) {
    const e = {
      id: id || "", children: [], attrs: {}, innerHTML: "", title: "", parentElement: null,
      classList: { set: new Set(), toggle(c, on) { on ? this.set.add(c) : this.set.delete(c); }, contains(c) { return this.set.has(c); } },
      setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
      addEventListener() {},
      remove() {
        if (this.parentElement) { const a = this.parentElement.children; a.splice(a.indexOf(this), 1); this.parentElement = null; }
        delete elems[this.id];
      },
      insertBefore(node, ref) {
        if (node.parentElement) node.remove();
        const a = this.children, i = ref ? a.indexOf(ref) : -1;
        if (i >= 0) a.splice(i, 0, node); else a.push(node);
        node.parentElement = this; elems[node.id] = node;
      },
      get previousElementSibling() { const a = this.parentElement ? this.parentElement.children : []; return a[a.indexOf(this) - 1] || null; },
      get nextSibling() { const a = this.parentElement ? this.parentElement.children : []; return a[a.indexOf(this) + 1] || null; },
    };
    if (id) elems[id] = e;
    return e;
  }
  const host = el("cpChips");
  host.insertBefore(el("limitBtn"), null);
  const env = { brain: "D:/brains/A", sid: "", calls: [], replies: {}, notes: [], events: [], registered: null };
  const win = {
    t: (k, v) => k + (v ? JSON.stringify(v) : ""),
    JavisSessions: { brain: () => env.brain, current: () => env.sid },
    JavisComposerMenu: { register(it) { env.registered = it; }, openItem() {}, icon: { folder: "<svg></svg>" } },
    JavisAttach: { note(s) { env.notes.push(s); } },
    matchMedia: () => ({ matches: false }),
    addEventListener() {},
    dispatchEvent(e) { env.events.push(e); },
  };
  const ctx = {
    window: win,
    document: { readyState: "complete", getElementById: (id) => elems[id] || null, createElement: () => el("") },
    CustomEvent: function (type, o) { this.type = type; this.detail = o && o.detail; },
    FormData: function () { this.data = {}; this.append = (k, v) => { this.data[k] = v; }; },
    fetch: (url, opt) => {
      env.calls.push({ url, body: opt && opt.body && opt.body.data });
      const key = Object.keys(env.replies).find((k) => url.indexOf(k) !== -1);
      const body = key ? env.replies[key] : { ok: true, folder: null };
      return Promise.resolve({ json: () => Promise.resolve(body) });
    },
    setTimeout, clearTimeout, console,
  };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  env.api = win.JavisPinnedFolder;
  env.chip = () => elems.pinChip || null;
  return env;
}
const tick = () => new Promise((r) => setTimeout(r, 0));

(async () => {
  // 1. Pin on an empty chat: held, chip shows, nothing sent yet.
  let e = makeEnv();
  await e.api.pin("projects/shop");
  check("pin on an empty chat is held: chip shows, no request sent", e.chip() && /shop/.test(e.chip().innerHTML) && e.calls.length === 0);
  check("claimPending without a session id returns null and keeps the pin", e.api.claimPending(null) === null && e.calls.length === 0);
  e.replies["/pin"] = { ok: true, folder: { id: "1", name: "shop", path: "D:/brains/A/projects/shop", exists: true }, in_brain: true, extra_folders: [] };
  const w = e.api.claimPending("s1");
  check("claimPending with the new session id returns a promise the first send can wait for", w && typeof w.then === "function");
  await w;
  check("the claim posts the held path to that session", e.calls.length === 1 && /\/coding\/session\/s1\/pin/.test(e.calls[0].url) && e.calls[0].body.path === "projects/shop");
  check("nothing held any more: the next claim returns null (no delay)", e.api.claimPending("s2") === null);

  // 2. A held pin does not follow a brain switch.
  e = makeEnv();
  await e.api.pin("projects/shop");
  e.brain = "D:/brains/B";
  check("after a brain switch the held pin is dropped instead of binding in the other brain",
    e.api.claimPending("s1") === null && e.calls.length === 0);
  await e.api.refresh();
  check("and the chip is cleared on the next refresh", !e.chip());

  // 3. In-brain tooltip for an absolute folder inside the brain.
  e = makeEnv();
  await e.api.pin("D:/brains/A/projects/site");
  check("an absolute folder inside the brain is not labelled 'outside the brain'", e.chip() && e.chip().title.indexOf("cp.pin_outside") === -1, e.chip() && e.chip().title);
  await e.api.pin("E:/elsewhere/repo");
  check("a folder outside the brain says only CLI brains can work there", e.chip().title.indexOf("cp.pin_outside") !== -1);

  // 4. Failed claim: chip cleared, reason shown in the composer.
  e = makeEnv();
  await e.api.pin("projects/gone");
  e.replies["/pin"] = { ok: false, error: "Folder does not exist" };
  await e.api.claimPending("s1");
  check("a failed claim clears the chip and shows the server's reason", !e.chip() && e.notes.indexOf("Folder does not exist") !== -1, JSON.stringify(e.notes));

  // 5. Extra folders bound before 0.158.0 show as +N with their names in the tooltip.
  e = makeEnv();
  e.sid = "s9";
  e.replies["/coding/session/s9"] = { folder: { id: "1", name: "app", path: "D:/x/app", exists: true }, in_brain: false, extra_folders: ["lib", "docs"] };
  await e.api.refresh();
  check("extra folders show as +N on the chip", e.chip() && /\+2/.test(e.chip().innerHTML), e.chip() && e.chip().innerHTML);
  check("the tooltip names the extra folders", e.chip().title.indexOf("lib") !== -1 && e.chip().title.indexOf("docs") !== -1, e.chip().title);

  // 6. Panel: the current folder is its own row, separate from Unpin; search asks for folders only.
  const box = { innerHTML: "", addEventListener() {}, querySelector: (s) => (s === ".cp-search" ? { value: "", focus() {}, addEventListener() {} } : { innerHTML: "", textContent: "" }) };
  e.registered.panel(box, { close() {} });
  check("panel shows the current folder as its own row", /class="cp-mi cp-pin-current"[^>]*>[\s\S]*app/.test(box.innerHTML), box.innerHTML.slice(0, 300));
  check("panel keeps Unpin as a separate button", /<button type="button" class="cp-mi" data-unpin="1">/.test(box.innerHTML));
  check("folder search asks the server for folders only", SRC.indexOf("only_dirs=true") !== -1 && SRC.indexOf("include_dirs=true") === -1);

  if (fails.length) { console.log("\nFAIL - test_pinned_folder_flow: " + fails.length); process.exit(1); }
  console.log("\nOK - test_pinned_folder_flow: all pass");
})().catch((err) => { console.error(err); process.exit(1); });
