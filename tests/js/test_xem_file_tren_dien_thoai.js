/* Mở file .txt / .md trên ĐIỆN THOẠI thì phải thoát ra được.

       node tests/js/test_xem_file_tren_dien_thoai.js

   Chủ repo báo 2026-09-08: "ở điện thoại khi mở file.txt trong khung chat hoặc khung .md thì
   không ấn nút tắt được, không có cách nào back lại màn hình cũ".

   NGUYÊN NHÂN, đo từ chính mã nguồn - ba thứ cộng lại thành một cái bẫy:

     1. Vừa mở file là `ta.focus()` chạy ngay. Trên điện thoại, focus = BÀN PHÍM ẢO bật lên
        chiếm gần nửa màn, và trình duyệt tự cuộn ô soạn vào giữa. Thẻ modal thì được căn giữa
        theo `max-height:88vh` của màn hình ĐẦY ĐỦ, nên đầu thẻ (chỗ có nút Đóng) bị đẩy lên
        ngoài vùng nhìn thấy.
     2. Hai đường thoát còn lại đều không dùng được ở đó: phím Esc thì điện thoại không có, còn
        bấm nền mờ chỉ nghe `mousedown` - iOS không phải lúc nào cũng sinh sự kiện đó cho một
        thẻ <div> trơn.
     3. Nút Back của điện thoại không đóng modal mà thoát luôn khỏi app, vì không ai chèn bước
        lịch sử nào.

   Trên máy tính không ai thấy: màn rộng nên nút Đóng luôn nằm đó, và Esc luôn sẵn.

   CI chỉ có node nên file này khoá phần hợp đồng đọc được từ mã nguồn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const FE = fs.readFileSync(path.join(ROOT, "dashboard", "file-editor.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Không tự đặt con tro vào ô soạn trên màn cảm ứng
// ============================================================
// Đây là gốc rễ: không có bàn phím bật lên thì thẻ vừa màn hình và nút Đóng luôn nhìn thấy.
check("CANARY: có cửa ải kiểm màn cảm ứng trước khi focus", /function\s+focusNeuDuocPhep/.test(FE));
check("cửa ải đó nhận diện bằng pointer:coarse (không đoán theo user-agent)",
  /pointer:\s*coarse/.test(FE));
check("CANARY: trình sửa file thường KHÔNG còn focus thẳng khi vừa mở",
  !/setTimeout\(function \(\) \{ try \{ ta\.focus\(\); \} catch \(e\) \{\} \}, 30\);/.test(FE));
check("trình sửa .md cũng đi qua cùng cửa ải",
  /setMode\("wys"\); focusNeuDuocPhep\(wys\)/.test(FE));
// Người dùng TỰ bấm sang chế độ soạn thì focus là đúng ý họ - đừng chặn nhầm cái đó.
check("bấm tay sang chế độ soạn thì vẫn focus như cũ",
  /bWys\.onclick[^\n]*wys\.focus\(\)/.test(FE));

// ============================================================
// 2. Màn hẹp: toàn màn hình, nút Đóng không bao giờ trôi khỏi tầm tay
// ============================================================
const mq = (FE.match(/@media\(max-width:700px\)\{[\s\S]{0,1200}?\n\s*"\}"/) || [""])[0];
check("có khối CSS riêng cho màn hẹp", mq.length > 0);
check("CANARY: thẻ chiếm trọn chiều cao THẬT của màn (dvh), không phải 88vh căn giữa",
  /100dvh/.test(mq) && /max-height:none/.test(mq));
check("nền mờ hết padding để thẻ dán vào bốn cạnh", /padding:0/.test(mq));
check("đầu thẻ dính ở trên khi thân cuộn", /position:sticky/.test(mq));
check("nút biểu tượng đủ to cho ngón tay (>=40px)", /\.jvfe-btn\.icon\{width:40px/.test(mq));

// Lớp khoá cuộn nền được gán từ lâu mà CHƯA BAO GIỜ có luật CSS - trang sau lưng vẫn cuộn được.
check("CANARY: body.jvfe-open có luật khoá cuộn thật", /body\.jvfe-open\{overflow:hidden\}/.test(FE));

// ============================================================
// 3. Ba đường thoát, không phải một
// ============================================================
check("CANARY: nút Back của điện thoại đóng trình sửa", /addEventListener\("popstate"/.test(FE));
check("mở file thì chèn một bước lịch sử để Back có chỗ lui", /history\.pushState/.test(FE));
check("đóng bằng nút X thì nhả luôn bước đó (không để Back rỗng một nhịp)",
  /history\.back\(\)/.test(FE));
check("bấm nền mờ nghe cả click, không chỉ mousedown (iOS)",
  /modal\.addEventListener\("click"/.test(FE));
check("phím Esc vẫn còn cho máy tính", /e\.key === "Escape"/.test(FE));
check("nút Đóng vẫn có trong mọi kiểu file", (FE.match(/closeBtn\(\)/g) || []).length >= 5);

console.log("");
if (fails.length) {
  console.log("FAIL - test_xem_file_tren_dien_thoai: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_xem_file_tren_dien_thoai: tất cả pass");
