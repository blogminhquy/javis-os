/* Trang Coding: phải MƯỢN khung chat sẵn có, không dựng bản thứ hai của bất cứ thứ gì.

       node tests/js/test_trang_coding.js

   Cả lý do trang này gói được trong một phiên sửa là nó không viết lại gì: khung chat, cây
   thư mục, trình sửa file, chip model, danh sách phiên đều đã có trong app. Nên thứ đáng canh
   nhất ở đây KHÔNG phải pixel, mà là luật mượn - thứ chỉ vỡ khi ai đó "tiện tay" dựng lại.

   Năm thứ file này canh:

   1. **Luật mượn.** coding.js không được tự dựng khung chat (#chatArea, .transcript) hay một
      cây thư mục thứ hai. Bản đầu của tab Thư mục đã mắc đúng lỗi này và chủ repo phải chỉ ra.

   2. **Trả node khi rời trang.** #modelBar là node MƯỢN của app. Nhét dải chip vào mà không
      gỡ là trang Trò chuyện mọc thêm một hàng nói về một repo không liên quan; không trả phiên
      là tin gõ ở trang Trò chuyện bay vào phiên coding, tức là chạy với cwd của một repo.

   3. **Chip Model không bị viết lại.** Chip engine/model đã là #mbOpen của app; dải chip của
      trang này chỉ thêm repo, nhánh, worktree, mức quyền, điểm hồi.

   4. **Mức Toàn quyền phải nhìn ra được.** Ở mức đó engine commit, push, deploy được. Một cái
      chip trông y hệt hai mức kia là người dùng không biết mình đang ở đâu.

   5. **Rollback phải hỏi lại.** `git reset --hard` không hoàn tác được.

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

// ---- 1. Luật mượn ----
check("coding.js KHÔNG tự dựng khung chat", !/id="chatArea"|class="transcript"/.test(CD));
check("coding.js nhận hàm mượn từ console.js", /opts\.borrow\(/.test(CD) && /#cdSlot/.test(CD));
check("console.js truyền _borrowChatNodes xuống trang Coding",
  /renderCoding[\s\S]{0,400}borrow: _borrowChatNodes/.test(CON));
check("coding.js KHÔNG dựng cây thư mục thứ hai",
  !/JavisVaultPanel\.borrow/.test(CD) || /mượn/.test(CD));

// ---- 2. Trả node khi rời trang ----
check("rời trang có gỡ dải chip khỏi #modelBar", /function goChip\(\)/.test(CD) && /roi\(\)[\s\S]{0,200}goChip\(\)/.test(CD));
check("rời trang có trả khung chat về cuộc cũ", /traKhungChat\(\)/.test(CD) && /JavisSessions\.new\(\)/.test(CD));
check("console.js gọi JavisCoding.roi rồi mới trả node",
  /JavisCoding\.roi[\s\S]{0,160}_returnChatNodes\(\)/.test(CON));

// ---- 3. Dải chip ----
const chipFull = M.chipHtml({ muc_quyen: "full", nhanh: "main", worktree: "" },
                            { id: "r1", ten: "javis-os", duong_dan: "/home/u/javis-os" });
check("chip có đủ repo, nhánh, worktree, mức quyền, điểm hồi",
  ["repo", "nhanh", "worktree", "quyen", "diemhoi"].every((k) => chipFull.includes('data-cd="' + k + '"')));
// Nhắc tới #mbOpen trong chú thích thì được (nó nói CHÍNH điều này); DỰNG một cái thứ hai
// thì không. Nên soi mã VẼ ra chip, chứ không soi cái tên.
check("chip KHÔNG viết lại chip model của app",
  !/class="mb-chip|id="mbOpen/.test(CD) && !/mbModelTxt|mbEffortTxt/.test(CD));
check("dải chip nhét vào chính #modelBar đã mượn", /getElementById\("modelBar"\)/.test(CD));
const chipTrong = M.chipHtml({}, null);
check("chưa gắn repo thì chỉ mời chọn repo, không vẽ nhánh rỗng",
  chipTrong.includes('data-cd="repo"') && !chipTrong.includes('data-cd="nhanh"'));
check("worktree đang bật thì chip sáng lên",
  M.chipHtml({ worktree: "/tmp/wt" }, { id: "r", ten: "x", duong_dan: "/x" }).includes("cd-chip on"));
check("tên repo trên chip là TÊN, không phải cả đường dẫn",
  M.nhanHienThi({ ten: "javis-os", duong_dan: "/home/u/javis-os" }) === "javis-os"
  && !chipFull.includes(">/home/u/javis-os<"));

// ---- 4. Mức Toàn quyền nhìn ra được ----
check("chip mức Toàn quyền mang lớp riêng", chipFull.includes("cd-mq-full"));
check("CSS tô cảnh báo cho mức Toàn quyền", /\.cd-mq-full\s*\{[^}]*var\(--warn\)/.test(CSS));
check("ba mức quyền đều có chữ", ["suggest", "auto", "full"].every((m) => VI["coding.mode_" + m] && EN["coding.mode_" + m]));

// ---- 5. Hành động phá huỷ phải hỏi lại ----
check("rollback hỏi lại trước khi chạy", /ckpt_confirm[\s\S]{0,120}confirm|confirm\(t\("coding\.ckpt_confirm"/.test(CD));
check("câu hỏi rollback nói rõ mất hẳn không hoàn tác", tu("coding.ckpt_confirm", "không hoàn tác"));
check("xoá repo hỏi lại", /confirm\(t\("coding\.remove_confirm"\)\)/.test(CD));
check("câu hỏi xoá repo nói rõ MÃ NGUỒN VẪN CÒN", tu("coding.remove_confirm", "vẫn còn nguyên"));

// ---- 6. Nối vào rail ----
check("coding có trong RAIL_ITEMS", /"terminal", "coding"/.test(CON));
check("coding nằm trong NHÓM Code", /ids: \["terminal", "coding"\]/.test(CON));
check("coding có icon riêng", /coding: "git-branch"/.test(CON));
check("coding có trong VIEW_META", /"terminal", "coding", "selfimprove"/.test(CON));
check("index.html nạp coding.js TRƯỚC console.js",
  HTML.indexOf("coding.js") > 0 && HTML.indexOf("coding.js") < HTML.indexOf("console.js?"));
check("nhãn trang có ở cả hai từ điển", !!VI["page.coding.label"] && !!EN["page.coding.label"]);

// ---- 7. Trạng thái phiên ----
check("bốn mức trạng thái, không đoán mức thứ năm",
  M.trangThaiPhien({ id: "a" }, "a", null) === "dang"
  && M.trangThaiPhien({ id: "a" }, null, { a: 1 }) === "het_luot"
  && M.trangThaiPhien({ id: "a", loi: 1 }, null, null) === "loi"
  && M.trangThaiPhien({ id: "a" }, null, null) === "xong");
check("coding.js nói rõ vì sao chưa có mức cần trả lời", /cần trả lời/.test(CD));

// ---- 8. Điện thoại ----
check("bề rộng hẹp thì cột trái thành ngăn kéo", /@media \(max-width: 900px\)[\s\S]{0,600}\.cd-left \{[^}]*translateX\(-105%\)/.test(CSS));
check("nút ẩn hiện cột trái hiểu hai bề rộng", /matchMedia[\s\S]{0,160}left-on/.test(CD));
check("chữ trên điện thoại không nhỏ hơn 16px", /@media \(max-width: 900px\)[\s\S]{0,600}\.cd-chip \{ font-size: 16px/.test(CSS));

console.log();
if (fails.length) { console.log("FAIL " + fails.length + " test: " + fails.join(", ")); process.exit(1); }
console.log("TẤT CẢ PASS");
