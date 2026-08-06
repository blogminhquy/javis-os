/* Khung chọn skill trong màn sửa Agent + phân trang các khung nhật ký.

       node tests/js/test_chon_skill_va_phan_trang.js

   Hai việc nhỏ đi chung một file vì cùng một bài học: đừng đẻ bản thứ hai của thứ đã có.

   Phần chọn skill có một bẫy chỉ lộ ra khi dùng thật và MẤT DỮ LIỆU IM LẶNG: khung có bộ lọc
   mà lúc lưu lại đi đọc trạng thái từ DOM thì mọi skill đang bị lọc khỏi màn hình sẽ mất
   tick. Người sửa agent gõ tìm "email", tick một cái, bấm Lưu - và 54 skill đã gán trước đó
   biến mất. Không có thông báo nào. Nên trạng thái phải nằm trong Set, DOM chỉ là hình chiếu.

   Phần phân trang thì canh chuyện chép khối: trước đây chỉ trang Việc định kỳ có phân trang,
   viết thẳng trong hàm render của nó. Chép ra thành bản thứ hai và thứ ba là ba bản trôi
   lệch nhau ngay lần sửa đầu tiên. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const STUDIO = D("studio.js");
const CONSOLE = D("console.js");
const CSS = D("style.css");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// A. Khung chọn skill
// ============================================================
check("có hàm vẽ khung chọn skill riêng", /function renderSkillPick\(box, skills, chosen\)/.test(STUDIO));
check("form Agent có ô tìm skill", STUDIO.indexOf('id="spSearch"') !== -1);
check("có ô đếm đã chọn bao nhiêu", STUDIO.indexOf('id="spCount"') !== -1);
check("có nút bỏ chọn hết", STUDIO.indexOf('id="spClear"') !== -1);

// Nhóm phải lấy từ field `group` sẵn có, đúng cái trang Skills đang dùng - không đẻ cách
// phân loại thứ hai để rồi hai chỗ hiểu khác nhau về cùng một skill.
check("gom nhóm theo field group sẵn có của skill", /const g = s\.group \|\| "Chung";/.test(STUDIO));
check("tìm không dấu (gõ 'viet email' ra 'Viết email')", /function _spNoAccent\(s\)/.test(STUDIO));
check("tìm theo cả tên, slug, nhóm và mô tả",
  /_spNoAccent\(`\$\{s\.name\} \$\{s\.slug\} \$\{s\.group \|\| ""\} \$\{s\.description \|\| ""\}`\)/.test(STUDIO));

// ---- Bẫy mất tick ----
check("CANARY: trạng thái chọn giữ trong Set, không đọc từ DOM",
  /const chosen = new Set\(a \? \(a\.skills \|\| \[\]\) : \[\]\);/.test(STUDIO));
check("CANARY: lúc lưu đọc từ Set (không phải querySelectorAll input:checked)",
  /const sk = \[\.\.\.chosen\]\.join\(","\);/.test(STUDIO));
check("CANARY: không còn đường đọc tick từ DOM lúc lưu",
  STUDIO.indexOf('querySelectorAll("#skillPick input:checked")') === -1);

// ---- Hành vi sổ nhóm ----
check("đang tìm thì nhóm khớp tự sổ ra", /const open = !!nq \|\| openGroups\.has\(g\);/.test(STUDIO));
check("nhóm có skill đã tick thì mở sẵn khi vào form",
  /skills\.filter\(s => chosen\.has\(s\.slug\)\)\.map\(s => s\.group \|\| "Chung"\)/.test(STUDIO));
check("CSS cho khung nhóm skill", /\.sp-g-head \{/.test(CSS) && /\.sp-groups \{/.test(CSS));
check("danh sách skill có giới hạn chiều cao (55+ skill không đẩy nút Lưu xuống dưới màn hình)",
  /\.sp-groups \{[^}]*max-height:/.test(CSS));

// ============================================================
// B. Phân trang
// ============================================================
check("có helper phân trang dùng chung", /function pager\(box, items, perPage, renderPage, emptyHtml\)/.test(CONSOLE));
check("CSS thanh lật trang gom về một chỗ", /\.jv-pager \{/.test(CSS));

// Ba chỗ dùng, và KHÔNG chỗ nào tự vẽ lại nút Trước/Sau.
const dung = (CONSOLE.match(/\bpager\(/g) || []).length;
check("dùng ở ít nhất 4 chỗ (loop, nhật ký học, commit học, bảng lượt gần nhất)", dung >= 4, dung);
check("CANARY: khối phân trang cũ của trang Việc định kỳ đã gỡ, không còn bản thứ hai",
  CONSOLE.indexOf("lpLogPrev") === -1 && CONSOLE.indexOf("lp-pager") === -1);

// Phân trang mà nguồn vẫn cắt ở 10 mục thì chẳng có gì để lật.
check("CANARY: nhật ký học tải sâu hơn hẳn (không còn limit=10)",
  /\/learn\/log\?brain=\$\{encodeURIComponent\(fbrain\(\)\)\}&limit=200/.test(CONSOLE));
check("CANARY: commit học tải sâu hơn (không còn limit=12)",
  /\/learn\/review\?brain=\$\{encodeURIComponent\(fbrain\(\)\)\}&limit=60/.test(CONSOLE));
// Bảng "Lượt gần nhất" biến mất cùng trang Tiết kiệm ở 0.24.7: nó liệt kê task_id,
// execution_path và độ lệch ước lượng - ngôn ngữ của người vận hành máy, không phải của
// người đang trả tiền token. Giữ lại phép thử chống cắt cứng cho các bảng còn lại.
check("CANARY: không bảng nào cắt cứng 60 dòng rồi bỏ phần còn lại",
  CONSOLE.indexOf("tasks.slice(0, 60)") === -1);
check("CANARY: trang Tiết kiệm đã gộp vào Mức dùng, không còn bảng chẩn đoán",
  CONSOLE.indexOf('id="rtTasks"') === -1 && CONSOLE.indexOf("renderRuntime") === -1);

// ---- Chạy thật helper để chắc nó lật đúng ----
const src = CONSOLE.slice(CONSOLE.indexOf("function pager(box, items"));
const body = src.slice(0, src.indexOf("\n  }\n") + 5);
const pager = new Function("return " + body.trim())();
const box = {
  innerHTML: "",
  _btn: {},
  querySelector(sel) { return this._btn[sel] || null; },
};
// Nút chỉ có thật khi HTML vừa vẽ ra chứa data-pg tương ứng.
const lam = (items, per) => {
  box._btn = {};
  const nhan = {};
  box.querySelector = (sel) => (box.innerHTML.indexOf(sel.replace(/[[\]]/g, "").replace("data-pg=", "data-pg=")) !== -1
    ? (nhan[sel] = nhan[sel] || {}) : null);
  pager(box, items, per, (page) => page.map((x) => `<i>${x}</i>`).join(""), "<em>trống</em>");
  return nhan;
};
lam([], 3);
check("danh sách rỗng thì hiện câu trống, không vẽ nút", box.innerHTML === "<em>trống</em>");
lam([1, 2], 3);
check("một trang thì không vẽ thanh lật", box.innerHTML.indexOf("jv-pager") === -1);
const nhan = lam([1, 2, 3, 4, 5], 2);
check("nhiều trang thì trang đầu chỉ hiện đúng số mục của nó",
  box.innerHTML.indexOf("<i>1</i><i>2</i>") === 0 && box.innerHTML.indexOf("<i>3</i>") === -1);
check("có thanh lật kèm tổng số mục", /Trang 1\/3 · 5 mục/.test(box.innerHTML));
check("trang đầu thì nút Trước bị khoá", /data-pg="prev" disabled/.test(box.innerHTML));
nhan['[data-pg="next"]'].onclick();
check("bấm Sau thì sang trang kế", box.innerHTML.indexOf("<i>3</i><i>4</i>") === 0);
nhan['[data-pg="next"]'].onclick();
check("trang cuối chỉ còn phần dư", box.innerHTML.indexOf("<i>5</i>") === 0);
check("trang cuối thì nút Sau bị khoá", /data-pg="next" disabled/.test(box.innerHTML));
nhan['[data-pg="prev"]'].onclick();
check("bấm Trước thì lùi lại", box.innerHTML.indexOf("<i>3</i><i>4</i>") === 0);

if (fails.length) {
  console.log("\nFAIL - test_chon_skill_va_phan_trang: " + fails.length + " lỗi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_chon_skill_va_phan_trang: tất cả pass");
