/* Searchable agent picker.
 *
 * Owner, 25/10/2026: "the agent choice has no search and the UI looks bad". A native <select> whose options read
 * "name - long description" opens as a wall of truncated lines with no way to search. This module progressively
 * enhances such a <select>:
 *
 * - the <select> stays in the DOM (hidden) and remains the source of truth, so code that reads `.value` or listens
 *   to `change` keeps working untouched;
 * - a button shows the chosen agent's name and a muted one-line description;
 * - opening it shows a popover (desktop) or a bottom sheet (phone) with a search box that matches name, slug and
 *   description, ignoring case and Vietnamese diacritics;
 * - keyboard: arrows move, Enter picks, Escape closes; a click outside closes.
 *
 * Each <option> may carry `data-name` (full name) and `data-desc` (full description). Without them the option text
 * is used as the name. Usage:
 *
 *     JavisAgentPicker.enhance(selectEl, { title: t("ap.title"), placeholder: t("ap.search_ph") });
 *
 * The pure helpers (fold, itemsFrom, filterItems, rowsHtml, choose) need no DOM and are tested in a vm by
 * tests/js/test_agent_picker.js.
 */
(function () {
  "use strict";

  var W = typeof window !== "undefined" ? window : {};

  function tr(key, vars) {
    var s = W.t ? W.t(key, vars) : key;
    if (vars) {
      s = String(s).replace(/\{(\w+)\}/g, function (m, k) {
        return Object.prototype.hasOwnProperty.call(vars, k) ? String(vars[k]) : m;
      });
    }
    return s;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function ic(name) { return W.ic ? W.ic(name) : ""; }

  // Lowercase, strip combining marks after NFD, and map the Vietnamese d-with-stroke (not a combining mark) to d,
  // so "dao dien" finds the same words written with Vietnamese marks.
  function fold(s) {
    s = String(s == null ? "" : s);
    if (s.normalize) s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    return s.replace(/\u0111/g, "d").replace(/\u0110/g, "D").toLowerCase().replace(/\s+/g, " ").trim();
  }

  // One item per <option>: { value, name, desc, disabled }.
  function itemsFrom(select) {
    var out = [];
    var opts = (select && select.options) || [];
    for (var i = 0; i < opts.length; i++) {
      var o = opts[i];
      var ds = o.dataset || {};
      out.push({
        value: String(o.value == null ? "" : o.value),
        name: String(ds.name || o.textContent || o.text || o.value || "").trim(),
        desc: String(ds.desc || "").trim(),
        disabled: !!o.disabled,
      });
    }
    return out;
  }

  // Every word of the query must appear in name, slug (value) or description. Items whose NAME holds every word
  // come first, the rest keep their original order.
  function filterItems(items, query) {
    var words = fold(query).split(" ").filter(Boolean);
    if (!words.length) return items.slice();
    var inName = [], inRest = [];
    items.forEach(function (it) {
      var name = fold(it.name);
      var hay = name + " " + fold(it.value) + " " + fold(it.value.replace(/[-_]+/g, " ")) + " " + fold(it.desc);
      if (!words.every(function (w) { return hay.indexOf(w) >= 0; })) return;
      (words.every(function (w) { return name.indexOf(w) >= 0; }) ? inName : inRest).push(it);
    });
    return inName.concat(inRest);
  }

  function rowsHtml(items, selected, active, idPrefix) {
    return items.map(function (it, i) {
      var on = it.value === selected;
      return '<div class="ap-row' + (on ? " is-sel" : "") + (i === active ? " is-active" : "") +
        (it.disabled ? " is-off" : "") + '" role="option" id="' + esc(idPrefix + "-" + i) + '" data-idx="' + i +
        '" aria-selected="' + (on ? "true" : "false") + '"' + (it.disabled ? ' aria-disabled="true"' : "") + ">" +
        '<span class="ap-row-txt"><span class="ap-row-name">' + esc(it.name) + "</span>" +
        (it.desc ? '<span class="ap-row-desc">' + esc(it.desc) + "</span>" : "") + "</span>" +
        '<span class="ap-row-check">' + (on ? ic("check") : "") + "</span></div>";
    }).join("");
  }

  // Sets the hidden select's value and fires `change` (and `input`) the way a real pick would. Returns true when
  // the value actually changed.
  function choose(select, value) {
    if (!select || String(select.value) === String(value)) return false;
    select.value = value;
    ["input", "change"].forEach(function (type) {
      var ev;
      if (typeof Event === "function") ev = new Event(type, { bubbles: true });
      else if (typeof document !== "undefined") { ev = document.createEvent("Event"); ev.initEvent(type, true, false); }
      if (ev && select.dispatchEvent) select.dispatchEvent(ev);
    });
    return true;
  }

  // ---------------------------------------------------------------- browser part

  var seq = 0;
  var openState = null;   // the one popover open at a time

  function isPhone() {
    try { return W.matchMedia("(max-width: 640px)").matches; } catch (e) { return false; }
  }

  function close(refocus) {
    var s = openState;
    if (!s) return;
    openState = null;
    W.removeEventListener("resize", s.onResize);
    if (s.layer.parentNode) s.layer.parentNode.removeChild(s.layer);
    s.btn.setAttribute("aria-expanded", "false");
    if (refocus) { try { s.btn.focus(); } catch (e) {} }
  }

  function place(s) {
    var pop = s.pop;
    if (s.phone) { pop.style.cssText = ""; return; }
    var r = s.btn.getBoundingClientRect();
    var vw = W.innerWidth, vh = W.innerHeight, gap = 6, edge = 8;
    var w = Math.min(Math.max(r.width, 340), vw - edge * 2);
    var left = Math.min(Math.max(r.left, edge), vw - w - edge);
    var below = vh - r.bottom - gap - edge, above = r.top - gap - edge;
    var down = below >= 300 || below >= above;
    var h = Math.min(440, down ? below : above);
    pop.style.left = left + "px";
    pop.style.width = w + "px";
    pop.style.maxHeight = h + "px";
    pop.style.top = down ? (r.bottom + gap) + "px" : "";
    pop.style.bottom = down ? "" : (vh - r.top + gap) + "px";
  }

  function open(p, initial) {
    if (openState) close(false);
    var phone = isPhone();
    var id = "ap" + (++seq);
    var layer = document.createElement("div");
    layer.className = "ap-layer" + (phone ? " is-phone" : "");
    layer.innerHTML =
      '<div class="ap-pop" role="dialog" aria-modal="true" aria-label="' + esc(p.opts.title || tr("ap.title")) + '">' +
        '<div class="ap-head"><span class="ap-title">' + esc(p.opts.title || tr("ap.title")) + "</span>" +
          '<button type="button" class="ap-x" aria-label="' + esc(tr("ap.close")) + '">' + ic("x") + "</button></div>" +
        '<div class="ap-search">' + ic("search") +
          '<input type="search" class="ap-q" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="true"' +
          ' aria-autocomplete="list" aria-controls="' + id + '-list" placeholder="' +
          esc(p.opts.placeholder || tr("ap.search_ph")) + '"></div>' +
        '<div class="ap-list" role="listbox" id="' + id + '-list"></div>' +
        '<div class="ap-empty" hidden></div>' +
      "</div>";
    document.body.appendChild(layer);
    var s = {
      p: p, btn: p.btn, layer: layer, pop: layer.querySelector(".ap-pop"), q: layer.querySelector(".ap-q"),
      list: layer.querySelector(".ap-list"), empty: layer.querySelector(".ap-empty"), id: id, phone: phone,
      items: itemsFrom(p.select), shown: [], active: -1,
    };
    s.onResize = function () { if (!s.phone) place(s); };
    openState = s;
    p.btn.setAttribute("aria-expanded", "true");
    W.addEventListener("resize", s.onResize);

    function render(keepActive) {
      s.shown = filterItems(s.items, s.q.value);
      var sel = String(p.select.value);
      if (!keepActive) {
        s.active = -1;
        if (!s.q.value.trim()) s.shown.forEach(function (it, i) { if (it.value === sel) s.active = i; });
        if (s.active < 0 && s.shown.length) s.active = 0;
      }
      s.list.innerHTML = rowsHtml(s.shown, sel, s.active, id);
      s.empty.hidden = s.shown.length > 0;
      s.empty.textContent = s.shown.length ? "" : tr("ap.empty", { q: s.q.value.trim() });
      s.q.setAttribute("aria-activedescendant", s.active >= 0 ? id + "-" + s.active : "");
      scrollToActive(!keepActive && !s.q.value.trim());
    }
    // On first open the chosen row sits mid-list so the agents around it show too; arrow keys scroll just enough.
    function scrollToActive(center) {
      var row = s.list.querySelector(".ap-row.is-active");
      if (!row) return;
      if (center) s.list.scrollTop = Math.max(0, row.offsetTop - (s.list.clientHeight - row.offsetHeight) / 2);
      else if (row.scrollIntoView) row.scrollIntoView({ block: "nearest" });
    }
    function setActive(i) {
      if (!s.shown.length) return;
      s.active = Math.max(0, Math.min(s.shown.length - 1, i));
      var rows = s.list.querySelectorAll(".ap-row");
      for (var k = 0; k < rows.length; k++) rows[k].classList.toggle("is-active", k === s.active);
      s.q.setAttribute("aria-activedescendant", id + "-" + s.active);
      scrollToActive();
    }
    function pick(i) {
      var it = s.shown[i];
      if (!it || it.disabled) return;
      choose(p.select, it.value);
      p.refresh();
      close(true);
    }

    s.q.addEventListener("input", function () { render(false); });
    s.q.addEventListener("keydown", function (e) {
      var k = e.key;
      if (k === "ArrowDown") { e.preventDefault(); setActive(s.active + 1); }
      else if (k === "ArrowUp") { e.preventDefault(); setActive(s.active - 1); }
      else if (k === "PageDown") { e.preventDefault(); setActive(s.active + 6); }
      else if (k === "PageUp") { e.preventDefault(); setActive(s.active - 6); }
      else if (k === "Enter") { e.preventDefault(); if (s.active >= 0) pick(s.active); }
      else if (k === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); }
      else if (k === "Tab") { close(false); }
    });
    s.list.addEventListener("mousemove", function (e) {
      var row = e.target.closest && e.target.closest(".ap-row");
      if (row && +row.dataset.idx !== s.active) setActive(+row.dataset.idx);
    });
    s.list.addEventListener("click", function (e) {
      var row = e.target.closest && e.target.closest(".ap-row");
      if (row) pick(+row.dataset.idx);
    });
    layer.querySelector(".ap-x").addEventListener("click", function () { close(true); });
    // A press on the layer itself (outside the panel) closes; mousedown so a drag that ends outside does not.
    layer.addEventListener("mousedown", function (e) { if (e.target === layer) { e.preventDefault(); close(true); } });
    layer.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); }
    });

    if (initial) s.q.value = initial;
    place(s);
    render(false);
    // Autofocus only on desktop: on a phone it would pop the keyboard over half the list before the owner has
    // even seen it. The sheet still traps Escape and the close button.
    if (!phone || initial) { try { s.q.focus(); } catch (e) {} }
    else { try { s.pop.setAttribute("tabindex", "-1"); s.pop.focus(); } catch (e) {} }
  }

  function enhance(select, opts) {
    if (!select || typeof document === "undefined") return null;
    if (select._agentPicker) { select._agentPicker.refresh(); return select._agentPicker; }
    opts = opts || {};
    var wrap = document.createElement("div");
    wrap.className = "agent-picker" + (opts.className ? " " + opts.className : "");
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ap-btn";
    btn.setAttribute("aria-haspopup", "dialog");
    btn.setAttribute("aria-expanded", "false");
    if (select.id) btn.id = select.id + "Btn";
    var aria = select.getAttribute("aria-label");
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(btn);
    wrap.appendChild(select);     // still in the DOM, still found by #id or .class
    select.hidden = true;
    select.classList.add("ap-native");
    select.setAttribute("tabindex", "-1");
    select.setAttribute("aria-hidden", "true");
    // A <label for="select"> now points at a hidden control: move it onto the button.
    if (select.id) {
      var lab = document.querySelector('label[for="' + select.id + '"]');
      if (lab) lab.setAttribute("for", btn.id);
    }

    var p = { select: select, btn: btn, wrap: wrap, opts: opts };
    p.refresh = function () {
      var items = itemsFrom(select);
      var cur = null;
      for (var i = 0; i < items.length; i++) if (items[i].value === String(select.value)) { cur = items[i]; break; }
      var name = cur ? cur.name : tr("ap.none");
      btn.innerHTML = '<span class="ap-btn-txt"><span class="ap-btn-name">' + esc(name) + "</span>" +
        (cur && cur.desc && opts.showDesc !== false ? '<span class="ap-btn-desc">' + esc(cur.desc) + "</span>" : "") +
        "</span>" + '<span class="ap-btn-chev">' + ic("chevron-down") + "</span>";
      btn.title = cur && cur.desc ? cur.name + ": " + cur.desc : name;
      if (aria) btn.setAttribute("aria-label", aria + ": " + name);
      btn.disabled = !!select.disabled;
    };
    p.open = function (q) { open(p, q); };
    p.close = function () { close(false); };

    btn.addEventListener("click", function () {
      if (openState && openState.p === p) close(true); else open(p, "");
    });
    btn.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); open(p, ""); }
      // Typing a letter on the closed button starts a search with it.
      else if (e.key && e.key.length === 1 && e.key !== " " && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault(); open(p, e.key);
      }
    });
    select.addEventListener("change", p.refresh);
    // Code that rebuilds the options (or flips `selected`) keeps the button in sync without knowing about it.
    if (typeof MutationObserver === "function") {
      new MutationObserver(p.refresh).observe(select, { childList: true, subtree: true, attributes: true,
        attributeFilter: ["selected", "disabled", "data-name", "data-desc"] });
    }
    select._agentPicker = p;
    p.refresh();
    return p;
  }

  var api = { enhance: enhance, close: close, fold: fold, itemsFrom: itemsFrom, filterItems: filterItems,
    rowsHtml: rowsHtml, choose: choose };
  W.JavisAgentPicker = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
