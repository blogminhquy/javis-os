/* chat-zoom.js - nút "phóng to" khung chat.
 *
 * TRƯỚC (tới 0.12.3): dựng một lớp nổi .chat-stage đè lên cockpit, MƯỢN chính các node
 * #chatArea/#attachBar/#modelBar/#hudVoice của HUD rồi trả về khi Esc. Nó tồn tại song song
 * với trang "Trò chuyện" (console.js renderChat) - vốn mượn ĐÚNG BỐN node đó và có sẵn
 * sidebar lịch sử. Hai chỗ giành cùng một bộ node nên phải rải các nhát "đang mở thì thu
 * lại" khắp navigateTo/openFilesAt/renderChat, và người dùng thì có hai khung chat trông
 * gần giống nhau mà hành xử khác nhau (một cái Esc thoát, một cái là một trang thật).
 *
 * NAY: bỏ hẳn lớp nổi. Phóng to = CHUYỂN sang trang Trò chuyện; ở đó có nút thu nhỏ để về
 * lại màn Javis. Một khung chat, một đường vào, không còn tranh node.
 *
 * Giữ nguyên tên window.JavisChatStage vì console.js/sessions-ui.js đang gọi: isOpen() nay
 * luôn false nên các nhát "thu lại" ở nơi khác thành vô hại, khỏi phải sửa lan man.
 */
(function () {
  "use strict";

  function nav() {
    try {
      if (window.Alpine && window.Alpine.store) return window.Alpine.store("nav") || null;
    } catch (e) {}
    return null;
  }

  function goTo(id) {
    var s = nav();
    if (!s) return false;
    if (s.active === id) return true;
    try { s.go(id); } catch (e) { return false; }
    return true;
  }

  function expand() { return goTo("chat"); }
  function collapse() { return goTo("home"); }

  function isOnChat() {
    var s = nav();
    return !!(s && s.active === "chat");
  }

  function toggle() { return isOnChat() ? collapse() : expand(); }

  function bind() {
    var btn = document.getElementById("chatZoomBtn");
    if (btn) btn.addEventListener("click", function () { expand(); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();

  window.JavisChatStage = {
    expand: expand,
    collapse: function () { /* không còn lớp nổi để thu; xem isOpen() */ },
    toggle: toggle,
    // Luôn false: không còn lớp nổi nào đang mượn node của HUD. Các chỗ gọi
    // "isOpen() thì collapse()" nhờ vậy tự thành no-op thay vì đá người dùng về trang chủ.
    isOpen: function () { return false; },
    // Nút "Lịch sử" ở header: sang trang Trò chuyện, nơi sidebar lịch sử là cột trái cố định
    // (màn hẹp thì mở drawer).
    showSide: function () {
      var ok = expand();
      setTimeout(function () {
        var page = document.getElementById("chatPage");
        if (page && window.innerWidth < 860) page.classList.add("side-open");
      }, 60);
      return ok;
    },
    goHome: collapse,
  };
})();
