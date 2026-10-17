/* tag-picker.js - the tag pieces shared by the Partners page and the Teams page (0.195.0).

   Owner, 17/10/2026: "tag em làm dropdown giống bên cộng sự đi em, cái gì mà có rồi thì tái sử dụng chứ đừng tự code ra
   thêm chức năng mới trong cùng 1 phần mềm". These are the Partners page pieces moved here unchanged, so both pages draw
   and behave the same:
   - barHtml: the filter button on top of a list ("All partners" / a tag, with a chevron) plus the clear button; the
     dropdown it opens is the shared JavisChatSide.menu.
   - pickerHtml + bind: the "Tag" picker inside a row's menu: back row, a box to add a new tag, then every tag as a
     check row (tap to add or remove). It stays open so several tags can be set in one go.
   Words come from the caller (each page has its own "All ..." label); the picker's own words are the ws.tag_* keys.
   No em dash anywhere (owner rule). */
(function () {
  "use strict";
  var t = function (k, v) { return (typeof window !== "undefined" && window.t ? window.t(k, v) : k); };
  var ic = function (n, o) { return (typeof window !== "undefined" && window.ic ? window.ic(n, o) : ""); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  // Filter bar. `o`: {label, icon, canClear, pickTitle, clearTitle}.
  function barHtml(o) {
    return '<button type="button" class="cs-proj-cur" title="' + esc(o.pickTitle) + '">' +
        '<span class="cs-proj-name">' + ic(o.icon || "layers") + ' ' + esc(o.label) + '</span>' +
        '<span class="cs-proj-caret">' + ic("chevron-down") + '</span></button>' +
      (o.canClear ? '<button type="button" class="cs-proj-x" title="' + esc(o.clearTitle) + '">' + ic("x") + '</button>' : '');
  }

  // Picker rows: `rows` = [{ten, key, on}], already in display order.
  function pickerHtml(rows) {
    return '<button type="button" class="ws-menu-it quay" data-act="quay">' + ic("chevron-left") +
        '<span>' + esc(t("ws.tag_menu")) + '</span></button>' +
      '<form class="ws-tag-new" data-act="moi"><input type="text" maxlength="40" class="ws-tag-in" ' +
        'placeholder="' + esc(t("ws.tag_new_ph")) + '" aria-label="' + esc(t("ws.tag_new_ph")) + '">' +
        '<button type="submit" class="ws-btn">' + esc(t("ws.tag_add")) + '</button></form>' +
      (rows || []).map(function (g) {
        return '<button type="button" role="menuitemcheckbox" aria-checked="' + g.on + '" class="ws-menu-it' +
          (g.on ? " on" : "") + '" data-tag="' + esc(g.ten) + '" data-key="' + esc(g.key) + '" title="' +
          esc(t(g.on ? "ws.tag_remove_title" : "ws.tag_add_title", { ten: g.ten })) +
          '">' + ic(g.on ? "check" : "tag") + '<span>' + esc(g.ten) + '</span></button>';
      }).join("");
  }

  // Wire a drawn picker. `h`: {back(), add(ten), toggle(ten, on, key)}. `focusKey`: FOCUS_INPUT after adding a new tag,
  // the key of the tag just toggled, or null (the input) after a redraw, so the keyboard keeps its place.
  var FOCUS_INPUT = "\u0001in";
  function bind(m, h, focusKey) {
    var back = m.querySelector('[data-act="quay"]');
    if (back) back.onclick = function () { h.back(); };
    var form = m.querySelector('[data-act="moi"]'), o = m.querySelector(".ws-tag-in");
    if (form) form.onsubmit = function (e) {
      e.preventDefault();
      var ten = String(o.value || "").trim();
      if (ten) h.add(ten);
    };
    Array.prototype.forEach.call(m.querySelectorAll("[data-tag]"), function (b) {
      b.onclick = function () { h.toggle(b.dataset.tag, b.getAttribute("aria-checked") === "true", b.dataset.key); };
    });
    var nhan = focusKey === FOCUS_INPUT || focusKey == null ? o
      : Array.prototype.find.call(m.querySelectorAll("[data-tag]"), function (b) { return b.dataset.key === focusKey; });
    if (nhan) try { nhan.focus(); } catch (e) {}
  }

  var API = { barHtml: barHtml, pickerHtml: pickerHtml, bind: bind, FOCUS_INPUT: FOCUS_INPUT };
  if (typeof window !== "undefined") window.JavisTagPicker = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
