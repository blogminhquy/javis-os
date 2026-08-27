/* Bấm "Phóng to" trong trình sửa .md phải phủ KÍN màn hình, kể cả rail bên trái.

       node tests/js/test_phong_to_md_che_het_rail.js

   Lỗi thật chủ repo báo 27/08/2026 (ảnh chụp: tiêu đề "AGENTS.md — Vault Schema" hiện ra
   thành "ENTS.md — Vault Schema" vì rail phủ lên mép trái). Bẫy CSS kinh điển:

     .note-editor.ne-full { position: fixed; inset: 0; z-index: 1000 }   <- tưởng là đủ
     .cview               { position: fixed; ...    ; z-index: 40   }   <- nhưng cái này
                                                                          TẠO STACKING CONTEXT

   Trình sửa nằm TRONG .cview (trang Trò chuyện, trang Tệp tin), nên z-index 1000 của nó chỉ
   có giá trị bên trong .cview. So với rail (z-index 60, tầng gốc) thì cả cụm .cview vẫn nằm
   dưới -> hộp trình sửa trải đúng hết màn hình nhưng bị rail VẼ ĐÈ lên, ăn mất chữ bên trái.
   Chữa: trong lúc phóng to thì nâng chính stacking context .cview lên trên rail.

   Ràng buộc phải giữ (test dưới đo bằng số THẬT parse từ CSS, không ghim tay):
     rail  <  tầng phóng to  <  panel artifact / thông báo / modal
   Vế phải quan trọng không kém: từ 0.47.7 thẻ mermaid/svg/html bấm được ngay trong trình
   sửa, nên panel xem phải còn nổi được lên trên một trình sửa đang phóng to. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const STYLE = read("dashboard/style.css");
const CONSOLE_CSS = read("dashboard/console.css");
const CJS = read("dashboard/console.js");
const HTML = read("dashboard/index.html");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}
// Lấy z-index của một selector: đọc số trong thân luật đầu tiên khớp.
function zOf(css, sel) {
  const i = css.indexOf(sel);
  if (i === -1) return null;
  const than = css.slice(i, css.indexOf("}", i));
  const m = than.match(/z-index:\s*(\d+)/);
  return m ? Number(m[1]) : null;
}

// ---- 1. Luật chữa phải tồn tại ----
check("có luật nâng .cview khi đang phóng to", /body\.ne-full-on \.cview \{[^}]*z-index:\s*\d+/.test(STYLE));
check("trình sửa phóng to vẫn phủ toàn màn (position:fixed + inset:0)",
  /\.note-editor\.ne-full \{[^}]*position:\s*fixed[^}]*inset:\s*0/.test(STYLE));

// ---- 2. Thứ tự tầng: rail < phóng to < panel/thông báo/modal ----
const zRail = zOf(CONSOLE_CSS, ".rail {");
const zFull = zOf(STYLE, "body.ne-full-on .cview");
const zPanel = zOf(STYLE, ".jv-artpanel {");
const zCview = zOf(CONSOLE_CSS, ".cview {");
check("đọc được cả bốn con số", [zRail, zFull, zPanel, zCview].every((x) => typeof x === "number"),
  JSON.stringify({ zRail, zFull, zPanel, zCview }));
check("CANARY: .cview có z-index nên nó TẠO stacking context (gốc của lỗi)", zCview > 0, zCview);
check("phóng to đứng TRÊN rail (hết cảnh chữ bị lẹm)", zFull > zRail, zFull + " > " + zRail);
check("phóng to vẫn đứng DƯỚI panel artifact (bấm thẻ mermaid trong trình sửa còn xem được)",
  zFull < zPanel, zFull + " < " + zPanel);
check("nâng lên là có tác dụng thật (cao hơn mức thường của .cview)", zFull > zCview, zFull + " > " + zCview);

// ---- 3. Lớp body phải SUY RA từ DOM thật, và không sót đường nào ----
check("có hàm _neSyncFull", CJS.indexOf("function _neSyncFull()") !== -1);
check("suy ra từ trạng thái thật (không hidden + đang có lớp ne-full)",
  /_neSyncFull\(\)[\s\S]{0,320}!ed\.hidden && ed\.classList\.contains\("ne-full"\)/.test(CJS));
// Mọi dòng ĐỘNG VÀO ne-full đều phải đồng bộ lại lớp body ngay dòng đó hoặc dòng kế.
const dong = CJS.split("\n");
const thieu = [];
dong.forEach((d, i) => {
  if (!/classList\.(remove|toggle|add)\("ne-full"\)/.test(d)) return;
  const ke = (d + "\n" + (dong[i + 1] || "") + "\n" + (dong[i + 2] || ""));
  if (ke.indexOf("_neSyncFull") === -1) thieu.push(i + 1);
});
check("mọi chỗ đổi lớp ne-full đều gọi _neSyncFull ngay sau đó", thieu.length === 0, "dòng " + thieu.join(", "));
check("rời trang khi đang phóng to cũng dọn lớp (không để .cview treo trên rail)",
  /_neSlot = null;[\s\S]{0,240}_neSyncFull\(\);/.test(CJS));

// ---- 4. cache-bust ----
const v = (f) => Number((HTML.match(new RegExp(f.replace(".", "\\.") + "\\?v=(\\d+)")) || [])[1] || 0);
check("style.css đã bump ?v= (>= 69)", v("style.css") >= 69, v("style.css"));
check("console.js đã bump ?v= (>= 117)", v("console.js") >= 117, v("console.js"));

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_phong_to_md_che_het_rail: tat ca pass");
