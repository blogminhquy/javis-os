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
check("nói rõ không cần là repo git", tu("coding.add_folder_note", "không cần là repo git"));
const chipGit = M.chipHtml({ muc_quyen: "auto" }, { id: "1", ten: "du-an", duong_dan: "/x", la_git: true });
const chipThuong = M.chipHtml({ muc_quyen: "auto" }, { id: "1", ten: "ghi-chu", duong_dan: "/y", la_git: false });
check("thư mục CÓ git thì hiện đủ nhánh, worktree, điểm hồi",
  ["nhanh", "worktree", "diemhoi", "quyen"].every((k) => chipGit.includes('data-cd="' + k + '"')));
check("thư mục KHÔNG git thì ẩn ba chip phụ thuộc git, vẫn còn mức quyền",
  !/data-cd="(nhanh|worktree|diemhoi)"/.test(chipThuong) && chipThuong.includes('data-cd="quyen"'));
check("chưa gắn thư mục thì chỉ một chip mời chọn",
  (() => { const c = M.chipHtml({}, null);
    return c.includes('data-cd="thumuc"') && !/data-cd="(nhanh|quyen|worktree|diemhoi)"/.test(c); })());
check("tên thư mục trên chip là TÊN, không phải cả đường dẫn",
  M.nhanHienThi({ ten: "du-an", duong_dan: "/home/u/du-an" }) === "du-an" && !chipGit.includes(">/x<"));

// ---- 3. Icon ----
check("icon mục Coding KHÔNG còn là git-branch", !/coding: "git-branch"/.test(CON));
check("icon mục Coding nói về mã nguồn", /coding: "file-code"/.test(CON));
check("nhóm Code đổi icon để không trùng mục con", /"Code": ic\("wrench"\)/.test(CON));

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
check("mức Toàn quyền nhìn ra được", chipGit.includes("cd-mq-auto")
  && M.chipHtml({ muc_quyen: "full" }, { id: "1", ten: "x", duong_dan: "/x", la_git: true }).includes("cd-mq-full")
  && /\.cd-mq-full\s*\{[^}]*var\(--warn\)/.test(CSS));

// ---- 7. Thêm thư mục bằng khung trong app, không phải hộp hệ thống ----
// Bóc chú thích trước khi soi: file này NÓI về prompt() trong phần giải thích vì sao không
// dùng nó, mà một khẳng định đỏ vì đúng câu giải thích của chính nó thì vô nghĩa.
const CD_MA = CD.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
check("KHÔNG gọi window.prompt", !/\bprompt\s*\(/.test(CD_MA));
check("KHÔNG gọi window.alert", !/\balert\s*\(/.test(CD_MA));
check("có khung nhập đường dẫn riêng", /cd-tam-nen/.test(CD) && /\.cd-tam input/.test(CSS));
check("lỗi thêm thư mục hiện tại chỗ", /cdTamLoi/.test(CD) && /\.cd-tam-loi/.test(CSS));

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
  && /\.cd-tam input \{[^}]*font-size: 16px/.test(CSS));

// ---- 9. Nối vào rail ----
check("coding có trong RAIL_ITEMS", /"terminal", "coding"/.test(CON));
check("coding nằm trong NHÓM Code", /ids: \["terminal", "coding"\]/.test(CON));
check("index.html nạp coding.js TRƯỚC console.js",
  HTML.indexOf("coding.js") > 0 && HTML.indexOf("coding.js") < HTML.indexOf("console.js?"));
check("nhãn trang có ở cả hai từ điển", !!VI["page.coding.label"] && !!EN["page.coding.label"]);

console.log();
if (fails.length) { console.log("FAIL " + fails.length + " test: " + fails.join(", ")); process.exit(1); }
console.log("TẤT CẢ PASS");
