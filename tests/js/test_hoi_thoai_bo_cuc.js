/* Trang Chatbot: bố cục gọn, khung làm việc lấp đầy màn hình (0.65.10).

       node tests/js/test_hoi_thoai_bo_cuc.js

   Chủ dự án (30/09/2026): "khoảng trống bên trên đang quá nhiều khiến khung làm việc bị đẩy xuống", và bốn thẻ số liệu ở đầu Hòm thư "không cần
   thống kê, nếu có thì làm một tab khác". Nguyên nhân gốc: `.ht-body` cao `calc(100vh - 300px)` trong khi phần phía trên (tiêu đề + phụ đề, tab,
   bốn thẻ, hàng lọc, dòng đếm) thực tế cao khoảng 390px, nên cả trang phải cuộn.

   Những chỗ hỏng lặng lẽ mà file này khoá lại:

   1. ĐẦU TRANG CHUNG PHẢI BẬT/TẮT Ở MỌI LẦN ĐỔI TRANG. Lớp `cview-hoi-thoai` nằm trên #cview (không bị clone như cviewBody). Chỉ bật mà không
      tắt thì mọi trang sau mất đầu trang; tắt ở một chỗ khác thì lần vào lại thiếu.
   2. KHÔNG ĐƯỢC HỨA CHIỀU CAO CỨNG. Vùng làm việc lấp đầy bằng flex, không quay lại `calc(100vh - N)`.
   3. DÒNG ĐẾM NẰM TRONG CỘT DANH SÁCH nhưng danh sách vẫn là ô cuộn RIÊNG (`.ht-list`, JS ghi đè nội dung của nó). Nếu dòng đếm nằm TRONG ô đó thì bị xoá
      mỗi lần vẽ lại danh sách.
   4. ĐIỆN THOẠI: mở một hội thoại phải ẩn CẢ cột (dòng đếm lẫn danh sách), không chỉ danh sách.
   5. Số chưa đọc vẫn còn (huy hiệu trên tab) và số liệu vẫn được nạp (ô lọc kênh cần), chỉ bỏ phần vẽ thẻ.
*/
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const CV = read("dashboard/conversations.js");
const CON = read("dashboard/console.js");
const CSS = read("dashboard/console.css");
const VI = JSON.parse(read("dashboard/i18n/vi.json"));
const EN = JSON.parse(read("dashboard/i18n/en.json"));

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. bốn thẻ số liệu đã bỏ ----
check("không còn ô .ht-stats và hàm veStats", !/ht-stats/.test(CV) && !/function veStats/.test(CV) && !/veStats\(/.test(CV));
check("không còn CSS thẻ số liệu", !/\.ht-stats\b/.test(CSS) && !/\.ht-stat\b/.test(CSS));
check("bốn khoá chữ của thẻ số liệu đã bỏ (vi, en)", ["ht.st_tong", "ht.st_hom_nay", "ht.st_chua_doc", "ht.st_can_nguoi"].every((k) => !(k in VI) && !(k in EN)));
check("số chưa đọc vẫn hiện thành huy hiệu trên tab", /_stats\.chua_doc\) \? '<span class="ht-badge">'/.test(CV));
check("số liệu vẫn được nạp (ô lọc kênh dùng theo_kenh)", /_stats\.theo_kenh/.test(CV) && /_stats = /.test(CV));

// ---- 2. đầu trang: tiêu đề cùng hàng với tab ----
check("tiêu đề và tab cùng một hàng .ht-top", /<div class="ht-top">/.test(CV) && /<div class="ht-title">/.test(CV) &&
  CV.indexOf('class="ht-title"') < CV.indexOf('class="ht-tabs"'));
check("tiêu đề lấy từ từ điển của trang (page.conversations.label)", /window\.t\("page\.conversations\.label"\)/.test(CV) && VI["page.conversations.label"] === "Chatbot");
check("đầu trang chung bị ẩn cho trang này", /\.cview\.cview-hoi-thoai \.cview-head \{ display: none; \}/.test(CSS));
check("CANARY: lớp cview-hoi-thoai được bật/tắt ở MỌI lần renderPage, trước khi rẽ nhánh theo trang",
  /cv\.classList\.toggle\("cview-hoi-thoai", id === "conversations" \|\| id === "chatbots"\)/.test(CON) &&
  CON.indexOf('cv.classList.toggle("cview-hoi-thoai"') < CON.indexOf('if (id === "chat")     return renderChat(el);'));
check("thân trang không cuộn (từng tab tự cuộn) và đệm gọn hơn", /\.cview\.cview-hoi-thoai \.cview-body \{ padding: 10px 20px 14px; overflow: hidden;/.test(CSS) &&
  /\.ht-tab-body \{[^}]*overflow-y: auto/.test(CSS));

// ---- 3. vùng làm việc lấp đầy ----
check("CANARY: không còn chiều cao cứng calc(100vh - 300px)", !/height: calc\(100vh - 300px\)/.test(CSS));
check("vùng làm việc lấp đầy bằng flex, có sàn thấp", /\.ht-body \{ display: flex; gap: 12px; flex: 1 1 auto; min-height: 260px; \}/.test(CSS));
check("danh sách là ô cuộn riêng trong cột, khung tin cũng vậy", /\.ht-list \{ flex: 1 1 auto; min-height: 0; width: 100%; overflow: auto;/.test(CSS) &&
  /\.ht-msgs \{[^}]*overflow: auto/.test(CSS));

// ---- 4. dòng đếm nằm trong cột danh sách, KHÔNG nằm trong ô cuộn ----
const cot = (CV.match(/<div class="ht-listcol">' \+[\s\S]*?<div class="ht-list">/) || [""])[0];
check("dòng đếm và chip lọc nằm trong cột danh sách, TRƯỚC ô .ht-list", /ht-fsum/.test(cot) && /ht-fcount/.test(cot) && /ht-fclear/.test(cot));
check("CANARY: dòng đếm KHÔNG nằm trong .ht-list (JS ghi đè nội dung ô đó mỗi lần vẽ lại)", !/<div class="ht-list">[^']*ht-fsum/.test(CV));
check("cột danh sách có bề ngang cố định trên màn rộng", /\.ht-listcol \{ width: 320px; flex: none; min-height: 0; display: flex; flex-direction: column;/.test(CSS));

// ---- 5. điện thoại ----
check("CANARY: mở hội thoại trên điện thoại ẩn CẢ cột (dòng đếm lẫn danh sách)", /\.ht-wrap\.thread-on \.ht-listcol \{ display: none; \}/.test(CSS) &&
  /\.ht-wrap\.thread-on \.ht-list \{ display: none; \}/.test(CSS));
check("điện thoại: cột danh sách rộng hết cỡ, đệm trang gọn", /\.ht-listcol \{ width: 100%; \}/.test(CSS) && /\.cview\.cview-hoi-thoai \.cview-body \{ padding: 8px 14px 10px; \}/.test(CSS));

check("không dùng em dash trong test này", fs.readFileSync(__filename, "utf8").indexOf(String.fromCharCode(0x2014)) < 0);

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK: bố cục trang Chatbot");
