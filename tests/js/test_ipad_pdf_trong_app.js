/* iPhone/iPad: bấm link PDF trong chat thì xem NGAY TRONG APP, có nút Đóng và Tải về.

       node tests/js/test_ipad_pdf_trong_app.js

   Video chủ repo 05/11/2026 (iPad, app cài ra màn hình chính): bấm link "Tải slide PDF" trong
   chat thì PDF đè lên cả Javis, không nút quay lại, không nút tải, phải tắt app. Link đó là
   <a download href="/files/raw?...&dl=1">; bộ chặn iOS cũ mở nó bằng window.open(..., "_blank"),
   và trên iPad kiểu app này iOS KHÔNG mở lớp Safari có nút Xong mà thay luôn cả app. Link có
   target="_blank" (URL đầy đủ) thì bộ chặn bỏ qua, kết quả y hệt.

   Đã chạy thật bằng Chromium giả lập iPad (mô tả PR): bấm cả hai kiểu link đều mở khung xem,
   địa chỉ trang không đổi, nút Back đóng khung, nút Tải về đưa đúng file PDF vào bảng chia sẻ.

   KHÔNG dùng ký tự em dash. */
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

global.window = { location: { href: "https://javis.example/", origin: "https://javis.example" } };
const CR = require(path.join(ROOT, "dashboard", "chat-render.js"));
const src = fs.readFileSync(path.join(ROOT, "dashboard", "chat-render.js"), "utf8");
const fe = fs.readFileSync(path.join(ROOT, "dashboard", "file-editor.js"), "utf8");

// ---- 1. Bộ chặn iOS: PDF vào khung xem trong app, TRƯỚC nhánh target="_blank" và window.open ----
const chan = src.slice(src.indexOf("// TAI FILE TREN IPHONE"), src.indexOf("// Checkbox task"));
const iPdf = chan.indexOf("moPdf(xem, ten)");
check("PDF mở bằng khung xem trong app", iPdf > 0 && /JavisFileEditor\.openPdf/.test(chan));
check("nhánh PDF chạy TRƯỚC khi bỏ qua link target=_blank", iPdf > 0 && iPdf < chan.indexOf('if (a.target === "_blank") return;'));
check("nhánh PDF chạy TRƯỚC window.open", iPdf < chan.lastIndexOf("window.open("));
check("nhánh PDF chặn điều hướng của trình duyệt", /e\.preventDefault\(\);\s*e\.stopPropagation\(\);\s*moPdf\(xem, ten\);/.test(chan));
check("xem bản không dl=1 (khung xem hiện PDF, không ép tải)", chan.indexOf("var xem = href.replace(/([?&])dl=1") < iPdf);

// ---- 2. Khung xem PDF ----
const rp = (fe.match(/function renderPdf\([\s\S]*?\n  \}/) || [""])[0];
check("iOS: nút Tải về là bảng chia sẻ, không có link mở tab", /if \(laIOS\(\)\) elActions\.appendChild\(taiVeIOS\(url, ten\)\);/.test(rp));
check("máy khác giữ nút mở tab và tải về như cũ", /openLinkUrl\(url\)/.test(rp) && /dlLinkUrl\(url, ten\)/.test(rp));
check("khung xem có nút Đóng", /elActions\.appendChild\(closeBtn\(\)\)/.test(rp));
const tv = (fe.match(/function taiVeIOS\([\s\S]*?\n  \}/) || [""])[0];
check("tải sẵn PDF thành File khi khung vừa mở", /fetch\(url, \{ credentials: "same-origin" \}\)/.test(tv) && /new File\(\[bl\], ten/.test(tv));
check("bấm Tải về: mở bảng chia sẻ ngay nếu file đã sẵn", /if \(tep && navigator\.share\) \{ chiaSe\(tep\); return; \}/.test(tv));
check("tự đóng bảng chia sẻ thì thôi, không mở gì thêm", /err\.name === "AbortError"\) return;/.test(tv));
check("iOS chặn vì quá cú bấm: báo bấm lại", /NotAllowedError/.test(tv) && /fedit\.dl_tap_again/.test(tv));
const op = (fe.match(/function openPdf\([\s\S]*?\n  \}/) || [""])[0];
check("openPdf dùng chung modal (nút Back của máy đóng được)", /moModal\(ten\)/.test(op) && /history\.pushState\(\{ jvfe: 1 \}/.test(fe));
check("openPdf được xuất ra cho chat-render.js", /JavisFileEditor = \{ open: open, close: close, openPdf: openPdf \}/.test(fe));

const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/en.json"), "utf8"));
check("câu bấm lại có đủ hai thứ tiếng", !!vi["fedit.dl_tap_again"] && !!en["fedit.dl_tap_again"]);

// ---- 3. Chữ đậm trong link ----
const h = CR.mdToHtml("Đây anh ạ: [**Tải slide PDF**](/files/raw?brain=b&path=exports/a.pdf).");
check("link [**chữ**](...) hiện chữ đậm, không lộ dấu sao", /<strong>Tải slide PDF<\/strong><\/a>/.test(h) && h.indexOf("**") < 0);
const h2 = CR.mdToHtml("[a*b](https://x.com)");
check("một dấu sao lẻ trong link giữ nguyên", />a\*b<\/a>/.test(h2));

console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
