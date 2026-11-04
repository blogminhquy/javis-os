/* reorder-dialog.js - one "Reorder" box for every list the owner can order by hand (0.454.0).

   Owner, 04/11/2026: "sắp xếp thứ tự Project kéo thả như Brain ... các tag và các project hoặc ghim và cả đoạn chat".
   The brain picker already had a Reorder mode (brain-picker.js): drag the handle, or the up / down arrows, then Done.
   This box is that same mode for the other lists, so they all move the same way:
     - projects of the chat panel (sessions-ui.js, POST /projects/order),
     - pinned chats (sessions-ui.js, POST /sessions/pin-order),
     - tags of the Partners page and of the Teams page (workspace.js, teams.js, POST /ui/order).
   JavisReorder.open({title, hint, items: [{id, label, icon}], save(ids) -> Promise<"" | error text>}).
   JavisReorder.rank(scope, key) and sortTags(list, scope, keyOf, nameOf) read the saved tag orders (GET /ui/order,
   loaded once and kept fresh after every save). Pure helpers are exported for node tests. No em dash here. */
(function (root) {
  "use strict";

  // ---- pure helpers (node-testable) ----
  function moveItem(list, from, to) {
    var a = list.slice();
    if (from < 0 || from >= a.length) return a;
    to = Math.max(0, Math.min(a.length - 1, to));
    var it = a.splice(from, 1)[0];
    a.splice(to, 0, it);
    return a;
  }
  // `list` sorted by the saved `order` (array of keys): ordered keys first, in that order; the rest after, by `nameOf`.
  function sortBy(list, order, keyOf, nameOf) {
    var pos = {};
    (order || []).forEach(function (k, i) { if (!Object.prototype.hasOwnProperty.call(pos, k)) pos[k] = i; });
    return (list || []).slice().sort(function (a, b) {
      var ka = keyOf(a), kb = keyOf(b);
      var ha = Object.prototype.hasOwnProperty.call(pos, ka), hb = Object.prototype.hasOwnProperty.call(pos, kb);
      if (ha && hb) return pos[ka] - pos[kb];
      if (ha !== hb) return ha ? -1 : 1;
      return String(nameOf(a)).localeCompare(String(nameOf(b)), "vi");
    });
  }
  function sameOrder(a, b) {
    return (a || []).length === (b || []).length && (a || []).every(function (x, i) { return x === b[i]; });
  }

  var orders = {};
  function rank(scope, key) {
    var o = orders[scope] || [];
    var i = o.indexOf(key);
    return i < 0 ? null : i;
  }
  function sortTags(list, scope, keyOf, nameOf) { return sortBy(list, orders[scope] || [], keyOf, nameOf); }

  var api = { moveItem: moveItem, sortBy: sortBy, sameOrder: sameOrder, rank: rank, sortTags: sortTags,
    _setOrders: function (o) { orders = o || {}; } };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (!root || typeof document === "undefined") return;
  root.JavisReorder = api;

  function t(key, vars) { try { return root.t ? root.t(key, vars) : key; } catch (e) { return key; } }
  function icon(name) { try { return root.ic ? root.ic(name) : ""; } catch (e) { return ""; } }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // Saved tag orders. Loaded once at start; pages that sort tags redraw when they change.
  function loadOrders() {
    return fetch("/ui/order", { credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (d) {
        if (d && d.orders) { orders = d.orders; announce(); }
      }).catch(function () {});
  }
  function announce() { try { root.dispatchEvent(new CustomEvent("javis:order-changed", { detail: { orders: orders } })); } catch (e) {} }
  api.load = loadOrders;
  // Save one tag list's order: (scope, keys) -> Promise<"" | error>.
  api.saveTags = function (scope, keys) {
    return post("/ui/order", { scope: scope, order: JSON.stringify(keys) }).then(function (res) {
      if (res.ok) { orders[scope] = (res.d && res.d.order) || keys; announce(); return ""; }
      return (res.d && res.d.error) || t("reorder.save_err");
    });
  };
  function post(url, body) {
    var fd = new FormData();
    Object.keys(body).forEach(function (k) { fd.append(k, body[k]); });
    return fetch(url, { method: "POST", body: fd, credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok && d && d.ok, d: d }; }); })
      .catch(function () { return { ok: false, d: { error: t("reorder.save_err") } }; });
  }
  api.post = post;

  // ---- the box ----
  function open(o) {
    close();
    var work = (o.items || []).slice(), start = work.map(function (x) { return x.id; }), saving = false;
    var m = document.createElement("div");
    m.id = "reorderBox";
    m.className = "mp-overlay open";
    m.innerHTML = '<div class="mp-box ro-box" role="dialog" aria-modal="true" aria-label="' + esc(o.title) + '">' +
      '<div class="mp-head"><div class="mp-title">' + esc(o.title) + '</div>' +
      '<button class="mp-x" type="button" data-ro-x="1" aria-label="' + esc(t("reorder.cancel")) + '">×</button></div>' +
      '<div class="ro-hint">' + esc(o.hint || t("reorder.hint")) + '</div>' +
      '<div class="bp-list ro-list"></div><div class="ro-err" role="status" hidden></div>' +
      '<div class="ro-foot"><button type="button" class="ws-btn" data-ro-x="1">' + esc(t("reorder.cancel")) + '</button>' +
      '<button type="button" class="ws-btn primary" data-ro-done="1">' + esc(t("reorder.done")) + "</button></div></div>";
    document.body.appendChild(m);
    var list = m.querySelector(".ro-list"), err = m.querySelector(".ro-err"), done = m.querySelector("[data-ro-done]");

    function row(x, i, n) {
      return '<div class="bp-row bp-move" data-i="' + i + '">' +
        '<span class="bp-grip" title="' + esc(t("reorder.drag")) + '">' + icon("arrow-up-down") + "</span>" +
        (x.icon ? '<span class="ro-ic">' + icon(x.icon) + "</span>" : "") +
        '<span class="bp-name"><span class="bp-label">' + esc(x.label) + "</span></span>" +
        '<button type="button" class="bp-arrow" data-move="-1" aria-label="' + esc(t("reorder.up")) + '"' + (i === 0 ? " disabled" : "") + ">" + icon("arrow-up") + "</button>" +
        '<button type="button" class="bp-arrow" data-move="1" aria-label="' + esc(t("reorder.down")) + '"' + (i === n - 1 ? " disabled" : "") + ">" + icon("arrow-down") + "</button></div>";
    }
    function draw() { list.innerHTML = work.map(function (x, i) { return row(x, i, work.length); }).join(""); }
    draw();

    m.addEventListener("click", function (e) {
      if (e.target === m || (e.target.closest && e.target.closest("[data-ro-x]"))) { close(); return; }
      var arrow = e.target.closest && e.target.closest(".bp-arrow");
      if (arrow) {
        var i = +arrow.closest(".bp-row").dataset.i, d = +arrow.dataset.move;
        work = moveItem(work, i, i + d);
        draw();
        var again = list.querySelector('.bp-row[data-i="' + (i + d) + '"] .bp-arrow[data-move="' + d + '"]');
        if (again && !again.disabled) again.focus();
        return;
      }
      if (e.target.closest && e.target.closest("[data-ro-done]")) finish();
    });
    m.addEventListener("keydown", function (e) { if (e.key === "Escape") { e.stopPropagation(); close(); } });
    list.addEventListener("pointerdown", grab);

    function finish() {
      if (saving) return;
      var ids = work.map(function (x) { return x.id; });
      if (sameOrder(ids, start)) { close(); return; }
      saving = true; done.disabled = true; err.hidden = true;
      Promise.resolve(o.save(ids)).then(function (msg) {
        saving = false; done.disabled = false;
        if (msg) { err.textContent = msg; err.hidden = false; return; }
        close();
      }, function () {
        saving = false; done.disabled = false;
        err.textContent = t("reorder.save_err"); err.hidden = false;
      });
    }

    // Drag by the handle (mouse, pen or finger), same feel as the brain picker: the row follows the pointer, the
    // others make room by their midpoint.
    function grab(e) {
      var grip = e.target.closest && e.target.closest(".bp-grip");
      if (!grip) return;
      var r = grip.closest(".bp-row");
      e.preventDefault();
      var rows = Array.prototype.slice.call(list.querySelectorAll(".bp-row"));
      var from = rows.indexOf(r), to = from, startY = e.clientY;
      var mids = rows.map(function (x) { var b = x.getBoundingClientRect(); return b.top + b.height / 2; });
      var h = r.getBoundingClientRect().height;
      r.classList.add("dragging");
      try { grip.setPointerCapture(e.pointerId); } catch (er) {}
      function move(ev) {
        var dy = ev.clientY - startY;
        r.style.transform = "translateY(" + dy + "px)";
        var y = mids[from] + dy;
        to = from;
        for (var k = 0; k < mids.length; k++) { if (k < from && y < mids[k]) { to = k; break; } }
        for (var j = mids.length - 1; j > from; j--) { if (y > mids[j]) { to = j; break; } }
        rows.forEach(function (x, k) {
          if (x === r) return;
          var shift = 0;
          if (from < to && k > from && k <= to) shift = -h;
          if (from > to && k < from && k >= to) shift = h;
          x.style.transform = shift ? "translateY(" + shift + "px)" : "";
        });
      }
      function up() {
        grip.removeEventListener("pointermove", move);
        grip.removeEventListener("pointerup", up);
        grip.removeEventListener("pointercancel", up);
        rows.forEach(function (x) { x.style.transform = ""; });
        r.classList.remove("dragging");
        if (to !== from) work = moveItem(work, from, to);
        draw();
      }
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", up);
      grip.addEventListener("pointercancel", up);
    }
    var first = list.querySelector(".bp-arrow:not([disabled])");
    if (first) first.focus();
  }
  function close() {
    var m = document.getElementById("reorderBox");
    if (m) m.remove();
  }
  api.open = open;
  api.close = close;

  loadOrders();
})(typeof window !== "undefined" ? window : null);
