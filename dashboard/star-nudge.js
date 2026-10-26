/* star-nudge.js - mời tặng Javis một ngôi sao trên GitHub (0.324.0, chủ repo 25/10/2026).

   Server quyết định CÓ MỜI KHÔNG (server/star_nudge.py: ngưỡng dùng, thời gian chờ, trạng thái
   chung cho mọi thiết bị). File này chỉ lo ba việc:

   1. Báo khoảnh khắc vui cho server, đúng lúc người dùng rảnh tay:
      - heart: vừa thả tim / like một câu trả lời (chat-reactions.js phát `javis:react-positive`).
        Chủ repo: "lần đầu thả tim ấy là lúc dễ add sao nhất".
      - work: việc nền vừa trả kết quả, hay một lượt Javis làm nhiều bước vừa xong (app.js gọi
        JavisStar.moment("work")).
      - load: mở app (server tự xem có cột mốc mới hay bản vừa cập nhật không).
      - manual: người dùng tự bấm nút sao ở góc trái hay trên trang Cập nhật.
   2. Vẽ thẻ mời cho người KHÔNG biết GitHub là gì: một linh vật ngôi sao, lời mời ấm áp, số sao
      thật kèm mốc kế tiếp, và hình minh hoạ chỉ đúng chỗ nút Star (bản máy tính và điện thoại).
   3. Ghi lại lựa chọn: Đã tặng / Để sau / Đừng hỏi nữa / đóng (X).

   Không bao giờ bung lên khi người dùng đang gõ dở hay tab đang ẩn: đợi họ rảnh rồi mới hiện,
   quá lâu thì thôi (lần vui sau sẽ tới).
*/
(function () {
  "use strict";
  var DOI = { heart: 1200, work: 8000, load: 15000, manual: 0 };
  var NGHI_HOI = 30 * 60 * 1000;      // server bảo "chưa" thì 30 phút không hỏi lại cùng lý do
  var lanHoi = {};
  var the = null;                     // thẻ đang mở
  var cho = null;                     // hẹn giờ đang chờ hiện

  function t(k, v) { return window.t ? window.t(k, v) : k; }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  /** Chữ từ từ điển, an toàn: thoát HTML rồi mới đổi **đậm** thành <b>. Từ điển không chứa thẻ
   *  HTML (tests/js/test_i18n.mjs), nên chỗ cần nhấn mạnh viết bằng hai dấu sao. */
  function dam(k, v) { return esc(t(k, v)).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>"); }
  function soDep(n) {
    try { return Number(n).toLocaleString(document.documentElement.lang || "vi"); } catch (e) { return String(n); }
  }
  function ic(ten) { return window.ic ? window.ic(ten) : ""; }
  // Con trỏ chuột vẽ tay: bộ Lucide của app không có icon con trỏ, và emoji thì bị cấm trong
  // giao diện (tests/python/test_icons.py) vì không đổi màu theo tông sáng/tối.
  var CON_TRO = '<svg class="sn-gh-tro" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 3l14 7.5-6.2 1.7L9.6 18z"/></svg>';
  function laDienThoai() {
    try { return window.matchMedia("(max-width: 700px)").matches; } catch (e) { return false; }
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
    }).then(function (r) { return r.json(); }).catch(function () { return null; });
  }

  /** Người dùng đang bận: gõ dở trong ô chat (hay ô nhập nào đó), hoặc không nhìn tab này. */
  function dangBan() {
    if (document.hidden) return true;
    var a = document.activeElement;
    if (a && (a.tagName === "TEXTAREA" || a.tagName === "INPUT" || a.isContentEditable)) {
      if (String(a.value || a.textContent || "").trim()) return true;
    }
    return false;
  }

  // ── Linh vật: đúng ngôi sao cam của logo Javis (dashboard/logo.svg) ─────────────────────
  // Chủ repo 25/10: "lấy sao giống hình icon javis sẵn có". Cùng đường hình, cùng màu thân
  // #FD6100 và viền #FBBA9C với logo; chỉ đổi nét mặt theo từng màn:
  //   vui   - mắt cười ^^ y như logo (màn mời);
  //   mong  - mắt tròn dài như linh vật đang sống, ngước lên chờ (màn "tặng xong chưa");
  //   thuong - mắt hình tim (màn cảm ơn).
  // Sửa hình sao ở logo.svg / pet.js thì sửa luôn ở đây.
  var SAO_JAVIS = "M145 81 Q160 59.4 175 81 L177.9 85.1 Q195.8 110.7 225.8 119.9 L230.6 121.3 Q255.7 128.9 239.8 149.8 "
    + "L236.8 153.8 Q217.9 178.8 218.5 210.1 L218.6 215.1 Q219.1 241.4 194.3 232.8 L189.6 231.1 Q160 220.8 130.4 231.1 "
    + "L125.7 232.8 Q100.9 241.4 101.4 215.1 L101.5 210.1 Q102.1 178.8 83.2 153.8 L80.2 149.8 Q64.3 128.9 89.4 121.3 "
    + "L94.2 119.9 Q124.2 110.7 142.1 85.1 Z";
  function timTai(x, y) {
    return '<path class="sn-tim" transform="translate(' + x + " " + y + ') scale(1.25)" '
      + 'd="M0 9C-3-1-15-1-13 -7C-11.5-12-4-12 0-5C4-12 11.5-12 13-7C15-1 3-1 0 9Z"/>';
  }
  function linhVat(mat) {
    var mat_ = mat === "thuong"
      ? timTai(134.5, 163) + timTai(185.2, 163)
      : mat === "mong"
        ? '<g class="sn-mat"><ellipse cx="141" cy="152" rx="7.2" ry="15"/><ellipse cx="179" cy="152" rx="7.2" ry="15"/></g>'
        : '<path class="sn-cuoi" d="M119.5 168.7 Q134.5 147.1 149.6 168.7 M170.2 168.7 Q185.2 147.1 200.1 168.7"/>';
    return '<svg class="sn-sao" viewBox="36 30 248 248" aria-hidden="true">'
      + '<g class="sn-lap"><path d="M60 70l5 12 12 5-12 5-5 12-5-12-12-5 12-5z"/>'
      + '<path d="M262 56l4 9 9 4-9 4-4 9-4-9-9-4 9-4z"/><path d="M268 214l3.5 8 8 3.5-8 3.5-3.5 8-3.5-8-8-3.5 8-3.5z"/></g>'
      + '<g class="sn-than">'
      + '<path class="sn-vien" d="' + SAO_JAVIS + '" transform="translate(160 160) scale(1.12) translate(-160 -160)"/>'
      + '<path class="sn-hinh" d="' + SAO_JAVIS + '"/>' + mat_ + "</g></svg>";
  }

  // ── Hình minh hoạ: đúng chỗ nút Star trên trang GitHub ───────────────────────────────────
  function minhHoa(n) {
    var so = n != null ? '<span class="sn-gh-so">' + esc(soDep(n)) + "</span>" : "";
    var nutStar = '<span class="sn-gh-star">' + ic("star") + " Star" + so
      + (laDienThoai() ? '<span class="sn-gh-cham" aria-hidden="true"></span>' : CON_TRO) + "</span>";
    if (laDienThoai()) {
      return '<div class="sn-gh sn-gh-dt" aria-hidden="true">'
        + '<div class="sn-gh-ten"><span class="sn-gh-ava"></span>blogminhquy / <b>javis-os</b></div>'
        + '<div class="sn-gh-mota">Javis OS</div>'
        + '<div class="sn-gh-hang">' + nutStar + '<span class="sn-gh-nut">' + ic("git-branch") + " Fork</span></div></div>";
    }
    return '<div class="sn-gh" aria-hidden="true">'
      + '<div class="sn-gh-ten"><span class="sn-gh-ava"></span>blogminhquy / <b>javis-os</b> <span class="sn-gh-pub">Public</span></div>'
      + '<div class="sn-gh-hang"><span class="sn-gh-nut">' + ic("eye") + ' Watch</span><span class="sn-gh-nut">' + ic("git-branch")
      + " Fork</span>" + nutStar + "</div></div>";
  }

  // Khoá viết TRỌN (không ghép chuỗi) để bộ kiểm i18n đọc được từng khoá đang dùng.
  var CHAO = { heart: "star.hi_heart", work: "star.hi_work", update: "star.hi_update", manual: "star.hi_manual" };
  var KY_NIEM = { 30: "star.d30", 100: "star.d100", 365: "star.d365", 730: "star.d730", 1095: "star.d1095" };
  function loiChao(d) {
    if (d.kind === "milestone") return t("star.hi_milestone", { n: soDep(d.n) });
    if (d.kind === "anniversary") return t("star.hi_anniv", { thoi: t(KY_NIEM[d.n] || "star.d30") });
    return t(CHAO[d.kind] || "star.hi_manual");
  }


  function phanSo(c) {
    if (!c || typeof c.stars !== "number") return "";
    var moc = c.milestone, buocTruoc = moc - (moc <= 1000 ? 100 : moc <= 5000 ? 500 : moc <= 20000 ? 1000 : 5000);
    var pt = Math.max(4, Math.min(100, Math.round((c.stars - buocTruoc) / (moc - buocTruoc) * 100)));
    return '<div class="sn-so">'
      + '<div class="sn-so-chu">' + dam("star.count", { n: "**" + soDep(c.stars) + "**", con: "**" + soDep(c.remaining) + "**",
        moc: "**" + soDep(c.milestone) + "**" }) + "</div>"
      + '<div class="sn-thanh" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pt + '">'
      + '<span style="width:' + pt + '%"></span></div></div>';
  }

  function dong(hanhDong) {
    if (!the) return;
    var el = the;
    the = null;
    if (hanhDong) post("/star-nudge/action", { action: hanhDong });
    el.classList.add("sn-di");
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 260);
  }

  function veThe(d) {
    if (the) return;
    var el = document.createElement("div");
    el.className = "sn-wrap";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-labelledby", "snTitle");
    var dt = laDienThoai();
    el.innerHTML =
      '<div class="sn-the">'
      + '<button type="button" class="sn-x" aria-label="' + esc(t("star.close")) + '">' + ic("x") + "</button>"
      + '<div class="sn-trang sn-moi">'
      + '  <div class="sn-dau"><div class="sn-lv">' + linhVat("vui") + "</div>"
      + '    <div><div class="sn-chao">' + esc(loiChao(d)) + "</div>"
      + '    <h3 class="sn-tieude" id="snTitle">' + esc(t("star.title")) + "</h3></div></div>"
      + '  <p class="sn-p">' + dam("star.body1") + "</p>"
      + '  <p class="sn-p">' + dam("star.body2") + "</p>"
      + phanSo(d.count)
      + '  <button type="button" class="sn-go">' + ic("star") + " " + esc(t("star.go")) + "</button>"
      + '  <details class="sn-cach"' + (dt ? "" : " open") + "><summary>" + esc(t("star.how")) + "</summary>"
      + minhHoa(d.count && d.count.stars)
      + '    <ol class="sn-buoc"><li>' + dam("star.step1") + "</li><li>" + dam(dt ? "star.step2_dt" : "star.step2") + "</li><li>" + dam("star.step3") + "</li></ol>"
      + "  </details>"
      + '  <p class="sn-cuoi">' + esc(t("star.thanks_line")) + "</p>"
      + '  <div class="sn-chan"><button type="button" class="sn-sau">' + esc(t("star.later")) + "</button>"
      + '    <button type="button" class="sn-thoi">' + esc(t("star.never")) + "</button></div>"
      + "</div>"
      + '<div class="sn-trang sn-cho" hidden>'
      + '  <div class="sn-dau"><div class="sn-lv">' + linhVat("mong") + "</div>"
      + '    <div><h3 class="sn-tieude">' + esc(t("star.wait_title")) + "</h3></div></div>"
      + '  <p class="sn-p">' + dam("star.wait_body") + "</p>"
      + '  <button type="button" class="sn-xong">' + ic("star") + " " + esc(t("star.done")) + "</button>"
      + '  <div class="sn-chan"><button type="button" class="sn-molai">' + esc(t("star.reopen")) + "</button>"
      + '    <button type="button" class="sn-sau">' + esc(t("star.later")) + "</button></div>"
      + "</div>"
      + '<div class="sn-trang sn-cam" hidden>'
      + '  <div class="sn-phao" aria-hidden="true">' + new Array(13).join("<i>" + ic("star") + "</i>") + "</div>"
      + '  <div class="sn-lv sn-lv-to">' + linhVat("thuong") + "</div>"
      + '  <h3 class="sn-tieude sn-giua">' + esc(t("star.thanks_title")) + "</h3>"
      + '  <p class="sn-p sn-giua">' + esc(t("star.thanks_body")) + "</p>"
      + "</div>"
      + "</div>";
    document.body.appendChild(el);
    the = el;

    var mo = function () {
      try { window.open(d.url || "https://github.com/blogminhquy/javis-os", "_blank", "noopener"); } catch (e) {}
      post("/star-nudge/action", { action: "opened" });
      el.querySelector(".sn-moi").hidden = true;
      el.querySelector(".sn-cho").hidden = false;
    };
    el.querySelector(".sn-go").onclick = mo;
    el.querySelector(".sn-molai").onclick = function () {
      try { window.open(d.url || "https://github.com/blogminhquy/javis-os", "_blank", "noopener"); } catch (e) {}
    };
    el.querySelector(".sn-xong").onclick = function () {
      post("/star-nudge/action", { action: "done" });
      el.querySelector(".sn-cho").hidden = true;
      el.querySelector(".sn-cam").hidden = false;
      el.classList.add("sn-vui");
      var hc = the;
      setTimeout(function () { if (the === hc) dong(null); }, 6000);
    };
    el.querySelectorAll(".sn-sau").forEach(function (b) { b.onclick = function () { dong("later"); }; });
    el.querySelector(".sn-thoi").onclick = function () { dong("never"); };
    el.querySelector(".sn-x").onclick = function () {
      // Đóng ở màn cảm ơn là xong việc rồi; ở hai màn kia là "chưa phải lúc" (hỏi lại sau 3 ngày).
      dong(el.querySelector(".sn-cam").hidden ? (d.kind === "manual" ? null : "dismiss") : null);
    };
    requestAnimationFrame(function () { el.classList.add("sn-hien"); });
  }

  function hoi(lyDo) {
    return post("/star-nudge/check", { reason: lyDo }).then(function (d) {
      if (d && d.ok && d.show) veThe(d);
      else lanHoi[lyDo] = Date.now();
    });
  }

  /** Một khoảnh khắc vui vừa tới. Đợi một nhịp cho người dùng đọc xong, rồi mới hỏi server. */
  function moment(lyDo) {
    if (!DOI.hasOwnProperty(lyDo) || the) return;
    if (lyDo === "manual") { clearTimeout(cho); return hoi("manual"); }
    if (lanHoi[lyDo] && Date.now() - lanHoi[lyDo] < NGHI_HOI) return;
    if (cho) return;                       // đã có một khoảnh khắc đang chờ hiện
    var thu = 0;
    var cb = function () {
      if (the) { cho = null; return; }
      if (dangBan()) {
        if (++thu > 20) { cho = null; return; }    // bận quá lâu (~5 phút): thôi, đợi lần vui sau
        cho = setTimeout(cb, 15000);
        return;
      }
      cho = null;
      hoi(lyDo);
    };
    cho = setTimeout(cb, DOI[lyDo]);
  }

  window.addEventListener("javis:react-positive", function () { moment("heart"); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && the && the.querySelector(".sn-x")) the.querySelector(".sn-x").click(); });

  // Nút "Tặng sao" luôn có sẵn ở chân thanh bên trái: ai muốn tặng sao lúc nào cũng tìm được.
  // Là một HÀNG RIÊNG trải hết bề ngang dưới số phiên bản và nút thu/mở (chủ repo 25/10: nhét
  // vào cột phiên bản thì chữ "Give a star" bị gãy làm hai dòng). Thanh thu gọn chỉ còn ngôi sao.
  function ganNutGoc() {
    var chan = document.querySelector(".rail-foot");
    if (!chan || chan.querySelector(".rf-star")) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "rf-star";
    veNutGoc(b);
    b.onclick = function () { moment("manual"); };
    chan.appendChild(b);
  }
  function veNutGoc(b) {
    b.innerHTML = ic("star") + '<span class="rf-star-chu">' + esc(t("star.rail")) + "</span>";
    b.title = t("star.go");
    b.setAttribute("aria-label", t("star.go"));
  }
  function batDau() {
    ganNutGoc();
    moment("load");
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", batDau);
  else batDau();
  window.addEventListener("javis:i18n", function () {
    var b = document.querySelector(".rf-star");
    if (b) veNutGoc(b);
  });

  /** Thẻ "Ủng hộ Javis" cố định trên trang Cập nhật (console.js gắn nút bấm). */
  function theUngHo() {
    return '<div class="sn-ho"><div class="sn-lv">' + linhVat("vui") + "</div>"
      + '<div class="sn-ho-chu"><b>' + esc(t("star.support_title")) + "</b><span>" + esc(t("star.support_body")) + "</span></div>"
      + '<button type="button" class="sn-go">' + ic("star") + " " + esc(t("star.go")) + "</button></div>";
  }

  window.JavisStar = { moment: moment, open: function () { moment("manual"); }, theUngHo: theUngHo };
})();
