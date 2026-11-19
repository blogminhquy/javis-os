/* `#task=<id>` opens one item of the Tasks page.

       node tests/js/test_deep_link_task.js

   Before: a link could name a page (`#p=tasks`) or a file (`#open=`), never one task, so a page
   outside the dashboard could only send the reader to the Tasks page to search by hand. Now
   `#task=k:<job>`, `#task=r:<reminder>` and `#task=m:<own task>` open the page, pick the tab the
   item lives on and open its details.

   Runs console.js's deepLinkTask, openTaskLink and runDeepLink, and tasks.js's openItem, in a vm. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CONSOLE = D("console.js");
const TASKS = D("tasks.js");

const fails = [];
const check = (name, cond, extra) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  if (!cond) fails.push(name);
};
const cut = (src, head) => {
  const a = src.indexOf(head);
  return a < 0 ? "" : src.slice(a, src.indexOf("\n  }\n", a) + 4);
};

(async () => {
  // 1. deepLinkTask: which hash names a task
  const fnSrc = cut(CONSOLE, "  function deepLinkTask(hash) {");
  check("console.js has deepLinkTask", !!fnSrc);
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(fnSrc + "\nthis.deepLinkTask = deepLinkTask;", ctx);
  const task = ctx.deepLinkTask;
  check("CANARY: an own task, a reminder and a Kanban job are task links",
    task("#task=m:t_12ab") === "m:t_12ab" && task("#task=r:r_593cbc299d") === "r:r_593cbc299d" && task("#task=k:j7c889795") === "k:j7c889795");
  check("an id without a known prefix is ignored", task("#task=abc") === "" && task("#task=x:1") === "" && task("#task=") === "");
  check("CANARY: markup or a path in the id is ignored",
    task("#task=m:<img>") === "" && task("#task=m:a/b") === "" && task("#task=m:a b") === "" && task("#task=m:a&x=1") === "");
  check("other hashes are not task links", task("#p=tasks") === "" && task("#open=a.md") === "" && task("") === "" && task(null) === "");

  // 2. runDeepLink sends a task link on, and leaves the three older kinds alone
  const bootSrc = CONSOLE.slice(CONSOLE.indexOf("function boot()"));
  const rdStart = bootSrc.indexOf("    let deepHashDone = null;");
  const rdSrc = bootSrc.slice(rdStart, bootSrc.indexOf("\n    };\n", rdStart) + 7);
  const calls = [];
  const rctx = {
    location: { hash: "" },
    openVaultPath: (p) => calls.push("open:" + p),
    moCongSu: (s) => calls.push("cs:" + s),
    deepLinkPage: (h) => (h === "#p=tasks" ? "tasks" : ""),
    deepLinkTask: task,
    openTaskLink: (id) => calls.push("task:" + id),
    Alpine: { store: () => ({ go: (id) => calls.push("go:" + id) }) },
  };
  vm.createContext(rctx);
  vm.runInContext(rdSrc + "\nthis.runDeepLink = runDeepLink;", rctx);
  const run = (hash) => { calls.length = 0; rctx.location.hash = hash; rctx.runDeepLink(); return JSON.stringify(calls); };
  check("CANARY: #task=m:t1 -> openTaskLink('m:t1')", run("#task=m:t1") === '["task:m:t1"]', calls);
  check("#p=tasks still only opens the page", run("#p=tasks") === '["go:tasks"]', calls);
  check("#open= still only opens the file", run("#open=wiki%2Fa.md") === '["open:wiki/a.md"]', calls);
  check("a bad task id opens nothing", run("#task=zzz") === "[]", calls);

  // 3. openTaskLink: Tasks page first, then the item, once tasks.js has its data
  const olSrc = cut(CONSOLE, "  async function openTaskLink(id) {");
  check("console.js has openTaskLink", !!olSrc);
  const mk = (page) => {
    const log = [];
    const c = {
      window: { JavisTasks: page }, log,
      Alpine: { store: () => ({ go: (id) => log.push("go:" + id) }) },
      toast: (m, err) => log.push("toast:" + m + ":" + err), t: (k) => k,
      setTimeout: (f) => setTimeout(f, 0), Promise,
    };
    vm.createContext(c);
    vm.runInContext(olSrc + "\nthis.openTaskLink = openTaskLink;", c);
    return c;
  };
  let n = 0;
  let c = mk({ ready: () => ++n > 3, openItem: async (id) => { c.log.push("item:" + id); return true; } });
  let r = await c.openTaskLink("m:t1");
  check("CANARY: waits for the page, then opens the item", r === true && JSON.stringify(c.log) === '["go:tasks","item:m:t1"]', c.log);
  c = mk({ ready: () => true, openItem: async () => false });
  r = await c.openTaskLink("m:gone");
  check("an item this brain lacks: says so, stays on Tasks", r === false && JSON.stringify(c.log) === '["go:tasks","toast:nv.link_missing:true"]', c.log);
  c = mk(undefined);
  r = await c.openTaskLink("m:t1");
  check("the page never loads: gives up quietly", r === false && JSON.stringify(c.log) === '["go:tasks"]', c.log);

  // 4. tasks.js openItem: right tab, one reload when missing, details opened
  const oiSrc = cut(TASKS, "  async function openItem(id) {");
  const showSrc = (/ {2}function show\(ref\) \{[^\n]*\}\n/.exec(TASKS) || [""])[0];
  check("tasks.js has openItem, and show() goes through it", !!oiSrc && /openItem\("k:"/.test(showSrc));
  check("tasks.js exports openItem", /window\.JavisTasks = \{[^\n]*openItem: openItem/.test(TASKS));
  const tk = (state, have, afterLoad) => {
    const log = [];
    const t = {
      S: state, log,
      setTab: (tab) => { log.push("tab:" + tab); t.S.tab = tab; if (tab === "me") t.S.sheet = { kind: "morning" }; },
      find: (id) => (have.indexOf(id) >= 0 ? { id } : null),
      load: async () => { log.push("load"); (afterLoad || []).forEach((x) => have.push(x)); },
      openDetail: (id) => log.push("detail:" + id),
    };
    vm.createContext(t);
    vm.runInContext(showSrc + oiSrc + "\nthis.openItem = openItem; this.show = show;", t);
    return t;
  };
  let t = tk({ ai: {}, tab: "ai" }, ["m:t1"]);
  r = await t.openItem("m:t1");
  check("CANARY: an own task switches to the Mine tab and opens", r === true && JSON.stringify(t.log) === '["tab:me","detail:m:t1"]', t.log);
  check("the morning sheet does not cover the opened task", t.S.sheet === null);
  t = tk({ ai: {}, tab: "me" }, ["r:r1"]);
  r = await t.openItem("r:r1");
  check("a reminder switches to the Javis tab and opens", r === true && JSON.stringify(t.log) === '["tab:ai","detail:r:r1"]', t.log);
  t = tk({ ai: {}, tab: "ai" }, [], ["k:j1"]);
  r = await t.show("j1");
  check("show() still opens a Kanban job, reloading once when it is new", r === true && JSON.stringify(t.log) === '["load","detail:k:j1"]', t.log);
  t = tk({ ai: {}, tab: "ai" }, []);
  r = await t.openItem("k:none");
  check("an unknown id: false, nothing opened", r === false && JSON.stringify(t.log) === '["load"]', t.log);
  t = tk(null, ["m:t1"]);
  check("page not mounted: false", (await t.openItem("m:t1")) === false);

  // 5. the line shown for a missing item exists in both languages
  const vi = JSON.parse(D("i18n/vi.json")), en = JSON.parse(D("i18n/en.json"));
  check("nv.link_missing is in vi.json and en.json", !!vi["nv.link_missing"] && !!en["nv.link_missing"]);

  console.log(fails.length ? "\n" + fails.length + " FAILED" : "\nall ok");
  process.exit(fails.length ? 1 : 0);
})();
