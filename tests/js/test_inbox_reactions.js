/* Inbox: a customer's emoji reaction is one small line, not a bubble (0.334.0, javis-zalo 1.7.0).

       node tests/js/test_inbox_reactions.js

Owner 26/10: "khách hàng đọc được emoji reaction trên zalo". A reaction shown as a bubble would read as something the
customer wrote; it shows as the emoji plus who put it on which message.
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const CV = fs.readFileSync(path.join(ROOT, "dashboard/conversations.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard/console.css"), "utf8");
const vi = require("../../dashboard/i18n/vi.json"), en = require("../../dashboard/i18n/en.json");
let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const i0 = CV.indexOf("function renderReaction(");
const i1 = CV.indexOf("\n  }\n", i0);
check("renderReaction exists", i0 !== -1 && i1 !== -1);
const window = { t: (k, v) => {
  let s = vi[k] || k;
  Object.keys(v || {}).forEach(n => { s = s.split("{" + n + "}").join(v[n]); });
  return s;
} };
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const gio = () => "10:20";
const renderReaction = new Function("window", "esc", "gio", CV.slice(i0, i1 + 4) + "\nreturn renderReaction;")(window, esc, gio);

const tim = renderReaction({ message_type: "reaction", created_at: 1, metadata: { reaction: {
  emoji: "❤️", target_text: "Dạ còn ạ, 50k một bông", target_side: "ours" } } }, "khach", "Lan");
check("a heart: the emoji, who, and the message quoted", tim.indexOf("❤️") !== -1 && tim.indexOf("Lan thả cảm xúc vào") !== -1
  && tim.indexOf("50k một bông") !== -1 && tim.indexOf("10:20") !== -1);
check("it sits on the reactor's side, as a reaction line, not a bubble",
  tim.indexOf('class="ht-msg ht-react khach"') !== -1 && tim.indexOf("ht-bubble") === -1);
const bo = renderReaction({ metadata: { reaction: { removed: true, code: "" } } }, "khach", "Lan");
check("taken back: says so, dimmed", bo.indexOf("Lan bỏ cảm xúc") !== -1 && bo.indexOf("ht-react khach off") !== -1);
const la = renderReaction({ metadata: { reaction: { emoji: "👍", target_text: "" } } }, "bot", "Hoa");
check("unknown target: 'a message', never a guess", la.indexOf("Hoa thả cảm xúc vào một tin") !== -1);
const xau = renderReaction({ metadata: { reaction: { emoji: "<b>", target_text: "<script>x</script>" } } }, "khach", "<i>");
check("everything is escaped", xau.indexOf("<script>") === -1 && xau.indexOf("<b>") === -1 && xau.indexOf("<i>") === -1);
check("veTin hands reaction rows to renderReaction", /if \(t\.message_type === "reaction"\) return renderReaction\(t, lop, ai\);/.test(CV));
["ht.react_on", "ht.react_any", "ht.react_off"].forEach(k => check(k + " in vi and en with the same placeholders",
  !!vi[k] && !!en[k] && JSON.stringify((vi[k].match(/\{\w+\}/g) || []).sort()) === JSON.stringify((en[k].match(/\{\w+\}/g) || []).sort())));
check("CSS for the reaction line", CSS.indexOf(".ht-react-row") !== -1 && CSS.indexOf(".ht-react-emoji") !== -1);

if (fails.length) { console.log("\nFAIL - test_inbox_reactions: " + fails.length); process.exit(1); }
console.log("\nOK - test_inbox_reactions: all pass");
