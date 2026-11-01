/* brain-picker.js - the brain picker, drawn by Javis instead of the browser (0.431.0).

   Owner, 2026-11-01, relaying a user with a phone screenshot: the brain list "shows one way on one device and another
   way on the next", and the order could not be changed. The list was a plain <select>, so every browser drew its own
   menu (an iOS wheel, an Android sheet, a desktop dropdown), and the order came from folder names.

   The <select id="graphSource"> stays as the single source of truth: about ten modules read its value and options and
   listen for its "change". It is hidden visually and this file draws over it:
   - a button showing the current brain and its note count;
   - a panel listing the brains (a dropdown on a wide screen, a sheet from the bottom on a phone), with search when the
     list is long, and external folders in their own group;
   - a Reorder mode: drag the handle, or use the up / down arrows, then Done saves the order to the server
     (POST /brains/order, server/brain_order.py) so every device shows the same order.
   Picking a brain sets the select's value and fires its "change", exactly as choosing in the old menu did.

   The pure part (moveItem, orderFromOptions) is tested in node by tests/js/test_brain_picker.js. No em dash here. */
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
  // Folder names of the listed brains, in the order shown (what POST /brains/order takes).
  function orderFromOptions(opts) {
    var out = [];
    (opts || []).forEach(function (o) {
      var n = o && (o.brainName || (o.dataset && o.dataset.brainName));
      if (n && out.indexOf(n) < 0) out.push(n);
    });
    return out;
  }
  var api = { moveItem: moveItem, orderFromOptions: orderFromOptions };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (!root || typeof document === "undefined") return;
  root.JavisBrainPicker = api;

  var sel = document.getElementById("graphSource");
  if (!sel) return;

  function t(key, vars, fallback) {
    try {
      var s = root.t ? root.t(key, vars) : "";
      if (s && s !== key) return s;
    } catch (e) {}
    return String(fallback || key).replace(/\{(\w+)\}/g, function (_, k) { return vars && vars[k] != null ? vars[k] : ""; });
  }
  function icon(name) { try { return root.ic ? root.ic(name) : ""; } catch (e) { return ""; } }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function isPhone() { return root.matchMedia ? root.matchMedia("(max-width: 860px)").matches : false; }

  // One entry per <option>: what the button and the panel need.
  function entries() {
    var out = [];
    Array.prototype.forEach.call(sel.options, function (o) {
      var grp = o.parentNode && o.parentNode.tagName === "OPTGROUP" ? o.parentNode.label : "";
      var name = o.dataset.brainLabel || o.textContent.replace(/\s+·\s+[\d.,]+\+?\s*$/, "").trim();
      out.push({ value: o.value, label: name, notes: o.dataset.notes || "", group: grp,
                 brainName: o.dataset.brainName || "", movable: !grp && !!o.dataset.brainName });
    });
    return out;
  }
  function current() {
    var all = entries();
    for (var i = 0; i < all.length; i++) if (all[i].value === sel.value) return all[i];
    return all[0] || { label: "", notes: "" };
  }
  function notesText(n) { return n ? t("bpick.notes", { n: n }, "{n} notes") : ""; }

  // ---- the button over the select ----
  sel.classList.add("bp-native");
  sel.setAttribute("tabindex", "-1");
  sel.setAttribute("aria-hidden", "true");
  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "bp-btn";
  btn.setAttribute("aria-haspopup", "listbox");
  btn.setAttribute("aria-expanded", "false");
  sel.parentNode.insertBefore(btn, sel.nextSibling);
  function drawButton() {
    var c = current();
    btn.innerHTML = '<span class="bp-btn-name">' + esc(c.label) + "</span>" +
      (c.notes ? '<span class="bp-btn-n">' + esc(c.notes) + "</span>" : "") +
      '<span class="bp-btn-chev">' + icon("chevron-down") + "</span>";
    btn.title = c.label + (c.notes ? " · " + notesText(c.notes) : "");
    btn.setAttribute("aria-label", t("bpick.title", null, "Choose a brain") + ": " + c.label);
  }
  drawButton();
  sel.addEventListener("change", drawButton);
  // Some code sets sel.value directly without a "change" (restoring the saved brain, a session on another brain).
  // Wrap this one element's value setter so the button follows every way the value can change.
  try {
    var desc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
    Object.defineProperty(sel, "value", {
      configurable: true,
      get: function () { return desc.get.call(this); },
      set: function (v) { desc.set.call(this, v); drawButton(); }
    });
  } catch (e) {}
  try {
    new MutationObserver(function () { drawButton(); if (open) drawList(); })
      .observe(sel, { childList: true, subtree: true, characterData: true, attributes: true });
  } catch (e) {}
  root.addEventListener("javis:i18n", drawButton);

  // ---- the panel ----
  var open = false, reorder = false, query = "", work = null, saving = false;
  var shade = null, pop = null, listEl = null, searchEl = null, headBtn = null, hintEl = null, errEl = null;

  function build() {
    if (pop) return;
    shade = document.createElement("div");
    shade.className = "bp-shade";
    shade.addEventListener("click", close);
    pop = document.createElement("div");
    pop.className = "bp-pop";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-modal", "true");
    pop.innerHTML =
      '<div class="bp-head"><span class="bp-title"></span><button type="button" class="bp-head-btn"></button></div>' +
      '<div class="bp-search-wrap"><span class="bp-search-ic">' + icon("search") + '</span>' +
      '<input type="search" class="bp-search" autocomplete="off" spellcheck="false"></div>' +
      '<div class="bp-hint" hidden></div><div class="bp-err" hidden></div>' +
      '<div class="bp-list" role="listbox"></div>';
    listEl = pop.querySelector(".bp-list");
    searchEl = pop.querySelector(".bp-search");
    headBtn = pop.querySelector(".bp-head-btn");
    hintEl = pop.querySelector(".bp-hint");
    errEl = pop.querySelector(".bp-err");
    searchEl.addEventListener("input", function () { query = searchEl.value; drawList(); });
    searchEl.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); focusRow(0); }
      if (e.key === "Enter") { var first = listEl.querySelector(".bp-row"); if (first) { e.preventDefault(); pick(first.dataset.value); } }
    });
    headBtn.addEventListener("click", function () { if (reorder) finishReorder(); else startReorder(); });
    listEl.addEventListener("click", onListClick);
    listEl.addEventListener("keydown", onListKey);
    listEl.addEventListener("pointerdown", onGrab);
    document.body.appendChild(shade);
    document.body.appendChild(pop);
  }

  function drawHead() {
    pop.querySelector(".bp-title").textContent = reorder ? t("bpick.reorder_title", null, "Reorder brains") : t("bpick.title", null, "Choose a brain");
    headBtn.innerHTML = reorder ? esc(t("bpick.done", null, "Done")) : icon("arrow-up-down") + " " + esc(t("bpick.reorder", null, "Reorder"));
    headBtn.classList.toggle("primary", reorder);
    headBtn.disabled = saving;
    headBtn.hidden = !reorder && entries().filter(function (x) { return x.movable; }).length < 2;
    var many = entries().length > 6;
    pop.querySelector(".bp-search-wrap").hidden = reorder || !many;
    searchEl.placeholder = t("bpick.search", null, "Find a brain");
    hintEl.hidden = !reorder;
    hintEl.textContent = t("bpick.hint", null, "Drag the handle or use the arrows. The order is saved for every device.");
  }

  function fold(s) {
    return String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[\u0110\u0111]/g, "d").toLowerCase();
  }

  function rowHtml(x, i, n) {
    var on = x.value === sel.value;
    var sub = notesText(x.notes);
    if (reorder) {
      return '<div class="bp-row bp-move" data-i="' + i + '" data-value="' + esc(x.value) + '">' +
        '<span class="bp-grip" title="' + esc(t("bpick.drag", null, "Drag to move")) + '">' + icon("arrow-up-down") + "</span>" +
        '<span class="bp-name"><span class="bp-label">' + esc(x.label) + "</span>" +
        (sub ? '<span class="bp-sub">' + esc(sub) + "</span>" : "") + "</span>" +
        '<button type="button" class="bp-arrow" data-move="-1" aria-label="' + esc(t("bpick.up", null, "Move up")) + '"' + (i === 0 ? " disabled" : "") + ">" + icon("arrow-up") + "</button>" +
        '<button type="button" class="bp-arrow" data-move="1" aria-label="' + esc(t("bpick.down", null, "Move down")) + '"' + (i === n - 1 ? " disabled" : "") + ">" + icon("arrow-down") + "</button>" +
        "</div>";
    }
    return '<div class="bp-row' + (on ? " on" : "") + '" role="option" tabindex="0" aria-selected="' + on + '" data-value="' + esc(x.value) + '">' +
      '<span class="bp-dot">' + esc((x.label || "?").trim().charAt(0).toUpperCase()) + "</span>" +
      '<span class="bp-name"><span class="bp-label">' + esc(x.label) + "</span>" +
      (sub ? '<span class="bp-sub">' + esc(sub) + "</span>" : "") + "</span>" +
      '<span class="bp-check">' + (on ? icon("check") : "") + "</span></div>";
  }

  function drawList() {
    if (!pop) return;
    drawHead();
    if (reorder) {
      listEl.innerHTML = work.map(function (x, i) { return rowHtml(x, i, work.length); }).join("");
      return;
    }
    var q = fold(query.trim());
    var all = entries().filter(function (x) { return !q || fold(x.label).indexOf(q) >= 0; });
    var html = "", lastGroup = "";
    all.forEach(function (x) {
      if (x.group && x.group !== lastGroup) { html += '<div class="bp-group">' + esc(x.group) + "</div>"; lastGroup = x.group; }
      html += rowHtml(x);
    });
    listEl.innerHTML = html || '<div class="bp-empty">' + esc(t("bpick.empty", null, "No brain matches.")) + "</div>";
  }

  function place() {
    if (isPhone()) { pop.classList.add("sheet"); pop.style.left = pop.style.top = pop.style.width = ""; return; }
    pop.classList.remove("sheet");
    var r = btn.getBoundingClientRect();
    var w = Math.max(300, Math.min(380, r.width + 120));
    var left = Math.min(Math.max(8, r.left), root.innerWidth - w - 8);
    pop.style.width = w + "px";
    pop.style.left = left + "px";
    pop.style.top = Math.min(r.bottom + 6, root.innerHeight - 200) + "px";
  }

  function show() {
    build();
    open = true; reorder = false; query = ""; searchEl.value = ""; errEl.hidden = true;
    drawList();
    place();
    shade.classList.add("open"); pop.classList.add("open");
    btn.setAttribute("aria-expanded", "true");
    document.addEventListener("keydown", onKey, true);
    root.addEventListener("resize", place);
    // Focus the current brain (or the search box on a long list), never on a phone: it would raise the keyboard.
    if (!isPhone()) {
      if (!pop.querySelector(".bp-search-wrap").hidden) searchEl.focus();
      else { var on = listEl.querySelector(".bp-row.on") || listEl.querySelector(".bp-row"); if (on) on.focus(); }
    }
    var cur = listEl.querySelector(".bp-row.on");
    if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "nearest" });
  }
  function close() {
    if (!open) return;
    open = false; reorder = false; work = null;
    shade.classList.remove("open"); pop.classList.remove("open");
    btn.setAttribute("aria-expanded", "false");
    document.removeEventListener("keydown", onKey, true);
    root.removeEventListener("resize", place);
    if (!isPhone()) btn.focus();
  }
  btn.addEventListener("click", function () { if (open) close(); else show(); });

  function pick(value) {
    close();
    if (value == null || value === sel.value) return;
    sel.value = value;
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function onKey(e) {
    if (e.key === "Escape") {
      e.preventDefault(); e.stopPropagation();
      if (reorder) { reorder = false; work = null; drawList(); } else close();
    }
  }
  function focusRow(i) {
    var rows = listEl.querySelectorAll(".bp-row[tabindex]");
    if (rows[i]) rows[i].focus();
  }
  function onListKey(e) {
    var row = e.target.closest && e.target.closest(".bp-row[tabindex]");
    if (!row) return;
    var rows = Array.prototype.slice.call(listEl.querySelectorAll(".bp-row[tabindex]"));
    var i = rows.indexOf(row);
    if (e.key === "ArrowDown") { e.preventDefault(); focusRow(Math.min(rows.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (i === 0 && !pop.querySelector(".bp-search-wrap").hidden) searchEl.focus(); else focusRow(Math.max(0, i - 1));
    }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(row.dataset.value); }
  }
  function onListClick(e) {
    var arrow = e.target.closest && e.target.closest(".bp-arrow");
    if (arrow && reorder) {
      var i = +arrow.closest(".bp-row").dataset.i;
      work = moveItem(work, i, i + (+arrow.dataset.move));
      drawList();
      var again = listEl.querySelector('.bp-row[data-i="' + (i + (+arrow.dataset.move)) + '"] .bp-arrow[data-move="' + arrow.dataset.move + '"]');
      if (again && !again.disabled) again.focus();
      return;
    }
    if (reorder) return;
    var row = e.target.closest && e.target.closest(".bp-row");
    if (row) pick(row.dataset.value);
  }

  // ---- reorder ----
  function startReorder() {
    work = entries().filter(function (x) { return x.movable; });
    reorder = true; errEl.hidden = true;
    drawList();
  }
  function finishReorder() {
    var order = orderFromOptions(work);
    var before = orderFromOptions(entries().filter(function (x) { return x.movable; }));
    if (order.join("\n") === before.join("\n")) { reorder = false; work = null; drawList(); return; }
    saving = true; drawHead();
    var fd = new FormData();
    fd.append("order", JSON.stringify(order));
    fetch("/brains/order", { method: "POST", body: fd })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok && d && d.ok, d: d }; }); })
      .then(function (res) {
        saving = false;
        if (!res.ok) throw new Error((res.d && res.d.error) || "");
        reorder = false; work = null;
        var reload = root.JavisBrains && root.JavisBrains.reload;
        return Promise.resolve(reload ? reload() : null).then(function () { if (open) drawList(); });
      })
      .catch(function (e) {
        saving = false;
        errEl.textContent = (e && e.message) || t("bpick.save_err", null, "Could not save the order.");
        errEl.hidden = false;
        if (open) drawHead();
      });
  }

  // Drag by the handle (mouse, pen or finger). The row follows the pointer; others make room by midpoint.
  function onGrab(e) {
    if (!reorder) return;
    var grip = e.target.closest && e.target.closest(".bp-grip");
    if (!grip) return;
    var row = grip.closest(".bp-row");
    e.preventDefault();
    var rows = Array.prototype.slice.call(listEl.querySelectorAll(".bp-row"));
    var from = rows.indexOf(row), to = from;
    var startY = e.clientY;
    var mids = rows.map(function (r) { var b = r.getBoundingClientRect(); return b.top + b.height / 2; });
    var h = row.getBoundingClientRect().height;
    row.classList.add("dragging");
    try { grip.setPointerCapture(e.pointerId); } catch (err) {}
    function move(ev) {
      var dy = ev.clientY - startY;
      row.style.transform = "translateY(" + dy + "px)";
      var y = mids[from] + dy;
      to = from;
      for (var k = 0; k < mids.length; k++) {
        if (k < from && y < mids[k]) { to = k; break; }
      }
      for (var j = mids.length - 1; j > from; j--) {
        if (y > mids[j]) { to = j; break; }
      }
      rows.forEach(function (r, k) {
        if (r === row) return;
        var shift = 0;
        if (from < to && k > from && k <= to) shift = -h;
        if (from > to && k < from && k >= to) shift = h;
        r.style.transform = shift ? "translateY(" + shift + "px)" : "";
      });
    }
    function up() {
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", up);
      grip.removeEventListener("pointercancel", up);
      rows.forEach(function (r) { r.style.transform = ""; });
      row.classList.remove("dragging");
      if (to !== from) work = moveItem(work, from, to);
      drawList();
    }
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
    grip.addEventListener("pointercancel", up);
  }
})(typeof window !== "undefined" ? window : null);
