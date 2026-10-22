/* composer-plus.js - the composer's "+" menu (0.153.0).
 * One registry: a new feature only calls JavisComposerMenu.register({...}), the composer is not touched.
 * Items are `run` (click and close), `submenu` (returns rows) or `panel` (draws its own body, 0.158.0).
 * Pure parts are exported for node tests.
 */
(function () {
  "use strict";

  function createRegistry() {
    var items = [];
    return {
      register: function (it) {
        items = items.filter(function (x) { return x.id !== it.id; });
        items.push(it);
        items.sort(function (a, b) { return (a.order || 0) - (b.order || 0); });
      },
      list: function () { return items.slice(); },
    };
  }
  // Left arrow goes back to the top menu, except while typing in a search box (it moves the cursor there).
  function shouldGoBack(e, hasBack) {
    var tag = e && e.target && e.target.tagName;
    return !!(e && e.key === "ArrowLeft" && hasBack && tag !== "INPUT" && tag !== "TEXTAREA");
  }
  // A file picked from the brain: images need a /files/raw url (path relative to the browse ceiling,
  // as /files/search returns it), otherwise the bubble renders them as "image expired".
  function brainAttachment(r, rel, brainPath) {
    var a = { path: r.path, name: r.name, size: r.size || 0, kind: r.kind || "file" };
    if (a.kind === "image") a.url = "/files/raw?brain=" + encodeURIComponent(brainPath) + "&path=" + encodeURIComponent(rel);
    return a;
  }

  var pure = { createRegistry: createRegistry, shouldGoBack: shouldGoBack, brainAttachment: brainAttachment };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;

  var reg = createRegistry();
  function tw(k, v) { return window.t ? window.t(k, v) : k; }
  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function brain() { try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; } catch (e) { return "brain"; } }
  function getJson(url) { return fetch(url, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); }
  function input() { return $("chatInput"); }

  function insertToken(text) {
    var el = input();
    if (!el) return;
    el.focus();
    var a = el.selectionStart || 0, b = el.selectionEnd || 0, v = el.value;
    var before = v.slice(0, a);
    var lead = before && !/\s$/.test(before) ? " " : "";
    el.value = before + lead + text + v.slice(b);
    var pos = (before + lead + text).length;
    el.setSelectionRange(pos, pos);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // ---- menu frame ----
  var menu = null, btn = null, view = [], active = 0;
  function isOpen() { return !!menu && !menu.hidden; }
  function close() {
    if (!menu) return;
    menu.hidden = true; menu.innerHTML = "";
    if (btn) btn.setAttribute("aria-expanded", "false");
  }
  function closeOthers() {
    try { var mb = $("mbPop"); if (mb) mb.hidden = true; } catch (e) {}
    try { var ep = $("effPop"); if (ep && !ep.hidden) { var eb = $("effBtn"); if (eb) eb.click(); } } catch (e) {}
  }
  function render(rows, title) {
    view = rows; active = 0;
    var head = title ? '<button type="button" class="cp-mi cp-back" data-back="1">' + ICON.back + '<span>' + esc(title) + '</span></button><div class="cp-sep"></div>' : "";
    menu.innerHTML = head + rows.map(function (r, i) {
      if (r.sep) return '<div class="cp-sep"></div>';
      var dot = r.dot ? '<span class="cp-dot cp-dot-' + r.dot + '"></span>' : "";
      return '<button type="button" class="cp-mi" role="menuitem" data-i="' + i + '">' + (r.icon || dot) +
        '<span class="cp-mi-lbl">' + esc(r.label) + '</span>' + (r.hint ? '<span class="cp-mi-hint' + (r.warn ? " cp-warn" : "") + '">' + esc(r.hint) + "</span>" : "") +
        (r.sub ? ICON.chevron : "") + "</button>";
    }).join("");
    focusRow(0);
  }
  function rowsEls() { return menu ? Array.prototype.slice.call(menu.querySelectorAll(".cp-mi")) : []; }
  function focusRow(i) { var els = rowsEls(); if (!els.length) return; active = (i + els.length) % els.length; els[active].focus(); }
  function topRows() {
    return reg.list().map(function (it) {
      return { icon: it.icon, label: tw(it.label), hint: it.hint ? it.hint() : "", warn: !!it.warn, sub: !!(it.submenu || it.panel), item: it };
    });
  }
  function open() {
    if (!menu || !btn) return;
    closeOthers();
    menu.hidden = false; btn.setAttribute("aria-expanded", "true");
    render(topRows());
    refreshConnHealth();
  }
  // The "Connections" row hint counts connections that need reconnecting. Re-read it each time
  // the menu opens (cheap, cached on the server) and redraw the top rows if it changed.
  function refreshConnHealth() {
    getJson("/connect/health").then(function (d) {
      var h = (d && d.health) || {};
      // A source still in its first start (kind "starting") is not broken: leave it out.
      var n = Object.keys(h).filter(function (k) { return h[k] && h[k].ok === false && h[k].kind !== "starting"; }).length;
      if (n === badConn) return;
      badConn = n;
      if (isOpen() && !menu.querySelector("[data-back]")) render(topRows());
    });
  }
  // Panel items draw their own body (search box, custom rows) under a back row.
  function openPanel(it) {
    view = []; active = 0;
    menu.innerHTML = '<button type="button" class="cp-mi cp-back" data-back="1">' + ICON.back + "<span>" + esc(tw(it.label)) + "</span></button>" +
      '<div class="cp-sep"></div><div class="cp-panel"></div>';
    it.panel(menu.querySelector(".cp-panel"), { close: close, back: function () { render(topRows()); }, brain: brain });
  }
  // Open the menu straight on one item (the pinned-folder chip opens its panel this way).
  function openItem(id) {
    var it = reg.list().filter(function (x) { return x.id === id; })[0];
    if (!it || !menu) return;
    closeOthers();
    menu.hidden = false; if (btn) btn.setAttribute("aria-expanded", "true");
    if (it.panel) openPanel(it); else render(topRows());
  }
  function choose(r) {
    if (!r) return;
    if (r.item && r.item.panel) { openPanel(r.item); return; }
    if (r.item && r.item.submenu) {
      var it = r.item;
      render([{ label: tw("cp.loading") }], tw(it.label));
      Promise.resolve(it.submenu()).then(function (rows) {
        if (!isOpen()) return;
        render(rows && rows.length ? rows : [{ label: tw(it.emptyKey || "cp.empty") }], tw(it.label));
      });
      return;
    }
    var run = r.run || (r.item && r.item.run);
    if (run) { close(); run(); }
  }

  // ---- default items ----
  var ICON = {
    clip: '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>',
    folder: '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    file: '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/></svg>',
    slash: '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M14 7l-4 10"/></svg>',
    plug: '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 2v6M15 2v6M7 8h10v3a5 5 0 0 1-10 0zM12 16v6"/></svg>',
    users: '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a5 5 0 0 1 3.5 6"/></svg>',
    chevron: '<svg class="cp-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg>',
    back: '<svg class="cp-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 6l-6 6 6 6"/></svg>',
  };
  var badConn = 0;

  reg.register({ id: "attach", order: 10, icon: ICON.clip, label: "cp.attach", hint: function () { return /Mac/.test(navigator.platform) ? "Cmd+U" : "Ctrl+U"; },
    run: function () { if (window.JavisAttach) window.JavisAttach.pick(); } });
  // order 20 ("folder") is registered by composer-folder.js: pin a working folder.
  reg.register({ id: "brain_file", order: 30, icon: ICON.file, label: "cp.brain_file", emptyKey: "cp.brain_empty",
    submenu: function () { return Promise.resolve(brainSearchRows("")); } });
  reg.register({ id: "commands", order: 40, icon: ICON.slash, label: "cp.commands", hint: function () { return "/"; },
    run: function () { insertToken("/"); } });
  reg.register({ id: "connections", order: 50, icon: ICON.plug, label: "cp.connections", emptyKey: "cp.conn_none",
    hint: function () { return badConn ? tw("cp.conn_bad", { n: badConn }) : ""; },
    submenu: function () {
      return Promise.all([getJson("/connect/catalog"), getJson("/connect/health")]).then(function (res) {
        var cat = (res[0] && res[0].catalog) || [], conns = (res[0] && res[0].connections) || [];
        var health = (res[1] && res[1].health) || {};
        var names = {}; cat.forEach(function (c) { names[c.id] = c.name; });
        var rows = conns.map(function (c) {
          var h = health[c.id];
          return { label: c.label || names[c.connector_id] || c.name || c.id,
            dot: !h || h.kind === "starting" ? "unknown" : (h.ok ? "ok" : "bad"), hint: h && !h.ok ? (h.message || "") : "",
            run: function () { goPage("mcp"); } };
        });
        if (rows.length) rows.push({ sep: true });
        rows.push({ label: tw("cp.conn_open"), run: function () { goPage("mcp"); } });
        return rows;
      });
    } });
  reg.register({ id: "partners", order: 60, icon: ICON.users, label: "cp.partners", emptyKey: "cp.partners_none",
    submenu: function () {
      var b = encodeURIComponent(brain());
      return Promise.all([getJson("/agents?prompt=0&brain=" + b), getJson("/workflows?brain=" + b)]).then(function (res) {
        var ag = (res[0] && (res[0].agents || res[0])) || [], wf = (res[1] && (res[1].workflows || res[1])) || [];
        var rows = [];
        (Array.isArray(ag) ? ag : []).forEach(function (a) { if (a && a.slug) rows.push({ label: a.name || a.slug, hint: a.role || "", run: function () { insertToken("/agent-" + a.slug + " "); } }); });
        (Array.isArray(wf) ? wf : []).forEach(function (w) { if (w && w.slug && w.status === "active") rows.push({ label: w.name || w.slug, hint: tw("cp.workflow"), run: function () { insertToken("/workflow-" + w.slug + " "); } }); });
        return rows;
      });
    } });

  function goPage(id) { try { window.Alpine.store("nav").go(id); } catch (e) { location.hash = "#" + id; } }

  // ---- pick a file from the brain: a search box inside the menu ----
  var brainSeq = 0;
  function brainSearchRows(q) {
    setTimeout(function () { mountBrainSearch(q); }, 0);
    return [{ label: tw("cp.brain_search_hint") }];
  }
  function mountBrainSearch(q) {
    if (!isOpen()) return;
    menu.innerHTML = '<button type="button" class="cp-mi cp-back" data-back="1">' + ICON.back + "<span>" + esc(tw("cp.brain_file")) + "</span></button>" +
      '<input type="search" class="cp-search" placeholder="' + esc(tw("cp.brain_search_ph")) + '" aria-label="' + esc(tw("cp.brain_search_ph")) + '">' +
      '<div class="cp-results"></div>';
    var box = menu.querySelector(".cp-search"), out = menu.querySelector(".cp-results");
    box.value = q || "";
    box.focus();
    var timer = 0;
    box.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(search, 180); });
    function search() {
      var term = box.value.trim(), seq = ++brainSeq;
      if (!term) { out.innerHTML = ""; return; }
      getJson("/files/search?mode=name&limit=20&brain=" + encodeURIComponent(brain()) + "&q=" + encodeURIComponent(term)).then(function (d) {
        if (seq !== brainSeq || !isOpen()) return;
        var items = (d && d.items) || [];
        out.innerHTML = items.length ? items.map(function (it, i) {
          return '<button type="button" class="cp-mi" data-file="' + i + '">' + ICON.file + '<span class="cp-mi-lbl">' + esc(it.name || it.path) +
            '</span><span class="cp-mi-hint">' + esc(it.path || "") + "</span></button>";
        }).join("") : '<div class="cp-empty">' + esc(tw("cp.brain_empty")) + "</div>";
        Array.prototype.forEach.call(out.querySelectorAll("[data-file]"), function (el) {
          el.addEventListener("click", function () {
            var it = items[+el.getAttribute("data-file")];
            getJson("/files/resolve?brain=" + encodeURIComponent(brain()) + "&path=" + encodeURIComponent(it.path)).then(function (r) {
              if (window.JavisAttach) {
                if (r && r.ok) window.JavisAttach.addBrainFile(brainAttachment(r, it.path, brain()));
                else window.JavisAttach.note(tw("cp.brain_failed"));
              }
              close(); var i2 = input(); if (i2) i2.focus();
            });
          });
        });
      });
    }
    if (q) search();
  }

  // ---- wiring ----
  function init() {
    menu = $("plusMenu"); btn = $("plusBtn");
    if (!menu || !btn) return;
    btn.addEventListener("click", function (e) { e.stopPropagation(); isOpen() ? close() : open(); });
    menu.addEventListener("click", function (e) {
      e.stopPropagation();
      if (e.target.closest("[data-back]")) { render(topRows()); return; }
      var el = e.target.closest("[data-i]");
      if (el) choose(view[+el.getAttribute("data-i")]);
    });
    menu.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); focusRow(active + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); focusRow(active - 1); }
      else if (e.key === "Escape") { e.preventDefault(); close(); btn.focus(); }
      else if (shouldGoBack(e, !!menu.querySelector("[data-back]"))) { e.preventDefault(); render(topRows()); }
    });
    document.addEventListener("click", function (e) { if (isOpen() && !menu.contains(e.target)) close(); });
    document.addEventListener("keydown", function (e) {
      var key = String(e.key || "").toLowerCase();
      if (key === "u" && (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey) {
        // Only when the composer is usable: on a page without it, or while Workspace has
        // disabled the + button, a file would land in a composer nobody can see.
        var pb = $("plusBtn"), card = $("hudVoice");
        if (!pb || pb.disabled || !card || card.offsetParent === null) return;
        var a = document.activeElement;
        var other = a && a !== input() && (a.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName));
        if (other) return;
        e.preventDefault();
        if (window.JavisAttach) window.JavisAttach.pick();
      }
    });
    // First count at page load; refreshed again each time the menu opens.
    refreshConnHealth();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();

  window.JavisComposerMenu = { register: reg.register, list: reg.list, open: open, close: close, isOpen: isOpen, openItem: openItem, icon: ICON };
})();
