/* Mở file .md từ tab Thư mục ở trang Trò chuyện: desktop phải GIỮ khung chat bên dưới
   trình sửa (chủ yêu cầu 27/08/2026) - vừa sửa file vừa nhắn Javis, không phải đóng
   trình sửa. Màn hẹp giữ lối cũ (trình sửa chiếm chỗ) vì không đủ chỗ xếp chồng.

       node tests/js/test_sua_md_giu_khung_chat.js
*/
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const cjs = fs.readFileSync(path.join(root, "dashboard", "console.js"), "utf8");
const html = fs.readFileSync(path.join(root, "dashboard", "index.html"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// Bóc đúng khối CSS của trang Trò chuyện (_injectChatCss) để không bắt nhầm
// .fm-page.edit-on của trang Tệp tin - trang đó vẫn ẩn phần duyệt như cũ.
const a = cjs.indexOf("function _injectChatCss()");
const b = cjs.indexOf("function _neoCuon", a);
const CSS = cjs.slice(a, b);
check("tìm thấy _injectChatCss", a !== -1 && b > a);

// display:none cho khung chat chỉ còn ĐÚNG MỘT chỗ - khối màn hẹp (check riêng bên dưới).
// Đếm số lần thay vì regex vắt qua nhiều khối media (bản đầu của check này bắt nhầm
// min-width của khối side-thu đứng trước rồi khớp với display:none của khối max-width).
check("desktop KHÔNG còn ẩn khung chat khi mở trình sửa",
  CSS.split(".chatpage-main.edit-on > .chatpage-slot{ display:none").length - 1 === 1);
check("desktop: khung chat rút gọn ở dưới (max-height, không display:none)",
  /@media \(min-width:861px\)\{[\s\S]*?\.chatpage-main\.edit-on > \.chatpage-slot\{ flex:0 0 auto; min-height:0; max-height:45vh; \}/.test(CSS));
check("hội thoại đang xem rút còn ~24vh và cuộn được",
  CSS.indexOf(".chatpage-main.edit-on > .chatpage-slot .transcript{ flex:0 1 auto; min-height:0; max-height:24vh; }") !== -1);
check("màn hẹp vẫn ẩn khung chat (không đủ chỗ xếp chồng)",
  /@media \(max-width:860px\)\{[\s\S]{0,200}\.chatpage-main\.edit-on > \.chatpage-slot\{ display:none; \}/.test(CSS));
check("trình sửa vẫn hiện khi edit-on",
  CSS.indexOf(".chatpage-main.edit-on > .chatpage-edit{ display:flex; }") !== -1);
check("trang Tệp tin không bị vạ lây (fm-page vẫn ẩn phần duyệt)",
  cjs.indexOf(".fm-page.edit-on>.fm-browse{display:none}") !== -1);
check("console.js đã bump ?v= (>= 113)",
  Number((html.match(/console\.js\?v=(\d+)/) || [])[1] || 0) >= 113);

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_sua_md_giu_khung_chat: tat ca pass");
