/* Khung project: chip ở thanh tiêu đề khung chat + ngăn kéo Hướng dẫn / File / Link.

       node tests/js/test_khung_project.js

   Đợt 3 của tính năng Project (đợt 1 dựng kho + API, đợt 2 bơm vào system prompt). Ở đây mới
   có đường cho người dùng ĐỔ nội dung vào, nên mấy chỗ dễ làm sai nhất được canh riêng:

   - Chip phải nói về project CỦA LƯỢT CHAT chứ không phải bộ lọc cột trái. Server bơm hướng
     dẫn theo `sessions.project_id`; chip mà đọc bộ lọc là nó nói dối đúng vào lúc người dùng
     mở nó ra để kiểm tra xem Javis đang nhận hướng dẫn nào.
   - Hướng dẫn lưu theo debounce, nên phải có đường XẢ khi đóng ngăn kéo / rời tab / rời ô
     nhập. Thiếu nhát đó thì gõ xong đóng nhanh tay là mất chữ, và mất im lặng.
   - Tải file lên phải tính từ GỐC BRAIN. Trần duyệt trên localhost là cả ổ đĩa, gửi thẳng
     "attachments" là ghi ra ngoài brain rồi ghi một đường dẫn vô nghĩa vào project. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const SU = D("sessions-ui.js");
const CS = D("console.js");
const HTML = D("index.html");
const CSS = D("style.css");
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
check("mà là nút ghim", /icon: "pin", giuMo: true,/.test(SU));
check("ghim gọi đúng route project (không phải route ghim file/link)",
  /"\/projects\/" \+ encodeURIComponent\(p\.id\) \+ "\/pin",\s*\n\s*\{ pinned:/.test(SU));
// Đóng menu sau mỗi lần bấm thì xếp 5 project phải mở menu 5 lần.
check("bấm ghim GIỮ menu mở", /if \(!a\.giuMo\) closeMenu\(\);/.test(SU));
// renderProjBar() thay node neo bằng node mới, giữ tham chiếu cũ là menu rơi ra ngoài màn.
check("và mở lại menu bằng neo HỎI LẠI chứ không giữ tham chiếu cũ",
  /var neo = projBar && projBar\.querySelector\("\.cs-proj-cur"\);\s*\n\s*if \(neo\) openProjMenu\(neo\);/.test(SU));
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
// 4. Tải file lên: tính từ GỐC BRAIN, không phải trần duyệt
// ============================================================
const home = (SU.match(/async function homeCuaBrain\(\)[\s\S]*?\n  \}/) || [""])[0];
check("có hàm hỏi gốc brain", !!home);
check("lấy `home` của /files/list (gốc brain tính theo trần)",
  /\/files\/list\?brain=/.test(home) && /d\.home/.test(home));
check("và ghép vào trước attachments khi tải lên",
  /var thuMuc = \(home \? home \+ "\/" : ""\) \+ "attachments";/.test(SU));
check("đăng ký vào project đúng đường vừa tải lên",
  /themFile\(thuMuc \+ "\/" \+ up\.name, up\.name, null\)/.test(SU));
check("tìm file trong brain dùng /files/search mode=name", /\/files\/search\?brain=[\s\S]{0,80}mode=name/.test(SU));
check("file đã có trong project thì nút Thêm xám đi, không thêm trùng",
  /daCo\[it\.path\] \? " disabled" : ""/.test(SU));

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

console.log("");
if (fails.length) { console.log("ĐỎ " + fails.length + " mục"); process.exit(1); }
console.log("Tất cả xanh.");
