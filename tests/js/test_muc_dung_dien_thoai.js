/* Trang Mức dùng trên điện thoại (0.421.0): không tràn khung, chọn kỳ bằng một ô thả xuống, mở nhanh.

       node tests/js/test_muc_dung_dien_thoai.js

   Chủ repo gửi ảnh 30/10/2026: trên iPhone trang Mức dùng lệch hẳn sang trái, mép trái mất chữ, mép phải
   hở một khoảng. Đo lại: nhãn số ngày cuối dưới biểu đồ ("30") canh giữa một cột hẹp hơn chữ nên thò ra
   ngoài mép trang vài px, thế là khung cuộn của trang trượt ngang được. Kỳ dài còn tệ hơn: 3 tháng hay
   Năm nay là 90-365 cột, mỗi cột tối thiểu 3px cộng khe 3px, rộng gấp mấy màn hình.

   Cùng lần đó chủ repo muốn tám nút chọn kỳ thành một ô thả xuống "cho gọn", và trang dựng nhanh hơn:
   bảy lượt hỏi cộng lượt quét log chạy song song giành nhau một nhân Python, mỗi lượt 0,05 s thành
   0,7-1,7 s.

   CI chỉ có node nên file này khoá phần hợp đồng đọc được từ mã nguồn; phần đo thật (bề ngang trang trên
   iPhone giả lập ở cả tám kỳ) làm bằng Playwright lúc sửa. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "usage.js"), "utf8");
const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };
const fn = (ten) => (SRC.split("function " + ten + "(")[1] || "").split("\n  }\n")[0];

// ── 1. Không tràn khung ──
check("CANARY: khối trang chặn mọi thứ thò ra ngoài bề ngang (clip, hidden cho máy cũ)",
  /\.tk-wrap\{[^}]*overflow-x:hidden;overflow-x:clip/.test(SRC));
check("nhãn đầu và cuối dưới biểu đồ canh vào trong, không canh giữa cột hẹp",
  /\.tk-x:first-child\{text-align:left\}/.test(SRC) && /\.tk-x:last-child\{text-align:right;direction:rtl\}/.test(SRC));
check("CANARY: kỳ dài cho cột co về 0 và khe hẹp lại",
  /\.tk-dai \.tk-col,\.tk-dai \.tk-x,\.tk-dai \.tk-m\{min-width:0\}/.test(SRC)
  && /ts\.length > 45 \? ' tk-dai" style="gap:' \+ \(ts\.length > 120 \? 0 : 1\)/.test(SRC));
check("ba hàng của biểu đồ (cột, nhãn, mốc) cùng mang lớp kỳ dài, kẻo lệch cột",
  /<div class="tk-chart' \+ dai/.test(SRC) && /'<\/div><div class="tk-xrow' \+ dai/.test(SRC) && /<\/div><div class="tk-mrow' \+ dai/.test(SRC));
check("kỳ dài ghi tên tháng thay cho số ngày", /ts\.length > 62 \? nhanThang\(/.test(SRC) && /month: "short"/.test(SRC));

// ── 2. Chọn kỳ bằng một ô thả xuống ──
const paint = fn("paint");
check("CANARY: chọn kỳ là một <select>, không còn hàng nút tk-chip", /<select class="tk-sel" data-period-sel/.test(paint) && !/tk-chip/.test(SRC));
check("ô có đủ tám kỳ, kỳ đang xem được chọn sẵn", /PERIODS\(\)\.map/.test(paint) && /p\[0\] === state\.period \? " selected"/.test(paint));
check("đổi ô là nạp lại kỳ mới", /sel\.onchange = function \(\) \{ state\.period = sel\.value; load\(false\); \}/.test(fn("bind")));
check("ô thả xuống có nhãn cho trình đọc màn hình", /aria-label="' \+ esc\(window\.t\("usage\.ky\.chon"\)\)/.test(paint));
check("điện thoại: chữ ô 16px (dưới mức đó iOS tự phóng to trang)", /@media\(max-width:640px\)\{\.tk-sel\{font-size:16px/.test(SRC));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/en.json"), "utf8"));
check("khoá usage.ky.chon có ở vi và en", !!(vi["usage.ky.chon"] && en["usage.ky.chon"]));

// ── 3. Mở nhanh ──
const render = fn("render");
check("CANARY: quét log nền chạy SAU lượt nạp đầu, không giành nhân với nó", /load\(false\)\.then\(function \(\) \{ quetNen\(el\); \}\)/.test(render));
const load = fn("load");
check("load() trả Promise để render nối quét nền sau nó", /return Promise\.all\(\[/.test(load));
check("CANARY: đã có số của kỳ đó thì vẽ ngay, số mới về thì vẽ lại",
  /var khoa = state\.period \+ "\|" \+ state\.provider, cu = state\.dangHien !== khoa && state\.nho\[khoa\]/.test(load)
  && /if \(cu\) \{ state\.tq = cu\.tq; paint\(cu\.s, cu\.ins\); state\.dangHien = khoa; \}/.test(load));
check("kết quả mới được nhớ theo kỳ", /state\.nho\[khoa\] = \{ s: res\[0\]/.test(load));
check("CANARY: số về muộn của kỳ cũ không vẽ đè kỳ người dùng vừa chọn",
  /if \(khoa !== state\.period \+ "\|" \+ state\.provider\) return;/.test(load)
  && load.indexOf("if (khoa !== state.period") < load.indexOf("state.tq = res[2]"));
check("đang hiện số cũ mà lượt mới lỗi thì giữ số cũ, không thay bằng trang lỗi", /if \(!cu\) loi\(/.test(load));
check("mở trang và trang lỗi đều quên kỳ đang hiện, để lần sau vẽ lại từ nhớ",
  /state\.dangHien = null;/.test(render) && /state\.dangHien = null;/.test(fn("loi")));

console.log("");
if (fails.length) { console.log("THẤT BẠI " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("OK - test_muc_dung_dien_thoai: tất cả pass");
