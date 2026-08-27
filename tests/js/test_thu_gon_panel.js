/* Thu gọn hai panel như sidebar (chủ yêu cầu 27/08/2026):
   1. Panel VAULT (cột trái màn chính) - nút thu trong vault-tools, thu xong còn một nút
      mở lại; trạng thái nhớ qua localStorage và áp lại ngay lúc boot.
   2. Cột lịch sử HỘI THOẠI của trang Trò chuyện - nút lịch sử trên thanh tiêu đề giờ
      hiện cả desktop: màn hẹp vẫn là drawer, desktop thu tại chỗ (.side-thu, có nhớ).

   Bẫy phải canh: tab "Thư mục" của trang Trò chuyện MƯỢN đúng node .hud-left, nên CSS
   thu gọn phải khoá vào con trực tiếp của .hud-body, không được đi lạc theo node.

       node tests/js/test_thu_gon_panel.js
*/
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const html = read("dashboard/index.html");
const css = read("dashboard/style.css");
const cjs = read("dashboard/console.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. Panel Vault ----
check("index.html có nút thu #vtCollapse trong vault-tools", html.indexOf('id="vtCollapse"') !== -1);
check("index.html có nút mở lại #vtExpand", html.indexOf('id="vtExpand"') !== -1);
check("CSS thu gọn khoá vào con trực tiếp của .hud-body (không đi lạc khi node bị mượn)",
  css.indexOf("body.vault-thu .hud-body > .hud-left") !== -1);
check("thu xong cột trái còn dải hẹp (đổi grid-template-columns)",
  /body\.vault-thu \.hud-body \{[^}]*grid-template-columns/.test(css));
check("nút mở lại ẩn mặc định", /\.vault-expand \{ display: none; \}/.test(css));
check("mượn sang tab Thư mục thì giấu cả nút thu lẫn nút mở lại",
  css.indexOf(".cside-pane .vault-tools #vtCollapse") !== -1
  && css.indexOf(".cside-pane > .hud-left > .vault-expand") !== -1);
check("console.js gắn handler thu/mở và lưu localStorage",
  cjs.indexOf('"javis_vault_thu"') !== -1 && cjs.indexOf("vtCollapse") !== -1
  && cjs.indexOf("vtExpand") !== -1);
check("boot() áp lại trạng thái đã lưu (không nháy to rồi mới thu)",
  /function boot\(\) \{[\s\S]{0,600}javis_vault_thu/.test(cjs));

// ---- 2. Cột Hội thoại/Thư mục trang Trò chuyện ----
check("nút lịch sử hiện cả desktop (không còn display:none mặc định)",
  cjs.indexOf(".cp-side-toggle{ display:inline-block; }") !== -1);
check("thu xong còn dải hẹp có nút mở lại (không ẩn hẳn mất đường về)",
  /\.chatpage\.side-thu \.chatpage-side\{ width:46px/.test(cjs)
  && cjs.indexOf(".chatpage.side-thu .chatpage-side > .cside-expand{ display:flex") !== -1);
check("có nút thu ngay trên panel (cside-thu-btn), gắn SAU JavisChatSide.mount",
  cjs.indexOf("cside-thu-btn") !== -1
  && cjs.indexOf("JavisChatSide.mount") < cjs.indexOf('thuBtn.className = "cside-thu-btn"'));
check("luật thu khoá trong media min-width (không đụng drawer mobile)",
  /@media \(min-width:861px\)\{[\s\S]*?\.chatpage\.side-thu \.chatpage-side\{ width:46px/.test(cjs));
check("màn hẹp vẫn là drawer (side-open giữ nguyên)",
  cjs.indexOf('page.classList.toggle("side-open")') !== -1);
check("trạng thái thu cột lịch sử có nhớ qua localStorage",
  cjs.indexOf('"javis_chatside_thu"') !== -1);

// ---- 3. Khung HỘI THOẠI (cột phải màn chính) - thu co VÀO BÊN PHẢI ----
check("index.html có nút thu #chatColThu và nút mở lại #chatColMo",
  html.indexOf('id="chatColThu"') !== -1 && html.indexOf('id="chatColMo"') !== -1);
check("CSS thu cột phải khoá vào con trực tiếp .hud-body (node chat hay bị mượn đi)",
  css.indexOf("body.chatcol-thu .hud-body > .hud-right") !== -1);
check("thu xong cột phải còn dải 44px",
  /body\.chatcol-thu \.hud-body \{ grid-template-columns: 260px minmax\(0, 1fr\) 44px; \}/.test(css));
check("thu CẢ HAI panel cùng lúc vẫn đúng lưới (44px hai bên)",
  /body\.vault-thu\.chatcol-thu \.hud-body \{ grid-template-columns: 44px minmax\(0, 1fr\) 44px; \}/.test(css));
check("mọi luật chatcol-thu nằm trong media min-width (mobile cột này chính là khung chat)",
  /@media \(min-width: 861px\) \{[\s\S]*?body\.chatcol-thu \.hud-body \{/.test(css));
check("nút thu ẩn ở màn hẹp",
  /@media \(max-width: 860px\) \{ \.chatcol-thu-btn \{ display: none; \} \}/.test(css));
check("icon lật gương thành panel-right",
  css.indexOf(".chatcol-thu-btn svg, .chatcol-expand svg { transform: scaleX(-1); }") !== -1);
check("console.js gắn handler + nhớ localStorage javis_chatcol_thu",
  cjs.indexOf('"javis_chatcol_thu"') !== -1 && cjs.indexOf("chatColThu") !== -1
  && cjs.indexOf("chatColMo") !== -1);

// ---- cache-bust ----
check("style.css đã bump ?v= (>= 66)",
  Number((html.match(/style\.css\?v=(\d+)/) || [])[1] || 0) >= 66);
check("console.js đã bump ?v= (>= 111)",
  Number((html.match(/console\.js\?v=(\d+)/) || [])[1] || 0) >= 111);

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_thu_gon_panel: tat ca pass");
