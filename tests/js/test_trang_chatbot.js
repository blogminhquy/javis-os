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
check("form nói rõ bot đọc tài liệu của brain nào", /chính brain này/.test(CB));
// Lựa chọn quyết định bot "ăn nhập với Agent" hay không. Bản 0.20.0 ép cứng chế độ chỉ-tài-
// liệu cho mọi bot, và một Agent coach viết rất kỹ vẫn trả lời "em chưa có thông tin" cho
// đúng câu thuộc chuyên môn của nó. Phải cho chọn, và phải giải thích ngay tại chỗ chọn.
check("form cho chọn nguồn trả lời", /id="cbNguon"/.test(CB));
check("mặc định là chuyên môn Agent", /value="agent"[^>]*\+ \(!b \|\| b\.nguon_tra_loi !== "tai_lieu"/.test(CB));
check("giải thích khi nào dùng chế độ nào", /thiệt hại thật/.test(CB));
// Trang phải nói ĐÚNG việc Javis làm: nó không viết luật cho bot, nó chỉ khoá phạm vi brain.
// Hứa nhiều hơn thế là dạy người dùng tin vào một rào không tồn tại.
check("nói rõ Javis không thêm luật của mình vào Agent",
  /Javis không thêm luật nào của/.test(CB));
check("nói rõ rào duy nhất là chỉ đọc được brain này",
  /chỉ đọc\b[\s\S]{0,40}brain này/.test(CB));
check("lựa chọn được gửi lên server", /nguon_tra_loi: ngu/.test(CB));
check("thẻ bot hiện đang chạy chế độ nào", /b\.nguon_tra_loi === "tai_lieu" \? "chỉ tài liệu"/.test(CB));
check("trang nói rõ bot không ghi, không có lệnh quản trị",
  /không có lệnh quản trị/.test(CB));

// ============================================================
// 5b. Mức quyền: nới được, nhưng phải NHÌN THẤY cái mình đang trao đi
// ============================================================
// Chủ repo mở phạm vi ngày 2026-08-05: "anh vẫn muốn có thể thực hiện nhiều task, nhưng em
// thêm phần thông báo cho anh để hiểu rõ nguy cơ". Nghĩa là ô chọn mức KHÔNG được là một
// dropdown trơ ba dòng - mỗi mức phải kể ra nó lấy đi cái gì, ngay tại chỗ chọn.
check("form cho chọn mức quyền", /id="cbMuc"/.test(CB));
check("có ô đồng ý rủi ro", /id="cbAck"/.test(CB));
check("gửi mức quyền lên server", /muc_quyen: muc/.test(CB));
check("gửi kèm xác nhận đã đọc rủi ro", /xac_nhan_rui_ro: "1"/.test(CB));
// Câu chữ cảnh báo do SERVER cấp. Chép cứng ở giao diện thì một hôm server siết thêm rào mà ô
// cảnh báo vẫn hứa như cũ, và chủ bấm đồng ý dựa trên một câu đã sai.
check("cảnh báo lấy từ server chứ không chép cứng ở giao diện",
  /d\.muc_quyen \|\| \[\]/.test(CB) && /m\.canh_bao/.test(CB));
check("đổi mức là vẽ lại cảnh báo ngay", /oMuc\.onchange/.test(CB));
// Chưa tick mà lưu được thì cả khối cảnh báo chỉ là trang trí.
check("chưa tick đồng ý thì không lưu được",
  /can_xac_nhan && !\(ack && ack\.checked\)/.test(CB));
check("mức toàn quyền còn hỏi lại một lần nữa", /muc === "full" &&\s*\n?\s*!confirm\(/.test(CB));
check("cảnh báo nói thẳng người điều khiển là người nhắn cho bot",
  /người nhắn cho nó|người điều khiển bot/.test(CB));
// CANARY - chữ trên trang phải tả theo LOẠI THAO TÁC, không kể tên việc của một ngành.
// Bản đầu viết "tạo đơn, tiêu tiền quảng cáo, đăng bài": người dùng Javis để quản lý dự án hay
// dạy học đọc xong tưởng cảnh báo không áp cho mình. Chủ repo bác (2026-08-05).
["đơn hàng", "tạo đơn", "tiêu tiền", "quảng cáo", "đăng bài", "cửa hàng", "bán hàng", "bảng giá"]
  .forEach((n) => {
    check(`CANARY: trang KHÔNG kể tên việc của một ngành - "${n}"`, CB.indexOf(n) === -1);
  });
// Nhìn lưới thẻ phải phân biệt được ngay con nào có quyền thao tác. Không thì chủ nhớ nhầm
// con nào là con nào rồi thả nhầm vào nhóm khách.
check("thẻ bot hiện mức quyền khi được nới", /cb-quyen/.test(CB));
check("thẻ bot mức chỉ đọc KHÔNG dán nhãn (mặc định thì không cần)",
  /mq === "suggest" \? "" :/.test(CB));
check("bật bot có quyền thao tác thì hỏi lại", /if \(on && mucCua\(mq\)\.can_xac_nhan/.test(CB));
check("CSS cho nhãn mức quyền và khối cảnh báo",
  /\.cb-quyen\.full/.test(CSS) && /\.cb-canhbao\.full/.test(CSS) && /\.cb-ack/.test(CSS));
// Hai rào KHÔNG đổi theo mức, và trang phải nói đúng như vậy - hứa thiếu thì chủ ngại nâng
// mức một cách vô cớ, hứa thừa thì chủ tin vào một rào không tồn tại.
check("trang nói rõ hai rào giữ nguyên ở mọi mức",
  /không thấy brain khác, và không chạy được lệnh máy/.test(CB));

// ============================================================
// 6. Bot KHÔNG có brain riêng - trang thuộc về brain đang mở
// ============================================================
// Bản 0.22.3 bắt chọn brain trong form, rồi phải nhớ Agent nằm ở brain nào - hai lớp phải khớp
// nhau mà không có gì bắt chúng khớp. Chủ repo bác: "lựa brain nào thì hiện agent và chatbot
// của brain đó thôi". Bỏ hẳn ô brain thì phạm vi của trang CHÍNH LÀ câu trả lời.
check("CANARY: form KHÔNG còn ô chọn brain", CB.indexOf('id="cbBrain"') === -1);
check("CANARY: form KHÔNG còn nút tạo brain", CB.indexOf('cbNewBrain') === -1);
check("trang lọc bot theo brain đang mở", /\/chatbots\?brain=" \+ encodeURIComponent\(brain\(\)\)/.test(CB));
check("form nạp Agent của brain đang mở",
  /var br = brain\(\)/.test(CB) && /nạpAgent\(br\)/.test(CB));
check("lưu bot thì Agent và tài liệu cùng một brain", /agent_brain: br, brain: br,/.test(CB));
check("trang nói rõ đang xem bot của brain nào", /Bot của brain <b>/.test(CB));
check("trang chỉ cách xem brain khác", /Đổi brain ở đầu trang/.test(CB));
// Thẻ bot bỏ dòng brain: mọi bot ở đây đều cùng một brain nên nhắc lại từng thẻ chỉ là nhiễu.
check("thẻ bot không nhắc lại brain", !/ic\("brain"\) \+ ' ' \+ esc\(b\.brain\)/.test(CB));
check("có nút sang trang Agents để tạo", /id="cbNewAgent"/.test(CB) && /JavisNav\.go\("agents"\)/.test(CB));
// Vai trò dài làm <option> tràn ngang khỏi hộp, mà <option> thì không tạo kiểu được.
check("vai trò Agent bị cắt ngắn trước khi vào option", /vai\.slice\(0, 34\)/.test(CB));
check("CSS chặn select nở rộng ra khỏi form", /\.cb-form select \{[^}]*text-overflow: ellipsis/.test(CSS));
check("console phơi cửa chuyển trang cho module ngoài",
  /window\.JavisNav = \{ go: navigateTo \}/.test(CON));
// Vai trò dài làm <option> tràn ngang khỏi hộp, mà <option> thì không tạo kiểu được.
check("vai trò Agent bị cắt ngắn trước khi vào option", /vai\.slice\(0, 34\)/.test(CB));
check("CSS chặn select nở rộng ra khỏi form", /\.cb-form select \{[^}]*text-overflow: ellipsis/.test(CSS));

// ============================================================
// 6b. Nhật ký: mở ra là thấy VIỆC CẦN LÀM, không phải thấy log
// ============================================================
check("thẻ nào cũng mở được nhật ký", /cb-log/.test(CB) && /\/log\?limit=/.test(CB));
check("nhật ký có hai tab", /data-t="gaps"/.test(CB) && /data-t="turns"/.test(CB));
// Tab mặc định là "Bot bí" chứ không phải hội thoại: hội thoại chỉ để soi lại khi nghi ngờ,
// còn mỗi dòng trong "Bot bí" là một chỗ tài liệu đang thiếu - thứ chủ làm được gì đó với nó.
check("mở ra vào thẳng tab Bot bí", /ve\("gaps"\)/.test(CB));
check("tab Bot bí là tab được đánh dấu sẵn", /data-t="gaps"[\s\S]{0,40}>Bot bí|cb-tab on" data-t="gaps"/.test(CB));
check("lỗ hổng xếp theo số lần hỏi", /g\.lan/.test(CB));
check("nói rõ mỗi dòng nghĩa là tài liệu đang thiếu", /tài liệu.{0,20}(đang )?thiếu/.test(CB));
// Nguồn phải hiện: không có nó thì "bot trả lời đúng chưa" là câu hỏi không kiểm chứng được.
check("từng lượt hiện NGUỒN bot đã dùng", /t\.nguon/.test(CB));
check("lượt không tìm ra tài liệu bị đánh dấu", /không tìm thấy tài liệu/.test(CB));
check("chưa có lượt nào thì dạy bước tiếp theo", /Nhắn thử cho bot/.test(CB));
check("CSS của nhật ký đã có", /\.cb-tab/.test(CSS) && /\.cb-turn/.test(CSS));

// ============================================================
// 7. Luật chung của dashboard
// ============================================================
check("HTML người dùng nhập đều qua esc()", !/innerHTML\s*=\s*[^;]*\+\s*(b|e)\.(name|message)\b(?![^;]*esc)/.test(CB));
check("không có em dash trong nguồn", CB.indexOf("—") === -1);

console.log("");
if (fails.length) { console.log("ĐỎ " + fails.length + " mục: " + fails.join(", ")); process.exit(1); }
console.log("Tất cả xanh.");
