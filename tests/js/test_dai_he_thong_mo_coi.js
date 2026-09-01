/* Dải "Hệ thống" trong rail không được đứng lại một mình sau khi rỗng ruột.

       node tests/js/test_dai_he_thong_mo_coi.js

   Chủ repo báo 01/09 kèm ảnh: "thi thoảng chữ hệ thống to lại hiện ra trong khi chỗ đó đáng
   nhẽ là không có gì" - một nhãn "Hệ thống" cỡ lớn nằm giữa ô chọn ngôn ngữ và hàng version,
   bên dưới trống trơn.

   Nguyên nhân: trên màn hẹp `mobile-chat.js` dựng một khung `.rail-sys` (nhãn + chỗ chứa) rồi
   mượn ba thứ từ HUD bỏ vào (chọn brain, đổi tông, dải VỪA GỌI). Khi quay về desktop nó TRẢ
   ba thứ đó về chỗ cũ - nhưng KHÔNG dọn cái khung. `ensureSysHost` lại giữ tham chiếu và
   thoát sớm nếu đã dựng, nên cái nhãn ở lại vĩnh viễn, đứng trên một khoảng trống.

   Đây là loại lỗi chỉ lộ ra khi ĐỔI BỀ NGANG, nên đọc code một lượt rất dễ bỏ qua: nhánh
   mobile hoàn toàn đúng, chỉ nhánh quay về là thiếu một dòng. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "dashboard", "mobile-chat.js"), "utf8");

const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};

const place = (JS.match(/function placeSystem\(\)[\s\S]*?\n    \}/) || [""])[0];
check("tìm được placeSystem", place.length > 100);

// ---- 1. Có hàm dọn, và nó dọn CẢ tham chiếu ----
const bo = (JS.match(/function boSysHost\(\)[\s\S]*?\n    \}/) || [""])[0];
check("có hàm gỡ khung khỏi rail", bo.length > 20, bo);
check("gỡ khỏi DOM", /removeChild\(sysHost\)/.test(bo), bo);
// Chỉ removeChild mà giữ biến là lần sau ensureSysHost thoát sớm, khung không bao giờ dựng lại
// -> quay về màn hẹp thì mất luôn nhóm Hệ thống. Phải xoá cả tham chiếu.
check("và xoá cả tham chiếu để lần sau dựng lại được",
  /sysHost = null/.test(bo) && /sysBtns = null/.test(bo), bo);

// ---- 2. Quay về desktop thì dọn ----
check("trả nút về desktop xong là dọn khung",
  /moved = \[\];\s*\n\s*boSysHost\(\)/.test(place), place);
// Nhánh desktop mà `moved` rỗng (khung dựng hụt, hoặc nút bị vẽ lại mất) trước đây không làm
// gì cả - đúng ca để lại nhãn mồ côi.
check("desktop mà moved rỗng vẫn dọn (ca để lại nhãn mồ côi)",
  /\} else \{\s*\n\s*boSysHost\(\)/.test(place), place);

// ---- 3. Màn hẹp: nhãn không được đứng một mình ----
check("màn hẹp mà khung không còn nút nào thì cũng dọn",
  /sysHost && !sysHost\.querySelector\(/.test(place), place);
check("soi đúng ba thứ được mượn vào khung",
  /querySelector\("\.navbar-brain, #themeToggle, #sysBar"\)/.test(place), place);
check("dọn xong thì reset moved để lần sau mượn lại được",
  /!sysHost\.querySelector\([\s\S]{0,80}moved = \[\];/.test(place), place);

// ---- 4. Nhánh mobile vốn đúng thì giữ nguyên ----
check("màn hẹp vẫn mượn đủ ba thứ",
  /moveEl\(document\.querySelector\("\.navbar-brain"\)/.test(place)
  && /moveEl\(document\.getElementById\("themeToggle"\)/.test(place)
  && /moveEl\(document\.getElementById\("sysBar"\)/.test(place), place);
check("và chỉ mượn khi chưa mượn (không mượn chồng)", /if \(!moved\.length\)/.test(place), place);

console.log();
if (fails.length) {
  console.log("FAIL " + fails.length + ": " + fails.join("; "));
  process.exit(1);
}
console.log("Tất cả xanh.");
