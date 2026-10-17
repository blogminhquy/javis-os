// 0.200.0: the "Đã tạo ... · Hoàn tác" line. Only NEW items get Undo, mapped to the route that removes that kind.
const path = require("path");
const D = require(path.join(__dirname, "../../dashboard/chat-doi.js"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const block = '<!-- JAVIS_DOI: {"brain":"/b","items":[{"kind":"reminder","id":"r_1","title":"Báo <b>7h</b>","act":"new"},'
  + '{"kind":"agent","id":"lan","title":"Lan","act":"updated"},{"kind":"evil","id":"x","act":"new"}]} -->';
const t = D.tach("Đã đặt lịch.\n" + block);
check("block taken out of the text", t.clean === "Đã đặt lịch." && t.doi);
check("unknown kinds dropped", t.doi.items.length === 2);
const h = D.lineHtml(t.doi);
check("title escaped", h.includes("&lt;b&gt;7h") && !h.includes("<b>7h"));
check("undo only on the new item", (h.match(/doi-undo/g) || []).length === 1 && h.includes('data-id="r_1"'));
check("undo routes exist for every kind", ["reminder", "loop", "agent", "workflow", "skill"].every(k => D.UNDO[k]));
check("reminder undo cancels rather than deletes", D.UNDO.reminder === "/reminders/cancel");
check("broken block leaves clean text", D.tach("x <!-- JAVIS_DOI: {bad} -->").clean === "x" && !D.tach("x <!-- JAVIS_DOI: {bad} -->").doi);

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
