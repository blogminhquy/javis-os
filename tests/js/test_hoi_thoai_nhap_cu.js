/* Nút "Nhập tin cũ" trên thẻ tài khoản Zalo cá nhân ở Hộp thư (0.174.0): canh bằng cấu trúc mã.

       node tests/js/test_hoi_thoai_nhap_cu.js

   Chủ repo hỏi 16/10/2026: đăng nhập Zalo lần đầu thì có đồng bộ tin cũ được không, làm thành tuỳ chọn riêng. Nút chỉ hiện khi kênh
   có năng lực `nhap_lich_su` (server suy ra từ hàm của module), luôn hỏi lại trước khi chạy, và nói rõ kết quả. Không dùng em dash.
*/
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const CV = src("dashboard/conversations.js");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

check("nút chỉ hiện khi kênh có năng lực nhập tin cũ và là tài khoản (không phải bot)",
  /nl\.nhap_lich_su && a\.kind === "account"/.test(CV) && /ht-acc-nhap-cu/.test(CV));
const CB = src("dashboard/chatbots.js");
check("kênh đã có bot: chip Zalo trên thẻ bot là nút nhập tin cũ (thẻ kênh không hiện ở mục Kênh chưa có bot)",
  /\(k\.nang_luc \|\| \{\}\)\.nhap_lich_su/.test(CB) && /cb-kenh-nhap-cu/.test(CB) &&
  /JavisConversations\.nhapTinCu/.test(CB) && /nhapTinCu: nhapTinCu/.test(CV));
check("bấm là hỏi lại trước khi chạy", /confirm\(window\.t\("ht\.xn_nhap_cu"/.test(CV));
check("gọi đúng endpoint import-history kèm kênh", /\/import-history"/.test(CV) && /fd\(\{ channel: a\.channel \}\)/.test(CV));
check("khoá nút trong lúc chạy, trả lại khi xong", /nut\.disabled = true/.test(CV) && /nut\.disabled = false/.test(CV));
check("báo kết quả: số tin, cuộc chat bỏ qua, chạm trần",
  /ht\.da_nhap_cu/.test(CV) && /ht\.nhap_cu_bo_qua/.test(CV) && /ht\.nhap_cu_het_tran/.test(CV));
for (const k of ["ht.nhap_cu", "ht.xn_nhap_cu", "ht.dang_nhap_cu", "ht.da_nhap_cu", "ht.khong_co_tin_cu",
                 "ht.nhap_cu_bo_qua", "ht.nhap_cu_het_tran", "ht.loi_nhap_cu", "cb.nhap_cu_title"]) {
  check("khoá " + k + " có cả vi và en", typeof VI[k] === "string" && typeof EN[k] === "string");
}
check("câu hỏi lại nói rõ bot không trả lời và không tính chưa đọc",
  /Bot không trả lời/.test(VI["ht.xn_nhap_cu"]) && /không tính là chưa đọc/.test(VI["ht.xn_nhap_cu"]));
check("không em dash trong chữ mới", ![VI["ht.xn_nhap_cu"], EN["ht.xn_nhap_cu"]].some((s) => s.includes("—")));

console.log();
if (fails.length) { console.log("ĐỎ " + fails.length + " mục"); process.exit(1); }
console.log("Tất cả xanh.");
