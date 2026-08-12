/* Hai thứ hỏng trên ĐIỆN THOẠI mà trên máy tính không thấy gì.

       node tests/js/test_nhat_ky_va_thu_muc_mobile.js

   Chủ repo gửi ảnh chụp màn hình (2026-08-12), hai lỗi rời nhau:

   1. Tab "Thư mục" ở trang Trò chuyện bấm vào chỉ thấy một khoảng TRẮNG. Không lỗi, không
      thông báo. Nguyên nhân: tab đó không dựng cây riêng mà MƯỢN đúng node .hud-left của
      màn chính - mà console.css lại ẩn hẳn .hud-left trên điện thoại. Luật ẩn đi theo node
      sang chỗ mới. Đúng cái giá của việc mượn node: mượn cả những luật CSS đang dính vào nó.

   2. Trang Nhật ký cập nhật in ra nguyên "**Bấm vào link...**" kèm dấu sao và dấu huyền
      quanh mỗi tên file. CHANGELOG.md là markdown, mà trang này lại in bằng esc(). Trên màn
      hẹp thì dấu nhiều hơn chữ. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const STYLE = D("style.css");
const CCSS = D("console.css");
const CON = D("console.js");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Tab "Thư mục" phải hiện được trên điện thoại
// ============================================================
// Điều kiện của lỗi: console.css CÓ ẩn .hud-left trên màn hẹp. Nếu luật đó biến mất thì test
// dưới không còn ý nghĩa - canh luôn để không bảo vệ một thứ đã hết tồn tại.
check("tiền đề: console.css vẫn ẩn .hud-left trên màn hẹp",
  /\.hud-left \{ display: none;/.test(CCSS));

const muon = /\.cside-pane > \.hud-left \{([^}]*)\}/.exec(STYLE);
check("bóc được luật panel Vault khi bị mượn", !!muon);
check("CANARY: node mượn được bật hiện lại (không thì cả tab trắng)",
  !!muon && /display:\s*flex/.test(muon[1]));
// Hai lớp thắng một lớp trong media query - không cần !important. Nếu ai đó hạ xuống một lớp
// thì luật ẩn thắng trở lại và tab trắng y như cũ, mà nhìn code không thấy gì sai.
check("CANARY: chọn bằng HAI lớp để thắng luật một lớp trong media query",
  /\.cside-pane > \.hud-left/.test(STYLE));
// Pane đang tắt vẫn phải display:none, nếu không cây thư mục đổ xuống dưới danh sách hội thoại.
check("pane không hoạt động vẫn ẩn", /\.cside-pane \{ display: none;/.test(STYLE));

// ============================================================
// 2. Nhật ký cập nhật phải dựng markdown, không in dấu thô
// ============================================================
// Bóc đúng hàm ra chạy thật, không đọc chữ trong source: thứ cần canh là ĐẦU RA.
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
  .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const src = /function _clInline\(s\) \{[\s\S]*?\n  \}/.exec(CON);
check("bóc được hàm dựng dòng nhật ký", !!src);
let _clInline = null;
if (src) _clInline = new Function("esc", "return (" + src[0].replace(/^function/, "function") + ")")(esc);

if (_clInline) {
  check("CANARY: **đậm** ra thẻ đậm chứ không ra dấu sao",
    _clInline("**Bấm vào link** thì mở") === "<strong>Bấm vào link</strong> thì mở");
  check("CANARY: `mã` ra thẻ code chứ không ra dấu huyền",
    _clInline("ghi `LLM%20Wiki.md` vào") === "ghi <code>LLM%20Wiki.md</code> vào");
  // Dấu sao NẰM TRONG một đoạn mã là dấu sao thật, không phải lệnh tô đậm.
  check("dấu sao trong đoạn mã giữ nguyên",
    _clInline("`a ** b`") === "<code>a ** b</code>");
  // esc() chạy TRƯỚC khi dựng thẻ nên không có đường nào chèn HTML vào trang, kể cả khi
  // CHANGELOG.md bị sửa bậy.
  check("CANARY: HTML trong nhật ký bị vô hiệu hoá",
    _clInline("<script>x</script> **đậm**") === "&lt;script&gt;x&lt;/script&gt; <strong>đậm</strong>");
  check("dòng không có dấu gì thì giữ nguyên",
    _clInline("chỉ là một câu bình thường") === "chỉ là một câu bình thường");
  check("chuỗi rỗng / null không nổ", _clInline(null) === "" && _clInline("") === "");
}

// Cả hai chỗ in dòng nhật ký đều phải đi qua hàm này - trang Nhật ký VÀ khối "Bản mới có gì"
// trong thẻ cập nhật. Sót một chỗ là chỗ đó vẫn hiện dấu thô.
check("CANARY: trang Nhật ký dùng hàm dựng",
  /\(s\.items \|\| \[\]\)\.map\(it => `<li>\$\{_clInline\(it\)\}<\/li>`\)/.test(CON));
check("CANARY: khối 'Bản mới có gì' cũng dùng hàm dựng",
  /items\.map\(it => `<li>\$\{_clInline\(it\)\}<\/li>`\)/.test(CON));
check("không còn chỗ nào in dòng nhật ký bằng esc thô",
  !/<li>\$\{esc\(it\)\}<\/li>/.test(CON));

// Đường dẫn dài trong đoạn mã phải ngắt được: trang đọc chữ mà cuộn ngang là hỏng trên điện thoại.
check("đoạn mã dài ngắt dòng được", /\.cl-sec li code[^}]*overflow-wrap:anywhere/.test(CON));

console.log("");
if (fails.length) { console.log("THẤT BẠI " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("OK - test_nhat_ky_va_thu_muc_mobile: tất cả pass");
