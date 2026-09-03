/* Khung project: chip ở thanh tiêu đề khung chat + ngăn kéo Hướng dẫn / File / Link.

       node tests/js/test_khung_project.js

   Đợt 3 của tính năng Project (đợt 1 dựng kho + API, đợt 2 bơm vào system prompt). Ở đây mới
   có đường cho người dùng ĐỔ nội dung vào, nên mấy chỗ dễ làm sai nhất được canh riêng:

   - Chip phải nói về project CỦA LƯỢT CHAT chứ không phải bộ lọc cột trái. Server bơm hướng
     dẫn theo `sessions.project_id`; chip mà đọc bộ lọc là nó nói dối đúng vào lúc người dùng
     mở nó ra để kiểm tra xem Javis đang nhận hướng dẫn nào.
   - Hướng dẫn lưu theo debounce, nên phải có đường XẢ khi đóng ngăn kéo / rời tab / rời ô
     nhập. Thiếu nhát đó thì gõ xong đóng nhanh tay là mất chữ, và mất im lặng.
   - Tài liệu tải lên phải vào SOURCES, và tên thư mục phải do SERVER tìm. Hai cái bẫy nằm
     cạnh nhau: attachments là vùng cache bị media_gc dọn theo tuổi nên tài liệu để đó là hẹn
     ngày mất, còn đoán tên thư mục bằng chuỗi cứng thì brain đặt "01 - Sources" là file đi
     lạc vào một thư mục thứ hai trùng nghĩa. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const SU = D("sessions-ui.js");
const CS = D("console.js");
const HTML = D("index.html");
const CSS = D("style.css");
const APP = D("app.js");
const PY = fs.readFileSync(path.join(ROOT, "server", "sessions.py"), "utf8");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const EN = JSON.parse(D(path.join("i18n", "en.json")));

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

// ============================================================
// 1. Chip: có chỗ đứng ở CẢ HAI khung chat
// ============================================================
check("chip có chỗ đứng ở thanh nhãn khung chat màn Javis",
  /<span class="proj-chip-host" id="projChipHost"><\/span>/.test(HTML));
check("và ở thanh tiêu đề trang Trò chuyện",
  /'<span class="proj-chip-host"><\/span>' \+/.test(CS));
// Trang Trò chuyện dựng lại thanh tiêu đề từ đầu mỗi lần vào, nên phải vẽ lại chip sau đó -
// không thì chip chỉ có ở màn Javis, đúng chỗ người dùng ít chat nhất.
check("renderChat vẽ lại chip sau khi dựng thanh tiêu đề",
  /JavisChatSide\.chip\(\)/.test(CS));
check("module xuất hàm vẽ chip và hàm mở khung",
  /chip: renderProjChip, moKhung: openProjDrawer/.test(SU));
// 0.53.1: nút "Mở khung project" trong menu ĐỔI thành nút GHIM (chủ repo yêu cầu 01/09).
// Khung vẫn vào được qua chip - chọn project rồi mở hội thoại là chip hiện ra - nên chỗ đó
// không phải lối vào duy nhất, còn xếp thứ tự thì trước nay chưa có đường nào.
check("menu project không còn nút mở khung", !/Mở khung project/.test(SU));
// 0.54.1 dời nút ghim VÀO hộp chức năng ba chấm (mục 11), nên nó không còn là một icon
// hover ở hàng nữa. Cái phải còn lại ở hàng là DẤU ghim - thứ giải thích thứ tự danh sách.
check("ghim nằm trong hộp chức năng", /icon: "pin", run: function \(\) \{ ghimProject\(p\); \}/.test(SU));
check("ghim gọi đúng route project (không phải route ghim file/link)",
  /"\/projects\/" \+ encodeURIComponent\(p\.id\) \+ "\/pin",\s*\n\s*\{ pinned:/.test(SU));
// `giuMo` vẫn còn trong openMenu như một khả năng của khung, dù sau 0.54.1 chưa hàng nào
// dùng tới (ghim đã dời vào hộp chức năng, bấm xong quay về danh sách đã xếp lại).
check("openMenu vẫn cho phép một nút giữ menu mở", /if \(!a\.giuMo\) closeMenu\(\);/.test(SU));
// renderProjBar() thay node neo bằng node mới, giữ tham chiếu cũ là menu rơi ra ngoài màn.
check("và mở lại menu bằng neo HỎI LẠI chứ không giữ tham chiếu cũ",
  /var neo = projBar && projBar\.querySelector\("\.cs-proj-cur"\);/.test(SU)
  && /if \(neo\) openProjMenu\(neo\);/.test(SU));
// Hàng nút trong menu chỉ hiện khi rê chuột, nên dấu ghim phải nằm NGOÀI hàng đó.
check("dấu ghim nằm ngoài hàng nút hover", /pinIcon \? '<span class="cs-menu-pin">/.test(SU));
const menuRow = (SU.match(/var row = el\('<div class="cs-menu-row[\s\S]*?cs-menu-acts[^;]*;/) || [""])[0];
check("dấu ghim nằm TRONG nút chính (luôn hiện), trước hàng nút hover",
  menuRow.indexOf("cs-menu-pin") > 0
  && menuRow.indexOf("cs-menu-pin") < menuRow.indexOf("cs-menu-acts"),
  menuRow.slice(0, 80));
check("và CSS của nó không bị hạ opacity như hàng nút hover",
  /\.cs-menu-pin \{[^}]*\}/.test(CSS)
  && !/\.cs-menu-pin \{[^}]*opacity/.test(CSS));

// Kho: ghim xếp lên đầu, và KHÔNG đụng updated_at.
check("kho xếp project ghim lên đầu", /ORDER BY p\.pinned DESC, p\.updated_at DESC/.test(PY));
check("ghim không bump updated_at (nếu không, bỏ ghim là nhảy lên đầu nhóm chưa ghim)",
  /UPDATE projects SET pinned = \? WHERE id = \?/.test(PY));
check("DB cũ được thêm cột pinned qua migration",
  /\("pinned", "INTEGER NOT NULL DEFAULT 0"\)/.test(PY));

// ============================================================
// 1b. Thanh tiêu đề trang Trò chuyện: bỏ tiêu đề tĩnh, chip lùi về mép phải
// ============================================================
check("không còn thẻ tiêu đề tĩnh trong thanh", !/<span class="cp-title">/.test(CS));
check("và không còn CSS .cp-title mồ côi", !/\.cp-title\{/.test(CS));
check("chip lùi hẳn về mép phải thanh đó",
  /\.chatpage-bar \.proj-chip-host\{ margin-left:auto; \}/.test(CS));

// ============================================================
// 1c. Bản hẹp: chip hiện ĐỦ TÊN project, không thu về icon tròn
// ============================================================
const mqChip = (CSS.match(/@media \(max-width: 860px\) \{\s*\n\s*\.proj-chip \{[\s\S]*?\n\}/) || [""])[0];
check("tìm được khối bản hẹp của chip", !!mqChip);
check("bản hẹp KHÔNG giấu tên project nữa", !/\.pc-name[^}]*display: none/.test(mqChip), mqChip.slice(0, 160));
check("và không bóp chip thành hình tròn", !/border-radius: 50%;[^}]*\}/.test(mqChip.split(".pc-dot")[0]));
check("chỉ giấu hai con số file/link cho đỡ chật",
  /\.proj-chip \.pc-meta \{ display: none; \}/.test(mqChip));
check("chip vẫn bị siết bề ngang để không đè nút bên cạnh",
  /\.proj-chip \{ max-width: 45vw; \}/.test(mqChip));

// ============================================================
// 2. Chip đọc project CỦA PHIÊN, không đọc bộ lọc cột trái
// ============================================================
const duAn = (SU.match(/async function duAnCuaLuot\(\)[\s\S]*?\n  \}/) || [""])[0];
check("có hàm hỏi project của lượt chat", !!duAn);
check("hỏi hàng phiên qua /sessions/{id}/meta chứ không đọc bộ lọc",
  /\/sessions\/" \+ encodeURIComponent\(sid\) \+ "\/meta/.test(duAn), duAn.slice(0, 120));
// Chat chưa gửi tin nào thì chưa có hàng trong DB; lúc đó bộ lọc MỚI là câu trả lời đúng vì
// JavisProjects.claim sẽ gắn tin đầu tiên vào đúng project đang lọc.
check("chưa có phiên thì mới rơi về bộ lọc", /if \(!sid\) return locThat;/.test(duAn));
check("404 (id đã mint, chưa gửi tin) cũng rơi về bộ lọc", /pid = locThat;/.test(duAn));
// Mạng hỏng mà ghi cache thì cái sai đó sống tới khi đổi phiên.
check("mạng hỏng thì KHÔNG ghi cache", /catch \(e\) \{ return locThat; \}/.test(duAn));
check("đổi phiên là bỏ cache rồi vẽ lại chip",
  /javis:sessions-changed", function \(\) \{\s*\n\s*quenPhienProj\(\);\s*\n\s*renderProjChip\(\);/.test(SU));
// refresh() thoát sớm khi cột trái chưa mount, mà chip còn đứng ở màn Javis - nơi cột đó
// không bao giờ mount. Nên chip phải nghe sự kiện bằng listener RIÊNG.
check("chip có listener riêng, không dựa vào refresh() của cột trái",
  (SU.match(/addEventListener\("javis:sessions-changed"/g) || []).length === 2);
check("đổi project của một cuộc cũng làm chip vẽ lại",
  /quenPhienProj\(\);\s*\n\s*renderProjChip\(\);\s*\n\s*cached = null;/.test(SU));

// ============================================================
// 3. Hướng dẫn: debounce PHẢI có đường xả
// ============================================================
check("gõ xong 800ms mới lưu", /setTimeout\(function \(\) \{ luuHuongDan\(ta\.value\); \}, 800\)/.test(SU));
const xa = (SU.match(/function xaLuuHuongDan\(\)[\s\S]*?\n  \}/) || [""])[0];
check("có hàm xả cái đang chờ", /clearTimeout\(pdLuuTimer\)/.test(xa) && /luuHuongDan\(ta\.value\)/.test(xa));
check("đóng ngăn kéo thì xả", /function closeProjDrawer\(\) \{\s*\n(?:.*\n)*?\s*xaLuuHuongDan\(\);/.test(SU));
check("rời tab thì xả", /function showProjTab\(tab\) \{\s*\n\s*xaLuuHuongDan\(\);/.test(SU));
check("rời ô nhập thì xả", /ta\.onblur = function \(\) \{ xaLuuHuongDan\(\); \};/.test(SU));
check("trần ký tự khớp server", /PROJ_INSTR_MAX = 4000/.test(SU));
check("và 4000 đúng là trần server đang cắt", /PROJECT_INSTRUCTIONS_MAX = 4000/.test(PY));
check("ô nhập tự chặn ở 4000 chứ không để gõ thừa rồi bị cắt lặng lẽ",
  /maxlength="' \+ PROJ_INSTR_MAX \+ '"/.test(SU));
// Chip đọc has_instructions từ danh sách project, nên lưu xong phải nạp lại danh sách.
check("lưu hướng dẫn xong thì nạp lại danh sách để chấm báo trên chip đúng",
  /datTrangThaiLuu\("saved"\);\s*\n(?:.*\n)*?\s*loadProjects\(\);/.test(SU));

// ============================================================
// 4. Tải file lên: vào SOURCES, và để SERVER tìm tên thư mục
// ============================================================
// 02/09: chủ repo báo file tải lên trong khung Project rơi vào attachments. attachments là
// VÙNG CACHE - media_gc dọn nó theo tuổi (mặc định 30 ngày) và theo trần dung lượng - nên
// tài liệu của một project để ở đó là hẹn ngày mất, và mất rồi thì project còn lại một hàng
// trỏ vào hư không.
const taiLen = (SU.match(/async function taiLenMot\([\s\S]*?\n  \}/) || [""])[0];
check("có hàm tải file lên", !!taiLen);
check("CANARY: tải vào sources, KHÔNG còn nhắc attachments",
  /"folder", "sources"/.test(taiLen) && !/attachments/.test(taiLen));
// Dòng chú thích dưới ô thả từng ghi "nằm ở thư mục attachments" - sai từ lúc đường tải đổi
// sang sources, và nó là thứ DUY NHẤT người dùng đọc để biết file mình vừa tải đi đâu.
check("chú thích dưới ô thả nói đúng thư mục", /sources/.test(VI["proj.upload_dest"])
  && !/attachments/.test(VI["proj.upload_dest"] + EN["proj.upload_dest"]));
// Bản cũ đoán tên thư mục ở frontend bằng chuỗi cứng "attachments". Brain đặt "01 - Sources"
// hay "05 - Attachments" là nó đẻ ra một thư mục thứ hai trùng nghĩa, file đi lạc khỏi chỗ
// người dùng nhìn. Tên thư mục thật chỉ server mới biết.
check("CANARY: không còn đoán tên thư mục ở frontend",
  !/homeCuaBrain/.test(SU) && !/pdHome/.test(SU));
check("đăng ký vào project đúng đường SERVER trả về",
  /themFile\(up\.path, up\.name, null\)/.test(taiLen));
check("tìm file trong brain dùng /files/search mode=name", /\/files\/search\?brain=[\s\S]{0,80}mode=name/.test(SU));
// 03/09: nút của file đã thêm trước đây là chữ "Đã thêm" tắt cứng, nên lỡ thêm nhầm là phải
// đóng form, lần tìm nó trong danh sách trên rồi mới gỡ được. Nay nó đổi thành "Gỡ" ngay tại
// hàng kết quả - thêm và bỏ cùng một chỗ, cùng một cú bấm.
const veNut = (SU.match(/function veNutKetQua\([\s\S]*?\n  \}/) || [""])[0];
check("kết quả tìm kiếm có nút đổi Thêm / Gỡ", !!veNut
  && /proj\.remove_short/.test(veNut) && /proj\.add/.test(veNut));
check("nút đọc lại trạng thái từ projChiTiet chứ không đóng cứng lúc vẽ",
  /\(projChiTiet\.files \|\| \[\]\)\.forEach\(function \(f\) \{ theoDuong\[f\.path\] = f; \}\)/.test(veNut));
check("và gỡ ngay tại kết quả gọi đúng route xoá file khỏi project",
  /async function goNhanhFile\(f, nut\)[\s\S]*?\/files\/" \+\s*\n?\s*encodeURIComponent\(f\.id\) \+ "\/delete"/.test(SU));
check("thêm hoặc gỡ xong thì vẽ lại nút, không phải tìm lại từ đầu",
  (SU.match(/veNutKetQua\(\);/g) || []).length >= 3);
check("nhãn Gỡ có ở cả hai từ điển", !!VI["proj.remove_short"] && !!EN["proj.remove_short"]);

// ============================================================
// 4b. Chọn NHIỀU file, và thả vào ngăn kéo thì đừng rơi xuống khung chat
// ============================================================
// 03/09: hộp chọn file chỉ nhận một file, còn kéo-thả vào ô "kéo thả vào đây" thì file nhảy
// sang khung chat - app.js có một tay bắt drop toàn cục, ô thả cũ chặn mặc định nhưng không
// chặn bọt nên window vẫn ăn tiếp.
check("ô chọn file nhận nhiều file", /<input type="file" class="pd-file" multiple hidden>/.test(SU));
check("có vòng tải lần lượt từng file kèm đếm n/tổng",
  /async function taiLenNhieu\(files, drop\)/.test(SU)
  && /\(i \+ 1\) \+ "\/" \+ ds\.length/.test(SU));
check("một file hỏng không chặn những file còn lại", /loi\.push\(ds\[i\]\.name/.test(SU));
check("CANARY: cả tấm ngăn kéo là vùng thả, tự chặn bọt lên window",
  /panel\.setAttribute\("data-localdrop", "1"\)/.test(SU)
  && /e\.stopPropagation\(\);\s+\/\/ không để app\.js/.test(SU));
check("CANARY: app.js bỏ qua drop rơi vào vùng thả riêng",
  /closest\("\[data-localdrop\]"\)/.test(APP)
  && /if \(inLocalDrop\(e\)\) return;/.test(APP));
check("và ô .pd-drop không còn bắt drop lần thứ hai (thả trúng nút là tải lên hai lần)",
  !/drop\.ondrop/.test(SU));

// ============================================================
// 4c. Dải đính kèm dưới khung chat: nhiều file thì phải CUỘN
// ============================================================
// 03/09: chủ repo đính 9 file, dải cao 140px cắt cụt ở hàng thứ ba và overflow:hidden nên
// không cuộn được - mấy file cuối còn nguyên đó nhưng không cách nào bấm X bỏ đi.
const dai = (CSS.match(/\.attach-bar\.has-items \{[\s\S]*?\}/) || [""])[0];
check("dải đính kèm cuộn được khi tràn", /overflow-y:\s*auto/.test(dai), dai.slice(0, 90));

// ============================================================
// 5. Ghim = nạp nội dung. Gỡ file KHÔNG xoá file trong brain.
// ============================================================
check("nút ghim gọi đúng route ghim file",
  /\/files\/" \+\s*\n?\s*encodeURIComponent\(f\.id\) \+ "\/pin"/.test(SU));
check("ghim đảo trạng thái hiện tại", /pinned: f\.pinned \? "0" : "1"/.test(SU));
check("chú thích nói rõ ghim là nạp sẵn NỘI DUNG, không phải đổi thứ tự",
  /nạp sẵn/.test(VI["proj.pin_on"] || "") && /2000/.test(VI["proj.pin_note"] || ""));
check("hai trần trong chú thích khớp server", /PROJECT_GHIM_FILE_MAX = 2000/.test(
  fs.readFileSync(path.join(ROOT, "server", "main.py"), "utf8")));
check("hỏi lại trước khi gỡ file, và nói rõ file vẫn còn trong brain",
  /confirm\(pdT\("proj\.confirm_remove_file"/.test(SU) && /vẫn còn trong brain/.test(VI["proj.confirm_remove_file"] || ""));
check("link nói rõ chỉ mở được khi bộ não có công cụ duyệt web",
  /duyệt web/.test(VI["proj.link_note"] || ""));
check("link mở ở tab mới có rel=noopener", /rel="noopener noreferrer"/.test(SU));

// ============================================================
// 6. Onboarding: tạo project xong là mở khung ra ngay
// ============================================================
const moi = (SU.match(/async function newProject\(\)[\s\S]*?\n  \}/) || [""])[0];
check("tạo xong thì mở luôn khung project", /openProjDrawer\(r\.id\)/.test(moi));
check("kèm banner chào", /pdOnboard = true;/.test(moi));
check("và mở sẵn một hội thoại trống để tin đầu rơi vào project mới",
  /JavisSessions\.new\(\)/.test(moi));
check("banner chỉ sống trong lần mở đó, đóng khung là tắt",
  /pdOnboard = false;/.test((SU.match(/function closeProjDrawer\(\)[\s\S]*?\n  \}/) || [""])[0]));
check("xoá project đang mở thì đóng khung theo",
  /if \(projChiTiet && projChiTiet\.id === p\.id\) \{ projChiTiet = null; closeProjDrawer\(\); \}/.test(SU));

// ============================================================
// 7. Một khung cho hai bề ngang, và đóng được bằng mọi đường quen thuộc
// ============================================================
check("chỉ có MỘT khung .pd-panel, không nhân đôi DOM cho mobile",
  (SU.match(/class="pd-panel"/g) || []).length === 1);
check("màn hẹp đổi khung thành tấm trượt từ đáy",
  /@media \(max-width: 860px\) \{[\s\S]*?\.pd-panel \{ top: auto; left: 0;/.test(CSS));
check("có vạch kéo, chỉ hiện ở bản hẹp",
  /\.pd-grip \{ display: none; \}/.test(CSS) && /\.pd-grip \{ display: block;/.test(CSS));
check("chạm nền mờ là đóng", /\.pd-scrim"\)\.onclick = closeProjDrawer/.test(SU));
check("Esc cũng đóng", /e\.key === "Escape" && pdEl && pdEl\.classList\.contains\("on"\)/.test(SU));
check("nền mờ dùng token --scrim (tông sáng không bị phủ đen)",
  /\.pd-scrim \{[^}]*background: var\(--scrim\)/.test(CSS));
// Khung dựng MỘT lần nên nút đóng / đổi tên không tự vẽ lại như thân khung: đổi ngôn ngữ mà
// không bỏ node đi thì hai nút đó nói tiếng cũ mãi mãi.
check("đổi ngôn ngữ thì bỏ node khung đi để lần sau dựng lại",
  /addEventListener\("javis:i18n", function \(\) \{[\s\S]*?pdEl = null;/.test(SU));

// ============================================================
// 8. i18n: khung mới không được là ốc đảo tiếng Việt cứng
// ============================================================
const khoa = [...new Set((SU.match(/pdT\("([\w.]+)"/g) || []).map((s) => s.slice(5, -1)))];
check("có dùng t() cho chuỗi của khung", khoa.length > 20, String(khoa.length));
const thieuVi = khoa.filter((k) => !(k in VI));
check("mọi khoá đều có trong vi.json", thieuVi.length === 0, thieuVi.join(", "));
const thieuEn = khoa.filter((k) => !(k in EN));
check("và trong en.json", thieuEn.length === 0, thieuEn.join(", "));
check("không dùng emoji thay icon (mockup dùng emoji, app dùng Lucide)",
  !/[\u{1F300}-\u{1FAFF}]/u.test(SU.split("// ===== Khung project")[1] || ""));

// ============================================================
// 9. Phản hồi 01/09: mở file, xoá hẳn, icon tab, giữ form tìm
// ============================================================
// Bấm vào tên một tài liệu mà không mở được nó ra đọc là phản xạ bị phụ - danh sách này
// chính là chỗ người ta đi tìm tài liệu.
check("tên file là NÚT mở, dùng lại ba nấc của chip 'file đang mở'",
  /JavisOpenNoteAt === "function" && window\.JavisOpenNoteAt\(f\.path, ten\)/.test(SU)
  && /JavisEditFile === "function"/.test(SU) && /JavisOpenFiles === "function"/.test(SU));
check("mở file thì đóng ngăn kéo (trình sửa hiện ra sau nó)",
  /function moFile\(f\) \{[\s\S]*?closeProjDrawer\(\);/.test(SU));
// <a> lồng trong <button> là HTML sai và trình duyệt nuốt cú bấm vào link.
check("hàng LINK không bọc thẻ <a> trong <button>",
  /: '<span class="pd-row-body">'\) \+/.test(SU));
check("có nút xoá HẲN khỏi brain, tách khỏi nút gỡ khỏi project",
  /class="pd-row-act pd-xoa"/.test(SU) && /post\("\/files\/delete"/.test(SU));
// Hai hành động, hai hậu quả rất khác nhau, nên hai câu hỏi lại phải khác nhau rõ ràng.
check("hai câu xác nhận khác nhau và câu xoá hẳn nói rõ không hoàn tác",
  VI["proj.confirm_remove_file"] !== VI["proj.confirm_delete_file"]
  && /không hoàn tác/i.test(VI["proj.confirm_delete_file"] || ""));
check("xoá file xong thì gỡ luôn khỏi project, không để lại dòng trỏ vào hư không",
  /function xoaHanFile[\s\S]*?\/files\/" \+\s*\n?\s*encodeURIComponent\(f\.id\) \+ "\/delete"/.test(SU));
check("ba tab có icon", /icoTab|ico: "scroll-text"/.test(SU) && /\.pd-tab \.ic \{/.test(CSS));
// Vẽ lại cả khung là form tìm kiếm dựng lại từ đầu: mất chữ đã gõ, mất kết quả, muốn thêm
// file thứ hai phải gõ lại - đúng lỗi chủ repo báo.
check("thêm file xong chỉ vẽ lại danh sách, KHÔNG vẽ lại cả khung",
  /veLaiDanhSach\(\);\s*\/\/ KHÔNG veDrawer/.test(SU));
check("danh sách nằm trong hộp riêng để vẽ lại được", /'<div class="pd-list">'/.test(SU));
check("thêm link xong cũng giữ form và dọn ô để dán tiếp",
  /u\.value = ""; u\.focus\(\);/.test(SU));

// ============================================================
// 10. File và link của một CUỘC TRÒ CHUYỆN
// ============================================================
check("có nút mở khung đó ở thanh tiêu đề", /class="cts-btn"/.test(SU));
// LỖI THẬT ở 0.54.0: chỗ này viết `html = '<button class="proj-chip...` nên hễ cuộc thuộc
// một project là nút vừa dựng bị gán đè mất - mà đó là trường hợp thường gặp nhất, nên nút
// coi như không tồn tại. Canh bằng dấu cộng, không phải bằng sự có mặt của chuỗi.
check("chip CỘNG THÊM vào nút đó chứ không gán đè",
  /html \+= '<button class="proj-chip/.test(SU) && !/html = '<button class="proj-chip/.test(SU));
// Chat dài đẻ ra tài liệu ở MỌI cuộc, kể cả cuộc chưa xếp vào project nào.
check("nút hiện theo phiên đã lưu, không phụ thuộc project",
  /var html = currentId\(\)\s*\n\s*\? '<button class="cts-btn"/.test(SU));
check("gọi endpoint tài sản của phiên", /"\/sessions\/" \+ encodeURIComponent\(sid\) \+ "\/assets\?brain="/.test(SU));
// Dựng khung thứ hai cho hai danh sách trông giống nhau, hành xử giống nhau, chỉ khác nguồn
// dữ liệu là nhân đôi số chỗ phải sửa về sau.
check("dùng lại vỏ ngăn kéo của project chứ không dựng khung thứ hai",
  (SU.match(/class="pd-panel"/g) || []).length === 1 && /pdCheDo = "cuoc"/.test(SU));
check("thanh tab dựng động: chế độ cuộc chỉ có File và Link",
  /if \(pdCheDo === "cuoc"\) return \[tabFile, tabLink\];/.test(SU));
check("mở khung project thì trả chế độ về project", /pdDung\(\);\s*\n\s*pdCheDo = "project";/.test(SU));
check("file đã dời vẫn hiện, mờ đi và gạch ngang",
  /\.pd-row\.mat \{ opacity/.test(CSS) && /\.pd-row\.mat \.pd-row-name \{ text-decoration: line-through/.test(CSS));
check("và nói rõ vì sao nó mờ", /đổi tên hoặc dời/i.test(VI["cts.file_gone"] || ""));
// Người dùng phải biết danh sách này gom từ đâu, nếu không thiếu một file là mất lòng tin.
check("nói thẳng giới hạn: chỉ gom file Javis có nhắc tên",
  /nhắc tên/.test(VI["cts.note"] || ""));
check("ghi rõ link do ai gửi", !!VI["cts.from_you"] && !!VI["cts.from_javis"]);

// ============================================================
// 11. Phản hồi 01/09: nút ba chấm, tên project đủ chỗ, chip không phá thanh nhãn
// ============================================================
// Bốn icon hiện-khi-rê-chuột ăn ~100px trong popover 280px, và hover thì KHÔNG tồn tại trên
// màn cảm ứng - ở đó chúng là bốn chức năng không có đường nào bấm tới.
check("một nút ba chấm thay cho bốn icon hover",
  /icon: "ellipsis-vertical", title: "Chức năng của project"/.test(SU)
  && !/\{ icon: "palette", title: "Đổi icon"/.test(SU));
check("icon ba chấm có thật trong bộ đã vendor",
  /"ellipsis-vertical":/.test(fs.readFileSync(path.join(ROOT, "dashboard", "vendor", "lucide-icons.js"), "utf8")));
check("và được khai trong manifest (để lần sinh lại còn giữ)",
  JSON.stringify(JSON.parse(D("icons.manifest.json")).groups).includes("ellipsis-vertical"));
check("hộp chức năng có đủ ghim, đổi icon, đổi tên, xoá, và lối quay lại",
  /function openProjActs/.test(SU) && /Quay lại danh sách/.test(SU)
  && /Đổi tên project/.test(SU) && /Xoá project/.test(SU));
check("và có cả lối mở khung Hướng dẫn / File / Link", /Mở khung Hướng dẫn/.test(SU));
// Đi sâu trong CÙNG một popover: hai lớp nổi chồng nhau thì bấm ra ngoài lớp trong đóng
// nhầm cả hai.
check("hộp đi sâu trong cùng popover, không bung lớp nổi thứ hai",
  /function openProjActs\(anchor, p\) \{\s*\n\s*openMenu\(anchor, \[/.test(SU));
check("nút chức năng không còn nấp sau hover",
  /\.cs-menu-acts \{[^}]*opacity: \.55/.test(CSS));
// Chỗ vừa lấy lại từ 4 icon phải về tay cái TÊN, không thì sửa xong vẫn cụt như cũ.
check("popover rộng ra cho tên project", /\.cs-menu \{[^}]*max-width: 340px/.test(CSS));
check("tên project ở đầu hộp hiện ĐỦ, xuống dòng thay vì cắt ba chấm",
  /wrap: true,/.test(SU) && /\.cs-menu-lbl\.nhieu-dong \{[^}]*white-space: normal/.test(CSS));

// Thanh nhãn cột hẹp: tên project dài đẩy chữ "HỘI THOẠI" vỡ thành hai dòng.
check("chữ HỘI THOẠI không co, không vỡ dòng",
  /\.panel-label > span:first-child \{ flex: none; white-space: nowrap; \}/.test(CSS));
// 02/09: chủ repo chụp ba ảnh cho thấy hàng nhãn để lại dải trống: chip được ép chiếm trọn
// một hàng CẢ KHI RỖNG (flex: 1 0 100%), nên hai nút luôn rớt xuống hàng dưới. Nay chip cùng
// hàng và co bằng ba chấm; chip rỗng không chiếm chỗ; cột hẹp thì chip CÓ nội dung mới xuống
// hàng riêng để tên project vẫn đủ bề ngang.
const CCSS = D("console.css");
check("chip cùng hàng với nhãn, co được (flex: 1 1 auto; min-width: 0)",
  /\.panel-label \.proj-chip-host \{ flex: 1 1 auto; min-width: 0/.test(CSS));
check("CANARY: chip RỖNG không chiếm hàng nào", /\.panel-label \.proj-chip-host:empty \{ display: none; \}/.test(CSS));
check("hai nút dồn về mép phải cùng hàng nhãn", /\.panel-label \.panel-acts \{[^}]*margin-left: auto/.test(CSS)
  && /<span class="panel-acts">/.test(HTML));
check("cột hẹp: chip CÓ nội dung mới xuống hàng riêng",
  /\.hud-right \.panel-label \.proj-chip-host:not\(:empty\) \{ flex: 1 0 100%; order: 3; \}/.test(CCSS)
  && /\.panel-label \{[^}]*flex-wrap: wrap/.test(CSS));

console.log("");
if (fails.length) { console.log("ĐỎ " + fails.length + " mục"); process.exit(1); }
console.log("Tất cả xanh.");
