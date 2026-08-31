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

  var chatArea = null, boc = null, ray = null, hop = null, tam = null;
  var moc = [];             // [{el, text}]
  var vanTruoc = "";        // chữ ký nội dung, để bỏ qua lượt dựng lại không đổi gì
  var choDung = null, choScroll = 0, choDong = null;

  // Màn hẹp dùng chế độ KHÁC HẲN, không phải dãy vạch thu nhỏ. Dãy vạch sống bằng rê chuột, mà
  // ngón tay không rê được; và một dải chạm sát mép phải thì giành mất cú vuốt để cuộn - hai
  // thứ đó bỏ đi là cả tính năng vô dụng trên điện thoại. Nên ở đây là một nút mở tấm trượt,
  // mỗi dòng đủ to để chạm.
  function hepQua() {
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
    // Ruột để veLai() dựng, vì hai chế độ (máy tính / điện thoại) có cấu trúc khác hẳn nhau.
    // Mấy handler dưới đây chỉ có tác dụng ở chế độ máy tính, nhưng gắn một lần ở đây là đủ:
    // chế độ điện thoại không có node nào khớp nên chúng lặng lẽ không làm gì.
    //
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

  // Đang bôi đen chữ thì ĐỪNG mở danh sách. Hai dấu hiệu, phải xét cả hai:
  //   - `e.buttons` khác 0: chuột đang giữ, tức cú quét còn đang diễn ra.
  //   - vùng chọn hiện có không rỗng: quét xong rồi, người ta đang rê tới nút Copy hoặc chuẩn
  //     bị Ctrl+C; bung một hộp che ngang lúc đó cũng phá đúng thao tác đó.
  // Thiếu bước này thì mọi lần copy một câu cũ đều bị danh sách nhảy ra chắn (báo 2026-08-31).
  function dangBoiDen(e) {
    if (e && typeof e.buttons === "number" && e.buttons !== 0) return true;
    try {
      var sel = window.getSelection();
      return !!(sel && !sel.isCollapsed && String(sel).trim());
    } catch (err) { return false; }
  }

  function moHop(e) {
    clearTimeout(choDong);
    if (dangBoiDen(e)) return;
    if (!hop || !moc.length) return;
    hop.hidden = false;
    // Đưa mục đang đọc vào tầm mắt: hội thoại dài thì danh sách tự cuộn, mở ra mà nó nằm ở
    // đầu danh sách trong khi mình đang ở giữa hội thoại là phải cuộn tay lần nữa.
    var act = hop.querySelector(".cm-muc.active");
    if (act && act.scrollIntoView) {
      try { act.scrollIntoView({ block: "nearest" }); } catch (e) {}
    }
  }
  // Đóng CÓ TRỄ. Hình học ở trên đã bỏ khoảng trống giữa vạch và hộp, nhưng chuột người ta đi
  // không thẳng: vòng ra ngoài mép một chút rồi vào lại là chuyện thường, và nếu đóng ngay thì
  // lần nào cũng hụt. Đây là lớp bảo hiểm thứ hai cho đúng lỗi "hiện xa trỏ nên không trỏ được".
  function dongHop(ngay) {
    clearTimeout(choDong);
    if (ngay) { if (hop) hop.hidden = true; return; }
    choDong = setTimeout(function () { if (hop) hop.hidden = true; }, 220);
  }

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
    dongHop(true);
    dongTam();
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
    // KHÔNG chặn theo `ray`: chế độ điện thoại không có dãy vạch, chặn ở đây là con số "4/9"
    // trên nút đứng im mãi ở lượt dựng đầu tiên - sai mà trông vẫn có vẻ chạy.
    if (!chatArea || !moc.length) return;
    var moc0 = chatArea.getBoundingClientRect().top
      + Math.min(180, chatArea.clientHeight * 0.4);
    var at = 0;
    for (var i = 0; i < moc.length; i++) {
      if (moc[i].el.getBoundingClientRect().top <= moc0) at = i; else break;
    }
    // querySelectorAll(".cm-vach") chứ KHÔNG phải ray.children: hộp danh sách nay cũng là con
    // của ray, nên đếm theo children là lẫn nó vào dãy vạch và chỉ số lệch ngay khi ai đó đổi
    // thứ tự dựng. Chọn theo lớp thì không có cách nào lẫn.
    if (ray) {
      var vach = ray.querySelectorAll(".cm-vach");
      for (var k = 0; k < vach.length; k++) vach[k].classList.toggle("active", k === at);
    }
    // Điện thoại không có dãy vạch để nói "đang ở đâu" bằng hình, nên nút phải nói bằng chữ.
    var so = boc && boc.querySelector(".cm-nut-so");
    if (so) so.textContent = (at + 1) + "/" + moc.length;
    // Tô mục đang đọc ở CẢ hộp rê chuột lẫn tấm trượt - chỉ một trong hai đang sống mỗi lúc.
    var mucs = (boc || document).querySelectorAll(".cm-muc");
    for (var j = 0; j < mucs.length; j++) mucs[j].classList.toggle("active", j === at);
    if (tam) {
      var tm = tam.querySelectorAll(".cm-muc");
      for (var q = 0; q < tm.length; q++) tm[q].classList.toggle("active", q === at);
    }
  }

  function mucHtml() {
    var h = "";
    for (var i = 0; i < moc.length; i++) {
      h += '<button type="button" class="cm-muc" data-cm="' + i + '">'
        + '<span class="cm-so">' + (i + 1) + "</span>" + escHtml(moc[i].text) + "</button>";
    }
    return h;
  }

  function veLai() {
    if (!chatArea) return;
    moc = docMoc();
    if (moc.length < TOI_THIEU) { thaoRa(); return; }
    var hep = hepQua();

    // Đổi chế độ (xoay ngang máy, kéo cửa sổ) phải dựng lại từ đầu: hai chế độ có cấu trúc
    // node khác hẳn nhau, giữ lại bản cũ là còn nguyên dãy vạch trên điện thoại.
    var van = (hep ? "m|" : "d|") + moc.length + "|" + moc.map(function (m) { return m.text; }).join("");
    var daGan = boc && boc.parentNode === chatArea;
    if (van === vanTruoc && daGan) { doCao(); capNhatDangDoc(); return; }
    vanTruoc = van;

    dungBoc();
    if (hep) {
      // ĐIỆN THOẠI: không có chuột để rê nên không có dãy vạch. Một nút nhỏ ở góc trên, chạm
      // vào thì mở tấm trượt lên từ đáy - ngón cái với tới được, và mỗi dòng đủ to để chạm.
      // Nút hiện luôn "đang ở câu mấy trên tổng mấy", thứ mà dãy vạch bên máy tính nói bằng
      // hình thì ở đây phải nói bằng chữ.
      boc.innerHTML = '<button type="button" class="cm-nut" aria-haspopup="dialog">'
        + '<span class="cm-nut-ic" aria-hidden="true"></span>'
        + '<span class="cm-nut-so"></span></button>';
      ray = null; hop = null;
      boc.querySelector(".cm-nut").onclick = moTam;
    } else {
      boc.innerHTML = '<div class="cm-ray" role="navigation" aria-label="Mốc hội thoại"></div>';
      ray = boc.querySelector(".cm-ray");
      var rayHtml = "";
      for (var i = 0; i < moc.length; i++) {
        rayHtml += '<button type="button" class="cm-vach" data-cm="' + i + '" tabindex="-1" '
          + 'aria-label="Câu hỏi ' + (i + 1) + '"></button>';
      }
      // Dựng MỘT LƯỢT cả vạch lẫn hộp: hộp là con của ray nên ghi ray.innerHTML riêng sẽ xoá
      // mất nó, rồi biến `hop` thành con trỏ tới một node đã rời khỏi trang - hover không
      // còn gì để mở, mà nhìn code thì vẫn thấy "có gán hop" nên rất khó soi ra.
      ray.innerHTML = rayHtml + '<div class="cm-hop" hidden>' + mucHtml() + "</div>";
      hop = ray.querySelector(".cm-hop");
      dongTam();   // rời khỏi cỡ điện thoại thì tấm trượt không còn chỗ đứng
    }

    // Chèn LÊN ĐẦU: app.js chèn tin mới vào trước #newMsgBtn nên nó luôn ở cuối; để thanh
    // ở đầu thì hai bên không giành chỗ. Sticky vẫn bám đúng vì phần tử neo theo cả vùng cuộn.
    if (!daGan) chatArea.insertBefore(boc, chatArea.firstChild);
    // Khung chat chừa lề phải cho dải mốc - chỉ khi dải THẬT SỰ đang hiện, và chỉ ở chế độ
    // máy tính (điện thoại là một nút góc trên, không có dải nào để né).
    try { chatArea.classList.toggle("cm-co-thanh", !hepQua()); } catch (e) {}
    doCao();
    capNhatDangDoc();
  }

  // ---- Tấm trượt lên từ đáy (chỉ điện thoại) -------------------------------------------
  // Gắn vào BODY chứ không vào #chatMarks. #chatMarks nằm trong khung chat đang cuộn, mà một
  // lớp phủ toàn màn hình thì phải neo theo MÀN HÌNH; để trong đó là nó cuộn theo nội dung
  // và cái nền mờ chỉ che được đúng phần khung chat. Đổi lại phải tự dọn khi đóng.
  function moTam() {
    dongTam();
    tam = document.createElement("div");
    tam.className = "cm-tam-lop";
    tam.innerHTML = '<div class="cm-tam" role="dialog" aria-label="Câu hỏi trong hội thoại">'
      + '<div class="cm-tam-dau"><b>Câu hỏi trong hội thoại</b>'
      + '<button type="button" class="cm-tam-dong" aria-label="Đóng">\u2715</button></div>'
      + '<div class="cm-tam-ds">' + mucHtml() + "</div></div>";
    document.body.appendChild(tam);
    tam.addEventListener("click", function (e) {
      // Chạm ra ngoài tấm (tức trúng nền mờ) thì đóng - phản xạ ai cũng thử trước khi đi tìm
      // nút X, nhất là khi tay đang cầm máy một tay.
      if (e.target === tam || (e.target.closest && e.target.closest(".cm-tam-dong"))) { dongTam(); return; }
      var n = e.target.closest ? e.target.closest("[data-cm]") : null;
      if (!n) return;
      nhayToi(parseInt(n.getAttribute("data-cm"), 10));
    });
    capNhatDangDoc();
    var act = tam.querySelector(".cm-muc.active");
    if (act && act.scrollIntoView) { try { act.scrollIntoView({ block: "center" }); } catch (e) {} }
  }
  function dongTam() {
    if (tam && tam.parentNode) tam.parentNode.removeChild(tam);
    tam = null;
  }

  function doCao() {
    if (!ray || !chatArea || !moc.length) return;   // chế độ điện thoại không có dãy vạch
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
    dongTam();
    if (boc && boc.parentNode) boc.parentNode.removeChild(boc);
    // Gỡ luôn lề phải: giữ lại là khung chat chừa một khoảng trắng cho một dải không còn ở đó.
    try { if (chatArea) chatArea.classList.remove("cm-co-thanh"); } catch (e) {}
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
    // Trong lúc giữ chuột kéo, dải mốc trong suốt với chuột (xem .cm-dang-chon trong CSS).
    // Nghe ở DOCUMENT chứ không ở chatArea: cú quét thường bắt đầu trong bong bóng rồi đi ra
    // ngoài khung, mà `mouseup` lúc đó rơi ngoài chatArea - nghe hẹp thì class không bao giờ
    // được gỡ và dải mốc chết hẳn, không bấm được nữa.
    document.addEventListener("mousedown", function (e) {
      if (e.button !== 0 || !chatArea) return;
      // Bấm vào chính dải mốc thì KHÔNG phải bôi đen - đó là cú bấm để nhảy về câu cũ.
      if (boc && e.target && boc.contains(e.target)) return;
      chatArea.classList.add("cm-dang-chon");
    }, true);
    document.addEventListener("mouseup", function () {
      if (chatArea) chatArea.classList.remove("cm-dang-chon");
    }, true);
    // Esc đóng tấm trượt. Máy tính bảng có bàn phím rời cũng rơi vào cỡ màn hẹp này, và một
    // lớp phủ toàn màn hình mà không thoát được bằng Esc thì thành cái bẫy.
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && tam) dongTam(); });
    veLai();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", gan);
  else gan();

  window.JavisChatMarks = { refresh: veLai, jump: nhayToi };
})();
