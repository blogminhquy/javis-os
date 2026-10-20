/* Nút "Ghi chú hôm nay" trong thanh công cụ Vault.

       node tests/js/test_nut_nhat_ky_hom_nay.js

   Nút này tự tìm sổ Daily Log rồi mở note của ngày hôm nay, chưa có thì tạo theo mẫu. Ba chỗ
   hỏng ÂM THẦM nên phải canh:

     1. Tên thư mục. Vault ngoài đời có cả "01 - Daily Log", "Daily Log" lẫn "Daily" (server
        nhận diện linh hoạt y hệt trong STANDARD_STRUCTURE). Gõ cứng một tên là đẻ ra thư mục
        thứ hai đứng ngay cạnh cái đang dùng, và note mỗi ngày rơi vào hai chỗ khác nhau.
     2. Ngày. Lấy ngày bằng toISOString() là lấy theo UTC, tức buổi tối ở Việt Nam (UTC+7)
        note nhảy sang ngày MAI. Phải lấy theo giờ máy.
     3. Ghi đè. Bấm nút lần thứ hai trong cùng ngày mà ghi lại mẫu là xoá sạch những gì đã
        viết từ sáng. */
const fs = require("fs");
const path = require("path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CON = D("console.js");
const HTML = D("index.html");
const VI = JSON.parse(D("i18n/vi.json"));
const EN = JSON.parse(D("i18n/en.json"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Hàm thuần - chạy THẬT mã trong console.js
// ============================================================
const dau = CON.indexOf("const _VT_DAILY_RE");
const cuoi = CON.indexOf("  // Mở ghi chú của HÔM NAY", dau);
check("moi được mấy hàm nhật ký ra khỏi console.js", dau > 0 && cuoi > dau);

const ctx = { window: { t: (k) => "<" + k + ">" }, LOC: () => "vi-VN" };
const src = CON.slice(dau, cuoi) + "; ({ _VT_DAILY_RE, _vtNgayHomNay, _vtThuMucNhatKy, _vtMauNhatKy })";
const H = vm.runInNewContext(src, ctx);

// --- 1a. Dò thư mục ---
const dir = (n) => ({ name: n, type: "dir" });
check("nhận thư mục có số thứ tự", H._vtThuMucNhatKy([dir("01 - Daily Log")]) === "01 - Daily Log");
check("nhận thư mục không số", H._vtThuMucNhatKy([dir("Daily Log")]) === "Daily Log");
check("nhận thư mục rút gọn", H._vtThuMucNhatKy([dir("daily")]) === "daily");
check("CANARY: vault chưa có sổ -> dùng tên chuẩn để /files/write tự tạo",
  H._vtThuMucNhatKy([dir("wiki"), dir("sources")]) === "01 - Daily Log");
check("FILE tên trùng không bị nhận là sổ",
  H._vtThuMucNhatKy([{ name: "Daily Log", type: "file" }]) === "01 - Daily Log");
check("tên gần giống không bị nhận nhầm",
  H._vtThuMucNhatKy([dir("Daily Logs"), dir("My Daily Log")]) === "01 - Daily Log");
check("danh sách rỗng hay thiếu không làm nổ", H._vtThuMucNhatKy(null) === "01 - Daily Log");

// --- 1b. Ngày theo GIỜ MÁY, không theo UTC ---
// 23:30 ngày 11 ở UTC+7 là 16:30 cùng ngày ở UTC, nhưng 00:30 ngày 12 thì UTC vẫn còn 11.
// Mốc dưới đây được dựng bằng giờ ĐỊA PHƯƠNG nên test đúng ở mọi múi giờ của máy chạy CI.
check("ngày lấy theo giờ máy, có đệm 0", H._vtNgayHomNay(new Date(2026, 8, 5, 23, 30)) === "2026-09-05");
check("CANARY: gần nửa đêm không nhảy sang ngày mai",
  H._vtNgayHomNay(new Date(2026, 0, 1, 0, 30)) === "2026-01-01");
check("không tham số thì lấy hôm nay", /^\d{4}-\d{2}-\d{2}$/.test(H._vtNgayHomNay()));

// --- 1c. Mẫu note ---
const mau = H._vtMauNhatKy("2026-09-11");
check("mẫu có frontmatter type: daily", /^---\ntype: daily\ndate: 2026-09-11\n/.test(mau));
check("mẫu có tiêu đề là ngày", mau.includes("# 2026-09-11"));
check("mẫu có thứ trong tuần theo locale giao diện", /# 2026-09-11 - \S/.test(mau));
check("mẫu có dòng task bấm được (dataview kéo được)", mau.includes("- [ ] "));
check("chữ trong mẫu đi qua từ điển, không gõ cứng",
  mau.includes("<cs.vt_daily_tasks>") && mau.includes("<cs.vt_daily_notes>"));

// ============================================================
// 2. Nút và phần đấu dây
// ============================================================
check("có nút trong thanh công cụ Vault", HTML.includes('id="vtDaily"'));
check("nút đứng cạnh mấy nút tạo file/thư mục",
  HTML.indexOf('id="vtNewFile"') < HTML.indexOf('id="vtDaily"')
  && HTML.indexOf('id="vtDaily"') < HTML.indexOf('id="vtRefresh"'));
check("nút có tooltip dịch được", HTML.includes('data-i18n-title="vault.daily"'));
check("nút được đấu dây trong _vtWire", /getElementById\("vtDaily"\)/.test(CON));
check("bấm nút gọi đúng hàm", /dn\.onclick = \(\) => _vtMoNhatKyHomNay\(\)/.test(CON));

// Đã có note thì chỉ MỞ: /files/read phải chạy trước, và /files/write nằm trong nhánh chưa có.
const thanHam = CON.slice(CON.indexOf("async function _vtMoNhatKyHomNay"),
                          CON.indexOf("function _vtWire()"));
check("kiểm tồn tại bằng /files/read trước khi ghi",
  thanHam.indexOf("/files/read") > 0 && thanHam.indexOf("/files/read") < thanHam.indexOf("/files/write"));
check("CANARY: đã có note thì KHÔNG ghi đè", /if \(!daCo\) \{/.test(thanHam));
check("cuối cùng luôn mở note ra sửa", /openNote\(rel,/.test(thanHam));
check("ghi lỗi thì báo chứ không im lặng mở file rỗng",
  thanHam.includes("cs.vt_daily_fail") && /return;/.test(thanHam));

check("nhật ký mở trong khung đang đứng, không phủ kín màn hình", /openNote\(rel, \{[^}]*\}, \{ giuKhung: true \}\)/.test(thanHam));
check("openNote chỉ phóng to khi KHÔNG xin giữ khung",
  /ed\.classList\.toggle\("ne-full", !\(opts && opts\.giuKhung\)\)/.test(CON));
check("CANARY: chỉ 404 mới tạo mới, lỗi khác không ghi đè", /daCo = r\.status !== 404/.test(thanHam));

// ============================================================
// 2b. Phím tắt Ctrl/Cmd+D - chạy THẬT bộ bắt phím
// ============================================================
const dauPhim = CON.indexOf("function _vtPhimNhatKy");
const cuoiPhim = CON.indexOf('document.addEventListener("keydown", _vtPhimNhatKy)', dauPhim);
check("có bộ bắt phím nhật ký gắn ở mức document", dauPhim > 0 && cuoiPhim > dauPhim);
let goi = 0;
const P = vm.runInNewContext(CON.slice(dauPhim, cuoiPhim) + "; _vtPhimNhatKy",
  { _vtMoNhatKyHomNay: () => { goi++; } });
const phim = (o) => { let chan = false; P(Object.assign({ key: "d", code: "KeyD", preventDefault: () => { chan = true; } }, o)); return chan; };
goi = 0; check("Ctrl+D mở nhật ký và chặn bookmark", phim({ ctrlKey: true }) && goi === 1);
goi = 0; check("Cmd+D (Mac) mở nhật ký", phim({ metaKey: true }) && goi === 1);
goi = 0; check("bàn phím gõ tiếng Việt vẫn nhận theo code", phim({ ctrlKey: true, key: "đ" }) && goi === 1);
goi = 0; check("giữ phím không mở liên tục", phim({ ctrlKey: true, repeat: true }) && goi === 0);
goi = 0; check("Ctrl+Shift+D không bị chiếm", !phim({ ctrlKey: true, shiftKey: true }) && goi === 0);
goi = 0; check("chữ d trơn khi gõ không bị chiếm", !phim({}) && goi === 0);
check("tooltip có ghi phím tắt", /Ctrl\+D/.test(VI["vault.daily"]) && /Cmd\+D/.test(EN["vault.daily"]));

// ============================================================
// 3. Từ điển
// ============================================================
for (const k of ["vault.daily", "cs.vt_daily_tasks", "cs.vt_daily_notes", "cs.vt_daily_fail"]) {
  check(`khoá ${k} có ở cả vi và en`, k in VI && k in EN);
}

console.log("");
if (fails.length) { console.log("ĐỎ " + fails.length + " mục"); process.exit(1); }
console.log("Tất cả xanh.");
