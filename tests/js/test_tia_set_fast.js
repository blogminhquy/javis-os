/* Fast mode bolt (0.153.0): tooltip per brain, dimmed when the brain has no Fast mode, saves settings.model.fast.

       node tests/js/test_tia_set_fast.js
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const src = fs.readFileSync(path.join(ROOT, "dashboard/model-picker.js"), "utf8");
const vi = require("../../dashboard/i18n/vi.json"), en = require("../../dashboard/i18n/en.json");
let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const m = src.match(/\/\/ FAST_NOTE_BEGIN[\s\S]*?\/\/ FAST_NOTE_END/);
check("the FAST_NOTE block can be extracted for testing", !!m);
const fastNote = new Function(m[0] + "\nreturn fastNote;")();
const cases = [
  ["anthropic-cli", "", true, "fast.claude"], ["anthropic-cli", "claude-opus-5-5", true, "fast.claude"],
  ["anthropic-cli", "claude-sonnet-5-5", false, "fast.model_none"], ["anthropic-api", "claude-opus-4-8", true, "fast.api"],
  ["openai-oauth", "gpt-6.1-sol", true, "fast.codex"], ["openai", "gpt-6-sol", true, "fast.api"],
  ["openrouter", "openai/gpt-6", true, "fast.api"], ["gemini", "gemini-4-argon", true, "fast.api"],
  ["grok-cli", "", false, "fast.none"], ["antigravity-cli", "gemini-3.8-flash-high", false, "fast.none"],
  ["groq", "x", false, "fast.none"], ["deepseek", "x", false, "fast.none"], ["ollama", "x", false, "fast.none"],
  // The Claude Code alias "opus" points at Opus 5.5 (first in the catalog and the fallback default).
  ["anthropic-cli", "opus", true, "fast.claude"], ["anthropic-cli", "sonnet", false, "fast.model_none"],
];
cases.forEach(([p, mo, sup, note]) => {
  const r = fastNote(p, mo);
  check(p + " " + (mo || "(default)") + " -> " + (sup ? "supported" : "not supported") + ", " + note, r.supported === sup && r.note === note);
});
["fast.claude", "fast.codex", "fast.api", "fast.none", "fast.model_none"].forEach(k =>
  check("key " + k + " in vi and en", !!vi[k] && !!en[k]));
check("the tooltip starts with 'Fast mode' and no on/off text shows on the page", src.indexOf('"Fast mode\\n" + window.t(') !== -1);
// 0.164.0: Fast mode is wired into the engines, so the "takes effect in the next update" line is gone,
// and the tooltip shows the last real state the brain reported (GET /model/fast-state).
check("the pending line is gone now that Fast mode is wired", src.indexOf("fast.pending") === -1 && !vi["fast.pending"] && !en["fast.pending"]);
check("the bolt reads the real state from /model/fast-state", src.indexOf('"/model/fast-state"') !== -1);
check("cooldown and fallback states have their own tooltip line",
  /fast\.state_cooldown/.test(src) && /fast\.state_fallback/.test(src) && !!vi["fast.state_cooldown"] && !!en["fast.state_fallback"]);
const stateLine = (src.match(/\/\/ FAST_STATE_BEGIN[\s\S]*?\/\/ FAST_STATE_END/) || [""])[0];
check("the state line is a pure function that can be tested", !!stateLine);
const fastStateKey = new Function(stateLine + "\nreturn fastStateKey;")();
check("cooldown maps to its line", fastStateKey({ state: "cooldown" }) === "fast.state_cooldown");
check("fallback maps to its line", fastStateKey({ state: "fallback" }) === "fast.state_fallback");
check("on or unknown adds no line", fastStateKey({ state: "on" }) === "" && fastStateKey(null) === "");
// Review 0.164.0: Claude Code reports off + a reason (e.g. out_of_credits); the tooltip must say why.
check("off because of usage credits has its own line", fastStateKey({ state: "off", reason: "out_of_credits" }) === "fast.state_credits");
check("off with another reason shows that reason", fastStateKey({ state: "off", reason: "org_disabled" }) === "fast.state_off");
check("off without a reason adds no line", fastStateKey({ state: "off", reason: "" }) === "");
check("i18n has the off lines", !!vi["fast.state_credits"] && !!en["fast.state_off"] && /\{reason\}/.test(en["fast.state_off"]));
check("UI and server agree on which Claude ids support Fast mode",
  fastNote("anthropic-cli", "claude-opus-5-50").supported === false && fastNote("anthropic-cli", "claude-opus-5-20261001").supported === true
  && fastNote("anthropic-cli", "opus").supported === true);
check("clicking the bolt saves settings.model.fast", src.indexOf("saveModel({ fast: state.fast })") !== -1);
// 0.329.0 (owner, 25/10): the bolt moved into the Effort popover's top-right corner; the composer button is the
// plan usage ring now (plan-limit.js). The particles on the slider only run while Fast mode is on.
const slider = fs.readFileSync(path.join(ROOT, "dashboard/effort-slider.js"), "utf8");
const html = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8");
check("the dimmed bolt uses aria-disabled, not disabled", slider.indexOf('setAttribute("aria-disabled"') !== -1 && !/fastBtn\.disabled/.test(slider));
check("the composer has no bolt button any more", html.indexOf('id="fastBtn"') === -1 && src.indexOf("#fastBtn") === -1);
check("the bolt is drawn in the Effort popover head", /class="eff-head"[\s\S]{0,200}eff-fast/.test(slider));
check("the picker hands the popover the Fast state, its tooltip and the save", /fast: \{[\s\S]{0,300}supported: fn\.supported, on: state\.fast, title: fastTitle/.test(src));
check("particles are drawn only while Fast mode is on", /if \(fastOn\) parts\.forEach/.test(slider));
check("the animation frame repeats only while Fast mode is on", /if \(fastOn && !still\) raf = requestAnimationFrame\(draw\)/.test(slider));
check("the Effort chip shows a small bolt while Fast mode is on", html.indexOf('id="effFast"') !== -1 && src.indexOf('$("effFast")') !== -1);

if (fails.length) { console.log("\nFAIL - test_tia_set_fast: " + fails.length); process.exit(1); }
console.log("\nOK - test_tia_set_fast: all pass");
