/* Hòm thư tải dần: danh sách theo trang, khung tin tải 40 tin mới nhất và kéo lên để xem thêm (0.65.11).

       node tests/js/test_hoi_thoai_tai_dan.js

   Chủ dự án (30/09/2026): "cơ chế tải lùi những tin gần nhất, lướt lên cùng thì tải thêm để đỡ lag máy người xem tin". Trước đó nhịp 5 giây tải lại 200 tin rồi
   vẽ lại toàn bộ khung (kéo người đang đọc tin cũ về đầu mỗi khi có tin mới), và danh sách cố định 60 dòng, hiện "60+" mà không tải thêm được.

   Những chỗ hỏng lặng lẽ mà file này khoá lại (cùng các bẫy đã ghi ở test_chat_tai_dan.js cho khung chat chính):

   1. GIỮ CHỖ ĐANG ĐỌC KHI CHÈN TIN CŨ LÊN ĐẦU. Phải đo theo ĐÁY khung (scrollHeight - scrollTop), không theo scrollTop: phần chèn nằm phía trên nên scrollTop
      cũ trỏ vào một chỗ khác hẳn.
   2. NHỊP CHỈ HỎI TIN MỚI HƠN TIN CUỐI, rồi CHÈN vào cuối. Vẽ lại cả khung thì mất chỗ đọc và tốn máy. Hai lượt hỏi chồng nhau không được chèn trùng một tin.
   3. PHẦN ĐẦU KHUNG VẪN PHẢI CẬP NHẬT khi thứ nó phụ thuộc đổi (chế độ Tự động/Tôi trả lời, bot chạy hay tắt, lý do bot im, tin cuối do ai gửi), và
      người gọi ép được bằng `_dauVetTin = ""`. Nếu không nút "Trả lời giúp tin này" kẹt ở trạng thái cũ.
   4. KHÔNG TỰ TẢI HẾT KHI KHUNG ĐANG ẨN. Chiều cao 0 (khung ẩn, chưa đo) thì "chưa đủ cao để cuộn" luôn đúng và vòng tự tải kéo về cả nghìn tin.
   5. DÙNG SỰ KIỆN CUỘN, KHÔNG DÙNG IntersectionObserver: callback của nó bị trình duyệt hoãn khi khung không được vẽ, sự kiện cuộn thì luôn tới.
*/
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const CV = read("dashboard/conversations.js");
const CSS = read("dashboard/console.css");
const SRV = read("server/routes/conversations.py");
const VI = JSON.parse(read("dashboard/i18n/vi.json"));
const EN = JSON.parse(read("dashboard/i18n/en.json"));

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. danh sách theo trang ----
check("trang 40 dòng, nhịp làm mới tối đa 200 dòng đầu", /var TRANG = 40;/.test(CV) && /var MAX_DONG_NHIP = 200;/.test(CV));
check("một hàm dựng URL dùng chung cho trang đầu và trang kế (cùng bộ lọc, tìm kiếm, tài khoản)", /function urlDanhSach\(limit, offset\)/.test(CV) &&
  /"&offset=" \+ offset/.test(CV) && /urlDanhSach\(soDong, 0\)/.test(CV) && /urlDanhSach\(TRANG, _items\.length\)/.test(CV));
check("nhịp hỏi lại đúng số dòng người dùng đã tải, phần sâu hơn giữ nguyên", /var soDong = im \? Math\.min\(MAX_DONG_NHIP, TRANG \* _soTrang\) : TRANG;/.test(CV) &&
  /var duoi = im \? _items\.slice\(soDong\) : \[\];/.test(CV) && /_items = dau\.concat\(duoi\);/.test(CV));
check("đổi bộ lọc hoặc gõ tìm (không phải nhịp) thì về trang đầu và cuộn lên đầu", /if \(!im\) \{ _soTrang = 1; box\.scrollTop = 0; \}/.test(CV));
check("tải trang kế không hiện trùng dòng (có hội thoại mới chen lên đầu làm dòng bị đẩy qua trang)", /_items\.forEach\(function \(c\) \{ co\[c\.id\] = true; \}\)/.test(CV) &&
  /them\.filter\(function \(c\) \{ return !co\[c\.id\]; \}\)/.test(CV));
check("chỉ một lượt tải trang kế chạy một lúc", /if \(_dangTaiDS \|\| !_conDS \|\| !_host\) return;/.test(CV));
check("nút Xem thêm ở cuối khi còn trang sau", /<div class="ht-more"><button type="button" class="s-btn-ghost ht-more-b">/.test(CV) && /\(_conDS \? '<div class="ht-more">/.test(CV));
check("CANARY: tự tải bằng SỰ KIỆN CUỘN gần đáy, KHÔNG dùng IntersectionObserver",
  /box\.onscroll = function \(\) \{ if \(_conDS && box\.scrollHeight - box\.scrollTop - box\.clientHeight < 240\) taiThem\(\); \};/.test(CV) &&
  !/new IntersectionObserver/.test(CV));
check("CANARY: tự lấp đầy chỉ khi khung ĐÃ ĐO ĐƯỢC (clientHeight > 0)", /_conDS && box\.clientHeight > 0 && box\.scrollHeight <= box\.clientHeight \+ 40/.test(CV));
check("dòng đếm hiện 'N+' khi còn trang sau, không còn mốc cứng 60+", /n: _items\.length \+ \(_conDS \? "\+" : ""\)/.test(CV) && !/TRANG \+ "\+"/.test(CV));

// ---- 2. khung tin: 40 tin mới nhất, nhịp chỉ hỏi phần mới ----
check("mở hội thoại lấy 40 tin mới nhất (không còn limit=200 cho mọi nhịp)", /var TIN_TRANG = 40;/.test(CV) && /"limit=" \+ TIN_TRANG/.test(CV) && !/messages\?limit=200"/.test(CV));
check("CANARY: đã có tin thì nhịp chỉ hỏi tin MỚI hơn tin cuối (after=)", /"after=" \+ _msgs\[_msgs\.length - 1\]\.id \+ "&limit=200"/.test(CV));
check("hai lượt hỏi chồng nhau không chèn trùng: chỉ nhận tin mới hơn tin cuối THẬT lúc ghép", /var cuoi = _msgs\.length \? _msgs\[_msgs\.length - 1\]\.id : 0;/.test(CV) &&
  /filter\(function \(m\) \{ return m\.id > cuoi; \}\)/.test(CV));
check("mở hội thoại khác thì bỏ hết tin cũ trong bộ nhớ và tải lại từ tin mới nhất", /_msgs = \[\]; _conCu = false; _dangTaiCu = false; _vetMeta = "";/.test(CV));
check("CANARY: chỉ vẽ lại phần đầu khung khi chữ ký đổi, hoặc bị ép bằng _dauVetTin = \"\"", /if \(dau \|\| !_dauVetTin \|\| sig !== _vetMeta \|\| !box\.querySelector\("\.ht-msgs"\)\)/.test(CV) &&
  /if \(moi\.length\) chenTin\(moi\);/.test(CV));
check("chữ ký gồm mọi thứ phần đầu khung phụ thuộc (chế độ, bot chạy, lý do im, tin cuối do ai gửi)",
  /function metaSig\(\)/.test(CV) && /c\.mode, c\.bot_id, c\.bot_name/.test(CV) && /_silence, _running, u\.sender_type/.test(CV));
check("chèn tin mới trước dòng 'Bot im', và chỉ trượt theo khi người đọc đang ở đáy", /sil\.insertAdjacentHTML\("beforebegin", html\)/.test(CV) &&
  /var oDay = m\.scrollHeight - m\.scrollTop - m\.clientHeight < 80;\s*\n\s*var html = moi\.map\(veTin\)/.test(CV) && /if \(oDay\) m\.scrollTop = m\.scrollHeight;/.test(CV));
check("vẽ lại cả khung khi cần thì giữ nguyên chỗ đang đọc (đo theo đáy), không kéo về đầu", /var tuDay = cuon \? cuon\.scrollHeight - cuon\.scrollTop : 0;/.test(CV) &&
  /else if \(cuon\) m\.scrollTop = m\.scrollHeight - tuDay;/.test(CV));

// ---- 3. kéo lên tải tin cũ ----
check("kéo gần đầu khung hoặc bấm nút thì tải 40 tin cũ hơn theo con trỏ before", /m\.onscroll = function \(\) \{ if \(_conCu && m\.scrollTop < 120\) taiCu\(\); \};/.test(CV) &&
  /"\/messages\?before=" \+ _msgs\[0\]\.id \+ "&limit=" \+ TIN_TRANG/.test(CV) && /class="ht-older"/.test(CV));
check("CANARY: chèn tin cũ lên đầu rồi giữ chỗ bằng cách đo theo ĐÁY khung", /var tuDay = m2\.scrollHeight - m2\.scrollTop;/.test(CV) &&
  /m2\.scrollTop = m2\.scrollHeight - tuDay;/.test(CV) && /insertAdjacentHTML\("afterbegin", nutTinCu\(\) \+ cu\.map\(veTin\)\.join\(""\)\)/.test(CV));
check("chỉ một lượt tải tin cũ chạy một lúc, và bỏ kết quả nếu đã sang hội thoại khác", /if \(_dangTaiCu \|\| !_conCu \|\| !_chon \|\| !_msgs\.length \|\| !_host\) return;/.test(CV) &&
  /if \(_chon !== id\) \{ _dangTaiCu = false; return; \}/.test(CV));
check("tin còn ngắn chưa cuộn được thì tải tiếp, nhưng CANARY: chỉ khi khung đã đo được", /_conCu && m\.clientHeight > 0 && m\.scrollHeight <= m\.clientHeight \+ 40\) taiCu\(\)/.test(CV) &&
  /tiep = _conCu && m2\.clientHeight > 0 && m2\.scrollHeight <= m2\.clientHeight \+ 40;/.test(CV));
check("hết tin cũ thì nút biến mất (has_more do server báo)", /_conCu = !!d\.has_more && cu\.length > 0;/.test(CV) && /_conCu = !!d\.has_more;/.test(CV));

// ---- 4. server ----
check("server có after và has_more", /def conversations_messages\(conv_id: int, limit: int = 100, before: int = 0, after: int = 0\)/.test(SRV) &&
  /"has_more":/.test(SRV) && /co_tin_cu\(conv_id, msgs\[0\]\["id"\]\)/.test(SRV));
check("lý do bot im tính trên tin cuối THẬT của cuộc chat, không phải phần trả về", /cuoi = msgs if \(not moi and not before\) else conversations\.tin_nhan\(conv_id, limit=1\)/.test(SRV));
check("trang thứ hai của danh sách không tính lại số đếm", /if offset > 0:/.test(SRV) && /return \{"ok": True, "items": items\}/.test(SRV));

// ---- 5. giao diện + từ điển ----
check("có kiểu cho nút Xem thêm và nút Xem tin cũ hơn", /\.ht-more \{/.test(CSS) && /\.ht-older \{/.test(CSS) && /\.ht-older\.busy \{/.test(CSS));
check("hai khoá chữ mới có ở vi và en, và được mã dùng", VI["ht.xem_them"] && EN["ht.xem_them"] && VI["ht.tin_cu"] && EN["ht.tin_cu"] &&
  CV.indexOf('"ht.xem_them"') > 0 && CV.indexOf('"ht.tin_cu"') > 0);
check("hết icon robot ở trạng thái bot và nút Trả lại cho bot", !/ic\("bot"/.test(CV) && !/actionButton\("[a-z]+", "bot"/.test(CV) && !/: "bot"\)/.test(CV) &&
  /"undo-2", "ht\.act_back"/.test(CV) && /off \? "circle-stop" : "sparkles"/.test(CV));
check("không dùng em dash trong test này", fs.readFileSync(__filename, "utf8").indexOf(String.fromCharCode(0x2014)) < 0);

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK: Hòm thư tải dần");
