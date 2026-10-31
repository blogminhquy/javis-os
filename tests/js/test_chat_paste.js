// Focused regression for readable clipboard paste (no browser or network needed).
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Paste = require("../../dashboard/chat-paste.js");

function check(name, fn) {
  try { fn(); console.log("ok   " + name); }
  catch (e) { console.error("FAIL " + name + ": " + e.message); process.exitCode = 1; }
}
check("short Vietnamese paste remains inline", () => {
  assert.equal(Paste.isLong("Xin chào, đây là ghi chú ngắn.\nBảng giá 2026"), false);
  assert.equal(Paste.isLong("a".repeat(1500)), false);
  assert.equal(Paste.isLong("a".repeat(12000)), false);
});
check("only large paste opens choice", () => {
  assert.equal(Paste.isLong("a".repeat(12001)), true);
  assert.equal(Paste.isLong(Array(150).fill("x").join("\n")), false);
  assert.equal(Paste.isLong(Array(151).fill("x").join("\n")), true);
});
check("line endings do not change threshold", () => {
  assert.equal(Paste.isLong(Array(150).fill("x").join("\r\n")), false);
  assert.equal(Paste.isLong(Array(151).fill("x").join("\r\n")), true);
});
check("Markdown stays Markdown on Ctrl+V", () => {
  const md = "# Báo cáo\n\n**Quan trọng**\n\n| Kênh | Doanh thu |\n|---|---|\n| FB | 20 |";
  assert.equal(Paste.prepare(md, "<b>trang web</b>"), md);
  assert.equal(Paste.isMarkdown(md), true);
  const fence = String.fromCharCode(96).repeat(3);
  assert.equal(Paste.isMarkdown(fence + "js\nx\n" + fence), true);
  assert.equal(Paste.isMarkdown("Chỉ là một câu ngắn."), false);
});
check("safe HTML-to-Markdown conversion preserves structure", () => {
  function txt(t) { return { nodeType: 3, nodeValue: t }; }
  function elem(tag, children, props) {
    const e = { nodeType: 1, tagName: tag.toUpperCase(), childNodes: children || [],
      getAttribute: k => (props || {})[k] || "" };
    e.children = e.childNodes.filter(x => x.nodeType === 1);
    e.querySelectorAll = () => [];
    return e;
  }
  const a = elem("a", [txt("đọc thêm")], { href: "javascript:alert(1)" });
  const body = elem("body", [
    elem("h2", [txt("Báo cáo")]), elem("p", [elem("strong", [txt("Đạt")]), txt(" mục tiêu.")]),
    elem("script", [txt("steal()")]), elem("p", [a])
  ]);
  body.querySelector = () => ({});
  const old = global.DOMParser;
  global.DOMParser = class { parseFromString() { return { body }; } };
  try {
    const md = Paste.htmlToMarkdown("<h2>Báo cáo</h2><p><strong>Đạt</strong></p>");
    assert.ok(md.includes("## Báo cáo"), md);
    assert.ok(md.includes("**Đạt** mục tiêu."), md);
    assert.ok(md.includes("đọc thêm"), md);
    assert.equal(md.includes("steal()"), false);
    assert.equal(md.includes("javascript:"), false);
  } finally { if (old === undefined) delete global.DOMParser; else global.DOMParser = old; }
});
check("fallback retains original text if no HTML parser", () => {
  assert.equal(Paste.prepare("giữ nguyên\nchữ", "<h1>Không chạy</h1>"), "giữ nguyên\nchữ");
});
check("integration keeps full plaintext payload and uses readable choice", () => {
  const app = fs.readFileSync(path.resolve(__dirname, "../../dashboard/app.js"), "utf8");
  const html = fs.readFileSync(path.resolve(__dirname, "../../dashboard/index.html"), "utf8");
  assert.ok(html.includes("/static/chat-paste.js?v=1"));
  assert.ok(html.indexOf("/static/chat-paste.js?v=1") < html.indexOf("/static/app.js?v="));
  assert.match(app, /paste\.offer\(text, insert, pasteAsTxt\)/);
  assert.match(app, /chatInput\.setRangeText\(value, range\.start, range\.end, "end"\)/);
  assert.match(app, /const plain = e\.clipboardData\.getData\("text\/plain"\)/);
  assert.match(app, /if \(e\.defaultPrevented \|\| e\.target !== chatInput\) return;/);
  assert.match(app, /window\.JavisPaste\.isMarkdown\(text\)/);
  assert.match(app, /window\.mdToHtml\(text\)/);
  assert.match(app, /div\.dataset\.text = text \|\| ""/);
  const teams = fs.readFileSync(path.resolve(__dirname, "../../dashboard/teams.js"), "utf8");
  assert.ok(teams.includes("paste.offer(content, insert, attachText)"));
  assert.ok(teams.includes("window.JavisPaste.isMarkdown(rest)"));
});
check("preview choices and sanitizing are wired", () => {
  const src = fs.readFileSync(path.resolve(__dirname, "../../dashboard/chat-paste.js"), "utf8");
  for (const text of ["Xem trước nội dung dán", "Dán vào chat", "Đính kèm .txt", "Hủy"]) {
    assert.ok(src.includes(text), text);
  }
  assert.ok(src.includes("preview.value = text"));
  assert.ok(src.includes("preview.readOnly = true"));
  assert.ok(src.includes("dialog.setAttribute(\"aria-modal\", \"true\")"));
  assert.ok(src.includes("node.nodeType !== 1"));
  assert.ok(src.includes("script|style|svg|iframe"));
});
if (process.exitCode) process.exit(process.exitCode);
