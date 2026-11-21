/* The repo chip and the repo list, run against the REAL github-connect.js with a small fake page (21/11/2026).

       node tests/js/test_github_repo_picker.js

Owner, 21/11/2026, on a user's report ("đổi về Brain của anh cứ lâu lâu lại nhảy qua Javis OS"): "cho anh nút x rõ ràng
khi ghim ở khung chat cũng như ở trên mục lựa chọn, tìm xem khi thao tác có dễ bị chọn nhầm không".

What went wrong before: every tick sent the chat's WHOLE repo list. A repo holding unsaved work could not come off, the
server refused the request as a whole, and the picker put every tick back, the repo just added included. Nothing on
screen let the person remove that repo anyway. Covered here:
  1. A tap adds ONE repo (`add=`), an X removes ONE (`/detach`); the whole list is never sent again.
  2. A refused removal keeps the repo that was just added, and asks on that row: keep it, or remove it anyway (force).
  3. A chosen row does nothing when tapped: only its X removes it.
  4. The chip under the composer has an X; on a repo with unsaved work it opens the list on that question.
  5. An empty chat holds its picks until the first message.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "../..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard/github-connect.js"), "utf8");
const gh = require(path.join(ROOT, "dashboard/github-connect.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/en.json"), "utf8"));
const fails = [];
function check(name, cond, extra) { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  " + extra : "")); if (!cond) fails.push(name); }
const tick = () => new Promise((r) => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 12; i++) await tick(); };

// ---- pure helpers ----
check("unsaved edits: the question says they are deleted, the button says so too",
  gh.askSpec({ risk: "dirty" }).text === "gh.ask_dirty" && gh.askSpec({ risk: "dirty" }).go === "gh.ask_drop");
check("unpushed commits: another question, with their count",
  gh.askSpec({ risk: "unpushed", count: 3 }).text === "gh.ask_unpushed" && gh.askSpec({ risk: "unpushed", count: 3 }).n === 3
  && gh.askSpec({ risk: "unpushed" }).go === "gh.ask_go");
check("the chip's X names one repo, or counts several",
  gh.removeLabel(["a/x"]).key === "gh.remove_chat" && gh.removeLabel(["a/x"]).vars.name === "a/x"
  && gh.removeLabel(["a/x", "a/y"]).key === "gh.remove_all" && gh.removeLabel(["a/x", "a/y"]).vars.n === 2);
["gh.remove_one", "gh.remove_chat", "gh.remove_all", "gh.add_one", "gh.adding", "gh.removing", "gh.ask_dirty", "gh.ask_unpushed",
  "gh.ask_keep", "gh.ask_drop", "gh.ask_go"].forEach((k) => {
  check("text " + k + " in vi and en, short enough to stand outside an (i)", !!vi[k] && !!en[k] && vi[k].length <= 100 && en[k].length <= 100);
});

// ---- a fake page around the real script ----
function makeEnv(o) {
  o = o || {};
  const elems = {};
  function el(id) {
    const e = {
      id: id || "", children: [], attrs: {}, innerHTML: "", title: "", className: "", parentElement: null, handlers: {},
      classList: { set: new Set(), add(c) { this.set.add(c); }, remove(c) { this.set.delete(c); },
        toggle(c, on) { on ? this.set.add(c) : this.set.delete(c); }, contains(c) { return this.set.has(c); } },
      setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
      addEventListener(t, fn) { this.handlers[t] = fn; },
      remove() {
        if (this.parentElement) { const a = this.parentElement.children; a.splice(a.indexOf(this), 1); this.parentElement = null; }
        delete elems[this.id];
      },
      appendChild(node) {
        if (node.parentElement) node.remove();
        this.children.push(node); node.parentElement = this; elems[node.id] = node;
      },
      get nextElementSibling() { const a = this.parentElement ? this.parentElement.children : []; return a[a.indexOf(this) + 1] || null; },
    };
    if (id) elems[id] = e;
    return e;
  }
  const host = el("cpCtx");
  host.hidden = true;
  // The fake server: which repos the chat has, and which of them hold unsaved work.
  const env = { sid: o.sid || "", attached: (o.attached || []).slice(), dirty: o.dirty || {}, calls: [], opened: [], notes: [], host };
  const view = () => ({ ok: true, repos: env.attached.map((n) => ({ full_name: n, default_branch: "main", base_branch: "main" })), icon: null });
  const win = {
    t: (k, v) => k + (v ? JSON.stringify(v) : ""),
    JavisSessions: { brain: () => "brain", current: () => env.sid },
    JavisComposerMenu: { register(it) { env.item = it; }, openItem(id) { env.opened.push(id); } },
    JavisAttach: { note(s) { env.notes.push(s); } },
    matchMedia: () => ({ matches: false }),
    addEventListener() {}, dispatchEvent() {},
  };
  const ctx = {
    window: win,
    document: { readyState: "complete", hidden: false, getElementById: (id) => elems[id] || null, createElement: () => el(""),
      addEventListener() {}, removeEventListener() {} },
    CustomEvent: function (type, d) { this.type = type; this.detail = d && d.detail; },
    FormData: function () { this.data = {}; this.append = (k, v) => { this.data[k] = v; }; },
    fetch: (url, opt) => {
      const body = (opt && opt.body && opt.body.data) || null;
      env.calls.push({ url, body });
      let out = { ok: true };
      if (/\/github\/status/.test(url)) out = { ok: true, connected: true, source: "token" };
      else if (/\/github\/repos\?/.test(url)) out = { ok: true, items: (o.remote || []).map((n) => ({ full_name: n, cloned: true })) };
      else if (/\/detach$/.test(url)) {
        if (env.dirty[body.full_name] && body.force !== "1") {
          out = { ok: false, error: "refused", code: "work_at_risk", full_name: body.full_name, risk: env.dirty[body.full_name], count: 2 };
        } else { env.attached = env.attached.filter((x) => x !== body.full_name); out = { ok: true, detached: true }; }
      } else if (/\/repos$/.test(url)) {
        if (body.add) { if (env.attached.indexOf(body.add) < 0) env.attached.push(body.add); }
        else env.attached = String(body.repos || "").split(",").filter(Boolean);
        out = view();
      } else if (/\/github\/session\//.test(url)) out = view();
      return Promise.resolve({ json: () => Promise.resolve(out) });
    },
    setTimeout, clearTimeout, setInterval() {}, console,
  };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  env.api = win.JavisGithubRepos;
  env.chip = () => elems.ghChip || null;
  env.chipHtml = () => (elems.ghChip ? elems.ghChip.innerHTML.replace(/&quot;/g, '"') : "");
  // A box as the + menu hands one to the panel; `click(attr, i)` is a tap on the element carrying that attribute.
  env.openPanel = () => {
    const parts = {
      ".cp-search": { value: "", focused: false, focus() { this.focused = true; }, addEventListener() {} },
      ".cp-results": { innerHTML: "", handlers: {}, addEventListener(t, fn) { this.handlers[t] = fn; } },
      ".cp-pin-err": { textContent: "" },
    };
    const stubs = {};
    const box = { innerHTML: "", isConnected: true, parentElement: null, addEventListener() {},
      querySelector(sel) { return parts[sel] || (stubs[sel] = stubs[sel] || { focus() {} }); } };
    env.item.panel(box, { close() {}, back() { env.wentBack = true; }, brain: () => "brain" });
    return {
      box, out: parts[".cp-results"], err: parts[".cp-pin-err"], search: parts[".cp-search"], stubs,
      click(attr, i) {
        parts[".cp-results"].handlers.click({ target: { closest: (sel) => (sel === "[" + attr + "]" ? { getAttribute: () => String(i) } : null) } });
      },
    };
  };
  env.clickChip = (cls) => env.chip().handlers.click({ stopPropagation() {}, target: { closest: (sel) => (sel === cls ? {} : null) } });
  env.posts = () => env.calls.filter((c) => c.body);
  return env;
}

(async () => {
  // ---- 1 and 2. The swap that "jumped back": add the brain repo, then take javis-os off while it holds unsaved work.
  let e = makeEnv({ sid: "s1", attached: ["blog/javis-os"], dirty: { "blog/javis-os": "dirty" }, remote: ["blog/javis-os", "loc/brain"] });
  await settle();
  check("an open chat with a repo shows the chip with an X", e.chip() && /class="cp-pin-open"/.test(e.chip().innerHTML) && /class="cp-pin-x"/.test(e.chip().innerHTML), e.chip() && e.chip().innerHTML.slice(0, 200));
  check("the chip is a group, not a button holding buttons", !!e.chip() && e.chip().type === undefined);
  check("the X says what it removes", /gh\.remove_chat\{"name":"blog\/javis-os"\}/.test(e.chipHtml()));

  let p = e.openPanel();
  await settle();
  // Repos are attached, so the panel opens on the short menu; "Change repo" leads to the list.
  check("with repos attached the panel opens on the short menu", /data-gh-go="repos"/.test(p.box.innerHTML));
  p.stubs['[data-gh-go="repos"]'].onclick();
  await settle();
  check("a chosen repo is a plain row with an X, not a button that toggles",
    /<div class="gh-sel"><div class="cp-mi gh-repo gh-on">/.test(p.out.innerHTML) && /class="gh-row-x" data-gh-x="0"/.test(p.out.innerHTML), p.out.innerHTML.slice(0, 300));
  check("any other repo is one tap to add, marked with a +", /<button type="button" class="cp-mi gh-repo" data-gh-i="1"/.test(p.out.innerHTML) && /class="gh-add"/.test(p.out.innerHTML));
  check("the old tick is gone from the repo list", !/gh-tick/.test(p.out.innerHTML) && !/aria-selected/.test(p.out.innerHTML));

  // 3. A tap on the chosen row itself (not on its X) changes nothing.
  const before = e.posts().length;
  p.click("data-nothing", 0);
  await settle();
  check("a tap on a chosen row does nothing: only its X removes it", e.posts().length === before && e.attached.join() === "blog/javis-os");

  p.click("data-gh-i", 1);
  await settle();
  const addCall = e.posts().slice(-1)[0];
  check("a tap adds ONE repo: the request names it and leaves the rest alone",
    /\/github\/session\/s1\/repos$/.test(addCall.url) && addCall.body.add === "loc/brain" && addCall.body.repos === undefined, JSON.stringify(addCall));
  check("both repos are on the chat now", e.attached.join() === "blog/javis-os,loc/brain" && (p.out.innerHTML.match(/class="gh-row-x"/g) || []).length === 2);

  p.click("data-gh-x", 0);
  await settle();
  const rm = e.posts().slice(-1)[0];
  check("the X removes ONE repo through /detach, without force", /\/github\/session\/s1\/detach$/.test(rm.url) && rm.body.full_name === "blog/javis-os" && rm.body.force === "", JSON.stringify(rm));
  check("a refused removal keeps the repo that was just added (no more jumping back)", e.attached.join() === "blog/javis-os,loc/brain"
    && /loc<\/span>|loc ·/.test(p.out.innerHTML) && (p.out.innerHTML.match(/class="gh-row-x"/g) || []).length === 2);
  check("the row asks: keep it, or remove it and delete the changes",
    /class="gh-sel is-asking"/.test(p.out.innerHTML) && /gh\.ask_dirty/.test(p.out.innerHTML) && /data-gh-keep="1"/.test(p.out.innerHTML)
    && /data-gh-force="0"[^>]*>gh\.ask_drop/.test(p.out.innerHTML), p.out.innerHTML.slice(0, 600));
  check("no raw server sentence or path under the list", p.err.textContent === "");
  check("the whole list is never sent", !e.posts().some((c) => c.body.repos !== undefined));

  p.click("data-gh-keep", 1);
  await settle();
  check("Keep it closes the question and changes nothing", !/gh-ask/.test(p.out.innerHTML) && e.attached.length === 2);

  p.click("data-gh-x", 0);
  await settle();
  p.click("data-gh-force", 0);
  await settle();
  const forced = e.posts().slice(-1)[0];
  check("Remove anyway sends force", /\/detach$/.test(forced.url) && forced.body.force === "1" && forced.body.full_name === "blog/javis-os");
  check("the chat ends on the brain repo alone", e.attached.join() === "loc/brain" && /gh\.remove_chat\{"name":"loc\/brain"\}/.test(e.chipHtml()));

  // ---- 4. The chip's own X.
  e = makeEnv({ sid: "s2", attached: ["a/clean"], remote: ["a/clean"] });
  await settle();
  e.clickChip(".cp-pin-x");
  await settle();
  check("the chip's X takes a clean repo off in one tap, and the chip goes", e.attached.length === 0 && !e.chip() && e.host.hidden === true);
  check("it does not open the panel for that", e.opened.length === 0);

  e = makeEnv({ sid: "s3", attached: ["a/clean", "blog/javis-os"], dirty: { "blog/javis-os": "unpushed" }, remote: ["a/clean", "blog/javis-os"] });
  await settle();
  check("several repos: the X counts them", /gh\.remove_all\{"n":2\}/.test(e.chipHtml()));
  e.clickChip(".cp-pin-x");
  await settle();
  check("the chip's X on a repo with unsaved work keeps it and opens the picker", e.attached.join() === "blog/javis-os" && e.opened.join() === "github");
  p = e.openPanel();
  await settle();
  check("the picker opens straight on the list, on that repo's question, without raising the keyboard",
    /class="gh-sel is-asking"/.test(p.out.innerHTML) && /gh\.ask_unpushed\{&quot;n&quot;:2\}/.test(p.out.innerHTML) && /gh\.ask_go/.test(p.out.innerHTML)
    && p.search.focused === false, p.out.innerHTML.slice(0, 400));
  const p2 = e.openPanel();
  await settle();
  check("the question is asked once: the next opening is the short menu again", /data-gh-go="repos"/.test(p2.box.innerHTML));

  e.clickChip(".cp-pin-open");
  check("the name of the chip opens the panel", e.opened.slice(-1)[0] === "github");

  // ---- 5. An empty chat: picks are held, nothing is sent.
  e = makeEnv({ sid: "", remote: ["a/x", "a/y"] });
  await settle();
  p = e.openPanel();
  await settle();
  check("no repo yet: the panel opens on the list", /data-gh-i="0"/.test(p.out.innerHTML) && p.search.focused === true);
  p.click("data-gh-i", 0);
  await settle();
  p.click("data-gh-i", 1);
  await settle();
  check("picks on an empty chat are held: chip shows, no request sent", e.posts().length === 0 && /x \+1/.test(e.chip().innerHTML), e.chip() && e.chip().innerHTML.slice(0, 200));
  p.click("data-gh-x", 0);
  await settle();
  check("an X on an empty chat drops the held pick", e.posts().length === 0 && /<span>y<\/span>/.test(e.chip().innerHTML));
  e.sid = "new1";
  await e.api.claimPending("new1");
  await settle();
  const claim = e.posts()[0];
  check("the first message attaches what was held", /\/github\/session\/new1\/repos$/.test(claim.url) && claim.body.repos === "a/y" && e.attached.join() === "a/y");

  // ---- source canaries for what a fake page cannot show ----
  const css = fs.readFileSync(path.join(ROOT, "dashboard/style.css"), "utf8");
  check("the row X is a bordered round button, 44px on a touch screen",
    /\.gh-row-x \{[^}]*border: 1px solid var\(--border\)/.test(css) && css.includes("@media (pointer: coarse) { .gh-row-x, .gh-add { width: 44px; height: 44px; } }"));
  check("the question's buttons are 44px tall", /\.gh-ask-keep, \.gh-ask-go \{[^}]*min-height: 44px/.test(css));
  check("the folder chip next to it has the same X", (() => {
    const cf = fs.readFileSync(path.join(ROOT, "dashboard/composer-folder.js"), "utf8");
    return /class="cp-pin-open"/.test(cf) && /class="cp-pin-x"/.test(cf) && /closest\("\.cp-pin-x"\)\) \{\s*pin\(""\)/.test(cf);
  })());
  check("no em dash in the script", SRC.indexOf(String.fromCharCode(0x2014)) < 0);

  if (fails.length) { console.log("\nFAIL - test_github_repo_picker: " + fails.length + ": " + fails.join(", ")); process.exit(1); }
  console.log("\nOK - test_github_repo_picker: all pass");
  process.exit(0);
})().catch((err) => { console.error(err); process.exit(1); });
