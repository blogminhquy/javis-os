/* The inbox's quick row: All / Messages / Comments, and Has phone (owner, 2026-11-24: "Làm cho anh phần lọc tin nhắn,
   lọc bình luận, lọc số điện thoại riêng nhé", after a Facebook Page showed comment threads and Messenger chats mixed in
   one list).

       node tests/js/test_inbox_quick_filters.js

   inbox-v5.js and conversations-filters.js run for real under node; conversations.js and inbox-compact.css are guarded
   by their structure. Guarded:
     1. The row's HTML: the three choices in order, the pressed one, the server's numbers (none before the first answer),
        Has phone as the Lucide phone icon with its words for screen readers and the tooltip.
     2. conversations.js: the row sits right under "who" and the channel picker, a tap saves and reloads, the 5-second
        refresh redraws it only when it changed and keeps the focus, the counts come from the server, and nothing in it
        branches on a channel id (the server decides what a comment thread is).
     3. CSS: one low row as tall as the row above, the phone's words only in a wide column, theme colours only.
     4. Words: vi and en for every key.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const V5SRC = src("dashboard/inbox-v5.js");
const MOD = src("dashboard/conversations-filters.js");
const CV = src("dashboard/conversations.js");
const CSS = src("dashboard/inbox-compact.css");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

const win = { t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : ""), localStorage: { getItem: () => null, setItem() {} } };
const ctx = { window: win, console, encodeURIComponent, String, Object, Array, Number, JSON };
vm.createContext(ctx);
vm.runInContext(MOD, ctx);
vm.runInContext(V5SRC, ctx);
const V = win.JavisInboxV5;
const F = win.JavisConvFilters;
const I = (n) => "[" + n + "]";

// ---- 1. the row's HTML ----
check("inbox-v5 exposes quickRowHtml", typeof V.quickRowHtml === "function");
const first = V.quickRowHtml(F.emptyState(), null, I);
check("three choices in order, All pressed by default", /data-kind="" aria-pressed="true"[\s\S]*data-kind="message" aria-pressed="false"[\s\S]*data-kind="comment" aria-pressed="false"/.test(first) &&
  /class="ib-kopt on" data-kind=""/.test(first) && (first.match(/class="ib-kopt/g) || []).length === 3, first);
check("the choices form one labelled group", /<span class="ib-kseg" role="group" aria-label="ib\.k_aria">/.test(first));
check("before the first answer no number is shown", first.indexOf("ib-kn") < 0);
check("Has phone: an off toggle with the phone icon, its words in the button and its tooltip",
  /<button type="button" class="ib-kphone" aria-pressed="false" title="ib\.k_phone">\[phone\]<span class="ib-kt">ib\.k_phone<\/span><\/button>/.test(first), first);
const on = V.quickRowHtml({ kind: "comment", phone: "1" }, { message: 12, comment: 7, phone: 3 }, I);
check("the picked kind and Has phone are pressed", /class="ib-kopt on" data-kind="comment" aria-pressed="true"/.test(on) &&
  /class="ib-kopt" data-kind="" aria-pressed="false"/.test(on) && /class="ib-kphone on" aria-pressed="true"/.test(on), on);
check("numbers from the server on Messages, Comments and Has phone; All has none",
  /data-kind="message"[^>]*><span class="ib-kt">ib\.k_msg<\/span><span class="ib-kn">12<\/span>/.test(on) &&
  /data-kind="comment"[^>]*><span class="ib-kt">ib\.k_cmt<\/span><span class="ib-kn">7<\/span>/.test(on) &&
  /ib\.k_phone<\/span><span class="ib-kn">3<\/span><\/button>$/.test(on) &&
  /data-kind=""[^>]*><span class="ib-kt">ib\.k_all<\/span><\/button>/.test(on), on);
const odd = V.quickRowHtml({ kind: "<x>" }, { message: "<b>", comment: null, phone: undefined }, I);
check("an unknown kind presses All; a number that is not one draws 0, never markup",
  /class="ib-kopt on" data-kind=""/.test(odd) && odd.indexOf("<b>") < 0 && odd.indexOf("<x>") < 0 && (odd.match(/<span class="ib-kn">0<\/span>/g) || []).length === 3, odd);
check("no emoji, only the Lucide icon", !/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/u.test(on));

// ---- 2. conversations.js ----
const head = CV.slice(CV.indexOf('<div class="ib-lhead">'), CV.indexOf('<div class="ht-sdt"'));
check("the row sits right under the who dropdown and the channel picker, above the chips",
  /class="ib-lrow"[\s\S]*class="ib-picker"[\s\S]*<\/div>' \+[\s\S]*'<div class="ib-krow"><\/div>' \+\s*'<div class="ib-activef"><\/div>'/.test(head), head);
const click = CV.slice(CV.indexOf('querySelector(".ib-krow").onclick'), CV.indexOf('querySelector(".ib-activef").onclick'));
check("a tap toggles Has phone or picks a kind, then saves, redraws and reloads",
  /if \(b\.classList\.contains\("ib-kphone"\)\) _phone = _phone \? "" : "1";/.test(click) &&
  /else if \(b\.dataset\.kind != null\) _kind = b\.dataset\.kind;/.test(click) && /onFilterChange\(\);/.test(click), click);
const paint = CV.slice(CV.indexOf("  function paintHead() {"), CV.indexOf("  function dropFilter("));
check("the head draws the row from the filter state and the server's numbers, only when it changed",
  /var kh = V\.quickRowHtml\(filterState\(\), _quick, ic\);\s*if \(kr\.dataset\.sig !== kh\)/.test(paint), paint);
check("a redraw gives the focus back to the button that had it", /var ae = document\.activeElement, back = ae && kr\.contains\(ae\)/.test(paint) &&
  /if \(back\) focusOpener\(back\);/.test(paint));
check("the numbers come from the server's quick_counts, kept for the 5-second refresh",
  /if \(d\.quick_counts\) _quick = d\.quick_counts;/.test(CV) && /_whoCounts, _quick\]\)/.test(CV));
check("the two filters are saved with the rest and sent as kind and has_phone",
  /kind: _kind, phone: _phone/.test(CV) && /if \(s\.kind\) q \+= "&kind=" \+ s\.kind;/.test(MOD) && /if \(s\.phone\) q \+= "&has_phone=1";/.test(MOD));
const quickCode = click + paint + V5SRC.slice(V5SRC.indexOf("var KIND_OPTS"), V5SRC.indexOf("// ---- \"Who replies\" bar"));
check("nothing in the row branches on a channel id: the server knows what a comment thread is",
  !/messenger|threads|zalo|telegram|cmt:|igc:/.test(quickCode));

// ---- 3. CSS ----
const rule = (sel) => { const i = CSS.indexOf(sel + " {"); return i < 0 ? "" : CSS.slice(i, CSS.indexOf("}", i)); };
check("one low row: the segment and the chip are as tall as the who button (34px), same 13px type",
  /height: 34px/.test(rule(".ib-kseg")) && CSS.indexOf(".ib-kphone { position: relative; flex: none; height: 34px;") >= 0 &&
  /height: 34px/.test(rule(".ib-whobtn, .ib-v5 .ib-picker")) && /font-size: 13px/.test(rule(".ib-kopt, .ib-kphone")) &&
  /font-size: 13px/.test(rule(".ib-whobtn, .ib-v5 .ib-picker")));
check("nothing wraps: one line, labels end in '...' before a number is lost", /white-space: nowrap/.test(rule(".ib-kopt, .ib-kphone")) &&
  /text-overflow: ellipsis/.test(rule(".ib-kt")) && /flex: none/.test(rule(".ib-kn")));
check("Has phone keeps its words for screen readers in a narrow column and shows them from 420px",
  /\.ib-kphone \.ib-kt \{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect\(0 0 0 0\)/.test(CSS) &&
  /container-type: inline-size/.test(rule(".ib-krow")) && /@container \(min-width: 420px\) \{ \.ib-kphone \.ib-kt \{ position: static;/.test(CSS));
const block = CSS.slice(CSS.indexOf("/* the quick row under them"), CSS.indexOf(".ib-kopt.on .ib-kn"));
check("theme colours only in the new rules", block.length > 200 && !/#[0-9a-fA-F]{3,8}\b|rgba?\(/.test(block));

// ---- 4. words ----
const KEYS = { "ib.k_all": ["Tất cả", "All"], "ib.k_msg": ["Tin nhắn", "Messages"], "ib.k_cmt": ["Bình luận", "Comments"],
  "ib.k_phone": ["Có SĐT", "Has phone"] };
check("the owner's words in Vietnamese, their English twins", Object.keys(KEYS).every((k) => VI[k] === KEYS[k][0] && EN[k] === KEYS[k][1]));
check("the group's spoken name and the Filter menu's Pinned category in vi and en", ["ib.k_aria", "ib.f_pin"].every((k) => VI[k] && EN[k]));
check("the old 'phone or email' words are gone with their filter", !("ht.f_st_contact" in VI) && !("ib.fc_contact" in VI) &&
  !("ib.f_info" in EN) && !/ib\.fc_contact|ht\.f_st_contact|ib\.f_info/.test(V5SRC + CV + MOD));
const DASH = new RegExp("[" + String.fromCharCode(0x2013) + String.fromCharCode(0x2014) + "]");
check("no long dash in the new code and this test", ![quickCode, block, fs.readFileSync(__filename, "utf8")].some((t) => DASH.test(t)));

if (fails.length) { console.log("\nFAILED " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_inbox_quick_filters: all pass");
