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
// RAIL_ITEMS nay là danh sách ID phẳng (nhãn lấy từ từ điển i18n).
check("console có mục Chatbot trên thanh bên", /"chatbots"/.test(CON));
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
  /if \(!im\) box\.innerHTML = '<div class="cb-empty">Đang tải…/.test(CB));

// ============================================================
// 6d. Nhóm chưa được bật phải NỔI LÊN thẻ, không được im lặng
// ============================================================
// Chủ repo báo cùng ngày: "cho vào nhóm tag tên để nhắn thì nó không phản hồi". Rào "bot không
// tự nhận việc trong nhóm lạ" là đúng, nhưng cách từ chối thì sai: im hoàn toàn, không log,
// không dòng nào ở đây. "Hành vi đúng" và "bot hỏng" trông y hệt nhau.
check("thẻ hiện nhóm đang chờ chủ cho phép", /b\.nhom_cho/.test(CB) && /cb-nhomcho/.test(CB));
check("cho phép nhóm bằng ĐÚNG một cú bấm",
  /cb-ok-nhom/.test(CB) && /\/groups"/.test(CB) && /choNhom\(b, cid, true\)/.test(CB));
check("và bỏ qua được nhóm không muốn", /cb-bo-nhom/.test(CB) && /choNhom\(b, cid, false\)/.test(CB));
check("CSS cho khối nhóm chờ đã có", /\.cb-nhomcho \{/.test(CSS));
// Khai nhóm ngay lúc TẠO. Bản trước chỉ cho khai ở form Sửa, nên đường đi tự nhiên nhất (tạo
// bot rồi thả thẳng vào nhóm) bảo đảm lần thử đầu của mọi người dùng gặp một con bot im lặng.
check("CANARY: ô nhóm KHÔNG còn bị giấu sau form Sửa",
  !/\(sua \? '<label>Nhóm được phép/.test(CB) && /id="cbGroups"/.test(CB));
check("form tạo cũng gửi nhóm lên server", /groups: gr, reply_when: rw/.test(CB));
check("chọn được khi nào bot lên tiếng trong nhóm", /id="cbReplyWhen"/.test(CB));
// Chế độ riêng tư của Telegram chặn Ở PHÍA TELEGRAM, trước khi Javis nhìn thấy tin nào. Đây là
// nguyên nhân số một của "nhắn riêng thì được, trong nhóm tag tên thì im re", nên cảnh báo phải
// hiện cho MỌI bot có dùng nhóm - không riêng bot đặt "trả lời mọi tin" như bản trước.
check("cảnh báo chế độ riêng tư cho mọi bot có dùng nhóm",
  /var duNhom = \(b\.groups \|\| \[\]\)\.length \|\| \(b\.nhom_cho \|\| \[\]\)\.length/.test(CB) &&
  /duNhom && st\.da_hoi_telegram && !st\.doc_moi_tin_nhom/.test(CB));
check("cảnh báo chỉ ra CẢ HAI cách sửa, không chỉ BotFather",
  /setprivacy/.test(CB) && /quản trị viên/.test(CB));
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

check("kênh hiện trên thẻ bot (huy hiệu ở icon + chip ở phần thông tin)",
  /class="cb-ico-kenh"/.test(CB) && /function chipKenh\(/.test(CB) && /chipKenh\(kenh\)/.test(CB));
check("form hỏi kênh NGAY Ở ĐẦU, trước cả tên bot",
  CB.indexOf("Bot này nói chuyện ở đâu") > -1 &&
  CB.indexOf("Bot này nói chuyện ở đâu") < CB.indexOf("<label>Tên bot</label>"));
check("chọn kênh bằng thẻ bấm có logo, không phải <select> trơn",
  /class="cb-kenh"/.test(CB) && /class="cb-kenh-o/.test(CB) && /cb-kenh-logo/.test(CB));
check("mỗi kênh nói rõ ưu và nhược ngay trên nút",
  /KENH_TOM\s*=/.test(CB) && /chưa gửi được tài liệu/.test(CB));
// Đổi kênh của bot đã tạo = đổi sang một con bot khác (token khác, khách khác). Khoá lại và
// nói thẳng, chứ đừng cho bấm rồi báo lỗi token ở bước sau.
check("sửa bot thì kênh bị KHOÁ kèm lý do",
  /veKenhChon\(kenh, sua\)/.test(CB) && /cb-kenh-khoa/.test(CB) &&
  /Không đổi được kênh của bot đã tạo/.test(CB));
check("đổi kênh là đổi theo cả form (nhãn token, chỗ lấy token, khối nhóm)",
  /function apKenh\(k\)/.test(CB) && /cbTokenLabel/.test(CB) && /cbNhomBox/.test(CB));
check("đổi kênh thì BỎ token đã kiểm (nó là danh tính ở nền tảng kia)",
  /function apKenh\(k\)[\s\S]{0,400}if \(k !== kenh\) uname = "";/.test(CB));
// Hàm này còn chạy MỘT LẦN lúc mở form để dựng trạng thái ban đầu. Bỏ uname vô điều kiện thì
// mở form Sửa rồi bấm Lưu là xoá trắng tên bot đang chạy, và thẻ báo "chưa có token" cho một
// con bot vẫn sống - hỏng im lặng, chỉ lộ ra khi nhìn kỹ thẻ.
check("mở form Sửa mà chưa đổi kênh thì KHÔNG xoá tên bot đang dùng",
  /if \(k !== kenh\) uname = "";/.test(CB) &&
  /sua && k === \(\(b && b\.channel\) \|\| "telegram"\) && uname/.test(CB));
check("kiểm token gửi kèm kênh để hỏi đúng nền tảng",
  /channel: kenh/.test(CB) && /Đang hỏi " \+ kc\.nhan/.test(CB));
check("tạo bot gửi kênh lên server", /channel: kenh,/.test(CB));
check("kênh không vào được nhóm thì ẨN cả khối nhóm, không hiện ra rồi vô tác dụng",
  /cbKhongNhom/.test(CB) && /kc\.co_nhom \? "" : "none"/.test(CB));
check("và KHÔNG gửi id nhóm thừa lên server",
  /var coNhom = kenhCua\(kenh\)\.co_nhom/.test(CB) && /coNhom \? box\.querySelector\("#cbGroups"\)/.test(CB));
check("cảnh báo riêng tư chỉ hiện cho bot Telegram", /kenh === "telegram" && duNhom/.test(CB));
check("bộ lọc kênh chỉ hiện khi có từ hai kênh trở lên",
  /function veLoc\(/.test(CB) && /if \(ks\.length < 2\)/.test(CB));
check("danh sách kênh lấy từ SERVER, không chép cứng ở giao diện",
  /_kenhDS = d\.kenh \|\| \[\]/.test(CB));
check("CSS của bộ chọn kênh đã có",
  /\.cb-kenh-o/.test(CSS) && /\.cb-loc-o/.test(CSS) && /\.cb-ico-kenh/.test(CSS));
check("icons.js không có em dash", ICONS.indexOf("—") === -1);

// ============================================================
// 7. Luật chung của dashboard
// ============================================================
check("HTML người dùng nhập đều qua esc()", !/innerHTML\s*=\s*[^;]*\+\s*(b|e)\.(name|message)\b(?![^;]*esc)/.test(CB));
check("không có em dash trong nguồn", CB.indexOf("—") === -1);

console.log("");
if (fails.length) { console.log("ĐỎ " + fails.length + " mục: " + fails.join(", ")); process.exit(1); }
console.log("Tất cả xanh.");
