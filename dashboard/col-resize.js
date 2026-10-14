/* Kéo đường biên để đổi bề rộng một cột (0.148.0). Dùng cho trang đồ thị (cột Vault trái, cột hội thoại phải) và trang
 * Trò chuyện (cột Hội thoại/Thư mục). Trang Cộng sự có bản riêng trong workspace.js (cùng cách làm).
 *
 * Bề rộng nằm trong một biến CSS trên `host` (vd. --hud-left-w); CSS của cột đọc biến đó, thiếu biến thì về mặc định cũ.
 * Bề rộng đã kéo được nhớ qua localStorage. Tay kéo là separator có nhãn: kéo chuột hay chạm, mũi tên trái/phải đổi 16px,
 * nhấp đúp về mặc định. Không đụng tới bố cục màn hẹp: CSS tự ẩn tay kéo ở đó.
 */
(function () {
  "use strict";

  function t(k, v) { return (typeof window !== "undefined" && window.t) ? window.t(k, v) : k; }

  function doc(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function ghi(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, String(v)); } catch (e) {} }

  // Chặn bề rộng: [min, max] và chừa cho phần giữa ít nhất `keep` px (trừ cả cột bên kia nếu có).
  function chan(o, w) {
    var max = typeof o.max === "function" ? o.max() : o.max;
    var tong = o.total ? o.total() : 0;
    if (tong) {
      var khac = o.other ? (o.other() || 0) : 0;
      max = Math.min(max, tong - khac - (o.keep || 360));
    }
    return Math.max(o.min, Math.min(max, Math.round(w)));
  }

  // Áp bề rộng đã nhớ (gọi lúc dựng trang).
  function apply(o) {
    var v = parseInt(doc(o.key) || "0", 10) || 0;
    if (v) o.host.style.setProperty(o.varName, chan(o, v) + "px");
  }

  // Gắn tay kéo vào cột `col`. `edge`: "right" khi tay kéo nằm ở mép phải của cột (kéo sang phải là rộng ra), "left" khi
  // nằm ở mép trái. Trả hàm gỡ.
  function attach(col, o) {
    if (!col || col.querySelector(":scope > .col-resize")) return function () {};
    var h = document.createElement("div");
    h.className = "col-resize col-resize-" + (o.edge === "left" ? "left" : "right");
    h.setAttribute("role", "separator");
    h.setAttribute("aria-orientation", "vertical");
    h.tabIndex = 0;
    // Nhãn đặt lại lúc trỏ vào hay focus: trang đồ thị gắn tay kéo trước khi từ điển i18n tải xong.
    var nhan = function () { h.setAttribute("aria-label", t(o.label || "common.resize_col")); h.title = t("common.resize_hint"); };
    nhan();
    h.addEventListener("pointerenter", nhan);
    h.addEventListener("focus", nhan);
    col.appendChild(h);
    var dau = null;
    var dat = function (w) { o.host.style.setProperty(o.varName, chan(o, w) + "px"); if (o.onChange) o.onChange(); };
    var luu = function () { ghi(o.key, Math.round(col.getBoundingClientRect().width)); };
    h.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      dau = { x: e.clientX, w: col.getBoundingClientRect().width };
      try { h.setPointerCapture(e.pointerId); } catch (e2) {}
      document.body.classList.add("col-resizing");
    });
    h.addEventListener("pointermove", function (e) {
      if (!dau) return;
      var dx = e.clientX - dau.x;
      dat(dau.w + (o.edge === "left" ? -dx : dx));
    });
    var xong = function () {
      if (!dau) return;
      dau = null;
      document.body.classList.remove("col-resizing");
      luu();
    };
    h.addEventListener("pointerup", xong);
    h.addEventListener("pointercancel", xong);
    h.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      var buoc = (e.key === "ArrowRight" ? 16 : -16) * (o.edge === "left" ? -1 : 1);
      dat(col.getBoundingClientRect().width + buoc);
      luu();
    });
    h.addEventListener("dblclick", function () {
      o.host.style.removeProperty(o.varName);
      ghi(o.key, null);
      if (o.onChange) o.onChange();
    });
    return function () { if (h.parentNode) h.parentNode.removeChild(h); };
  }

  // Trang đồ thị: cột Vault (.hud-left) và cột hội thoại (.hud-right) của .hud-body. Biến đặt trên <html> để mọi luật
  // grid của .hud-body (kể cả khi thu một cột về 44px) đọc được.
  function hud() {
    var body = document.querySelector(".hud-body");
    if (!body) return;
    var left = body.querySelector(":scope > .hud-left"), right = body.querySelector(":scope > .hud-right");
    var root = document.documentElement;
    var wOf = function (el) { return el ? el.getBoundingClientRect().width : 0; };
    var base = { host: root, total: function () { return body.clientWidth; }, keep: 360 };
    var oL = Object.assign({}, base, { varName: "--hud-left-w", key: "javis_hud_left_w", min: 200, max: 560, edge: "right",
      label: "common.resize_vault", other: function () { return wOf(right); } });
    var oR = Object.assign({}, base, { varName: "--hud-right-w", key: "javis_hud_right_w", min: 280, max: 820, edge: "left",
      label: "common.resize_chatcol", other: function () { return wOf(left); } });
    apply(oL); apply(oR);
    attach(left, oL);
    attach(right, oR);
  }

  var api = { attach: attach, apply: apply, chan: chan, hud: hud };
  if (typeof window !== "undefined") {
    window.JavisColResize = api;
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", hud);
    else hud();
  }
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
