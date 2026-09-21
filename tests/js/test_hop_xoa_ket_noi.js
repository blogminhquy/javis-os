/* Hộp thoại XOÁ KẾT NỐI dùng đúng vỏ .pkm đã thiết kế sẵn, thay vì lưới hai cột của bộ chọn
 * model.
 *
 *       node tests/js/test_hop_xoa_ket_noi.js
 *
 * Chủ repo báo 21/09: "ui xoá kết nối quá xấu, margin padding không phù hợp, trong khi đợt
 * trước có bản thêm sửa và xoá kết nối đã được thiết kế nhưng không được áp dụng".
 *
 * Đúng vậy: `.pkm` (console.css) là vỏ hộp thoại MỘT CỘT dựng cho luồng cài/gỡ gói ở trang
 * Kho - có sẵn cả `.pkm-mat` là danh sách "sẽ mất những gì" khi gỡ. Màn xoá kết nối lại vẫn
 * dùng `.mp-body`, vốn là `display:grid; grid-template-columns:260px 1fr` của bộ chọn model.
 * Nhồi một màn hình đọc-từ-trên-xuống vào cái lưới ấy chính là thứ làm nó trông vụn: danh
 * sách dạt sang cột phải, ô tích rơi khỏi mạch đọc, mọi khoảng cách là của bố cục khác.
 *
 * Test này canh: (1) đã chuyển sang vỏ .pkm, (2) không quay lại .mp-body, (3) những thứ vỏ đó
 * cần mà nó chưa có thì phải được thêm, (4) bấm ra ngoài đóng được. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
const check = (ten, ok, them) => {
  console.log((ok ? "ok   " : "FAIL ") + ten + (ok || them === undefined ? "" : "  [" + them + "]"));
  if (!ok) fails.push(ten);
};
// Thân hàm openPurgeModal: mọi phép soi dưới đây chỉ nhìn trong đó, không quét cả file.
const HAM = (JS.match(/async function openPurgeModal\([\s\S]*?\n  \}\n/) || [""])[0];
// Bản ĐÃ BÓC CHÚ THÍCH, dành cho mấy phép canary: chú thích ở đây có nhắc tên lớp cũ để giải
// thích vì sao bỏ nó, và soi cả chú thích thì canary đỏ vì đúng cái câu giải thích ấy.
const CHAY = HAM.split("\n").filter((d) => !d.trim().startsWith("//")).join("\n");

// ============================================================
// 1. Dùng vỏ .pkm
// ============================================================
check("bóc được hàm openPurgeModal", HAM.length > 500, HAM.length);
check("connModal nhận biến thể pkm", /function connModal\(html, maxw, pkm\)/.test(JS));
check("và gắn đúng lớp cho cả lớp phủ lẫn hộp",
      /"mp-overlay open" \+ \(pkm \? " pkm-lop" : ""\)/.test(JS)
      && /'<div class="mp-box' \+ \(pkm \? " pkm" : ""\)/.test(JS));
check("hộp xoá kết nối mở ở chế độ pkm", /, 560, true\)|, 0, true\)/.test(HAM), HAM.slice(0, 400));
check("đầu hộp theo khuôn pkm (icon + tên + dòng phụ)", /class="pkm-dau"/.test(JS)
      && /class="pkm-ico"/.test(JS) && /class="pkm-phu"/.test(JS));
check("thân hộp một cột", /class="pkm-than"/.test(HAM));
check('danh sách "sẽ mất" dùng đúng .pkm-mat đã có sẵn', /class="pkm-mat"/.test(HAM));
check("và nằm trong khối cảnh báo đỏ", /class="pkm-canh do"/.test(HAM));
check("lúc đang hỏi máy chủ thì hiện vòng quay của vỏ đó", /class="pkm-quay"/.test(HAM));

// CANARY: hai dấu vết của bố cục cũ. Quay lại một trong hai là hộp vụn y như trước.
check("CANARY: không còn dùng .mp-body (lưới hai cột của bộ chọn model)",
      !/mp-body/.test(CHAY), CHAY.match(/.{0,60}mp-body.{0,40}/) || "");
check("CANARY: không còn kê khoảng cách bằng style nội tuyến",
      !/style="margin/.test(CHAY), (CHAY.match(/style="margin[^"]*"/g) || []).join(" | "));

// ============================================================
// 2. Chân hộp dính đáy, không cuộn đi mất
// ============================================================
check("chân hộp gắn thẳng vào .mp-box chứ không nằm trong thân",
      /function pgChan\(hop, html\)[\s\S]{0,400}hop\.appendChild\(el\)/.test(JS));
check("gọi lại nhiều lần cũng chỉ còn một chân",
      /function pgChan\([\s\S]{0,300}querySelector\("\.pkm-chan"\)[\s\S]{0,60}remove\(\)/.test(JS));
// Hai lối cụt (đọc hỏng, kết nối đang bận) trước đây in mỗi một dòng chữ vào thân rồi dừng:
// không nút, không lối ra ngoài phím Esc.
check("lối cụt vẫn có nút đóng", /function cut\(mau, chu\)[\s\S]{0,400}pgChan\(hop,/.test(HAM));
check("và cả hai lối cụt đều đi qua nó",
      /cut\("do",/.test(HAM) && /cut\("vang",/.test(HAM));

// ============================================================
// 3. Ô tích 13px thành hàng gạt bấm được cả dải
// ============================================================
check("ô tích nhật ký thành hàng gạt .pkm-gat", /class="pkm-gat"/.test(HAM));
check("CANARY: không còn <input type=checkbox> trần", !/type="checkbox"/.test(CHAY));
check("đọc trạng thái từ aria-pressed khi gửi đi",
      /purge_audit: !!\(gat && gat\.getAttribute\("aria-pressed"\) === "true"\)/.test(HAM));
check("câu phụ nói rõ mặc định là GIỮ nhật ký",
      /mặc định giữ lại/.test(VI["cs.cn_pg_audit_note"] || ""), VI["cs.cn_pg_audit_note"]);

// ============================================================
// 4. Bấm ra ngoài đóng, và không để sót tay bắt cho hộp sau
// ============================================================
check("bấm trúng lớp phủ thì đóng",
      /m\.onclick = pkm \? \(e\) => \{ if \(e\.target === m\) closeConnModal\(\); \} : null;/.test(JS));
// Và CHỈ ở hộp pkm: mấy hộp thường của khối kết nối là nơi dán khoá API, bấm trượt ra nền mà
// mất sạch chữ đang gõ thì tệ hơn việc phải với tay lên nút X.
check("hộp thường KHÔNG đóng khi bấm ra ngoài (đang dán khoá API thì mất chữ)",
      /m\.onclick = pkm \?/.test(JS) && /: null;/.test(JS));
check("đóng hộp thì gỡ luôn tay bắt đó",
      /function closeConnModal\(\)[\s\S]{0,500}m\.onclick = null;/.test(JS));
// Hộp pkm tự khai bề ngang trong CSS (kèm biến thể tờ trượt trên điện thoại). Nhét max-width
// nội tuyến là style nội tuyến thắng cả media query, và hộp kẹt ở bề ngang máy tính.
check("chế độ pkm KHÔNG nhét max-width nội tuyến",
      /\(pkm \? '"' : '" style="max-width:/.test(JS));

// ============================================================
// 5. Thứ vỏ .pkm chưa có thì phải thêm
// ============================================================
check("có kiểu cho ô icon đầu hộp", /\.pkm-ico \{/.test(CSS));
check("và cho chữ mờ dùng chung", /\.pkm-nhe \{/.test(CSS));
check("dòng phụ gộp tên kết nối + tên dịch vụ, không nói lại lần hai trong thân",
      /function pgPhu\(ten, dichVu\)/.test(JS) && !/pkm-mota/.test(HAM));
["cs.cn_pg_warn_head"].forEach((k) => {
  check("khoá " + k + " có ở cả vi và en", !!VI[k] && !!EN[k]);
});
// Khoá cũ của dòng bị bỏ phải dọn theo, không thì từ điển tích chữ chết.
check("khoá của dòng đã bỏ cũng được dọn khỏi từ điển",
      !("cs.cn_pg_about" in VI) && !("cs.cn_pg_about" in EN));

if (fails.length) {
  console.log(`\nFAIL ${fails.length} muc: ` + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_hop_xoa_ket_noi: tat ca pass");
