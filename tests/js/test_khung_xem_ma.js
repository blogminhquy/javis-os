/* Khung xem mã (artifact) là HỘP THOẠI GIỮA MÀN HÌNH, và mã XUỐNG DÒNG.
 *
 *       node tests/js/test_khung_xem_ma.js
 *
 * Chủ repo báo 21/09: mở một khối mã trong file .md thì khung dính mép phải màn hình, chữ
 * chạy thẳng sang phải vô hạn, phải kéo ngang từng dòng mới đọc được, và bấm ra ngoài không
 * đóng được.
 *
 * Ba tính chất được canh ở đây, vì cả ba đều dễ bị một lần dọn CSS sau này làm hỏng lặng lẽ:
 *
 *   1. GIỮA MÀN HÌNH: lớp phủ căn giữa, hộp thật nằm trong. Không phải "ngăn kéo rộng hơn".
 *   2. XUỐNG DÒNG MẶC ĐỊNH, kèm `overflow-wrap` - thiếu vế sau thì một chuỗi dài không có dấu
 *      cách (URL, base64, đường dẫn) vẫn đẩy ngang một dòng duy nhất ra khỏi hộp, tức là
 *      "đã xuống dòng" mà vẫn phải kéo ngang.
 *   3. BẤM RA NGOÀI LÀ ĐÓNG - chỉ đúng vì khung này thuần để XEM; ở một hộp xác nhận thì bấm
 *      nhầm ra ngoài mà coi là đồng ý sẽ là chuyện khác hẳn.
 *
 * Thứ tự tầng (z-index) so với trình sửa phóng to do test_phong_to_md_che_het_rail.js canh. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "dashboard", "chat-render.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
const check = (ten, ok, them) => {
  console.log((ok ? "ok   " : "FAIL ") + ten + (ok || them === undefined ? "" : "  [" + them + "]"));
  if (!ok) fails.push(ten);
};
/** Thân của luật CSS đầu tiên khớp selector (so đúng chuỗi selector + " {"). */
function luat(sel) {
  const i = CSS.indexOf(sel + " {");
  return i === -1 ? "" : CSS.slice(i, CSS.indexOf("}", i));
}

// ============================================================
// 1. Giữa màn hình, không còn là ngăn kéo mép phải
// ============================================================
const lop = luat(".jv-artpanel");
check("lớp phủ phủ kín màn hình", /position:\s*fixed/.test(lop) && /inset:\s*0/.test(lop), lop);
check("và căn GIỮA", /align-items:\s*center/.test(lop) && /justify-content:\s*center/.test(lop), lop);
check("có màn che mờ phía sau", /background:\s*var\(--scrim\)/.test(lop), lop);
// CANARY: đúng ba thứ làm nên cái ngăn kéo cũ. Còn sót là nó lại dính mép phải.
check("CANARY: không còn dính mép phải (right/bottom/border-left của ngăn kéo cũ)",
      !/right:\s*0/.test(lop) && !/border-left/.test(lop), lop);
const hop = luat(".jv-ap-box");
check("hộp thật là .jv-ap-box, có bo góc và trần chiều cao",
      /border-radius/.test(hop) && /max-height/.test(hop), hop);
check("hộp dựng trong JS đúng lớp đó", /class="jv-ap-box"/.test(JS));
check("và khai báo là hộp thoại cho trình đọc màn hình",
      /role="dialog" aria-modal="true"/.test(JS));
// Đoạn mã ngắn nằm trong hộp cao 84% màn hình thì chín phần mười hộp trống trơn; nhưng tab
// xem trước chứa <iframe> cao 100%, mà iframe trong hộp cao-theo-nội-dung thì xẹp còn 0.
check("xem mã thì hộp ôm nội dung, xem trước thì cao đủ cho iframe",
      /\.jv-artpanel:not\(\.jv-ap-oncode\) \.jv-ap-box \{[^}]*height:/.test(CSS));
check("khoá cuộn nền khi hộp đang mở",
      /body\.jv-artpanel-open \{[^}]*overflow:\s*hidden/.test(CSS));

// ============================================================
// 2. Xuống dòng
// ============================================================
const ma = luat(".jv-ap-code");
check("mã XUỐNG DÒNG mặc định", /white-space:\s*pre-wrap/.test(ma), ma);
check("và chuỗi dài không dấu cách cũng ngắt được", /overflow-wrap:\s*anywhere/.test(ma), ma);
// Luật chung .code-block đặt `white-space: pre`, nên luật của khung này phải đứng SAU nó
// trong file mới thắng (hai bên cùng độ ưu tiên 0,1,0).
check("luật của khung đứng sau .code-block nên thắng được luật chung",
      CSS.indexOf(".jv-ap-code {") > CSS.indexOf(".code-block {"));
check("tắt nút thì quay về cuộn ngang như cũ",
      /\.jv-artpanel\.jv-ap-nowrap \.jv-ap-code \{[^}]*white-space:\s*pre[;\s}]/.test(CSS));
check("có nút gạt xuống dòng, bật sẵn", /var wrapMa = true;/.test(JS)
      && /data-act="wrap" aria-pressed="true"/.test(JS));
check("bấm nút chỉ lật một lớp trên khung, KHÔNG vẽ lại nội dung",
      /act === "wrap"\) \{ wrapMa = !wrapMa; syncWrap\(\); \}/.test(JS));
check("nút chỉ hiện khi đang nhìn mã",
      /classList\.toggle\("jv-ap-oncode"/.test(JS)
      && /\.jv-artpanel:not\(\.jv-ap-oncode\) \.jv-ap-tog \{[^}]*display:\s*none/.test(CSS));
["crender.ap_wrap", "crender.ap_wrap_hint", "crender.art_lines_n"].forEach((k) => {
  check("khoá " + k + " có ở cả vi và en", !!VI[k] && !!EN[k]);
});

// ============================================================
// 3. Bấm ra ngoài là đóng
// ============================================================
check("bấm trúng LỚP PHỦ (không phải hộp) thì đóng",
      /if \(e\.target === panel\) \{ closePanel\(\); return; \}/.test(JS));
check("Esc vẫn đóng được như cũ",
      /e\.key === "Escape" && panel && panel\.classList\.contains\("open"\)/.test(JS));
check("mở hộp thì tiêu điểm vào trong hộp (Tab không lạc ra trang bị che)",
      /querySelector\("\.jv-ap-close"\)[\s\S]{0,60}\.focus\(\)/.test(JS));

// Nút Copy đổi thành icon SVG, mà textContent của icon là chuỗi rỗng: nhớ lại bằng
// textContent thì sau một giây nút trống không, không còn gì để bấm.
check("nút Copy khôi phục bằng innerHTML chứ không phải textContent",
      /var o = btn\.innerHTML;[\s\S]{0,140}btn\.innerHTML = o;/.test(JS)
      && !/btn\.textContent = o;/.test(JS));

if (fails.length) {
  console.log(`\nFAIL ${fails.length} muc: ` + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_khung_xem_ma: tat ca pass");
