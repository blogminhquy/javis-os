/* fetch-gop.js - gộp các lượt ĐỌC trùng nhau trong một khoảnh khắc (0.416.0).

   Đo lúc mở app ngày 30/10/2026: /settings bị hỏi 9 lần, /agents, /skills, /workflows mỗi cái 2 lần, /connect/health
   2 lần, vì mỗi phần của dashboard (app.js, console.js, pet.js, branding.js, model-picker.js...) tự hỏi lấy cái nó
   cần. Qua Cloudflare mỗi lượt là một chuyến đi về, và chúng tranh chỗ với chính các file đang tải.

   Sửa từng chỗ gọi thì sót, và chỗ mới viết mai lại sót tiếp. Nên gộp ở MỘT điểm: bọc window.fetch. Cùng một GET tới
   cùng một địa chỉ trong DANH SÁCH dưới đây, gọi trong vòng 1,5 giây, thì dùng chung một câu trả lời (mỗi bên nhận một
   bản sao riêng, đọc thoải mái). Bất kỳ lượt GHI nào (POST, PUT, PATCH, DELETE) đều xoá sạch phần đã nhớ, nên đọc ngay
   sau khi lưu luôn ra dữ liệu mới. Chỉ gộp các địa chỉ trong danh sách: đọc thì rẻ để trùng, còn đường lạ (stream,
   tải file) thì không bao giờ động tới.

   0.417.0, THỬ LẠI. Ngày 30/10/2026 một khách bấm cập nhật, trang mở lại giữa lúc máy chủ (hay đường hầm Cloudflare trước
   nó) còn khởi động; mọi lượt hỏi nhận về trang lỗi 502 và giao diện vỡ luôn ("The string did not match the expected
   pattern" là câu Safari báo khi đọc trang lỗi HTML như JSON). Lớp này giờ còn làm thêm một việc cho cả dashboard:
   - lượt ĐỌC (GET) cùng máy chủ gặp lỗi đường truyền hay mã 502, 503, 504, 520-530 (mã của Cloudflare khi không tới được
     máy chủ) thì tự thử lại sau 0,5, 1, 2, 3, 4 giây (tổng khoảng 10 giây) trước khi trả lỗi cho chỗ gọi;
   - lượt GHI không bao giờ tự gửi lại: gửi trùng một lệnh là làm hai lần;
   - 500 là lỗi thật của code, không thử lại; lượt tự lo việc chờ (`cache: no-store`, có `signal`) cũng không đụng;
   - đang thử lại thì hiện một dải nhỏ "Đang kết nối lại máy chủ" ở đầu trang, có câu trả lời tốt là tự ẩn.

   gopDuoc, khoaGop, thuLaiDuoc, maTam là hàm thuần để node test chạy được. */
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

  var CHO_THU_LAI = [500, 1000, 2000, 3000, 4000];

  // Mã trả về cho thấy máy chủ CHƯA tới được (đang khởi động, đường hầm chập chờn), không phải lỗi của chính yêu cầu.
  function maTam(status) { return status === 502 || status === 503 || status === 504 || (status >= 520 && status <= 530); }

  // Lời gọi này có được tự thử lại không: GET tới chính máy chủ Javis, không phải file tĩnh, không tự lo việc chờ.
  function thuLaiDuoc(input, init, goc) {
    if (typeof input !== "string") return false;
    if (laGet(init) !== "GET" || (init && init.body)) return false;
    if (init && (init.signal || init.cache === "no-store" || init.cache === "reload")) return false;
    var u;
    try { u = new URL(input, goc || "http://x"); } catch (e) { return false; }
    if (goc && u.origin !== new URL(goc).origin) return false;
    return u.pathname.indexOf("/static/") !== 0 && !/stream|events|sse/i.test(u.pathname);
  }

  var api = { khoaGop: khoaGop, gopDuoc: gopDuoc, thuLaiDuoc: thuLaiDuoc, maTam: maTam, CHO_THU_LAI: CHO_THU_LAI, GIU_MS: GIU_MS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined" || typeof window.fetch !== "function") return;

  var gocThat = window.fetch.bind(window);
  var nho = {};   // khoá -> { luc, p: Promise<Response> }

  // ── Dải "Đang kết nối lại máy chủ" ──
  var dangThu = 0, dai = null;
  function veDai(hien) {
    try {
      if (hien) {
        if (!dai) {
          dai = document.createElement("div");
          dai.id = "javisKetNoiLai";
          dai.setAttribute("role", "status");
          dai.style.cssText = "position:fixed;left:50%;top:max(10px,env(safe-area-inset-top));transform:translateX(-50%);"
            + "z-index:99998;padding:8px 16px;border-radius:999px;font-size:15px;line-height:1.4;"
            + "background:var(--bg2,#1b1f2a);color:var(--text,#e8eaf0);border:1px solid var(--yellow,#e0a800);"
            + "box-shadow:0 6px 20px rgba(0,0,0,.3);pointer-events:none";
        }
        // Từ điển chưa về (máy chủ đang khởi động thì nó cũng đang thử lại) thì chỉ hiện dấu chấm, không hiện mã khoá.
        var chu = window.t ? window.t("net.reconnecting") : "";
        dai.textContent = chu && chu !== "net.reconnecting" ? chu : "…";
        if (!dai.isConnected && document.body) document.body.appendChild(dai);
      } else if (dai && dai.isConnected) {
        dai.remove();
      }
    } catch (e) { /* dải báo không bao giờ được làm hỏng lời gọi */ }
  }

  function ngu(ms) { return new Promise(function (xong) { setTimeout(xong, ms); }); }

  // fetch thật, kèm thử lại cho lượt đọc khi máy chủ chưa tới được.
  function goc(input, init) {
    if (!thuLaiDuoc(input, init, location.origin)) {
      return gocThat(input, init).then(function (r) {
        if (dangThu === 0 && dai && r.ok) veDai(false);
        return r;
      });
    }
    var lan = 0, dangBao = false;
    function bao(on) {
      if (on && !dangBao) { dangBao = true; dangThu++; veDai(true); }
      if (!on && dangBao) { dangBao = false; dangThu--; if (dangThu <= 0) { dangThu = 0; veDai(false); } }
    }
    function thu() {
      return gocThat(input, init).then(function (r) {
        if (maTam(r.status) && lan < CHO_THU_LAI.length) {
          bao(true);
          return ngu(CHO_THU_LAI[lan++]).then(thu);
        }
        bao(false);
        return r;
      }, function (loi) {
        if (lan < CHO_THU_LAI.length) {
          bao(true);
          return ngu(CHO_THU_LAI[lan++]).then(thu);
        }
        bao(false);
        throw loi;
      });
    }
    return thu();
  }

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
