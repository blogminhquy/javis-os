/* Trang Mức dùng KHÔNG được đứng chờ quét log mới vẽ.

       node tests/js/test_muc_dung_khong_cho_quet.js

   Chủ repo báo (2026-09-21): "trang mức dùng mỗi lần vào cũng rất lag", ảnh chụp là trang đứng
   ở chữ "Đang dựng chỉ số token...".

   Đo được trên máy chủ dự án: `~/.claude/projects` có 651 file và 602 MB, quét đầy đủ mất 27
   GIÂY. Mà `render()` gọi `load(true)`, tức `/usage/summary?refresh=1`, tức CHỜ quét xong mới
   vẽ dòng nào - trong khi số liệu cũ đã nằm sẵn trong chỉ số, chẳng việc gì phải giấu đi.

   Hợp đồng sau khi sửa, và đây là thứ file này khoá lại:
     - render() vẽ ngay bằng chỉ số đang có: `load(false)`, KHÔNG phải `load(true)`.
     - rồi mới đi quét ở nền qua `/usage/refresh`.
     - quét xong mà KHÔNG động tới gì thì đừng vẽ lại (tránh nháy trang vô cớ).
     - người dùng rời trang giữa chừng thì đừng vẽ đè lên trang họ đang xem.

   CI chỉ có node nên file này khoá phần hợp đồng đọc được từ mã nguồn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "usage.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// Thân hàm render() - mọi phép thử dưới đây soi đúng trong đó, không lẫn sang chỗ khác.
const render = (SRC.split("function render(el) {")[1] || "").split("\n  }")[0];
check("tìm thấy hàm render()", render.length > 0);

// ============================================================
// 1. Vẽ ngay, không chờ quét
// ============================================================
check("CANARY: render() vẽ bằng chỉ số đang có (load(false))", /\bload\(false\)/.test(render));
check("CANARY: render() KHÔNG còn chờ quét xong mới vẽ (load(true))", !/\bload\(true\)/.test(render));
check("CANARY: và có đi quét ở nền", /quetNen\(/.test(render));

// ============================================================
// 2. Quét nền phải lành
// ============================================================
const quet = (SRC.split("function quetNen(el) {")[1] || "").split("\n  }")[0];
check("có hàm quét nền riêng", quet.length > 0);
check("CANARY: quét nền đi đường /usage/refresh", /fetch\("\/usage\/refresh"/.test(quet));
check("CANARY: rời trang giữa chừng thì không vẽ đè", /el\.isConnected/.test(quet) && /state\.el !== el/.test(quet));
check("CANARY: không động tới gì thì không vẽ lại", /_co_thay_doi\(/.test(quet));
check("cờ báo có thay đổi nhìn đủ cả ba nguồn + lượt quét lại",
  /claude_files/.test(SRC) && /codex_files/.test(SRC) && /api_events/.test(SRC) && /quet_lai/.test(SRC));

// ============================================================
// 3. Đường gọi số liệu vẫn phải nói rõ refresh=0
// ============================================================
// load() ghép `&refresh=` từ tham số, nên nếu ai đó lỡ bỏ tham số đi thì server lấy mặc định
// refresh=1 và trang lại đứng chờ y như cũ - lỗi quay lại mà không ai thấy.
check("CANARY: load() vẫn gửi refresh tường minh lên server", /&refresh=" \+ \(doRefresh \? 1 : 0\)/.test(SRC));

console.log("");
if (fails.length) { console.log("THẤT BẠI " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("OK - test_muc_dung_khong_cho_quet: tất cả pass");
