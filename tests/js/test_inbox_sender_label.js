/* Inbox: every outgoing message says who wrote it, the AI agent or a person (2026-11-22).

       node tests/js/test_inbox_sender_label.js

Owner 22/11: both the agent and people reply in the same chat, so anyone reading it back must tell them apart. An agent's
message shows that agent's own icon, its name and an "AI" tag; a person's shows a person icon and their name.
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const CV = fs.readFileSync(path.join(ROOT, "dashboard/conversations.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard/console.css"), "utf8");
const V5CSS = fs.readFileSync(path.join(ROOT, "dashboard/inbox-v5.css"), "utf8");
const RUNTIME = fs.readFileSync(path.join(ROOT, "server/chatbot_runtime.py"), "utf8");
const ROUTES = fs.readFileSync(path.join(ROOT, "server/routes/conversations.py"), "utf8");
const vi = require("../../dashboard/i18n/vi.json"), en = require("../../dashboard/i18n/en.json");
let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const i0 = CV.indexOf("  var GENERIC_NAMES = ");
const i1 = CV.indexOf("  // One message of the open chat.", i0);
check("the sender helpers exist before renderMessage", i0 !== -1 && i1 !== -1);
const window = { t: k => vi[k] || k };
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const ic = n => "[icon:" + n + "]";
const conv = { bot_name: "Chị Lan", bot_icon: "flower" };
const H = new Function("window", "esc", "ic", "_conv", CV.slice(i0, i1) +
  "\nreturn { senderName: senderName, senderHtml: senderHtml };")(window, esc, ic, conv);
const label = t => H.senderHtml(t, t.sender_type === "ai" ? "bot" : t.sender_type === "human" ? "nguoi" : "khach", H.senderName(t));

const ai = label({ sender_type: "ai", sender_name: "Trợ lý Hoa", metadata: { bot_icon: "heart-handshake" } });
check("an agent's message: its name, its own icon, and the AI tag", ai.indexOf("<b>Trợ lý Hoa</b>") !== -1 &&
  ai.indexOf("[icon:heart-handshake]") !== -1 && ai.indexOf('class="ht-who-tag">AI<') !== -1 && ai.indexOf('ht-who ai') !== -1);
const old = label({ sender_type: "ai", sender_name: "Bot", metadata: {} });
check("an old message stored as 'Bot' takes the chat's agent name and icon", old.indexOf("<b>Chị Lan</b>") !== -1 &&
  old.indexOf("[icon:flower]") !== -1 && old.indexOf(">Bot<") === -1);
conv.bot_icon = ""; conv.bot_name = "";
const bare = label({ sender_type: "ai", sender_name: "" });
check("no name and no icon anywhere: 'Bot' with the AI sparkles, never a robot", bare.indexOf("<b>Bot</b>") !== -1 &&
  bare.indexOf("[icon:sparkles]") !== -1 && bare.indexOf("[icon:bot]") === -1);
const you = label({ sender_type: "human", sender_name: "Bạn" });
check("a person stored as 'Ban' reads 'Ban' with a person icon, no AI tag", you.indexOf("<b>" + vi["ht.ban"] + "</b>") !== -1 &&
  you.indexOf("[icon:user-round]") !== -1 && you.indexOf("ht-who-tag") === -1 && you.indexOf("ht-who human") !== -1);
const staff = label({ sender_type: "human", sender_name: "Minh Quý" });
check("a person with a real name (the owner's Zalo name, Staff) shows that name", staff.indexOf("<b>Minh Quý</b>") !== -1);
const evil = label({ sender_type: "ai", sender_name: "<img onerror=x>", metadata: { bot_icon: "x" } });
check("names are escaped", evil.indexOf("<img") === -1);
check("a customer gets no badge, just the name", label({ sender_type: "customer", sender_name: "Lan" }) === "Lan");

check("renderMessage puts the label in the line under the bubble", /var whoHtml = senderHtml\(t, side, who\);/.test(CV) &&
  /'<div class="ht-msg-h">' \+ whoHtml/.test(CV));
check("no Vietnamese names left in the message renderer", !/function veTin\(/.test(CV) && !/\.map\(veTin\)/.test(CV));
["ht.who_ai", "ht.who_ai_tip", "ht.who_human_tip"].forEach(k => check(k + " in vi and en", !!vi[k] && !!en[k]));
check("CSS for the label and the AI tag", CSS.indexOf(".ht-who {") !== -1 && CSS.indexOf(".ht-who-tag {") !== -1 &&
  V5CSS.indexOf(".ib-v5 .ht-who.ai") !== -1 && V5CSS.indexOf(".ib-v5 .ht-who.human") !== -1);
check("server: a bot answer keeps the icon it was sent with", /md\["bot_icon"\] = str\(cfg\.get\("icon"\)\)\[:40\]/.test(RUNTIME));
check("server: the chat detail carries the bot's icon for older messages", /d\["bot_icon"\] = /.test(ROUTES));

if (fails.length) { console.log("\nFAIL - test_inbox_sender_label: " + fails.length); process.exit(1); }
console.log("\nOK - test_inbox_sender_label: all pass");
