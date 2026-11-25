/* `#ht=<id>` opens one conversation of the Inbox (Hộp thư).

       node tests/js/test_deep_link_conv.js

   Owner 2026-11-25: a report listing customers who wait for an answer should carry a button that opens that
   customer's chat. Runs console.js's deepLinkConv, chat-render.js's link rule and conversations.js's moTu. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CONSOLE = D("console.js");
const RENDER = D("chat-render.js");
const CONV = D("conversations.js");

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
  const fnSrc = cut(CONSOLE, "  function deepLinkConv(hash) {");
  check("console.js has deepLinkConv", !!fnSrc);
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(fnSrc + "\nthis.f = deepLinkConv;", ctx);
  const f = ctx.f;
  check("CANARY: #ht=<number> names a conversation", f("#ht=1") === 1 && f("#ht=4821") === 4821);
  check("zero, letters, markup and extras are ignored",
    f("#ht=0") === 0 && f("#ht=abc") === 0 && f("#ht=1<img>") === 0 && f("#ht=1&x=2") === 0 && f("#ht=") === 0);
  check("other hashes are not conversation links", f("#p=conversations") === 0 && f("#task=k:1") === 0 && f(null) === 0);

  // runDeepLink hands a #ht= link to openConvLink
  const bootSrc = CONSOLE.slice(CONSOLE.indexOf("function boot()"));
  const rdStart = bootSrc.indexOf("    let deepHashDone = null;");
  const rdSrc = bootSrc.slice(rdStart, bootSrc.indexOf("\n    };\n", rdStart) + 7);
  const calls = [];
  const rctx = {
    location: { hash: "#ht=77" }, window: { addEventListener() {} },
    openVaultPath: () => calls.push("open"), moCongSu: () => calls.push("cs"),
    deepLinkPage: () => "", deepLinkTask: () => "", openTaskLink: () => calls.push("task"),
    deepLinkConv: f, openConvLink: (id) => calls.push("conv:" + id),
    Alpine: { store: () => ({ go: (id) => calls.push("go:" + id) }) },
  };
  vm.createContext(rctx);
  vm.runInContext(rdSrc + "\nrunDeepLink();", rctx);
  check("CANARY: runDeepLink opens the conversation", calls.join() === "conv:77", calls);

  // chat-render.js turns [text](#ht=id) into an in-app link, and only for a plain number
  check("chat-render renders #ht= as a jv-ht link", /class="jv-ht" href="#ht=' \+ ht\[1\]/.test(RENDER));
  check("chat-render click opens it through JavisOpenConv", /a\.jv-ht[\s\S]{0,400}JavisOpenConv/.test(RENDER));
  check("console.js exposes JavisOpenConv", /window\.JavisOpenConv = openConvLink/.test(CONSOLE));

  // conversations.js moTu with conv: selects that chat and clears the filters
  const moSrc = cut(CONV, "  function moTu(opts) {");
  const c2 = { _cho: null, _chon: 0, _msgs: [1], _conv: {}, _dauVetTin: "x", _vetMeta: "x", _tab: "",
    TABS: ["inbox", "bot"], chuanTab: (x) => x, _host: null, document: { body: { contains: () => false } },
    went: "" };
  c2.Alpine = { store: () => ({ go(id) { c2.went = id; } }) };
  c2.window = { Alpine: c2.Alpine };
  vm.createContext(c2);
  vm.runInContext("var _cho=this._cho,_chon=0,_msgs=[1],_conv={},_dauVetTin='x',_vetMeta='x',_tab='',_host=null;" + moSrc +
    "\nmoTu({tab:'inbox', conv: 42}); this.r = {chon:_chon, cho:_cho, msgs:_msgs.length, conv:_conv, tab:_tab};", c2);
  check("CANARY: moTu opens that conversation with no filter left", c2.r.chon === 42 && JSON.stringify(c2.r.cho) === "{}" &&
    c2.r.msgs === 0 && c2.r.conv === null && c2.r.tab === "inbox" && c2.went === "conversations", c2.r);

  if (fails.length) { console.log("\n" + fails.length + " failed"); process.exit(1); }
  console.log("\nall ok");
})();
