/* Tab Code + Terminal: khung trang, đường nạp, và mấy chỗ dễ đứt khi sửa sau này.

       node tests/js/test_code_terminal.js

   CI chỉ có node, không có trình duyệt, nên file này khoá phần HỢP ĐỒNG đọc được từ mã nguồn:
   trang mới phải được khai đủ SÁU chỗ trong console.js (icon, rail, nhóm, tiêu đề, bảng định
   tuyến, hàm render) - thiếu một chỗ là một triệu chứng khác nhau và không chỗ nào báo lỗi:
   thiếu rail thì không có lối vào, thiếu VIEW_META thì tiêu đề trang trống trơn, thiếu case
   trong renderPage thì bấm vào ra khung "đang phát triển".

   Ba thứ nữa được canh vì chúng là lý do người ta sẽ chửi chứ không phải lý do code xấu:
     - xterm.js (285KB) KHÔNG được nằm trong index.html: nó phải nạp lười, không thì mọi lượt
       mở dashboard đều gánh nó dù chín trên mười lượt không vào tab Code;
     - rời tab phải dọn WebSocket + ResizeObserver, không thì mỗi lần ghé qua bỏ lại một socket;
     - rời tab KHÔNG được đóng phiên shell - đang `npm install` mà bấm sang tab khác là mất. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CON = D("console.js");
const CODE = D("code-term.js");
const HTML = D("index.html");
const CSS = D("console.css");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// Bỏ comment trước khi soi: mấy file này nhắc tên "terminal" trong phần giải thích (vd chú
// thích về đăng nhập `agy` bằng terminal của máy), quét cả comment là bắt nhầm lời giải thích.
const khongComment = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
const CON_CODE = khongComment(CON);
const CODE_CODE = khongComment(CODE);

// ============================================================
// 1. Trang Code khai đủ sáu chỗ trong console.js
// ============================================================
check("VIEW_ICON có mục 'code'", /\bcode:\s*"terminal"/.test(CON_CODE));
check("RAIL_ITEMS có mục Code", /id:\s*"code".*label:\s*"Code"/.test(CON_CODE));
check("Code nằm trong một nhóm của rail (không rơi vào nhóm 'Khác')",
      /ids:\s*\[[^\]]*"code"[^\]]*\]/.test(CON_CODE));
check("VIEW_META có tiêu đề + phụ đề cho trang Code",
      /code:\s*\{\s*icon:\s*VIEW_ICON\.code[^}]*label:\s*"Code"[^}]*sub:/.test(CON_CODE));
check("renderPage định tuyến id 'code'", /if \(id === "code"\)\s+return renderCode\(el\)/.test(CON_CODE));
check("có hàm renderCode uỷ quyền cho code-term.js",
      /function renderCode\(el\)/.test(CON_CODE) && /window\.JavisCode/.test(CON_CODE));

// ============================================================
// 2. Nạp lười: xterm KHÔNG được nằm trong đường khởi động
// ============================================================
check("index.html nạp code-term.js (phần khung, nhẹ)", /\/static\/code-term\.js/.test(HTML));
check("code-term.js nạp TRƯỚC console.js (renderCode cần uỷ quyền được)",
      HTML.indexOf("/static/code-term.js") < HTML.indexOf("/static/console.js"));
// Bỏ comment HTML trước khi soi: chính chỗ khai code-term.js có câu giải thích "xterm.js nạp
// lười", quét cả comment là bắt nhầm lời giải thích đó.
check("CANARY: index.html KHÔNG nạp sẵn xterm (285KB phải nạp lười)",
      !/xterm/i.test(HTML.replace(/<!--[\s\S]*?-->/g, "")));
check("code-term.js tự chèn thẻ script xterm khi mở tab lần đầu",
      /vendor\/xterm-5\.5\.0\.min\.js/.test(CODE_CODE) && /createElement\("script"\)/.test(CODE_CODE));
check("nạp xong thì nhớ lại, lần sau không tải nữa",
      /if \(window\.Terminal && window\.FitAddon\) return Promise\.resolve\(\)/.test(CODE_CODE));
check("file xterm đã vendor sẵn trong repo (app không gọi mạng lúc chạy)",
      ["xterm-5.5.0.min.js", "xterm-5.5.0.css", "xterm-addon-fit-0.10.0.min.js"]
        .every((f) => fs.existsSync(path.join(ROOT, "dashboard", "vendor", f))));

// ============================================================
// 3. Rời tab: dọn socket nhưng ĐỪNG giết shell
// ============================================================
const renderCode = CON_CODE.slice(CON_CODE.indexOf("function renderCode"),
                                  CON_CODE.indexOf("function renderChatbots"));
check("rời trang Code có gọi dọn (JavisCode.roi)", /_pageLeave = \(\) =>/.test(renderCode)
      && /JavisCode\.roi\(\)/.test(renderCode));
check("rời trang Code gỡ lại lớp .cview-flush (cloneNode giữ class -> trang sau mất padding)",
      /classList\.remove\("cview-flush"\)/.test(renderCode));
check("huy() đóng WebSocket và ngắt ResizeObserver",
      /huy: function[\s\S]{0,400}ngatWs\(\)/.test(CODE_CODE) && /ro\.disconnect\(\)/.test(CODE_CODE));
// Gỡ handler TRƯỚC khi close, nếu không thì onclose (hàm tự-nối-lại) vẫn nổ sau đó và đẻ ra
// một socket thứ hai - hai shell ghi chung một màn hình.
check("ngatWs() gỡ handler rồi mới đóng (chống hai socket cùng chạy)",
      /function ngatWs\(\)[\s\S]{0,220}ws\.onclose = null[\s\S]{0,160}ws\.close\(\)/.test(CODE_CODE));
check("huy() gỡ luôn listener đổi tông (không thì mỗi lần vào tab lại chồng một cái)",
      /removeEventListener\("javis-theme-change"/.test(CODE_CODE));
// lastIndexOf, không phải indexOf: "huy: function" xuất hiện mấy lần (veTerminal có một cái
// tạm), cái CUỐI mới là hàm dọn thật của dungTerminal.
check("CANARY: rời tab KHÔNG gọi /terminal/close (shell phải chạy tiếp)",
      !/\/terminal\/close/.test(CODE_CODE.slice(CODE_CODE.lastIndexOf("huy: function"))));
check("chỉ nút 'Phiên mới' mới đóng hẳn phiên", /termNew[\s\S]{0,600}\/terminal\/close/.test(CODE_CODE));
check("mất kết nối thì tự nối lại (shell vẫn sống ở server)",
      /onclose[\s\S]{0,300}setTimeout\(noi/.test(CODE_CODE));

// ============================================================
// 4. Chế độ ống (Windows): phải nói thật + tự lo phần việc của tty
// ============================================================
check("có nhận biết chế độ ống", /st\.che_do === "ong"/.test(CODE_CODE));
check("chế độ ống hiện lời cảnh báo cho người dùng, không im lặng",
      /Chế độ đơn giản \(Windows\)/.test(CODE));
check("chế độ ống tự hiện chữ vừa gõ + Backspace + gom dòng rồi mới gửi",
      /\\x7f/.test(CODE_CODE) && /boDem \+ "\\n"/.test(CODE_CODE));
check("Ctrl-C ở chế độ ống đi bằng gói tín hiệu riêng",
      /type: "sig", name: "int"/.test(CODE_CODE));

// ============================================================
// 5. Khung trang mở rộng được + CSS
// ============================================================
check("danh sách chức năng khai thành mảng (thêm chức năng sau = thêm một dòng)",
      /var CHUC_NANG = \[/.test(CODE_CODE));
check("Terminal là chức năng đầu tiên", /\{ id: "terminal"/.test(CODE_CODE));
check("có dải tab để cắm chức năng sau", /class="code-tabs"/.test(CODE));
check("nhớ tab con đang xem giữa các lần vào", /KHOA_TAB/.test(CODE_CODE));
check("CSS có khung trang Code + terminal",
      /\.cview-body\.cview-flush/.test(CSS) && /\.code-page/.test(CSS) && /\.term-host/.test(CSS));
check("terminal chiếm hết chiều cao khung (không thì xterm tính hụt số dòng)",
      /\.code-page \{[^}]*height: 100%/.test(CSS));
check("bảng màu terminal có cả tông sáng lẫn tối", /javisTheme && window\.javisTheme\.isLight/.test(CODE_CODE));

console.log();
if (fails.length) { console.log(fails.length + " test HỎNG: " + fails.join(", ")); process.exit(1); }
console.log("Tất cả test code_terminal đã qua.");
