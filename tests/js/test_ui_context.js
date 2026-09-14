/* Khối [NGỮ CẢNH GIAO DIỆN: ...] (dashboard/ui-context.js) và việc lột nó khỏi bong bóng.

       node tests/js/test_ui_context.js

   Voice V1 spec mục 5. Khối rỗng khi không có gì; trang chat/home không tính; đoạn chọn cắt
   600 ký tự; ngoặc vuông trong dữ liệu không được phá ranh giới khối; app.js lột khối này
   cùng cách với FILE ĐANG MỞ (nếu quên, mỗi bong bóng người dùng sẽ mở đầu bằng chữ máy). */
const fs = require("fs");
const path = require("path");
const U = require("../../dashboard/ui-context.js");
const app = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "app.js"), "utf8");
const sessions = fs.readFileSync(path.join(__dirname, "..", "..", "server", "sessions.py"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

check("không có gì -> rỗng", U.build({}) === "");
check("trang chat -> rỗng", U.build({ page: "chat" }) === "");
check("trang home -> rỗng", U.build({ page: "home" }) === "");
check("trang kanban -> có trang=", U.build({ page: "kanban" }) === "[NGỮ CẢNH GIAO DIỆN: trang=kanban]");
let s = U.build({ page: "files", selection: "Doanh thu tháng 9 tăng 12%" });
check("có chọn=", s.indexOf('chọn="Doanh thu tháng 9 tăng 12%"') > 0);
s = U.build({ selection: "x".repeat(700) });
check("chọn cắt 600", s.length < 640 && s.indexOf("…") > 0);
s = U.build({ selection: "a [b] c\nd" });
check("ngoặc vuông và xuống dòng bị thay", s.indexOf("[b]") < 0 && s.indexOf("\n") < 0 && /^\[NGỮ CẢNH GIAO DIỆN: .*\]$/.test(s));
s = U.build({ interruptedAt: "Doanh thu tháng này" });
check("ngắt_lời=", s === '[NGỮ CẢNH GIAO DIỆN: ngắt_lời="Doanh thu tháng này"]');
s = U.build({ page: "kanban", selection: "abc", interruptedAt: "xyz" });
check("ba phần nối bằng dấu chấm phẩy", s === '[NGỮ CẢNH GIAO DIỆN: trang=kanban; chọn="abc"; ngắt_lời="xyz"]');

check("V3: voice -> kênh=giọng", U.build({ voice: true }) === "[NGỮ CẢNH GIAO DIỆN: kênh=giọng]");
check("V3: voice false -> không có gì", U.build({ voice: false }) === "");
check("V3: kênh=giọng đứng cuối, sau ngắt_lời", U.build({ page: "kanban", voice: true }) === "[NGỮ CẢNH GIAO DIỆN: trang=kanban; kênh=giọng]");

check("app.js lột khối này khỏi bong bóng (_KHOI_NGU_CANH)", /_KHOI_NGU_CANH = \[[^\]]*"\[NGỮ CẢNH GIAO DIỆN:"/.test(app));
check("app.js chèn khối trước khi gửi qua JavisUiContext.build", /JavisUiContext\.build\(/.test(app));
check("sessions.py lột khối khỏi tiêu đề", /_KHOI_NGU_CANH_UI/.test(sessions));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - ui-context");
