/* Thanh mốc hội thoại: nhảy nhanh về một câu hỏi cũ trong khung chat.

       node tests/js/test_moc_hoi_thoai.js

   Người dùng Trưng Minh đề nghị qua chủ repo (2026-08-12): quen ChatGPT, ở đó cột phải có một
   dãy vạch nhỏ, mỗi vạch là một câu mình đã hỏi; rê vào hiện danh sách để nhảy thẳng về prompt
   cũ. Hội thoại dài mà thiếu cái này thì tìm lại một câu hỏi cũ phải kéo tay cả khung.

   HÀNH VI đã đo trong Chromium THẬT trước khi chốt (18 phép thử: chèn lười, đếm vạch, rê chuột
   mở danh sách, bấm nhảy đúng chỗ, vạch sáng đi theo vị trí cuộn, 60 câu hỏi không tràn khung,
   xoá hết thì tự tháo, màn hẹp thì không bày ra). Chính lượt đo đó bắt được một lỗi đọc code
   không thấy: đường ngắm đặt sát mép trên làm vạch sáng lệch một câu so với thứ đang chiếm màn
   hình. CI chỉ có node nên file này khoá phần hợp đồng đọc được từ mã nguồn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const JS = D("chat-marks.js");
const CSS = D("style.css");
const HTML = D("index.html");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Có mặt và được nạp
// ============================================================
check("index.html nạp chat-marks.js", /chat-marks\.js/.test(HTML));
check("module không đụng vào app.js",
  !/chat-marks/.test(fs.readFileSync(path.join(ROOT, "dashboard", "app.js"), "utf8")));

// ============================================================
// 2. Ba quyết định kiến trúc - mỗi cái đều có cách làm sai trông hợp lý hơn
// ============================================================
// (a) Theo dõi KẾT QUẢ chứ không hook từng chỗ thêm tin. Hook appendUserMessage + lúc nạp hội
//     thoại cũ + lúc xoá chat là ba chỗ, và chỗ thứ tư sinh sau sẽ không ai nhớ hook.
check("CANARY: dựng lại theo MutationObserver, không đi hook từng chỗ",
  /new MutationObserver/.test(JS));
// Nghe subtree là dựng lại hàng chục lần mỗi câu trả lời (bong bóng vẽ lại theo từng chữ),
// trong khi số câu HỎI có đổi đâu.
check("CANARY: chỉ nghe childList, KHÔNG nghe subtree",
  /observe\([^)]*\{\s*childList:\s*true\s*\}\)/.test(JS) && !/subtree:\s*true/.test(JS));

// (b) Thanh là CON của #chatArea. #chatArea bị dời qua lại giữa màn chính và trang Trò chuyện
//     (console.js mượn node); là con thì nó đi theo, là lớp fixed thì phải tự dò xem khung vừa
//     nhảy đi đâu.
check("CANARY: chèn vào trong #chatArea (đi theo khi khung bị mượn)",
  /chatArea\.insertBefore\(boc/.test(JS));
check("CANARY: dùng position sticky, không phải fixed",
  /#chatMarks \{[^}]*position: sticky/.test(CSS) && !/#chatMarks \{[^}]*position: fixed/.test(CSS));
// height:0 + align-self:flex-end: .transcript là flex DỌC nên một flex item bình thường sẽ
// chiếm nguyên một hàng ngang và đẩy hết tin nhắn xuống.
check("CANARY: cao 0 nên không chiếm hàng, không đẩy tin nhắn xuống",
  /#chatMarks \{[^}]*height: 0/.test(CSS));

// (c) Chèn LƯỜI. `.transcript:empty::after` là câu mời "Nói hoặc gõ để bắt đầu" - chèn một node
//     con thường trực là #chatArea không còn :empty và câu đó biến mất IM LẶNG. Cùng cái bẫy đã
//     ghi sẵn trong app.js cho #newMsgBtn.
check("CANARY: câu mời khi khung rỗng vẫn còn trong CSS",
  /\.transcript:empty::after/.test(CSS));
check("CANARY: có đường THÁO node ra khi không đủ mốc", /function thaoRa\(/.test(JS));
check("dưới ngưỡng thì tháo, không để lại node rỗng",
  /moc\.length < TOI_THIEU\) \{ thaoRa\(\); return; \}/.test(JS));
check("1 câu hỏi thì chưa bày thanh ra", /TOI_THIEU = 2/.test(JS));

// ============================================================
// 3. Nhảy tới đúng chỗ ở CẢ HAI trang
// ============================================================
// offsetTop đo theo offsetParent, mà #chatArea bị dời qua lại nên offsetParent đổi theo. Hiệu
// hai getBoundingClientRect thì đúng ở mọi chỗ đứng - đây đúng loại lỗi chỉ lộ ở một trang.
check("CANARY: cuộn tính bằng hiệu rect, KHÔNG bằng offsetTop",
  /getBoundingClientRect\(\)\.top - chatArea\.getBoundingClientRect\(\)\.top/.test(JS)
  && !/\.offsetTop/.test(JS));
check("nhảy xong có nháy vào đúng bong bóng vừa tới", /cm-vua-nhay/.test(JS) && /cm-vua-nhay/.test(CSS));

// ============================================================
// 4. Vạch sáng phải khớp thứ đang CHIẾM màn hình
// ============================================================
// Lỗi đo được trong Chromium: đường ngắm sát mép trên thì màn hình đã hiện rõ câu hỏi 4 mà thanh
// vẫn sáng vạch 3, chỉ vì đuôi câu trả lời 3 còn sót vài chục pixel trên đỉnh.
check("CANARY: đường ngắm hạ xuống khỏi mép trên", /clientHeight \* 0\.4/.test(JS));
check("đường ngắm có trần, hội thoại câu ngắn không nhảy vọt", /Math\.min\(180,/.test(JS));
check("cập nhật vạch sáng theo cuộn, có ghìm bằng rAF",
  /requestAnimationFrame/.test(JS) && /addEventListener\("scroll"/.test(JS));

// ============================================================
// 4b. Rê vào phải TỚI ĐƯỢC danh sách
// ============================================================
// Chủ repo báo bản đầu (2026-08-12): "hover vào nó đang bị hiện hơi xa trỏ nên không trỏ được".
// Hộp neo ở ĐỈNH khung trong khi chùm vạch nằm GIỮA, nên giữa hai thứ là một vùng không thuộc
// hover; chuột đi chéo qua đó là rời vùng và hộp tắt trước khi tới nơi.
//
// Gốc của cái sai: #chatMarks cao 0, mà mọi phần trăm dọc tính trên nó đều ra 0. Đưa hộp vào
// TRONG .cm-ray (cao thật) thì top:50% mới có nghĩa.
check("CANARY: hộp nằm trong .cm-ray để căn giữa được theo phần trăm",
  /ray\.innerHTML = rayHtml \+ '<div class="cm-hop"/.test(JS));
check("CANARY: hộp căn giữa theo chiều dọc, ngang hàng chùm vạch",
  /\.cm-hop \{[^}]*top: 50%[^}]*transform: translateY\(-50%\)/.test(CSS));
check("CANARY: hộp DÍNH vào dãy vạch, không chừa khe (right:100%)",
  /\.cm-hop \{[^}]*right: 100%/.test(CSS));
check("hộp không tràn ra ngoài khung chat", /max-height: min\(420px, calc\(100% - 16px\)\)/.test(CSS));
// Lớp bảo hiểm thứ hai: chuột người ta đi không thẳng, vòng ra mép rồi vào lại là chuyện thường.
check("CANARY: đóng có TRỄ, không tắt phựt khi chuột lỡ ra mép", /choDong = setTimeout/.test(JS));
check("bấm xong thì đóng NGAY, không chờ hết trễ", /dongHop\(true\)/.test(JS));
// Hộp nay cũng là con của ray, nên đếm vạch bằng ray.children là lẫn nó vào và lệch chỉ số.
check("CANARY: đếm vạch theo lớp, không theo ray.children",
  /ray\.querySelectorAll\(["']\.cm-vach["']\)/.test(JS) && !/var vach = ray\.children/.test(JS));

// ============================================================
// 5. Hội thoại dài
// ============================================================
check("khoảng cách vạch nén dần khi nhiều câu hỏi", /CACH_TOI_THIEU/.test(JS) && /CACH_TOI_DA/.test(JS));
check("danh sách có thanh cuộn riêng", /\.cm-hop \{[^}]*overflow-y: auto/.test(CSS));
check("chữ dài trong danh sách cắt bằng dấu ba chấm", /\.cm-muc \{[^}]*text-overflow: ellipsis/.test(CSS));
// CANARY cho một lỗi ĐÃ RA TỚI TAY người dùng (chủ repo báo kèm ảnh 2026-08-13): hội thoại dài
// thì danh sách thành một mớ vệt mờ không đọc được. .cm-hop là flex column có max-height, con
// của flex mặc định co lại được, nên nhiều mốc hơn chỗ chứa là mọi dòng bị bóp thay vì hộp
// cuộn. Đo trong Chromium thật: 5 câu mỗi dòng 30.8px, 60 câu còn 12px (đúng bằng phần đệm,
// chữ cắt còn 0); thêm flex:none thì 30.8px ở mọi độ dài.
//
// Bài học đáng giữ hơn cả cái luật CSS: dòng mô tả đầu file này vẫn ghi "60 câu hỏi không tràn
// khung" và điều đó ĐÚNG - hộp không hề tràn, vì các dòng đã bị bóp cho vừa. Đo đúng thứ nhưng
// sai chỗ đau, nên lỗi lọt qua cả một lượt kiểm bằng trình duyệt thật.
check("CANARY: dòng trong danh sách KHÔNG được co (hội thoại dài là chữ bị bóp mất)",
      /\.cm-muc \{[^}]*flex: none/.test(CSS));

// ============================================================
// 6. Điện thoại: chế độ KHÁC HẲN, không phải dãy vạch thu nhỏ
// ============================================================
// Bản 0.27.0 bỏ hẳn tính năng này trên màn hẹp, và chủ repo bảo "làm cho điện thoại luôn nhé".
// Thu nhỏ dãy vạch là đáp án SAI: nó sống bằng rê chuột (ngón tay không rê được) và bằng một
// dải sát mép phải (giành mất cú vuốt để cuộn). Bỏ hai thứ đó thì chẳng còn gì. Nên màn hẹp là
// một nút mở tấm trượt lên từ đáy, mỗi dòng đủ to để chạm.
check("CANARY: màn hẹp dựng NÚT chứ không tháo bỏ", /boc\.querySelector\("\.cm-nut"\)\.onclick = moTam/.test(JS));
check("CANARY: CSS đổi chế độ chứ không ẩn cả khối",
  /@media \(max-width: 860px\) \{\s*\.cm-ray \{ display: none; \}\s*\.cm-nut \{ display: inline-flex; \}\s*\}/.test(CSS)
  && !/#chatMarks \{ display: none; \}/.test(CSS));
check("mốc màn hẹp khớp trang Trò chuyện (860px)", /HEP = 860/.test(JS));
// Điện thoại không có dãy vạch để nói vị trí bằng hình, nên nút phải nói bằng chữ.
check("nút nói 'đang ở câu mấy trên tổng mấy'", /\(at \+ 1\) \+ "\/" \+ moc\.length/.test(JS));
// Chặn theo `ray` ở đây là con số trên nút đứng im mãi - sai mà trông vẫn có vẻ chạy.
check("CANARY: cập nhật vị trí KHÔNG chặn theo dãy vạch",
  !/if \(!chatArea \|\| !moc\.length \|\| !ray\) return;/.test(JS));

// Tấm trượt gắn ở BODY: nó là lớp phủ toàn màn hình, để trong khung chat đang cuộn thì nền mờ
// chỉ che được đúng phần khung và nó cuộn theo nội dung.
check("CANARY: tấm trượt gắn vào body, không nhét trong khung chat",
  /document\.body\.appendChild\(tam\)/.test(JS));
check("tấm trượt dán đáy màn hình", /\.cm-tam-lop \{[^}]*position: fixed[^}]*\}/.test(CSS)
  && /align-items: flex-end/.test(CSS));
// Ba lối thoát: nút X, chạm nền mờ, phím Esc. Thiếu lối nào cũng thành bẫy trên màn nhỏ.
check("đóng được bằng nút X", /cm-tam-dong/.test(JS));
check("CANARY: chạm nền mờ cũng đóng", /e\.target === tam/.test(JS));
check("CANARY: Esc cũng đóng", /e\.key === "Escape" && tam/.test(JS));
// Ngón tay cần đích chạm thật, không phải một dòng chữ mảnh.
check("mỗi dòng cao tối thiểu 44px theo cỡ ngón tay", /\.cm-tam \.cm-muc \{[^}]*min-height: 44px/.test(CSS));
check("chừa vùng an toàn dưới đáy (thanh gạt Home)", /env\(safe-area-inset-bottom/.test(CSS));
// Đổi chế độ giữa chừng (xoay máy) phải dựng lại: hai chế độ có cấu trúc node khác hẳn.
check("CANARY: đổi cỡ màn thì dựng lại chứ không giữ bản cũ",
  /\(hep \? "m\|" : "d\|"\)/.test(JS));

// ============================================================
// 7. Chữ người dùng gõ là DỮ LIỆU, không phải HTML
// ============================================================
check("CANARY: chữ câu hỏi được escape trước khi dựng danh sách",
  /escHtml\(moc\[i\]\.text\)/.test(JS));
check("có tôn trọng prefers-reduced-motion", /prefers-reduced-motion/.test(CSS));

// ============================================================
// 8. KHÔNG được cản việc bôi đen để copy chữ (người dùng báo 2026-08-31)
// ============================================================
// Dải mốc nằm đè lên mép phải vùng chữ: quét chuột để copy một câu cũ là đi vào dải, danh sách
// bung ra che mất và cắt ngang thao tác. Ba tầng chắn, mỗi tầng một canary - bỏ tầng nào lỗi
// cũng quay lại ở một hình dạng hơi khác.
check("dải mốc sát mép phải, không lùi vào đè lên chữ",
  /\.cm-ray \{[^}]*right: 0;/.test(CSS));
check("và rộng đúng bằng vạch dài nhất (20px), không phải 22px như bản đầu",
  /\.cm-ray \{[^}]*width: 20px;/.test(CSS));
check("khung chat chừa lề phải cho dải mốc, nên hai vùng không chồng nhau",
  /\.transcript\.cm-co-thanh \{ padding-right: \d+px; \}/.test(CSS));
check("CANARY: đang giữ chuột kéo thì dải mốc trong suốt với chuột",
  /\.transcript\.cm-dang-chon \.cm-ray[^{]*\{[^}]*pointer-events: none/.test(CSS));
check("CANARY: mở danh sách phải xét đang-bôi-đen trước",
  /function moHop\(e\) \{[\s\S]{0,80}if \(dangBoiDen\(e\)\) return;/.test(JS));
check("nhận ra đang bôi đen qua nút chuột đang giữ", /e\.buttons !== 0/.test(JS));
check("và qua vùng chọn chữ chưa rỗng", /sel && !sel\.isCollapsed/.test(JS));
// Nghe hẹp ở chatArea thì cú quét ra ngoài khung không bao giờ nhả class -> dải chết hẳn.
check("CANARY: theo dõi cú kéo ở DOCUMENT, không phải chỉ trong khung chat",
  /document\.addEventListener\("mouseup"/.test(JS));
check("bấm vào chính dải mốc KHÔNG bị tính là bôi đen (còn nhảy về câu cũ được)",
  /boc\.contains\(e\.target\)\) return;/.test(JS));
// Gỡ dải mà quên gỡ lề là khung chat chừa chỗ cho một thứ không còn ở đó.
check("tháo dải thì gỡ luôn lề phải", /classList\.remove\("cm-co-thanh"\)/.test(JS));
check("điện thoại KHÔNG chừa lề (chế độ nút, không có dải)",
  /toggle\("cm-co-thanh", !hepQua\(\)\)/.test(JS));

console.log("");
if (fails.length) { console.log("THẤT BẠI " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("OK - test_moc_hoi_thoai: tất cả pass");
