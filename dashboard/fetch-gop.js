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
  // 2026-11-05: + `sessions/<id>/meta`, asked twice on every chat switch (model bar and project chip).
  var DUONG = /^\/(settings|config|brains|agents|skills|workflows|connect\/health|auth\/status|voice\/ear|voice\/call|plan-limits|sessions\/[^/?]+\/meta)(\?|$)/;

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

  // ── Stale-while-revalidate for the console pages (2026-11-08) ──
  // Owner, 2026-11-08: pages "load" for seconds. Measured over a 250 ms tunnel: 0.3-1.4 s per page, spent waiting for
  // the server, every visit. The reads below feed the console pages (Skills, Connections, Channels, Settings, Models,
  // Self-learning, Usage, Webhooks...). While a page is first drawn (EARLY_MS after its visit began) each of them is
  // answered at once from the copy the last visit left (up to SWR_MAX_AGE_MS old) while the server is asked again;
  // console.js draws the page again when the answer differs. Later reads on the same visit (polling, a refresh button)
  // go to the server as before, so nothing stays one step behind. Any write clears every copy (except the bookkeeping
  // posts in NO_CHANGE_POSTS), and so does the end of every chat turn (app.js): Javis may have just changed a skill, a
  // connection or a setting.
  var SWR_MAX_AGE_MS = 10 * 60 * 1000;
  var SWR = new RegExp("^/(settings|agents|skills|workflows|brains|plugins|tools/optional|packs|logins|share/list|"
    + "webhooks|webhooks/health|connect/(catalog|health)|github/status|messenger/setup|threads/setup|"
    + "(telegram|whatsapp|zalo-bot|discord|slack|lark)/status|claude/status|autostart|domain/status|"
    + "remote-access/status|auth/tokens|learn/(config|metrics|review|log)|auto-learning|backup/status|"
    + "usage/(insights|theo-gio|tong-quan)|runtime/muc|cache-keepwarm)(\\?|$)");
  // Posts that change nothing a page shows: a chat marked read on every switch, error and diagnostics reports.
  var NO_CHANGE_POSTS = /^\/(sessions\/[^/?]+\/read|client-errors|diag\/|star-nudge\/check)(\?|$)/;

  // Key of a read that may be answered from a kept copy, or "". Like khoaGop, other list; a refresh asked explicitly
  // (`refresh=1`, no-store, reload) always goes to the server. A read with its own timeout (AbortController) is
  // allowed: a copy answers at once, and without one it still gets its own request with its own signal.
  function swrKey(input, init, goc) {
    if (typeof input !== "string" || laGet(init) !== "GET" || (init && init.body)) return "";
    if (init && (init.cache === "no-store" || init.cache === "reload")) return "";
    var u;
    try { u = new URL(input, goc || "http://x"); } catch (e) { return ""; }
    if (goc && u.origin !== new URL(goc).origin) return "";
    if (/(^|[?&])refresh=(1|true)(&|$)/.test(u.search)) return "";
    var path = u.pathname + u.search;
    return SWR.test(path) ? path : "";
  }

  // Does this call leave every kept copy valid? Only reads and the bookkeeping posts above do.
  function keepsCopies(input, init, goc) {
    if (laGet(init) && !(init && init.body)) return true;
    var path = "";
    try { var u = new URL(typeof input === "string" ? input : input.url, goc || "http://x"); path = u.pathname; } catch (e) {}
    return NO_CHANGE_POSTS.test(path);
  }

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

  var api = { khoaGop: khoaGop, gopDuoc: gopDuoc, thuLaiDuoc: thuLaiDuoc, maTam: maTam, CHO_THU_LAI: CHO_THU_LAI, GIU_MS: GIU_MS,
    swrKey: swrKey, keepsCopies: keepsCopies, SWR_MAX_AGE_MS: SWR_MAX_AGE_MS };
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
  // 0.444.4: lệch ngẫu nhiên ±30%. Không có nó, mọi lượt đọc của mọi tab thử lại ĐÚNG cùng nhịp và dồn một lúc vào
  // máy chủ vừa chậm lại, làm nó càng chậm.
  function lech(ms) { return Math.round(ms * (0.7 + Math.random() * 0.6)); }

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
          return ngu(lech(CHO_THU_LAI[lan++])).then(thu);
        }
        bao(false);
        return r;
      }, function (loi) {
        if (lan < CHO_THU_LAI.length) {
          bao(true);
          return ngu(lech(CHO_THU_LAI[lan++])).then(thu);
        }
        bao(false);
        throw loi;
      });
    }
    return thu();
  }

  // ── Kept copies for the console pages (see SWR above) ──
  var copies = {};         // key -> { at, text, status, ct }
  var inflight = {};       // key -> Promise<Response>, one request in flight per key
  var page = "";           // the console page being drawn (console.js tells, see api.pageStart)
  var readThisVisit = {};  // keys read on this page visit (a changed answer for one of them redraws the page)
  var visitAt = 0;         // when the page visit began
  var EARLY_MS = 2500;     // reads this soon after the visit began belong to its first drawing and may use a copy

  function fromCopy(c) { return new Response(c.text, { status: c.status, headers: { "Content-Type": c.ct } }); }

  // Keep the answer's text as the copy of `key`; when it differs from the copy the page was drawn from, ask
  // console.js to draw the page again.
  function keep(key, r) {
    if (!r.ok) { delete copies[key]; return Promise.resolve(r); }
    return r.clone().text().then(function (text) {
      var c0 = copies[key];
      copies[key] = { at: Date.now(), text: text, status: r.status, ct: r.headers.get("Content-Type") || "application/json" };
      if (c0 && c0.text !== text && page && readThisVisit[key]) {
        try { window.dispatchEvent(new CustomEvent("javis:page-data", { detail: { page: page, key: key } })); } catch (e) {}
      }
      return r;
    }, function () { return r; });
  }

  // One shared request per key. Never carries a caller's signal: one caller giving up must not cancel it for the rest.
  function refetch(key, input, init) {
    if (inflight[key]) return inflight[key];
    var own = {};
    for (var k in (init || {})) if (k !== "signal") own[k] = init[k];
    var p = goc(input, own).then(function (r) { return keep(key, r); });
    inflight[key] = p;
    var done = function () { if (inflight[key] === p) delete inflight[key]; };
    p.then(done, done);
    return p;
  }

  function fromCopyOrServer(key, input, init) {
    var c = copies[key], now = Date.now();
    var early = now - visitAt <= EARLY_MS;
    readThisVisit[key] = true;
    if (c && now - c.at <= GIU_MS) return Promise.resolve(fromCopy(c));
    if (early && c && now - c.at <= SWR_MAX_AGE_MS) {
      refetch(key, input, init).catch(function () {});
      return Promise.resolve(fromCopy(c));
    }
    // No usable copy: a caller with its own timeout keeps its own request; the others share one.
    if (init && init.signal) return goc(input, init).then(function (r) { return keep(key, r); }).then(function (r) { return r.clone(); });
    return refetch(key, input, init).then(function (r) { return r.clone(); });
  }

  // console.js: a page starts drawing (a visit, or a redraw). Its first read of each key may use a kept copy again.
  api.pageStart = function (id) { page = String(id || ""); readThisVisit = {}; visitAt = Date.now(); };
  // Forget every kept copy (a chat turn ended: Javis may have changed what the pages show).
  api.forget = function () { copies = {}; nho = {}; };

  window.fetch = function (input, init) {
    // Một lượt ghi: những gì đã nhớ có thể đã cũ.
    if (!keepsCopies(input, init, location.origin)) { nho = {}; copies = {}; }
    var copyKey = swrKey(input, init, location.origin);
    if (copyKey) return fromCopyOrServer(copyKey, input, init);
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
