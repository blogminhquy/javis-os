/* Models page usage order (0.351.0, docs/dev/2026-10-model-routing-spec.md 2.1-2.4).

       node tests/js/test_models_order.js

   The pure parts of dashboard/models-order.js (moving a card, the Swap button), and the wiring in console.js that the
   owner settled on the approved mockup: only signed-in cards stand in the order, the top one is MAIN, each card carries
   its own model and Effort chips, API keys are a numbered list, the background model sits under the order with its
   own Effort chip, and the providers still to connect wait behind one button. */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const MO = require(path.join(ROOT, "dashboard", "models-order.js"));
const JS = D("console.js");
const HTML = D("index.html");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const EN = JSON.parse(D(path.join("i18n", "en.json")));
const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ---- 1. pure parts ----
const L = ["claude", "codex", "groq", "agy"];
check("drag the last card to the top makes it MAIN", eq(MO.move(L, 3, 0), ["agy", "claude", "codex", "groq"]));
check("drag MAIN below the next card", eq(MO.move(L, 0, 1), ["codex", "claude", "groq", "agy"]));
check("drag to the end", eq(MO.move(L, 0, 3), ["codex", "groq", "agy", "claude"]));
check("a drop on the same place changes nothing", eq(MO.move(L, 2, 2), L));
check("the list given is never changed in place", eq(L, ["claude", "codex", "groq", "agy"]));
check("Swap between card 1 and 2", eq(MO.swapAt(L, 1), ["codex", "claude", "groq", "agy"]));
check("Swap out of range changes nothing", eq(MO.swapAt(L, 0), L) && eq(MO.swapAt(L, 9), L));
check("an account moves up one place", eq(MO.move(["a", "b", "c"], 2, 1), ["a", "c", "b"]));
check("an account moves down one place", eq(MO.move(["a", "b", "c"], 0, 1), ["b", "a", "c"]));

// ---- 2. console.js wiring ----
const i = JS.indexOf("async function renderModelsCloudTab(el)");
const CL = JS.slice(i, JS.indexOf("\n  async function", i + 10));
const B = JS.slice(JS.indexOf("function bindOrderCards(el, c)"), JS.indexOf("async function refreshClaudeCard"));
check("found the cloud tab and its bindings", i > 0 && B.length > 1000);
check("the order comes from the server's routing view", /const R = m\.routing \|\| \{\};/.test(CL));
check("a Claude card the CLI says is signed out leaves the order", /claudeOut/.test(CL) && /id === "anthropic-cli" && claudeOut/.test(CL));
check("the top card is MAIN, the others are numbered fallbacks", /ord\.idx === 0[\s\S]{0,80}MAIN/.test(CL) && /models\.ord_backup/.test(CL));
check("a fallback chat runs on right now is marked in use", /R\.chat_in_use === p\.id/.test(CL) && /models\.ord_live/.test(CL));
check("each card has a model chip and an Effort chip", /data-ordpop="model"/.test(CL) && /data-ordpop="eff"/.test(CL));
check("a Swap button stands between two cards", /\(i \? swapRow\(i\) : ""\)/.test(CL));
check("API cards with several keys get the numbered key list", /multiKey\.indexOf\(p\.id\) >= 0 \? acctList\(p\)/.test(CL));
check("unconnected providers hide behind one button", /id="ordMore"/.test(CL) && /id="ordOff" \$\{showOff \? "" : "hidden"\}/.test(CL));
// 0.406.0 (owner, 2026-10-29): a first visit with nothing signed in opens on the connect list, at the top.
check("nothing signed in: the connect list comes first and open, until the owner folds or opens it",
  /const showOff = ui\.set \? ui\.showOff : !connList\.length;/.test(CL) && /el\.innerHTML = `\s*\$\{connList\.length \? "" : moreHtml\}/.test(CL) &&
  /\$\{connList\.length \? moreHtml : ""\}`;/.test(CL) && /el\._ordUi\.set = true;/.test(B));
// 0.406.0 (owner, 2026-10-29: "Off and Change model are misaligned"): the button matches the Effort chip, and a
// section title keeps its (i) next to the name on a phone instead of a squeezed second column.
check("Change model has the Effort chip's height and no top margin", /\.aux-card \.aux-now-act \.gcard-btn \{ margin-top: 0; min-height: 36px;/.test(D("console.css")));
check("section titles wrap; on a phone the (i) follows the name and the sub-label takes its own line",
  /flex-wrap: wrap; row-gap: 2px;/.test(D("console.css")) && /\.cview-section h3 > \.info-i \{ order: 1; margin-left: 0; \}/.test(D("console.css")) &&
  /\.cview-section h3 > span \{ order: 2; flex-basis: 100%; \}/.test(D("console.css")));
check("nothing signed in: no empty order section, the note sits above the list", /\$\{connList\.length \? `<div class="cview-section">\s*<h3>◆ \$\{esc\(t\("models\.h_order"\)\)\}/.test(CL) &&
  CL.indexOf('esc(t("models.ord_empty"))') < CL.indexOf('id="ordMore"'));
check("the background card sits under the order", CL.indexOf("models.h_order") < CL.indexOf("models.h_aux"));
check("the background card has its own Effort chip", /data-p="__bg"[\s\S]{0,200}data-ordpop="eff"/.test(CL));
check("no 'back to MAIN' button on the background card", !/auxReset/.test(CL));
check("the old Main Model box and the global effort row are gone", !/id="mdChange"/.test(CL) && !/data-reason=/.test(CL));
check("the background notice says which card runs while the model rests", /bgUse\.step !== "background"/.test(CL) && /models\.bg_using/.test(CL));

check("drag and Swap save the whole order", /save\(\{ order: MO\.move\(c\.order, from, to\) \}\)/.test(B) && /save\(\{ order: MO\.swapAt\(c\.order/.test(B));
check("a card's model saves to its profile", /save\(\{ profile: \{ provider: pid, model: mid \} \}\)/.test(B));
check("a card's effort saves to its profile, the background's to auxiliary",
  /\{ auxiliary: \{ reasoning: v \} \}/.test(B) && /\{ profile: \{ provider: pid, reasoning: v \} \}/.test(B));
check("keys save as one list (order, on/off, new key)", /save\(\{ accounts: \{ provider: pid, items: list, removed: removed \|\| \[\] \} \}\)/.test(B));
check("removing a plan account names it, a stale page never drops one (0.355.0)",
  /const gone = l\.splice\(i, 1\)\[0\];\s*saveAcc\(pid, l, \[gone\.id\]\);/.test(B));
check("removing the last key warns that the provider leaves the order", /models\.acct_rm_last_q/.test(B));
check("the background picker lists signed-in providers only", /openModelPicker\(c\.connList,/.test(B) && /connectedOnly: true/.test(B));
check("on a phone the background picker is the composer-style list", /matchMedia\("\(max-width: 600px\)"\)/.test(B) && /JavisModelList\.render\(o\)/.test(B));
check("every popover is placed (opens upward, clamped)", /MO\.place\(pop\)/.test(B));
check("Escape and a tap outside close the popover", /e\.key === "Escape"/.test(B) && /closest\("\.ord-chips"\)/.test(B));

// ---- 2b. phone pickers (0.352.0, owner's screenshots 27/10) ----
check("a phone gets a bottom sheet, not a popover over the card",
  /const phone = \(\) => window\.matchMedia\("\(max-width: 600px\)"\)\.matches;/.test(B) && /ord-sheet-back/.test(B) && /ord-sheet-x/.test(B));
check("the keyboard waits until the search box is tapped", /if \(!sh\.sheet\) inp\.focus\(\);/.test(B) && !/\n\s*inp\.focus\(\);\n\s*\}\);/.test(B));
check("the sheet closes on its own button, the backdrop and Escape",
  /\.ord-sheet-x"\)\.onclick = \(\) => closePop\(\)/.test(B) && /closest\("\.ord-chips, \.ord-pop"\)/.test(B));
check("model list: Default first, the model in use next, the rest A-Z",
  /\[""\]\.concat\(now \? \[now\] : \[\]\)/.test(B) && /sort\(\(a, b\) => a\.localeCompare\(b\)\)/.test(B));
check("on a phone the MAIN / Fallback badge moves to the chip row", /ordBadges\(p, ord, "ord-badges-m"\)/.test(CL)
  && /\.ord-head \.ord-badges \{ display: none; \}/.test(D("console.css")));

check("the card holding an open popover is lifted above the next card (each card is its own layer)",
  /raised\.classList\.add\("ord-raise"\)/.test(B) && /openPop\.raised\.classList\.remove\("ord-raise"\)/.test(B)
  && /\.prov-card\.ord-raise, \.gcard\.ord-raise \{ position: relative; z-index: 70; \}/.test(D("console.css")));

// ---- 2c. several accounts on a plan card (0.353.0) ----
check("ChatGPT, Grok and Claude cards list their accounts", /const planAccts = \(p, ord\) =>/.test(CL)
  && (CL.match(/planAccts\(p, ord\)/g) || []).length >= 3);
check("Claude on an API key shows no plan account list", /p\.id === "anthropic-cli" && p\.auth_mode === "api_key"/.test(CL));
check("adding an account shows the gentle warning and asks for a sign-in link",
  /models\.pacct_warn/.test(CL) && /models\.pacct_warn2/.test(CL) && /data-pacct-go/.test(CL));
check("sign-in: link and code, a pasted code for Claude, polling for ChatGPT and Grok",
  /\/plan-accounts\/login-start/.test(B) && /\/plan-accounts\/login-code/.test(B) && /\/plan-accounts\/login-poll/.test(B)
  && /setTimeout\(tick, 3000\)/.test(B));
check("account 1 can be turned off but not removed or re-signed here", /\$\{a\.main \? "" : `<button type="button" class="gcard-btn ghost" data-pacct-act="relogin">/.test(CL));
check("plan accounts reorder by drag and arrows", /key\.indexOf\("pacct:"\) === 0/.test(B) && /data-pacct-move/.test(B));
check("cancel stops a sign-in that never finished", /\/plan-accounts\/login-cancel/.test(B));
const warn = (VI["models.pacct_warn"] || "") + " " + (VI["models.pacct_warn2"] || "");
check("the warning is gentle: a risk, no reported case, tell the developer",
  /nguy cơ/.test(warn) && /chưa ghi nhận/.test(warn) && /nhà phát triển/.test(warn));

// ---- 3. loading and words ----
check("models-order.js loads before console.js",
  HTML.indexOf("/static/models-order.js") > 0 && HTML.indexOf("/static/models-order.js") < HTML.indexOf("/static/console.js"));
const keys = [...new Set(((CL + B).match(/t\("(models\.(?:ord|acct|pacct|bg|h_order|order)[\w.]*)"/g) || []).map((s) => s.slice(3, -1)))];
check("the new words are found", keys.length >= 20, String(keys.length));
const noVi = keys.filter((k) => !VI[k]), noEn = keys.filter((k) => !EN[k]);
check("every new key is in vi.json", noVi.length === 0, noVi.join(", "));
check("every new key is in en.json", noEn.length === 0, noEn.join(", "));
const dash = Object.entries(VI).concat(Object.entries(EN)).filter(([k, v]) => /^models\./.test(k) && /[–—]/.test(v));
check("no long dash in the Models page words", dash.length === 0, dash.map((x) => x[0]).join(", "));

console.log();
if (fails.length) { console.log("ĐỎ " + fails.length + " mục"); process.exit(1); }
console.log("Tất cả xanh.");
