/* pet-menu.js - the owner's own MASCOT MENU: which Javis features the pet opens, in which order.

   Owner, 2026-11-05: "Chỉ cần thêm và sắp xếp vị trí thôi là ok rồi. Và cho phần này vào trong phần cài đặt linh vật."
   So this file only lets the owner ADD a feature and REORDER the list. No renaming, no icon or action change, no
   removing or hiding, no "restore defaults" (that would drop what was added). The server enforces the same rule
   (server/pet_menu.py): a save that drops an item already saved is refused.

   Three parts:
     - CATALOG: every feature the pet can open, with a stable id, its own i18n label and icon, and a check that says
       why it cannot run right now. Ids are what is saved, never the shown name (names change with language and,
       for the mic, with its state).
     - the store: GET / POST /pet/menu, cached in localStorage so the menu is right before the server answers, kept
       in step across windows by the `storage` event. Every change fires "javis:pet-menu"; pet.js closes an open
       menu on it, and builds the new one the next time it opens.
     - the "Mascot menu" card of Settings > Mascot (renderSettings): a draft list, Add feature, Discard, Save.

   No customised menu yet = the default six, exactly as before. Pure helpers are exported for node tests.
   No em dash in this file. */
(function (root) {
  "use strict";

  var DEFAULT_ITEMS = ["chat", "agent", "workflow", "mic", "pet", "teams"];
  var CACHE_KEY = "javis.pet.menu";

  // label/sub: i18n keys written out in full (the i18n scanner only sees whole keys). icon: Lucide name; a page takes
  // the icon of its rail item from JavisNav.iconName first, so the two can never drift apart.
  // Must list the same ids as KNOWN_ACTIONS in server/pet_menu.py (tests/js/test_pet_menu.js checks).
  var CATALOG = [
    { id: "chat", label: "pet.menu.chat", fb: "Chat", icon: "message-circle", sub: "page.chat.sub" },
    { id: "agent", label: "pet.menu.agent", fb: "Assistants", icon: "bot", sub: "petmenu.sub.agent" },
    { id: "workflow", label: "pet.menu.workflow", fb: "Workflows", icon: "workflow", sub: "petmenu.sub.workflow" },
    { id: "mic", label: "petmenu.mic_label", fb: "Mic on / off", icon: "mic", sub: "petmenu.sub.mic" },
    { id: "pet", label: "pet.menu.settings", fb: "Mascot settings", icon: "settings", sub: "page.pet.sub" },
    { id: "teams", label: "pet.menu.teams", fb: "Team chat", icon: "users", sub: "page.teams.sub" },
    { id: "home", label: "page.home.label", fb: "Graph", page: true, sub: "page.home.sub" },
    { id: "files", label: "page.files.label", fb: "Files", page: true, sub: "page.files.sub" },
    { id: "learn", label: "page.learn.label", fb: "Self-learning", page: true, sub: "page.learn.sub" },
    { id: "conversations", label: "page.conversations.label", fb: "Chatbot", page: true, sub: "page.conversations.sub" },
    { id: "skills", label: "page.skills.label", fb: "Skills", page: true, sub: "page.skills.sub" },
    { id: "plugins", label: "page.plugins.label", fb: "Plugins", page: true, sub: "page.plugins.sub" },
    { id: "terminal", label: "page.terminal.label", fb: "Terminal", page: true, sub: "page.terminal.sub" },
    { id: "tasks", label: "page.tasks.label", fb: "Tasks", page: true, sub: "page.tasks.sub" },
    { id: "webhooks", label: "page.webhooks.label", fb: "Webhooks", page: true, sub: "page.webhooks.sub" },
    { id: "mcp", label: "page.mcp.label", fb: "Connections", page: true, sub: "page.mcp.sub" },
    { id: "packs", label: "page.packs.label", fb: "Javis Store", page: true, sub: "page.packs.sub" },
    { id: "channels", label: "page.channels.label", fb: "Admin channels", page: true, sub: "page.channels.sub" },
    { id: "logins", label: "page.logins.label", fb: "Cookies", page: true, sub: "page.logins.sub" },
    { id: "models", label: "page.models.label", fb: "Models", page: true, sub: "page.models.sub" },
    { id: "settings", label: "page.settings.label", fb: "Settings", page: true, sub: "" },
    { id: "share", label: "page.share.label", fb: "Share links", page: true, sub: "page.share.sub" },
    { id: "account", label: "page.account.label", fb: "Account", page: true, sub: "page.account.sub" },
    { id: "usage", label: "page.usage.label", fb: "Usage", page: true, sub: "page.usage.sub" },
    { id: "logs", label: "page.logs.label", fb: "Updates", page: true, sub: "page.logs.sub" },
  ];
  var BY_ID = {};
  CATALOG.forEach(function (c) { BY_ID[c.id] = c; });

  // ---- pure helpers (node-testable) ----
  function moveItem(list, from, to) {
    var a = list.slice();
    if (from < 0 || from >= a.length) return a;
    to = Math.max(0, Math.min(a.length - 1, to));
    var it = a.splice(from, 1)[0];
    a.splice(to, 0, it);
    return a;
  }
  function sameOrder(a, b) {
    return (a || []).length === (b || []).length && (a || []).every(function (x, i) { return x === b[i]; });
  }
  // Add at the END, never twice. Returns a new list (the same content when `id` is already there).
  function addItem(list, id) {
    var a = (list || []).slice();
    if (a.indexOf(id) < 0) a.push(id);
    return a;
  }
  // The server's {state, rev, items} made safe to use: unknown state or a broken list falls back to the default.
  function normalize(m) {
    var o = m && typeof m === "object" ? m : {};
    var state = o.state === "custom" || o.state === "invalid" ? o.state : "default";
    var rev = typeof o.rev === "number" && o.rev >= 0 ? Math.floor(o.rev) : 0;
    var items = [];
    (Array.isArray(o.items) ? o.items : []).forEach(function (x) {
      if (typeof x === "string" && x && items.indexOf(x) < 0) items.push(x);
    });
    if (state !== "custom" || !items.length) items = DEFAULT_ITEMS.slice();
    return { state: state, rev: rev, items: items };
  }
  // Lowercase without diacritics, so "tro chuyen" finds "Trò chuyện".
  function fold(s) {
    var v = String(s == null ? "" : s).toLowerCase();
    try { v = v.normalize("NFD").replace(/[\u0300-\u036f]/g, ""); } catch (e) {}
    return v.replace(/\u0111/g, "d").trim();
  }
  function matches(query, text) { var q = fold(query); return !q || fold(text).indexOf(q) >= 0; }

  var api = {
    DEFAULT_ITEMS: DEFAULT_ITEMS.slice(), CATALOG: CATALOG,
    moveItem: moveItem, sameOrder: sameOrder, addItem: addItem, normalize: normalize, fold: fold, matches: matches,
    known: function (id) { return !!BY_ID[id]; },
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (!root || typeof document === "undefined") return;
  root.JavisPetMenu = api;

  function t(key, vars, fb) {
    try {
      var v = root.t ? root.t(key, vars) : key;
      return (!v || v === key) ? (fb || key) : v;
    } catch (e) { return fb || key; }
  }
  function icon(name) { try { return root.ic ? root.ic(name) : ""; } catch (e) { return ""; } }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ---- what one item looks like and whether it can run ----
  function iconName(c) {
    var n = "";
    try { if (c.page && root.JavisNav && root.JavisNav.iconName) n = root.JavisNav.iconName(c.id) || ""; } catch (e) {}
    return n || c.icon || "circle";
  }
  // "" when the feature can run now, else the reason in the owner's language.
  function why(id) {
    var c = BY_ID[id];
    if (!c) return t("petmenu.why_gone", null, "This feature is no longer in Javis");
    if (id === "mic") {
      var md = root.navigator && root.navigator.mediaDevices;
      if (!md || typeof md.getUserMedia !== "function" || !document.getElementById("voiceBtn")) {
        return t("petmenu.why_mic", null, "This browser does not allow the mic here");
      }
    }
    if (c.page) {
      try {
        if (root.JavisNav && root.JavisNav.has && !root.JavisNav.has(id)) return t("petmenu.why_page", null, "This Javis has no such page");
      } catch (e) {}
    }
    return "";
  }
  // {id, gone, label, sub, icon (svg), why}. `ctx.mic` = the mic is on now: the pet menu names what a press will do.
  function entry(id, ctx) {
    var c = BY_ID[id];
    if (!c) return { id: id, gone: true, label: t("petmenu.gone_name", null, "Feature no longer available"), sub: id, icon: icon("circle-help"), why: why(id) };
    var label = t(c.label, null, c.fb);
    if (id === "mic" && ctx && ctx.forMenu) {
      label = ctx.mic ? t("pet.menu.mic_off", null, "Turn mic off") : t("pet.menu.mic_on", null, "Turn mic on");
    }
    var sub = c.sub ? t(c.sub, null, "") : "";
    if (sub === c.sub) sub = "";
    return { id: id, gone: false, label: label, sub: sub, icon: icon(iconName(c)) || icon("circle"), why: why(id) };
  }
  api.entry = entry;
  api.why = why;

  // ---- the store ----
  var menu = normalize(null), loaded = false;
  try {
    var cached = JSON.parse(root.localStorage.getItem(CACHE_KEY) || "null");
    if (cached) menu = normalize(cached);
  } catch (e) {}
  function announce(remote) {
    try { root.dispatchEvent(new CustomEvent("javis:pet-menu", { detail: { menu: snapshot(), remote: !!remote } })); } catch (e) {}
  }
  function snapshot() { return { state: menu.state, rev: menu.rev, items: menu.items.slice() }; }
  function adopt(m, remote) {
    var next = normalize(m), changed = next.rev !== menu.rev || next.state !== menu.state || !sameOrder(next.items, menu.items);
    menu = next;
    try { root.localStorage.setItem(CACHE_KEY, JSON.stringify(menu)); } catch (e) {}
    if (changed) announce(remote);
    return changed;
  }
  // GET /pet/menu. Resolves true when the server answered, false when it did not (the cache stays in use).
  function load() {
    return fetch("/pet/menu", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.menu) return false;
        loaded = true;
        adopt(d.menu, false);
        return true;
      })
      .catch(function () { return false; });
  }
  // POST the whole list with the revision it was edited from. Resolves {ok, code, error}.
  function save(items, baseRev) {
    var fd = new FormData();
    fd.append("items", JSON.stringify(items));
    fd.append("base_rev", String(baseRev));
    return fetch("/pet/menu", { method: "POST", body: fd, credentials: "same-origin" })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (r.ok && d && d.ok && d.menu) { adopt(d.menu, false); return { ok: true }; }
          return { ok: false, code: (d && d.code) || "net", error: (d && d.error) || "", menu: d && d.menu };
        });
      })
      .catch(function () { return { ok: false, code: "net", error: "" }; });
  }
  // Another window saved: it wrote the cache, and that write reaches this window as a `storage` event.
  root.addEventListener("storage", function (e) {
    if (e.key !== CACHE_KEY || !e.newValue) return;
    try { adopt(JSON.parse(e.newValue), true); } catch (er) {}
  });
  api.current = function () { return menu.items.slice(); };
  api.state = snapshot;
  api.load = load;
  api.save = save;
  api.loaded = function () { return loaded; };
  // The pet's menu rows: saved order, gone ids left out (they only show, as unavailable, in Settings).
  api.menuEntries = function (ctx) {
    var c = Object.assign({ forMenu: true }, ctx || {});
    return menu.items.map(function (id) { return entry(id, c); }).filter(function (m) { return !m.gone; });
  };

  // ---- the "Mascot menu" card of Settings > Mascot ----
  function renderSettings(host) {
    if (!host) return;
    var saved = snapshot(), draft = saved.items.slice(), saving = false, note = null, loadFailed = false;
    function dirty() { return !sameOrder(draft, saved.items); }
    function locked() { return saved.state === "invalid"; }
    function guard() {
      if (!host.isConnected) { clearGuard(); return ""; }
      return dirty() ? t("petmenu.leave", null, "The mascot menu has unsaved changes.") : "";
    }
    function clearGuard() { try { root.JavisLeaveGuard && root.JavisLeaveGuard.clear(guard); } catch (e) {} }
    try { root.JavisLeaveGuard && root.JavisLeaveGuard.set(guard); } catch (e) {}

    function row(id, i, n) {
      var m = entry(id);
      var lock = locked() || saving;
      return '<div class="bp-row bp-move pm-row' + (m.why ? " pm-off" : "") + '" data-i="' + i + '" role="listitem">' +
        '<span class="bp-grip' + (lock ? " pm-nograb" : "") + '" title="' + esc(t("reorder.drag")) + '" aria-hidden="true">' + icon("arrow-up-down") + "</span>" +
        '<span class="ro-ic">' + m.icon + "</span>" +
        '<span class="bp-name pm-name"><span class="bp-label">' + esc(m.label) + "</span>" +
        (m.why ? '<span class="pm-why">' + esc(m.why) + "</span>" : "") + "</span>" +
        '<button type="button" class="bp-arrow" data-move="-1" aria-label="' + esc(t("reorder.up") + ": " + m.label) + '"' + (i === 0 || lock ? " disabled" : "") + ">" + icon("arrow-up") + "</button>" +
        '<button type="button" class="bp-arrow" data-move="1" aria-label="' + esc(t("reorder.down") + ": " + m.label) + '"' + (i === n - 1 || lock ? " disabled" : "") + ">" + icon("arrow-down") + "</button></div>";
    }
    function statusHtml() {
      if (!note) return "";
      var ok = note.kind === "ok";
      return (ok ? icon("circle-check") : icon("triangle-alert")) + " " + esc(note.text) +
        (note.reload ? ' <button type="button" class="gcard-btn ghost pm-reload" data-pm-reload>' + esc(t("petmenu.reload", null, "Reload")) + "</button>" : "");
    }
    function draw(focusSel) {
      var lock = locked();
      host.innerHTML = '<div class="settings-card pm-card" data-pet-menu-card>' +
        '<div class="settings-card-head"><b>' + esc(t("petmenu.title", null, "Mascot menu")) + "</b>" +
        '<span class="gcard-tag">' + esc(t("petmenu.count", { n: draft.length }, draft.length + " items")) + "</span></div>" +
        '<p class="pm-desc">' + esc(t("petmenu.desc", null, "Add and arrange the features you want to open from the mascot.")) + "</p>" +
        (lock ? '<p class="pm-alert" role="alert">' + icon("triangle-alert") + " " + esc(t("petmenu.invalid", null, "The saved menu settings are damaged.")) + "</p>" : "") +
        (loadFailed && !lock ? '<p class="pm-alert">' + esc(t("petmenu.load_err", null, "Could not load the saved menu.")) + "</p>" : "") +
        '<div class="bp-list pm-list" role="list" aria-label="' + esc(t("petmenu.title", null, "Mascot menu")) + '">' +
        draft.map(function (id, i) { return row(id, i, draft.length); }).join("") + "</div>" +
        '<div class="js-actions pm-actions">' +
        '<button type="button" class="gcard-btn ghost" data-pm-add' + (lock || saving ? " disabled" : "") + ">" + icon("plus") + " " + esc(t("petmenu.add", null, "Add feature")) + "</button>" +
        '<button type="button" class="gcard-btn ghost" data-pm-cancel' + (!dirty() || saving ? " disabled" : "") + ">" + esc(t("petmenu.cancel", null, "Discard changes")) + "</button>" +
        '<button type="button" class="gcard-btn" data-pm-save' + (!dirty() || saving || lock ? " disabled" : "") + ">" + esc(saving ? t("petmenu.saving", null, "Saving...") : t("petmenu.save", null, "Save changes")) + "</button>" +
        (lock ? '<button type="button" class="gcard-btn ghost" data-pm-reload>' + esc(t("petmenu.reload", null, "Reload")) + "</button>" : "") +
        "</div>" +
        '<div class="gcard-meta pm-status" role="status" aria-live="polite">' + statusHtml() + "</div></div>";
      if (focusSel) { var f = host.querySelector(focusSel); if (f && !f.disabled) try { f.focus(); } catch (e) {} }
    }

    // Load what the server holds before editing starts. A draft already being edited is never replaced.
    function refresh(force) {
      return load().then(function (ok) {
        if (!host.isConnected) return;
        loadFailed = !ok;
        if (force || !dirty()) { saved = snapshot(); draft = saved.items.slice(); }
        if (force) note = null;
        draw();
      });
    }

    host.onclick = function (e) {
      var el = e.target.closest && e.target.closest("button");
      if (!el || !host.contains(el) || el.disabled) return;
      if (el.classList.contains("bp-arrow")) {
        var i = +el.closest(".bp-row").dataset.i, d = +el.dataset.move;
        draft = moveItem(draft, i, i + d);
        note = null;
        draw('.bp-row[data-i="' + (i + d) + '"] .bp-arrow[data-move="' + d + '"]');
        return;
      }
      if (el.hasAttribute("data-pm-add")) { openPicker(); return; }
      if (el.hasAttribute("data-pm-cancel")) { draft = saved.items.slice(); note = null; draw("[data-pm-add]"); return; }
      if (el.hasAttribute("data-pm-reload")) { refresh(true); return; }
      if (el.hasAttribute("data-pm-save")) doSave();
    };
    host.onpointerdown = function (e) {
      if (locked() || saving || !root.JavisReorder || !root.JavisReorder.dragRow) return;
      var list = host.querySelector(".pm-list");
      if (!list) return;
      root.JavisReorder.dragRow(e, list, function (from, to) { draft = moveItem(draft, from, to); note = null; }, function () { draw(); });
    };

    function doSave() {
      if (saving || !dirty() || locked()) return;
      saving = true; note = null; draw();
      save(draft.slice(), saved.rev).then(function (r) {
        saving = false;
        if (!host.isConnected) return;
        if (r.ok) {
          saved = snapshot(); draft = saved.items.slice();
          note = { kind: "ok", text: t("petmenu.saved", null, "Mascot menu updated") };
        } else if (r.code === "conflict" || r.code === "invalid_saved") {
          // Keep the draft on screen: the owner decides to reload. Nothing of theirs is thrown away silently.
          note = { kind: "err", text: r.error || t("petmenu.conflict", null, "The mascot menu was changed in another window."), reload: true };
        } else {
          note = { kind: "err", text: r.error || t("petmenu.save_err", null, "Not saved yet. Please try again.") };
        }
        draw(r.ok ? "[data-pm-add]" : "[data-pm-save]");
      });
    }

    // Another window saved a newer menu while this card is open.
    function onRemote(e) {
      if (!host.isConnected) { root.removeEventListener("javis:pet-menu", onRemote); return; }
      if (!e.detail || !e.detail.remote || saving) return;
      if (!dirty()) { saved = snapshot(); draft = saved.items.slice(); note = null; draw(); return; }
      note = { kind: "err", text: t("petmenu.conflict", null, "The mascot menu was changed in another window."), reload: true };
      draw();
    }
    root.addEventListener("javis:pet-menu", onRemote);

    // ---- Add feature: the catalog with a search box. Added ones say so; unavailable ones say why. ----
    function openPicker() {
      closePicker();
      var m = document.createElement("div");
      m.id = "petMenuPick";
      m.className = "mp-overlay open";
      var title = t("petmenu.add", null, "Add feature");
      m.innerHTML = '<div class="mp-box ro-box pm-pick" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
        '<div class="mp-head"><div class="mp-title">' + esc(title) + "</div>" +
        '<button class="mp-x" type="button" data-pm-x aria-label="' + esc(t("petmenu.close", null, "Close")) + '">×</button></div>' +
        '<div class="pm-search"><input type="search" class="js-input" data-pm-q autocomplete="off" spellcheck="false" placeholder="' +
        esc(t("petmenu.search", null, "Search by name")) + '" aria-label="' + esc(t("petmenu.search", null, "Search by name")) + '"></div>' +
        '<div class="ro-list pm-pick-list" role="list"></div></div>';
      document.body.appendChild(m);
      var list = m.querySelector(".pm-pick-list"), q = m.querySelector("[data-pm-q]");
      function opt(c) {
        var e = entry(c.id), have = draft.indexOf(c.id) >= 0, off = have || !!e.why;
        var tag = have ? t("petmenu.added", null, "Added") : e.why;
        return '<button type="button" class="bp-row pm-opt' + (off ? " pm-off" : "") + '" role="listitem" data-pm-pick="' + esc(c.id) + '"' + (off ? ' disabled aria-disabled="true"' : "") + ">" +
          '<span class="ro-ic">' + e.icon + "</span>" +
          '<span class="bp-name pm-name"><span class="bp-label">' + esc(e.label) + "</span>" +
          (e.sub ? '<span class="pm-sub">' + esc(e.sub) + "</span>" : "") + "</span>" +
          (tag ? '<span class="pm-tag">' + esc(tag) + "</span>" : "") + "</button>";
      }
      function fill() {
        var hits = CATALOG.filter(function (c) { var e = entry(c.id); return matches(q.value, e.label + " " + e.sub); });
        list.innerHTML = hits.length ? hits.map(opt).join("") : '<div class="pm-empty">' + esc(t("petmenu.none", null, "No feature found")) + "</div>";
      }
      fill();
      q.addEventListener("input", fill);
      m.addEventListener("click", function (e) {
        if (e.target === m || (e.target.closest && e.target.closest("[data-pm-x]"))) { closePicker(true); return; }
        var b = e.target.closest && e.target.closest("[data-pm-pick]");
        if (!b || b.disabled) return;
        var id = b.getAttribute("data-pm-pick");
        if (!BY_ID[id] || why(id) || draft.indexOf(id) >= 0) return;
        draft = addItem(draft, id);
        note = null;
        closePicker();
        draw('.bp-row[data-i="' + (draft.length - 1) + '"] .bp-arrow[data-move="-1"]');
      });
      m.addEventListener("keydown", function (e) { if (e.key === "Escape") { e.stopPropagation(); closePicker(true); } });
      try { q.focus(); } catch (e) {}
    }
    function closePicker(back) {
      var m = document.getElementById("petMenuPick");
      if (m) m.remove();
      if (back) { var a = host.querySelector("[data-pm-add]"); if (a) try { a.focus(); } catch (e) {} }
    }

    draw();
    refresh(false);
  }
  api.renderSettings = renderSettings;

  load();
})(typeof window !== "undefined" ? window : null);
