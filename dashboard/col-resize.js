/* Kéo đường biên để đổi bề rộng một cột (0.148.0). Dùng cho trang đồ thị (cột Vault trái, cột hội thoại phải) và trang
 * Trò chuyện (cột Hội thoại/Thư mục). Trang Cộng sự có bản riêng trong workspace.js (cùng cách làm).
 *
 * Bề rộng nằm trong một biến CSS trên `host` (vd. --hud-left-w); CSS của cột đọc biến đó, thiếu biến thì về mặc định cũ.
 * Bề rộng đã kéo được nhớ qua localStorage. Tay kéo là separator có nhãn: kéo chuột hay chạm, mũi tên trái/phải đổi 16px,
 * nhấp đúp về mặc định. Không đụng tới bố cục màn hẹp: CSS tự ẩn tay kéo ở đó.
 *
 * 0.196.0 (owner, 17/10/2026: "kéo đến 1 cỡ nhất định thì nó ẩn vào thụt luôn vào trong", same as the Partners page):
 * - `collapse: { below, run }`: let go narrower than `below` and the column folds away with the page's OWN collapse
 *   (`run`, usually a click on its existing collapse button). The width it had stays remembered for when it reopens.
 * - `snap: { below, to, onSnap(on) }`: narrower than `below` snaps to `to` px (an avatar strip, like the Partners list);
 *   `onSnap(true|false)` tells the page to switch its compact look.
 * - `miniTip`: the name card shown next to an avatar of a snapped strip (moved here from workspace.js so every page
 *   draws the same card, element #wsMiniTip / .ws-mini-tip).
 */
(function () {
  "use strict";

  function t(k, v) { return (typeof window !== "undefined" && window.t) ? window.t(k, v) : k; }

  // Fold point for a column of minimum width `min`: 60px under it, the same gap as the Partners list (min 220, snaps at
  // 160).
  function FOLD_AT(min) { return min - 60; }

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

  // Width after the snap rule (0.196.0): narrower than snap.below is the strip width, else the usual clamp.
  function fit(o, w) {
    if (o.snap && w < o.snap.below) return o.snap.to;
    return chan(o, w);
  }

  function setW(o, w) {
    o.host.style.setProperty(o.varName, w + "px");
    if (o.snap && o.snap.onSnap) o.snap.onSnap(w === o.snap.to);
  }

  // Áp bề rộng đã nhớ (gọi lúc dựng trang).
  function apply(o) {
    var v = parseInt(doc(o.key) || "0", 10) || 0;
    if (v) setW(o, fit(o, v));
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
    // `raw`: the width the pointer asks for, before clamping; used to tell "let go to fold it away" (0.196.0).
    var raw = 0;
    var dat = function (w) {
      raw = w;
      setW(o, fit(o, w));
      // Past the fold point the column shows it will fold (CSS dims it) until the pointer comes back.
      if (o.collapse && col.classList) col.classList.toggle("col-resize-folding", w < o.collapse.below);
      if (o.onChange) o.onChange();
    };
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
      var start = dau.w;
      dau = null;
      document.body.classList.remove("col-resizing");
      if (col.classList) col.classList.remove("col-resize-folding");
      if (o.collapse && raw < o.collapse.below) {
        // Fold it away and keep the width it had before the drag, so reopening gives the column back as it was.
        setW(o, chan(o, start));
        ghi(o.key, Math.round(chan(o, start)));
        o.collapse.run();
        return;
      }
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
      if (o.snap && o.snap.onSnap) o.snap.onSnap(false);
      if (o.onChange) o.onChange();
    });
    return function () { if (h.parentNode) h.parentNode.removeChild(h); };
  }

  // The name card next to an avatar of a snapped strip (0.196.0, moved from workspace.js 0.191.0). `d`: {ava (html), name,
  // time, sub, stText, st}. One card for the whole app, moved from row to row; the row's own tooltip is held back while
  // it shows (restored by hide).
  var tipRow = null;
  function tipEl() {
    var el = document.getElementById("wsMiniTip");
    if (!el) {
      el = document.createElement("div");
      el.id = "wsMiniTip"; el.className = "ws-mini-tip"; el.setAttribute("role", "tooltip"); el.hidden = true;
      document.body.appendChild(el);
    }
    return el;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }
  function tipHtml(d) {
    return '<div class="ws-mini-tip-head">' + (d.ava ? '<span class="ws-mini-tip-ava">' + d.ava + '</span>' : "") +
      '<strong>' + esc(d.name) + '</strong>' + (d.time ? '<span class="ws-mini-tip-time">' + esc(d.time) + '</span>' : "") + '</div>' +
      (d.sub ? '<div class="ws-mini-tip-sub">' + esc(d.sub) + '</div>' : "") +
      (d.stText ? '<div class="ws-mini-tip-st" data-st="' + esc(d.st || "") + '">' + esc(d.stText) + '</div>' : "");
  }
  function tipHide() {
    var el = document.getElementById("wsMiniTip");
    if (el) el.hidden = true;
    if (tipRow && tipRow.hasAttribute("data-tip-title")) {
      tipRow.setAttribute("title", tipRow.getAttribute("data-tip-title"));
      tipRow.removeAttribute("data-tip-title");
    }
    tipRow = null;
  }
  function tipShow(row, d) {
    tipHide();
    var el = tipEl();
    el.innerHTML = tipHtml(d);
    if (row.hasAttribute("title")) { row.setAttribute("data-tip-title", row.getAttribute("title")); row.removeAttribute("title"); }
    tipRow = row;
    el.hidden = false;
    var r = row.getBoundingClientRect(), h = el.getBoundingClientRect().height;
    el.style.left = Math.round(r.right + 8) + "px";
    el.style.top = Math.round(Math.max(8, Math.min(window.innerHeight - h - 8, r.top + r.height / 2 - h / 2))) + "px";
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
    // 0.196.0: let go narrower than the fold point and the column folds with its own collapse button (same as clicking it).
    var press = function (sel) { return function () { var b = document.querySelector(sel); if (b) b.click(); }; };
    var oL = Object.assign({}, base, { varName: "--hud-left-w", key: "javis_hud_left_w", min: 200, max: 560, edge: "right",
      label: "common.resize_vault", other: function () { return wOf(right); },
      collapse: { below: FOLD_AT(200), run: press("#vtCollapse") } });
    var oR = Object.assign({}, base, { varName: "--hud-right-w", key: "javis_hud_right_w", min: 280, max: 820, edge: "left",
      label: "common.resize_chatcol", other: function () { return wOf(left); },
      collapse: { below: FOLD_AT(280), run: press("#chatColThu") } });
    apply(oL); apply(oR);
    attach(left, oL);
    attach(right, oR);
  }

  var api = { attach: attach, apply: apply, chan: chan, fit: fit, hud: hud, FOLD_AT: FOLD_AT,
    miniTip: { show: tipShow, hide: tipHide, html: tipHtml } };
  if (typeof window !== "undefined") {
    window.JavisColResize = api;
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", hud);
    else hud();
  }
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
