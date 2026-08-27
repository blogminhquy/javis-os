/* Trang Trò chuyện, mở file .md: TRÌNH SỬA TRÀN SANG PHẢI ĐÈ LÊN CỘT HỘI THOẠI.

       node tests/js/test_trinh_sua_de_len_cot_hoi_thoai.js

   Lỗi thật chủ repo báo 27/08/2026 (ảnh chụp: chữ trong cột hội thoại bên phải bị cắt mất
   mép trái, đọc thành "não thứ 2" đó bắt họ", "n giản đến mức bạn"). Không phải cột hội
   thoại vẽ sai chỗ - nó đứng đúng ô grid của nó; chính TRÌNH SỬA phình rộng hơn cột trái
   rồi nằm đè lên. Đo bằng Chromium: khung trái 350px mà trình sửa vẫn 434px, đè 70px.

   Dây chuyền gây lỗi có ba mắt, thiếu một mắt là bệnh quay lại:

     1. `.chatpage-edit` để `display:flex` mặc định, tức flex-direction ROW. Trình sửa thành
        item của một hàng ngang.
     2. Item hàng ngang có `min-width:auto` = min-content, nên nó TỪ CHỐI co xuống dưới
        min-content. Ô grid `minmax(0,1fr)` co lại được, item thì không -> phần thừa tràn
        sang phải, và trình sửa có nền đục nên nó che luôn chữ bên dưới.
     3. Con số min-content đó ~434px là do `.ne-bar` (hàng 8 nút Sửa/Nguồn/Lưu/xoá/Tải/...)
        không xuống dòng được. Luật cho nó xuống dòng vốn nằm trong @media(max-width:700px),
        mà media query đo BỀ RỘNG CỬA SỔ - ở đây trình sửa nằm trong một CỘT hẹp giữa một
        cửa sổ RỘNG nên luật đó không bao giờ chạy.

   Cách chữa: xếp dọc + min-width:0 ở cả hai tầng (mắt 1-2), và cho `.ne-bar` wrap ngay ở
   luật gốc chứ không chỉ trong media query (mắt 3). */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const cjs = fs.readFileSync(path.join(root, "dashboard", "console.js"), "utf8");
const css = fs.readFileSync(path.join(root, "dashboard", "style.css"), "utf8");
const html = fs.readFileSync(path.join(root, "dashboard", "index.html"), "utf8");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// Bóc đúng khối CSS của trang Trò chuyện để không bắt nhầm luật của trang Tệp tin.
const a = cjs.indexOf("function _injectChatCss()");
const b = cjs.indexOf("function _neoCuon", a);
const CSS = cjs.slice(a, b);
check("tìm thấy _injectChatCss", a !== -1 && b > a);

// ---- Mắt 1: khung mượn trình sửa phải xếp DỌC ----
const khung = (CSS.match(/\.chatpage-edit\{[^}]*\}/) || [""])[0];
check("tìm thấy luật .chatpage-edit", !!khung);
check("khung mượn trình sửa xếp DỌC (flex-direction:column)",
  /flex-direction:\s*column/.test(khung), khung);
check("CANARY: khung mượn không được bỏ trống flex-direction (mặc định row là sinh ra lỗi)",
  khung.indexOf("flex-direction") !== -1);
check("khung mượn co được (min-width:0)", /min-width:\s*0/.test(khung), khung);

// ---- Mắt 2: chính trình sửa phải co được xuống dưới min-content ----
const ed = (CSS.match(/\.chatpage-edit > \.note-editor:not\(\.ne-full\)\{[^}]*\}/) || [""])[0];
check("tìm thấy luật trình sửa trong khung chat", !!ed);
check("CANARY: trình sửa có min-width:0 - thiếu nó là item flex giữ nguyên min-content rồi đè lên cột hội thoại",
  /min-width:\s*0/.test(ed), ed);
check("trình sửa vẫn là khối thường trong khung (position:static), không phải lớp nổi",
  /position:\s*static/.test(ed));
check("nhưng lúc PHÓNG TO thì không dính luật này (:not(.ne-full) còn nguyên)",
  CSS.indexOf(".chatpage-edit > .note-editor:not(.ne-full)") !== -1);

// ---- Mắt 3: hàng nút của trình sửa phải tự xuống dòng khi thanh hẹp ----
const iBar = css.indexOf(".ne-bar {");
const bar = (css.slice(iBar).match(/^\.ne-bar \{[^}]*\}/m) || [""])[0];
check("tìm thấy luật gốc .ne-bar", iBar !== -1 && !!bar);
check("hàng nút tự xuống dòng được (flex-wrap:wrap) ngay ở luật GỐC",
  /flex-wrap:\s*wrap/.test(bar), bar);

// Đây là mắt xích hay bị chữa nhầm nhất: nhét wrap vào một media query trông có vẻ đủ,
// nhưng media query đo cửa sổ chứ không đo cái cột chứa trình sửa. Đo bằng cách đếm ngoặc
// còn treo trước luật: 0 = luật nằm ở TẦNG GỐC, >0 = đang bị bọc trong @media nào đó.
const bocTrong = (s, i) => {
  let n = 0;
  for (let k = 0; k < i; k++) { const c = s[k]; if (c === "{") n++; else if (c === "}") n--; }
  return n;
};
check("CANARY: luật wrap nằm ở TẦNG GỐC, không bị bọc trong @media - media query đo CỬA SỔ, không đo cột",
  iBar !== -1 && bocTrong(css, iBar) === 0, "boc trong " + bocTrong(css, iBar) + " ngoac");
// Và luật màn hẹp cũ thì NGƯỢC LẠI: nó phải còn nằm trong media query như trước.
const iHep = css.indexOf(".ne-title { order: -1; flex: 1 0 100%; }");
check("vẫn giữ luật màn hẹp cũ (tên file xuống dòng riêng trên điện thoại)",
  iHep !== -1 && bocTrong(css, iHep) === 1, iHep);
// Tên file phải cắt bằng ba chấm thay vì đẩy rộng thanh ra.
check("tên file cắt bằng ba chấm và co được về 0", /\.ne-title \{[^}]*text-overflow:\s*ellipsis/.test(css)
  && /\.ne-title \{[^}]*min-width:\s*0/.test(css));

// ---- Bố cục đã chốt ở 0.47.6 phải còn nguyên (fix này không được làm hỏng) ----
check("cột hội thoại vẫn đứng ô grid bên phải",
  CSS.indexOf(".chatpage-main.edit-on > .chatpage-slot > .transcript{ grid-row:2; grid-column:2") !== -1);
check("trình sửa vẫn ở cột trái với min-width:0 tầng grid",
  CSS.indexOf(".chatpage-main.edit-on > .chatpage-edit{ grid-row:2; grid-column:1; min-width:0; }") !== -1);
check("ô nhập vẫn trải dài toàn bề rộng dưới cùng",
  CSS.indexOf(".chatpage-main.edit-on > .chatpage-slot > .hud-voice{ grid-row:6; grid-column:1 / -1; }") !== -1);

// ---- cache-bust ----
const v = (f) => Number((html.match(new RegExp(f.replace(".", "\\.") + "\\?v=(\\d+)")) || [])[1] || 0);
check("console.js đã bump ?v= (>= 118)", v("console.js") >= 118, v("console.js"));
check("style.css đã bump ?v= (>= 70)", v("style.css") >= 70, v("style.css"));

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_trinh_sua_de_len_cot_hoi_thoai: tat ca pass");
