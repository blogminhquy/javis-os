/* ui-context.js - khối [NGỮ CẢNH GIAO DIỆN: ...] dashboard chèn trước câu hỏi (Voice V1, spec mục 5).

   Javis cần biết người dùng ĐANG NHÌN gì để "cái này", "đoạn này", "cuộn xuống" có nghĩa mà
   không phải hỏi lại. Ba thứ được gửi: trang đang mở (trừ chat/home, mặc định không mang tin),
   đoạn đang bôi đen (cắt 600 ký tự), và câu Javis bị ngắt lời lúc đọc (để nó không đọc lại từ
   đầu). Không có gì thì trả chuỗi RỖNG: đừng tốn token cho một khối trống.

   Khối này bị lột khỏi bong bóng hiển thị (app.js chuNguoiGo) và khỏi tiêu đề hội thoại
   (sessions.py), cùng cách với khối FILE ĐANG MỞ. Thuần, test bằng node được.
   Ghi chú: KHÔNG dùng ký tự em dash. */
(function () {
  "use strict";

  var PREFIX = "[NGỮ CẢNH GIAO DIỆN:";
  var MAX_SEL = 600;
  var MAX_INT = 240;

  function clip(s, n) {
    s = String(s == null ? "" : s).replace(/\s+/g, " ").trim();
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  // Ngoặc vuông và xuống dòng trong dữ liệu người dùng làm hỏng ranh giới khối -> thay đi.
  function safe(s) {
    return String(s == null ? "" : s).replace(/[\[\]]/g, " ").replace(/[\r\n]+/g, " ");
  }

  function build(ctx) {
    ctx = ctx || {};
    var parts = [];
    var page = String(ctx.page || "").trim();
    if (page && page !== "chat" && page !== "home") parts.push("trang=" + safe(page));
    var sel = clip(ctx.selection, MAX_SEL);
    if (sel) parts.push('chọn="' + safe(sel) + '"');
    var it = clip(ctx.interruptedAt, MAX_INT);
    if (it) parts.push('ngắt_lời="' + safe(it) + '"');
    // Đang nói chuyện bằng giọng (mic bật, câu trả lời sẽ ĐỌC ra loa): model phải trả lời như
    // người đang nói, ngắn và không dàn trang (V3). channel_context.py giải thích khoá này.
    if (ctx.voice) parts.push("kênh=giọng");
    if (!parts.length) return "";
    return PREFIX + " " + parts.join("; ") + "]";
  }

  var api = { build: build, PREFIX: PREFIX, MAX_SEL: MAX_SEL };
  if (typeof window !== "undefined") window.JavisUiContext = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
