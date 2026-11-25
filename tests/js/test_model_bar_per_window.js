// Model and effort picked in one chat window stay in that window. Runs model-picker.js with a fake
// page and records every request it sends.
//
//     node tests/js/test_model_bar_per_window.js
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.resolve(__dirname, "..", "..");
let fails = 0;
function check(name, cond, extra) { console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]")); if (!cond) fails++; }

function el() {
  const cls = new Set();
  return { textContent: "", title: "", hidden: false, innerHTML: "", dataset: {}, style: {},
    classList: { toggle: (c, on) => { if (on) cls.add(c); else cls.delete(c); }, contains: (c) => cls.has(c) },
    setAttribute() {}, querySelector: () => null, insertBefore() {}, has: (c) => cls.has(c) };
}

(async () => {
  const els = { mbModelTxt: el(), mbOpen: el(), effTxt: el(), effBtn: el() };
  const calls = [];
  let sid = null;
  let meta = {};
  const listeners = {};
  const resp = (d) => Promise.resolve({ ok: true, json: () => Promise.resolve(d) });
  const sb = {
    console, Promise, setTimeout, clearTimeout, encodeURIComponent,
    FormData: function () { const f = {}; this.append = (k, v) => { f[k] = v; }; this.fields = f; },
    CustomEvent: function (n) { this.type = n; },
    document: { addEventListener() {}, getElementById: (id) => els[id] || null, activeElement: null, createElement: () => el() },
    fetch: (u, o) => {
      u = String(u);
      if (o && o.method === "POST") { calls.push([u, o.body.fields]); return resp({ ok: true }); }
      if (u === "/settings") return resp({ model: { providers: [
        { id: "openai-oauth", label: "ChatGPT", configured: true }, { id: "anthropic-cli", label: "Claude Code", configured: true }],
        main: { provider: "openai-oauth", model: "gpt-x" }, reasoning: "ultra", routing: { defaults: {} } } });
      if (u.startsWith("/chat/route")) return resp(u.includes("anthropic-cli")
        ? { provider: "anthropic-cli", model: "opus", reasoning: "high", fallback: false }
        : { provider: "openai-oauth", model: "gpt-x", reasoning: "ultra", fallback: false });
      return resp(meta);
    },
  };
  sb.window = sb;
  sb.t = (k) => k;
  sb.addEventListener = (n, f) => { listeners[n] = f; };
  sb.dispatchEvent = () => {};
  sb.matchMedia = () => ({ matches: false });
  sb.JavisSessions = { current: () => sid, brain: () => "brain" };
  vm.createContext(sb);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "dashboard", "model-picker.js"), "utf8"), sb);
  await sb.initModelBar();

  // an empty chat: the pick is held, nothing is saved anywhere
  sb.JavisModelList = { models: async (p) => (p === "anthropic-cli" ? ["opus"] : ["gpt-x"]) };
  await sb.JavisModelBar.chon("opus");
  check("picking a model on an empty chat saves nothing", calls.length === 0, JSON.stringify(calls));
  check("...and the chip shows that model with its card's level",
    els.mbModelTxt.textContent === "Opus" && els.effTxt.textContent === "eff.high",
    els.mbModelTxt.textContent + " " + els.effTxt.textContent);

  sid = "NEW1";
  const done = sb.JavisModelBar.claimPending("NEW1");
  check("the first send gets a promise to wait for", !!done && typeof done.then === "function");
  await done;
  check("the picked model goes to that chat only", calls.length === 1 && calls[0][0] === "/sessions/NEW1/model"
    && calls[0][1].provider === "anthropic-cli", JSON.stringify(calls));
  check("nothing more to claim", sb.JavisModelBar.claimPending("NEW2") === null);

  // a saved chat: another model, in this chat only
  calls.length = 0;
  sid = "OLD1";
  meta = { id: "OLD1", channel: "web", pinned_provider: "openai-oauth", pinned_model: "gpt-x",
    route: { provider: "openai-oauth", model: "gpt-x", reasoning: "low", fallback: false } };
  await sb.initModelBar();
  check("a saved chat shows its own level", els.effTxt.textContent === "eff.low", els.effTxt.textContent);
  await sb.JavisModelBar.chon("opus");
  check("changing the model of a saved chat posts to that chat alone",
    calls.length === 1 && calls[0][0] === "/sessions/OLD1/model", JSON.stringify(calls.map((c) => c[0])));

  // an unpinned Javis Core window follows Core's model without being drawn as pinned
  sid = "CORE1";
  meta = { id: "CORE1", channel: "agent:javis-core", agent_slug: "javis-core", agent_reasoning: "medium",
    inherited_pin: { provider: "anthropic-cli", model: "opus" } };
  await sb.initModelBar();
  check("an unpinned Core window shows Javis Core's model", els.mbModelTxt.textContent === "Opus", els.mbModelTxt.textContent);
  check("...and is not drawn as pinned", !els.mbOpen.has("is-pinned"));

  const app = fs.readFileSync(path.join(ROOT, "dashboard", "app.js"), "utf8");
  check("app.js makes the first turn wait for the picks",
    /_modelClaim = window\.JavisModelBar\.claimPending\(savedSessionId\)/.test(app) && /_modelClaim\.catch/.test(app));
  if (fails) { console.log("\nFAILED " + fails); process.exit(1); }
  console.log("\nOK - test_model_bar_per_window");
})();
