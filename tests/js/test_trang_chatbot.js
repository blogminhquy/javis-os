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
// Bảng bí danh lệnh nói ở server: nhãn đổi thì nói tên mới cũng phải mở được đúng trang.
const SRV2 = fs.readFileSync(path.join(ROOT, "server", "ui_targets.py"), "utf8");
// 0.55.14 đưa chữ tiếng Việt của dashboard vào từ điển i18n: chatbots.js gọi `window.t("khoa")`,
// câu chữ nằm ở vi.json. Nên mọi khẳng định về LỜI trang nói phải soi ĐỦ HAI VẾ - giao diện gọi
// đúng khoá, VÀ khoá đó mang đúng câu. Soi một vế thôi là test hở: chỉ kiểm khoá thì đổi nội
// dung khoá thành câu ngược nghĩa vẫn xanh, chỉ kiểm từ điển thì gỡ hẳn dòng chữ khỏi giao diện
// vẫn xanh. Chuỗi dùng để SO SÁNH và khoá tra cứu của object vẫn nằm nguyên trong .js.
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
// Vế 2 dùng chung: khoá `k` trong vi.json có chứa câu `chu` không.
const tu = (k, chu) => String(VI[k] || "").includes(chu);
// Cả hai vế cho ca thường: chatbots.js gọi khoá `k`, và khoá đó mang câu `chu`.
const noi = (k, chu) => CB.includes(k) && tu(k, chu);

// ============================================================
// 1. Trang được đăng ký đúng chỗ
// ============================================================
check("index.html có nạp module trang Chatbot", /chatbots\.js\?v=/.test(HTML));
// So bằng thẻ <script> chứ không bằng tên file: console.js được NHẮC trong hơn chục comment
// nằm phía trên, nên indexOf("console.js") trần trụi trỏ vào comment đầu tiên.
check("nạp TRƯỚC console.js (console gọi window.JavisChatbots)",
  HTML.indexOf('src="/static/chatbots.js') < HTML.indexOf('src="/static/console.js'));
check("module phơi ra đúng một cửa vào", /window\.JavisChatbots\s*=\s*\{\s*render:\s*render\s*\}/.test(CB));
// RAIL_ITEMS nay là danh sách ID phẳng (nhãn lấy từ từ điển i18n). Id `chatbots` VẪN còn (nó
// là nguồn icon + nhãn, và là bí danh cho lệnh nói / bookmark cũ) nhưng KHÔNG được hiện thành
// một mục trên thanh bên: trang Chatbot là tab của trang Hội thoại từ 0.61.0.
check("console vẫn biết id chatbots (nguồn icon, nhãn, bí danh)", /"chatbots"/.test(CON));
// 0.62.5: `chatbots` nằm trong RAIL_AN nhưng KHÔNG nằm trong `ids` của nhóm nào, nên tới
// 0.62.4 nó rơi qua nhánh "mục chưa xếp nhóm" và hiện ra ở CUỐI nhóm Hệ thống - cạnh Tài
// khoản, đúng chỗ chẳng ai ngờ (chủ repo thấy 21/09). Lọc phải áp cho cả nhánh đó.
check("CANARY: mục chưa xếp nhóm cũng phải đi qua RAIL_AN",
  /RAIL_ITEMS\.filter\(i => !seen\.has\(i\.id\) && !RAIL_AN\.has\(i\.id\)\)/.test(CON));
// Hidden items (including chatbots) are checked through railGroups in test_settings_tabs.js.
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
check("có trạng thái rỗng dạy người dùng bước đầu", noi("cb.rong_tieu_de", "Chưa có bot nào"));

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
// 4. Token KHÔNG nằm trong form bot nữa (0.61.1)
// ============================================================
// Trước đó form bot có form dán token riêng, y hệt modal "Thêm tài khoản" của tab Kênh. Hai
// form song song nghĩa là hướng dẫn lấy token của từng kênh bị nhân đôi, và thêm một kênh mới
// là phải sửa cả hai nơi. Nay chỉ còn MỘT chỗ biết dán token (conversations.js), form bot gọi
// lại chính nó - xem test_hoi_thoai_khach.js cho các phép kiểm về token.
check("CANARY: form bot KHÔNG còn ô token", CB.indexOf('id="cbToken"') === -1);
check("CANARY: form bot KHÔNG còn tự gọi verify-token", CB.indexOf("/chatbots/verify-token") === -1);
check("CANARY: form bot KHÔNG còn gửi token lên server", !/chung\.token = /.test(CB));
check("nối kênh mới thì gọi lại modal Thêm tài khoản của tab Kênh",
  /JavisConversations && window\.JavisConversations\.themTaiKhoan/.test(CB) &&
  noi("cb.noi_kenh_moi", "Kết nối kênh mới"));
check("nối xong thì nạp lại danh sách tài khoản và TÍCH SẴN con vừa nối",
  /function noiKenhMoi\(/.test(CB) && /onXong: async function \(tk\)/.test(CB) &&
  /if \(aid\) giu\.push\(aid\)/.test(CB));

// ============================================================
// 5. Nói thật với người dùng về hậu quả
// ============================================================
check("xoá bot có hỏi lại", /confirm\(/.test(CB));
check("xoá nói rõ brain và Agent KHÔNG bị xoá",
  noi("cb.xn_xoa_giu", "KHÔNG bị xoá") && tu("cb.xn_xoa_giu", "Brain và Agent"));
check("form nói rõ bot tạo ra ở trạng thái tắt",
  /<b>' \+\s*\n?\s*esc\(window\.t\("cb\.tao_xong_tat"\)\) \+ '<\/b>/.test(CB)
  && VI["cb.tao_xong_tat"] === "TẮT" && tu("cb.tao_xong_1", "trạng thái"));
check("form nói rõ bot đọc tài liệu của brain nào", noi("cb2.s_ai_hint", "chỉ đọc tài liệu trong brain"));
// Lựa chọn quyết định bot "ăn nhập với Agent" hay không. Bản 0.20.0 ép cứng chế độ chỉ-tài-
// liệu cho mọi bot, và một Agent coach viết rất kỹ vẫn trả lời "em chưa có thông tin" cho
// đúng câu thuộc chuyên môn của nó. Phải cho chọn, và phải giải thích ngay tại chỗ chọn.
check("form cho chọn nguồn trả lời (nút bấm chọn một)", /htmlSeg\("cbNguon", "cbNguon"/.test(CB));
check("mặc định là chuyên môn Agent", /nguon0 = \(b && b\.nguon_tra_loi === "tai_lieu"\) \? "tai_lieu" : "agent"/.test(CB));
check("giải thích khi nào dùng chế độ nào", noi("cb2.nguon_tl_h", "giá và chính sách"));
// Trang phải nói ĐÚNG việc Javis làm: nó không viết luật cho bot, nó chỉ khoá phạm vi brain.
// Hứa nhiều hơn thế là dạy người dùng tin vào một rào không tồn tại.
check("nói rõ Javis không thêm luật của mình vào Agent",
  noi("cb2.nguon_agent_h", "Javis không thêm luật nào của"));
check("nói rõ rào duy nhất là chỉ đọc được brain này",
  CB.includes("cb.intro_chi_doc") && /chỉ đọc\b[\s\S]{0,40}brain này/.test(VI["cb.intro_chi_doc"] || ""));
check("lựa chọn được gửi lên server", /nguon_tra_loi: giaTri\("cbNguon"\)/.test(CB));
check("thẻ bot hiện đang chạy chế độ nào",
  /b\.nguon_tra_loi === "tai_lieu" \? window\.t\("cb\.nguon_tl_ngan"\)/.test(CB)
  && tu("cb.nguon_tl_ngan", "chỉ tài liệu"));
check("trang nói rõ bot không ghi, không có lệnh quản trị",
  noi("cb.intro_5", "không có lệnh quản trị") && tu("cb.intro_5", "không ghi"));

// ============================================================
// 5b. Mức quyền: nới được, nhưng phải NHÌN THẤY cái mình đang trao đi
// ============================================================
// Chủ repo mở phạm vi ngày 2026-08-05: "anh vẫn muốn có thể thực hiện nhiều task, nhưng em
// thêm phần thông báo cho anh để hiểu rõ nguy cơ". Nghĩa là ô chọn mức KHÔNG được là một
// dropdown trơ ba dòng - mỗi mức phải kể ra nó lấy đi cái gì, ngay tại chỗ chọn.
check("form cho chọn mức quyền (ba nút bấm, không phải ô xổ xuống)", /htmlMuc\(muc0\)/.test(CB) && /htmlSeg\("cbMuc", "cbMuc"/.test(CB));
check("có ô đồng ý rủi ro", /id="cbAck"/.test(CB));
check("gửi mức quyền lên server", /muc_quyen: muc/.test(CB));
check("gửi kèm xác nhận đã đọc rủi ro", /xac_nhan_rui_ro: "1"/.test(CB));
// Câu chữ cảnh báo do SERVER cấp. Chép cứng ở giao diện thì một hôm server siết thêm rào mà ô
// cảnh báo vẫn hứa như cũ, và chủ bấm đồng ý dựa trên một câu đã sai.
check("cảnh báo lấy từ server chứ không chép cứng ở giao diện",
  /d\.muc_quyen \|\| \[\]/.test(CB) && /m\.canh_bao/.test(CB));
check("đổi mức là vẽ lại cảnh báo ngay", /input\[name="cbMuc"\]'\)\.forEach[\s\S]{0,160}veCanhBao\(giaTri\("cbMuc"\)\)/.test(CB));
// Chưa tick mà lưu được thì cả khối cảnh báo chỉ là trang trí.
check("chưa tick đồng ý thì không lưu được",
  /can_xac_nhan && !\(ack && ack\.checked\)/.test(CB));
check("mức toàn quyền còn hỏi lại một lần nữa", /muc === "full" &&\s*\n?\s*!confirm\(/.test(CB));
check("cảnh báo nói thẳng người điều khiển là người nhắn cho bot",
  noi("cb.intro_6", "người điều khiển bot là người nhắn cho nó")
  || noi("cb.mq_full", "Người điều khiển là người nhắn cho nó"));
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
// Đổi ý có lý do, ghi lại để khỏi quay về: bản trước bỏ trống nhãn cho mức chỉ đọc vì "mặc
// định thì không cần dán nhãn". Nhưng ô trống đọc ra được HAI nghĩa ngược nhau - bot đang chỉ
// đọc, hay trang này không nói? Chủ repo hỏi đúng câu đó (2026-08-06) khi nhìn một thẻ không
// có dòng mức nào. Nay cả ba mức đều có nhãn, mức chỉ đọc mang màu xám để vẫn phân biệt được
// từ xa với hai mức có quyền thao tác.
check("thẻ bot dán nhãn mức quyền ở CẢ BA mức, kể cả chỉ đọc",
  !/mq === "suggest" \? "" :/.test(CB) && /cb-quyen ' \+ \(mq === "full"/.test(CB));
check("mức chỉ đọc có màu riêng chứ không mượn màu cảnh báo",
  /\.cb-quyen\.doc \{/.test(CSS) && /"doc"\)/.test(CB));
check("bật bot có quyền thao tác thì hỏi lại", /if \(on && mucCua\(mq\)\.can_xac_nhan/.test(CB));
check("CSS cho nhãn mức quyền và khối cảnh báo",
  /\.cb-quyen\.full/.test(CSS) && /\.cb-canhbao\.full/.test(CSS) && /\.cb-ack/.test(CSS));
// Hai rào KHÔNG đổi theo mức, và trang phải nói đúng như vậy - hứa thiếu thì chủ ngại nâng
// mức một cách vô cớ, hứa thừa thì chủ tin vào một rào không tồn tại.
check("trang nói rõ hai rào giữ nguyên ở mọi mức",
  noi("cb.intro_7", "không thấy brain khác, và không chạy được lệnh máy"));

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
check("trang nói rõ đang xem bot của brain nào",
  /window\.t\("cb\.intro_1"\)\) \+ ' <b>' \+ esc\(brain\(\)\)/.test(CB)
  && tu("cb.intro_1", "Bot của brain"));
check("trang chỉ cách xem brain khác", noi("cb.intro_8", "Đổi brain ở đầu trang"));
// Thẻ bot bỏ dòng brain: mọi bot ở đây đều cùng một brain nên nhắc lại từng thẻ chỉ là nhiễu.
check("thẻ bot không nhắc lại brain", !/ic\("brain"\) \+ ' ' \+ esc\(b\.brain\)/.test(CB));
// Trang "Agents" riêng đã gộp vào trang Cộng sự, nên nút này phải dẫn tới "workspace": dẫn
// sang một id trang không còn tồn tại thì rail không sáng mục nào và khung giữa trắng trơn.
check("có nút sang trang Cộng sự để tạo trợ lý", /id="cbNewAgent"/.test(CB) && /JavisNav\.go\("workspace"\)/.test(CB));
// Vai trò dài làm <option> tràn ngang khỏi hộp, mà <option> thì không tạo kiểu được.
check("vai trò Agent bị cắt ngắn trước khi vào option", /vai\.slice\(0, 34\)/.test(CB));
check("CSS chặn select nở rộng ra khỏi form", /\.cb-form select \{[^}]*text-overflow: ellipsis/.test(CSS));
// Kiểm Ý NGHĨA (có cửa `go` cho module ngoài gọi), không khoá cứng hình dạng: 0.57.5 đổi
// `{ go: navigateTo }` thành object có thêm openGroup/setCollapsed và `go` đi qua store Alpine
// để bung luôn nhóm chứa trang. Khoá cứng nguyên văn thì mỗi lần thêm cửa là test đỏ oan.
check("console phơi cửa chuyển trang cho module ngoài",
  /window\.JavisNav = \{/.test(CON) && /\bgo\((id)?\)/.test(CON));
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
check("lượt không tìm ra tài liệu bị đánh dấu", noi("cb.khong_tai_lieu", "không tìm thấy tài liệu"));
check("chưa có lượt nào thì dạy bước tiếp theo", noi("cb.chua_luot_goi_y", "Nhắn thử cho bot"));
check("CSS của nhật ký đã có", /\.cb-tab/.test(CSS) && /\.cb-turn/.test(CSS));

// ============================================================
// 6c. Thẻ phải TỰ CẬP NHẬT - trạng thái bot đổi mà không ai bấm gì
// ============================================================
// Chủ repo báo (2026-08-06): "bot đã chạy rồi, đã khởi động rồi mà vẫn hiện đang khởi động".
// Đúng vậy: bấm Bật xong server trả về "starting" (poller vừa tạo, chưa kịp hỏi Telegram), rồi
// vài giây sau nó thành "polling" - nhưng trang chỉ nạp lại khi người dùng bấm cái gì đó. Thẻ
// đứng nguyên ở "Đang khởi động" cho tới lúc rời trang rồi quay lại. Nhịp tự làm mới cũng là
// thứ DUY NHẤT phát hiện được bot vừa chết.
check("trang có nhịp tự làm mới", /setInterval\(/.test(CB) && /nhipTuLamMoi/.test(CB));
check("nhịp dừng khi rời trang (node bị tháo khỏi DOM)",
  /document\.body\.contains\(_host\)/.test(CB) && /clearInterval\(_timer\)/.test(CB));
check("tab bị ẩn thì không gọi mạng vô ích", /document\.hidden/.test(CB));
check("đang mở form thì không vẽ lại dưới chân người dùng",
  /querySelector\("\.cb-modal"\)/.test(CB));
// Nạp NGẦM khác nạp do người bấm: không được xoá lưới đang hiện để thay bằng "Đang tải…", và
// mạng hỏng một nhịp thì giữ nguyên màn hình cũ. Nhấp nháy mỗi 5 giây tệ hơn số cũ vài giây.
check("nạp ngầm không nhấp nháy màn hình", /async function tai\(im\)/.test(CB) &&
  /if \(!im\) box\.innerHTML = '<div class="cb-empty">' \+ esc\(window\.t\("common\.loading"\)\)/.test(CB)
  && tu("common.loading", "Đang tải"));

// ============================================================
// 6d. Nhóm chưa được bật phải NỔI LÊN thẻ, không được im lặng
// ============================================================
// Chủ repo báo cùng ngày: "cho vào nhóm tag tên để nhắn thì nó không phản hồi". Rào "bot không
// tự nhận việc trong nhóm lạ" là đúng, nhưng cách từ chối thì sai: im hoàn toàn, không log,
// không dòng nào ở đây. "Hành vi đúng" và "bot hỏng" trông y hệt nhau.
check("thẻ hiện nhóm đang chờ chủ cho phép", /b\.nhom_cho/.test(CB) && /cb-nhomcho/.test(CB));
check("cho phép nhóm bằng ĐÚNG một cú bấm",
  /cb-ok-nhom/.test(CB) && /\/groups"/.test(CB) && /choNhom\(b, cid, true, loai\)/.test(CB));
check("và bỏ qua được nhóm không muốn", /cb-bo-nhom/.test(CB) && /choNhom\(b, cid, false, loai\)/.test(CB));
check("CSS cho khối nhóm chờ đã có", /\.cb-nhomcho \{/.test(CSS));
// Khai nhóm ngay lúc TẠO. Bản trước chỉ cho khai ở form Sửa, nên đường đi tự nhiên nhất (tạo
// bot rồi thả thẳng vào nhóm) bảo đảm lần thử đầu của mọi người dùng gặp một con bot im lặng.
check("CANARY: ô nhóm KHÔNG còn bị giấu sau form Sửa",
  !/\(sua \? '<label>Nhóm được phép/.test(CB) && /id="cbPk"/.test(CB));
check("form tạo cũng gửi nhóm và người lên server",
  /groups: co \? ds\("group"\)\.join/.test(CB) && /audience: aud, people: ds\("private"\)/.test(CB));
check("chọn được khi nào bot lên tiếng trong nhóm", /htmlSeg\("cbRw", "cbRw"/.test(CB));
check("có lựa chọn Tự đánh giá (reply_when=auto) trong nút chọn khi nào bot lên tiếng",
      /v: "auto"/.test(CB) && /cb2\.rw_auto/.test(CB));
check("thẻ bot nêu đúng chế độ Tự đánh giá, không gộp vào 'khi được gọi tên'",
      /reply_when === "auto"[\s\S]{0,80}cb\.tl_tu_danh_gia/.test(CB));
check("gợi ý chế độ riêng tư chỉ hiện khi có tài khoản Telegram (Zalo không có @BotFather)",
      /class="cb-hint cb-chi-tg" id="cbRwTg"/.test(CB) && /a\.channel === "telegram"[\s\S]{0,160}cbRwTg/.test(CB));
check("lựa chọn 'được gọi tên' KHÔNG được chọn sẵn khi bot đang ở Tự đánh giá",
      /var rw0 = \(b && \(b\.reply_when === "auto" \|\| b\.reply_when === "always"\)\) \? b\.reply_when : "mention"/.test(CB));
// Chế độ riêng tư của Telegram chặn Ở PHÍA TELEGRAM, trước khi Javis nhìn thấy tin nào. Đây là
// nguyên nhân số một của "nhắn riêng thì được, trong nhóm tag tên thì im re", nên cảnh báo phải
// hiện cho MỌI bot có dùng nhóm - không riêng bot đặt "trả lời mọi tin" như bản trước.
check("cảnh báo chế độ riêng tư cho mọi bot có dùng nhóm",
  /var duNhom = \(b\.groups \|\| \[\]\)\.length \|\| \(b\.nhom_cho \|\| \[\]\)\.length/.test(CB) &&
  /duNhom && st\.da_hoi_telegram && !st\.doc_moi_tin_nhom/.test(CB));
// `/setprivacy` là LỆNH gõ cho BotFather nên cố ý không dịch, vẫn nằm thẳng trong .js.
check("cảnh báo chỉ ra CẢ HAI cách sửa, không chỉ BotFather",
  /setprivacy/.test(CB) && noi("cb.rt_quan_tri", "quản trị viên"));
// getMe hỏng: bot trả lời tin nhắn riêng hoàn hảo nhưng điếc trong mọi nhóm, vì không biết
// @username của chính mình. Chấm vẫn xanh, lượt vẫn chạy - không có dòng này thì không ai đoán ra.
check("thẻ nói ra khi bot không hỏi được danh tính của chính nó",
  /st\.loi_danh_tinh/.test(CB) && /loiTen/.test(CB));

// ============================================================
// 6b. Hai KÊNH: chọn đúng chỗ, và không lẫn con nọ với con kia
// ============================================================
// Từ 0.26.5 bot chạy được trên Telegram HOẶC Zalo. Hai con bot khác nền tảng nằm cạnh nhau
// trong cùng một lưới thẻ mà chỉ khác nhau ở một chữ nhỏ thì người ta sẽ bấm nhầm, và bấm
// nhầm ở đây nghĩa là sửa nhầm con bot đang nói chuyện với khách.
const ICONS = D("icons.js");
check("có dấu hiệu kênh vẽ sẵn cho cả hai nền tảng",
  /telegram:\s*\{/.test(ICONS) && /zalo:\s*\{/.test(ICONS) && /function kenh\(id, opts\)/.test(ICONS));
check("dấu hiệu kênh giữ MÀU thương hiệu, không theo màu chữ như icon Lucide",
  /#229ED9/.test(ICONS) && /#0068FF/.test(ICONS));
check("Telegram là máy bay giấy trắng trên nền xanh",
  /rect width="24" height="24" rx="7" fill="#229ED9"/.test(ICONS) && /fill="#fff"/.test(ICONS));
check("Zalo là chữ Z trắng trong bong bóng trò chuyện xanh",
  /zalo:[\s\S]{0,400}fill="#0068FF"[\s\S]{0,600}M8\.5 7\.9h7\.05/.test(ICONS));
check("kênh lạ trả rỗng chứ không vẽ dấu hỏi", /if \(!k\) return "";/.test(ICONS));

// 0.61.0: bot TRỎ tới tài khoản kênh (một bot trực được nhiều tài khoản), kênh không còn là
// một trường của bot. Thẻ hiện một chip cho MỖI tài khoản; huy hiệu ở icon chỉ khi có đúng một.
check("kênh hiện trên thẻ bot (huy hiệu ở icon khi một tài khoản + chip cho từng tài khoản)",
  /class="cb-ico-kenh"/.test(CB) && /function chipTK\(/.test(CB) && /\.map\(chipTK\)/.test(CB));
check("form hỏi KÊNH NGAY Ở ĐẦU, trước cả tên bot",
  tu("cb.lb_tai_khoan", "kênh") && CB.indexOf('window.t("cb.lb_tai_khoan")') > -1 &&
  CB.indexOf('window.t("cb.lb_tai_khoan")') < CB.indexOf('"cb2.s_ai"'));
check("tích được NHIỀU kênh (cùng một vai trực Telegram, Zalo Bot lẫn Zalo cá nhân)",
  /class="cb-tk-o"/.test(CB) && /account_ids: ids\.join\(","\)/.test(CB) && tu("cb.hint_tai_khoan", "nhiều kênh"));
// 0.64.80: chọn Zalo cá nhân thì nói thẳng bot trả lời DƯỚI TÊN chủ. Đọc theo `kind` server khai.
check("kênh kiểu tài khoản (Zalo cá nhân) có dòng lưu ý ngay lúc chọn",
  /k\.kind === "account"/.test(CB) && /cb\.tk_ca_nhan_luu_y/.test(CB) &&
  tu("cb.tk_ca_nhan_luu_y", "dưới tên bạn") && !!EN["cb.tk_ca_nhan_luu_y"]);
// CANARY: giao diện KHÔNG đoán gì theo id kênh. Logo, nhãn, năng lực đều từ danh sách server;
// thêm kênh ở server là trang này vẽ được ngay, không sửa một dòng nào ở đây.
check("CANARY: không rẽ nhánh theo id kênh (logo qua kenhCua().logo, không Icons.kenh(kenh) trực tiếp)",
  /function logoKenh\(/.test(CB) && !/Icons\.kenh\(kenh/.test(CB) && !/Icons\.kenh\(k\.id/.test(CB)
  && !/=== "zalo"/.test(CB));
check("không tài khoản nào vào được nhóm thì ẨN cả khối nhóm, không hiện ra rồi vô tác dụng",
  /function coNhomForm\(/.test(CB) && /#cbRwBox"\)\.style\.display = co \? "" : "none"/.test(CB) &&
  /\.cb-rc\[data-v="all"\]'\)\.style\.display = co \? "" : "none"/.test(CB));
check("và KHÔNG gửi id nhóm thừa lên server",
  /var co = coNhomForm\(\)/.test(CB) && /groups: co \? ds\("group"\)\.join\("\\n"\) : ""/.test(CB));
check("thẻ bot nói thẳng khi chưa có kênh nào",
  noi("cb.chua_token", "chưa có kênh"));
check("mở form từ tab Tài khoản bot với tài khoản tích sẵn", /javis:chatbot-new/.test(CB) && /chonSan/.test(CB));
check("cảnh báo riêng tư chỉ hiện khi bot có tài khoản Telegram",
  /a\.channel === "telegram"/.test(CB) && /coTelegram && duNhom/.test(CB));
check("bộ lọc kênh chỉ hiện khi có từ hai kênh trở lên",
  /function veLoc\(/.test(CB) && /if \(ks\.length < 2\)/.test(CB));
check("danh sách kênh lấy từ SERVER, không chép cứng ở giao diện",
  /_kenhDS = d\.kenh \|\| \[\]/.test(CB));
check("CSS của bộ chọn kênh đã có",
  /\.cb-kenh-o/.test(CSS) && /\.cb-loc-o/.test(CSS) && /\.cb-ico-kenh/.test(CSS));
check("icons.js không có em dash", ICONS.indexOf("—") === -1);

// ============================================================
// 6e. Form tạo bot đi HAI BƯỚC (0.61.1)
// ============================================================
// Chủ repo báo (2026-09-21) khi nhìn form trên điện thoại: "phần lựa chọn kênh này quá nhiều
// ghi chú và phức, cách chọn kênh cũng sẽ không có tính mở rộng về sau". Đúng vậy: một màn
// duy nhất phải cõng cả chọn tài khoản, dán token, hướng dẫn riêng của từng kênh, tên bot,
// Agent, nguồn trả lời, mức quyền, ngôn ngữ, chuyển người thật và nhóm. Người dùng cuộn qua
// một trang chú thích trước khi thấy ô Tên bot, và mỗi kênh thêm vào là dài thêm một khối nữa.
check("có hai bước, bước 1 chọn chỗ trả lời và bước 2 mới cài đặt",
  /id="cbB1"/.test(CB) && /id="cbB2"/.test(CB) && /function veBuoc\(n\)/.test(CB));
check("bước 1 chỉ hỏi bot trả lời ở đâu, KHÔNG hỏi tên bot",
  CB.indexOf('id="cbB1"') < CB.indexOf('window.t("cb.lb_tai_khoan")') &&
  CB.indexOf('window.t("cb.lb_tai_khoan")') < CB.indexOf('id="cbB2"') &&
  CB.indexOf('id="cbB2"') < CB.indexOf('"cb2.s_ai"'));
check("nói rõ đang ở bước mấy", noi("cb.buoc_may", "Bước {n}") && /id="cbBuoc"/.test(CB));
// Chưa tích tài khoản nào mà sang được bước 2 thì bot tạo ra không có chỗ nào để trả lời.
check("chưa chọn tài khoản thì không sang được bước 2",
  /function sangBuoc2\(\)[\s\S]{0,160}if \(!tkDangChon\(\)\.length\) return alert/.test(CB));
// Sang bước 2 là mất dấu lựa chọn vừa làm nếu không tóm tắt lại, và người dùng phải lùi lại
// chỉ để nhìn cho chắc.
check("bước 2 tóm tắt lại bot sẽ trả lời ở đâu, kèm lối quay lại đổi",
  /function veTom\(\)/.test(CB) && /class="cb-doi-tk"/.test(CB) &&
  noi("cb.tra_loi_o", "Trả lời ở") && noi("cb.doi", "Đổi"));
check("sửa bot thì vào thẳng bước 2 (tài khoản đã chọn rồi)", /var buoc = sua \? 2 : 1;/.test(CB));
// Một cặp nút cố định đọc dễ hơn hai hàng nút hiện ra rồi biến đi, và trên điện thoại ngón
// tay luôn tìm thấy chúng ở đúng chỗ cũ.
check("hai nút ở chân form đổi vai theo bước chứ không mọc thêm hàng nút",
  /id="cbLui"/.test(CB) && /id="cbTien"/.test(CB) &&
  noi("cb.quay_lai", "Quay lại") && noi("cb.tiep_tuc", "Tiếp tục"));
// Ba ô có mặc định dùng được ngay mới được gấp. Mức quyền thì KHÔNG: đọc sót nó là mất tiền
// thật, nên nó phải nằm phơi ra trên màn hình chứ không phải sau một cú bấm.
check("chỉ ngôn ngữ gấp vào Nâng cao; nhóm và người nằm ở phần Bot trả lời ai, ngoài khối gấp",
  /class="cb-nangcao"/.test(CB) && noi("cb.nang_cao", "Nâng cao: ngôn ngữ trả lời") &&
  CB.indexOf('class="cb-nangcao"') < CB.indexOf('id="cbNgonNgu"') &&
  CB.indexOf('id="cbPk"') < CB.indexOf('class="cb-nangcao"') && !/id="cbNhomBox"/.test(CB));
// 0.64.83: chủ dự án bỏ ô "người trực nhận chuyển tiếp" (Chat ID Telegram, vô nghĩa với bot Zalo).
check("form KHÔNG còn ô người trực nhận chuyển tiếp và không gửi handoff_to lên server",
  !/id="cbHandoff"/.test(CB) && !/handoff_to:\s*ho/.test(CB) && !/cb\.lb_handoff/.test(CB));
check("thẻ bot KHÔNG còn nhãn cảnh báo 'chưa đặt người nhận' (hết chỗ để đặt)",
  !/cb\.chua_nguoi_nhan/.test(CB));
// 0.64.85: form một cuộn, bốn phần theo đúng thứ tự, phần "bot trả lời ai" là phần nổi bật thứ hai.
check("bốn phần theo đúng thứ tự: Bot là ai, Bot trả lời ai, Bot dựa vào đâu, Bot được làm gì",
  CB.indexOf('secH("bot", "cb2.s_ai")') > -1 &&
  CB.indexOf('secH("bot", "cb2.s_ai")') < CB.indexOf('secH("users", "cb2.s_doituong")') &&
  CB.indexOf('secH("users", "cb2.s_doituong")') < CB.indexOf('secH("book-open", "cb2.s_nguon")') &&
  CB.indexOf('secH("book-open", "cb2.s_nguon")') < CB.indexOf('secH("shield", "cb2.s_quyen")'));
check("'Bot trả lời ai' có bốn thẻ chọn: tự động hóa tất cả, mọi cuộc chat, nhóm thì chọn, chỉ người và nhóm chọn",
  /htmlThe\("auto"/.test(CB) && /htmlThe\("all"/.test(CB) && /htmlThe\("nhom"/.test(CB) && /htmlThe\("chon"/.test(CB) &&
  /name="cbAud"/.test(CB) && tu("cb2.aud_all_t", "Mọi cuộc chat") && tu("cb2.aud_chon_t", "Chỉ người và nhóm") &&
  tu("cb2.aud_auto_t", "Tự động hóa tất cả"));
// 0.65.2: thẻ Tự động hóa tất cả là MỘT CÚ CHỌN gộp hai cài đặt cũ, không phải giá trị lưu mới.
check("thẻ Tự động hóa tất cả lưu thành audience=all + reply_when=auto (server không thêm giá trị mới)",
  /var aud = the === "auto" \? "all" : the;/.test(CB) &&
  /reply_when: co \? \(the === "auto" \? "auto" : \(giaTri\("cbRw"\) \|\| "mention"\)\) : "mention"/.test(CB));
check("bot đã cài mọi cuộc chat + tự đánh giá từ trước tự hiện đúng thẻ này khi mở lại",
  /var card0 = \(aud0 === "all" && rw0 === "auto"\) \? "auto" : aud0;/.test(CB) &&
  /htmlThe\("auto", card0/.test(CB) && /htmlThe\("nhom", card0/.test(CB));
check("thẻ này ẨN nút chọn khi nào lên tiếng (đã quyết sẵn), và thẻ 'mọi cuộc chat' bỏ nút Tự đánh giá",
  /id="cbRwSeg"/.test(CB) && /#cbRwSeg"\)\.style\.display = tuDong \? "none" : ""/.test(CB) &&
  /card === "all" \? "none" : ""/.test(CB));
check("thẻ này đòi cùng ô tick xác nhận với 'mọi cuộc chat' (và nói thêm chuyện ghi chữ chat để học)",
  /\(aud === "all" \|\| aud === "auto"\) && !\(sua && b\.audience === "all"\)/.test(CB) &&
  /cb2\.aud_auto_ack/.test(CB) && tu("cb2.aud_auto_ack", "ghi lại chữ chat") && /id="cbAckAudT"/.test(CB));
check("kênh không có nhóm thì ẩn cả thẻ Tự động hóa tất cả và rơi về 'nhắn riêng thoải mái'",
  /\.cb-rc\[data-v="auto"\]'\)\.style\.display = co \? "" : "none"/.test(CB) &&
  /!co && \(aud === "all" \|\| aud === "auto"\)/.test(CB) && /!co && \(the === "all" \|\| the === "auto"\)/.test(CB));
check("thẻ bot gọi tên chế độ này là 'tự động hóa tất cả', không kèm dòng bộ phán xử thừa",
  /aud === "all" && cn && b\.reply_when === "auto"\) return window\.t\("cb2\.tt_auto"\)/.test(CB) &&
  /!\(b\.audience === "all" && b\.reply_when === "auto"\)/.test(CB) && tu("cb2.tt_auto", "tự động hóa tất cả"));
check("chữ mô tả Tự đánh giá không còn nói về cửa từ khoá cũ", !/từ khoá|tài liệu của nó trả lời được/.test(VI["cb2.rw_auto_h"]) &&
  /ngữ cảnh/.test(VI["cb2.rw_auto_h"]));
check("chọn 'mọi cuộc chat' phải tick xác nhận rủi ro (server cũng chặn lần nữa)",
  /id="cbAckAud"/.test(CB) && /cb2\.can_ack_aud/.test(CB) && tu("cb2.aud_all_ack", "bạn bè và người nhà"));
check("ô chọn người/nhóm lấy danh sách từ Hộp thư qua /chatbots/chats, không bắt dán id",
  /\/chatbots\/chats\?account_ids=/.test(CB) && /id="cbPkQ"/.test(CB) && /id="cbPkAdd"/.test(CB) &&
  tu("cb2.pk_cho", "Chờ bạn cho phép"));
check("kênh không có nhóm thì ẨN thẻ 'mọi cuộc chat' và đổi chữ hai thẻ còn lại",
  /aud_moi_t/.test(CB) && /aud_chon_ko_t/.test(CB));
check("thẻ bot có một dòng 'Trả lời: ...' và menu '...' cho việc phụ",
  /tomTatDoiTuong\(b\)/.test(CB) && /class="cb-mn"/.test(CB) && /class="cb-mn-l" hidden/.test(CB) &&
  /cb-log/.test(CB) && /cb-hoi-thoai/.test(CB) && /cb-del/.test(CB));
check("hàng chờ duyệt có cả người, nút Cho phép gọi /people cho người và /groups cho nhóm",
  /\/people"/.test(CB) && /cb2\.cho_nguoi/.test(CB) && /data-loai=/.test(CB));
check("cảnh báo mức quyền gọn: hiện 2 câu đầu, còn lại sau 'Xem đủ rủi ro'",
  /const HIEN|var HIEN = 2/.test(CB) && /class="cb-xem-du"/.test(CB) && tu("cb2.xem_du", "Xem đủ rủi ro"));
check("mọi khoá cb2.* giao diện dùng đều có trong tiếng Việt và tiếng Anh", (function () {
  var ks = {};
  (CB.match(/"cb2\.[a-z_]+"/g) || []).forEach(function (k) { ks[k.slice(1, -1)] = 1; });
  var thieu = Object.keys(ks).filter(function (k) { return !VI[k] || !EN[k]; });
  if (thieu.length) console.log("  thiếu:", thieu.join(", "));
  return Object.keys(ks).length > 30 && !thieu.length;
})());
check("CANARY: mức quyền KHÔNG bị gấp vào khối Nâng cao",
  CB.indexOf('htmlMuc(muc0)') > -1 && CB.indexOf('htmlMuc(muc0)') < CB.indexOf('class="cb-nangcao"'));
check("CSS của form hai bước đã có",
  /\.cb-wizard \.cb-form-acts/.test(CSS) && /\.cb-buoc \{/.test(CSS) &&
  /\.cb-tom \{/.test(CSS) && /\.cb-nangcao \{/.test(CSS) &&
  /\.cb-rc \{|\.cb-form label\.cb-rc \{/.test(CSS) && /\.cb-seg \{/.test(CSS) && /\.cb-pk \{/.test(CSS) &&
  /\.cb-mn \{/.test(CSS));
// Gõ lại đúng cái tên vừa đọc ở bước trước là việc thừa.
check("gợi sẵn tên bot từ tài khoản vừa chọn",
  /if \(!ten\.value\.trim\(\)\) ten\.value = \(tkDangChon\(\)\[0\] \|\| \{\}\)\.ten/.test(CB));

// ============================================================
// 6b. Thẻ phải nói bot chạy MODEL nào (0.62.3)
// ============================================================
// Từ 0.62.3 bot mượn model của Agent nó trỏ tới, không còn luôn chạy model chính. Không hiện
// ra thì chọn model cho trợ lý xong vẫn không có cách nào biết bot đã theo hay chưa.
check("thẻ bot hiện model đang chạy", /b\.agent_model \|\| window\.t\("cb\.model_chinh"\)/.test(CB));
check("agent để Mặc định thì nói rõ là theo model chính, không để trống",
  CB.indexOf('window.t("cb.model_chinh")') !== -1);

// ============================================================
// 6c. Nhãn trang và ba tab (0.62.5)
// ============================================================
// Chủ repo chốt 21/09: thanh bên gọi trang này là "Chatbot", ba tab là Hòm thư bot /
// Tài khoản bot / Tạo chatbot. Nhãn nằm trong từ điển, nên canary soi từ điển.
check("thanh bên gọi trang này là Chatbot", VI["page.conversations.label"] === "Chatbot");
check("ba tab đúng tên mới",
  VI["ht.tab_inbox"] === "Hòm thư bot" && VI["ht.tab_kenh"] === "Kênh của bot" &&
  VI["ht.tab_chatbot"] === "Tạo chatbot");
check("nói tên mới cũng mở đúng trang",
  SRV2.includes('"hom thu bot": "conversations"') && SRV2.includes('"tai khoan bot": "conversations"') && SRV2.includes('"kenh cua bot": "conversations"') &&
  SRV2.includes('"tao chatbot": "chatbots"'));

// ============================================================
// 7. Luật chung của dashboard
// ============================================================
check("HTML người dùng nhập đều qua esc()", !/innerHTML\s*=\s*[^;]*\+\s*(b|e)\.(name|message)\b(?![^;]*esc)/.test(CB));
check("không có em dash trong nguồn", CB.indexOf("—") === -1);

console.log("");
if (fails.length) { console.log("ĐỎ " + fails.length + " mục: " + fails.join(", ")); process.exit(1); }
console.log("Tất cả xanh.");
