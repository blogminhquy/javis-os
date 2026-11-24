/* Pinned answers bar above the main chat, Partners and Chat (owner, 2026-11-24: "cả cộng sự cả hội thoại").

       node tests/js/test_chat_pins.js

The Chatbot page's Zalo-style bar (pin-bar.js) also sits above the main chat. chat-pins.js reads GET /sessions/<id>/pins,
draws the bar as the first child of #chatArea (sticky, only when there is a pin), and a tap goes to the answer, paging
back through older messages. app.js hands it the open chat and the pin mark through window.JavisChatPinHost.
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const P = require("../../dashboard/pin-bar.js");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const CP = src("dashboard/chat-pins.js");
const APP = fs.readFileSync(path.join(ROOT, "dashboard/app.js")).toString("utf8");
const WS = src("dashboard/workspace.js");
const CSS = src("dashboard/pin-bar.css");
const HTML = src("dashboard/index.html");
const MAIN = src("server/main.py");
const vi = require("../../dashboard/i18n/vi.json");
let fails = [];
function check(name, cond, extra) { console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]")); if (!cond) fails.push(name); }

// ---- an answer reads as its first line of words ----
check("a heading loses its marks", P.plain("## Báo cáo **tuần** 3\n\nchi tiết") === "Báo cáo tuần 3");
check("a code block is skipped, a link keeps its words", P.plain("```\ncode\n```\n- [Xem](http://a) ngay") === "Xem ngay");
check("snake_case words stay whole", P.plain("Đặt tên file_name_moi") === "Đặt tên file_name_moi");
check("empty answer: empty line", P.plain("") === "" && P.plain(null) === "");

// ---- the bar with the main chat's preview ----
const pins = [{ message_id: 9, role: "assistant", text: "### Kế hoạch\nLàm **bước** 2" }, { message_id: 4, role: "assistant", text: "Đã xong" }];
const html = P.barHtml(pins, { ic: (n) => "[" + n + "]", who: () => "Javis Core", preview: (p) => ({ icon: "", text: P.plain(p.text) }) });
check("the bar names the partner and the answer's first line", html.indexOf("Javis Core: Kế hoạch") !== -1 && html.indexOf("**") === -1);
check("'+1 pinned' for the second", html.indexOf(vi["pin.more"].replace("{n}", "1")) !== -1);

// ---- wiring ----
check("loaded on every page, after app.js", HTML.indexOf('src="/static/chat-pins.js') > HTML.indexOf('src="/static/app.js'));
check("reads the chat's pins from the server", CP.indexOf('"/sessions/" + encodeURIComponent(sid) + "/pins"') !== -1);
check("only a chat with a pin gets the bar (the empty-chat hint stays)", /if \(!S\.pins\.length\) \{ if \(b\) b\.remove\(\);/.test(CP));
check("the bar is the first child of #chatArea", /a\.insertBefore\(b, a\.firstChild\)/.test(CP));
check("another chat or a redraw is noticed", /new MutationObserver\(onMutate\)\.observe\(a, \{ childList: true \}\)/.test(CP));
check("a saved pin reads the list again", CP.indexOf('addEventListener("jv-pins-saved"') !== -1 &&
  APP.indexOf('chatArea.dispatchEvent(new CustomEvent("jv-pins-saved"))') !== -1);
check("Move to top and Unpin go through the answer pin route", CP.indexOf('{ pinned: false } : { pinned: true, top: true }') !== -1);
check("unpinning from the bar clears the pin under the answer", /H\.mark\(mid, false\)/.test(CP) && /mark\(mid, on\) \{/.test(APP));
check("a pin not loaded yet pages back through older messages", /H\.loadOlder\(\)/.test(CP) && /loadOlder: \(\) => taiTinCu\(\)/.test(APP));
check("a tap lights the answer up", CP.indexOf('el.classList.add("pin-flash")') !== -1 && /\.msg\.pin-flash \.bubble \{ animation: pb-flash/.test(CSS));
check("the host tells the open chat", /window\.JavisChatPinHost = \{\s*sid: \(\) => savedSessionId,/.test(APP));
check("Partners names the answers after the partner", /currentName: function \(\) \{ var x = active \? dangChon\(\) : null;/.test(WS));
check("the bar stays at the top while the chat scrolls", /\.chat-pinbar \{ position: sticky; top: 0;/.test(CSS));
check("the server lists pins and moves one to the top", MAIN.indexOf('@app.get("/sessions/{session_id}/pins")') !== -1 &&
  MAIN.indexOf('top=body.get("top") is True') !== -1);

if (fails.length) { console.log("\nFAIL " + fails.length); process.exit(1); }
console.log("\nOK - test_chat_pins.js: all pass");
