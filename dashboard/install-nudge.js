/* install-nudge.js - nhắc thêm Javis vào Màn hình chính, MỖI NGÀY MỘT LẦN.

   Vì sao cần: trên điện thoại, Javis mở bằng tab trình duyệt và Javis mở bằng app đã cài là
   hai trải nghiệm khác hẳn nhau - và cái khác lớn nhất không nhìn thấy được. iOS CHỈ cho
   nhận thông báo đẩy khi trang đã được "Thêm vào MH chính" (iOS 16.4+). Ai dùng Javis bằng
   Safari thường sẽ không bao giờ nhận được kết quả việc nền, mà cũng không có gì nói cho họ
   biết vì sao. Nút "Mở như app" trên thanh trạng thái chỉ hiện ở trình duyệt có
   beforeinstallprompt (Chrome/Edge), tức là đúng iOS - nơi cần nhất - lại không có nút nào.

   Ba luật giữ cho lời nhắc này không thành phiền phức:

   1. MỘT LẦN MỖI NGÀY, và có nút tắt hẳn. Chủ repo chốt nhịp một ngày (27/08); "Đừng nhắc
      nữa" là lối ra cho người đã quyết định không cài - nhắc mãi một người đã từ chối thì
      họ học cách bấm tắt mà không đọc, và lần có việc thật cũng chịu chung số phận.
   2. Không bung ngay lúc mở trang. Chờ một nhịp để người ta làm xong việc họ vào đây để làm;
      popup đè lên màn hình ở giây đầu tiên là thứ ai cũng đóng theo phản xạ.
      17/11/2026 (chủ repo: "phải vào được màn sử dụng mới hiện chứ vừa mới đăng nhập đã hiện gây
      khó chịu, dùng một chút rồi hãng hiện ra"): 12 giây sau khi mở trang là chưa đủ, nó bung đè
      lên màn đăng nhập và bộ cài đặt lần đầu. Nay chỉ đếm lúc DÙNG THẬT: trang đang hiện, không
      có màn đăng nhập, bộ cài đặt hay hộp nào khác đang mở, và người dùng vừa chạm hay gõ trong
      một phút qua. Đủ 3 phút dùng (cộng dồn qua các lần mở, lưu trong localStorage) mới nhắc, và
      không nhắc giữa lúc đang gõ.
   3. Nói ĐÚNG cách cài của TỪNG trình duyệt. iOS không có nút cài nào để bấm - chỉ vẽ nút
      "Cài" trên Safari là hứa một thứ không tồn tại, nên bên đó phải chỉ đường Chia sẻ →
      Thêm vào MH chính.

   Nút "Cài lên điện thoại" ở chân menu (0.450.0, chủ repo 04/11/2026): lời nhắc mỗi ngày
   một lần thì ai đã bấm "Đừng nhắc nữa" hay lỡ đóng mất sẽ không còn đường nào mở lại hướng
   dẫn. Nút này luôn có trên điện thoại khi Javis CHƯA chạy dạng app, bấm là mở đúng popup ở
   trên. Đã cài (mở từ màn hình chính) thì nút không hiện, cài xong ngay trong phiên thì nút
   tự gỡ. Nút không đọc cờ "Đừng nhắc nữa": cờ đó tắt lời nhắc tự bung, không tắt việc người
   dùng tự đi tìm hướng dẫn.
*/
(function () {
  "use strict";
  var KEY_LUC = "javis.install.nhac_luc";     // lần nhắc gần nhất (epoch ms)
  var KEY_TAT = "javis.install.tat_nhac";     // "1" = người dùng bảo đừng nhắc nữa
  var MOT_NGAY = 24 * 60 * 60 * 1000;
  var KEY_DUNG = "javis.install.da_dung_ms";  // thời gian đã dùng thật, cộng dồn (ms) - xem luật 2
  var CAN_DUNG_MS = 3 * 60 * 1000;            // dùng đủ 3 phút mới nhắc
  var NHIP_MS = 5000;                         // mỗi 5 giây xem một lần
  var CON_DUNG_MS = 60 * 1000;                // chạm hay gõ trong 1 phút qua thì còn tính là đang dùng
  var lucCham = 0;                            // lần chạm/gõ gần nhất trong phiên này

  function doc(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function ghi(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  function daLaApp() {
    try {
      return window.matchMedia("(display-mode: standalone)").matches
        || window.navigator.standalone === true;      // iOS standalone kiểu cũ
    } catch (e) { return false; }
  }
  // iPadOS 13+ khai mình là Mac, chỉ lộ ra qua maxTouchPoints - thiếu nhánh này thì iPad
  // nhận hướng dẫn của Android, tức là chỉ vào một cái menu không có ở đó.
  function laIOS() {
    var ua = navigator.userAgent || "";
    return /iP(hone|ad|od)/.test(ua)
      || (navigator.platform === "MacIntel" && (navigator.maxTouchPoints || 0) > 1);
  }
  function laDienThoai() {
    try {
      return window.matchMedia("(max-width: 860px)").matches
        || window.matchMedia("(pointer: coarse)").matches;
    } catch (e) { return false; }
  }

  function denHen() {
    if (doc(KEY_TAT) === "1") return false;
    var luc = Number(doc(KEY_LUC) || 0);
    return !luc || (Date.now() - luc) >= MOT_NGAY;
  }

  function dong(el) { if (el && el.parentNode) el.parentNode.removeChild(el); }

  function ve(tuMenu) {
    var ios = laIOS();
    var coNutCai = !!(window.JavisInstall && window.JavisInstall.coHopCai());
    var than = ios
      ? '<ol class="inud-buoc">'
        + '<li>' + window.t("instl.ios1_a") + ' <b>' + window.t("instl.ios1_b") + '</b> ' + window.t("instl.ios1_c") + '</li>'
        + '<li>' + window.t("instl.ios2_a") + ' <b>' + window.t("instl.ios2_b") + '</b>.</li>'
        + '<li>' + window.t("instl.tap") + ' <b>' + window.t("instl.ios3_b") + '</b> ' + window.t("instl.ios3_c") + '</li></ol>'
      : (coNutCai
        ? '<p class="inud-mo">' + window.t("instl.tap") + ' <b>' + window.t("instl.cai") + '</b>, ' + window.t("instl.tap_note") + '</p>'
        : '<ol class="inud-buoc">'
          + '<li>' + window.t("instl.menu1_a") + ' <b>menu</b> ' + window.t("instl.menu1_b") + '</li>'
          + '<li>' + window.t("instl.menu2_a") + ' <b>' + window.t("instl.menu2_b") + '</b> ' + window.t("instl.menu2_or") + ' <b>' + window.t("instl.menu2_c") + '</b>.</li></ol>');

    var el = document.createElement("div");
    el.className = "inud-wrap";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", window.t("instl.title"));
    el.innerHTML =
      '<div class="inud-nen"></div>'
      + '<div class="inud-hop">'
      + '  <div class="inud-dau">'
      + '    <img class="inud-icon" src="/static/icon-192.png" alt="">'
      + '    <div class="inud-tieude">'
      + '      <b>' + window.t("instl.title") + '</b>'
      + '      <span>' + window.t("instl.sub_a") + ' <b>' + window.t("instl.sub_b") + '</b> ' + window.t("instl.sub_c") + '</span>'
      + '    </div>'
      + '  </div>'
      + than
      + '  <div class="inud-nut">'
      // Tự bấm mở từ menu thì không cần "Đừng nhắc nữa": người ta đang chủ động hỏi.
      + (tuMenu ? "" : '    <button type="button" class="inud-tat" id="inudTat">' + window.t("instl.tat") + '</button>')
      + '    <span class="inud-day"></span>'
      + '    <button type="button" class="inud-sau" id="inudSau">' + window.t("instl.sau") + '</button>'
      + (coNutCai && !ios ? '    <button type="button" class="inud-cai" id="inudCai">' + window.t("instl.cai") + '</button>' : "")
      + '  </div>'
      + '</div>';
    document.body.appendChild(el);

    // Ghi mốc NGAY khi hiện, không đợi người dùng bấm gì: đóng bằng cách vuốt / tải lại
    // trang cũng phải tính là "đã nhắc hôm nay", không thì mỗi lần F5 lại bung ra một lần.
    // Tự mở từ menu cũng tính: vừa đọc hướng dẫn xong thì lời nhắc tự bung hôm nay là thừa.
    ghi(KEY_LUC, String(Date.now()));

    var sau = el.querySelector("#inudSau");
    var tat = el.querySelector("#inudTat");
    var cai = el.querySelector("#inudCai");
    if (sau) sau.onclick = function () { dong(el); };
    if (tat) tat.onclick = function () { ghi(KEY_TAT, "1"); dong(el); };
    if (cai) cai.onclick = async function () {
      cai.disabled = true;
      var xong = await window.JavisInstall.moHopCai();
      dong(el);
      // Cài xong thì thôi hẳn; từ chối thì mai nhắc lại như thường.
      if (xong) { ghi(KEY_TAT, "1"); goNutMenu(); }
    };
    var nen = el.querySelector(".inud-nen");
    if (nen) nen.onclick = function () { dong(el); };
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") { dong(el); document.removeEventListener("keydown", esc); }
    });
  }

  // Màn đăng nhập, bộ cài đặt lần đầu và mọi hộp .modal-overlay đang mở, hay ngăn kéo menu: chưa phải lúc dùng app.
  function dangBiChe() {
    return !!document.querySelector(".modal-overlay.open") || document.body.classList.contains("nav-open");
  }
  function dangGo() {
    var a = document.activeElement;
    return !!a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.isContentEditable);
  }
  function daDung() { return Number(doc(KEY_DUNG) || 0); }

  // Một nhịp 5 giây: cộng vào thời gian dùng nếu người dùng đang thật sự dùng app, rồi xem đã tới lúc nhắc chưa.
  function nhip() {
    if (!laDienThoai() || daLaApp() || !denHen()) return;
    var dung = document.visibilityState !== "hidden" && !dangBiChe() && lucCham && (Date.now() - lucCham) < CON_DUNG_MS;
    if (dung && daDung() < CAN_DUNG_MS) ghi(KEY_DUNG, String(daDung() + NHIP_MS));
    thu();
  }

  function thu() {
    if (!laDienThoai() || daLaApp() || !denHen()) return;
    if (daDung() < CAN_DUNG_MS || dangBiChe() || dangGo()) return;
    if (document.querySelector(".inud-wrap")) return;
    ve();
  }

  /** Mở hướng dẫn ngay, bỏ qua nhịp mỗi ngày một lần (nút ở menu bấm vào). */
  function moHuongDan() {
    if (daLaApp()) return;
    dong(document.querySelector(".inud-wrap"));
    // Ngăn kéo menu trên điện thoại đang mở thì đóng lại, để hướng dẫn không nằm đè lên nó.
    // Đóng thẳng chứ không bấm hộ nền mờ: nền mờ bỏ qua cú chạm trong 400ms đầu (mobile-chat.js).
    document.body.classList.remove("nav-open");
    var nen = document.getElementById("navBackdrop");
    if (nen) nen.hidden = true;
    ve(true);
  }

  // ---- Nút "Cài lên điện thoại" ở chân menu ----
  function veNutMenu(b) {
    var chu = window.t("instl.rail");
    // A touch tablet or laptop shows this in the 160px computer rail, where "Install on phone" does not fit (owner,
    // 2026-11-09: "nút install app bị vỡ"). CSS shows the short label there and the long one in the phone drawer.
    b.innerHTML = (typeof window.ic === "function" ? window.ic("download") : "")
      + '<span class="rf-install-chu">' + chu + "</span>"
      + '<span class="rf-install-short">' + window.t("instl.rail_short") + "</span>";
    b.title = chu;
    b.setAttribute("aria-label", chu);
  }
  function ganNutMenu() {
    if (!laDienThoai() || daLaApp()) return;
    var chan = document.querySelector(".rail-foot");
    if (!chan || chan.querySelector(".rf-install")) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "rf-install";
    veNutMenu(b);
    b.onclick = moHuongDan;
    // Đứng trên "Tặng sao" nếu nút đó đã có (thứ tự nạp script không được quyết định chỗ đứng).
    chan.insertBefore(b, chan.querySelector(".rf-star"));
  }
  function goNutMenu() { dong(document.querySelector(".rail-foot .rf-install")); }

  // Cài xong thì không bao giờ nhắc nữa, kể cả khi lần sau lỡ mở lại bằng tab trình duyệt.
  window.addEventListener("appinstalled", function () { ghi(KEY_TAT, "1"); goNutMenu(); });
  window.addEventListener("javis:i18n", function () {
    var b = document.querySelector(".rail-foot .rf-install");
    if (b) veNutMenu(b);
  });

  function cham() { lucCham = Date.now(); }
  function batDau() {
    ganNutMenu();
    ["pointerdown", "keydown", "touchstart"].forEach(function (ev) {
      document.addEventListener(ev, cham, { capture: true, passive: true });
    });
    setInterval(nhip, NHIP_MS);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", batDau);
  else batDau();

  window.JavisInstallNudge = { thu: thu, nhip: nhip, moHuongDan: moHuongDan, denHen: denHen, laIOS: laIOS,
    laDienThoai: laDienThoai, dangBiChe: dangBiChe };
})();
