// 0.190.0: the "Đã nhớ · Hoàn tác" line under an answer (dashboard/chat-nho.js).
//
//     node tests/js/test_chat_nho.js
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const N = require(path.join(root, "dashboard", "chat-nho.js"));
const read = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");
const vi = JSON.parse(read("i18n/vi.json"));
const en = JSON.parse(read("i18n/en.json"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + String(extra).slice(0, 400)));
  if (!cond) fails++;
}

const block = '<!-- JAVIS_NHO: {"brain":"/b","items":[{"slug":"kenh-ban","title":"Kênh <bán>","act":"new"},' +
  '{"slug":"xung-ho","title":"Xưng hô","act":"updated"},{"slug":"cu","title":"Cũ","act":"forgot"}]} -->';
const t = N.tach("Đã nhớ: Kênh bán\n" + block);
check("takes the block out, keeps the plain line", t.clean === "Đã nhớ: Kênh bán" && t.nho && t.nho.brain === "/b"
  && t.nho.items.length === 3, JSON.stringify(t));
check("a broken block never shows on screen", N.tach("x\n<!-- JAVIS_NHO: {oops -->").clean === "x"
  && N.tach("x\n<!-- JAVIS_NHO: {oops -->").nho === null);
check("no block: text untouched", N.tach("bình thường").clean === "bình thường" && N.tach("bình thường").nho === null);
const h = N.lineHtml(t.nho);
check("new memory: Remembered + title + Undo", h.includes(vi["nho.saved"] + ": <strong>Kênh &lt;bán&gt;</strong>")
  && (h.match(/class="nho-undo"/g) || []).length === 1 && h.includes('data-slug="kenh-ban"'), h);
check("changed and forgotten ones say so, with no Undo", h.includes(vi["nho.updated"] + ": <strong>Xưng hô")
  && h.includes(vi["nho.forgot"] + ": <strong>Cũ"));
check("an unknown act is shown as updated, never as new with an Undo",
  !N.lineHtml(N.tach('<!-- JAVIS_NHO: {"brain":"b","items":[{"slug":"x","act":"hack"}]} -->').nho).includes("nho-undo"));
const src = read("chat-nho.js");
check("Undo forgets it on the server (not learnt again), success only after the reply",
  src.includes('fetch("/memory/forget"') && /r\.status !== 200 && r\.status !== 404\) throw/.test(src));
const app = read("app.js");
check("every Javis message goes through it (live push and reopened chat)",
  app.includes("window.JavisNho.tach(tv.clean)") && app.includes("if (tn.nho) window.JavisNho.ve(div, tn.nho);"));
check("the line is not a message: no reactions (live or reopened), never read aloud",
  /if \(el && el\.classList\.contains\("msg-nho"\)\) \{ scrollBottom\(\); notifySessions\(\); return; \}/.test(app)
  && (app.match(/window\.JavisChatReactions && !el\.classList\.contains\("msg-nho"\)\)/g) || []).length === 2);
const html = read("index.html");
check("loaded before app.js", html.indexOf("/static/chat-nho.js") > 0 && html.indexOf("/static/chat-nho.js") < html.indexOf("/static/app.js"));
const keys = ["nho.saved", "nho.updated", "nho.forgot", "nho.undo", "nho.undone", "nho.undo_err"];
check("i18n vi/en", keys.every((k) => vi[k] && en[k]));
check("CSS: a quiet line, touch-size Undo on phones", read("console.css").includes(".nho-undo {")
  && /\(pointer: coarse\) \{ \.nho-row \{ font-size: 15px; \}/.test(read("console.css")));
check("no em dash", !/[–—]/.test(src + keys.map((k) => vi[k] + en[k]).join("")));

if (fails) { console.log("\nFAIL " + fails); process.exit(1); }
console.log("\nOK test_chat_nho");
