/* Trang Coding: vào là chat được, thư mục gắn sau, và mượn khung chat chứ không dựng lại.

       node tests/js/test_trang_coding.js

   Bản 0.63.0 hỏng ba chỗ mà chủ dự án chỉ ra ngay khi dùng thử, nên file này canh đúng ba
   chỗ ấy để chúng không quay lại:

   1. **KHÔNG có màn chặn "chưa có repo".** Trang này là trang CHAT; dựng một bước cài đặt
      chắn trước nó là làm ngược chính spec của nó. Vào trang phải có phiên ngay, và phiên
      chưa gắn thư mục vẫn nhắn được (cwd suy biến về brain).

   2. **THƯ MỤC chứ không phải REPO.** Không đòi `.git`. Ba chip phụ thuộc git (nhánh,
      worktree, điểm hồi) chỉ hiện khi thư mục thật sự là repo - bày một chip bấm vào chỉ để
      nhận lỗi là hứa suông.

   3. **Icon nói đúng việc.** "git-branch" nói "git", mà trang này nhận mọi thư mục.

   Và hai chỗ 0.63.2 sửa tiếp:

   4. **Cột trái phải là CHÍNH cột hội thoại của trang Trò chuyện** (mượn qua JavisChatSide),
      không phải một danh sách rút gọn tự vẽ. Đây là lần thứ hai cùng một lỗi "dựng bản thứ
      hai" trong cùng một trang, nên canh hẳn bằng test.

   5. **Ba chế độ đọc là Plan / Tự động / Toàn quyền**, và Plan phải thật sự BẢO engine lập
      kế hoạch rồi dừng, chứ không chỉ là chặn ghi file.

   Cộng hai luật cũ vẫn phải giữ: mượn khung chat chứ không dựng bản thứ hai, và trả node lại
   khi rời trang.

   Chữ hiện ra nằm ở i18n nên mọi khẳng định về LỜI soi đủ hai vế: giao diện gọi đúng khoá, VÀ
   khoá đó mang đúng câu. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

const CD = D("coding.js");
const CON = D("console.js");
const HTML = D("index.html");
const CSS = D("console.css");
const VI = JSON.parse(D("i18n/vi.json"));
const EN = JSON.parse(D("i18n/en.json"));
const tu = (k, chu) => String(VI[k] || "").includes(chu);

// Hàm thuần nạp thẳng: kiểm hành vi thật thay vì regex trên mã nguồn.
const M = require(path.join(ROOT, "dashboard", "coding.js"));

// ---- 1. Vào là chat được ngay ----
check("KHÔNG còn màn chặn 'chưa có repo/thư mục'",
  !/cdOnboard|onboard-on|ob_title/.test(CD) && !VI["coding.ob_title"] && !EN["coding.ob_title"]);
check("mở trang thì mở phiên gần nhất, chưa có thì TẠO luôn một phiên",
  /await moPhienDau\(\)/.test(CD)
  && /ds\.length\) await moPhien\(ds\[0\]\.id\);[\s\S]{0,40}else await moPhienMoi\(\)/.test(CD));
check("tạo phiên KHÔNG kèm thư mục nào", /channel: S\.kenh/.test(CD) && !/thu_muc:[^}]*sessions\/new/.test(CD));
check("server không đòi thư mục khi mở phiên coding", (() => {
  const MAIN = fs.readFileSync(path.join(ROOT, "server", "main.py"), "utf8");
  return /loai == "coding"[\s\S]{0,700}create_session/.test(MAIN)
    && !/loai == "coding"[\s\S]{0,400}status_code=404/.test(MAIN);
})());
check("chưa gắn thư mục thì nói rõ đang làm trong bộ não",
  /coding\.in_brain/.test(CD) && tu("coding.in_brain", "bộ não"));

// ---- 2. Thư mục, không phải repo ----
check("chữ trên giao diện nói THƯ MỤC", tu("coding.add_folder", "thư mục") && !!EN["coding.add_folder"]);
check("khoá cũ nói 'repo' đã bỏ hẳn",
  ["coding.add_repo", "coding.remove_repo", "coding.chip_pick_repo", "coding.ask_path"]
    .every((k) => !VI[k] && !EN[k]));
// 0.63.8: bỏ dòng giảng giải ở chân hộp chọn thư mục (chủ dự án: "nghe kỳ quá"). Việc
// "không cần là repo git" đã tự thể hiện: thư mục nào cũng chọn được, và ba chip phụ thuộc
// git chỉ hiện khi thư mục đó thật sự có git.
check("hộp chọn thư mục KHÔNG còn dòng giảng giải ở chân",
  !VI["coding.add_folder_note"] && !EN["coding.add_folder_note"] && !/ghiChu:/.test(CD));
const chipGit = M.chipHtml({ muc_quyen: "auto" }, { id: "1", ten: "du-an", duong_dan: "/x", la_git: true });
const chipThuong = M.chipHtml({ muc_quyen: "auto" }, { id: "1", ten: "ghi-chu", duong_dan: "/y", la_git: false });
check("thư mục CÓ git thì hiện đủ nhánh, worktree, điểm hồi",
  ["nhanh", "worktree", "diemhoi", "quyen"].every((k) => chipGit.includes('data-cd="' + k + '"')));
check("thư mục KHÔNG git thì ẩn ba chip phụ thuộc git, vẫn còn mức quyền",
  !/data-cd="(nhanh|worktree|diemhoi)"/.test(chipThuong) && chipThuong.includes('data-cd="quyen"'));
// Chưa gắn thư mục vẫn phải thấy mức quyền: server đã áp mức đó cho MỌI phiên kênh coding
// ngay từ lượt chat đầu (xem `_muc_quyen_luot_chat`), nên giấu chip đi là bắt người dùng chạy
// ở một mức quyền họ không nhìn thấy và không đổi được. Chủ dự án báo lỗi này ở 0.63.4.
check("chưa gắn thư mục thì có chip mời chọn VÀ chip mức quyền",
  (() => { const c = M.chipHtml({}, null);
    return c.includes('data-cd="thumuc"') && c.includes('data-cd="quyen"')
      && !/data-cd="(nhanh|worktree|diemhoi)"/.test(c); })());
check("chip mức quyền nói đúng mức đang chạy, cả khi chưa có thư mục",
  M.chipHtml({ muc_quyen: "suggest" }, null).includes("cd-mq-suggest")
  && M.chipHtml({}, null).includes("cd-mq-auto"));
check("server thật sự áp mức quyền cho phiên chưa gắn thư mục", (() => {
  const ST = fs.readFileSync(path.join(ROOT, "server", "coding_store.py"), "utf8");
  return /def muc_quyen_cua_phien[\s\S]{0,160}MUC_QUYEN_MAC_DINH/.test(ST);
})());
check("tên thư mục trên chip là TÊN, không phải cả đường dẫn",
  M.nhanHienThi({ ten: "du-an", duong_dan: "/home/u/du-an" }) === "du-an" && !chipGit.includes(">/x<"));

// ---- 3. Icon ----
check("icon mục Coding KHÔNG còn là git-branch hay file-code",
  !/coding: "(git-branch|file-code)"/.test(CON));
check("icon mục Coding là ký hiệu lập trình </>", /coding: "code-xml"/.test(CON));
check("icon đó có thật trong bộ icon đã sinh sẵn", (() => {
  const man = JSON.parse(D("icons.manifest.json"));
  const co = Object.values(man.groups).some((g) => g.includes("code-xml"));
  return co && D("vendor/lucide-icons.js").includes('"code-xml":');
})());
check("nhóm Code giữ icon file-code như trước khi có mục Coding",
  /"Code": ic\("file-code"\)/.test(CON));
check("icon nhóm và icon mục KHÔNG trùng nhau",
  (CON.match(/"Code": ic\("([a-z-]+)"\)/) || [])[1] !== (CON.match(/coding: "([a-z-]+)"/) || [])[1]);

// ---- 4. Cột trái MƯỢN nguyên cột hội thoại của trang Trò chuyện ----
check("gắn module lịch sử thật, không tự vẽ danh sách",
  /JavisChatSide\.mount\(/.test(CD) && !/cdPhienDs|cd-phien-ds/.test(CD));
check("lọc theo kênh Coding và thay hành vi nút Hội thoại mới",
  /\{ kenh: S\.kenh, onNew: moPhienMoi \}/.test(CD));
check("KHÔNG bật chế độ gọn, để giữ đủ tab và thanh gom nhóm", !/chiHoiThoai/.test(CD));
check("có chỗ cho chip gom nhóm đậu vào", /proj-chip-host/.test(CD) && /JavisChatSide\.chip\(\)/.test(CD));
check("khung trang dùng lại bộ lớp .chatpage của trang Trò chuyện",
  /class="chatpage"/.test(CD) && /class="chatpage-side"/.test(CD) && /class="chatpage-slot"/.test(CD));
check("và KHÔNG đẻ bộ lớp bố cục thứ hai", !/\.cd-left|\.cd-main|\.cd-page/.test(CSS));
check("bấm một hội thoại ở cột trái thì dải chip cập nhật theo",
  /function bocMoPhien\(\)/.test(CD) && /JavisSessions\.open = function/.test(CD)
  && /function traMoPhien\(\)/.test(CD) && /roi\(\)[\s\S]{0,200}traMoPhien\(\)/.test(CD));

// ---- 4b. Ba chế độ, và Plan phải thật sự lập kế hoạch ----
check("ba chế độ đọc là Plan / Tự động / Toàn quyền",
  VI["coding.mode_suggest"] === "Plan" && VI["coding.mode_auto"] === "Tự động"
  && EN["coding.mode_suggest"] === "Plan");
check("mỗi chế độ có một dòng nói rõ nó cho làm gì",
  ["suggest", "auto", "full"].every((m) => !!VI["coding.mode_" + m + "_note"] && !!EN["coding.mode_" + m + "_note"]));
check("menu chế độ đánh dấu cái đang chọn", /chon: \(S\.rb\.muc_quyen \|\| "auto"\) === m/.test(CD));
check("Plan nhìn khác hai mức kia", /\.cd-mq-suggest\s*\{/.test(CSS) && /\.cd-mq-full\s*\{/.test(CSS));
check("server BẢO engine lập kế hoạch rồi dừng ở chế độ Plan", (() => {
  const ST = fs.readFileSync(path.join(ROOT, "server", "coding_store.py"), "utf8");
  return /KHOI_PLAN/.test(ST) && /KHÔNG sửa file/.test(ST) && /def khoi_prompt/.test(ST);
})());
check("khối đó được nối vào prompt của lượt chat", (() => {
  const MAIN = fs.readFileSync(path.join(ROOT, "server", "main.py"), "utf8");
  return (MAIN.match(/\+ _khoi_coding\(_row0\)/g) || []).length >= 2
    && /def _khoi_coding\(/.test(MAIN);
})());
check("và nói cho engine biết nó đang đứng ở thư mục nào", (() => {
  const ST = fs.readFileSync(path.join(ROOT, "server", "coding_store.py"), "utf8");
  return /Thư mục làm việc: \{cwd\}/.test(ST);
})());

// ---- 5. Luật mượn (giữ từ bản đầu) ----
check("coding.js KHÔNG tự dựng khung chat", !/id="chatArea"|class="transcript"/.test(CD));
check("nhận hàm mượn từ console.js", /opts\.borrow\(/.test(CD) && /#cdSlot/.test(CD));
check("console.js truyền _borrowChatNodes xuống trang Coding",
  /renderCoding[\s\S]{0,400}borrow: _borrowChatNodes/.test(CON));
check("rời trang có gỡ dải chip khỏi #modelBar",
  /function goChip\(\)/.test(CD) && /roi\(\)[\s\S]{0,200}goChip\(\)/.test(CD));
check("rời trang có trả khung chat về cuộc cũ", /traKhungChat\(\)/.test(CD));
check("chip KHÔNG viết lại chip model của app",
  !/class="mb-chip|id="mbOpen/.test(CD) && !/mbModelTxt|mbEffortTxt/.test(CD));
check("dải chip nhét vào chính #modelBar đã mượn", /getElementById\("modelBar"\)/.test(CD));

// ---- 6. Hành động phá huỷ phải hỏi lại, và nói rõ cái gì mất ----
check("rollback hỏi lại", /confirm\(t\("coding\.ckpt_confirm"/.test(CD));
check("câu hỏi rollback nói rõ không hoàn tác", tu("coding.ckpt_confirm", "không hoàn tác"));
check("bỏ thư mục hỏi lại", /confirm\(t\("coding\.forget_confirm"/.test(CD));
check("câu hỏi bỏ thư mục nói rõ THƯ MỤC TRÊN ĐĨA VẪN CÒN", tu("coding.forget_confirm", "vẫn còn nguyên"));
// Chốt cũ ghim `var(--warn)`, mà bảng màu KHÔNG có token tên đó: trình duyệt bỏ cả dòng khai
// báo nên chip Toàn quyền bấy lâu trông y hệt chip thường, còn test thì vẫn xanh vì nó chỉ soi
// mã nguồn chứ không soi token có thật. Nay đòi màu CHỮ và màu NỀN riêng, và đòi chúng khác
// hẳn chip Plan. Việc "token phải có thật" do test_theme_tokens.py canh.
check("mức Toàn quyền nhìn ra được", chipGit.includes("cd-mq-auto")
  && M.chipHtml({ muc_quyen: "full" }, { id: "1", ten: "x", duong_dan: "/x", la_git: true }).includes("cd-mq-full")
  && /\.cd-mq-full\s*\{[^}]*color: var\(--warn-ink\)/.test(CSS)
  && /\.cd-mq-full\s*\{[^}]*background: var\(--warn-wash\)/.test(CSS));
// `(?<![-\w])` để không bắt nhầm `border-color`, thứ hoàn toàn ĐƯỢC PHÉP dùng biến -line.
check("KHÔNG lấy biến viền (-line) làm màu CHỮ: chúng có alpha thấp nên chữ bị chìm",
  !/\.cd-mq-(suggest|full)[^{}]*\{[^}]*(?<![-\w])color: var\(--[a-z]+-line\)/.test(CSS));
check("chip mức quyền giữ màu của nó khi rê chuột, không nhảy về màu chữ thường",
  /\.cd-chip\.cd-mq-full:hover\s*\{[^}]*color: var\(--warn-ink\)/.test(CSS));

// ---- 7. Thêm thư mục là DUYỆT rồi bấm chọn, không phải gõ đường dẫn ----
// Bản 0.63.2 chỉ có một ô chữ trống: trên điện thoại là gõ tay cả đường dẫn tuyệt đối, sai
// một ký tự thì nhận câu "không phải thư mục" mà không biết sai ở đâu.
// Bóc chú thích trước khi soi: file này NÓI về prompt() trong phần giải thích vì sao không
// dùng nó, mà một khẳng định đỏ vì đúng câu giải thích của chính nó thì vô nghĩa.
const CD_MA = CD.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const FP = D("folder-picker.js");
const FP_MA = FP.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
const STYLE = D("style.css");
check("KHÔNG gọi window.prompt", !/\bprompt\s*\(/.test(CD_MA));
check("KHÔNG gọi window.alert", !/\balert\s*\(/.test(CD_MA));
check("thêm thư mục thì MỞ HỘP DUYỆT", /JavisFolderPicker\.open\(/.test(CD_MA));
check("KHÔNG còn ô gõ đường dẫn làm đường chính",
  !/cd-tam-nen|id="cdPath"/.test(CD) && !VI["coding.path_ph"] && !EN["coding.path_ph"]);
check("hộp duyệt đứng trên chính endpoint /browse đã có, không đẻ endpoint mới",
  /fetch\("\/browse\?/.test(FP_MA));
check("và gọi đường md=0: chọn thư mục CODE thì đừng quét đếm .md",
  /md=" \+ \(o\.demMd \? "1" : "0"\)/.test(FP_MA) && /demMd: false/.test(CD_MA));
check("server có đường md=0 và báo thư mục nào là repo git", (() => {
  const MAIN = fs.readFileSync(path.join(ROOT, "server", "main.py"), "utf8");
  return /def _browse_sync\(path: str, dem_md: bool = True\)/.test(MAIN)
    && /def _la_repo\(/.test(MAIN) && /"git": _la_repo\(full\)/.test(MAIN);
})());
check("hộp duyệt MẶC lại bộ lớp .folder-modal/.fm-* có sẵn, không vẽ kiểu riêng",
  /class="folder-modal"/.test(FP) && /class="fm-list"/.test(FP)
  && /\.folder-modal \{/.test(STYLE) && !/\.fp-modal|\.fp-list|\.fp-row/.test(STYLE + CSS));
check("bấm lên trên và bấm vào thư mục con đều duyệt tiếp",
  /duyet\(d\.parent\)/.test(FP_MA) && /duyet\(x\.path\)/.test(FP_MA));
check("vẫn dán được đường dẫn dài rồi Enter", /fp-go/.test(FP_MA) && /key !== "Enter"/.test(FP_MA));
check("lỗi thêm thư mục hiện TẠI CHỖ và giữ hộp mở",
  /return \(r && r\.error\) \|\| t\("coding\.add_err"\)/.test(CD_MA)
  && /if \(loi\) \{ mach\(loi, true\); return; \}/.test(FP_MA));
check("chữ của hộp duyệt có ở cả hai từ điển",
  ["fp.title", "fp.use", "fp.up", "fp.pick", "fp.path_ph"].every((k) => !!VI[k] && !!EN[k]));
// Hộp duyệt mở ra ở thư mục nhà thì trên VPS chỗ đó chỉ có file ẩn, mà /browse lọc hết file
// ẩn, nên hộp hiện ra TRỐNG TRƠN và người dùng lại phải gõ tay đường dẫn (chủ dự án báo).
check("chưa gắn gì thì hộp mở ở màn ĐIỂM XUẤT PHÁT, không đổ thẳng vào thư mục nhà",
  /function veDiem\(\)/.test(FP_MA) && /return p \? taiThuMuc\(p\) : veDiem\(\)/.test(FP_MA));
check("điểm xuất phát lấy từ server, có brain đang mở",
  /fetch\("\/browse\/starts\?brain=/.test(FP_MA) && /brain: brain\(\)/.test(CD_MA));
check("server trả điểm xuất phát: bộ não, thư mục chứa các bộ não, thư mục nhà", (() => {
  const MAIN = fs.readFileSync(path.join(ROOT, "server", "main.py"), "utf8");
  return /@app\.get\("\/browse\/starts"\)/.test(MAIN) && /_brain_root\(brain\)/.test(MAIN)
    && /BRAINS_DIR/.test(MAIN) && /expanduser\("~"\)/.test(MAIN);
})());
check("chỉ trả chỗ CÓ THẬT và không trùng nhau", (() => {
  const MAIN = fs.readFileSync(path.join(ROOT, "server", "main.py"), "utf8");
  const kh = (MAIN.match(/def browse_starts[\s\S]*?return await asyncio/) || [""])[0];
  return /os\.path\.isdir\(p\)/.test(kh) && /normcase/.test(kh);
})());
check("không lấy được điểm nào thì vẫn duyệt thư mục nhà như bản trước",
  /if \(!ds2\.length\) return taiThuMuc\(""\)/.test(FP_MA));
check("có đường VỀ màn điểm xuất phát khi đã duyệt sâu", /data-nha/.test(FP_MA));
check("chữ của màn điểm xuất phát có ở cả hai từ điển",
  ["fp.starts", "fp.starts_note", "fp.start_brain", "fp.start_brains", "fp.start_home"]
    .every((k) => !!VI[k] && !!EN[k]));

check("index.html nạp folder-picker.js TRƯỚC coding.js",
  HTML.indexOf("folder-picker.js") > 0 && HTML.indexOf("folder-picker.js") < HTML.indexOf("coding.js"));

// ---- 7a. Gắn NHIỀU thư mục vào một việc (0.63.8) ----
// Một việc thật hay đụng nhiều thư mục cùng lúc, nên bắt chọn đúng một cái là bắt người dùng
// đổi qua đổi lại giữa chừng (chủ dự án yêu cầu 22/09).
check("menu thư mục là TÍCH CHỌN, bấm vào là thêm/bớt chứ không thay",
  /tich: true/.test(CD_MA) && /ids\.splice\(i, 1\); else ids\.push\(x\.id\)/.test(CD_MA));
check("menu KHÔNG đóng sau mỗi lần tích", /giuMo: true/.test(CD_MA)
  && /if \(x && x\.giuMo && veLai\)/.test(CD_MA));
check("có ô vuông để đọc ra là đang gắn hay không",
  /class="cd-tich"/.test(CD_MA) && /\.cd-tich \{/.test(CSS));
check("gắn nhiều thì chip nói rõ còn mấy thư mục nữa",
  M.chipHtml({ muc_quyen: "auto", so_thu_muc: 3 }, { id: "1", ten: "du-an", duong_dan: "/x" }).includes("+2")
  && !M.chipHtml({ muc_quyen: "auto", so_thu_muc: 1 }, { id: "1", ten: "du-an", duong_dan: "/x" }).includes("+"));
check("server nhận cả DANH SÁCH thư mục cho một phiên", (() => {
  const ST = fs.readFileSync(path.join(ROOT, "server", "coding_store.py"), "utf8");
  const RT = fs.readFileSync(path.join(ROOT, "server", "routes", "coding.py"), "utf8");
  return /def thu_muc_cua_phien\(/.test(ST) && /thu_muc_ids: Optional\[List\[str\]\]/.test(ST)
    && /thu_mucs: str = Form\(None\)/.test(RT);
})());
check("thư mục phụ đi vào prompt bằng đường dẫn tuyệt đối", (() => {
  const ST = fs.readFileSync(path.join(ROOT, "server", "coding_store.py"), "utf8");
  return /ĐƯỜNG DẪN TUYỆT ĐỐI/.test(ST) && /def khoi_prompt[\s\S]{0,2000}thu_muc_cua_phien/.test(ST);
})());
check("git chỉ chạy ở thư mục chính, và nói rõ điều đó", (() => {
  const ST = fs.readFileSync(path.join(ROOT, "server", "coding_store.py"), "utf8");
  return /chỉ chạy ở thư mục làm việc/.test(ST);
})());
// Menu tích chọn vẽ lại sau mỗi lần bấm, mỗi lần lại gắn một bộ nghe "bấm ra ngoài thì đóng".
// Không gỡ thì chúng đọng lại và đóng oan một menu mở sau đó.
check("bộ nghe đóng menu được GỠ chứ không đọng lại",
  /function goBoDong\(\)/.test(CD_MA) && /removeEventListener\("click", _boDong/.test(CD_MA)
  && /function dongMenu\(\)\s*\{\s*goBoDong\(\)/.test(CD_MA));

// ---- 7b. Mở file: bấm trong cây thư mục hay bấm chip "file đang mở" ----
// Lỗi 0.63.4 chủ dự án báo: bấm một file thì LẶNG LẼ không có gì mở ra. Nguyên nhân là
// _borrowNoteEditor của console.js dò khung bằng một DANH SÁCH ID VIẾT CỨNG, mà tên khung của
// trang Coding không có trong đó. Đúng lỗi trang Cộng sự đã dính ở 0.59.2, nên lần này canh
// cả LUẬT (khung tự khai bằng thuộc tính) chứ không chỉ canh thêm một cái tên.
check("khung trình sửa của trang Coding tự khai data-ne-host", /id="cdEdit" data-ne-host/.test(CD));
check("console.js dò khung bằng thuộc tính, KHÔNG dò bằng danh sách id viết cứng",
  /querySelector\("\[data-ne-host\]"\)/.test(CON)
  && !/getElementById\("chatPageEdit"\) \|\| document\.getElementById\("wsEdit"\)/.test(CON));
check("cả ba trang mượn khung chat đều khai khung trình sửa của mình",
  /id="chatPageEdit" data-ne-host/.test(CON)
  && /id="wsEdit" data-ne-host/.test(D("workspace.js"))
  && /id="cdEdit" data-ne-host/.test(CD));
check("rời trang Coding thì trả trình sửa về chỗ cũ (qua _returnChatNodes)",
  /renderCoding[\s\S]{0,400}_returnChatNodes\(\)/.test(CON)
  && /function _returnChatNodes\(\)[\s\S]{0,400}_returnNoteEditor\(\)/.test(CON));

// ---- 8. Điện thoại ----
// Ngăn kéo trên màn hẹp và nút thu gọn nay là của .chatpage (console.js _injectChatCss), nên
// canh ở đó chứ không canh một bộ lớp riêng đã bỏ.
check("bề rộng hẹp thì cột hội thoại thành ngăn kéo (luật của .chatpage)",
  /\.chatpage-side\{ position:absolute/.test(CON) || /chatpage\.side-mo/.test(CON)
  || /\.chatpage\.side-thu \.chatpage-side/.test(CON));
check("nút thu gọn cột dùng đúng lớp của trang Trò chuyện",
  /cp-side-toggle/.test(CD) && /classList\.toggle\("side-thu"\)/.test(CD));
check("chữ trên điện thoại không nhỏ hơn 16px",
  /@media \(max-width: 900px\)[\s\S]{0,400}\.cd-chip \{ font-size: 16px/.test(CSS)
  && /@media \(max-width: 900px\)[\s\S]{0,600}\.cd-menu button \{ font-size: 16px/.test(CSS)
  && /\.fm-path \.fp-go \{[^}]*font-size: 16px/.test(STYLE));

// ---- 8a. Menu thư mục không được tràn màn hình (0.63.10) ----
// Tên thư mục và đường dẫn là chữ phụ, để 16px trên máy tính thì menu phình ra choán màn
// hình; danh sách dài lại tràn khỏi khung, đè cả thanh điều hướng (chủ dự án báo 22/09).
check("trên máy tính, tên thư mục và đường dẫn là chữ nhỏ",
  /\.cd-menu button \{[^}]*font-size: 14px/.test(CSS)
  && /\.cd-menu button small \{[^}]*font-size: 12px/.test(CSS));
check("menu dài thì tự cuộn chứ không tràn ra ngoài",
  /\.cd-menu \{[^}]*overflow-y: auto/.test(CSS)
  && /\.cd-menu \{[^}]*max-height:/.test(CSS));
// Luật cho ô chữ CO được phải chừa ô tích ra: nới cả hai thì ô vuông 16px bị kéo dài thành
// thanh ngang (thấy trong ảnh chụp thử 22/09).
check("đường dẫn dài cắt bằng dấu ba chấm, ô tích vẫn vuông",
  /\.cd-menu button\.tich > span:not\(\.cd-tich\) \{[^}]*min-width: 0/.test(CSS));
check("menu đo chỗ trống thật quanh chip rồi mới đặt",
  /m\.style\.maxHeight/.test(CD_MA) && /W\.innerHeight/.test(CD_MA)
  && /m\.offsetWidth/.test(CD_MA));

// ---- 9. Nối vào rail ----
check("coding có trong RAIL_ITEMS", /"terminal", "coding"/.test(CON));
check("coding nằm trong NHÓM Code", /ids: \["terminal", "coding"\]/.test(CON));
check("index.html nạp coding.js TRƯỚC console.js",
  HTML.indexOf("coding.js") > 0 && HTML.indexOf("coding.js") < HTML.indexOf("console.js?"));
check("nhãn trang có ở cả hai từ điển", !!VI["page.coding.label"] && !!EN["page.coding.label"]);

console.log();
if (fails.length) { console.log("FAIL " + fails.length + " test: " + fails.join(", ")); process.exit(1); }
console.log("TẤT CẢ PASS");
