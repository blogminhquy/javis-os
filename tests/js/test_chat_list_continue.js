// A numbered list continues itself on a new line in every chat box (owner, 2026-11-11: "like in Claude").
// dashboard/chat-list.js: one delegated `input` listener, the rule itself is the pure continueList().
//
//     node tests/js/test_chat_list_continue.js
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const L = require(path.join(D, "chat-list.js"));
const { napTruoc } = require("./_thu_tu_nap.js");
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// Type a line break at "|" in `text`, then apply the edit: returns the text with "|" at the new caret.
function press(text) {
  const at = text.indexOf("|");
  const value = text.slice(0, at) + "\n" + text.slice(at + 1);
  const edit = L.continueList(value, at + 1);
  if (!edit) return null;
  const out = value.slice(0, edit.start) + edit.text + value.slice(edit.end);
  return out.slice(0, edit.caret) + "|" + out.slice(edit.caret);
}

check("a new line under item 1 opens with 2.", press("1. Ten goi tren OA|") === "1. Ten goi tren OA\n2. |");
check("the count goes on: 9 then 10", press("9. a|") === "9. a\n10. |");
check("it follows the last item, not the first", press("1. a\n2. b|") === "1. a\n2. b\n3. |");
check("1) style keeps its bracket", press("1) a|") === "1) a\n2) |");
check("the indent of the item is kept", press("  3. a|") === "  3. a\n  4. |");
check("breaking an item in two numbers the second half", press("1. abc|def") === "1. abc\n2. |def");
check("a new line in the middle pushes the numbers below up by one",
  press("1. a|\n2. b\n3. c\nbye") === "1. a\n2. |\n3. b\n4. c\nbye");
check("numbers below that do not carry on the count are left alone", press("1. a|\n5. b") === "1. a\n2. |\n5. b");
check("an empty item ends the list: the number goes away", press("1. a\n2. |") === "1. a\n|");
check("ending the list keeps the text below", press("1. a\n2. |\nbye") === "1. a\n|\nbye");
check("a lone '1. ' the user typed is not taken away", press("1. |") === null && press("hello\n1. |") === null);
check("an ordinary line is left alone", press("hello|") === null && press("") === null);
check("a number that is not a list marker is left alone",
  press("1.5 trieu|") === null && press("2026 la nam|") === null && press("Gia 10. ok|") === null);
check("the caret before the item's text is left alone", press("1. |abc") === null);
check("a caret that is not behind a line break changes nothing",
  L.continueList("1. a", 4) === null && L.continueList("1. a\n", 0) === null && L.continueList(null, 3) === null);

// Which input events count as a typed line break.
const ev = (o) => Object.assign({ inputType: "insertLineBreak", isComposing: false, data: null }, o);
check("a line break counts (Enter on a phone, Shift+Enter on a computer)",
  L.isLineBreak(ev()) && L.isLineBreak(ev({ inputType: "insertParagraph" })) && L.isLineBreak(ev({ inputType: "insertText", data: "\n" })));
check("typing, pasting and deleting do not count",
  !L.isLineBreak(ev({ inputType: "insertText", data: "a" })) && !L.isLineBreak(ev({ inputType: "insertFromPaste" }))
  && !L.isLineBreak(ev({ inputType: "deleteContentBackward" })) && !L.isLineBreak({}) && !L.isLineBreak(null));
check("an IME still composing never counts", !L.isLineBreak(ev({ isComposing: true })));

// Every chat screen is covered by the one listener (owner rule of 2026-11-05: chat boxes stay in sync).
const read = (f) => fs.readFileSync(path.join(D, f), "utf8");
const boxes = L.BOXES.split(",").map((s) => s.trim());
check("main chat box is covered", boxes.includes("#chatInput") && /<textarea id="chatInput"/.test(read("index.html")));
check("Team chat box is covered", boxes.includes(".tm-input") && /<textarea class="tm-input"/.test(read("teams.js")));
check("customer reply box and its AI draft are covered", boxes.includes(".ib-cin textarea") && boxes.includes(".ib-draft-t")
  && /<div class="ib-cin">' \+\s*'<textarea /.test(read("conversations.js")) && /<textarea class="ib-draft-t"/.test(read("inbox-v5.js")));
check("background-job answer box is covered", boxes.includes(".viec-tl-o") && /<textarea class="viec-tl-o"/.test(read("chat-viec.js")));
check("chatbot trial box is covered", boxes.includes("#cbTryText") && /<textarea id="cbTryText"/.test(read("chatbots-try.js")));
check("chat-list.js loads on the page, before app.js", napTruoc("chat-list.js", ["app.js"]));
const src = read("chat-list.js");
check("it listens to input, not keydown (a phone keyboard does not name its Enter key)",
  /document\.addEventListener\("input"/.test(src) && !/addEventListener\("keydown"/.test(src));
check("the edit goes through execCommand first so undo takes it back", /document\.execCommand\(edit\.text \? "insertText" : "delete"/.test(src));

if (fails) { console.log("\nFAIL - test_chat_list_continue: " + fails); process.exit(1); }
console.log("\nOK - test_chat_list_continue");
