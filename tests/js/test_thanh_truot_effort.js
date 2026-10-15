/* Effort slider (0.153.0): 6 stops, English labels, locked when the model carries its own level.

       node tests/js/test_thanh_truot_effort.js
*/
const fs = require("fs");
const path = require("path");
const S = require("../../dashboard/effort-slider.js");
const ROOT = path.join(__dirname, "../..");
const picker = fs.readFileSync(path.join(ROOT, "dashboard/model-picker.js"), "utf8");
const vi = require("../../dashboard/i18n/vi.json"), en = require("../../dashboard/i18n/en.json");
let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

check("6 stops in the server's value order", JSON.stringify(S.LEVELS) === JSON.stringify(["off", "low", "medium", "high", "xhigh", "ultra"]));
check("position 0 -> off, 1 -> ultra", S.levelFromRatio(0) === "off" && S.levelFromRatio(1) === "ultra");
check("a position in between rounds to the nearest stop", S.levelFromRatio(0.41) === "medium" && S.levelFromRatio(0.49) === "medium");
check("positions outside the track are clamped", S.levelFromRatio(-3) === "off" && S.levelFromRatio(9) === "ultra");
check("ratioFromLevel is the inverse, unknown levels map to 0", S.ratioFromLevel("medium") === 0.4 && S.ratioFromLevel("unknown") === 0);
check("an Antigravity name ending in -high is a locked model", S.isLocked("antigravity-cli", "gemini-3.8-flash-high") === true);
check("an Antigravity name without a level suffix is not locked", S.isLocked("antigravity-cli", "claude-sonnet-4-6") === false);
check("other providers are never locked", S.isLocked("openai-oauth", "gpt-6.1-sol-high") === false);
const labels = { off: "Off", low: "Light", medium: "Medium", high: "High", xhigh: "Extra", ultra: "Ultra" };
Object.keys(labels).forEach(k => check("label " + k + " = " + labels[k] + " in both vi and en", vi["eff." + k] === labels[k] && en["eff." + k] === labels[k]));
check("model-picker.js keeps all 6 quoted values", ["off", "low", "medium", "high", "xhigh", "ultra"].every(v => picker.indexOf('"' + v + '"') !== -1));
check("the model chip no longer says 'Effort:'", picker.indexOf('"Effort: "') === -1 && picker.indexOf("mb-eff-row") === -1);
check("outside click: the model picker closes even for clicks in the button row (+, mic, send)", picker.indexOf('e.target.closest("#modelBar")') === -1);
const srcSlider = fs.readFileSync(path.join(ROOT, "dashboard/effort-slider.js"), "utf8");
check("the slider has role=slider and arrow keys", srcSlider.indexOf('"slider"') !== -1 && srcSlider.indexOf("ArrowRight") !== -1);
check("respects reduced motion", srcSlider.indexOf("prefers-reduced-motion") !== -1);
check("no Vietnamese in effort-slider.js run code", !/[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]/i.test(srcSlider.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "")));

if (fails.length) { console.log("\nFAIL - test_thanh_truot_effort: " + fails.length); process.exit(1); }
console.log("\nOK - test_thanh_truot_effort: all pass");
