/* Trang Chatbot còn HAI tab: Hòm thư và Bot (0.65.9).

       node tests/js/test_chatbot_hai_tab.js

   Chủ dự án (30/09/2026): thêm kênh và tạo bot đang nằm ở hai tab khác nhau ("Kênh của bot", "Tạo chatbot"), người dùng phải nhớ
   làm cái nào trước rồi tick lại đúng kênh vừa thêm, "khó hiểu". Gộp thành tab Bot: bot ở trên, mục "Kênh chưa có bot" ngay dưới.

   Những chỗ dễ hỏng (mất chức năng, hoặc hỏng lặng lẽ) mà file này khoá lại:

   1. ID TAB CŨ vẫn dẫn về đúng chỗ: console.js, link và bookmark cũ còn gọi "kenh" và "chatbot".
   2. KHÔNG MẤT CHỨC NĂNG QUẢN LÝ KÊNH. Kênh đã có bot không còn thẻ riêng, nên chip kênh trên thẻ bot phải bấm được để sửa và xoá kênh.
      Kênh kiểu tài khoản (Zalo cá nhân) là kết nối ở trang Kết nối nên chip chỉ để đọc.
   3. KÊNH CỦA BOT Ở BRAIN KHÁC không được biến mất. Đang xem "mọi brain" thì mục kênh phải liệt kê cả chúng (bot đó không hiện ở trang này).
   4. DÒNG KHOÁ TRONG FORM KHÔNG ĐƯỢC TÍNH LÀ ĐÃ TICK. Chỉ `.cb-tk-o` được đếm là kênh đã chọn; dòng khoá mà mang lớp đó thì bot bị gắn
      vào kênh của bot khác (server từ chối, form báo lỗi khó hiểu).
   5. Icon robot bị chê "xấu": trang Chatbot và Hòm thư không dùng lại icon `bot`.
*/
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const CV = read("dashboard/conversations.js");
const CB = read("dashboard/chatbots.js");
const CON = read("dashboard/console.js");
const CSS = read("dashboard/console.css") + read("dashboard/style.css");
const VI = JSON.parse(read("dashboard/i18n/vi.json"));
const EN = JSON.parse(read("dashboard/i18n/en.json"));

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. hai tab, id cũ vẫn chạy ----
// Chatbot v5 (2026-10-28): four tabs again, Hội thoại · Bot · Kênh · Thống kê; the channel accounts moved to "kenh".
check("bốn tab: inbox, bot, kenh, thongke", /var TABS = \["inbox", "bot", "kenh", "thongke"\];/.test(CV));
check("id tab cũ 'chatbot' được đổi về 'bot' ('kenh' là tab Kênh thật)", /var TAB_CU = \{ chatbot: "bot" \};/.test(CV) &&
  /function chuanTab\(id\) \{ return TAB_CU\[id\] \|\| id; \}/.test(CV));
check("chonTab, render và moTu đều chuẩn hoá id tab", /id = chuanTab\(id\);\s*\n\s*if \(TABS\.indexOf\(id\) < 0\) return;/.test(CV) &&
  /TABS\.indexOf\(chuanTab\(_cho\.tab\)\) >= 0\) _tab = chuanTab\(_cho\.tab\)/.test(CV) && /var tabMo = chuanTab\(_cho\.tab \|\| ""\);/.test(CV));
check("console.js chọn tab Bot khi vào bằng id trang cũ 'chatbots'", CON.indexOf('chonTab("bot", true)') > 0);
check("nhãn tab: Hội thoại, Bot, Kênh, Thống kê (vi, en); khoá tab cũ đã bỏ",
  VI["ib.tab_inbox"] === "Hội thoại" && VI["ht.tab_bot"] === "Bot" && EN["ht.tab_bot"] === "Bots" && VI["ib.tab_kenh"] === "Kênh" &&
  VI["ib.tab_stats"] === "Thống kê" && !("ht.tab_kenh" in VI) && !("ht.tab_chatbot" in VI) && !("ht.tab_kenh" in EN) && !("ht.tab_chatbot" in EN));
check("tab Bot dựng danh sách bot (chatbots.js); tài khoản kênh nằm ở tab Kênh",
  /function renderBot\(body\)/.test(CV) && /class="ht-tab-bot"><div class="ht-bot-ds"><\/div><\/div>/.test(CV) &&
  /window\.JavisChatbots && window\.JavisChatbots\.render/.test(CV) && /renderSub\(body, window\.JavisInboxChannels/.test(CV));
check("KHÔNG dùng lại lớp 'ht-bot' (tên cũ của ô chọn bot ở Hòm thư, test_hoi_thoai_bo_loc canh nó)", !/class="ht-bot"/.test(CV));
check("nhịp làm mới danh sách kênh chạy ở tab Kênh", /else if \(_tab === "kenh"\) \{\s*\n\s*taiTK\(true\);/.test(CV) &&
  /if \(_tab === "kenh" && window\.JavisInboxChannels\) window\.JavisInboxChannels\.paint\(\);/.test(CV));

// ---- 2. tab Kênh (Chatbot v5, inbox-channels.js) ----
const KN = fs.readFileSync(path.join(root, "dashboard", "inbox-channels.js"), "utf8");
check("tab Kênh có nút Kết nối kênh mới và công tắc 'Xem mọi brain'",
  /kn-add/.test(KN) && /kn-allbr-cb/.test(KN) && /ht\.tk_xem_moi_brain/.test(KN) && /setAllBrains: function \(on\)/.test(CV));
check("CANARY: xem mọi brain thì liệt kê MỌI tài khoản, kể cả kênh đang do bot của brain KHÁC trực (không lọc theo bot_id)",
  /function accs\(\) \{ return C\.accounts\(\)\.filter\(function \(a\) \{ return a && a\.account_key; \}\); \}/.test(KN) &&
  /\(_tkMoiBrain \? "&tat_ca=1" : ""\)/.test(CV));
check("chưa có tài khoản nào thì nói rõ (không để trống trơn)", /ht\.tk_rong/.test(KN) && VI["ht.tk_rong"] && EN["ht.tk_rong"]);
check("'Tạo bot cho kênh này' mở form ngay tại tab Bot, không dựng lại tab", /if \(_tab !== "bot"\) chonTab\("bot"\);/.test(CV) &&
  /javis:chatbot-new/.test(CV) && VI["ht.tk_tao_bot"] === "Tạo bot cho kênh này");
check("hộp thư trống chỉ sang tab Kênh (nơi thêm tài khoản)", /nut\.onclick = function \(\) \{ chonTab\("kenh"\); \};/.test(CV));

// ---- 3. chip kênh trên thẻ bot: quản lý kênh không mất ----
check("chip kênh kiểu bot là NÚT bấm được, gọi JavisConversations.suaKenh",
  /if \(k\.kind === "bot"\) \{\s*\n\s*return '<button type="button" class="cb-kenh-chip cb-kenh-sua" data-tk="'/.test(CB) &&
  /window\.JavisConversations && window\.JavisConversations\.suaKenh/.test(CB));
check("chip kênh kiểu tài khoản (Zalo cá nhân) chỉ để đọc", /return '<span class="cb-kenh-chip" title="'/.test(CB));
check("chip 'Thêm kênh' trên thẻ mở form Sửa thẳng ở bước chọn kênh",
  /class="cb-kenh-chip cb-kenh-them"/.test(CB) && /moForm\(b, \{ buoc: 1 \}\)/.test(CB) && /var buoc = \(truoc && truoc\.buoc\) \|\| \(sua \? 2 : 1\);/.test(CB));
check("sửa kênh: bảng sửa có nút Xoá kênh (kênh kiểu bot) và dùng chung một hàm xoá với thẻ kênh",
  /class="s-btn-ghost ht-xoa-tk"/.test(CV) && /nutXoa\.onclick = function \(\) \{ dong\(\); xoaTK\(a\); \}/.test(CV) &&
  /xoa\.onclick = function \(\) \{ xoaTK\(a\); \}/.test(CV) && (CV.match(/\/channels\/accounts\/" \+ encodeURIComponent\(a\.id\) \+ "\/delete"/g) || []).length === 1);
check("xoá xong thì dựng lại tab để chip của kênh vừa xoá biến mất", /if \(_tab === "bot" \|\| _tab === "kenh"\) veTab\(\);/.test(CV));
check("suaKenh và tenBrain được xuất cho chatbots.js", /suaKenh: suaKenh, tenBrain: tenBrain/.test(CV));
check("chỉ kênh sửa được (sua_duoc) mới mở bảng sửa", /if \(a && a\.sua_duoc\) moSuaTK\(a\);/.test(CV));

// ---- 4. form Bot mới: kênh khoá ----
check("form nạp danh sách kênh đang có bot từ server (tai_khoan_ban)", /_tkBan = d\.tai_khoan_ban \|\| \[\];/.test(CB));
check("dòng khoá ghi tên bot đang giữ, kèm brain khi khác brain đang mở",
  /cb\.tk_khoa/.test(CB) && /cb\.tk_khoa_brain/.test(CB) && /a\.bot_brain !== brain\(\)/.test(CB) && VI["cb.tk_khoa"] && EN["cb.tk_khoa"]);
const khoa = (CB.match(/return '<div class="cb-tk cb-tk-khoa"[\s\S]*?'<\/span><\/div>';/) || [""])[0];
check("CANARY: dòng khoá KHÔNG có ô tick và KHÔNG mang lớp cb-tk-o (không thì bị đếm là kênh đã chọn)",
  khoa.length > 50 && khoa.indexOf("<input") < 0 && khoa.indexOf("cb-tk-o") < 0, khoa.length);
check("kênh của chính bot đang sửa không hiện thành khoá", /_tkBan\.filter\(function \(a\) \{ return !da\[a\.id\]; \}\)/.test(CB));

// ---- 5. icon ----
const dungBot = (s) => /ic\("bot"/.test(s);
check("CANARY: chatbots.js và conversations.js không dùng icon robot", !dungBot(CB) && !dungBot(CV));
check("icon mới: tai nghe cho tab, người cho Agent", /bot: \["ht\.tab_bot", "headset"\]/.test(CV) && /ic\("user-round"\) \+ ' ' \+ esc\(b\.agent_name/.test(CB));

// ---- 6. giao diện ----
check("có kiểu cho mục kênh, chip bấm được và dòng khoá",
  /\.ht-kenh-sec \{/.test(CSS) && /\.cb-kenh-sua|button\.cb-kenh-chip/.test(CSS) && /\.cb-kenh-them \{/.test(CSS) && /\.cb-tk-khoa \{/.test(CSS));
const moi = ["ht.xoa_kenh", "cb.sua_kenh_title", "cb.tk_khoa", "cb.tk_khoa_brain"];
check("khoá mới có ở cả vi và en", moi.every((k) => VI[k] && EN[k]), moi.filter((k) => !VI[k] || !EN[k]).join(","));
check("mọi khoá mới đều được mã dùng", moi.every((k) => (CV + CB).indexOf('"' + k + '"') > 0), moi.filter((k) => (CV + CB).indexOf('"' + k + '"') < 0).join(","));
const cu = ["tab Kênh của bot", "tab Chatbot", "Bot channels tab", "Chatbot tab"];
check("từ điển không còn chỉ người dùng sang tab đã bỏ", !cu.some((c) => JSON.stringify(VI).indexOf(c) >= 0 || JSON.stringify(EN).indexOf(c) >= 0),
  cu.filter((c) => JSON.stringify(VI).indexOf(c) >= 0 || JSON.stringify(EN).indexOf(c) >= 0).join(","));
check("không dùng em dash trong test này và mã mới", fs.readFileSync(__filename, "utf8").indexOf(String.fromCharCode(0x2014)) < 0 &&
  CV.indexOf(String.fromCharCode(0x2014)) < 0 && CB.indexOf(String.fromCharCode(0x2014)) < 0);

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK: trang Chatbot hai tab");
