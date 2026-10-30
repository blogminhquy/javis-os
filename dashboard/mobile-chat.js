// Wiring giao diện chat trên điện thoại (mobile-only, <=860px):
//  - dời chip model (#mbOpen + #mbPop) và nút + (#newChatBtn) lên header khi mobile, trả về khi desktop
//  - dời nhóm Hệ thống (chọn brain, đổi tông, loa, dải HỆ THỐNG) vào đáy ngăn kéo
//  - nút + = hội thoại mới (reset) + focus ô nhập
//  - ngăn kéo điều hướng: nút menu mở/đóng, backdrop / Esc / chọn mục thì đóng
//  - rút gọn placeholder ô nhập cho vừa bề ngang điện thoại
(function () {
  function init() {
    var mq = window.matchMedia("(max-width: 860px)");
    var railEl = document.querySelector(".rail");

    // ---- 1) Header mobile: dời chip model + nút + lên header; desktop trả về chỗ cũ ----
    var mbOpen = document.getElementById("mbOpen");
    var mbPop = document.getElementById("mbPop");
    // Since 0.153.0 the model chip lives in the composer's button row (#cpChips); its picker (#mbPop) is a child of the card.
    var chipHost = document.getElementById("cpChips");
    var mbPopHome = mbPop ? mbPop.parentElement : null;
    var headerRoot = document.querySelector(".hud-top");
    var headerCenter = document.querySelector(".hud-center-title");
    var newChatBtn = document.getElementById("newChatBtn");
    var origNewChatParent = newChatBtn ? newChatBtn.parentElement : null;
    var notificationTrigger = document.getElementById("notificationTrigger");
    var origNotificationParent = notificationTrigger ? notificationTrigger.parentElement : null;
    var origNotificationNext = notificationTrigger ? notificationTrigger.nextSibling : null;
    function placeHeader() {
      if (!headerRoot) return;
      if (mq.matches) {
        if (notificationTrigger && notificationTrigger.parentElement !== headerRoot) {
          var navToggle = document.getElementById("navToggle");
          if (navToggle && navToggle.parentElement === headerRoot) headerRoot.insertBefore(notificationTrigger, navToggle.nextSibling);
          else headerRoot.insertBefore(notificationTrigger, headerRoot.firstChild);
        }
        // 0.182.0: back in the header on a phone (0.180.0 had moved it into the composer; the owner found that worse).
        if (mbOpen && mbOpen.parentElement !== headerRoot) {
          if (headerCenter && headerCenter.parentElement === headerRoot) headerRoot.insertBefore(mbOpen, headerCenter.nextSibling);
          else headerRoot.appendChild(mbOpen);
          if (mbPop) headerRoot.insertBefore(mbPop, mbOpen.nextSibling);
        }
        if (newChatBtn && newChatBtn.parentElement !== headerRoot) headerRoot.appendChild(newChatBtn);  // + về cuối header
      } else {
        if (mbOpen && chipHost && mbOpen.parentElement !== chipHost) {
          chipHost.insertBefore(mbOpen, document.getElementById("effBtn"));
          if (mbPop && mbPopHome) mbPopHome.appendChild(mbPop);
        }
        if (newChatBtn && origNewChatParent && newChatBtn.parentElement !== origNewChatParent) origNewChatParent.appendChild(newChatBtn);
        if (notificationTrigger && origNotificationParent && notificationTrigger.parentElement !== origNotificationParent) {
          if (origNotificationNext && origNotificationNext.parentElement === origNotificationParent) {
            origNotificationParent.insertBefore(notificationTrigger, origNotificationNext);
          } else {
            origNotificationParent.appendChild(notificationTrigger);
          }
        }
      }
    }

    // ---- 2) Nhóm Hệ thống: mobile dời vào đáy ngăn kéo, desktop trả về chỗ cũ ----
    var sysHost = null, sysBtns = null, sysLbl = null, moved = [];
    function ensureSysHost() {
      if (sysHost || !railEl) return;
      sysHost = document.createElement("div");
      sysHost.className = "rail-sys";
      sysLbl = document.createElement("div");
      sysLbl.className = "rail-sys-lbl";
      sysLbl.textContent = window.t("nav.group.he_thong");
      sysHost.appendChild(sysLbl);
      sysBtns = document.createElement("div");
      sysBtns.className = "rail-sys-btns";
      sysHost.appendChild(sysBtns);
      var foot = railEl.querySelector(".rail-foot");
      railEl.insertBefore(sysHost, foot || null);
    }
    // `toFoot` (0.393.0, owner): the light/dark switch goes to the drawer's foot, just left of the collapse button,
    // instead of a row of its own under the "System" label.
    function moveEl(el, toBtns, toFoot) {
      if (!el) return;
      ensureSysHost();
      if (!sysHost) return;
      moved.push({ el: el, parent: el.parentElement, next: el.nextSibling });
      var foot = toFoot && railEl && railEl.querySelector(".rail-foot");
      if (foot) foot.insertBefore(el, foot.querySelector(".rail-collapse-btn"));
      else (toBtns ? sysBtns : sysHost).appendChild(el);
    }
    function traVe(m) {
      if (m.next && m.next.parentElement === m.parent) m.parent.insertBefore(m.el, m.next);
      else m.parent.appendChild(m.el);
    }
    // Gỡ hẳn khung "Hệ thống" khỏi rail. PHẢI có hàm này: `ensureSysHost` dựng khung một lần
    // rồi giữ tham chiếu, còn `placeSystem` trước đây chỉ trả các nút về chỗ cũ mà KHÔNG dọn
    // cái khung rỗng. Nên sau một lần đi qua màn hẹp là cái nhãn "Hệ thống" ở lại vĩnh viễn,
    // đứng chình ình trên hàng version mà bên dưới chẳng còn gì (chủ repo báo 01/09: "thi
    // thoảng chữ hệ thống to lại hiện ra trong khi chỗ đó đáng nhẽ là không có gì").
    function boSysHost() {
      if (sysHost && sysHost.parentElement) sysHost.parentElement.removeChild(sysHost);
      sysHost = null; sysBtns = null; sysLbl = null;
    }
    function placeSystem() {
      if (mq.matches) {
        if (!moved.length) {
          moveEl(document.querySelector(".navbar-brain"), false);
          moveEl(document.getElementById("themeToggle"), true, true);
          // Nút loa header đã bỏ (0.48.3), nút loa thanh nhập cũng bỏ (02/09): giọng đi theo
          // mic, bấm mic là bật loa. Không còn nút loa nào để dời cả.
          // Dải "VỪA GỌI" cũng bỏ (0.64.15): bước tool đã hiện ngay trong khung chat.
        }
        // Nhãn không được đứng một mình. Mấy nút mượn nằm trong HUD, mà HUD bị vẽ lại ở vài
        // đường (đổi brain, đổi trang) - lúc đó chúng biến mất khỏi khung này và để lại đúng
        // cái nhãn trơ ra. Còn nút thì giữ, hết nút thì dọn.
        if (sysHost && !sysHost.querySelector(".navbar-brain, #themeToggle")) {
          var cu = moved; moved = [];
          // Whatever still sits in the foot goes home, so the next pass borrows it again from its real place.
          cu.forEach(function (m) { if (m.el.parentElement && m.el.parentElement !== m.parent) traVe(m); });
          boSysHost();
        }
      } else if (moved.length) {
        moved.forEach(traVe);
        moved = [];
        boSysHost();   // trả nút về desktop rồi thì cái khung rỗng cũng phải đi theo
      } else {
        boSysHost();   // desktop mà vẫn còn khung (dựng hụt, hoặc nút bị vẽ lại mất) -> dọn
      }
    }

    // ---- 3) Placeholder ngắn cho ô nhập trên mobile ----
    // Cả hai chuỗi đều TRA TỪ ĐIỂN lúc vẽ. Bản trước CHỤP placeholder từ DOM một lần lúc
    // khởi tạo, mà lúc đó applyDom() của i18n chưa chạy, nên cái chụp được luôn là chuỗi
    // tiếng Việt viết cứng trong index.html - chọn tiếng Anh thì ô nhập trên màn rộng vẫn
    // nói tiếng Việt. Từ điển về sau DOMContentLoaded nên còn phải vẽ lại ở "javis:i18n".
    var chatInput = document.getElementById("chatInput");
    function setPlaceholder() {
      if (!chatInput) return;
      var khoa = mq.matches ? "mchat.input_ph_short" : "bar.input_ph";
      var chu = window.t(khoa);
      // t() trả về CHÍNH cái khoá khi từ điển chưa về (hoặc thiếu khoá). Ghi đè lúc đó là
      // in "bar.input_ph" vào ô nhập, tệ hơn hẳn chuỗi tiếng Việt sẵn trong HTML. Bỏ qua,
      // lượt "javis:i18n" bên dưới sẽ vẽ lại bằng chữ thật.
      if (chu === khoa) return;
      chatInput.setAttribute("placeholder", chu);
    }

    // ---- 4) Nút + = hội thoại mới (reset) + focus ô nhập cho phản hồi tức thì ----
    var reset = document.getElementById("resetBtn");
    if (newChatBtn && reset) newChatBtn.addEventListener("click", function () {
      reset.click();
      if (chatInput) { try { chatInput.focus(); } catch (e) {} }
    });

    // ---- 5) Ngăn kéo điều hướng ----
    var toggle = document.getElementById("navToggle");
    var backdrop = document.getElementById("navBackdrop");
    // 0.216.0: một lần chạm trên điện thoại có thể tới thành HAI cú bấm (iPhone), cú thứ hai rơi đúng vào nút menu hoặc
    // nền mờ vừa hiện ra và đóng ngay ngăn kéo vừa mở. Bỏ qua lệnh đóng bằng chạm trong NGAN_DONG ms sau khi mở.
    var NGAN_DONG = 400, moLuc = 0;
    function openNav() { document.body.classList.add("nav-open"); if (backdrop) backdrop.hidden = false; moLuc = Date.now(); }
    function closeNav() { document.body.classList.remove("nav-open"); if (backdrop) backdrop.hidden = true; }
    function closeByTap() { if (Date.now() - moLuc >= NGAN_DONG) closeNav(); }
    if (toggle) toggle.addEventListener("click", function () {
      document.body.classList.contains("nav-open") ? closeByTap() : openNav();
    });
    if (backdrop) backdrop.addEventListener("click", closeByTap);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeNav(); });
    if (railEl) railEl.addEventListener("click", function (e) {
      if (e.target.closest(".rail-item") && mq.matches) closeNav();  // chọn mục điều hướng -> đóng
    });

    // ---- 6) Bung/thu khoang não (mobile-only) ----
    // Khoang não trên điện thoại chỉ cao hơn 200px một chút. Kể cả sau khi đã siết lề canh
    // khung, thu nhỏ nhãn và làm mỏng dải số liệu, chừng đó vẫn không phải chỗ để NHÌN một
    // đồ thị - đây mới là câu trả lời cho "não bé quá không thấy gì".
    // Bung xong phải gọi refit(): canvas vừa đổi kích thước, mà mức zoom hiện tại là mức
    // canh cho khung CŨ, giữ nguyên là đồ thị vẫn bé y như lúc chưa bung.
    var brainMaxBtn = document.getElementById("brainMaxBtn");
    function refitGraph(delay) {
      setTimeout(function () {
        try {
          var g = window.__javisGraph;
          if (g && typeof g.refit === "function") g.refit(360);
          else if (g && typeof g.resize === "function") g.resize();
        } catch (e) {}
      }, delay || 60);
    }
    function setBrainMax(on) {
      document.body.classList.toggle("brain-max", !!on);
      if (brainMaxBtn) {
        brainMaxBtn.setAttribute("aria-pressed", on ? "true" : "false");
        brainMaxBtn.title = on ? window.t("mchat.brain_min_title")
                               : window.t("orb.max_title");
      }
      refitGraph(340);   // đợi hết hoạt ảnh đổi layout rồi mới đo lại
    }
    if (brainMaxBtn) brainMaxBtn.addEventListener("click", function () {
      setBrainMax(!document.body.classList.contains("brain-max"));
    });
    // Về desktop (xoay máy, đổi cửa sổ) thì trạng thái bung không còn nghĩa gì: khoang não
    // vốn đã là cả cột giữa. Bỏ cờ đi kẻo khung chat biến mất trên màn rộng.
    function syncBrainMax() {
      if (!mq.matches && document.body.classList.contains("brain-max")) setBrainMax(false);
    }

    // ---- 7) Bàn phím ảo: khung chat bám đúng phần màn hình còn nhìn thấy ----
    // Chủ repo báo 27/09 (kèm ảnh so với app Claude và Telegram): gõ trên điện thoại thì ô
    // nhập đứng cách bàn phím một khoảng trống to. Nguyên nhân: ô nhập luôn chừa lề đáy bằng
    // safe-area-inset-bottom (34px trên iPhone có vạch Home), mà lúc bàn phím mở thì vạch Home
    // nằm DƯỚI bàn phím, chừa nữa là chừa cho khoảng không. Cộng thêm iOS không co 100dvh theo
    // bàn phím mà trượt cả trang lên, nên phần đáy trang lộ ra dưới ô nhập.
    // Cách sửa: đo visualViewport (phần thật sự nhìn thấy), gắn lớp `kb-open` lên body, rồi
    // CSS đặt khung chat đúng bằng vùng đó và bỏ lề an toàn. Nhận ra bàn phím bằng cách so với
    // chiều cao lúc KHÔNG gõ (mốc), vì trên iOS innerHeight không đổi còn trên Android (có
    // interactive-widget=resizes-content) thì innerHeight co theo, so với nó là không thấy gì.
    // 0.359.0 (PR #850 của hwangrin, iPhone cài như app): lúc KHÔNG gõ, 100dvh của iOS standalone có khi lệch với phần
    // màn hình thật sự nhìn thấy (đầu khung chat bị hụt, dưới ô nhập thừa một dải trống). Khung chat lúc nghỉ dùng đúng
    // chiều cao visualViewport (`--app-h`, chỉ chiều cao, không cộng độ lệch: không có bàn phím thì vùng nhìn thấy bắt
    // đầu từ mép trên), và bàn phím hạ xuống mà iOS để trang trượt lên thì kéo trang về đầu. Giữ nguyên thanh trạng
    // thái trong suốt (black-translucent) nên giao diện không đổi.
    var vv = window.visualViewport;
    var rootStyle = document.documentElement.style;
    var mocCao = 0, kbHen = 0, vuaGo = false, vuaMo = false;
    function dangGo() {
      var a = document.activeElement;
      if (!a || a === document.body) return false;
      var tag = (a.tagName || "").toLowerCase();
      if (tag === "textarea" || a.isContentEditable) return true;
      if (tag !== "input") return false;
      return !/^(button|checkbox|radio|range|color|file|submit|reset|image|hidden)$/i.test(a.type || "");
    }
    function syncKeyboard() {
      kbHen = 0;
      if (!vv) return;
      var go = dangGo();
      if (!go || !mocCao) mocCao = Math.max(go ? mocCao : 0, vv.height);
      var mo = mq.matches && go && mocCao - vv.height > 120;
      document.body.classList.toggle("kb-open", mo);
      if (mo) {
        rootStyle.setProperty("--vv-h", Math.round(vv.height) + "px");
        rootStyle.setProperty("--vv-top", Math.max(0, Math.round(vv.offsetTop)) + "px");
        rootStyle.setProperty("--vv-ptop", Math.max(0, Math.round(vv.pageTop)) + "px");
      } else {
        rootStyle.removeProperty("--vv-h");
        rootStyle.removeProperty("--vv-top");
        rootStyle.removeProperty("--vv-ptop");
      }
      if (mq.matches && !go && Math.abs((vv.scale || 1) - 1) < 0.01 && vv.height > 200) {
        rootStyle.setProperty("--app-h", Math.round(vv.height) + "px");
        // Bàn phím vừa hạ: trang (vốn không cuộn được) bị iOS để trượt lên, đầu khung chat nằm khuất trên mép màn.
        if (vuaGo && (window.scrollY || document.documentElement.scrollTop)) window.scrollTo(0, 0);
      } else if (!mq.matches) {
        rootStyle.removeProperty("--app-h");
      }
      // 0.409.0: the keyboard can also go down while the box KEEPS its focus (it turned read-only for dictation). The
      // page is still slid up then, and on a slid page iOS hit-tests the fixed chat layer away from where it draws it:
      // taps on the dictation bar's X and stop landed on the text box (owner's iPhone, 2026-10-30). Slide it back.
      if (mq.matches && vuaMo && !mo && (window.scrollY || document.documentElement.scrollTop)) window.scrollTo(0, 0);
      vuaMo = mo;
      vuaGo = go;
    }
    function henKeyboard() {
      if (!kbHen) kbHen = (window.requestAnimationFrame || setTimeout)(syncKeyboard);
    }
    if (vv) {
      vv.addEventListener("resize", henKeyboard);
      vv.addEventListener("scroll", henKeyboard);
      document.addEventListener("focusin", henKeyboard);
      // Blur xong bàn phím còn đang hạ xuống; đo ngay thì vẫn thấy cao cũ. Đo thêm một nhịp muộn.
      document.addEventListener("focusout", function () { henKeyboard(); setTimeout(syncKeyboard, 350); });
      window.addEventListener("orientationchange", function () { mocCao = 0; setTimeout(syncKeyboard, 400); });
    }

    function applyAll() { placeHeader(); placeSystem(); setPlaceholder(); syncBrainMax(); syncKeyboard(); }
    applyAll();

    // Từ điển nạp bất đồng bộ (i18n/index.js fetch xong mới bắn "javis:i18n"), nên mọi chữ
    // vẽ bằng window.t() ở trên đều chạy TRƯỚC khi có từ điển. Vẽ lại đúng những chỗ đó.
    window.addEventListener("javis:i18n", function () {
      setPlaceholder();
      if (sysLbl) sysLbl.textContent = window.t("nav.group.he_thong");
      if (brainMaxBtn) {
        var dangBung = document.body.classList.contains("brain-max");
        brainMaxBtn.title = dangBung ? window.t("mchat.brain_min_title") : window.t("orb.max_title");
      }
    });

    // Chỉ đóng ngăn kéo khi THẬT SỰ sang màn rộng: trên màn rộng nó không phải ngăn kéo nữa.
    var onChange = function () { applyAll(); if (!mq.matches) closeNav(); };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
