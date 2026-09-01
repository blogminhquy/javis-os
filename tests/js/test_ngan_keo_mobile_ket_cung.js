/* Điện thoại: mở một file để sửa thì ngăn kéo Hội thoại/Thư mục phải đóng được.

       node tests/js/test_ngan_keo_mobile_ket_cung.js

   Chủ repo báo 01/09 kèm ảnh chụp màn hình điện thoại: "khi mobile mở 1 file chỉnh sửa thì
   narbar bị chết cứng không có đóng mà luôn hiện ở đấy, không làm cách nào đóng được".

   Đúng vậy, và nó là ba đường đóng cùng chết một lúc chứ không phải một lỗi:

     1. Nút bật/tắt (.cp-side-toggle) nằm trên thanh tiêu đề của khung chính, mà ngăn kéo rộng
        84vw phủ đè lên đó.
     2. Handler "chạm khung chat thì đóng" gắn trên .chatpage-slot, mà mở file để sửa thì
        chính slot đó bị `display:none` nhường chỗ cho trình sửa.
     3. Handler "chạm một dòng trong ngăn kéo thì đóng" chỉ bắt .cside-item (dòng hội thoại),
        còn cây Vault ở tab Thư mục dựng bằng .vt-node.

   Và ngăn kéo KHÔNG có nền mờ, nên cũng chẳng có chỗ nào để chạm-ra-ngoài. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const JS = D("console.js");

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

// Khối CSS màn hẹp: mọi luật dưới đây chỉ được áp cho điện thoại, không đụng desktop.
const mobile = (JS.match(/@media \(max-width:860px\)\{[\s\S]*?\n    \}`/) || [""])[0];
check("tìm được khối CSS màn hẹp của trang Trò chuyện", mobile.length > 200);

// ---------------------------------------------------------------- 1. Nền mờ
check("ngăn kéo mở ra có NỀN MỜ để chạm ra ngoài mà đóng",
  /\.chatpage\.side-open::before\{[^}]*content:""/.test(mobile), mobile.slice(0, 120));
const nen = (mobile.match(/\.chatpage\.side-open::before\{[^}]*\}/) || [""])[0];
check("nền mờ phủ kín khung", /inset:0/.test(nen), nen);
check("nền mờ có màu (không phải một lớp trong suốt vô hình)", /background:/.test(nen), nen);
// Thứ tự chồng lớp là cả vấn đề: nền phải NẰM TRÊN nội dung nhưng DƯỚI chính ngăn kéo, không
// thì hoặc nó không hứng được cú chạm, hoặc nó che mất ngăn kéo.
const zNen = Number((nen.match(/z-index:(\d+)/) || [])[1]);
const zKeo = Number(((mobile.match(/\.chatpage-side\{[^}]*\}/) || [""])[0].match(/z-index:(\d+)/) || [])[1]);
check(`nền mờ (z=${zNen}) nằm DƯỚI ngăn kéo (z=${zKeo})`, zNen > 0 && zKeo > 0 && zNen < zKeo);

// ---------------------------------------------------------------- 2. Chạm nền = đóng
// Pseudo-element không phải một node riêng: cú chạm rơi vào chính .chatpage, nên điều kiện
// phải là e.target === page. So bằng closest(".chatpage") là bắt luôn cả cú chạm trong ngăn kéo.
check("có handler đóng khi chạm nền mờ",
  /page\.addEventListener\("click", \(e\) => \{[\s\S]{0,220}e\.target === page[\s\S]{0,120}remove\("side-open"\)/.test(JS));
check("và chỉ áp trên màn hẹp", /e\.target === page[\s\S]{0,80}isNar\(\)|isNar\(\) && e\.target === page/.test(JS));

// ---------------------------------------------------------------- 3. Mở file = đóng ngăn kéo
// Chốt ở _borrowNoteEditor vì đó là chỗ MỌI đường mở file đi qua (bấm file trong cây, bấm
// [[wikilink]], bấm chip file đang ghim). Gắn ở từng handler là sót đường.
const borrow = (JS.match(/function _borrowNoteEditor\(into\)[\s\S]*?\n  \}/) || [""])[0];
check("tìm được _borrowNoteEditor", borrow.length > 100);
check("mở file trên màn hẹp thì đóng luôn ngăn kéo",
  /remove\("side-open"\)/.test(borrow), borrow);
check("và chỉ đóng khi thật sự là màn hẹp",
  /matchMedia\("\(max-width: 860px\)"\)\.matches/.test(borrow), borrow);
check("đọc #chatPage từ DOM chứ không dựa vào biến cục bộ của renderChat",
  /getElementById\("chatPage"\)/.test(borrow), borrow);
// Trang Tệp tin cũng mượn chính trình sửa này và KHÔNG có #chatPage - không được nổ ở đó.
check("không có #chatPage (trang Tệp tin) thì bỏ qua, không nổ",
  /const _cp = document\.getElementById\("chatPage"\);\s*\n\s*if \(_cp &&/.test(borrow), borrow);

// ---------------------------------------------------------------- 4. Đường cũ vẫn còn
// Ba đường đóng cũ không bị gỡ - chúng vẫn đúng ở các ca khác, chỉ là không đủ.
check("vẫn đóng khi chạm khung chat", /slot\.addEventListener\("click"[\s\S]{0,140}remove\("side-open"\)/.test(JS));
check("vẫn đóng khi chọn một hội thoại trong ngăn kéo",
  /closest\("\.cside-item"\)\) page\.classList\.remove\("side-open"\)/.test(JS));
check("nút bật/tắt vẫn toggle như cũ trên màn hẹp",
  /if \(isNar\(\)\) \{ page\.classList\.toggle\("side-open"\); return; \}/.test(JS));

check("index.html bump console.js để trình duyệt không giữ bản cũ",
  /console\.js\?v=(12[3-9]|1[3-9]\d|[2-9]\d\d)/.test(D("index.html")),
  (D("index.html").match(/console\.js\?v=\d+/) || [])[0]);

console.log();
if (fails.length) {
  console.log("FAIL " + fails.length + ": " + fails.join("; "));
  process.exit(1);
}
console.log("Tất cả xanh.");
