/* Mở file .md từ tab Thư mục ở trang Trò chuyện (desktop): trình sửa bên TRÁI, khung
   chat co thành CỘT PHẢI như màn Javis - hội thoại trên, ô nhập dưới đáy cột (chủ chỉnh
   27/08: bản xếp chồng dọc trước đó để chat nằm TRÊN trình sửa theo thứ tự DOM, nhìn
   ngược). Kèm nút thu khung chat phải - co vào bên phải, có nhớ. Màn hẹp giữ lối cũ
   (trình sửa chiếm chỗ) vì không đủ chỗ.

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

// ---- 1. Bố cục desktop: trình sửa trái, chat thành cột phải ----
check("edit-on desktop chuyển sang grid 2 cột (trình sửa + cột chat phải)",
  /\.chatpage-main\.edit-on\{ display:grid;[\s\S]{0,120}grid-template-columns:minmax\(0,1fr\) 340px/.test(CSS));
check("trình sửa nằm cột TRÁI", CSS.indexOf(".chatpage-main.edit-on > .chatpage-edit{ grid-row:2; grid-column:1") !== -1);
check("khung chat nằm cột PHẢI (grid đặt chỗ, thứ tự DOM hết quyết định vị trí)",
  CSS.indexOf(".chatpage-main.edit-on > .chatpage-slot{ grid-row:2; grid-column:2") !== -1);
check("hội thoại chiếm phần trên của cột (ô nhập tự về đáy)",
  CSS.indexOf(".chatpage-main.edit-on > .chatpage-slot .transcript{ flex:1 1 auto; min-height:0; max-height:none; }") !== -1);
check("bỏ trần 900px của slot trong cột hẹp",
  CSS.indexOf(".chatpage-main.edit-on > .chatpage-slot > *{ max-width:none; }") !== -1);
check("thanh tiêu đề vắt ngang cả hai cột",
  CSS.indexOf(".chatpage-main.edit-on > .chatpage-bar{ grid-column:1 / -1; }") !== -1);

// ---- 2. Nút thu khung chat phải (co vào bên phải, có nhớ) ----
check("có nút thu .cedit-thu-btn và nút mở lại .cedit-expand trong CSS",
  CSS.indexOf(".cedit-thu-btn") !== -1 && CSS.indexOf(".cedit-expand") !== -1);
check("trạng thái thu: cột phải còn dải 44px",
  CSS.indexOf(".chatpage-main.edit-on.echat-thu{ grid-template-columns:minmax(0,1fr) 44px; }") !== -1);
check("thu xong chỉ còn nút mở lại",
  CSS.indexOf(".chatpage-main.edit-on.echat-thu > .chatpage-slot > :not(.cedit-expand){ display:none; }") !== -1);
check("icon lật gương thành panel-right (bộ icon chưa có panel-right)",
  /\.cedit-thu-btn svg, \.cedit-expand svg\{ transform:scaleX\(-1\); \}/.test(CSS));
check("JS gắn nút + nhớ localStorage javis_editchat_thu",
  cjs.indexOf('"javis_editchat_thu"') !== -1 && cjs.indexOf('et.className = "cedit-thu-btn"') !== -1);

// ---- 3. Màn hẹp giữ lối cũ, trang Tệp tin không vạ lây ----
check("màn hẹp vẫn ẩn khung chat (không đủ chỗ)",
  /@media \(max-width:860px\)\{[\s\S]{0,200}\.chatpage-main\.edit-on > \.chatpage-slot\{ display:none; \}/.test(CSS));
check("trình sửa vẫn hiện khi edit-on",
  CSS.indexOf(".chatpage-main.edit-on > .chatpage-edit{ display:flex; }") !== -1);
check("trang Tệp tin không bị vạ lây (fm-page vẫn ẩn phần duyệt)",
  cjs.indexOf(".fm-page.edit-on>.fm-browse{display:none}") !== -1);
check("console.js đã bump ?v= (>= 114)",
  Number((html.match(/console\.js\?v=(\d+)/) || [])[1] || 0) >= 114);

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_sua_md_giu_khung_chat: tat ca pass");
