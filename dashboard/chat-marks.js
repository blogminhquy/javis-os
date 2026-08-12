/* chat-marks.js - thanh mốc hội thoại: nhảy nhanh về một câu hỏi cũ trong khung chat.
 *
 * Người dùng Trưng Minh đề nghị qua chủ repo (2026-08-12): quen ChatGPT, ở đó cột phải có một
 * dãy vạch nhỏ, mỗi vạch là một câu mình đã hỏi; rê vào thì hiện danh sách để nhảy thẳng về
 * prompt cũ. Hội thoại dài mà thiếu cái này thì tìm lại một câu hỏi cũ phải kéo tay cả khung.
 *
 * BA QUYẾT ĐỊNH KIẾN TRÚC, ghi ở đây vì mỗi cái đều có cách làm sai trông hợp lý hơn:
 *
 * 1. KHÔNG sửa app.js. Module tự theo dõi #chatArea bằng MutationObserver rồi dựng lại thanh
 *    mốc. Đi hook vào appendUserMessage / lúc nạp hội thoại cũ / lúc xoá chat là ba chỗ, và
 *    chỗ thứ tư sinh ra sau này sẽ không ai nhớ hook. Quan sát KẾT QUẢ thì không sót đường nào.
 *
 * 2. Thanh nằm TRONG #chatArea, position:sticky - không phải position:fixed tính theo toạ độ.
 *    #chatArea bị DI CHUYỂN qua lại giữa màn chính và trang Trò chuyện (console.js mượn node).
 *    Là con của nó thì thanh đi theo, khỏi phải dựng lại; là lớp fixed thì phải tự dò xem khung
 *    chat vừa nhảy đi đâu, mà nhịp dò với nhịp chuyển trang không bao giờ khớp hẳn.
 *
 * 3. Chèn LƯỜI, và gỡ ra khi không đủ mốc. `.transcript:empty::after` là câu mời "Nói hoặc gõ
 *    để bắt đầu" - chèn một node con thường trực là #chatArea không còn :empty và câu đó biến
 *    mất im lặng. Đây là cái bẫy đã ghi sẵn trong app.js cho #newMsgBtn; giẫm lại thì phí.
 */
(function () {
  "use strict";

  var TOI_THIEU = 2;        // 1 câu hỏi thì không có gì để "nhảy về" - đừng bày thanh ra
  var CACH_TOI_DA = 11;     // khoảng cách giữa hai vạch (px) khi còn rộng chỗ
  var CACH_TOI_THIEU = 4;   // hội thoại dài thì nén lại, dưới mức này vạch dính vào nhau
  var HEP = 860;            // khớp mốc màn hẹp của trang Trò chuyện (console.js)
  var DAI_XEM_TRUOC = 70;   // số ký tự hiện trong danh sách

  var chatArea = null, boc = null, ray = null, hop = null;
  var moc = [];             // [{el, text}]
  var vanTruoc = "";        // chữ ký nội dung, để bỏ qua lượt dựng lại không đổi gì
  var choDung = null, choScroll = 0;

  function hepQua() {
    // Màn hẹp KHÔNG có thanh này. Khung chat trên điện thoại đã chật, mà thao tác chính của
    // thanh là RÊ CHUỘT - ngón tay không rê được, còn chạm sát mép phải thì giành mất cú vuốt
    // để cuộn. Thà không có còn hơn có mà cướp thao tác cuộn.
    try { return window.innerWidth < HEP; } catch (e) { return false; }
  }

  function gonChu(s) {
    s = String(s == null ? "" : s).replace(/\s+/g, " ").trim();
    return s.length > DAI_XEM_TRUOC ? s.slice(0, DAI_XEM_TRUOC - 1) + "…" : s;
  }

  function docMoc() {
    var ds = [];
    if (!chatArea) return ds;
    var els = chatArea.querySelectorAll(".msg-user");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      // dataset.text là nguyên văn user gõ (app.js giữ lại để gửi lại / sửa lại). Rơi về chữ
      // hiện trên bong bóng khi thiếu, vd tin dựng từ đường khác.
      var t = el.dataset && el.dataset.text != null ? el.dataset.text : el.textContent;
      t = gonChu(t);
      if (!t) t = "(chỉ có tệp đính kèm)";
      ds.push({ el: el, text: t });
    }
    return ds;
  }

  function dungBoc() {
    if (boc) return boc;
    boc = document.createElement("div");
    boc.id = "chatMarks";
    boc.innerHTML = '<div class="cm-ray" role="navigation" aria-label="Mốc hội thoại"></div>'
      + '<div class="cm-hop" hidden></div>';
    ray = boc.querySelector(".cm-ray");
    hop = boc.querySelector(".cm-hop");
    // Rê vào bất kỳ đâu trong khối thì mở danh sách; rời ra thì đóng. Nghe ở KHỐI BỌC chứ
    // không ở riêng thanh: chuột đi từ thanh sang danh sách phải được coi là vẫn ở trong.
    boc.addEventListener("mouseenter", moHop);
    boc.addEventListener("mouseleave", dongHop);
    boc.addEventListener("focusin", moHop);
    boc.addEventListener("focusout", function (e) {
      if (!boc.contains(e.relatedTarget)) dongHop();
    });
    boc.addEventListener("click", function (e) {
      var n = e.target.closest ? e.target.closest("[data-cm]") : null;
      if (!n) return;
      e.preventDefault();
      nhayToi(parseInt(n.getAttribute("data-cm"), 10));
    });
    return boc;
  }

  function moHop() {
    if (!hop || !moc.length) return;
    hop.hidden = false;
    // Đưa mục đang đọc vào tầm mắt: hội thoại dài thì danh sách tự cuộn, mở ra mà nó nằm ở
    // đầu danh sách trong khi mình đang ở giữa hội thoại là phải cuộn tay lần nữa.
    var act = hop.querySelector(".cm-muc.active");
    if (act && act.scrollIntoView) {
      try { act.scrollIntoView({ block: "nearest" }); } catch (e) {}
    }
  }
  function dongHop() { if (hop) hop.hidden = true; }

  function nhayToi(i) {
    var m = moc[i];
    if (!m || !chatArea) return;
    // Tính bằng hiệu hai getBoundingClientRect chứ KHÔNG dùng offsetTop: offsetTop đo theo
    // offsetParent, mà #chatArea bị dời qua lại giữa hai trang nên offsetParent đổi theo. Hiệu
    // rect thì đúng ở mọi chỗ đứng.
    var d = m.el.getBoundingClientRect().top - chatArea.getBoundingClientRect().top;
    var toi = chatArea.scrollTop + d - 12;
    try { chatArea.scrollTo({ top: toi, behavior: "smooth" }); }
    catch (e) { chatArea.scrollTop = toi; }
    dongHop();
    m.el.classList.add("cm-vua-nhay");
    setTimeout(function () { m.el.classList.remove("cm-vua-nhay"); }, 1200);
  }

  // Vạch nào đang đọc: câu hỏi CUỐI CÙNG nằm trên đường ngắm.
  //
  // Đường ngắm KHÔNG đặt sát mép trên. Đo thật trong Chromium: để ở mép thì màn hình đã hiện
  // rõ câu hỏi 4 cùng câu trả lời của nó mà thanh vẫn sáng vạch 3, chỉ vì đoạn đuôi của trả
  // lời 3 còn sót vài chục pixel trên đỉnh. Nhìn là thấy sai. Hạ đường ngắm xuống một khoảng
  // thì vạch sáng khớp với phần đang CHIẾM màn hình. Chặn trần 180px để hội thoại có câu trả
  // lời ngắn không bị nhảy vọt qua hai ba câu một lúc.
  function capNhatDangDoc() {
    if (!chatArea || !moc.length || !ray) return;
    var moc0 = chatArea.getBoundingClientRect().top
      + Math.min(180, chatArea.clientHeight * 0.4);
    var at = 0;
    for (var i = 0; i < moc.length; i++) {
      if (moc[i].el.getBoundingClientRect().top <= moc0) at = i; else break;
    }
    var vach = ray.children, mucs = hop ? hop.children : [];
    for (var k = 0; k < vach.length; k++) vach[k].classList.toggle("active", k === at);
    for (var j = 0; j < mucs.length; j++) mucs[j].classList.toggle("active", j === at);
  }

  function veLai() {
    if (!chatArea) return;
    if (hepQua()) { thaoRa(); return; }
    moc = docMoc();
    if (moc.length < TOI_THIEU) { thaoRa(); return; }

    var van = moc.length + "|" + moc.map(function (m) { return m.text; }).join("");
    var daGan = boc && boc.parentNode === chatArea;
    if (van === vanTruoc && daGan) { doCao(); capNhatDangDoc(); return; }
    vanTruoc = van;

    dungBoc();
    var rayHtml = "", hopHtml = "";
    for (var i = 0; i < moc.length; i++) {
      rayHtml += '<button type="button" class="cm-vach" data-cm="' + i + '" tabindex="-1" '
        + 'aria-label="Câu hỏi ' + (i + 1) + '"></button>';
      hopHtml += '<button type="button" class="cm-muc" data-cm="' + i + '">'
        + escHtml(moc[i].text) + "</button>";
    }
    ray.innerHTML = rayHtml;
    hop.innerHTML = hopHtml;

    // Chèn LÊN ĐẦU: app.js chèn tin mới vào trước #newMsgBtn nên nó luôn ở cuối; để thanh ở
    // đầu thì hai bên không giành chỗ. Sticky vẫn bám đúng vì phần tử neo theo cả vùng cuộn.
    if (!daGan) chatArea.insertBefore(boc, chatArea.firstChild);
    doCao();
    capNhatDangDoc();
  }

  function doCao() {
    if (!ray || !chatArea || !moc.length) return;
    var caoKhung = chatArea.clientHeight;
    ray.style.height = caoKhung + "px";
    // Khoảng cách giữa hai vạch: rộng thì để thoáng, hội thoại dài thì nén dần. Chạm sàn thì
    // thôi không nén nữa - vạch dính vào nhau chỉ còn là hình trang trí, và LÚC ĐÓ danh sách
    // rê chuột mới là đường đi thật, nên nó có thanh cuộn riêng.
    var cho = Math.max(0, caoKhung - 48);
    var cach = moc.length > 1 ? cho / (moc.length - 1) : CACH_TOI_DA;
    cach = Math.max(CACH_TOI_THIEU, Math.min(CACH_TOI_DA, cach));
    ray.style.setProperty("--cm-cach", cach + "px");
  }

  function thaoRa() {
    if (boc && boc.parentNode) boc.parentNode.removeChild(boc);
    vanTruoc = "";
    moc = [];
  }

  function escHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function hen() {
    clearTimeout(choDung);
    choDung = setTimeout(veLai, 120);
  }

  function gan() {
    chatArea = document.getElementById("chatArea");
    if (!chatArea) return;
    // childList thôi, KHÔNG subtree: lúc Javis trả lời, nội dung bong bóng vẽ lại liên tục
    // theo từng chữ. Nghe subtree là dựng lại thanh mốc hàng chục lần mỗi câu trả lời, trong
    // khi số câu HỎI có đổi gì đâu.
    try {
      new MutationObserver(hen).observe(chatArea, { childList: true });
    } catch (e) {}
    chatArea.addEventListener("scroll", function () {
      if (choScroll) return;
      choScroll = requestAnimationFrame(function () { choScroll = 0; capNhatDangDoc(); });
    }, { passive: true });
    window.addEventListener("resize", hen);
    veLai();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", gan);
  else gan();

  window.JavisChatMarks = { refresh: veLai, jump: nhayToi };
})();
