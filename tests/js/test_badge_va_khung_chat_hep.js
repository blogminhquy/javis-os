/* Hàng tiêu đề trang Trò chuyện phải gọn một dòng trên màn hẹp (0.12.5).

       node tests/js/test_badge_va_khung_chat_hep.js

   Hàng tiêu đề vỡ trên màn hẹp: "Trò chuyện với Javis" xuống BỐN dòng, chữ "Thu nhỏ" xuống
   hai dòng, đẩy khung chat tụt hẳn xuống. Hồi quy do chính nút Thu nhỏ thêm ở 0.12.4 - hàng
   vốn đã chật, thêm một nút chữ nữa là vỡ.

   NỬA KIA CỦA FILE NÀY ĐÃ BỎ ở 0.52.13. Nó canh badge engine+model ở đầu khung hội thoại:
   bảng nhãn tám bộ não, và `_mainProviderModel` đọc model chính đúng thứ tự server dùng. Chủ
   repo cho bỏ badge (model đã hiện ở thanh ngay dưới ô chat, chỗ đó dành cho tính năng mới),
   nên cả dây chuyền đó đi theo - xem tests/js/test_bo_badge_engine.js, file khoá việc dọn
   phải dọn HẾT chứ không để lại mắt xích chạy không tải. Giữ lại phép thử về bảng nhãn ở đây
   là canh một thứ không còn tồn tại.

   Một dòng của nửa cũ vẫn ở lại: bảng nhãn của panel Mức dùng. Nó là bảng KHÁC (_PROV_LABEL),
   phục vụ trang Mức dùng, và vẫn đang chạy. */
const fs = require("fs");
const path = require("path");

const D = (f) => fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", f), "utf8");
const APP = D("app.js");
const CONSOLE = D("console.js");
const HTML = D("index.html");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// Panel Mức dùng cũng phải biết Groq/Gemini, nếu không nó hiện trần id provider.
check("bảng nhãn panel Mức dùng có Groq và Gemini",
      /_PROV_LABEL = \{[^}]*groq: "Groq"/.test(APP) && /_PROV_LABEL = \{[^}]*gemini: "Gemini"/.test(APP));

// ---- 1. Hàng tiêu đề trang Trò chuyện phải gọn một dòng trên màn hẹp ----
const iMq = CONSOLE.indexOf("@media (max-width:860px)");
check("tìm được media query của trang Trò chuyện", iMq !== -1);
const MQ = CONSOLE.slice(iMq, iMq + 900);
check("CANARY: màn hẹp thì nút Thu nhỏ chỉ còn icon", /\.cp-min span\{\s*display:none/.test(MQ));
check("CANARY: tiêu đề cấm xuống dòng", /\.cp-title\{[^}]*white-space:nowrap/.test(MQ));
check("tiêu đề dài thì cắt bằng dấu ba chấm", /\.cp-title\{[^}]*text-overflow:ellipsis/.test(MQ));
// Trong flexbox, thiếu min-width:0 thì ellipsis không bao giờ ăn - phần tử cứ nở ra.
check("tiêu đề có min-width:0 (thiếu là ellipsis vô hiệu)",
      /\.cp-title\{[^}]*min-width:0/.test(MQ));

// Ẩn được chữ là nhờ nó nằm trong <span>. Để chữ trần thì không cách nào ẩn mà giữ icon.
check("CANARY: chữ 'Thu nhỏ' nằm trong <span> để ẩn được",
      CONSOLE.indexOf("<span>Thu nhỏ</span>") !== -1);
// Ẩn chữ thì trình đọc màn hình mất nghĩa của nút, nên phải có nhãn thay thế.
check("nút vẫn có nhãn cho trình đọc màn hình khi ẩn chữ",
      /id="cpMinBtn"[\s\S]{0,160}aria-label="Thu nhỏ/.test(CONSOLE));

// ---- 2. Trình duyệt phải nạp lại file đã sửa ----
const v = (f) => {
  const m = HTML.match(new RegExp(f.replace(".", "\\.") + "\\?v=(\\d+)"));
  return m ? Number(m[1]) : -1;
};
check("app.js được bump phiên bản", v("app.js") >= 76);
check("console.js được bump phiên bản", v("console.js") >= 91);

if (fails.length) {
  console.log("\nFAIL - test_badge_va_khung_chat_hep: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_badge_va_khung_chat_hep: tất cả pass");
