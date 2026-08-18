/* Nhóm Code trên rail + Terminal: cấu trúc điều hướng, đường nạp, và mấy chỗ dễ đứt khi sửa.

       node tests/js/test_code_terminal.js

   CI chỉ có node, không có trình duyệt, nên file này khoá phần HỢP ĐỒNG đọc được từ mã nguồn:
   trang mới phải được khai đủ SÁU chỗ trong console.js (icon, rail, nhóm, tiêu đề, bảng định
   tuyến, hàm render) - thiếu một chỗ là một triệu chứng khác nhau và không chỗ nào báo lỗi:
   thiếu rail thì không có lối vào, thiếu VIEW_META thì tiêu đề trang trống trơn, thiếu case
   trong renderPage thì bấm vào ra khung "đang phát triển".

   Bốn thứ nữa được canh vì chúng là lý do người ta sẽ chửi chứ không phải lý do code xấu:
     - "Code" phải là NHÓM RIÊNG trên rail, không phải một mục nhét vào "Bộ não". Bản 0.34.0
       xếp nhầm và chủ repo báo ngay: Code là khu vực sẽ dày lên, không phải chức năng của
       Second Brain;
     - convertEol phải bật ở chế độ ống - thiếu nó thì output Windows trôi thành bậc thang;
     - xterm.js (285KB) KHÔNG được nằm trong index.html: nó phải nạp lười, không thì mọi lượt
       mở dashboard đều gánh nó dù chín trên mười lượt không vào nhóm Code;
     - rời trang phải dọn WebSocket + ResizeObserver nhưng KHÔNG được đóng phiên shell - đang
       `npm install` mà bấm sang trang khác là mất. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
// Nhãn rail/trang nay nằm trong từ điển i18n, không còn viết cứng trong console.js.
const VI_JSON = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/vi.json"), "utf8"));
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
// 1. "Code" là NHÓM RIÊNG trên rail, Terminal là một mục trong đó
// ============================================================
// Nhãn nhóm rail nay là getter đọc từ điển (`t("nav.group.code")`) chứ không phải chuỗi
// viết cứng, nên bám vào KHOÁ thay vì bám vào chữ hiển thị. Bám chữ hiển thị thì mỗi lần
// đổi cách viết một nhãn là test đỏ vì lý do chẳng liên quan.
const nhomCode = /nav\.group\.code"\)[\s\S]{0,140}?ids:\s*\[([^\]]*)\]/.exec(CON_CODE);
check("rail có nhóm riêng tên 'Code'", !!nhomCode);
check("Terminal là một mục trong nhóm Code", !!nhomCode && /"terminal"/.test(nhomCode[1]));
// Bản 0.34.0 nhét "Code" thành một mục của nhóm Bộ não. Chủ repo báo ngay (2026-08-14):
// "ở sidebar sai rồi... chứ không phải chức năng trong bộ não".
const nhomBoNao = /nav\.group\.bo_nao"\)[\s\S]{0,140}?ids:\s*\[([^\]]*)\]/.exec(CON_CODE);
check("CANARY: nhóm Bộ não KHÔNG chứa Code/Terminal",
      !!nhomBoNao && !/"code"|"terminal"/.test(nhomBoNao[1]));
check("nhóm Code có icon riêng ở tầng nhãn nhóm", /"Code":\s*ic\(/.test(CON_CODE));

check("VIEW_ICON có mục 'terminal'", /\bterminal:\s*"terminal"/.test(CON_CODE));
// RAIL_ITEMS nay là danh sách ID; nhãn lấy từ dashboard/i18n/*.json qua t().
check("RAIL_ITEMS có mục Terminal", /"terminal"/.test(CON_CODE));
check("và nhãn Terminal có trong từ điển", !!VI_JSON["page.terminal.label"]);
check("VIEW_META có tiêu đề + phụ đề cho trang Terminal",
      !!VI_JSON["page.terminal.label"] && !!VI_JSON["page.terminal.sub"]);
check("renderPage định tuyến mọi trang thuộc nhóm Code",
      /CODE_PAGES\.includes\(id\)\)\s*return renderCode\(el, id\)/.test(CON_CODE)
      && /const CODE_PAGES = \[[^\]]*"terminal"/.test(CON_CODE));
check("có hàm renderCode uỷ quyền cho code-term.js",
      /function renderCode\(el, id\)/.test(CON_CODE) && /window\.JavisCode/.test(CON_CODE));

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
check("huy() đóng WebSocket của MỌI tab và ngắt ResizeObserver",
      /huy: function[\s\S]{0,400}ngatWs\(tb\)/.test(CODE_CODE) && /ro\.disconnect\(\)/.test(CODE_CODE));
// Gỡ handler TRƯỚC khi close, nếu không thì onclose (hàm tự-nối-lại) vẫn nổ sau đó và đẻ ra
// một socket thứ hai - hai shell ghi chung một màn hình.
check("ngatWs() gỡ handler rồi mới đóng (chống hai socket cùng chạy)",
      /function ngatWs\(tb\)[\s\S]{0,260}ws\.onclose = null[\s\S]{0,160}ws\.close\(\)/.test(CODE_CODE));
check("huy() gỡ luôn listener đổi tông (không thì mỗi lần vào tab lại chồng một cái)",
      /removeEventListener\("javis-theme-change"/.test(CODE_CODE));
// lastIndexOf, không phải indexOf: "huy: function" xuất hiện mấy lần (veTerminal có một cái
// tạm), cái CUỐI mới là hàm dọn thật của dungTerminal.
check("CANARY: rời trang KHÔNG gọi /terminal/close (shell mọi tab phải chạy tiếp)",
      !/\/terminal\/close/.test(CODE_CODE.slice(CODE_CODE.lastIndexOf("huy: function"))));
check("nút 'Khởi động lại' (termNew) đóng hẳn phiên của tab đang xem",
      /termNew[\s\S]{0,700}\/terminal\/close/.test(CODE_CODE));
check("mất kết nối thì tự nối lại (shell vẫn sống ở server)",
      /onclose[\s\S]{0,320}noi\(tb\)/.test(CODE_CODE));

// ============================================================
// 4. Chế độ ống (Windows): phải nói thật + tự lo phần việc của tty
// ============================================================
check("có nhận biết chế độ ống", /st\.che_do === "ong"/.test(CODE_CODE));
// Lỗi thật, đã ra tới tay chủ repo ở 0.34.0 kèm ảnh: cả màn `git help` trôi xiên sang phải.
// Chế độ ống không có tty driver đổi "\n" thành "\r\n", mà với xterm "\n" chỉ xuống dòng chứ
// KHÔNG về đầu dòng - nên mỗi dòng bắt đầu ở chỗ dòng trước kết thúc.
check("CANARY: convertEol bật ở chế độ ống (không thì output Windows thành bậc thang)",
      /convertEol:\s*ong\b/.test(CODE_CODE));
check("CANARY: convertEol KHÔNG bật cứng (bật ở pty là cướp mất '\\n' trần của chương trình TUI)",
      !/convertEol:\s*true/.test(CODE_CODE));
check("chế độ ống hiện lời cảnh báo cho người dùng, không im lặng",
      /Chế độ đơn giản \(Windows\)/.test(CODE));
check("chế độ ống tự hiện chữ vừa gõ + Backspace + gom dòng rồi mới gửi",
      /\\x7f/.test(CODE_CODE) && /boDem \+ "\\n"/.test(CODE_CODE));
check("Ctrl-C ở chế độ ống đi bằng gói tín hiệu riêng",
      /type: "sig", name: "int"/.test(CODE_CODE));

// ============================================================
// 5. Nhiều tab phiên: mỗi tab một shell riêng, F5 không mất
// ============================================================
check("có dải tab phiên (term-tabs) và nút mở thêm tab",
      /term-tabs/.test(CODE_CODE) && /termTabAdd/.test(CODE_CODE) && /\.term-tabs/.test(CSS));
check("trần số tab lấy từ server (max_phien), không viết cứng",
      /st\.max_phien/.test(CODE_CODE));
check("chạm trần thì nút '+' bị khoá chứ không lặng lẽ mở thêm",
      /tabs\.length >= maxTab/.test(CODE_CODE) && /disabled/.test(CODE_CODE));
check("danh sách tab lưu ở sessionStorage để F5/đổi trang quay lại còn nguyên",
      /javis\.code\.tabs/.test(CODE_CODE) && /function ghiTabs\(\)/.test(CODE_CODE));
check("di cư được khoá một-phiên cũ (javis.code.phien) sang tab đầu tiên",
      /javis\.code\.phien/.test(CODE_CODE) && /function docTabs\(\)/.test(CODE_CODE));
// Đóng TAB (dấu x) là chủ ý "xong việc với shell này" nên phải đóng hẳn phiên ở server -
// khác với rời trang (chỉ thôi xem). Không đóng thì shell mồ côi chiếm suất trong trần 4 phiên.
check("đóng tab (dấu x) gọi /terminal/close để giết shell của tab đó",
      /function dongTab\(i\)[\s\S]{0,700}\/terminal\/close/.test(CODE_CODE));
check("đóng tab cuối cùng thì tự mở tab mới (luôn còn ít nhất một tab)",
      /if \(!tabs\.length\) \{ themTab\(\); return; \}/.test(CODE_CODE));
// Khung ẩn phải CÓ kích thước để xterm đo được cột/dòng: ẩn bằng visibility, cấm display:none.
check("tab khuất ẩn bằng visibility (xterm cần khung có kích thước để đo)",
      /\.term-hosts \.term-host:not\(\.act\) \{ visibility: hidden; \}/.test(CSS));

// ============================================================
// 6. Khung mở rộng được + CSS
// ============================================================
check("danh sách chức năng khai thành mảng (thêm chức năng sau = thêm một dòng)",
      /var CHUC_NANG = \[/.test(CODE_CODE));
check("Terminal là chức năng đầu tiên", /\{ id: "terminal"/.test(CODE_CODE));
check("render nhận id để biết mở chức năng nào", /function render\(el, id\)/.test(CODE_CODE));
// Mỗi chức năng Code là MỘT MỤC trên rail, nên dải tab ĐIỀU HƯỚNG trong trang là thừa - hai
// tầng điều hướng cho cùng một thứ chỉ làm người dùng phải nhớ chức năng nằm ở tầng nào.
// (term-tabs ở mục 5 là chuyện khác: đó là tab PHIÊN của riêng terminal, không phải điều hướng.)
check("CANARY: không còn dải tab điều hướng trong trang (điều hướng nằm ở rail)",
      !/code-tabs/.test(CODE_CODE) && !/code-tabs/.test(CSS));
check("CSS có khung trang Code + terminal",
      /\.cview-body\.cview-flush/.test(CSS) && /\.code-page/.test(CSS) && /\.term-host/.test(CSS));
check("terminal chiếm hết chiều cao khung (không thì xterm tính hụt số dòng)",
      /\.code-page \{[^}]*height: 100%/.test(CSS));
check("bảng màu terminal có cả tông sáng lẫn tối", /javisTheme && window\.javisTheme\.isLight/.test(CODE_CODE));

console.log();
if (fails.length) { console.log(fails.length + " test HỎNG: " + fails.join(", ")); process.exit(1); }
console.log("Tất cả test code_terminal đã qua.");
