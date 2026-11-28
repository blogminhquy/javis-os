// Claude Code card: Connect Claude signs in fully first, then adds the long-lived token as the backup (owner,
// 2026-11-28: "keep both, but sign in fully first and get the token after").
//
//     node tests/js/test_claude_login_then_token.js
//
// One sign-in cannot give both (a setup-token carries `user:inference` only, the claude.ai connectors need the full
// login), so the card chains the two: step 1 `claude auth login`, step 2 `claude setup-token` right after it, with a
// Later button. A login with no token behind it shows an amber row and one button for the token.
//
// Test style: load the REAL card functions out of console.js into a vm with a stub DOM, then press the buttons.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : ""));
  if (!cond) fails.push(name);
}

function grab(head) {
  const i = SRC.indexOf(head);
  if (i === -1) return "";
  return SRC.slice(i, SRC.indexOf("\n  }\n", i) + 4);
}
const fnCard = grab("async function refreshClaudeCard(");
const fnUpd = grab("function veCapNhatClaude(");
const fnBox = grab("function claudeTokenBox(");
const fnBind = grab("function bindClaudeToken(");
const iFlows = SRC.indexOf("  const CLAUDE_FLOWS");
const fnFlows = iFlows < 0 ? "" : SRC.slice(iFlows, SRC.indexOf("\n  }\n", SRC.indexOf("async function startClaudeToken", iFlows)) + 4);
check("the card's functions are in console.js", !!(fnCard && fnUpd && fnBox && fnBind && fnFlows));

// ---- stub DOM: one node per id and per data- attribute, made again on every render ----
// Redrawing a node drops what was inside it, like the browser: everything a render made after the node's own id (the
// card's markup nests that way) or made by the node's earlier render.
function makeDom() {
  const byId = {}, byAttr = {}, made = new Map();   // node -> [render html, position]
  function drop(self) {
    for (const map of [byId, byAttr]) {
      for (const [k, n] of Object.entries(map)) {
        if (!made.has(n)) continue;   // the page's own nodes, drawn before the card
        const [html, at] = made.get(n);
        const own = html.indexOf('id="' + self.id + '"');
        if (html === self._html || (own >= 0 && at > own)) delete map[k];
      }
    }
  }
  function node(id) {
    return {
      id, className: "", textContent: "", value: "", disabled: false, hidden: false, onclick: null,
      style: {}, isConnected: true, _html: "",
      set innerHTML(v) {
        drop(this);
        this._html = v = String(v);
        for (const m of v.matchAll(/id="([^"]+)"/g)) { byId[m[1]] = node(m[1]); made.set(byId[m[1]], [v, m.index]); }
        for (const m of v.matchAll(/(data-[a-z-]+)="/g)) { byAttr[m[1]] = node(m[1]); made.set(byAttr[m[1]], [v, m.index]); }
      },
      get innerHTML() { return this._html; },
      querySelector(sel) {
        if (sel.startsWith("#")) return byId[sel.slice(1)] || null;
        const m = /^\[(data-[a-z-]+)\]$/.exec(sel);
        return m ? (byAttr[m[1]] || null) : null;
      },
      closest() { return null; },
      addEventListener() {},
      focus() {},
      insertAdjacentHTML(where, v) { this.innerHTML = this._html + v; },
    };
  }
  const el = node("page");
  for (const id of ["cliStatus", "cliAction", "cliUpd"]) byId[id] = node(id);
  return { el, byId, byAttr };
}

function load(answers) {
  const calls = { fetch: [], render: 0 };
  const ctx = {
    t: (k, v) => k + (v ? JSON.stringify(v) : ""),
    esc: (s) => String(s == null ? "" : s),
    safeHref: (u) => u,
    Icons: { warn: (s) => "WARN:" + s },
    CHECK_ICON: "",
    LOC: () => "en-US",
    infoBtn: () => '<button class="info-i"></button>',
    infoBody: (h) => '<div class="info-body">' + h + "</div>",
    renderModelsCloudTab: () => { calls.render++; },
    takeAcctName: () => "",
    savePlanName: async () => {},
    ic: (n) => '<svg data-ic="' + n + '"></svg>',
    acctNameTag: () => "",
    acctLine: () => "",
    acctNameField: () => "",
    saveSetting: async () => ({ ok: true }),
    setTimeout: () => 0,
    clearTimeout: () => {},
    window: { addEventListener() {}, removeEventListener() {} },
    document: { hidden: false, addEventListener() {}, removeEventListener() {} },
    FormData: class { append(k, v) { this[k] = v; } },
    fetch: async (url, init) => {
      calls.fetch.push(url);
      const a = answers[url.split("?")[0]];
      return { json: async () => (typeof a === "function" ? a() : a || { ok: true }) };
    },
  };
  vm.createContext(ctx);
  vm.runInContext([fnUpd, fnBox, fnBind, fnFlows, fnCard].join("\n")
    + "\nthis.refreshClaudeCard = refreshClaudeCard; this.CLAUDE_FLOWS = CLAUDE_FLOWS;", ctx);
  return { ctx, calls };
}

const LINK = { ok: true, url: "https://claude.ai/oauth/authorize?x=1" };
const tick = () => new Promise((r) => setImmediate(r));
async function press(btn) { await btn.onclick(); for (let i = 0; i < 5; i++) await tick(); }

(async () => {
  const gate = (first) => ({ connected: false, auth_mode: "subscription", auth_token_auto: true, auth_login_first: first,
    cap_nhat: {} });

  // ---- 1. Connect Claude on a machine that can: step 1 is the full sign-in, step 2 the token, right after ----
  {
    const { ctx, calls } = load({ "/claude/status": gate(true), "/claude/login-start": LINK, "/claude/token/start": LINK,
      "/claude/login-code": { ok: true }, "/claude/token/code": { ok: true } });
    const { el, byId, byAttr } = makeDom();
    await ctx.refreshClaudeCard(el);
    check("the gate's (i) explains the two steps", byId.cliAction.innerHTML.includes("models.tok_first_info"));
    await press(byAttr["data-tok-get"]);
    check("CANARY: Connect Claude starts the FULL sign-in first, not the token",
      calls.fetch.includes("/claude/login-start") && !calls.fetch.includes("/claude/token/start"), calls.fetch.join(","));
    const s1 = byId.cliTok.innerHTML;
    check("step 1 says it is step 1 of 2 and carries the connectors", s1.includes("models.tok_step1")
      && s1.includes("models.conn_s1_first"));
    check("step 1 has no Later button (the sign-in is the step turns run on)", !s1.includes('id="cliTokLater"'));
    byId.cliTokCode.value = "code-1";
    await press(byId.cliTokCodeBtn);
    check("the step 1 code goes to the sign-in, not the token", calls.fetch.includes("/claude/login-code")
      && !calls.fetch.includes("/claude/token/code"));
    check("CANARY: step 1 done: step 2 (the token) starts on its own, the card is not redrawn yet",
      calls.fetch.includes("/claude/token/start") && calls.render === 0, calls.fetch.join(","));
    const s2 = byId.cliTok.innerHTML;
    check("step 2 says it is step 2 of 2 and that claude.ai is already signed in",
      s2.includes("models.tok_step2") && s2.includes("models.tok_s1_backup"));
    check("step 2 has a Later button", s2.includes('id="cliTokLater"'));
    byId.cliTokCode.value = "code-2";
    await press(byId.cliTokCodeBtn);
    check("step 2's code makes the token, then the card is redrawn",
      calls.fetch.includes("/claude/token/code") && calls.render === 1);
  }

  // ---- 2. Later on step 2: the card is redrawn, no token is asked for ----
  {
    const { ctx, calls } = load({ "/claude/status": gate(true), "/claude/login-start": LINK, "/claude/token/start": LINK,
      "/claude/login-code": { ok: true } });
    const { el, byId, byAttr } = makeDom();
    await ctx.refreshClaudeCard(el);
    await press(byAttr["data-tok-get"]);
    byId.cliTokCode.value = "code-1";
    await press(byId.cliTokCodeBtn);
    await press(byId.cliTokLater);
    check("Later redraws the card and sends no token code",
      calls.render === 1 && !calls.fetch.includes("/claude/token/code"));
  }

  // ---- 3. Step 2 cannot start: the reason shows in step 1's message line ----
  {
    const { ctx } = load({ "/claude/status": gate(true), "/claude/login-start": LINK,
      "/claude/token/start": { ok: false, error: "no-pty" }, "/claude/login-code": { ok: true } });
    const { el, byId, byAttr } = makeDom();
    await ctx.refreshClaudeCard(el);
    await press(byAttr["data-tok-get"]);
    byId.cliTokCode.value = "code-1";
    await press(byId.cliTokCodeBtn);
    check("a step 2 that cannot start says why, on the card", /WARN:no-pty/.test(byId.cliTokMsg2.innerHTML || ""));
  }

  // ---- 4. A Mac or Windows (auth_login_first false): the token stays the one way in, as before ----
  {
    const { ctx, calls } = load({ "/claude/status": gate(false), "/claude/token/start": LINK });
    const { el, byId, byAttr } = makeDom();
    await ctx.refreshClaudeCard(el);
    check("the gate's (i) is the token one", byId.cliAction.innerHTML.includes("models.tok_info")
      && !byId.cliAction.innerHTML.includes("models.tok_first_info"));
    await press(byAttr["data-tok-get"]);
    check("Connect Claude runs the token there", calls.fetch.includes("/claude/token/start")
      && !calls.fetch.includes("/claude/login-start"));
    check("with no step header", !byId.cliTok.innerHTML.includes("models.tok_step1"));
  }

  // ---- 5. Signed in, no token behind it: an amber row and one button that gets the token (not a new sign-in) ----
  {
    const { ctx, calls } = load({ "/claude/status": { connected: true, auth_mode: "subscription", auth_token_auto: true,
      auth_login_first: true, cap_nhat: {} }, "/claude/token/start": LINK });
    const { el, byId, byAttr } = makeDom();
    await ctx.refreshClaudeCard(el);
    const h = byId.cliAction.innerHTML;
    check("CANARY: a login with no backup token shows the amber row", /prov-tok-row warn[\s\S]*models\.tok_backup_off/.test(h));
    check("its button is Get the backup token, its (i) says why", h.includes("models.tok_backup_btn")
      && h.includes("models.tok_backup_info") && !h.includes("models.tok_switch\""));
    check("Disconnect stays on the card", h.includes('id="cliLogout"'));
    await press(byAttr["data-tok-get"]);
    check("the button runs the token only", calls.fetch.includes("/claude/token/start")
      && !calls.fetch.includes("/claude/login-start"));
    check("as step 2 alone (no step header, no chain)", !byId.cliTok.innerHTML.includes("models.tok_step"));
  }
  {
    const { ctx } = load({ "/claude/status": { connected: true, auth_mode: "subscription", auth_token_auto: true,
      auth_login_first: false, cap_nhat: {} } });
    const { el, byId } = makeDom();
    await ctx.refreshClaudeCard(el);
    check("where the token is the one way in, the old Switch to a long-lived token stays",
      byId.cliAction.innerHTML.includes("models.tok_switch") && !byId.cliAction.innerHTML.includes("models.tok_backup_off"));
  }

  // ---- 6. Strings ----
  const KEYS = ["models.tok_step1", "models.conn_s1_first", "models.tok_step2", "models.tok_s1_backup",
    "models.tok_later", "models.tok_backup_off", "models.tok_backup_btn", "models.tok_backup_info",
    "models.tok_first_info"];
  for (const [lang, tr] of [["vi", VI], ["en", EN]]) {
    check(lang + ": the new lines are translated", KEYS.every((k) => tr[k]));
    check(lang + ": no em or en dash in them", KEYS.every((k) => !/[\u2013\u2014]/.test(tr[k] || "")));
    check(lang + ": the lines outside (i) stay short", ["models.tok_backup_off", "models.conn_s1_first",
      "models.tok_s1_backup"].every((k) => (tr[k] || "").length <= 110));
  }

  console.log();
  if (fails.length) { console.log("FAILED " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
  console.log("All passed");
})();
