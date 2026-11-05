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
check("the background card has its own Effort chip", /data-p="__bg"[\s\S]{0,200}effChip\("__bg", bgCfg\.reasoning\)/.test(CL)
  && /data-ordpop="eff"/.test(CL));
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
check("the background picker is the composer-style list in a sheet on every screen",
  /if \(!window\.JavisModelList\) \{/.test(B) && /JavisModelList\.render\(o\)/.test(B) && !/matchMedia\("\(max-width: 600px\)"\)\.matches \|\| !window\.JavisModelList/.test(B));
check("Escape and a tap outside close the popover", /e\.key === "Escape"/.test(B) && /closest\("\.ord-chips"\)/.test(B));

// ---- 2b. pickers (0.352.0 on a phone; owner 05/11/2026: "pull up, not drop down" on every screen) ----
const SH = B.slice(B.indexOf("const shell = "), B.indexOf("el._ordClose = closePop;"));
check("every picker is a pull-up sheet, on a computer too: no popover branch left",
  /ord-sheet-back/.test(SH) && /ord-sheet-x/.test(SH) && !/phone\(\)/.test(SH) && !/MO\.place/.test(B) && !/sh\.sheet \?/.test(B));
check("the keyboard waits until the search box is tapped on a phone", /if \(!phone\(\)\) inp\.focus\(\);/.test(B) && !/\n\s*inp\.focus\(\);\n\s*\}\);/.test(B));
check("the sheet closes on its own button, the backdrop and Escape",
  /\.ord-sheet-x"\)\.onclick = \(\) => closePop\(\)/.test(B) && /closest\("\.ord-chips, \.ord-pop"\)/.test(B));
check("model list: Default first, the model in use next, the rest A-Z",
  /\[""\]\.concat\(now \? \[now\] : \[\]\)/.test(B) && /sort\(\(a, b\) => a\.localeCompare\(b\)\)/.test(B));
// Owner 05/11/2026 (approved design): the badges stand at the end of the chip row on every screen.
check("MAIN / Fallback / IN USE / BACKGROUND badges sit at the end of the chip row", /\$\{ordBadges\(p, ord\)\}/.test(CL)
  && /class="ord-badges-m"/.test(CL) && /models\.badge_bg/.test(CL) && !/\.ord-badges-m \{ display: none; \}/.test(D("console.css")));

check("a computer gets a narrower sheet centered at the bottom", /@media \(min-width: 601px\) \{\s*\.ord-sheet \{ left: 50%;/.test(D("console.css")));
// 05/11/2026: an account's ⋯ opens a sheet in the Tasks page's style instead of unfolding buttons inside the card.
check("a key's or an account's ⋯ opens a sheet, nothing unfolds inside the card",
  !/class="ord-menu"/.test(CL) && !/class="ord-addbox" data-acct-box/.test(CL) && /data-acct-menu/.test(CL)
  && (B.match(/menuSheet\(btn, name, \[/g) || []).length === 2 && /\.ord-mi \{/.test(D("console.css")));
check("a new key, a new name and a replacement key are typed inside a sheet",
  /const addKeySheet = /.test(B) && /models\.acct_rename/.test(B) && /formSheet\(btn,\s*t\("models\.acct_rekey"\)/.test(B));
check("remove and Disconnect ask in a sheet, not the browser's confirm box",
  /const confirmSheet = /.test(B) && !/window\.confirm/.test(B.slice(0, B.indexOf("async function disconnectCard"))) && /disconnectCard\(el, pid, btn, p\.label, true\)/.test(B));
// ---- 2e. approved design (owner 05/11/2026): logos, the button row, background work, Fast mode, the connect sheet ----
check("each card shows its provider's own logo (provider-logos.js, loaded before console.js)",
  /const logoTile = /.test(CL) && /JavisProviderLogos/.test(CL)
  && HTML.indexOf("/static/provider-logos.js") > 0 && HTML.indexOf("/static/provider-logos.js") < HTML.indexOf("/static/console.js"));
check("a card in the order has the button row: background work, check, add, Disconnect",
  /const ordActs = /.test(CL) && /data-setbg=/.test(CL) && /data-disccard=/.test(CL) && /data-addacc=/.test(CL) && /data-addkey=/.test(CL));
check("Use for background work saves the card as the background model",
  /const setBg = \(pid\) => save\(\{ auxiliary: \{ provider: pid/.test(B));
check("the Effort sheet carries the composer's Fast mode bolt, one app-wide setting",
  /fast: \{ supported: fn\.supported, on: c\.fast/.test(B) && /saveSetting\("model", \{ fast: on \}\)/.test(B)
  && /javis:fast-changed/.test(B) && /javis:fast-changed/.test(D("model-picker.js")));
check("Connect another provider opens a sheet and brings the picked card into view",
  /menuSheet\(more, t\("models\.connect_more"\)/.test(B) && /data-offp=/.test(CL) && /ord-flash/.test(B));
check("the Swap button sits in the middle of the gap", /\.ord-swap-row \{ display: flex; align-items: center; justify-content: center; margin: 4px 0; \}/.test(D("console.css")));
check("Advanced API key: a list of gateways, added and edited in a sheet, never named Anthropic Compatible on screen",
  /data-dnd="adv:/.test(CL) && /const advSheet = /.test(B) && /\/provider\/anthropic-compat\/connect/.test(B)
  && !/Anthropic Compatible/.test(VI["models.adv_note"] + VI["models.adv_add_note"]));
check("an extra Antigravity account signs in through a command for the Terminal page",
  /const agySheet = /.test(B) && /r\.terminal/.test(B) && /JavisNav\.go\("terminal"\)/.test(B));
// ---- 2d. a card's ⋯ and Disconnect for every card (owner 05/11/2026) ----
check("every card in the order has a ⋯ button", /data-cmenu="\$\{esc\(p\.id\)\}"/.test(CL) && (CL.match(/\$\{cardMenuBtn\(p, ord\)\}/g) || []).length === 2);
check("the card sheet holds model, effort, MAIN, move, add, check and Disconnect",
  ["models.change_model", "eff.head", "models.make_main", "models.move_up", "models.move_down", "models.acct_add", "models.pacct_add",
   "qs.recheck", "models.disconnect_full"].every(k => B.indexOf('t("' + k + '")') > 0));
const DC = JS.slice(JS.indexOf("async function disconnectCard("), JS.indexOf("async function refreshClaudeCard"));
check("Disconnect reaches every kind of card", /"antigravity-cli": "\/antigravity\/logout"/.test(JS) && /"grok-cli": "\/grok\/logout"/.test(JS)
  && /"openai-oauth": "\/oauth\/openai\/disconnect"/.test(JS) && /"anthropic-cli": "\/claude\/logout"/.test(JS)
  && /clear_key: pid/.test(DC) && /\/ollama-local\/endpoint/.test(DC) && /window\.confirm\(q\)/.test(DC));
check("the Antigravity card has Disconnect, and Connect again once switched off",
  /data-agydisc="1"/.test(CL) && /data-agyon="1"/.test(CL) && /\/antigravity\/reconnect/.test(CL));
check("a card the router skips for quota says until when, with Use again now",
  /R\.limited \|\| \{\}/.test(CL) && /data-retry=/.test(CL) && /"\/routing\/retry"/.test(B));

// ---- 2c. several accounts on a plan card (0.353.0) ----
check("ChatGPT, Grok and Claude cards list their accounts", /const planAccts = \(p, ord\) =>/.test(CL)
  && (CL.match(/planAccts\(p, ord\)/g) || []).length >= 3);
check("Claude on an API key shows no plan account list", /p\.id === "anthropic-cli" && p\.auth_mode === "api_key"/.test(CL));
check("adding an account shows the gentle warning and asks for a sign-in link",
  /models\.pacct_warn/.test(B) && /models\.pacct_warn2/.test(B) && /data-pacct-go/.test(B));
check("sign-in: link and code, a pasted code for Claude, polling for ChatGPT and Grok",
  /\/plan-accounts\/login-start/.test(B) && /\/plan-accounts\/login-code/.test(B) && /\/plan-accounts\/login-poll/.test(B)
  && /setTimeout\(tick, 3000\)/.test(B));
check("account 1 can be turned off but not removed or re-signed here",
  /if \(!a\.main\) rows\.push\(\{ ic: "log-in", label: t\("models\.pacct_relogin"\)/.test(B) && /a\.main \? \[\] : \[\{ ic: "trash-2"/.test(B));
check("plan accounts reorder by drag and by Move up / Move down in the sheet", /key\.indexOf\("pacct:"\) === 0/.test(B)
  && /saveAcc\(pid, MO\.move\(items\(pid\), idx\(\), idx\(\) - 1\)\)/.test(B));
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
