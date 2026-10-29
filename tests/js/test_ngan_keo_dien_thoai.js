// Ngăn kéo menu trên điện thoại (0.216.0).
//
//     node tests/js/test_ngan_keo_dien_thoai.js
//
// Chủ repo 18/10/2026 (iPhone, kèm ảnh): "đang mở menu thì nó tắt luôn và hiện màn hình tối hơn, không mở được menu cứ
// hiện rồi tắt luôn". Ngăn kéo trượt ra rồi biến mất, chỉ còn nền mờ. Ba chốt:
//   1. Ngăn kéo không dùng backdrop-filter trên điện thoại: Safari có lúc thôi vẽ một khung vừa làm mờ, vừa trượt, vừa
//      cuộn. Nó nằm trên nền mờ rồi nên không cần làm mờ, dùng nền đặc.
//   2. Nền mờ chỉ hiện theo trạng thái của ngăn kéo (body.nav-open), không theo thuộc tính `hidden` riêng: hai thứ lệch
//      nhau là màn hình tối mà không có menu.
//   3. Một chạm thành hai cú bấm (iPhone) không được đóng ngay ngăn kéo vừa mở.
var fs = require("fs");
var path = require("path");
var vm = require("vm");
var ROOT = path.resolve(__dirname, "..", "..");
var CSS = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
var SRC = fs.readFileSync(path.join(ROOT, "dashboard", "mobile-chat.js"), "utf8");

var fails = [];
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails.push(name); }

var m = CSS.match(/@media \(max-width: 860px\) \{[\s\S]*?\/\* Rail: từ thanh đáy → ngăn kéo trượt từ trái \*\/\s*\.rail \{([^}]*)\}/);
var rail = m ? m[1] : "";
check("tìm thấy luật ngăn kéo trên điện thoại", !!rail);
check("ngăn kéo không làm mờ nền (cả bản -webkit-)", /\bbackdrop-filter: none;/.test(rail) && /-webkit-backdrop-filter: none;/.test(rail));
check("ngăn kéo có nền đặc", /background: var\(--bg\);/.test(rail));
// 0.393.0 (owner, iPhone video: the drawer showed mid-slide, then only the dim screen stayed). No transform layer on
// the drawer: it slides on `left`, is hidden while shut, and is the only scroller inside it.
check("ngăn kéo không trượt bằng transform", /transform: none;/.test(rail) && /will-change: auto;/.test(rail)
  && /left: calc\(-1 \* min\(280px, 82vw\)\);/.test(rail));
check("ngăn kéo đóng thì ẩn hẳn", /visibility: hidden;/.test(rail)
  && /body\.nav-open \.rail \{ left: 0; visibility: visible;/.test(CSS));
check("danh sách menu không tự cuộn bên trong ngăn kéo",
  /\.rail-nav \{ flex-direction: column; overflow: visible;/.test(CSS));
check("nền mờ mặc định ẩn, kể cả khi thiếu thuộc tính hidden",
  /\.nav-backdrop, \.nav-backdrop\[hidden\] \{[^}]*display: none;/.test(CSS));
check("nền mờ chỉ hiện khi ngăn kéo mở", /body\.nav-open \.nav-backdrop \{ display: block; \}/.test(CSS));

// ---- Hành vi: chạy phần ngăn kéo của mobile-chat.js trên một DOM giả ----
function El(id) {
  this.id = id; this.hidden = true; this.listeners = {};
  this.classList = { _s: {}, add: function (c) { this._s[c] = 1; }, remove: function (c) { delete this._s[c]; },
    contains: function (c) { return !!this._s[c]; }, toggle: function (c, on) { if (on === undefined) on = !this._s[c]; if (on) this._s[c] = 1; else delete this._s[c]; return on; } };
}
El.prototype.addEventListener = function (t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); };
El.prototype.fire = function (t, ev) { (this.listeners[t] || []).forEach(function (f) { f(ev || { target: { closest: function () { return null; } } }); }); };
var els = { navToggle: new El("navToggle"), navBackdrop: new El("navBackdrop") };
var body = new El("body");
var now = 1000;
var mqListeners = [];
var mq = { matches: true, addEventListener: function (t, f) { mqListeners.push(f); } };
var docListeners = {};
var sandbox = {
  window: { matchMedia: function () { return mq; }, t: function (k) { return k; }, addEventListener: function () {}, visualViewport: null },
  document: { readyState: "complete", body: body, documentElement: { style: { setProperty: function () {}, removeProperty: function () {} } },
    getElementById: function (id) { return els[id] || null; }, querySelector: function () { return null; },
    querySelectorAll: function () { return []; }, addEventListener: function (t, f) { (docListeners[t] = docListeners[t] || []).push(f); },
    createElement: function () { return new El("x"); }, activeElement: null },
  Date: { now: function () { return now; } }, setTimeout: function () {}, clearTimeout: function () {}, console: console,
};
sandbox.window.document = sandbox.document;
try { vm.runInNewContext(SRC, sandbox); } catch (e) { check("chạy được mobile-chat.js trên DOM giả: " + e.message, false); }
var open = function () { return body.classList.contains("nav-open"); };

els.navToggle.fire("click");
check("bấm nút menu: ngăn kéo mở, nền mờ hiện", open() && els.navBackdrop.hidden === false);
now += 80; els.navToggle.fire("click"); els.navBackdrop.fire("click");
check("cú bấm thứ hai của cùng một chạm (80ms sau) không đóng ngăn kéo", open());
now += 500; els.navBackdrop.fire("click");
check("chạm nền mờ sau đó thì đóng như thường", !open() && els.navBackdrop.hidden === true);
els.navToggle.fire("click"); now += 500; els.navToggle.fire("click");
check("bấm lại nút menu thì đóng", !open());
els.navToggle.fire("click"); now += 10;
(docListeners.keydown || []).forEach(function (f) { f({ key: "Escape" }); });
check("phím Esc đóng ngay, không chờ", !open());
els.navToggle.fire("click"); now += 500;
mqListeners.forEach(function (f) { f(); });
check("trình duyệt báo đổi khổ mà vẫn là điện thoại: ngăn kéo không tự đóng", open());
mq.matches = false; mqListeners.forEach(function (f) { f(); });
check("sang màn rộng thì đóng", !open());

if (fails.length) { console.log("\nFAIL " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("\nOK - test_ngan_keo_dien_thoai: all pass");
