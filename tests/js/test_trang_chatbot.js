/* Trang Chatbot: giao diện phải chịu được NHIỀU bot ngay từ bản đầu, và không rò token.

       node tests/js/test_trang_chatbot.js

   Chủ repo đặt đề bài rõ: "Làm 1 bot, khách hỏi chuyển cho nhân viên. Nhưng anh muốn làm uxui
   có tính scale để thêm sửa xoá nhiều bot." Nghĩa là bản đầu chạy một con nhưng KHUNG phải là
   khung nhiều con - thêm bot thứ hai không được kéo theo một đợt sửa giao diện.

   Bốn thứ file này canh, đều là loại hỏng lặng lẽ:

   1. **Lưới thẻ + ô tìm, không phải form một bot.** Bản "một bot" hay bị viết thành một trang
      cấu hình phẳng; đến bot thứ hai thì vứt đi viết lại.

   2. **Bốn trạng thái, không phải hai.** Bot chết âm thầm (token bị thu hồi, mạng rớt) là thứ
      chủ chỉ biết khi khách phàn nàn. Nếu thẻ chỉ có bật/tắt thì trạng thái "lỗi" không có
      chỗ nào để hiện ra.

   3. **Không hiện token.** Trang này đổ thẳng JSON từ /chatbots ra màn hình. Ô token phải là
      type=password và không bao giờ đổ giá trị cũ vào lại.

   4. **Xoá phải nói rõ cái gì mất, cái gì còn.** Brain của bot có thể chứa cả tháng tài liệu
      chủ tự soạn; xoá bot mà không nói rõ brain vẫn còn thì người dùng không dám bấm. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

const CB = D("chatbots.js");
const CON = D("console.js");
const HTML = D("index.html");
const CSS = D("style.css");

// ============================================================
// 1. Trang được đăng ký đúng chỗ
// ============================================================
check("index.html có nạp module trang Chatbot", /chatbots\.js\?v=/.test(HTML));
// So bằng thẻ <script> chứ không bằng tên file: console.js được NHẮC trong hơn chục comment
// nằm phía trên, nên indexOf("console.js") trần trụi trỏ vào comment đầu tiên.
check("nạp TRƯỚC console.js (console gọi window.JavisChatbots)",
  HTML.indexOf('src="/static/chatbots.js') < HTML.indexOf('src="/static/console.js'));
check("module phơi ra đúng một cửa vào", /window\.JavisChatbots\s*=\s*\{\s*render:\s*render\s*\}/.test(CB));
check("console có mục Chatbot trên thanh bên", /id:\s*"chatbots"/.test(CON));
check("console định tuyến sang trang Chatbot",
  /if \(id === "chatbots"\) return renderChatbots\(el\)/.test(CON));
check("console uỷ quyền cho module chứ không tự vẽ lại",
  /window\.JavisChatbots/.test(CON));
check("có icon riêng cho mục Chatbot", /chatbots:\s*"[a-z-]+"/.test(CON));
check("CSS của trang đã có", /\.cb-grid/.test(CSS) && /\.cb-card/.test(CSS));

// ============================================================
// 2. Khung NHIỀU bot chứ không phải form một bot
// ============================================================
check("có lưới thẻ", /class="cb-grid"/.test(CB));
check("có ô tìm bot theo tên", /class="cb-search"/.test(CB) && /_q/.test(CB));
check("có nút tạo bot mới", /class="s-btn cb-new"/.test(CB));
check("mỗi bot một thẻ, dựng bằng vòng lặp", /ds\.forEach\(function \(b\) \{ box\.appendChild\(the\(b\)\)/.test(CB));
check("thẻ nào cũng có bật/tắt tại chỗ", /cb-toggle/.test(CB));
check("thẻ nào cũng có sửa", /cb-edit/.test(CB));
check("thẻ nào cũng có xoá", /cb-del/.test(CB));
check("gọi endpoint theo id, không phải endpoint số ít",
  /\/chatbots\/" \+ encodeURIComponent\(b\.id\)/.test(CB));
check("có trạng thái rỗng dạy người dùng bước đầu", /Chưa có bot nào/.test(CB));

// ============================================================
// 3. Bốn trạng thái, và lỗi phải NHÌN THẤY
// ============================================================
["running", "starting", "error", "off"].forEach((s) => {
  check(`bảng trạng thái có "${s}"`, new RegExp("\\b" + s + ":\\s*\\{").test(CB));
});
check("lỗi cuối cùng được hiện ra thẻ", /st\.last_error/.test(CB) && /cb-err/.test(CB));
check("CSS có màu riêng cho ô trạng thái lỗi", /\.cb-dot\.err/.test(CSS));
check("Agent biến mất thì thẻ báo động", /agent_missing/.test(CB));

// ============================================================
// 4. Token không rò, và mỗi bot một token
// ============================================================
check("ô token là type=password", /id="cbToken" type="password"/.test(CB));
check("KHÔNG đổ token cũ vào ô", !/id="cbToken"[^>]*value="/.test(CB));
check("sửa bot thì nói rõ để trống là giữ nguyên", /để trống nếu không đổi/.test(CB));
check("có nút kiểm tra token trước khi lưu", /chatbots\/verify-token/.test(CB));
check("dặn mỗi bot một token riêng", /token RIÊNG/.test(CB));

// ============================================================
// 5. Nói thật với người dùng về hậu quả
// ============================================================
check("xoá bot có hỏi lại", /confirm\(/.test(CB));
check("xoá nói rõ brain và Agent KHÔNG bị xoá", /KHÔNG bị xoá/.test(CB));
check("form nói rõ bot tạo ra ở trạng thái tắt", /trạng thái <b>TẮT<\/b>/.test(CB));
check("form cảnh báo bot chỉ biết những gì trong brain của nó",
  /Bot chỉ biết những gì nằm trong brain này/.test(CB));
check("trang nói rõ bot không ghi, không có lệnh quản trị",
  /không có lệnh quản trị/.test(CB));

// ============================================================
// 6. Chọn Agent có sẵn HOẶC tạo brain mới ngay trong form
// ============================================================
check("form nạp danh sách Agent của brain hiện tại", /\/agents\?brain=/.test(CB));
check("form nạp danh sách brain", /api\("\/brains"\)/.test(CB));
check("tạo bot mới thì tạo được brain ngay tại chỗ", /\/brains\/new/.test(CB));
check("chỉ vào trang Agents khi chưa có Agent phù hợp", /trang <b>Agents<\/b>/.test(CB));

// ============================================================
// 7. Luật chung của dashboard
// ============================================================
check("HTML người dùng nhập đều qua esc()", !/innerHTML\s*=\s*[^;]*\+\s*(b|e)\.(name|message)\b(?![^;]*esc)/.test(CB));
check("không có em dash trong nguồn", CB.indexOf("—") === -1);

console.log("");
if (fails.length) { console.log("ĐỎ " + fails.length + " mục: " + fails.join(", ")); process.exit(1); }
console.log("Tất cả xanh.");
