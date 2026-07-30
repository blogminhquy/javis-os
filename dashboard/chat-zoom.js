/* chat-zoom.js - phóng to khung chat thành CHAT WORKSPACE (kiểu Claude/Cowork):
   gần full màn hình, 2 cột = sidebar Lịch sử trái (sessions-ui.js render qua
   window.JavisChatSide) + cột chat chính. Di chuyển CHÍNH các node #chatArea +
   #attachBar + #modelBar + #hudVoice vào lớp nổi (giữ nguyên mọi handler đã gắn), Esc hoặc
   nút đóng để thu nhỏ. Tách riêng để không đụng app.js. */
(function () {
  "use strict";
  var stage = null, expanded = false, slots = [];
  var SIDE_KEY = "javis.chatside.v1";   // "on" | "off" (desktop nhớ lựa chọn)

  function sideDefaultOn() {
    var saved = "";
    try { saved = localStorage.getItem(SIDE_KEY) || ""; } catch (e) {}
    if (window.innerWidth < 900) return false;          // màn hẹp: mặc định ẩn (drawer)
    return saved !== "off";
  }

  function setSide(on, remember) {
    if (!stage) return;
    stage.classList.toggle("side-on", !!on);
    var t = stage.querySelector(".cs-side-toggle");
    if (t) t.classList.toggle("active", !!on);
    if (remember && window.innerWidth >= 900) {
      try { localStorage.setItem(SIDE_KEY, on ? "on" : "off"); } catch (e) {}
    }
    if (on && window.JavisChatSide) window.JavisChatSide.refresh();
  }

  function ensureStage() {
    if (stage) return stage;
    stage = document.createElement("div");
    stage.className = "chat-stage";
    stage.innerHTML =
      '<div class="chat-stage-head">' +
      '<span class="cs-actions">' +
      '<button class="cs-side-toggle" type="button" title="Ẩn/hiện lịch sử hội thoại">' + ic("history") + ' Lịch sử</button>' +
      '</span>' +
      '<span>HỘI THOẠI</span>' +
      '<button class="chat-stage-close" type="button">' + ic("x") + ' Thu nhỏ (Esc)</button></div>' +
      '<div class="chat-stage-main">' +
      '<aside class="chat-side" id="chatSide"></aside>' +
      '<div class="chat-stage-body"></div>' +
      '</div>';
    document.body.appendChild(stage);
    stage.querySelector(".chat-stage-close").addEventListener("click", collapse);
    stage.querySelector(".cs-side-toggle").addEventListener("click", function () {
      setSide(!stage.classList.contains("side-on"), true);
    });
    // Màn hẹp: sidebar là drawer nổi → bấm ra vùng chat thì tự đóng
    stage.querySelector(".chat-stage-body").addEventListener("click", function () {
      if (window.innerWidth < 900 && stage.classList.contains("side-on")) setSide(false);
    });
    if (window.JavisChatSide) window.JavisChatSide.mount(stage.querySelector("#chatSide"));
    return stage;
  }

  // Đo ĐÚNG khung nội dung rồi bơm vào 4 biến CSS. Không hardcode vì khung này co giãn theo
  // ba thứ: rail trái (thu còn 60px, hoặc 0 ở mobile), chiều cao thanh top, và cỡ cửa sổ.
  // Đo .hud thay vì cộng trừ var(--rail-w): .hud đã mang sẵn margin/width do rail đẩy, và khi
  // trang KHÔNG có rail (body thiếu .has-rail) thì --rail-w vẫn là 160px - cộng tay là lệch.
  function fitToFrame() {
    if (!stage) return;
    var hud = document.querySelector(".hud");
    if (!hud) return;
    var r = hud.getBoundingClientRect();
    var top = document.querySelector(".hud-top");
    var duoiTop = top ? top.getBoundingClientRect().bottom : r.top;
    stage.style.setProperty("--cs-top", duoiTop + "px");
    stage.style.setProperty("--cs-left", r.left + "px");
    stage.style.setProperty("--cs-w", r.width + "px");
    stage.style.setProperty("--cs-h", Math.max(0, r.bottom - duoiTop) + "px");
  }

  // Rail thu/mở đổi bề ngang .hud mà KHÔNG bắn sự kiện resize của window, nên chỉ nghe resize
  // là khung sẽ lệch mất một dải đúng bằng phần rail vừa co. ResizeObserver bám thẳng .hud nên
  // bắt được cả hai, kể cả trong lúc rail đang chạy hoạt ảnh 0.28s.
  function theoDoiKhung() {
    window.addEventListener("resize", function () { if (expanded) fitToFrame(); });
    if (typeof ResizeObserver !== "function") return;
    var hud = document.querySelector(".hud");
    if (!hud) return;
    try { new ResizeObserver(function () { if (expanded) fitToFrame(); }).observe(hud); }
    catch (e) {}
  }

  function moveInto(node, container) {
    if (!node) return;
    slots.push({ node: node, parent: node.parentNode, next: node.nextSibling });
    container.appendChild(node);
  }

  function restore() {
    for (var i = slots.length - 1; i >= 0; i--) {
      var s = slots[i];
      if (!s.parent) continue;
      if (s.next && s.next.parentNode === s.parent) s.parent.insertBefore(s.node, s.next);
      else s.parent.appendChild(s.node);
    }
    slots = [];
  }

  function expand() {
    if (expanded) return;
    var body = ensureStage().querySelector(".chat-stage-body");
    moveInto(document.getElementById("chatArea"), body);
    moveInto(document.getElementById("attachBar"), body);   // chip file đính kèm hiện TRONG workspace
    moveInto(document.getElementById("modelBar"), body);    // menu đổi model + effort đi theo vào workspace
    moveInto(document.getElementById("hudVoice"), body);
    document.body.classList.add("chat-zoomed");
    expanded = true;
    // Đo SAU khi gắn .chat-zoomed: class đó đổi lưới .hud (hàng chat co về 0), đo trước là
    // lấy nhầm số đo của bố cục cũ.
    fitToFrame();
    setSide(sideDefaultOn());
    var ca = document.getElementById("chatArea");
    if (ca) ca.scrollTop = ca.scrollHeight;
    var ci = document.getElementById("chatInput");
    if (ci) { try { ci.focus(); } catch (e) {} }
  }

  function collapse() {
    if (!expanded) return;
    restore();
    document.body.classList.remove("chat-zoomed");
    expanded = false;
  }

  function toggle() { if (expanded) collapse(); else expand(); }

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !expanded) return;
    // Màn hẹp đang mở drawer lịch sử → Esc đóng drawer trước, chưa thu nhỏ chat
    if (window.innerWidth < 900 && stage && stage.classList.contains("side-on")) { setSide(false); return; }
    collapse();
  });

  function bind() {
    var btn = document.getElementById("chatZoomBtn");
    if (btn) btn.addEventListener("click", toggle);
    theoDoiKhung();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();

  // Cho module khác (nút Lịch sử cũ, sessions-ui) mở workspace
  window.JavisChatStage = {
    expand: expand, collapse: collapse, toggle: toggle,
    isOpen: function () { return expanded; },
    showSide: function () { expand(); setSide(true); },
  };
})();
