/* Hồi quy: Enter khi bộ gõ tiếng Việt/IME còn composition không được gửi tin. */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const app = fs.readFileSync(path.join(root, "dashboard", "app.js"), "utf8");
const html = fs.readFileSync(path.join(root, "dashboard", "index.html"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

check("theo dõi compositionstart", /chatInput\.addEventListener\("compositionstart"/.test(app));
check("theo dõi compositionend", /chatInput\.addEventListener\("compositionend"/.test(app));
check("keydown chặn cờ composition riêng", /if \(chatInputComposing \|\|/.test(app));
check("keydown chặn isComposing chuẩn", /\|\| e\.isComposing \|\|/.test(app));
check("keydown có dự phòng IME keyCode 229", /e\.keyCode === 229\) return/.test(app));
check("Enter thường vẫn gửi tin", /e\.key === "Enter" && !e\.shiftKey/.test(app));
const appVersion = Number((html.match(/app\.js\?v=(\d+)/) || [])[1] || 0);
check("app.js đã bump cache", appVersion >= 80);

if (fails.length) {
  console.log("\nFAIL - test_chat_ime_enter: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_chat_ime_enter: tất cả pass");
