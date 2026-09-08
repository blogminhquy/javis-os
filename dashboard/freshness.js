/* Người gác cổng bản cũ: phát hiện trình duyệt đang chạy code KHÔNG khớp với máy chủ.
 *
 * VÌ SAO CÓ FILE NÀY (vụ 03/09/2026)
 * Chủ repo báo "up file vẫn không chọn được nhiều file" sau khi bản vá đã lên main và đã
 * cập nhật máy chủ. Hoá ra trình duyệt chạy sessions-ui.js CŨ, trong khi dòng chữ ngay
 * cạnh cái ô đó lại là chữ MỚI - vì hai thứ đi hai đường khác nhau tới trình duyệt:
 *   - từ điển i18n: tải kèm `cache: no-cache`, luôn hỏi lại máy chủ  -> LUÔN mới
 *   - file .js/.css: mang `?v=<phiên bản>` + đóng dấu cache 1 năm immutable -> đứng yên
 *     vĩnh viễn nếu có tầng cache nào bỏ qua phần `?v=`
 * Kết quả là một sự cố CÂM: bản vá "không ăn", người dùng tưởng code sai, người sửa không
 * tài nào tái hiện. Chú thích trong main.root() cho thấy repo đã vấp đúng chuyện này một
 * lần trước đó (console.js đứng yên suốt hàng chục bản mà không ai biết).
 *
 * VÌ SAO KHÔNG CHỈ SO SỐ PHIÊN BẢN
 * Ở đúng ca trên, số phiên bản KHỚP mà nội dung thì cũ. Nên file này so chính NỘI DUNG:
 * server nhúng vào trang crc32 của từng file .js/.css, ở đây tải lại đúng URL ấy (lấy từ
 * cache, không tốn mạng) rồi băm và đối chiếu. Lệch nghĩa là thứ đang chạy không phải thứ
 * máy chủ có.
 *
 * ĐIỂM TỰA: index.html được trả kèm `no-store` nên nó LUÔN mới, kể cả khi mọi file JS
 * quanh nó đã cũ. Khối <script id="javis-fresh"> nằm trong đó vì vậy luôn nói thật.
 * Chính file này cũng nạp KHÔNG kèm `?v=` và được đóng dấu `no-cache` (xem middleware
 * _static_cache_headers) - người gác cổng mà cũ theo thì nó gác cái gì.
 */
(function () {
  "use strict";

  var CHU_KY_MS = 5 * 60 * 1000;     // nhịp hỏi lại máy chủ xem đã có bản mới chưa
  var KHOA_DA_TAI = "javis-fresh-reloaded";   // chống vòng lặp tải lại vô tận

  function moc() {
    var el = document.getElementById("javis-fresh");
    if (!el) return null;
    try { return JSON.parse(el.textContent || "{}"); } catch (e) { return null; }
  }

  /* crc32 khớp từng bit với zlib.crc32 bên Python (server dùng chính hàm đó).
   * Không dùng crypto.subtle: nó chỉ có trong ngữ cảnh bảo mật, mà Javis rất hay chạy
   * trên http:// theo IP của VPS - dùng nó là người gác cổng chết lặng đúng lúc cần nhất. */
  var BANG = null;
  function bangCrc() {
    if (BANG) return BANG;
    BANG = new Uint32Array(256);
    for (var i = 0; i < 256; i++) {
      var c = i;
      for (var k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      BANG[i] = c >>> 0;
    }
    return BANG;
  }

  function crc32(bytes) {
    var t = bangCrc(), c = 0xFFFFFFFF;
    for (var i = 0; i < bytes.length; i++) c = t[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    c = (c ^ 0xFFFFFFFF) >>> 0;
    var s = c.toString(16);
    while (s.length < 8) s = "0" + s;
    return s;
  }

  /* Tải một file tĩnh ĐÚNG như trình duyệt đã tải nó lúc dựng trang: KHÔNG ép làm mới, để
   * nó trả về đúng bản đang nằm trong cache (của trình duyệt hay của proxy). Đây mới là
   * thứ cần đo - ép làm mới là đo file trên máy chủ, tức là đo nhầm đầu. */
  function taiNhuTrang(url) {
    return fetch(url, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.arrayBuffer() : null; })
      .catch(function () { return null; });
  }

  /* Trả về danh sách file mà NỘI DUNG đang chạy khác nội dung máy chủ. */
  function doLech(m) {
    var ds = Object.keys(m.assets || {});
    if (!ds.length) return Promise.resolve([]);
    var ver = encodeURIComponent(m.version || "0");
    return Promise.all(ds.map(function (rel) {
      // `?v=` phải TRÙNG KHÍT khoá mà trang đã dùng lúc nạp file, nếu không ta đo một URL
      // khác - cache miss, tải lại từ máy chủ, tức là đo file TRÊN MÁY CHỦ chứ không phải
      // file trình duyệt ĐANG CHẠY, đúng cái bẫy mà chú thích taiNhuTrang ở trên cảnh báo.
      // Server đóng dấu bằng vân tay từng file (xem `root()` trong main.py), nên khoá là
      // chính crc trong `m.assets`; rơi về số phiên bản cho bản server cũ hơn.
      var khoa = encodeURIComponent(m.assets[rel] || "") || ver;
      return taiNhuTrang("/static/" + rel + "?v=" + khoa).then(function (buf) {
        if (!buf) return null;                       // không đọc được thì im, đừng báo oan
        return crc32(new Uint8Array(buf)) === m.assets[rel] ? null : rel;
      });
    })).then(function (kq) { return kq.filter(Boolean); });
  }

  // ── Dải báo ───────────────────────────────────────────────────────────────────
  function veDai(tieuDe, chiTiet, nhanNut, khiBam) {
    if (document.getElementById("javis-fresh-bar")) return;
    var css = document.createElement("style");
    css.textContent =
      "#javis-fresh-bar{position:fixed;left:50%;transform:translateX(-50%);top:14px;z-index:99999;" +
      "display:flex;align-items:center;gap:12px;max-width:min(92vw,720px);padding:12px 16px;" +
      "border-radius:12px;border:1px solid var(--yellow,#e0a800);background:var(--bg2,#1b1f2a);" +
      "color:var(--text,#e8eaf0);font-size:16px;line-height:1.5;box-shadow:0 10px 30px rgba(0,0,0,.4)}" +
      "#javis-fresh-bar .jf-txt{flex:1 1 auto;min-width:0}" +
      "#javis-fresh-bar .jf-sub{display:block;margin-top:3px;font-size:14px;opacity:.8}" +
      "#javis-fresh-bar button{flex:none;cursor:pointer;border-radius:8px;font-size:15px;padding:7px 13px;" +
      "font-family:inherit;border:1px solid var(--border,#39405180)}" +
      "#javis-fresh-bar .jf-ok{background:var(--yellow,#e0a800);border-color:var(--yellow,#e0a800);" +
      "color:#1a1a1a;font-weight:700}" +
      "#javis-fresh-bar .jf-x{background:transparent;color:var(--text3,#8b93a7)}";
    var bar = document.createElement("div");
    bar.id = "javis-fresh-bar";
    bar.setAttribute("role", "status");
    var txt = document.createElement("div");
    txt.className = "jf-txt";
    txt.textContent = tieuDe;
    if (chiTiet) {
      var sub = document.createElement("span");
      sub.className = "jf-sub";
      sub.textContent = chiTiet;
      txt.appendChild(sub);
    }
    var ok = document.createElement("button");
    ok.className = "jf-ok";
    ok.textContent = nhanNut;
    ok.onclick = khiBam;
    var x = document.createElement("button");
    x.className = "jf-x";
    x.textContent = "Để sau";
    x.onclick = function () { bar.remove(); };
    bar.appendChild(txt); bar.appendChild(ok); bar.appendChild(x);
    document.head.appendChild(css);
    document.body.appendChild(bar);
  }

  /* KHÔNG tự tải lại trang. Người dùng có thể đang gõ dở một câu dài, và mất chữ đang gõ vì
   * một thứ họ không hề bấm là tệ hơn hẳn cái nó chữa. Chỉ hiện dải và để họ bấm. */
  function baoCoBanMoi(verMoi) {
    veDai("Javis vừa cập nhật lên bản " + verMoi + ".",
          "Tải lại trang để dùng bản mới.", "Tải lại", function () { location.reload(); });
  }

  function baoChayBanCu(ds, daThuTaiLai) {
    var ten = ds.slice(0, 3).join(", ") + (ds.length > 3 ? " và " + (ds.length - 3) + " file nữa" : "");
    if (!daThuTaiLai) {
      veDai("Trình duyệt đang chạy bản cũ của Javis.",
            "Bấm để tải lại. (" + ten + ")", "Tải lại", function () {
              try { sessionStorage.setItem(KHOA_DA_TAI, "1"); } catch (e) { /* noop */ }
              location.reload();
            });
      return;
    }
    // Tải lại rồi mà vẫn lệch: cache nằm ngoài tầm với của trang (proxy, CDN). Nói THẲNG
    // phải làm gì, đừng để người dùng bấm Tải lại mãi mà không hiểu vì sao không đổi.
    veDai("Vẫn đang chạy bản cũ dù đã tải lại.",
          "Bấm Ctrl+Shift+R (máy Mac: Cmd+Shift+R). Vẫn vậy thì có một tầng cache giữa "
          + "máy bạn và Javis đang giữ file cũ: " + ten,
          "Thử lại", function () { location.reload(true); });
  }

  // ── Chạy ──────────────────────────────────────────────────────────────────────
  var m = moc();
  if (!m) return;              // server chưa nhúng khối này (bản cũ) - im lặng, đừng phá gì

  var daThu = false;
  try { daThu = sessionStorage.getItem(KHOA_DA_TAI) === "1"; } catch (e) { /* noop */ }

  function kiemNoiDung() {
    doLech(m).then(function (ds) {
      if (!ds.length) {
        try { sessionStorage.removeItem(KHOA_DA_TAI); } catch (e) { /* noop */ }
        return;
      }
      console.warn("[javis fresh] đang chạy bản cũ của:", ds.join(", "));
      baoChayBanCu(ds, daThu);
    });
  }

  // Đo SAU khi trang dựng xong: đây là lưới an toàn, không được làm chậm lúc mở app.
  if (document.readyState === "complete") setTimeout(kiemNoiDung, 1200);
  else window.addEventListener("load", function () { setTimeout(kiemNoiDung, 1200); });

  /* Máy chủ được cập nhật trong lúc tab đang mở: số phiên bản đổi, còn trang thì vẫn là
   * trang cũ. Hỏi lại theo nhịp, và hỏi luôn khi người dùng quay lại tab (rất hay là lúc
   * họ vừa bấm cập nhật ở tab khác). */
  var daBao = false;
  function kiemPhienBan() {
    if (daBao || document.hidden) return;
    fetch("/app-version", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.version || d.version === m.version) return;
        daBao = true;
        baoCoBanMoi(d.version);
      })
      .catch(function () { /* mất mạng một nhịp không phải chuyện để làm phiền người dùng */ });
  }

  setInterval(kiemPhienBan, CHU_KY_MS);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) kiemPhienBan();
  });
})();
