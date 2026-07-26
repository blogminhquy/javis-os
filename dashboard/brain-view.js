// Điều khiển lớp thông tin phủ trên brain.
// Nút mắt chỉ ẩn nhãn thư mục/% và thanh Agents/Skills/Workflows; graph + trạng thái vẫn giữ.
(function () {
  var STORAGE_KEY = "javis.brainOverlaysHidden";

  function init() {
    var root = document.querySelector(".hud-center");
    var button = document.getElementById("brainOverlayToggle");
    if (!root || !button) return;

    function readHidden() {
      try { return localStorage.getItem(STORAGE_KEY) === "1"; }
      catch (e) { return false; }
    }

    function apply(hidden, persist) {
      root.classList.toggle("brain-overlays-hidden", hidden);
      button.setAttribute("aria-pressed", hidden ? "true" : "false");
      button.setAttribute("aria-label", hidden ? "Hiện nhãn và số liệu brain" : "Ẩn nhãn và số liệu brain");
      button.title = hidden
        ? "Hiện nhãn thư mục và số liệu Agents / Skills / Workflows"
        : "Ẩn nhãn thư mục và số liệu Agents / Skills / Workflows";
      if (persist) {
        try { localStorage.setItem(STORAGE_KEY, hidden ? "1" : "0"); } catch (e) {}
      }
    }

    apply(readHidden(), false);
    button.addEventListener("click", function () {
      apply(!root.classList.contains("brain-overlays-hidden"), true);
    });

    // Đồng bộ nếu người dùng mở Javis ở nhiều tab.
    window.addEventListener("storage", function (event) {
      if (event.key === STORAGE_KEY) apply(event.newValue === "1", false);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
