/* Plan usage ring (0.329.0): only for brains on a plan, red near either limit, reset text, wiring.

       node tests/js/test_vong_han_muc.js

Owner 25/10: "Thay thế nút sét hiện tại ... là vòng tròn hạn mức ... có hiệu lực cho những model nào có gói
subscription thôi ... màu đỏ là gần hết hạn mức của khung 5 giờ hoặc gần hết hạn mức của tuần cũng đỏ".
*/
const fs = require("fs");
const path = require("path");
const L = require("../../dashboard/plan-limit.js");
const ROOT = path.join(__dirname, "../..");
const src = fs.readFileSync(path.join(ROOT, "dashboard/plan-limit.js"), "utf8");
const html = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8");
const app = fs.readFileSync(path.join(ROOT, "dashboard/app.js"), "utf8");
const picker = fs.readFileSync(path.join(ROOT, "dashboard/model-picker.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard/style.css"), "utf8");
const vi = require("../../dashboard/i18n/vi.json"), en = require("../../dashboard/i18n/en.json");
let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

check("Claude Code on its plan shows the ring", L.brainOf("anthropic-cli", { "anthropic-cli": true }) === "claude");
check("Claude Code on an API key does not", L.brainOf("anthropic-cli", { "anthropic-cli": false }) === "");
check("ChatGPT through Codex shows the ring", L.brainOf("openai-oauth", { "openai-oauth": true }) === "codex");
check("before /plan-limits answers, a plan brain still gets its ring", L.brainOf("anthropic-cli", null) === "claude");
check("Grok Build on its plan gets a ring (red only once refused)", L.brainOf("grok-cli", { "grok-cli": true }) === "grok");
check("Grok on an xAI API key does not", L.brainOf("grok-cli", { "grok-cli": false }) === "");
check("Antigravity gets a ring", L.brainOf("antigravity-cli", { "antigravity-cli": true }) === "agy");
check("the header names the plan when known", L.whoText("claude", "Max") === "Claude · Max" && L.whoText("codex", "Plus") === "ChatGPT · Plus");
check("no plan name: the brand alone, never a guess", L.whoText("agy", "") === "Antigravity");
check("each brain has its own empty-state line", ["claude", "codex", "grok", "agy"].every(b => vi[L.NONE_KEY[b]] && en[L.NONE_KEY[b]]));
check("the popover asks for plan names, the ring after each turn does not", src.indexOf('"?goi=1"') !== -1 && /refresh\(true, true\)/.test(src));
["anthropic-api", "openai", "openrouter", "gemini", "groq", "deepseek", "ollama"].forEach(p =>
  check(p + " has no ring (no plan meter Javis can read)", L.brainOf(p, {}) === ""));

check("under 50% is green", L.level(49) === "ok");
check("50% turns amber", L.level(50) === "warn");
check("80% turns red", L.level(80) === "bad" && L.level(97) === "bad");
check("the server's own thresholds win when sent", L.level(70, 40, 65) === "bad");

const now = 1792960000;
const hm = L.resetParts(now + 3 * 3600 + 7 * 60, now);
check("3 hours 7 minutes reads as hours and minutes", hm.key === "lim.reset_hm" && hm.vars.h === 3 && hm.vars.m === 7);
check("under an hour reads as minutes", L.resetParts(now + 25 * 60, now).key === "lim.reset_m");
check("a few seconds still reads as 1 minute, not 0", L.resetParts(now + 20, now).vars.m === 1);
check("past a day: weekday and time", L.resetParts(now + 3 * 86400, now).key === "lim.reset_at");
check("no reset time or already passed: nothing", L.resetParts(0, now) === null && L.resetParts(now - 5, now) === null);

check("the ring sits right after the Effort chip, hidden until a plan brain is chosen",
  /id="effBtn"[\s\S]*?<\/button>\s*<!--[\s\S]*?-->\s*<button type="button" class="cp-limit" id="limitBtn" hidden/.test(html));
check("the popover lives next to the Effort popover", /id="effPop"[^>]*><\/div>\s*<div class="eff-pop lim-pop" id="limitPop"/.test(html));
check("plan-limit.js is loaded", /<script src="\/static\/plan-limit\.js\?v=\d+"><\/script>/.test(html));
check("the picker tells the ring which brain is in use", picker.indexOf("JavisPlanLimit.setProvider(eff.provider)") !== -1);
check("each finished turn re-reads the meters", app.indexOf("window.JavisPlanLimit.refresh()") !== -1);
check("numbers come from GET /plan-limits", src.indexOf('fetch("/plan-limits"') !== -1);
check("CSS colours the ring green, amber, red", ['[data-muc="ok"]', '[data-muc="warn"]', '[data-muc="bad"]'].every(k => css.indexOf(".cp-limit" + k) !== -1));
const keys = ["lim.title", "lim.session", "lim.week", "lim.used", "lim.reset_hm", "lim.reset_m", "lim.reset_at", "lim.fresh",
  "lim.at", "lim.none_short", "lim.none_claude", "lim.none_codex", "lim.none_grok", "lim.none_agy", "lim.het", "lim.het_short",
  "lim.het_no_reset", "lim.no_meter"];
keys.forEach(k => check("key " + k + " in vi and en", !!vi[k] && !!en[k]));
check("placeholders match between vi and en", keys.every(k => JSON.stringify((vi[k].match(/\{\w+\}/g) || []).sort()) ===
  JSON.stringify((en[k].match(/\{\w+\}/g) || []).sort())));

if (fails.length) { console.log("\nFAIL - test_vong_han_muc: " + fails.length); process.exit(1); }
console.log("\nOK - test_vong_han_muc: all pass");
