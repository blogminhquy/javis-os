// ============================================
// JAVIS OS - Bộ đổi tông: TỐI ↔ SÁNG
// ============================================
// Tông lưu ở localStorage "javis.theme" với 2 giá trị: "dark" | "light".
// Tông sáng đặt data-theme="light" trên <html>; tông tối gỡ hẳn thuộc tính
// (nên mặc định của :root luôn là tối - trang vẫn đúng kể cả khi file này chưa tải).
//
// Giá trị cũ "dim" (tông tối-nhạt, đã gỡ ở 0.9.250) được quy về "dark" và ghi đè
// lại vào localStorage để lần sau không phải quy đổi nữa.
//
// Các lớp vẽ bằng canvas (starfield, knowledge graph) KHÔNG đọc được biến CSS,
// nên chúng nghe sự kiện "javis-theme-change" rồi tự vẽ lại bằng bảng màu tương ứng.
(function () {
  var KEY = "javis.theme";
  var root = document.documentElement;

  function read() {
    try { return localStorage.getItem(KEY) || ""; } catch (e) { return ""; }
  }
  function write(v) {
    try { localStorage.setItem(KEY, v); } catch (e) {}
  }

  function isLight() { return root.getAttribute("data-theme") === "light"; }

  // Màu thanh trình duyệt trên mobile - phải khớp nền header (--bg2) của từng tông.
  function syncMeta(light) {
    var m = document.querySelector('meta[name="theme-color"]');
    if (!m) {
      m = document.createElement("meta");
      m.setAttribute("name", "theme-color");
      document.head.appendChild(m);
    }
    m.setAttribute("content", light ? "#ffffff" : "#181822");
  }

  function syncButton(light) {
    var b = document.getElementById("themeToggle");
    if (!b) return;
    b.setAttribute("aria-pressed", light ? "true" : "false");
    // Tooltip lấy từ từ điển i18n khi nó đã nạp; chưa nạp (theme.js chạy rất sớm) thì dùng
    // tiếng Việt tại chỗ - và nghe "javis:i18n" bên dưới để tự sửa lại ngay khi từ điển về.
    var key = light ? "top.theme_light" : "top.theme_dark";
    var txt = window.t ? window.t(key) : key;
    if (txt === key) {
      txt = light ? "Đang dùng tông sáng - bấm để chuyển sang tông tối"
                  : "Đang dùng tông tối - bấm để chuyển sang tông sáng";
    }
    b.title = txt;
    b.setAttribute("aria-label", b.title);
  }
  window.addEventListener("javis:i18n", function () {
    syncButton(root.getAttribute("data-theme") === "light");
  });

  function apply(light, persist) {
    if (light) root.setAttribute("data-theme", "light");
    else root.removeAttribute("data-theme");
    if (persist) write(light ? "light" : "dark");
    syncMeta(light);
    syncButton(light);
    try {
      window.dispatchEvent(new CustomEvent("javis-theme-change", { detail: { light: light } }));
    } catch (e) {
      // Trình duyệt cũ không có CustomEvent constructor
      try {
        var ev = document.createEvent("Event");
        ev.initEvent("javis-theme-change", false, false);
        window.dispatchEvent(ev);
      } catch (e2) {}
    }
  }

  function toggle() { apply(!isLight(), true); }

  window.javisTheme = {
    isLight: isLight,
    apply: apply,
    toggle: toggle,
    // Đăng ký hàm vẽ lại; gọi luôn một lần để lớp canvas nhận tông hiện tại ngay khi khởi tạo.
    on: function (fn) {
      if (typeof fn !== "function") return;
      window.addEventListener("javis-theme-change", function (e) {
        fn(!!(e && e.detail ? e.detail.light : isLight()));
      });
      try { fn(isLight()); } catch (err) {}
    },
  };

  function init() {
    var saved = read();
    if (saved === "dim") write("dark");          // quy đổi tông tối-nhạt cũ, chỉ chạy một lần
    apply(saved === "light", false);

    var b = document.getElementById("themeToggle");
    if (b) b.addEventListener("click", toggle);

    // Mở Javis ở nhiều tab: đổi tông ở tab này thì tab kia đổi theo.
    window.addEventListener("storage", function (e) {
      if (e.key === KEY) apply(e.newValue === "light", false);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
