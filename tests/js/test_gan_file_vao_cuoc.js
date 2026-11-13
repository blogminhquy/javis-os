/* Gắn tay file & link vào MỘT cuộc trò chuyện (khung "Trong cuộc trò chuyện này").

       node tests/js/test_gan_file_vao_cuoc.js

   Chủ repo báo 05/09: khung đó đã tự dò ra file và link, nhưng không có đường nào để tự thêm
   vào - trong khi khung Project ngay bên cạnh thì có đủ tìm, tải lên, dán link, ghim, gỡ.

   Mấy chỗ dễ làm sai nhất được canh riêng:

   - Hai chế độ phải dùng CHUNG một bộ pane. Chép đôi paneFile/paneLink cho chế độ cuộc là
     nhân đôi số chỗ phải sửa, và hai bản sẽ trôi lệch ngay ở lần sửa sau.
   - Mọi hàm thêm/gỡ/ghim phải đi qua MỘT chỗ đổi gốc URL (pdApi). Nhúng "/projects/" thẳng
     vào từng hàm là chế độ cuộc lặng lẽ ghi vào project đang mở gần nhất.
   - Hàng TỰ DÒ không có id nên không được bày nút gỡ/ghim: bấm vào là gọi route với id rỗng,
     hỏng câm.
   - Gắn tay mà Javis không thấy thì cái nút chỉ là danh sách để ngắm. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const SU = D("sessions-ui.js");
const CSS = D("style.css");
const PY = fs.readFileSync(path.join(ROOT, "server", "main.py"), "utf8");
const PYS = fs.readFileSync(path.join(ROOT, "server", "sessions.py"), "utf8");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const EN = JSON.parse(D(path.join("i18n", "en.json")));

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

// ============================================================
// 1. Một bộ pane cho cả hai chế độ
// ============================================================
// paneCuocFile/paneCuocLink là hai bản sao cũ. Còn sót lại nghĩa là chế độ cuộc vẫn đi đường
// riêng, và mọi thứ thêm cho project sau này sẽ không tới được nó.
check("bỏ hẳn hai pane riêng của chế độ cuộc",
  !/function paneCuocFile/.test(SU) && !/function paneCuocLink/.test(SU));
// 2026-11-13 (owner): files, folders and links share ONE documents pane, so every mode draws it with paneFile.
check("veDrawer dùng chung MỘT pane tài liệu (file, thư mục, link) cho mọi chế độ",
  /projTab === "learned" \? paneLearned\(p\) : projTab === "instr" \? paneHuongDan\(p\) : paneFile\(p\)/.test(SU)
  && (SU.match(/function paneFile\(/g) || []).length === 1 && !/function paneLink\(/.test(SU));
// Ba chế độ (project / cuộc / trợ lý) dùng chung một ngăn kéo, nên "dữ liệu đang mở" phải
// đọc ở MỘT chỗ. Rẽ nhánh lại ở từng hàm là thêm chế độ thứ tư sẽ sót đúng một chỗ.
check("có hàm đọc dữ liệu đang mở, không rẽ nhánh ở từng chỗ",
  /function pdDuLieu\(\) \{ return pdLaCuoc\(\) \? cuocTS : pdLaAgent\(\) \? agentTS : projChiTiet; \}/.test(SU));

// ============================================================
// 2. Gốc URL đổi ở MỘT chỗ
// ============================================================
check("có hàm pdApi trả gốc theo chế độ",
  /function pdApi\(\)[\s\S]{0,240}\/sessions\/"[\s\S]{0,120}\/assets"[\s\S]{0,120}\/projects\/"/.test(SU));
["themFile", "goNhanhFile", "ghimFile", "goFile", "themLink", "ghimLink", "goLink"].forEach((fn) => {
  const than = (SU.match(new RegExp("async function " + fn + "\\([\\s\\S]*?\\n  \\}")) || [""])[0];
  // pdPost() = pdApi() cộng các trường đi kèm của chế độ (chế độ trợ lý phải gửi `brain`).
  check(fn + " gọi qua pdApi()/pdPost(), không nhúng cứng /projects/",
    /pdApi\(\)|pdPost\(/.test(than) && !/"\/projects\//.test(than), than.slice(0, 90));
});
check("nạp lại chi tiết cũng theo chế độ",
  /async function napLaiChiTiet\(\)[\s\S]{0,200}napCuocTS\(\)[\s\S]{0,120}napProjChiTiet/.test(SU));
// Chip chỉ hiện số của PROJECT. Gọi loadProjects() sau mỗi lần gắn file vào một cuộc là quét
// lại toàn bộ project mỗi cú bấm, không đổi gì trên màn hình.
check("chỉ project mới nạp lại danh sách cho chip",
  /function napLaiChip\(\) \{ if \(pdCheDo === "project"\) loadProjects\(\); \}/.test(SU));

// ============================================================
// 3. Hàng TỰ DÒ: mở được, nhưng không có nút gỡ/ghim
// ============================================================
const hang = (SU.match(/function hangMuc\([\s\S]*?\n  \}\n/) || [""])[0];
// Cắt riêng nhánh tự dò rồi mới soi: soi cả hàm thì regex trườn sang nhánh dưới và bao giờ
// cũng thấy pd-ghim, tức là phép kiểm luôn xanh dù code có sai.
const nhanhTuDong = (hang.match(/if \(o\.tuDong\) \{[\s\S]*?\n    \}/) || [""])[0];
check("hàng tự dò có nhánh riêng, không mang nút hành động",
  !!nhanhTuDong && !/pd-ghim/.test(nhanhTuDong) && !/pd-go/.test(nhanhTuDong));
check("và vẫn mở ra đọc được - việc chính của nó",
  /pd-row-body mo-duoc/.test(nhanhTuDong));
check("noiHang bỏ qua hàng không có id thay vì gọi route với id rỗng",
  /if \(!row\.dataset\.id\) \{[\s\S]{0,220}return;/.test(SU));
check("danh sách chia nhóm: gắn tay lên trên, tự dò xuống dưới",
  /cts\.added_group/.test(SU) && /cts\.auto_group/.test(SU)
  && /f\.manual/.test(SU));
check("kết quả tìm kiếm chỉ đối chiếu file GẮN TAY (file tự dò không gỡ được)",
  /if \(f\.id\) theoDuong\[f\.path\] = f;/.test(SU));

// ============================================================
// 4. Kéo-thả: cuộc trò chuyện giờ cũng có chỗ chứa
// ============================================================
// Trước đây chế độ cuộc nhường file cho khung chat vì cuộc chưa có chỗ chứa tài liệu. Nay nó
// có, mà ngăn kéo đang MỞ che gần hết màn hình - thả trúng nó mà file nhảy sang ô chat là
// đúng cái phản xạ bị phụ đã sửa cho project hôm 03/09.
check("vùng thả không còn loại trừ chế độ cuộc",
  !/pdCheDo !== "project"/.test(SU) && !/coFile\(e\) \|\| pdCheDo/.test(SU));
check("cờ data-localdrop bật ở CẢ hai chế độ (không gỡ đi ở chế độ cuộc)",
  !/removeAttribute\("data-localdrop"\)/.test(SU));

// ============================================================
// 5. Server: kho, route, và rào
// ============================================================
check("kho có bảng riêng cho tài liệu của cuộc",
  /CREATE TABLE IF NOT EXISTS session_files/.test(PYS)
  && /CREATE TABLE IF NOT EXISTS session_links/.test(PYS));
// Lưu brain lần nữa ở đây là mở cửa cho một cuộc trỏ sang file của brain khác - phá rào
// _safe_path bằng DỮ LIỆU chứ không bằng lỗi code, nên không rào nào bắt được.
// Cắt đúng câu CREATE TABLE rồi mới soi, cùng lý do như trên.
const bangSF = (PYS.match(/CREATE TABLE IF NOT EXISTS session_files \([\s\S]*?\n\);/) || [""])[0];
check("CANARY: bảng KHÔNG có cột brain (brain lấy từ phiên)",
  !!bangSF && !/brain/.test(bangSF));
check("xoá hội thoại thì tài liệu đi theo (khoá ngoại)",
  /session_id TEXT NOT NULL REFERENCES sessions\(id\) ON DELETE CASCADE,\n    path/.test(PYS));
check("có trần số lượng để một cuộc dài không âm thầm phình",
  /SESSION_ASSETS_MAX = \d+/.test(PYS) && /SESSION_ASSETS_MAX/.test(PY));
// Cắt riêng thân hàm rồi soi thứ tự bên trong: đo bằng cửa sổ ký tự thì thêm một dòng chú
// thích là phép kiểm đỏ oan.
const themFilePY = (PY.match(/def sessions_add_file\([\s\S]*?\n\n\n/) || [""])[0];
// 2026-11-12 (owner: "chọn được cả thư mục"): the fence moved one call down, into `_asset_target`, shared by the
// project, chat and agent routes. It takes a file or a whole folder, and still refuses the empty path.
const targetPY = (PY.match(/def _asset_target\([\s\S]*?\n\n\n/) || [""])[0];
check("route thêm file kiểm đường dẫn TRƯỚC khi ghi kho",
  themFilePY.indexOf("_asset_target(b, path)") > 0
  && themFilePY.indexOf("_asset_target(b, path)") < themFilePY.indexOf("add_session_file")
  && targetPY.indexOf("_safe_path(brain, path)") > 0);
// Đường dẫn rỗng giải ra chính thư mục trần, mà thư mục thì "có tồn tại": it stays refused (`if rel and ...`).
check("a file or a real folder is taken, the empty path (the ceiling itself) is not",
  /if rel and target\.is_dir\(\):\n\s+return rel \+ "\/", target\.name, True\n\s+if target\.is_file\(\):/.test(targetPY));
check("brain lấy từ phiên, không nhận từ client",
  /sessions_add_file[\s\S]{0,300}sess\.get\("brain"\)/.test(PY));
check("link chỉ nhận http/https",
  /sessions_add_link[\s\S]{0,500}\^https\?:\/\//.test(PY));
check("danh sách trộn hai nguồn, bản gắn tay thắng khi trùng",
  /ra_file = tay_file \+ \[f for f in ra_file/.test(PY)
  && /ra_link = tay_link \+ \[l for l in ra_link/.test(PY));
// Dọn mất tài liệu người dùng gắn vào là để lại một hàng trỏ vào hư không.
check("media_gc giữ lại file gắn tay của cuộc",
  /all_project_file_paths\(\)\s*\n?\s*\| get_store\(\)\.all_session_file_paths\(\)/.test(PY));

// ============================================================
// 6. Javis phải THẤY thứ được gắn
// ============================================================
check("có khối tài liệu của cuộc ghép vào system prompt",
  /def _session_block\(session_id: str\) -> str:/.test(PY)
  && /base \+= _session_block\(session_id\)/.test(PY));
// Hai khối chép đôi thì trần token trôi lệch, mà trần trôi lệch là kiểu hỏng không ai thấy
// cho tới lúc hoá đơn hoặc lỗi quá hạn mức xuất hiện.
check("dùng CHUNG bộ luật liệt kê/nạp ghim với project, không chép đôi",
  /def _liet_ke_tai_lieu\(/.test(PY)
  && (PY.match(/PROJECT_GHIM_TONG_MAX\n/g) || []).length <= 1);
check("lượt chat dashboard truyền session_id vào prompt",
  (PY.match(/session_id=conv_sid/g) || []).length >= 3);

// ============================================================
// 7. Từ điển: nhãn mới có ở CẢ hai ngôn ngữ
// ============================================================
["cts.added_group", "cts.auto_group", "cts.auto_links_group", "cts.pin_note",
 "cts.confirm_remove_file", "cts.confirm_remove_link"].forEach((k) => {
  check("nhãn " + k + " có ở cả vi và en", !!VI[k] && !!EN[k]);
});
check("chú thích ghim nói rõ chỉ áp cho RIÊNG cuộc này",
  /RIÊNG cuộc này/.test(VI["cts.pin_note"] || ""));
check("ô rỗng chỉ luôn đường thêm vào chứ không chỉ báo trống",
  /Thêm tài liệu/.test(VI["cts.files_empty"] || "") && /link/.test(VI["cts.files_empty"] || "")
  && VI["proj.add_doc"] === "Thêm tài liệu");
// Link tự dò: địa chỉ là thứ bấm được ở dòng TÊN, dòng dưới chỉ nói ai gửi. Nhét địa chỉ vào
// cả hai dòng là bắt đọc hai lần một thứ trong một hàng cao 40px.
check("link tự dò không lặp địa chỉ ở cả hai dòng",
  /tuDong: true, icon: "link", tenHtml: linkAnchor\(l\),\s*\n\s*sub: l\.vai === "user"/.test(SU));
// Gạch ngang là dấu "file này đã dời đi". Suy nó từ moDuoc thì mọi hàng link đều bị gạch,
// vì link không có khái niệm mở-được.
check("gạch ngang là cờ RIÊNG, không suy từ moDuoc",
  /if \(o\.tuDong\) \{\s*\n\s*return '<div class="pd-row' \+ \(o\.mat \? " mat" : ""\)/.test(SU));
check("chú thích ghim chỉ hiện khi đã có hàng ghim được",
  /function coGhimDuoc\(p\)/.test(SU) && /coGhimDuoc\(p\)\s*\n\s*\? '<div class="pd-note">/.test(SU));

// ---- a whole folder (2026-11-12, owner: "chọn được cả thư mục") ----
// The drawer is shared by the project, the chat and the agent, so these hold for all three.
const timFile = (SU.match(/async function timFile\([\s\S]*?\n  \}\n/) || [""])[0];
check("the brain search asks for folders too", timFile.includes("&mode=name&include_dirs=true&limit=20&q="));
check("a folder result goes by its path with a trailing slash, the spelling the server stores",
  /var dir = it\.type === "dir", duong = dir \? folderPath\(it\.path\) : it\.path;/.test(timFile)
  && /data-path="' \+ esc\(duong\)/.test(timFile) && /ic\(dir \? "folder" : icoFile\(it\.name\)\)/.test(timFile));
// The helper is run for real: the Add / Remove button finds a row again only when both sides spell the path alike.
const folderPath = new Function((SU.match(/function folderPath\(p\) \{[^\n]*\}/) || ["function folderPath(){}"])[0] + "; return folderPath;")();
const isFolderRow = new Function((SU.match(/function isFolderRow\(f\) \{[^\n]*\}/) || ["function isFolderRow(){}"])[0] + "; return isFolderRow;")();
check("folderPath leaves exactly one trailing slash", folderPath("a/b") === "a/b/" && folderPath("a/b//") === "a/b/");
check("a row is a folder by the server's flag or by its slash, never by a missing extension",
  isFolderRow({ dir: true, path: "a" }) && isFolderRow({ path: "a/b/" }) && !isFolderRow({ path: "a/README" }) && !isFolderRow(null));
check("a folder row never gets the 'delete from the brain' button", SU.includes("xoaDuoc: con && !dir"));
check("a folder row opens the Files page instead of the editor",
  /function moFile\(f\) \{\s*\n\s*if \(isFolderRow\(f\)\) \{ openFolderRow\(f\); return; \}/.test(SU)
  && /window\.JavisOpenFiles\(folderPath\(duong\)\)/.test(SU));
check("the folder's pin and open titles exist in both languages",
  ["proj.pin_on_dir", "proj.open_dir"].every((k) => VI[k] && EN[k] && VI[k] !== EN[k]));
check("the search box says folders can be found", /thư mục/.test(VI["proj.search_ph"]) && /folder/.test(EN["proj.search_ph"])
  && /thư mục/.test(VI["teams.pick.doc_search_ph"]) && /folder/.test(EN["teams.pick.doc_search_ph"]));

console.log("");
if (fails.length) { console.log("ĐỎ " + fails.length + " mục"); process.exit(1); }
console.log("Tất cả xanh.");
