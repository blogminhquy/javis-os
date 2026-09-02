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
    var modelBar = document.getElementById("modelBar");
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
        if (mbOpen && mbOpen.parentElement !== headerRoot) {
          if (headerCenter && headerCenter.parentElement === headerRoot) headerRoot.insertBefore(mbOpen, headerCenter.nextSibling);
          else headerRoot.appendChild(mbOpen);
          if (mbPop) headerRoot.insertBefore(mbPop, mbOpen.nextSibling);
        }
        if (newChatBtn && newChatBtn.parentElement !== headerRoot) headerRoot.appendChild(newChatBtn);  // + về cuối header
      } else {
        if (mbOpen && modelBar && mbOpen.parentElement !== modelBar) {
          modelBar.insertBefore(mbOpen, modelBar.firstChild);
          if (mbPop) modelBar.insertBefore(mbPop, mbOpen.nextSibling);
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
    var sysHost = null, sysBtns = null, moved = [];
    function ensureSysHost() {
      if (sysHost || !railEl) return;
      sysHost = document.createElement("div");
      sysHost.className = "rail-sys";
      var lbl = document.createElement("div");
      lbl.className = "rail-sys-lbl";
      lbl.textContent = "Hệ thống";
      sysHost.appendChild(lbl);
      sysBtns = document.createElement("div");
      sysBtns.className = "rail-sys-btns";
      sysHost.appendChild(sysBtns);
      var foot = railEl.querySelector(".rail-foot");
      railEl.insertBefore(sysHost, foot || null);
    }
    function moveEl(el, toBtns) {
      if (!el) return;
      ensureSysHost();
      if (!sysHost) return;
      moved.push({ el: el, parent: el.parentElement, next: el.nextSibling });
      (toBtns ? sysBtns : sysHost).appendChild(el);
    }
    // Gỡ hẳn khung "Hệ thống" khỏi rail. PHẢI có hàm này: `ensureSysHost` dựng khung một lần
    // rồi giữ tham chiếu, còn `placeSystem` trước đây chỉ trả các nút về chỗ cũ mà KHÔNG dọn
    // cái khung rỗng. Nên sau một lần đi qua màn hẹp là cái nhãn "Hệ thống" ở lại vĩnh viễn,
    // đứng chình ình trên hàng version mà bên dưới chẳng còn gì (chủ repo báo 01/09: "thi
    // thoảng chữ hệ thống to lại hiện ra trong khi chỗ đó đáng nhẽ là không có gì").
    function boSysHost() {
      if (sysHost && sysHost.parentElement) sysHost.parentElement.removeChild(sysHost);
      sysHost = null; sysBtns = null;
    }
    function placeSystem() {
      if (mq.matches) {
        if (!moved.length) {
          moveEl(document.querySelector(".navbar-brain"), false);
          moveEl(document.getElementById("themeToggle"), true);
          // Nút loa header đã bỏ (0.48.3), nút loa thanh nhập cũng bỏ (02/09): giọng đi theo
          // mic, bấm mic là bật loa. Không còn nút loa nào để dời cả.
          moveEl(document.getElementById("sysBar"), false);
        }
        // Nhãn không được đứng một mình. Mấy nút mượn nằm trong HUD, mà HUD bị vẽ lại ở vài
        // đường (đổi brain, đổi trang) - lúc đó chúng biến mất khỏi khung này và để lại đúng
        // cái nhãn trơ ra. Còn nút thì giữ, hết nút thì dọn.
        if (sysHost && !sysHost.querySelector(".navbar-brain, #themeToggle, #sysBar")) {
          moved = [];
          boSysHost();
        }
      } else if (moved.length) {
        moved.forEach(function (m) {
          if (m.next && m.next.parentElement === m.parent) m.parent.insertBefore(m.el, m.next);
          else m.parent.appendChild(m.el);
        });
        moved = [];
        boSysHost();   // trả nút về desktop rồi thì cái khung rỗng cũng phải đi theo
      } else {
        boSysHost();   // desktop mà vẫn còn khung (dựng hụt, hoặc nút bị vẽ lại mất) -> dọn
      }
    }

    // ---- 3) Placeholder ngắn cho ô nhập trên mobile ----
    var chatInput = document.getElementById("chatInput");
    var longPh = chatInput ? chatInput.getAttribute("placeholder") : "";
    function setPlaceholder() {
      if (chatInput) chatInput.setAttribute("placeholder", mq.matches ? "Nói hoặc gõ cho Javis…" : longPh);
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
    function openNav() { document.body.classList.add("nav-open"); if (backdrop) backdrop.hidden = false; }
    function closeNav() { document.body.classList.remove("nav-open"); if (backdrop) backdrop.hidden = true; }
    if (toggle) toggle.addEventListener("click", function () {
      document.body.classList.contains("nav-open") ? closeNav() : openNav();
    });
    if (backdrop) backdrop.addEventListener("click", closeNav);
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
        brainMaxBtn.title = on ? "Thu khoang não về khung nhỏ"
                               : "Bung khoang não ra toàn màn để nhìn rõ đồ thị";
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

    function applyAll() { placeHeader(); placeSystem(); setPlaceholder(); syncBrainMax(); }
    applyAll();

    var onChange = function () { applyAll(); closeNav(); };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
