// Long paste in the main chat and the team chat (0.430.1, dashboard/chat-paste.js). No browser needed.
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Paste = require("../../dashboard/chat-paste.js");
const read = (f) => fs.readFileSync(path.resolve(__dirname, "../../dashboard", f), "utf8");

function check(name, fn) {
  try { fn(); console.log("ok   " + name); }
  catch (e) { console.error("FAIL " + name + ": " + e.message); process.exitCode = 1; }
}
check("a short or moderate paste stays plain text", () => {
  assert.equal(Paste.isLong("Xin chào, đây là ghi chú ngắn.\nBảng giá 2026"), false);
  assert.equal(Paste.isLong("a".repeat(1501)), false);   // the old limit no longer makes a file
  assert.equal(Paste.isLong(Array(26).fill("x").join("\n")), false);
  assert.equal(Paste.isLong("a".repeat(12000)), false);
});
check("only past one of the two limits does the dialog open", () => {
  assert.equal(Paste.isLong("a".repeat(12001)), true);
  assert.equal(Paste.isLong(Array(150).fill("x").join("\n")), false);
  assert.equal(Paste.isLong(Array(151).fill("x").join("\n")), true);
});
check("Windows line endings count the same", () => {
  assert.equal(Paste.isLong(Array(150).fill("x").join("\r\n")), false);
  assert.equal(Paste.isLong(Array(151).fill("x").join("\r\n")), true);
  assert.equal(Paste.lineCount("a\r\nb\rc"), 3);
});
check("the main chat asks instead of turning text into a file", () => {
  const app = read("app.js");
  assert.ok(!app.includes("PASTE_TXT_CHARS"), "old 1500-char limit is gone");
  assert.match(app, /if \(e\.defaultPrevented \|\| e\.target !== chatInput\) return;/);
  assert.match(app, /if \(!paste \|\| !paste\.isLong\(txt\)\) return;/);
  assert.match(app, /paste\.offer\(txt, \(value\) => paste\.insertAt\(chatInput, range, value\), pasteAsTxt\)/);
});
check("the team chat uses the same dialog", () => {
  const tj = read("teams.js");
  assert.ok(!tj.includes("PASTE_TXT_CHARS"));
  assert.ok(tj.includes("paste.isLong(txt)") && tj.includes("paste.offer(txt,"));
  assert.ok(tj.includes("attachFiles([paste.textFile(value)])"));
});
check("chat-paste.js loads before app.js", () => {
  const html = read("index.html");
  const at = html.indexOf("/static/chat-paste.js?v=");
  assert.ok(at > 0 && at < html.indexOf("/static/app.js?v="));
});
check("the preview shows raw text and can be closed", () => {
  const src = read("chat-paste.js");
  assert.ok(src.includes("preview.value = text") && src.includes("preview.readOnly = true"));
  assert.ok(!/innerHTML/.test(src), "the pasted text is never read as HTML");
  assert.ok(src.includes('setAttribute("aria-modal", "true")') && src.includes('e.key === "Escape"'));
  for (const k of ["paste.title", "paste.note", "paste.preview", "paste.inline", "paste.attach", "paste.cancel"]) {
    assert.ok(src.includes('"' + k + '"'), k);
  }
});
if (process.exitCode) process.exit(process.exitCode);
