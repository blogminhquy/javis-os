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
      button.setAttribute("aria-label", hidden ? window.t("bview.overlay_show_aria") : window.t("orb.overlay_aria"));
      button.title = hidden
        ? window.t("bview.overlay_show_title")
        : window.t("orb.overlay_title");
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

    initTimelapse();
  }

  // Nút timelapse "cuộc đời brain": chiếu lại note mọc dần theo thời gian tạo.
  function initTimelapse() {
    var btn = document.getElementById("graphTimelapseBtn");
    if (!btn) return;

    function setPlaying(on) {
      btn.classList.toggle("playing", !!on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.title = on ? window.t("bview.timelapse_stop_title")
                     : window.t("orb.timelapse_title");
    }

    btn.addEventListener("click", function () {
      var g = window.__javisGraph;
      if (!g || typeof g.startTimelapse !== "function") {
        btn.title = window.t("bview.graph_not_ready");
        return;
      }
      if (g.timelapseRunning) { g.stopTimelapse(); return; }   // sự kiện end sẽ tự tắt trạng thái nút
      if (g.startTimelapse()) setPlaying(true);
    });

    // Hết phim (hoặc bấm dừng) → nút về trạng thái nghỉ
    window.addEventListener("javis-timelapse-end", function () { setPlaying(false); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
