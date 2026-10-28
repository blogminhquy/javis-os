/* Chatbot v5 Channels and Stats tabs (owner, 2026-10-28; docs/dev/2026-10-chatbot-v5-spec.md sections 2, 7, 9).

       node tests/js/test_inbox_tabs.js

   inbox-stats.js builders and inbox-channels.js `jobs` run for real under node; the wiring in conversations.js, the
   channel actions and the CSS are guarded by their structure.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const CV = src("dashboard/conversations.js");
const KN = src("dashboard/inbox-channels.js");
const ST = src("dashboard/inbox-stats.js");
const CSS = src("dashboard/inbox-v5.css");
const HTML = src("dashboard/index.html");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

const win = { t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : "") };
const ctx = { window: win, document: {}, console, String, Object, Array, Number, JSON, Math, isNaN };
vm.createContext(ctx);
vm.runInContext(ST, ctx);
vm.runInContext(KN, ctx);
const S = win.JavisInboxStats, K = win.JavisInboxChannels;

// ---- 1. Stats builders ----
check("wait in words: seconds, minutes, hours, nothing yet", S.fmtWait(42.4) === "ib.st_sec#42" && S.fmtWait(150) === "ib.st_min#3" &&
  S.fmtWait(5400) === "ib.st_hour#1.5" && S.fmtWait(null) === "-");
check("change vs the period before: more A.I. answers is good, a longer wait is bad", S.delta(12, 10).text === "+20%" && S.delta(12, 10).good === true &&
  S.delta(120, 60, true).good === false && S.delta(30, 60, true).good === true);
check("no change, nothing before, or something new", S.delta(5, 5).text === "ib.st_same" && S.delta(0, 0).text === "" && S.delta(3, 0).text === "ib.st_new");
const tiles = S.tilesHtml({ now: { ai: 12, human: 3, wait_avg: 90 }, before: { ai: 10, human: 3, wait_avg: 120 }, needs_you: 4 }, (n) => "[" + n + "]");
check("four tiles: A.I. answered, you answered, average wait, waiting for you", (tiles.match(/class="st-tile/g) || []).length === 4 &&
  /ib\.st_ai<\/span><span class="st-v">12/.test(tiles) && /ib\.st_wait<\/span><span class="st-v">ib\.st_min#2/.test(tiles) && /st-v">4</.test(tiles));
check("a shorter wait shows as good news, more A.I. answers too", /st-d up">ib\.st_vs#\+20%/.test(tiles) && /st-d up">ib\.st_vs#-25%/.test(tiles));
check("'waiting for you' opens the Needs you list, by mouse or keyboard", /role="button" tabindex="0" data-go="you"/.test(tiles) &&
  /C\.goWho\(g\.dataset\.go\)/.test(ST) && /e\.key === "Enter" \|\| e\.key === " "/.test(ST));
const bars = S.barsHtml("By channel", [{ label: "<Zalo>", value: 10 }, { label: "Telegram", value: 5 }, { label: "Slack", value: 0 }], "none");
check("bars: one hue, the longest is full width, the value written at the end, labels escaped",
  /width:100%/.test(bars) && /width:50%/.test(bars) && /width:2%/.test(bars) && /st-num">10</.test(bars) && bars.indexOf("<Zalo>") < 0);
check("bars: nothing in the period says so", /ib-hint">none</.test(S.barsHtml("x", [], "none")));
check("period: the date range picker (quick ranges or days on the calendar), remembered in this browser, sent as from/to",
  /window\.JavisDateRange\.open\(rb, _range/.test(ST) && /localStorage\.setItem\(KEY/.test(ST) &&
  /\/conversations\/insights\?" \+ \(d \? "from=" \+ d\.from \+ "&to=" \+ d\.to/.test(ST) && /aria-haspopup="dialog"/.test(ST));

// ---- 2. Channels ----
check("Channels badge counts the nicks and Pages that need something", K.jobs([{ loi: "x", bot_id: "b" }, { bot_id: "" }, { bot_id: "", no_bot: true },
  { bot_id: "b" }]) === 2 && K.jobs(null) === 0);
check("one dropdown for the bot on duty, with 'No A.I. needed'; Cancel and Save only after a change",
  /value="__none"/.test(KN) && /\(changed \? '<span class="kn-unsaved">'/.test(KN) && /kn-cancel/.test(KN) && /kn-save/.test(KN));
check("a bot from another brain stays selectable, so Save never moves it silently", /if \(cur && cur !== "__none" && !seen && a\)/.test(KN));
const DUTY = KN.slice(KN.indexOf("async function duty("), KN.indexOf("function after()"));
check("Save posts the bot to the account, and the 'No bot needed' mark when there is no bot",
  /\/channels\/accounts\/" \+ encodeURIComponent\(a\.id\) \+ "\/bot"/.test(DUTY) && /\/channels\/no-bot"/.test(DUTY) && /val === "__none" \? "1" : "0"/.test(DUTY));
check("Save has Undo back to the bot before, and says when the old bot was switched off", /ib\.kn_saved_off/.test(KN) &&
  /duty\(a, before\)\.then\(after\)/.test(KN));
check("per-chat switch: role=switch with its state, disabled without a bot, POST /ai, Undo", /role="switch" aria-checked="' \+ on/.test(KN) &&
  /\(a\.bot_id \? "" : " disabled"\)/.test(KN) && /\/conversations\/" \+ id \+ "\/ai"/.test(KN) && /on \? "0" : "1"/.test(KN));
check("Allow appears when someone called the A.I. in a chat not allowed", /c\.ai_pending && !on && a\.bot_id/.test(KN));
check("'Put an A.I. on several' ticks the places without a bot, one request each, says how many worked", /\(a\.bot_id \? "" : " checked"\)/.test(KN) &&
  /for \(var i = 0; i < ids\.length; i\+\+\)/.test(KN) && /ib\.kn_bulk_done/.test(KN) && /ib\.kn_bulk_some/.test(KN));
check("the account card (record, import, edit, delete) is the same one, from conversations.js", /C\.accountCard\(a\)/.test(KN) &&
  /accountCard: function \(a\) \{ return theTK\(a\); \}/.test(CV));
check("a nick's groups and people come 20 a page, Previous / Next with 'from-to of n', search asks the server",
  /var PAGE = 20/.test(KN) && /"&offset=" \+ pg \* PAGE/.test(KN) && /if \(d\.total != null\) _total = d\.total/.test(KN) &&
  /ib\.kn_range/.test(KN) && /\(q \? "&q=" \+ encodeURIComponent\(q\) : ""\)/.test(KN) && /setTimeout\(function \(\) \{ loadChats\(_sel, 0\); \}, 300\)/.test(KN) &&
  !/limit=200/.test(KN));
check("phones: the list, then the picked nick or Page with a back button", /kn-grid\.det \.kn-tree, \.kn-grid:not\(\.det\) \.kn-pane \{ display: none; \}/.test(CSS) &&
  /_det = true; paint\(\)/.test(KN));

// ---- 3. wiring ----
check("four tabs in the owner's order: Conversations, Bot, Channels, Stats", /var TABS = \["inbox", "bot", "kenh", "thongke"\];/.test(CV) &&
  /var TAB_CU = \{ chatbot: "bot" \};/.test(CV));
check("each tab has an icon and a word", /kenh: \["ib\.tab_kenh", "plug"\]/.test(CV) && /thongke: \["ib\.tab_stats", "chart-column"\]/.test(CV));
check("the Channels and Stats tabs draw from one context (no second copy of the channel logic)",
  /if \(_tab === "kenh"\) return renderSub\(body, window\.JavisInboxChannels/.test(CV) &&
  /if \(_tab === "thongke"\) return renderSub\(body, window\.JavisInboxStats/.test(CV) &&
  ["accounts:", "reloadAccounts:", "openChat:", "openBot:", "goWho:", "addAccount:"].every((k) => CV.indexOf(k) > 0));
check("the Bot tab no longer carries the 'channels without a bot' block (it is the Channels tab now)",
  !/ht-kenh-sec|function renderKenhSec|function dsKenhRanh/.test(CV));
check("'Open chat' puts filters aside and opens that chat on the Conversations tab", /openChat: function \(id\) \{ _cho = \{\}; _chon = id;/.test(CV) &&
  /if \(_chon\) body\.querySelector\("\.ht-wrap"\)\.classList\.add\("thread-on"\)/.test(CV));
check("index.html loads both tabs before conversations.js", ["inbox-channels.js", "inbox-stats.js"].every((f) =>
  HTML.indexOf("/static/" + f) > 0 && HTML.indexOf("/static/" + f) < HTML.indexOf("/static/conversations.js")));
check("phones: the four tabs share the width, icon above the word", /\.ht-page \.ht-tabs \{ display: grid; grid-template-columns: repeat\(4, 1fr\)/.test(CSS) &&
  /\.ht-page \.ht-tab \{ display: flex; flex-direction: column;/.test(CSS));
const sizes = [...CSS.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map((m) => +m[1]);
check("CSS: no text under 16px", sizes.every((n) => n >= 16), sizes.filter((n) => n < 16).join(","));

// ---- 4. words ----
const used = new Set();
[KN, ST, CV].forEach((t) => [...t.matchAll(/"(ib\.(?:kn|st|tab)_[a-z0-9_]+)"/g)].forEach((m) => used.add(m[1])));
const miss = [...used].filter((k) => !VI[k] || !EN[k]);
check(`every ib.kn_*, ib.st_*, ib.tab_* key used (${used.size}) is in vi and en`, used.size >= 50 && !miss.length, miss.join(","));
check("Vietnamese writes A.I. with dots, English plain AI", [...used].every((k) => !/(^|[^.A-Za-z])AI([^.A-Za-z]|$)/.test(VI[k]) && EN[k].indexOf("A.I.") < 0));
check("every new sentence under 100 characters (longer ones go behind (i))", [...used].every((k) => VI[k].length <= 100 && EN[k].length <= 100),
  [...used].filter((k) => VI[k].length > 100 || EN[k].length > 100).join(","));
const dashes = [String.fromCharCode(0x2014), String.fromCharCode(0x2013)];
check("no em or en dash in the new files or strings", ![KN, ST, fs.readFileSync(__filename, "utf8"), ...[...used].map((k) => VI[k] + EN[k])]
  .some((t) => dashes.some((d) => t.indexOf(d) >= 0)));

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_inbox_tabs: tất cả pass");
