/* Pinned messages bar of a customer conversation (owner, 2026-11-24, Zalo screenshots).

       node tests/js/test_inbox_pins.js

Like Zalo: the bar shows the first pin ("Message", then "Who: text" on one line), "+N pinned" opens the list
("Pinned messages (N)", "Collapse"), "..." beside a pin offers "Move to top" (not on the first) and "Unpin". A photo
reads "Photo", a file its name. conversations.js draws the bar in the thread, marks pinned messages and wires the
clicks; msg-press.js gives touch screens Pin / Unpin and Copy.
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const P = require("../../dashboard/pin-bar.js");
const vi = require("../../dashboard/i18n/vi.json"), en = require("../../dashboard/i18n/en.json");
const CV = fs.readFileSync(path.join(ROOT, "dashboard/conversations.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard/inbox-v5.css"), "utf8");
const STYLE = fs.readFileSync(path.join(ROOT, "dashboard/style.css"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8");
let fails = [];
function check(name, cond, extra) { console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]")); if (!cond) fails.push(name); }

const ic = n => "[icon:" + n + "]";
const who = p => p.sender_name || "";
const pins = [
  { message_id: 11, sender_type: "customer", sender_name: "Nhon", message_type: "text",
    text: "Mang cho bà 1 bộ quần áo\nmàu đỏ ở giường" },
  { message_id: 12, sender_type: "human", sender_name: "Minh Quý", message_type: "text", text: "teqja4-gohqow-Hogrug" },
  { message_id: 13, sender_type: "customer", sender_name: "Nhon", message_type: "image", text: "",
    metadata: { image_url: "https://f1.zdn.vn/x.jpg" } },
];

// ---- what a pin says ----
check("text: one line", P.preview(pins[0]).text === "Mang cho bà 1 bộ quần áo màu đỏ ở giường" && !P.preview(pins[0]).icon);
check("photo: 'Photo' with the photo icon", P.preview(pins[2]).text === vi["pin.photo"] && P.preview(pins[2]).icon === "image");
const file = P.preview({ message_type: "file", text: "", metadata: { attachment: { url: "https://x.vn/bao-gia.pdf", name: "bao-gia.pdf" } } });
check("file: its name with the clip icon", file.text === "bao-gia.pdf" && file.icon === "paperclip", JSON.stringify(file));

// ---- collapsed bar ----
const bar = P.barHtml(pins, { ic, who });
check("no pins: no bar", P.barHtml([], { ic, who }) === "");
check("the bar shows the first pin: chat icon, 'Message', 'Who: text'", bar.indexOf("[icon:message-circle]") !== -1 &&
  bar.indexOf("<b>" + vi["pin.kind"] + "</b>") !== -1 && bar.indexOf("Nhon: Mang cho bà") !== -1);
check("only the first pin is in the closed bar", bar.indexOf("teqja4") === -1 && bar.indexOf("pb-panel") === -1);
check("'+2 pinned' when there are three", bar.indexOf(vi["pin.more"].replace("{n}", "2")) !== -1 &&
  bar.indexOf('class="pb-more" aria-expanded="false"') !== -1);
check("one pin: no '+N' button", P.barHtml(pins.slice(0, 1), { ic, who }).indexOf("pb-more") === -1);
check("the pin is a button going to its message", bar.indexOf('data-pin-go="11"') !== -1);
check("its '...' names what it opens", bar.indexOf('data-pin-menu="11"') !== -1 && bar.indexOf('aria-haspopup="menu"') !== -1 &&
  bar.indexOf(vi["pin.opts"]) !== -1);

// ---- open list ----
const open = P.barHtml(pins, { ic, who, open: true });
check("open: 'Pinned messages (3)' and 'Collapse'", open.indexOf(vi["pin.title"].replace("{n}", "3")) !== -1 &&
  open.indexOf(vi["pin.less"]) !== -1 && open.indexOf("[icon:chevron-up]") !== -1);
check("open: every pin, in order", open.indexOf('data-pin-go="11"', open.indexOf("pb-list")) <
  open.indexOf('data-pin-go="12"') && open.indexOf('data-pin-go="12"') < open.indexOf('data-pin-go="13"'));
check("open: a photo pin reads 'Who: [photo icon] Photo'", open.indexOf("Nhon: <span class=\"pb-mic\">[icon:image]</span>" + vi["pin.photo"]) !== -1);
check("'+N' says it is open", open.indexOf('class="pb-more" aria-expanded="true"') !== -1);

// ---- the "..." menu ----
const m1 = P.barHtml(pins, { ic, who, open: true, menu: 12 });
const menu12 = m1.slice(m1.indexOf('data-pin-menu="12"'));
check("menu of a pin not on top: 'Move to top' then 'Unpin' (red)", menu12.indexOf('data-pin-act="top" data-mid="12"') !== -1 &&
  menu12.indexOf('class="pb-mi danger" data-pin-act="unpin" data-mid="12"') !== -1 &&
  menu12.indexOf(vi["pin.top"]) < menu12.indexOf(vi["pin.unpin"]));
const m0 = P.barHtml(pins, { ic, who, menu: 11 });
check("menu of the first pin: no 'Move to top'", m0.indexOf('data-pin-act="top"') === -1 && m0.indexOf('data-pin-act="unpin" data-mid="11"') !== -1);
check("only one menu at a time", (m1.match(/pb-menu/g) || []).length === 1);

// ---- safety and fingerprint ----
const evil = P.barHtml([{ message_id: 9, sender_name: "<img onerror=x>", text: "<script>x</script>" }], { ic, who });
check("names and text are escaped", evil.indexOf("<img") === -1 && evil.indexOf("<script") === -1);
check("the fingerprint changes when a pin moves or goes", P.sig(pins) !== P.sig([pins[1], pins[0], pins[2]]) &&
  P.sig(pins) !== P.sig(pins.slice(1)) && P.sig(pins) === P.sig(pins.map(p => Object.assign({}, p))));

// ---- strings ----
["pin.pin", "pin.unpin", "pin.top", "pin.kind", "pin.photo", "pin.go", "pin.opts", "pin.more",
  "pin.title", "pin.less", "pin.gone", "pin.finding", "pin.too_many", "pin.err", "pin.unpinned", "pin.copy"]
  .forEach(k => check("vi and en have " + k, !!vi[k] && !!en[k] && !/—/.test(vi[k] + en[k])));
check("the Vietnamese words follow Zalo's", vi["pin.top"] === "Đưa lên đầu" && vi["pin.unpin"] === "Bỏ ghim" &&
  vi["pin.less"] === "Thu gọn" && vi["pin.title"] === "Danh sách ghim ({n})" && vi["pin.more"] === "+{n} ghim");

// ---- wiring in conversations.js ----
check("the thread draws the bar above the messages", /pinBarSlot\(\) \+\s*\n\s*'<div class="ht-msgs">'/.test(CV));
check("each message carries its id and a pinned mark", CV.indexOf("(pinned ? \" pinned\" : \"\")") !== -1 &&
  CV.indexOf("' data-mid=\"' + esc(t.id) + '\"'") !== -1);
check("the poll redraws the bar only when it changed", CV.indexOf("if (pinSig() !== _pinSig) drawPins();") !== -1);
check("pins ride on the messages answer", CV.indexOf("_pins = d.pins || [];") !== -1);
check("changes go through POST /pins", CV.indexOf('"/conversations/" + id + "/pins"') !== -1);
check("a tap loads older pages until the message is there", /async function goToPin[\s\S]*?await taiCu\(\)/.test(CV) &&
  CV.indexOf('classList.add("pin-flash")') !== -1);
check("touch screens: hold a message for Pin and Copy", /MP\.bind\(box, \{\s*selector: "\.ht-msg\[data-mid\]"/.test(CV));
check("unpin offers Undo", CV.indexOf('toast(window.t("pin.unpinned"), function () { pinAct(mid, "pin", true); })') !== -1);
check("another chat closes the open list and menu", /if \(id !== _chon\) \{[^}]*_pinsOpen = false; _pinMenu = "";/.test(CV));

// ---- page and CSS ----
const PB = fs.readFileSync(path.join(ROOT, "dashboard/pin-bar.css"), "utf8");
check("the bar's code and looks load with every page (the main chat uses them too)",
  /<link rel="stylesheet" href="\/static\/pin-bar\.css\?v=\d+">/.test(HTML) && /<script src="\/static\/pin-bar\.js\?v=\d+"><\/script>/.test(HTML));
check("the Chatbot page holds the bar in its column, the open list lined up with it", /\.ht-pinbar \{ --pin-x: [^;]+; position: relative;/.test(CSS));
check("the open list lies over the messages", /\.pb-panel \{ position: absolute;/.test(PB));
check("touch screens show the pin only as a mark", /\(hover: none\), \(pointer: coarse\) \{\s*\.ht-msg:not\(\.pinned\) \.ht-mpin \{ display: none; \}/.test(CSS));
check("menu buttons are 44px", /\.pb-mi \{ min-height: 44px;/.test(PB));
check("held messages are not selected by the phone", STYLE.indexOf("  .mp-host .ht-msg { -webkit-user-select: none;") !== -1);
check("Zalo's 14px in the bar", /\.pb-line \{ font-size: 14px;/.test(PB) && /\.pb-t b \{ font-size: 14px;/.test(PB));
check("colours come from the theme", !/#[0-9a-f]{3,6}\b/i.test(PB) && !/#[0-9a-f]{3,6}\b/i.test(CSS.slice(CSS.indexOf("pinned messages (2026-11-24"))));

if (fails.length) { console.log("\nFAIL " + fails.length); process.exit(1); }
console.log("\nOK - test_inbox_pins.js: all pass");
