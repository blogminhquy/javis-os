/* Bảng markdown VUỐT NGANG được, thay vì bị bóp cho vừa khung.

       node tests/js/test_bang_vuot_ngang.js

   Chủ repo gửi ảnh 21/09: trên điện thoại một bảng 3 cột bị ép vào bề ngang màn hình thì mỗi ô
   còn vài ký tự, chữ vỡ dọc thành từng chữ cái. App Claude không bóp: giữ bề rộng tự nhiên của
   cột rồi cho vuốt sang phải đọc tiếp.

   Ba mảnh phải có đủ, thiếu mảnh nào cũng hỏng theo kiểu khác nhau:
     1. khung bọc `overflow-x: auto`  -> không có thì không cuộn được gì cả;
     2. `width: max-content` cho bảng -> thiếu thì bảng vẫn co cho vừa, y như cũ;
     3. `max-width` cho từng ô        -> thiếu thì một ô văn xuôi dài kéo bảng rộng hàng nghìn
                                         pixel, phải vuốt cả chục lần mới hết.

   Và một bất biến ÂM THẦM: lớp bọc là một <div> thêm vào giữa DOM của trình sửa .md, nên bản
   WYSIWYG lưu lại phải vẫn ra đúng bảng markdown cũ. Đã đo thật với turndown 7.2 + plugin gfm
   (đúng bộ console.js nạp): có bọc hay không, markdown trả về y hệt nhau. */
const fs = require("fs");
const path = require("path");
const { mdToHtml } = require("../../dashboard/chat-render.js");

const ROOT = path.join(__dirname, "..", "..");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
const DV = fs.readFileSync(path.join(ROOT, "dashboard", "dataview.js"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || them === undefined ? "" : "  [" + them + "]"));
  if (!cond) fails.push(name);
};

const BANG = [
  "| | Chọn ở đâu | Dùng khi nào |",
  "|---|---|---|",
  "| Model chính | Trang Models | Chat thường |",
  "| Model việc nền | Trang Models, mục việc nền | Loop, Kanban |",
].join("\n");

// ---- 1. Bảng ra HTML có lớp bọc cuộn ----
const h = mdToHtml(BANG);
check("bảng được bọc trong khung cuộn", h.indexOf('<div class="md-tablewrap">') !== -1, h.slice(0, 80));
check("bảng vẫn là <table class=\"md-table\"> như cũ", h.indexOf('<table class="md-table">') !== -1);
check("khung bọc đóng lại đúng chỗ", h.indexOf("</table></div>") !== -1);
check("vẫn dựng đủ hàng và ô",
  (h.match(/<tr>/g) || []).length === 3 && (h.match(/<td>/g) || []).length === 6,
  (h.match(/<tr>/g) || []).length + " hàng");

// ---- 2. Không có bảng thì KHÔNG đẻ ra khung bọc thừa ----
check("đoạn văn thường không bị bọc", mdToHtml("Chỉ là một câu.").indexOf("md-tablewrap") === -1);

// ---- 3. Ba mảnh CSS ----
check("1/3: khung bọc cuộn ngang được",
  /\.md-tablewrap[^{]*\{[^}]*overflow-x:\s*auto/.test(CSS));
check("2/3: bảng bỏ luật co-cho-vừa, lấy bề rộng tự nhiên",
  /\.md-tablewrap > \.md-table[^{]*\{[^}]*width:\s*max-content/.test(CSS));
check("bảng NGẮN vẫn trải hết khung, không co rúm vào một góc",
  /\.md-tablewrap > \.md-table[^{]*\{[^}]*min-width:\s*100%/.test(CSS));
check("3/3: có trần bề rộng cho từng ô (ô văn xuôi dài phải tự xuống dòng)",
  /\.md-tablewrap > \.md-table :is\(th, td\)[^{]*\{[^}]*max-width:/.test(CSS));
check("vuốt hết bảng thì dừng, không kéo cả trang trôi theo",
  /\.md-tablewrap[^{]*\{[^}]*overscroll-behavior-x:\s*contain/.test(CSS));

// ---- 4. Bảng của dataview đi chung một luật ----
// Nó vốn đã có .dv-tablewrap với overflow-x:auto, nhưng bảng bên trong vẫn width:100% nên
// không bao giờ tràn ra để mà cuộn - tức cũng bị bóp y như bảng chat.
check("bảng dataview dùng chung khung cuộn", DV.indexOf('class="dv-tablewrap md-tablewrap"') !== -1);
check("luật CSS phủ cả hai nơi", CSS.indexOf(".jv-dataview .dv-tablewrap") !== -1);

// ---- 5. CANARY: đổi CSS thì phải đổi ?v= kẻo trình duyệt giữ bản cũ ----
check("style.css và chat-render.js đã bump ?v=",
  /style\.css\?v=(\d+)/.test(HTML) && Number(HTML.match(/style\.css\?v=(\d+)/)[1]) >= 89 &&
  Number(HTML.match(/chat-render\.js\?v=(\d+)/)[1]) >= 15);

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_bang_vuot_ngang: tat ca pass");
