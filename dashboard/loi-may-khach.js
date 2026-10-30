/* loi-may-khach.js - hộp đen lỗi giao diện (0.416.0).

   Lỗi JS chỉ sống trong trình duyệt của người gặp nó. Ngày 30/10/2026 phải dựng lại từ ảnh chụp của khách mới biết trang
   đã nhận về trang lỗi HTML thay vì JSON. File này bắt lỗi (`error`) và promise hỏng không ai bắt (`unhandledrejection`)
   rồi gửi về máy chủ (POST /client-errors, server/loi_may_khach.py); trang Sức khoẻ liệt kê theo nhóm.

   Dè dặt để không thành nguồn ồn: mỗi lỗi chỉ gửi một lần mỗi trang (cùng thông điệp, file, dòng), tối đa 20 lỗi một
   lần mở trang, gom 2 giây một chuyến. Bỏ qua lỗi không phải của Javis (tiện ích trình duyệt, script từ nơi khác, "Script
   error." không có chi tiết). Không gửi nội dung chat, chỉ thông tin kỹ thuật.

   Số dòng báo về khớp mã nguồn dù file đã nén gọn (server/tinh_gon.py giữ nguyên số dòng). nenGui là hàm thuần cho test. */
(function () {
  "use strict";

  var TOI_DA = 20;
  // Tiếng ồn quen thuộc, không phải lỗi của Javis.
  var BO_QUA = /^(Script error\.?|ResizeObserver loop|.*AbortError|The operation was aborted)/i;

  // Có nên gửi lỗi này không. `goc` là location.origin.
  function nenGui(msg, src, goc) {
    msg = String(msg || "");
    if (!msg || BO_QUA.test(msg)) return false;
    src = String(src || "");
    if (!src) return true;
    if (/^(chrome|moz|safari|webkit)-extension:/.test(src)) return false;
    return src.indexOf(goc + "/") === 0 || src.charAt(0) === "/";
  }

  var api = { nenGui: nenGui, TOI_DA: TOI_DA };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined") return;

  var cho = [], daGui = {}, dem = 0, hen = 0;

  function phienBan() {
    try { return JSON.parse(document.getElementById("javis-fresh").textContent).version || ""; } catch (e) { return ""; }
  }
  function trang() {
    try { return (window.Alpine && Alpine.store("nav") && Alpine.store("nav").active) || ""; } catch (e) { return ""; }
  }

  function day() {
    hen = 0;
    if (!cho.length) return;
    var lo = cho.splice(0);
    try {
      fetch("/client-errors", {
        method: "POST", credentials: "same-origin", keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version: phienBan(), errors: lo }),
      }).catch(function () {});
    } catch (e) { /* hộp đen không bao giờ được tự gây lỗi */ }
  }

  function them(loai, msg, src, dong, cot, stack) {
    try {
      if (!nenGui(msg, src, location.origin)) return;
      src = String(src || "").replace(location.origin, "").replace(/\?v=[\w.]+/, "");
      var khoa = msg + "|" + src + "|" + dong;
      if (daGui[khoa] || dem >= TOI_DA) return;
      daGui[khoa] = 1;
      dem++;
      cho.push({ loai: loai, msg: String(msg).slice(0, 500), src: src, dong: dong || 0, cot: cot || 0,
        stack: String(stack || "").slice(0, 2000), trang: trang() });
      if (!hen) hen = setTimeout(day, 2000);
    } catch (e) { /* noop */ }
  }

  window.addEventListener("error", function (e) {
    // Ảnh hay script tải hỏng cũng bắn "error" (trên chính phần tử, không phải window): không phải lỗi code.
    if (!e || (e.target && e.target !== window)) return;
    them("error", e.message, e.filename, e.lineno, e.colno, e.error && e.error.stack);
  }, true);
  window.addEventListener("unhandledrejection", function (e) {
    var r = e && e.reason;
    var msg = r && r.message ? r.message : String(r);
    var st = r && r.stack ? String(r.stack) : "";
    // Lấy file và dòng từ dòng đầu của ngăn xếp có /static/ (Chrome: "at f (http://h/static/x.js?v=1:12:5)",
    // Safari: "f@http://h/static/x.js?v=1:12:5").
    var m = /(https?:\/\/[^\s)]+\/static\/[^\s):]+):(\d+):(\d+)/.exec(st);
    them("promise", msg, m ? m[1] : "", m ? Number(m[2]) : 0, m ? Number(m[3]) : 0, st);
  });
  window.addEventListener("pagehide", day);
  window.JavisLoiMayKhach = api;
})();
