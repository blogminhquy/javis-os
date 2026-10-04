// ============================================
// JAVIS OS - Bộ đổi tông: TỐI ↔ SÁNG, chọn tay hoặc tự động theo giờ
// ============================================
// Chế độ lưu ở localStorage "javis.theme" với 3 giá trị: "dark" | "light" | "auto".
// "auto" (0.74.0) đọc thêm khung giờ ở "javis.theme.schedule" dạng "06:00-18:00": từ giờ
// đầu tới trước giờ sau là tông sáng, còn lại là tông tối. Cả hai là lựa chọn THEO THIẾT BỊ
// (điện thoại để tự động, máy bàn ghim tối là hợp lệ), nên không lưu lên server.
//
// Tông sáng đặt data-theme="light" trên <html>; tông tối gỡ hẳn thuộc tính
// (nên mặc định của :root luôn là tối - trang vẫn đúng kể cả khi file này chưa tải).
// Đoạn script nhỏ đầu index.html tính lại đúng phép này trước khi vẽ để khỏi nháy tông:
// sửa quy tắc giờ ở đây thì sửa cả ở đó.
//
// Giá trị cũ "dim" (tông tối-nhạt, đã gỡ ở 0.9.250) được quy về "dark" và ghi đè
// lại vào localStorage để lần sau không phải quy đổi nữa.
//
// Các lớp vẽ bằng canvas (starfield, knowledge graph) KHÔNG đọc được biến CSS,
// nên chúng nghe sự kiện "javis-theme-change" rồi tự vẽ lại bằng bảng màu tương ứng.
(function () {
  var KEY = "javis.theme";
  var KEY_SCHED = "javis.theme.schedule";
  var DEFAULT_SCHED = { light: "06:00", dark: "18:00" };
  var root = document.documentElement;

  function read(k) {
    try { return localStorage.getItem(k) || ""; } catch (e) { return ""; }
  }
  function write(k, v) {
    try { localStorage.setItem(k, v); } catch (e) {}
  }

  // "HH:MM" -> phút trong ngày; sai khuôn thì -1 để bên gọi rơi về mặc định.
  function toMin(s) {
    var m = /^(\d{1,2}):(\d{2})$/.exec(String(s || "").trim());
    if (!m) return -1;
    var h = +m[1], mi = +m[2];
    if (h > 23 || mi > 59) return -1;
    return h * 60 + mi;
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function fromMin(n) { return pad(Math.floor(n / 60)) + ":" + pad(n % 60); }

  function mode() {
    var v = read(KEY);
    return v === "light" || v === "auto" ? v : "dark";
  }

  function schedule() {
    var parts = read(KEY_SCHED).split("-");
    var l = toMin(parts[0]), d = toMin(parts[1]);
    if (l < 0 || d < 0) return { light: DEFAULT_SCHED.light, dark: DEFAULT_SCHED.dark };
    return { light: fromMin(l), dark: fromMin(d) };
  }

  // Khung giờ được phép vắt qua nửa đêm (sáng từ 20:00 tới 04:00 cho người làm ca đêm).
  // Hai mốc trùng nhau thì không có khoảng sáng nào: coi là tối cả ngày.
  function lightAt(date, sched) {
    var l = toMin(sched.light), d = toMin(sched.dark);
    var n = date.getHours() * 60 + date.getMinutes();
    if (l === d) return false;
    return l < d ? (n >= l && n < d) : (n >= l || n < d);
  }

  function wantLight() {
    var m = mode();
    if (m === "auto") return lightAt(new Date(), schedule());
    return m === "light";
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
    // tiếng Anh tại chỗ - cùng nấc suy biến đầu của i18n/index.js - và nghe "javis:i18n" bên
    // dưới để tự sửa lại ngay khi từ điển về. Chữ gốc tiếng Việt nằm ở vi.json, không chép ra đây.
    var auto = mode() === "auto";
    var key = auto ? (light ? "top.theme_auto_light" : "top.theme_auto_dark")
                   : (light ? "top.theme_light" : "top.theme_dark");
    var txt = window.t ? window.t(key) : key;
    if (txt === key) {
      txt = auto
        ? (light ? "Auto by time, light now - click to pick dark by hand"
                 : "Auto by time, dark now - click to pick light by hand")
        : (light ? "Light theme is on - click to switch to dark"
                 : "Dark theme is on - click to switch to light");
    }
    b.title = txt;
    b.setAttribute("aria-label", b.title);
  }
  window.addEventListener("javis:i18n", function () { syncButton(isLight()); });

  function emit(light) {
    try {
      window.dispatchEvent(new CustomEvent("javis-theme-change", { detail: { light: light, mode: mode() } }));
    } catch (e) {
      // Trình duyệt cũ không có CustomEvent constructor
      try {
        var ev = document.createEvent("Event");
        ev.initEvent("javis-theme-change", false, false);
        window.dispatchEvent(ev);
      } catch (e2) {}
    }
  }

  // Vẽ tông. Gọi trùng tông đang có thì không phát sự kiện: chế độ tự động kiểm tra lại mỗi
  // nửa phút, không được bắt đồ thị và linh vật vẽ lại mỗi nửa phút.
  function paint(light, force) {
    var changed = light !== isLight();
    if (light) root.setAttribute("data-theme", "light");
    else root.removeAttribute("data-theme");
    syncMeta(light);
    syncButton(light);
    if (changed || force) emit(light);
  }

  // Giữ nguyên chữ ký cũ apply(light, persist): bên ngoài gọi apply là CHỌN TAY.
  function apply(light, persist) {
    if (persist) write(KEY, light ? "light" : "dark");
    paint(!!light, true);
  }

  function setMode(m) {
    if (m !== "light" && m !== "auto") m = "dark";
    write(KEY, m);
    paint(wantLight(), true);
  }

  function setSchedule(light, dark) {
    var l = toMin(light), d = toMin(dark);
    if (l < 0 || d < 0) return false;
    write(KEY_SCHED, fromMin(l) + "-" + fromMin(d));
    if (mode() === "auto") paint(wantLight(), true);
    else emit(isLight());                 // trang Cài đặt nghe để vẽ lại dòng trạng thái
    return true;
  }

  // Mốc đổi tông kế tiếp ("HH:MM"), chỉ có nghĩa ở chế độ tự động.
  function nextChange() {
    if (mode() !== "auto") return "";
    var s = schedule();
    if (s.light === s.dark) return "";
    return isLight() ? s.dark : s.light;
  }

  // Bấm nút trên thanh trên cùng: luôn là CHỌN TAY tông còn lại, kể cả khi đang tự động.
  // Muốn quay lại tự động thì vào Cài đặt; nút một chạm mà vòng qua ba chế độ thì người
  // dùng phải bấm hai lần mới ra tông mình muốn.
  function toggle() { apply(!isLight(), true); }

  window.javisTheme = {
    isLight: isLight,
    apply: apply,
    toggle: toggle,
    mode: mode,
    setMode: setMode,
    schedule: schedule,
    setSchedule: setSchedule,
    nextChange: nextChange,
    lightAt: lightAt,
    // Đăng ký hàm vẽ lại; gọi luôn một lần để lớp canvas nhận tông hiện tại ngay khi khởi tạo.
    on: function (fn) {
      if (typeof fn !== "function") return;
      window.addEventListener("javis-theme-change", function (e) {
        fn(!!(e && e.detail ? e.detail.light : isLight()));
      });
      try { fn(isLight()); } catch (err) {}
    },
  };

  // Chế độ tự động: đồng hồ kiểm tra lại mỗi 30 giây, và ngay khi tab hiện lại. setTimeout
  // canh đúng mốc thì gọn hơn nhưng bị trình duyệt hoãn khi máy ngủ hay tab chạy nền, nên
  // mở laptop lúc 19:00 sẽ vẫn sáng tới khi hẹn giờ kịp tỉnh. Kiểm tra này chỉ là so hai số.
  function tick() {
    if (mode() === "auto") paint(wantLight(), false);
  }

  function init() {
    if (read(KEY) === "dim") write(KEY, "dark");   // quy đổi tông tối-nhạt cũ, chỉ chạy một lần
    paint(wantLight(), true);

    var b = document.getElementById("themeToggle");
    if (b) b.addEventListener("click", toggle);

    setInterval(tick, 30000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) tick();
    });
    window.addEventListener("focus", tick);

    // Mở Javis ở nhiều tab: đổi tông hay khung giờ ở tab này thì tab kia đổi theo.
    window.addEventListener("storage", function (e) {
      if (e.key === KEY || e.key === KEY_SCHED) paint(wantLight(), true);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
