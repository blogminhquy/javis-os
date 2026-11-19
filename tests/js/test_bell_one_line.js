// Owner, 19/11/2026: "headline and content the same: show one line, not two". Runs the bell card's own dongPhu()
// from dashboard/notifications.js on the cases the owner saw and the near misses around them.
//   node tests/js/test_bell_one_line.js
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "notifications.js"), "utf8");
const m = src.match(/ {2}function dongPhu\(item\) \{[\s\S]*?\n {2}\}\n/);
assert.ok(m, "dongPhu() is in notifications.js");
const dongPhu = new Function(m[0] + "; return dongPhu;")();

const T = "Em kiểm tra hướng dẫn và lượt nhắc đến hạn, rồi đối chiếu lịch sử khách trước khi gửi.";
assert.strictEqual(dongPhu({ title: T, body: T }), "", "the owner's screenshot: title and text the same, one line");
assert.strictEqual(dongPhu({ title: T, body: T.slice(0, -1) }), "", "a missing full stop is still the same line");
assert.strictEqual(dongPhu({ title: T, body: "- **" + T + "**" }), "", "a bullet and bold marks are still the same line");
assert.strictEqual(dongPhu({ title: T, summary: T.toUpperCase(), body: T }), "", "a summary equal to the title is hidden");
assert.strictEqual(dongPhu({ title: T, body: T + "\nĐã gửi 2 tin." }), "Đã gửi 2 tin.", "a real detail line stays");
assert.strictEqual(dongPhu({ title: T, summary: "Đã gửi 2 tin.", body: T }), "Đã gửi 2 tin.", "a different summary stays");
assert.strictEqual(dongPhu({ title: T.slice(0, 40), body: T + "\nChi tiết" }), "Chi tiết",
  "a title cut at 120 characters drops the whole first line, no cut-off tail");
console.log("ok   bell card: one line when title and text say the same");
