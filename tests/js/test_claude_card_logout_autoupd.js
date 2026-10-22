// Claude Code card on the Models page: the Disconnect button asks first, and the daily
// auto-update has an on/off switch (customer report 0.270, codes 19 and 18).
//
//     node tests/js/test_claude_card_logout_autoupd.js
//
// Code 19: "Ngắt" called POST /claude/logout on the first tap, so one stray tap signed the
// machine out of the Claude plan. Code 18: the daily `claude update` could only be turned off
// with the env var JAVIS_CLAUDE_AUTO_UPDATE=0.
//
// Test style: load the REAL refreshClaudeCard / veCapNhatClaude out of console.js into a vm with
// a stub DOM, then press the buttons, instead of only scanning strings.
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
check("refreshClaudeCard is in console.js", !!fnCard);
check("veCapNhatClaude is in console.js", !!fnUpd);

// ---- stub DOM: one element per id, created on demand ----
function makeEl() {
  const byId = {};
  function node(id) {
    return {
      id, className: "", textContent: "", disabled: false, checked: false, onclick: null, onchange: null,
      style: {}, isConnected: true, _html: "",
      set innerHTML(v) {
        this._html = v;
        // Re-rendering creates fresh children, like the browser does.
        for (const m of String(v).matchAll(/id="([^"]+)"/g)) {
          byId[m[1]] = node(m[1]);
          if (m[1] === "cliAutoUpd") byId[m[1]].checked = / id="cliAutoUpd"[^>]* checked/.test(v);
        }
      },
      get innerHTML() { return this._html; },
      querySelector(sel) { return sel.startsWith("#") ? (byId[sel.slice(1)] || null) : null; },
    };
  }
  const el = node("page");
  for (const id of ["cliStatus", "cliAction", "cliUpd"]) byId[id] = node(id);
  return { el, byId };
}

function load(opts) {
  const calls = { fetch: [], confirm: [], save: [] };
  const ctx = {
    t: (k, v) => k + (v ? JSON.stringify(v) : ""),
    esc: (s) => String(s == null ? "" : s),
    Icons: { warn: (s) => "WARN:" + s },
    CHECK_ICON: "",
    LOC: () => "en-US",
    infoBtn: () => '<button class="info-i"></button>',
    infoBody: (h) => '<div class="info-body">' + h + "</div>",
    renderModelsCloudTab: () => {},
    startClaudeLogin: () => {},
    confirm: (msg) => { calls.confirm.push(msg); return opts.confirm; },
    saveSetting: async (section, data) => { calls.save.push([section, data]); return opts.save || { ok: true }; },
    fetch: async (url, init) => {
      calls.fetch.push([url, (init && init.method) || "GET"]);
      if (url.startsWith("/claude/status")) return { json: async () => opts.status };
      return { json: async () => ({ ok: true }) };
    },
  };
  vm.createContext(ctx);
  vm.runInContext(fnUpd + "\n" + fnCard + "\nthis.refreshClaudeCard = refreshClaudeCard; this.veCapNhatClaude = veCapNhatClaude;", ctx);
  return { ctx, calls };
}

(async () => {
  // ---- Code 19: Disconnect asks first ----
  const status = { connected: true, email: "a@b.c", cap_nhat: {}, auto_update: true };
  for (const yes of [false, true]) {
    const { ctx, calls } = load({ confirm: yes, status });
    const { el, byId } = makeEl();
    await ctx.refreshClaudeCard(el);
    const btn = byId.cliLogout;
    check("connected card draws the Disconnect button", !!btn);
    if (!btn) continue;
    await btn.onclick();
    const loggedOut = calls.fetch.some(([u, m]) => u === "/claude/logout" && m === "POST");
    check("Disconnect asks with the logout confirm text",
      calls.confirm.length === 1 && calls.confirm[0] === "models.cc_logout_confirm");
    if (yes) check("confirm accepted: POST /claude/logout is sent", loggedOut);
    else check("confirm cancelled: no POST /claude/logout and the button stays usable", !loggedOut && !btn.disabled);
  }
  check("vi confirm text says it signs out and must sign in again",
    /đăng xuất/i.test(VI["models.cc_logout_confirm"] || "") && /đăng nhập lại/i.test(VI["models.cc_logout_confirm"] || ""));
  check("en confirm text says it signs out and must sign in again",
    /sign claude code out/i.test(EN["models.cc_logout_confirm"] || "") && /sign in again/i.test(EN["models.cc_logout_confirm"] || ""));

  // ---- Code 18: the auto-update switch ----
  {
    const { ctx, calls } = load({ status });
    const { el, byId } = makeEl();
    ctx.veCapNhatClaude(el, { cap_nhat: { sau: "2.1.300", ts: 1 }, auto_update: true });
    const sw = byId.cliAutoUpd;
    check("the card draws the auto-update switch, on by default", !!sw && sw.checked && !sw.disabled);
    check("the switch has a 16px label and its long explanation sits in the (i) block",
      /cc-auto-row[^>]*font-size:16px/.test(byId.cliUpd.innerHTML)
      && /class="info-body">models\.cc_auto_info/.test(byId.cliUpd.innerHTML));
    sw.checked = false;
    await sw.onchange();
    check("turning it off saves model.claude_auto_update=false",
      calls.save.length === 1 && calls.save[0][0] === "model"
      && JSON.stringify(calls.save[0][1]) === '{"claude_auto_update":false}');
    check("after saving it says it is off", byId.cliUpdMsg.textContent === "models.cc_auto_off_done");
  }
  {
    const { ctx } = load({ status, save: { ok: false } });
    const { el, byId } = makeEl();
    ctx.veCapNhatClaude(el, { cap_nhat: {}, auto_update: false });
    const sw = byId.cliAutoUpd;
    check("saved off: the switch draws off", !!sw && !sw.checked);
    sw.checked = true;
    await sw.onchange();
    check("a failed save puts the switch back and says so",
      !sw.checked && /models\.cc_auto_save_fail/.test(byId.cliUpdMsg.innerHTML));
  }
  {
    const { ctx } = load({ status });
    const { el, byId } = makeEl();
    ctx.veCapNhatClaude(el, { cap_nhat: {}, auto_update: false, auto_update_env_off: true });
    const sw = byId.cliAutoUpd;
    check("env JAVIS_CLAUDE_AUTO_UPDATE=0: switch off and locked, with the reason shown",
      !!sw && !sw.checked && / id="cliAutoUpd"[^>]* disabled/.test(byId.cliUpd.innerHTML)
      && byId.cliUpd.innerHTML.includes("models.cc_auto_env_off"));
  }
  {
    const { ctx } = load({ status });
    const { el, byId } = makeEl();
    ctx.veCapNhatClaude(el, { cap_nhat_docker: true });
    check("Docker build: no switch (the image brings Claude Code)", !byId.cliAutoUpd);
  }

  for (const k of ["models.cc_logout_confirm", "models.cc_auto_label", "models.cc_auto_info",
    "models.cc_auto_env_off", "models.cc_auto_on_done", "models.cc_auto_off_done", "models.cc_auto_save_fail"]) {
    check("i18n key " + k + " exists in vi and en", !!VI[k] && !!EN[k]);
  }

  if (fails.length) { console.log("\nFAIL - test_claude_card_logout_autoupd: " + fails.length); process.exit(1); }
  console.log("\nOK - test_claude_card_logout_autoupd: all pass");
})().catch((e) => { console.log("FAIL crashed: " + (e && e.stack || e)); process.exit(1); });
