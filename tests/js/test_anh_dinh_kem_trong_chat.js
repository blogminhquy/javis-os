/* Ảnh dán vào khung chat phải xem lại được, hết hạn thì nói thẳng là hết hạn.

       node tests/js/test_anh_dinh_kem_trong_chat.js

   Chủ repo báo 01/09: "gửi ảnh vào javis để javis đọc thì sẽ không lưu lại tấm ảnh đó ở đoạn
   chat, và khi dán ảnh vào cũng không zoom lên được".

   Bong bóng tin của người dùng vẽ ảnh bằng `URL.createObjectURL(file)` - một URL chỉ sống
   trong tab đang mở, mà `clearAttachments()` thu hồi nó NGAY sau khi gửi. Thêm nữa lịch sử
   chỉ lưu `{name, kind}`, không lưu chỗ nào để trỏ tới. Nên ảnh vừa gửi đã hỏng, F5 một cái
   là mất hẳn, chỉ còn trơ cái tên file - và cũng chẳng bấm phóng to được vì nó là thẻ <img>
   trần, không nằm trong `a.jv-img-link` mà lightbox lắng nghe.

   File này chạy CHÍNH `attachHtml` lấy từ source, vì đây là loại lỗi đọc code không thấy:
   nhìn vào chỗ cũ thì "có hiện ảnh mà", chỉ khi soi ra ảnh trỏ vào đâu mới thấy vấn đề. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const APP = D("app.js");
const CSS = D("style.css");
const HTML = D("index.html");
const RENDER = D("chat-render.js");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

// ---- Lấy đúng hai hàm dựng HTML ra khỏi app.js rồi chạy thật ----
function catHam(ten) {
  const i = APP.indexOf("function " + ten + "(");
  if (i < 0) throw new Error("không thấy hàm " + ten + " trong app.js");
  // Cắt tới dòng "}" ở cột 0 đầu tiên - app.js thụt lề chuẩn nên đó là đúng cuối hàm.
  const j = APP.indexOf("\n}\n", i);
  return APP.slice(i, j + 3);
}
const fn = new Function(
  "escapeHtml", "ic", "t",
  catHam("attachHtml") + catHam("anhHetHan") + "\nreturn { attachHtml, anhHetHan };"
)(
  (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;"),
  (n) => "<svg data-ic=\"" + n + "\"></svg>",
  (k) => (VI[k] === undefined ? k : VI[k])
);

// ============================================================
// 1. Ảnh CÓ url trên máy chủ: hiện được, và bấm phóng to được
// ============================================================
const co = fn.attachHtml([{ name: "anh.png", kind: "image", url: "/upload/raw?name=anh.png" }]);
check("ảnh hiện bằng thẻ <img>", /<img [^>]*src="\/upload\/raw\?name=anh\.png"/.test(co), co);
check("KHÔNG dùng blob: URL nữa (thứ chết ngay sau khi gửi)", !/blob:/.test(co), co);
check("bọc trong a.jv-img-link -> dùng chung lightbox với mọi ảnh khác",
  /<a class="jv-img-link att-img"/.test(co), co);
check("mang theo tên thật cho lightbox (data-img-ten)",
  /data-img-ten="anh\.png"/.test(co), co);

// ============================================================
// 2. Ảnh KHÔNG còn url: khung "không còn xem lại được", không phải ô vỡ
// ============================================================
const mat = fn.attachHtml([{ name: "cu.png", kind: "image" }]);
check("tin cũ (chỉ có tên + loại) KHÔNG dựng thẻ <img> rỗng", !/<img/.test(mat), mat);
check("mà dựng khung .att-mat", /class="att-mat"/.test(mat), mat);
check("khung đó nói rõ là không xem lại được",
  mat.indexOf(VI["chat.att_gone"]) !== -1, mat);
check("vẫn giữ tên file để người dùng biết đó là ảnh nào",
  /class="att-mat-ten">cu\.png</.test(mat), mat);
check("và KHÔNG rơi xuống nhánh file-tag (ảnh không phải file đính kèm thường)",
  !/file-tag/.test(mat), mat);

// ============================================================
// 3. File thường vẫn y như cũ
// ============================================================
const tep = fn.attachHtml([{ name: "bao-cao.pdf", kind: "file", url: "/upload/raw?name=b.pdf" }]);
check("file không phải ảnh vẫn là thẻ tên file", /class="file-tag"/.test(tep), tep);
check("và KHÔNG bị dựng thành <img> (pdf nhét vào <img> là một ô vỡ)",
  !/<img/.test(tep), tep);
check("không có đính kèm -> chuỗi rỗng", fn.attachHtml([]) === "" && fn.attachHtml(null) === "");

// ============================================================
// 4. Tên file là chữ NGƯỜI DÙNG đặt -> phải escape
// ============================================================
const xss = fn.attachHtml([{ name: '"><img src=x onerror=alert(1)>', kind: "image" }]);
// Chuỗi "onerror=alert(1)" CÒN trong kết quả là bình thường - nó đã thành chữ hiển thị. Thứ
// phải chết là dấu ngoặc: không còn thẻ nào mọc ra từ tên file.
check("tên file có HTML bị escape ở khung mất ảnh", !/<img src=x/.test(xss), xss);
const xss2 = fn.attachHtml([{ name: '"><b>x</b>', kind: "image", url: "/upload/raw?name=a.png" }]);
check("tên file có HTML bị escape ở thẻ ảnh", !/<b>/.test(xss2), xss2);

// ============================================================
// 5. Hợp đồng với phần còn lại của dashboard
// ============================================================
check("lịch sử lưu cả url (thiếu nó thì F5 xong ảnh không còn gì để trỏ tới)",
  /recordTurn\("user", msg, atts\.map\(a => \(\{ name: a\.name, kind: a\.kind, url: a\.url/.test(APP));
check("uploadFile nhận url từ máy chủ", /att\.url = up\.url/.test(APP));
check("bong bóng gắn xử lý ảnh 404 (vaAnhHong)", /vaAnhHong\(div\)/.test(APP));
check("ô ảnh ở thanh đính kèm cũng bấm phóng to được",
  /jv-img-link chip-thumb/.test(APP));
check("lightbox đọc data-img-ten thay vì đoán tên từ đường dẫn",
  /getAttribute\("data-img-ten"\)/.test(RENDER));
check("nút Tải về của lightbox biết cả /upload/raw",
  /\(files\|upload\)\\\/raw/.test(RENDER), RENDER.match(/a\.href = .*/)[0]);
check("CSS có khung .att-mat", /\.msg-attach \.att-mat\b/.test(CSS));
check("CSS cho ảnh đính kèm con trỏ zoom-in", /\.att-img\s*\{[^}]*zoom-in/.test(CSS));

// ============================================================
// 6. Chữ mới phải có trong từ điển, và sống được khi từ điển về muộn
// ============================================================
["chat.att_zoom", "chat.att_gone", "chat.att_gone_hint"].forEach((k) =>
  check("vi.json có khoá " + k, typeof VI[k] === "string" && VI[k].length > 0));
check("khung mất ảnh gắn data-i18n để applyDom chữa lại khi từ điển về muộn",
  /data-i18n="chat\.att_gone"/.test(mat), mat);
check("tooltip phóng to cũng vậy", /data-i18n-title="chat\.att_zoom"/.test(co), co);
check("index.html bump app.js để trình duyệt không giữ bản cũ",
  /app\.js\?v=(9[89]|\d{3,})/.test(HTML), (HTML.match(/app\.js\?v=\d+/) || [])[0]);

console.log();
if (fails.length) {
  console.log("FAIL " + fails.length + ": " + fails.join("; "));
  process.exit(1);
}
console.log("Tất cả xanh.");
