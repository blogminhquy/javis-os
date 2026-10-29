/* Chatbot v5 Conversations tab (owner, 2026-10-28; docs/dev/2026-10-chatbot-v5-spec.md section 6): the channel picker,
   the quick "who" filters, the active-filter chips, the Info panel and the three-column layout.

       node tests/js/test_inbox_v5.js

   inbox-v5.js runs for real under node; conversations.js and inbox-v5.css are guarded by their structure.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const V5SRC = src("dashboard/inbox-v5.js");
const CV = src("dashboard/conversations.js");
const CB = src("dashboard/chatbots.js");
const CSS = src("dashboard/inbox-v5.css");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

const win = { t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : "") };
const ctx = { window: win, console, String, Object, Array, Number, JSON };
vm.createContext(ctx);
vm.runInContext(V5SRC, ctx);
const V = win.JavisInboxV5;
const I = (n) => "[" + n + "]";
const L = (ch) => "<" + ch + ">";

// ---- 1. the "who" dropdown (0.397.0: one button and a menu instead of four chips that wrapped) ----
const C = { you: 3, ai: 9, owner: 2, log: 6 };
const wb = V.whoButtonHtml("you", C, I);
check("the button shows the current view, its count and a chevron", /ib-dot w-you"><\/span><span class="ib-who-t">ib\.wq_you<\/span><span class="ib-qn you">3<\/span>\[chevron-down\]/.test(wb));
check("'All' counts every chat, logged ones included", /\[inbox\]<span class="ib-who-t">ib\.wq_all<\/span><span class="ib-qn">20/.test(V.whoButtonHtml("", C, I)));
check("an unknown view falls back to All", /ib\.wq_all/.test(V.whoButtonHtml("x", C, I)));
check("no counts yet (first paint): no numbers", V.whoButtonHtml("", null, I).indexOf("ib-qn") < 0 && V.whoMenuHtml("", null, I).indexOf("ib-qn") < 0);
const wm = V.whoMenuHtml("ai", C, I);
check("the menu: Needs you, A.I. handles, You handle, All, in that order", /data-who="you"[\s\S]*data-who="ai"[\s\S]*data-who="owner"[\s\S]*data-who=""/.test(wm));
check("each option says what it means and how many", ["you", "ai", "owner", "all"].every((w) => wm.indexOf("ib.wq_" + w + "_d") > 0) &&
  /ib\.wq_owner<\/b><small>ib\.wq_owner_d<\/small><\/span><span class="ib-qn">2/.test(wm));
check("the current option is checked, the others not", /class="ib-wm-o on" role="menuitemradio" aria-checked="true" data-who="ai"/.test(wm) &&
  (wm.match(/aria-checked="false"/g) || []).length === 3 && /\[check\]/.test(wm));

// ---- 2. channel picker ----
const ACC = [
  { account_key: "zalo:1", channel: "zalo", label: "Zalo OA Cô Ba", bot_name: "CSKH" },
  { account_key: "telegram:a", channel: "telegram", label: "Nước mắm <Cô Ba>", bot_name: "" },
  { account_key: "telegram:b", channel: "telegram", label: "Hỗ trợ đơn", bot_name: "Trực đơn" },
];
check("summary: nothing ticked = every channel together", V.pickerSummary(ACC, []).title === "ib.pk_all" && V.pickerSummary(ACC, []).sub === "ib.pk_merge#3");
check("summary: one ticked = its name", V.pickerSummary(ACC, ["zalo:1"]).title === "Zalo OA Cô Ba" && V.pickerSummary(ACC, ["zalo:1"]).one.channel === "zalo");
const two = V.pickerSummary(ACC, ["zalo:1", "telegram:b"]);
check("summary: several = how many, their names below, their channels for the logo stack", two.title === "ib.pk_n#2" &&
  two.sub === "Zalo OA Cô Ba, Hỗ trợ đơn" && JSON.stringify(two.channels) === '["zalo","telegram"]');
const pk = V.pickerHtml(ACC, ["telegram:a"], { "telegram:a": 4, "zalo:1": 1 }, "", L, (c) => "N:" + c, I);
check("picker: search box, 'All channels' with the total 'Needs you', then each channel with its real logo",
  /class="ib-pk-q"/.test(pk) && /ib-pk-all"> ?<span class="ib-pk-logo">\[layers\]/.test(pk.replace(' checked', '')) && /<span class="ib-cnt">5<\/span>/.test(pk) &&
  /<zalo><span>N:zalo<\/span>/.test(pk) && /<telegram><span>N:telegram<\/span>/.test(pk));
check("each nick or Page has a checkbox, its bot (or 'no A.I. yet') and its own 'Needs you' count",
  /data-k="telegram:a" checked>/.test(pk) && /data-k="zalo:1">/.test(pk) && /ib\.pk_ai#CSKH/.test(pk) && /ib\.pk_no_ai/.test(pk) &&
  /data-k="telegram:a" checked><span class="ib-pk-logo"><telegram><\/span><span class="ib-pk-t"><b>Nước mắm &lt;Cô Ba&gt;/.test(pk));
check("a channel with some accounts ticked shows half-ticked; 'All' is unticked while something is picked",
  /data-ch="telegram" data-half="1"/.test(pk) && !/ib-pk-all" checked/.test(pk));
check("footer: Manage channels, Clear (only when something is picked) and Done with the count",
  /ib-pk-manage/.test(pk) && /ib-pk-clear/.test(pk) && /ib\.pk_done \(1\)/.test(pk) && V.pickerHtml(ACC, [], {}, "", L, null, I).indexOf("ib-pk-clear") < 0);
const found = V.pickerHtml(ACC, [], {}, "trực", L, null, I);
check("the search matches a nick's name or its bot's, and hides channels with no match",
  /telegram:b/.test(found) && !/telegram:a/.test(found) && !/zalo:1/.test(found) && !/data-ch="zalo"/.test(found));

// ---- 3. Filter menu and chips ----
const cats = V.filterCats({ tagsAny: ["1", "2"], bot: "b", when: { preset: "d7" }, lastBy: "ai", pinned: "1" });
check("Filter menu categories, with how many are on in each", cats.map((c) => c.id).join() === "time,tagsAny,tagsNone,type,bot,status,last,contact" &&
  cats[0].n === 1 && cats[1].n === 2 && cats[4].n === 1 && cats[2].n === 0 && cats[6].n === 1 && cats[7].n === 1);
const tc = V.activeChips({ when: { preset: "d30" }, lastBy: "customer", pinned: "1" }, [], []);
check("chips for time, last message by, pinned", tc.map((c) => c.k).join() === "when,lastBy,pinned");
const chips = V.activeChips({ type: "group", bot: "-", status: "unread", contact: "1" }, [], []);
check("chips for the active filters, each removable by its key", chips.map((c) => c.k).join() === "type,bot,status,contact" &&
  chips[1].text === "ib.fc_nobot" && chips[2].text === "ib.fc_st_unread");
check("a bot chip names the bot", V.activeChips({ bot: "b1" }, [], [{ id: "b1", name: "Trực đơn" }])[0].text === "ib.fc_bot#Trực đơn");

// ---- 4. conversations.js: layout, Info panel ----
check("three columns: list | chat | Info", /<div class="ht-listcol">[\s\S]*<div class="ht-thread">[\s\S]*<div class="ht-info" hidden><\/div>/.test(CV));
check("rows: coloured edge by who, avatar with the channel logo, 'A.I.:' or 'You:' before the last message",
  /'<button type="button" class="ht-item w-' \+ who/.test(CV) && /'<span class="ib-kl">' \+ logoKenh\(c\.channel, "21px"\)/.test(CV) &&
  /c\.last_sender_type === "ai" \? window\.t\("ib\.pre_ai"\)/.test(CV));
check("rows name the nick or Page only when several are in view", /var many = _accs\.length !== 1;/.test(CV));
check("Info stays closed until asked (owner, 2026-10-29), the choice kept in this browser on wide screens only",
  /function infoOpen\(\) \{ return narrow\(\) \? _infoN : _info; \}/.test(CV) && /localStorage\.getItem\(INFO_KEY\) === "1"/.test(CV) &&
  /if \(narrow\(\)\) _infoN = !!on;/.test(CV) && /localStorage\.setItem\(INFO_KEY/.test(CV) && /max-width: 1200px/.test(CV));
const PI = CV.slice(CV.indexOf("  function paintInfo() {"), CV.indexOf("  async function saveNote("));
check("Info: customer, contact (private chats), tags, note, A.I. in this chat, channel", /ib-kh/.test(PI) && /c\.chat_type !== "group" \|\| c\.contact/.test(PI) &&
  /class="ht-tagrow"/.test(PI) && /class="ib-notebox"/.test(PI) && /ib\.i_ai/.test(PI) && /ib\.i_channel/.test(PI));
check("Info 'Who replies' offers off and the three modes; 'In groups, speaks up when' only for an allowed group",
  /\[\["off", t\("ib\.i_off"\)\], \["ai", t\("ib\.m_ai"\)\], \["draft", t\("ib\.m_draft"\)\], \["human", t\("ib\.m_human"\)\]\]/.test(PI) &&
  /c\.chat_type === "group" && c\.ai_allowed \? sel\("when"/.test(PI));
check("bot-wide settings say so once, and go through the bot's own update route", /ib\.i_botwide/.test(PI) &&
  /api\("\/chatbots\/" \+ encodeURIComponent\(botId\) \+ "\/update"/.test(CV));
check("the note is saved when the box loses focus, and typing survives the 5-second redraw", /note\.onblur = function \(\) \{ saveNote\(c\.id\); \};/.test(PI) &&
  /_noteEdit && _noteEdit\.id === c\.id \? _noteEdit\.text/.test(PI) && /\/note", \{ method: "POST", body: fd\(\{ note: text \}\) \}/.test(CV));
check("'Open the settings of bot X' asks the Bot tab to open that bot, which says so when it lives in another brain",
  /javis:chatbot-open", \{ detail: \{ bot_id: c\.bot_id \} \}/.test(CV) && /addEventListener\("javis:chatbot-open"/.test(CB) && /ib\.bot_other_brain/.test(CB));
check("every change from the chat or Info shows a toast; Undo where it can be put back", /function toast\(text, undo\)/.test(CV) &&
  /ib\.undo/.test(CV) && /setTimeout\(function \(\) \{ if \(t\.parentNode\) t\.parentNode\.removeChild\(t\); \}, 6000\)/.test(CV));
check("CANARY: no robot icon in the inbox (owner)", !/ic\("bot"\)/.test(CV) && !/I\("bot"\)/.test(V5SRC));

// ---- 5. CSS ----
check("CSS: Info is a third column on wide screens and slides over the chat below 1200px, inside the page box",
  /\.ht-info \{ width: 320px; flex: none;/.test(CSS) && /@media \(max-width: 1200px\) \{\s*\.ib-v5 \.ht-info \{ position: absolute;/.test(CSS));
check("CSS: the four who colours have light-theme values too", ["--ib-ai:", "--ib-owner:", "--ib-you:", "--ib-log:"].every((v) =>
  CSS.split(v).length === 3) && /:root\[data-theme="light"\]/.test(CSS));
const sizes = [...CSS.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map((m) => +m[1]);
check("CSS: no text under 16px (owner's rule)", sizes.length > 10 && sizes.every((n) => n >= 16), sizes.filter((n) => n < 16).join(","));

// ---- 6. words ----
const ib = Object.keys(VI).filter((k) => k.startsWith("ib."));
check("every ib.* key has an English twin, and the other way round", ib.every((k) => EN[k]) && Object.keys(EN).filter((k) => k.startsWith("ib.")).every((k) => VI[k]));
check("Vietnamese calls the user 'bạn', never 'anh' (owner, 2026-10-28)", ib.every((k) => !/(^|\s)anh(\s|$)/i.test(VI[k])),
  ib.filter((k) => /(^|\s)anh(\s|$)/i.test(VI[k])).join(","));
check("English keeps 'AI' without dots", Object.keys(EN).filter((k) => k.startsWith("ib.")).every((k) => EN[k].indexOf("A.I.") < 0));
check("who names as the owner wrote them: the long ones in sentences, the short ones in the dropdown", VI["ib.who_you"] === "Cần bạn" &&
  VI["ib.who_ai"] === "A.I. đang xử lý" && VI["ib.who_owner"] === "Bạn đang xử lý" && VI["ib.wq_you"] === "Cần bạn" &&
  VI["ib.wq_ai"] === "A.I. lo" && VI["ib.wq_owner"] === "Bạn lo" && VI["ib.wq_all"] === "Tất cả");
const dashes = [String.fromCharCode(0x2014), String.fromCharCode(0x2013)];
check("no em or en dash in the module, this test or the ib.* strings", ![V5SRC, CSS, fs.readFileSync(__filename, "utf8"), ...ib.map((k) => VI[k] + EN[k])]
  .some((t) => dashes.some((d) => t.indexOf(d) >= 0)));

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_inbox_v5: tất cả pass");
