/* Javis Core's model on the chat model chip (0.461.0). Since 2026-11-05 its card is the ordinary agent editor, whose
 * Model field is the same Javis Core pin; the separate card script (core-model.js) is gone.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.resolve(__dirname, "..", "..");
let fails = 0;
function check(name, cond, extra) { console.log((cond ? "ok   " : "FAIL ") + name + (cond ? "" : "  [" + extra + "]")); if (!cond) fails++; }

const mp = fs.readFileSync(path.join(ROOT, "dashboard", "model-picker.js"), "utf8");
check("the chat model bar tells the page when Javis Core's pin changes", mp.includes('"javis:core-model"') && mp.includes("coreChanged()"), "");

// Owner 04/11/2026: "the Core pin does not hold, changing the main chat's model changes Core too". One cause: after a
// message in an UNPINNED Core chat, noteStamped() drew the main model as this chat's pin (pin icon on the chip), as for
// a normal chat. The server never stamps a Core chat (it runs on Core's pin or the main model), so the chip lied.
(async () => {
  function el() {
    const cls = new Set();
    return { textContent: "", title: "", hidden: false, innerHTML: "", dataset: {}, style: {},
      classList: { toggle: (c, on) => { if (on) cls.add(c); else cls.delete(c); }, contains: (c) => cls.has(c) },
      setAttribute() {}, querySelector: () => null, insertBefore() {}, has: (c) => cls.has(c) };
  }
  const els = { mbModelTxt: el(), mbOpen: el() };
  let meta = {};
  const resp = (d) => Promise.resolve({ ok: true, json: () => Promise.resolve(d) });
  const sb = {
    console, Promise, setTimeout, CustomEvent: function (n, o) { this.type = n; this.detail = (o || {}).detail; },
    document: { addEventListener() {}, getElementById: (id) => els[id] || null, activeElement: null,
                createElement: () => el() },
    fetch: (u) => resp(String(u).startsWith("/settings")
      ? { model: { providers: [{ id: "anthropic-cli", label: "Claude Code", configured: true }],
                   main: { provider: "anthropic-cli", model: "opus" }, routing: { defaults: {} } } }
      : meta),
  };
  sb.window = sb;
  sb.t = (k) => k;
  sb.addEventListener = () => {};
  sb.dispatchEvent = () => {};
  sb.matchMedia = () => ({ matches: false });
  let sid = "CORE1";
  sb.JavisSessions = { current: () => sid, brain: () => "brain" };
  vm.createContext(sb);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "dashboard", "model-picker.js"), "utf8"), sb);
  meta = { id: "CORE1", channel: "agent:javis-core", agent_slug: "javis-core", agent_reasoning: "medium" };
  await sb.initModelBar();
  sb.JavisModelBar.noteStamped("CORE1");
  check("an unpinned Javis Core chat is not drawn as pinned after a message", !els.mbOpen.has("is-pinned"), "is-pinned set");
  sid = "MAIN1";
  meta = { id: "MAIN1", channel: "web" };
  await sb.initModelBar();
  sb.JavisModelBar.noteStamped("MAIN1");
  check("a normal chat still shows the model it was stamped with", els.mbOpen.has("is-pinned"), "no pin on a normal chat");
  if (fails) { console.log("\nFAILED " + fails); process.exit(1); }
  console.log("\nOK - test_core_model_card");
})();

