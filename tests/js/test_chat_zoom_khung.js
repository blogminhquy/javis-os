/* Khung chat mở rộng phải DÁN vào vùng nội dung, không nổi lên như popup.

       node tests/js/test_chat_zoom_khung.js

   Chủ repo yêu cầu (2026-07-31): "phần mở rộng trong chat là anh muốn nó dính vào luôn trong
   cái khung đỏ, không phải là popup nữa mà coi như nó choán luôn cái khung đấy, tệt luôn vào
   khung của phần ở giữa".

   Hình học thật đã đo bằng Chromium (rail 160px, rail thu 60px, không rail, đổi cỡ cửa sổ,
   thu rail giữa lúc đang mở): mép khung trùng khít .hud và đáy .hud-top. CI chỉ có node nên
   test này khoá phần HỢP ĐỒNG mà trình duyệt không cần chạy cũng kiểm được:
     - CSS hết sạch dấu vết popup (bo góc, bóng đổ, canh giữa, chừa mép).
     - CSS lấy toạ độ từ 4 biến do JS bơm, không hardcode.
     - JS đo .hud chứ không cộng tay var(--rail-w) - đây là chỗ dễ sai nhất: khi trang KHÔNG
       có rail thì --rail-w vẫn là 160px, cộng tay là khung lệch nguyên một dải.
     - JS nghe CẢ resize LẪN ResizeObserver - rail thu/mở đổi bề ngang .hud mà không bắn
       resize, chỉ nghe resize là khung đứng ì lệch mất phần rail vừa co. */
const fs = require("fs");
const path = require("path");

const CSS = fs.readFileSync(path.join(__dirname, "../../dashboard/style.css"), "utf8");
const JS = fs.readFileSync(path.join(__dirname, "../../dashboard/chat-zoom.js"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// Lay dung than rule ".chat-stage {" (khong dinh .chat-stage-head/-body/-main)
function than(sel) {
  const i = CSS.indexOf(sel + " {");
  if (i === -1) return "";
  return CSS.slice(i, CSS.indexOf("}", i) + 1);
}
const KHOI = than(".chat-stage");
check("tìm được rule .chat-stage", KHOI.length > 0);

// ---- 1. Hết dấu vết popup ----
check("không còn canh giữa bằng translateX", !/translateX/.test(KHOI));
check("không còn bo góc 16px", !/border-radius:\s*16px/.test(KHOI));
check("bo góc về 0", /border-radius:\s*0/.test(KHOI));
check("không còn bóng đổ nổi", !/box-shadow:\s*var\(--shadow-3\)/.test(KHOI));
check("bóng đổ tắt hẳn", /box-shadow:\s*none/.test(KHOI));
check("không còn chừa mép kiểu 96vw", !/96vw/.test(KHOI));
check("không còn nền kính mờ (blur khiến nó đọc ra lớp nổi)",
      !/backdrop-filter/.test(KHOI));

// ---- 2. Toạ độ lấy từ biến JS đo, không phải số cứng ----
for (const bien of ["--cs-top", "--cs-left", "--cs-w", "--cs-h"]) {
  check("toạ độ dùng biến " + bien, KHOI.indexOf("var(" + bien) !== -1);
}

// ---- 3. JS đo khung thật ----
// Soi phần CODE thôi. Comment trong chat-zoom.js có nhắc chữ var(--rail-w) để giải thích vì
// sao KHÔNG dùng nó; quét cả comment là bắt nhầm chính lời giải thích đó.
const JS_CODE = JS.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
check("JS đo .hud (không cộng tay --rail-w)",
      /querySelector\(["']\.hud["']\)/.test(JS_CODE) && !/var\(--rail-w\)/.test(JS_CODE));
check("JS lấy đáy .hud-top làm mép trên",
      /\.hud-top/.test(JS) && /getBoundingClientRect\(\)\.bottom/.test(JS));
for (const bien of ["--cs-top", "--cs-left", "--cs-w", "--cs-h"]) {
  check("JS bơm " + bien, JS.indexOf('"' + bien + '"') !== -1);
}

// ---- 4. Bám theo khi khung đổi ----
check("nghe resize cửa sổ", /addEventListener\(["']resize["']/.test(JS));
check("CANARY: có ResizeObserver (rail thu/mở KHÔNG bắn resize)",
      /ResizeObserver/.test(JS));
check("ResizeObserver bám .hud", /ResizeObserver[\s\S]{0,200}observe\(hud\)/.test(JS));
check("ResizeObserver có lối thoát khi trình duyệt cũ không hỗ trợ",
      /typeof ResizeObserver !== ["']function["']/.test(JS));

// ---- 5. Đo SAU khi gắn .chat-zoomed (class đó đổi lưới .hud) ----
const iZoom = JS.indexOf('classList.add("chat-zoomed")');
const iFit = JS.indexOf("fitToFrame()", iZoom);
check("CANARY: đo khung SAU khi gắn .chat-zoomed, không phải trước",
      iZoom !== -1 && iFit !== -1 && iFit > iZoom);

// ---- 6. Media query hẹp không được đặt lại toạ độ cứng đè lên số đo ----
const iMq = CSS.indexOf("@media (max-width: 900px)", CSS.indexOf(".chat-stage {"));
const mq = iMq === -1 ? "" : CSS.slice(iMq, iMq + 600);
const dongMq = (mq.match(/\.chat-stage \{[^}]*\}/) || [""])[0];
check("media query hẹp không hardcode lại width/top/height",
      !/width:|top:|height:/.test(dongMq));

if (fails.length) {
  console.log("\nFAIL - test_chat_zoom_khung: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_chat_zoom_khung: tất cả pass");
