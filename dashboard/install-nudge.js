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
   3. Nói ĐÚNG cách cài của TỪNG trình duyệt. iOS không có nút cài nào để bấm - chỉ vẽ nút
      "Cài" trên Safari là hứa một thứ không tồn tại, nên bên đó phải chỉ đường Chia sẻ →
      Thêm vào MH chính.
*/
(function () {
  "use strict";
  var KEY_LUC = "javis.install.nhac_luc";     // lần nhắc gần nhất (epoch ms)
  var KEY_TAT = "javis.install.tat_nhac";     // "1" = người dùng bảo đừng nhắc nữa
  var MOT_NGAY = 24 * 60 * 60 * 1000;
  var CHO_TRUOC_KHI_HIEN = 12000;             // 12 giây - xem luật 2

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

  function ve() {
    var ios = laIOS();
    var coNutCai = !!(window.JavisInstall && window.JavisInstall.coHopCai());
    var than = ios
      ? '<ol class="inud-buoc">'
        + '<li>Bấm nút <b>Chia sẻ</b> ở thanh dưới của Safari.</li>'
        + '<li>Kéo xuống chọn <b>Thêm vào MH chính</b>.</li>'
        + '<li>Bấm <b>Thêm</b> là xong.</li></ol>'
      : (coNutCai
        ? '<p class="inud-mo">Bấm <b>Cài Javis</b>, trình duyệt sẽ hỏi xác nhận một lần.</p>'
        : '<ol class="inud-buoc">'
          + '<li>Mở <b>menu</b> của trình duyệt (ba chấm ở góc).</li>'
          + '<li>Chọn <b>Thêm vào màn hình chính</b> hoặc <b>Cài ứng dụng</b>.</li></ol>');

    var el = document.createElement("div");
    el.className = "inud-wrap";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", "Thêm Javis vào Màn hình chính");
    el.innerHTML =
      '<div class="inud-nen"></div>'
      + '<div class="inud-hop">'
      + '  <div class="inud-dau">'
      + '    <img class="inud-icon" src="/static/icon-192.png" alt="">'
      + '    <div class="inud-tieude">'
      + '      <b>Thêm Javis vào Màn hình chính</b>'
      + '      <span>Mở nhanh như một app, và <b>nhận được thông báo</b> khi việc chạy nền xong.</span>'
      + '    </div>'
      + '  </div>'
      + than
      + '  <div class="inud-nut">'
      + '    <button type="button" class="inud-tat" id="inudTat">Đừng nhắc nữa</button>'
      + '    <span class="inud-day"></span>'
      + '    <button type="button" class="inud-sau" id="inudSau">Để sau</button>'
      + (coNutCai && !ios ? '    <button type="button" class="inud-cai" id="inudCai">Cài Javis</button>' : "")
      + '  </div>'
      + '</div>';
    document.body.appendChild(el);

    // Ghi mốc NGAY khi hiện, không đợi người dùng bấm gì: đóng bằng cách vuốt / tải lại
    // trang cũng phải tính là "đã nhắc hôm nay", không thì mỗi lần F5 lại bung ra một lần.
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
      if (xong) ghi(KEY_TAT, "1");
    };
    var nen = el.querySelector(".inud-nen");
    if (nen) nen.onclick = function () { dong(el); };
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") { dong(el); document.removeEventListener("keydown", esc); }
    });
  }

  function thu() {
    if (!laDienThoai() || daLaApp() || !denHen()) return;
    if (document.querySelector(".inud-wrap")) return;
    ve();
  }

  // Cài xong thì không bao giờ nhắc nữa, kể cả khi lần sau lỡ mở lại bằng tab trình duyệt.
  window.addEventListener("appinstalled", function () { ghi(KEY_TAT, "1"); });

  function batDau() { setTimeout(thu, CHO_TRUOC_KHI_HIEN); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", batDau);
  else batDau();

  window.JavisInstallNudge = { thu: thu, denHen: denHen, laIOS: laIOS, laDienThoai: laDienThoai };
})();
