/* fetch-gop.js - gộp các lượt ĐỌC trùng nhau trong một khoảnh khắc (0.416.0).

   Đo lúc mở app ngày 30/10/2026: /settings bị hỏi 9 lần, /agents, /skills, /workflows mỗi cái 2 lần, /connect/health
   2 lần, vì mỗi phần của dashboard (app.js, console.js, pet.js, branding.js, model-picker.js...) tự hỏi lấy cái nó
   cần. Qua Cloudflare mỗi lượt là một chuyến đi về, và chúng tranh chỗ với chính các file đang tải.

   Sửa từng chỗ gọi thì sót, và chỗ mới viết mai lại sót tiếp. Nên gộp ở MỘT điểm: bọc window.fetch. Cùng một GET tới
   cùng một địa chỉ trong DANH SÁCH dưới đây, gọi trong vòng 1,5 giây, thì dùng chung một câu trả lời (mỗi bên nhận một
   bản sao riêng, đọc thoải mái). Bất kỳ lượt GHI nào (POST, PUT, PATCH, DELETE) đều xoá sạch phần đã nhớ, nên đọc ngay
   sau khi lưu luôn ra dữ liệu mới. Chỉ gộp các địa chỉ trong danh sách: đọc thì rẻ để trùng, còn đường lạ (stream,
   tải file) thì không bao giờ động tới.

   gopDuoc, khoaGop là hàm thuần để node test chạy được. */
(function () {
  "use strict";

  var GIU_MS = 1500;
  // Đường đọc an toàn để dùng chung: trả JSON nhỏ, không có tác dụng phụ.
  var DUONG = /^\/(settings|config|brains|agents|skills|workflows|connect\/health|auth\/status|voice\/ear|voice\/call|plan-limits)(\?|$)/;

  function laGet(init) {
    var m = init && init.method ? String(init.method).toUpperCase() : "GET";
    return m === "GET" || m === "HEAD" ? m : "";
  }

  // Khoá gộp cho một lời gọi, hoặc "" khi không được gộp. `input` là chuỗi URL (Request object thì để nguyên).
  function khoaGop(input, init, goc) {
    if (typeof input !== "string") return "";
    var m = laGet(init);
    if (m !== "GET" || (init && init.body)) return "";
    // Có hẹn huỷ riêng (AbortController) thì không gộp: một bên huỷ là bên kia cũng mất. Người gọi ghi rõ muốn bản mới
    // nhất (no-store, reload) thì cũng không.
    if (init && (init.signal || init.cache === "no-store" || init.cache === "reload")) return "";
    var u;
    try { u = new URL(input, goc || "http://x"); } catch (e) { return ""; }
    if (goc && u.origin !== new URL(goc).origin) return "";
    var duong = u.pathname + u.search;
    return DUONG.test(duong) ? duong : "";
  }

  function gopDuoc(input, init, goc) { return khoaGop(input, init, goc) !== ""; }

  var api = { khoaGop: khoaGop, gopDuoc: gopDuoc, GIU_MS: GIU_MS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined" || typeof window.fetch !== "function") return;

  var goc = window.fetch.bind(window);
  var nho = {};   // khoá -> { luc, p: Promise<Response> }

  window.fetch = function (input, init) {
    // Một lượt ghi: những gì đã nhớ có thể đã cũ.
    if (!laGet(init) || (init && init.body)) nho = {};
    var khoa = khoaGop(input, init, location.origin);
    if (!khoa) return goc(input, init);
    var bay = Date.now();
    var e = nho[khoa];
    if (!e || bay - e.luc > GIU_MS) {
      e = { luc: bay, p: goc(input, init) };
      nho[khoa] = e;
      // Hỏng thì quên ngay, lần sau gọi lại thật.
      e.p.then(function (r) { if (!r.ok && nho[khoa] === e) delete nho[khoa]; },
        function () { if (nho[khoa] === e) delete nho[khoa]; });
    }
    return e.p.then(function (r) { return r.clone(); });
  };
  window.JavisFetchGop = api;
})();
