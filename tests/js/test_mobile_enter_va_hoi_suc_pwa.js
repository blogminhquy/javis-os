/* Hai lỗi mobile do người dùng thật báo (17/08/2026), cùng một phiên chat trên điện thoại:

   1. Máy chạm không có Shift+Enter nên Enter-gửi kiểu desktop nghĩa là KHÔNG CÁCH NÀO
      viết tin nhiều dòng. Máy chạm phải để Enter xuống dòng, gửi bằng nút Gửi.
   2. App "Thêm vào màn hình chính" bị iOS đóng băng nền: socket chết, tin đến trong lúc
      ngủ mất khỏi luồng live, và standalone KHÔNG có nút reload để user tự cứu. Phải tự
      hồi sức khi app dậy: nối lại socket + kéo lại hội thoại từ server.

       node tests/js/test_mobile_enter_va_hoi_suc_pwa.js
*/
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

// ---- 1. Enter trên máy chạm = xuống dòng ----
check("keydown chat có nhánh máy chạm (pointer: coarse)",
  /matchMedia\("\(pointer: coarse\)"\)\.matches\) return;/.test(app));
// Đo bằng pointer chứ không đo bề rộng màn: laptop cảm ứng có chuột vẫn Enter-gửi.
check("KHÔNG đo bằng bề rộng màn hình trong handler Enter",
  !/innerWidth[^\n]*sendMessage|sendMessage[^\n]*innerWidth/.test(app));
check("desktop vẫn Enter-gửi, Shift+Enter xuống dòng",
  /e\.key === "Enter" && !e\.shiftKey.*sendMessage\(\)/.test(app));
// Nhánh chạm phải đứng SAU chốt IME (tin đang ghép vần vẫn được bảo vệ ở mọi thiết bị)
// và TRƯỚC nhánh Enter-gửi.
const iIme = app.indexOf("e.keyCode === 229");
const iCoarse = app.indexOf('matchMedia("(pointer: coarse)")');
const iSend = app.indexOf('e.key === "Enter" && !e.shiftKey');
check("thứ tự: chốt IME -> nhánh chạm -> Enter-gửi",
  iIme > 0 && iCoarse > iIme && iSend > iCoarse);

// ---- 2. Hồi sức sau giấc ngủ nền ----
check("connect() có chốt chống nối trùng (hai đường gọi: retry 3s + hồi sức)",
  /readyState === WebSocket\.OPEN \|\| ws\.readyState === WebSocket\.CONNECTING\)\) return;/.test(app));
check("nghe visibilitychange để biết lúc app dậy", /addEventListener\("visibilitychange"/.test(app));
check("nghe pageshow bắt ca bfcache trả trang cũ", /addEventListener\("pageshow"/.test(app));
check("dậy là nối lại socket ngay, không đợi retry", /_resumeSauNgu/.test(app) && /try \{ connect\(\); \}/.test(app));
check("kéo lại hội thoại đang xem từ server để bù tin lỡ",
  /openStoredSession\(savedSessionId\)/.test(app));
// Ngủ ngắn (chuyển app qua lại vài giây) thì đừng ồn ào kéo lại - có ngưỡng thời gian.
check("có ngưỡng ngủ tối thiểu trước khi kéo lại", /_hiddenAt < 20000|20000 > /.test(app) || /_hiddenAt < 20 \* 1000/.test(app));

// ---- cache-bust ----
const v = Number((html.match(/app\.js\?v=(\d+)/) || [])[1] || 0);
check("app.js đã bump ?v= (>= 90)", v >= 90);

if (fails.length) {
  console.log("\nFAIL - test_mobile_enter_va_hoi_suc_pwa: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_mobile_enter_va_hoi_suc_pwa: tất cả pass");
