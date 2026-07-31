/* Nút xuống cuối khung chat phải hiện NGAY khi cuộn lên, không chờ tin mới.

       node tests/js/test_nut_xuong_day.js

   Chủ repo yêu cầu (2026-07-31): "thêm nút xuống dưới cùng khi cuộn lên trên vì trong khung
   chat quá dài việc đọc lại xong xuống dưới mất quá nhiều thời gian".

   Bệnh cũ: đã có #newMsgBtn nhưng nó chỉ được bật trong scrollBottom(), mà scrollBottom() chỉ
   chạy khi CÓ TIN MỚI. Cuộn lên đọc lại một hội thoại dài rồi muốn quay xuống thì không có nút
   nào, phải tự kéo tay hết cả khung.

   Hành vi đã đo trong app THẬT bằng Chromium (15 phép thử: cuộn lên hiện nút, bấm nhảy xuống
   đáy, có tin mới thì nút nở ra có chữ, về đáy thì ẩn và nhả dạng tin mới, và nút đi theo khi
   phóng to khung chat). CI chỉ có node nên test này khoá phần hợp đồng đọc được từ mã nguồn. */
const fs = require("fs");
const path = require("path");

const APP = fs.readFileSync(path.join(__dirname, "../../dashboard/app.js"), "utf8");
const CSS = fs.readFileSync(path.join(__dirname, "../../dashboard/style.css"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}
// Lay than mot rule CSS theo dung selector (khong dinh rule ".x.y" hay ".x:hover")
function than(sel) {
  const re = new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{[^}]*\\}");
  const m = CSS.match(re);
  return m ? m[0] : "";
}

// ---- 1. Bộ xử lý cuộn phải TỰ bật nút, không ăn theo scrollBottom ----
const iScroll = APP.indexOf('chatArea.addEventListener("scroll"');
check("có bắt sự kiện cuộn của khung chat", iScroll !== -1);
const thanScroll = APP.slice(iScroll, APP.indexOf("});", iScroll));
check("CANARY: cuộn lên là cập nhật nút NGAY trong bộ xử lý cuộn",
      /capNhatNutXuong\(\)/.test(thanScroll));
check("bộ xử lý cuộn tính lại việc đang-ở-đáy", /stickBottom\s*=\s*ganDay\(\)/.test(thanScroll));

// Ham cap nhat phai BAT nut khi roi day, chu khong chi tat khi ve day (loi cu).
const iCap = APP.indexOf("function capNhatNutXuong");
const thanCap = APP.slice(iCap, APP.indexOf("\n}", iCap));
check("rời đáy -> thêm lớp show", /classList\.add\("show"\)/.test(thanCap));
check("về đáy -> bỏ lớp show", /classList\.remove\("show"\)/.test(thanCap));
check("chưa có tin nào thì chưa đụng tới nút", /if \(!newMsgBtn\.parentNode\) return/.test(thanCap));

// ---- 2. Hai dạng nút ----
check("có hàm vẽ nút theo hai dạng", /function veNutXuong\(/.test(APP));
const iVe = APP.indexOf("function veNutXuong");
const thanVe = APP.slice(iVe, APP.indexOf("\n}", iVe));
check("dạng gọn: chỉ icon, không chữ", /coTinMoi \? XUONG_ICON \+ " Tin mới" : XUONG_ICON/.test(thanVe));
check("gắn/nhả lớp has-new", /classList\.toggle\("has-new"/.test(thanVe));
check("có nhãn trợ năng cho cả hai dạng",
      /aria-label/.test(thanVe) && /Xuống cuối hội thoại/.test(thanVe));

// Icon dung ic() nhung phai co loi thoat: app.js chay sau icons.js, van guard cho chac.
check("icon lấy qua ic() có lối thoát khi chưa nạp icons.js",
      /typeof ic === "function"/.test(APP) && /ic\("chevron-down"\)/.test(APP));

// ---- 3. Về đáy phải NHẢ dạng "Tin mới" ----
// Không nhả thì lần sau chỉ cuộn lên đọc lại vẫn thấy chữ "Tin mới" - báo sai, mất tin cậy.
const iSb = APP.indexOf("function scrollBottom");
const thanSb = APP.slice(iSb, APP.indexOf("\n}\n", iSb));
check("CANARY: cuộn về đáy thì nhả dạng Tin mới", /veNutXuong\(false\)/.test(thanSb));
check("có tin mới lúc đang đọc thì bật dạng Tin mới", /veNutXuong\(true\)/.test(thanSb));

// ---- 4. CSS ----
const B = than("#newMsgBtn");
check("tìm được rule #newMsgBtn", B.length > 0);
// .transcript la flex DOC -> nut la flex item se BI CO theo chieu cao. Thieu flex:none thi
// nut tron 32px bi bop con 15px (da dinh that luc do trong trinh duyet).
check("CANARY: có flex:none, nếu không nút tròn bị bóp méo", /flex:\s*none/.test(B));
check("dạng gọn là hình tròn", /border-radius:\s*50%/.test(B));
check("dạng gọn vuông 32x32", /width:\s*32px/.test(B) && /height:\s*32px/.test(B));
check("dính đáy khung chat", /position:\s*sticky/.test(B) && /bottom:\s*6px/.test(B));
check("mặc định ẩn", /display:\s*none/.test(B));
const HN = than("#newMsgBtn.has-new");
check("dạng Tin mới nở ra thành viên thuốc",
      /width:\s*auto/.test(HN) && /border-radius:\s*16px/.test(HN));
check("dạng Tin mới ăn màu nhấn", /var\(--accent\)/.test(HN));
check("lớp show mới thực sự hiện", /#newMsgBtn\.show\s*\{[^}]*display:\s*inline-flex/.test(CSS));
// Nut noi DE len chu tin nhan -> bong phai du dam, khong thi chim vao nen chu.
check("bóng đủ đậm để tách khỏi chữ bên dưới", /box-shadow:\s*var\(--shadow-2\)/.test(B));

// ---- 5. Không được bỏ sót: nút vẫn nằm TRONG #chatArea để đi theo lúc phóng to ----
// chat-zoom.js dời NGUYÊN #chatArea vào lớp phóng to; nút là con của nó nên đi theo.
check("nút được chèn vào chính #chatArea",
      /newMsgBtn\.parentNode !== chatArea/.test(APP) && /chatArea\.appendChild\(newMsgBtn\)/.test(APP));
check("tin nhắn luôn chèn TRƯỚC nút, để nút nằm cuối mà sticky",
      /chatArea\.insertBefore\(el, newMsgBtn\)/.test(APP));

if (fails.length) {
  console.log("\nFAIL - test_nut_xuong_day: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_nut_xuong_day: tất cả pass");
