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

   2026-11-09, owner: the four buttons beside the picker (new, rename, delete, outside folder) move INTO the panel, "giống
   phần tạo cộng sự": each brain's row carries Export (.zip), Rename and Delete, done right on the row (no prompt or alert),
   and the panel ends with New brain, Upload a brain (.zip) and Open an outside folder. The work itself is in
   brains-ui.js (window.JavisBrains); export and upload talk to /brains/export/* and /brains/import/*
   (server/brain_export.py): packing and unpacking run in the background, the upload goes in 32MB pieces.

   Each row's counts read "1920 Node · 2480 Link" on ONE line (2026-11-09, owner: it used to break in two); the same
   counts for the open brain sit in the graph's top-left corner, no longer beside this button.

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
  function icon(name, opts) { try { return root.ic ? root.ic(name, opts) : ""; } catch (e) { return ""; } }
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
                 brainName: o.dataset.brainName || "", movable: !grp && !!o.dataset.brainName,
                 custom: !!o.dataset.custom, pending: !!o.dataset.pending,
                 managed: !grp && !o.dataset.pending && (o.value === "brain" || !!o.dataset.brain) });
    });
    return out;
  }
  function current() {
    var all = entries();
    for (var i = 0; i < all.length; i++) if (all[i].value === sel.value) return all[i];
    return all[0] || { label: "", notes: "" };
  }
  function notesText(n) { return n ? t("bpick.notes", { n: n }, "{n} Nodes") : ""; }

  // Node and link counts as the graph shows them (2026-11-09, owner: "đếm số node và số link ngay ở phần này").
  // Asked only when the picker opens, one brain per request, never at page load; kept for COUNTS_MS on this page.
  // Until a count arrives the row shows the file count the brain list already carries.
  var COUNTS_MS = 60000;
  var counts = {};          // value -> {nodes, links, capped, at}
  var asking = {};
  function countsUrl(value) {
    var v = String(value || "");
    return "/graph/counts?" + (v.indexOf("path:") === 0 ? "path=" + encodeURIComponent(v.slice(5)) : "source=" + encodeURIComponent(v));
  }
  function askCounts(value) {
    var c = counts[value];
    if (asking[value] || (c && Date.now() - c.at < COUNTS_MS) || !root.fetch) return;
    asking[value] = true;
    root.fetch(countsUrl(value), { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && typeof d.nodes === "number") {
          counts[value] = { nodes: d.nodes, links: d.links || 0, capped: !!d.capped, at: Date.now() };
          drawButton();
          if (open && !reorder) drawList();
        }
      })
      .catch(function () { /* the row keeps its file count */ })
      .then(function () { delete asking[value]; });
  }
  function countText(x) {
    var c = counts[x.value];
    if (!c) return notesText(x.notes);
    return t("bpick.graph", { n: c.nodes + (c.capped ? "+" : ""), l: c.links }, "{n} Nodes · {l} Links");
  }

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
    var k = counts[c.value], n = k ? k.nodes + (k.capped ? "+" : "") : c.notes;
    btn.innerHTML = '<span class="bp-btn-name">' + esc(c.label) + "</span>" +
      (n ? '<span class="bp-btn-n">' + esc(n) + "</span>" : "") +
      '<span class="bp-btn-chev">' + icon("chevron-down") + "</span>";
    btn.title = c.label + (n ? " · " + countText(c) : "");
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
  var shade = null, pop = null, listEl = null, searchEl = null, headBtn = null, hintEl = null, errEl = null, footEl = null;
  // edit: the row form open now, {kind: "new" | "rename" | "delete" | "forget", value, text, err, busy}.
  // view "import": the panel shows the upload form instead of the list. note: one line of news (what just happened).
  var edit = null, view = "list", note = "", imp = { file: null, name: "", busy: false, msg: "", err: false };

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
      '<div class="bp-list" role="listbox"></div>' +
      '<div class="bp-foot"></div>';
    listEl = pop.querySelector(".bp-list");
    footEl = pop.querySelector(".bp-foot");
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
    listEl.addEventListener("input", onListInput);
    listEl.addEventListener("change", onListChange);
    listEl.addEventListener("dragover", function (e) { if (view === "import") { e.preventDefault(); var d = listEl.querySelector(".bp-drop"); if (d) d.classList.add("over"); } });
    listEl.addEventListener("dragleave", function () { var d = listEl.querySelector(".bp-drop"); if (d) d.classList.remove("over"); });
    listEl.addEventListener("drop", function (e) {
      if (view !== "import") return;
      e.preventDefault();
      var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) { imp.file = f; imp.msg = ""; drawList(); }
    });
    footEl.addEventListener("click", onFootClick);
    document.body.appendChild(shade);
    document.body.appendChild(pop);
  }

  function drawHead() {
    pop.querySelector(".bp-title").textContent = reorder ? t("bpick.reorder_title", null, "Reorder brains")
      : view === "import" ? t("bpick.import_title", null, "Upload a brain") : t("bpick.title", null, "Choose a brain");
    headBtn.innerHTML = reorder ? esc(t("bpick.done", null, "Done")) : icon("arrow-up-down") + " " + esc(t("bpick.reorder", null, "Reorder"));
    headBtn.classList.toggle("primary", reorder);
    headBtn.disabled = saving;
    headBtn.hidden = view === "import" || (!reorder && entries().filter(function (x) { return x.movable; }).length < 2);
    var many = entries().length > 6;
    pop.querySelector(".bp-search-wrap").hidden = reorder || view === "import" || !many;
    searchEl.placeholder = t("bpick.search", null, "Find a brain");
    hintEl.hidden = !reorder && !(note && view === "list");
    hintEl.textContent = reorder ? t("bpick.hint", null, "Drag the handle or use the arrows. The order is saved for every device.") : note;
    hintEl.classList.toggle("bp-note", !reorder);
    footEl.hidden = reorder || view === "import";
    if (!footEl.firstChild) {
      footEl.innerHTML =
        '<button type="button" class="bp-fbtn" data-foot="new">' + icon("plus") + '<span></span></button>' +
        '<button type="button" class="bp-fbtn" data-foot="import">' + icon("upload-cloud") + '<span></span></button>' +
        '<button type="button" class="bp-fbtn" data-foot="folder">' + icon("folder-open") + '<span></span></button>';
    }
    var fl = footEl.querySelectorAll(".bp-fbtn span");
    fl[0].textContent = t("bpick.new", null, "New brain");
    fl[1].textContent = t("bpick.import", null, "Upload a brain (.zip)");
    fl[2].textContent = t("bpick.folder", null, "Open an outside folder");
  }

  function fold(s) {
    return String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[\u0110\u0111]/g, "d").toLowerCase();
  }

  function rowHtml(x, i, n) {
    var on = x.value === sel.value;
    var sub = countText(x);
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
      '<span class="bp-acts">' + actsHtml(x) + "</span></div>" + formHtml(x);
  }

  function actBtn(act, ic, label, disabled) {
    return '<button type="button" class="bp-act' + (act === "delete" || act === "forget" ? " bp-act-del" : "") + '" data-act="' + act +
      '" title="' + esc(label) + '" aria-label="' + esc(label) + '"' + (disabled ? " disabled" : "") + ">" + icon(ic) + "</button>";
  }
  // Export, Rename, Default, Delete on a brain Javis manages; only "remove from the list" on an outside folder.
  // The star (2026-11-09): filled on the default brain, a button on every other one that makes it the default. That is
  // the way to delete the old default: it becomes an ordinary brain once another one is the default.
  function actsHtml(x) {
    if (x.custom) return actBtn("forget", "x", t("bpick.forget", null, "Remove from the list"));
    if (!x.managed) return "";
    var isDefault = x.value === "brain";
    var star = isDefault
      ? '<span class="bp-act bp-act-star on" role="img" title="' + esc(t("bpick.is_default", null, "Default brain")) + '" aria-label="' +
        esc(t("bpick.is_default", null, "Default brain")) + '">' + icon("star", { cls: "ic-fill" }) + "</span>"
      : actBtn("default", "star", t("bpick.make_default", null, "Make this the default brain"));
    return actBtn("export", "download", t("bpick.export", null, "Export as a .zip file")) +
      actBtn("rename", "pencil", t("bpick.rename", null, "Rename")) + star +
      actBtn("delete", "trash-2", isDefault ? t("bpick.no_delete_default", null, "The default brain cannot be deleted. Star another brain first.")
        : t("bpick.delete", null, "Delete"), isDefault);
  }
  // What a delete stops (GET /brains/ties), drawn in the delete form once the server answers.
  function tiesHtml(d) {
    if (!d) return "";
    var parts = [], out = "";
    if (d.loops) parts.push(t("bpick.off_loops", { n: d.loops }, "{n} loops"));
    if (d.reminders) parts.push(t("bpick.off_reminders", { n: d.reminders }, "{n} reminders"));
    if (parts.length) out += '<div class="bp-form-msg">' + esc(t("bpick.ties_work", { what: parts.join(", ") }, "Stops with it: {what}.")) + "</div>";
    var bots = (d.bots || []).map(function (b) { return b && b.name; }).filter(Boolean);
    if (bots.length) {
      out += '<div class="bp-form-msg bp-warn">' + esc(t("bpick.ties_bots", { names: bots.join(", ") },
        "Bots using this brain: {names}. Move them to another brain first.")) + "</div>";
    }
    return out;
  }
  function btnPair(cancelAct, goAct, goLabel, goClass, goDisabled) {
    return '<div class="bp-form-btns"><button type="button" class="bp-ibtn" data-act="' + cancelAct + '">' + esc(t("bpick.cancel", null, "Cancel")) +
      '</button><button type="button" class="bp-ibtn ' + goClass + '" data-act="' + goAct + '"' + (goDisabled ? " disabled" : "") + ">" + esc(goLabel) + "</button></div>";
  }
  // The form under a row (rename, delete, forget), drawn from `edit` so a redraw (a count arriving) keeps what was typed.
  function formHtml(x) {
    if (!edit || edit.value !== x.value) return "";
    var err = edit.err ? '<div class="bp-form-err">' + esc(edit.err) + "</div>" : "";
    var busy = !!edit.busy;
    if (edit.kind === "rename") {
      return '<div class="bp-form">' +
        '<input class="bp-in" data-in="rename" maxlength="60" value="' + esc(edit.text) + '" aria-label="' + esc(t("bpick.rename", null, "Rename")) + '">' +
        '<div class="bp-form-msg">' + esc(t("bpick.rename_hint", null, "The folder and links stay the same; only the shown name changes.")) + "</div>" + err +
        btnPair("cancel", "save", t("bpick.save", null, "Save"), "primary", busy) + "</div>";
    }
    if (edit.kind === "default") {
      var cur = entryOf("brain");
      return '<div class="bp-form">' +
        '<div class="bp-form-msg">' + esc(t("bpick.default_msg", { name: x.label, old: cur ? cur.label : "" },
          "{name} becomes the default brain: work that names no brain runs there. {old} becomes an ordinary brain you can delete.")) + "</div>" + err +
        btnPair("cancel", "make-default", t("bpick.default_go", null, "Make default"), "primary", busy) + "</div>";
    }
    if (edit.kind === "delete") {
      var ok = edit.text.trim() === x.brainName;
      return '<div class="bp-form danger">' +
        '<div class="bp-form-msg">' + esc(t("bpick.delete_msg", { name: x.label }, "{name} goes to the trash for 30 days, then it is gone; other synced machines delete it too. Export it first if in doubt.")) + "</div>" +
        tiesHtml(edit.ties) +
        '<div class="bp-form-msg">' + esc(t("bpick.delete_type", null, "Type the folder name to confirm:")) + " <b>" + esc(x.brainName) + "</b></div>" +
        '<input class="bp-in" data-in="confirm" autocomplete="off" spellcheck="false" placeholder="' + esc(x.brainName) + '" value="' + esc(edit.text) + '">' + err +
        btnPair("cancel", "really", t("bpick.delete_go", null, "Delete brain"), "red", busy || !ok) + "</div>";
    }
    if (edit.kind === "forget") {
      return '<div class="bp-form danger">' +
        '<div class="bp-form-msg">' + esc(t("bpick.forget_msg", { name: x.label }, "Remove {name} from the list? The files in the folder stay where they are.")) + "</div>" + err +
        btnPair("cancel", "really", t("bpick.forget", null, "Remove from the list"), "red", busy) + "</div>";
    }
    return "";
  }
  function newFormHtml() {
    if (!edit || edit.kind !== "new") return "";
    var err = edit.err ? '<div class="bp-form-err">' + esc(edit.err) + "</div>" : "";
    return '<div class="bp-form bp-form-new">' +
      '<input class="bp-in" data-in="new" maxlength="60" placeholder="' + esc(t("bpick.new_ph", null, "New brain name")) + '" value="' + esc(edit.text) + '">' + err +
      btnPair("cancel", "create", t("bpick.create", null, "Create"), "primary", !!edit.busy || !edit.text.trim()) + "</div>";
  }
  function importHtml() {
    var f = imp.file;
    return '<div class="bp-import">' +
      '<p class="bp-form-msg">' + esc(t("bpick.import_lead", null, "Choose a .zip exported by Javis, on this machine or another. Javis makes a NEW brain from it and never touches the brains you have.")) + "</p>" +
      '<label class="bp-drop">' + icon("upload-cloud") +
      '<span>' + esc(t("bpick.import_drop", null, "Drop the file here or tap to choose")) + "</span>" +
      (f ? '<span class="bp-file">' + esc(f.name) + " · " + esc(sizeText(f.size)) + "</span>" : "") +
      '<input type="file" class="bp-file-in" accept=".zip,application/zip"' + (imp.busy ? " disabled" : "") + "></label>" +
      '<label class="bp-field"><span>' + esc(t("bpick.import_name", null, "New brain name")) + "</span>" +
      '<input class="bp-in" data-in="import-name" maxlength="60" placeholder="' + esc(t("bpick.import_name_ph", null, "Leave empty to keep the name in the file")) + '" value="' + esc(imp.name) + '"></label>' +
      (imp.msg ? '<div class="' + (imp.err ? "bp-form-err" : "bp-form-msg bp-progress") + '">' + esc(imp.msg) + "</div>" : "") +
      btnPair("import-cancel", "import-go", t("bpick.import_go", null, "Upload"), "primary", imp.busy || !f) + "</div>";
  }
  function sizeText(b) {
    b = Number(b) || 0;
    if (b >= 1024 * 1024 * 1024) return (b / 1024 / 1024 / 1024).toFixed(1) + " GB";
    if (b >= 1024 * 1024) return (b / 1024 / 1024).toFixed(1) + " MB";
    return Math.max(1, Math.round(b / 1024)) + " KB";
  }

  function drawList() {
    if (!pop) return;
    drawHead();
    if (reorder) {
      listEl.innerHTML = work.map(function (x, i) { return rowHtml(x, i, work.length); }).join("");
      return;
    }
    // A redraw (a count arriving, the list reloading) must not steal the box someone is typing in.
    var fa = document.activeElement, key = fa && fa.getAttribute && listEl.contains(fa) ? fa.getAttribute("data-in") : null;
    var ss = key ? fa.selectionStart : 0, se = key ? fa.selectionEnd : 0;
    if (view === "import") {
      listEl.innerHTML = importHtml();
    } else {
      drawRows();
    }
    if (key) {
      var again = listEl.querySelector('[data-in="' + key + '"]');
      if (again) { again.focus(); try { again.setSelectionRange(ss, se); } catch (e) {} }
    }
  }
  function drawRows() {
    var q = fold(query.trim());
    var all = entries().filter(function (x) { return !q || fold(x.label).indexOf(q) >= 0; });
    var html = "", lastGroup = "";
    all.forEach(function (x) {
      if (x.group && x.group !== lastGroup) { html += '<div class="bp-group">' + esc(x.group) + "</div>"; lastGroup = x.group; }
      html += rowHtml(x);
    });
    listEl.innerHTML = newFormHtml() + (html || '<div class="bp-empty">' + esc(t("bpick.empty", null, "No brain matches.")) + "</div>");
  }

  function place() {
    if (isPhone()) { pop.classList.add("sheet"); pop.style.left = pop.style.top = pop.style.width = ""; return; }
    pop.classList.remove("sheet");
    var r = btn.getBoundingClientRect();
    var w = Math.max(360, Math.min(420, r.width + 170));
    var left = Math.min(Math.max(8, r.left), root.innerWidth - w - 8);
    pop.style.width = w + "px";
    pop.style.left = left + "px";
    pop.style.top = Math.min(r.bottom + 6, root.innerHeight - 200) + "px";
  }

  function show() {
    build();
    open = true; reorder = false; query = ""; searchEl.value = ""; errEl.hidden = true;
    edit = null; view = "list"; note = ""; if (!imp.busy) imp = { file: null, name: "", busy: false, msg: "", err: false };
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
    // The counts: the current brain first, then the others (each answer redraws the list).
    var all = entries();
    askCounts(sel.value);
    all.forEach(function (x) { if (x.value !== sel.value) askCounts(x.value); });
  }
  function close() {
    if (!open) return;
    open = false; reorder = false; work = null; edit = null;
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
      if (reorder) { reorder = false; work = null; drawList(); }
      else if (edit) { edit = null; drawList(); }
      else if (view === "import" && !imp.busy) { view = "list"; drawList(); }
      else close();
    }
  }
  function focusRow(i) {
    var rows = listEl.querySelectorAll(".bp-row[tabindex]");
    if (rows[i]) rows[i].focus();
  }
  function onListKey(e) {
    var inp = e.target.getAttribute && e.target.getAttribute("data-in");
    if (inp) {
      if (e.key === "Enter") {
        e.preventDefault();
        var go = { rename: "save", confirm: "really", "new": "create", "import-name": "import-go" }[inp];
        var b = go && listEl.querySelector('[data-act="' + go + '"]');
        if (b && !b.disabled) b.click();
      }
      return;
    }
    var row = e.target.closest && e.target.closest(".bp-row[tabindex]");
    if (!row || e.target !== row) return;
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
    var a = e.target.closest && e.target.closest("[data-act]");
    if (a) { e.stopPropagation(); if (!a.disabled) onAct(a.getAttribute("data-act"), a.closest(".bp-row")); return; }
    if (e.target.closest && e.target.closest(".bp-form, .bp-import")) return;
    var row = e.target.closest && e.target.closest(".bp-row");
    if (row) pick(row.dataset.value);
  }

  // ---- the row buttons, the forms, the footer (2026-11-09) ----
  function entryOf(value) {
    var all = entries();
    for (var i = 0; i < all.length; i++) if (all[i].value === value) return all[i];
    return null;
  }
  function say(text) { note = text || ""; errEl.hidden = true; drawList(); }
  function fail(text) { errEl.textContent = text; errEl.hidden = false; }
  function onAct(act, row) {
    var value = row ? row.dataset.value : (edit && edit.value);
    var x = value != null ? entryOf(value) : null;
    if (act === "cancel") { edit = null; drawList(); return; }
    if (act === "export" && x) { exportBrain(x); return; }
    if (act === "rename" && x) { toggleEdit("rename", x.value, x.label); return; }
    if ((act === "delete" || act === "forget" || act === "default") && x) {
      toggleEdit(act, x.value, "");
      if (act === "delete" && edit && edit.kind === "delete") loadTies(edit);
      return;
    }
    if (act === "import-cancel") { if (!imp.busy) { view = "list"; drawList(); } return; }
    if (act === "import-go") { uploadBrain(); return; }
    if (!edit) return;
    if (act === "create") run(root.JavisBrains && root.JavisBrains.create(edit.text), function (r) {
      return t("bpick.created", { name: r.name || edit.text.trim() }, "Created {name}.");
    });
    if (act === "save") run(root.JavisBrains && root.JavisBrains.rename(edit.value, edit.text), function (r) {
      return t("bpick.renamed", { name: r.label || edit.text.trim() }, "Renamed to {name}.");
    });
    if (act === "make-default") {
      var e1 = entryOf(edit.value), newName = e1 ? e1.label : "";
      run(root.JavisBrains && root.JavisBrains.setDefault && root.JavisBrains.setDefault(edit.value), function (r) {
        return t("bpick.default_done", { name: r.label || newName }, "{name} is now the default brain.");
      });
    }
    if (act === "really") {
      var e0 = entryOf(edit.value), name = e0 ? e0.label : "";
      if (edit.kind === "forget") run(root.JavisBrains && root.JavisBrains.forget(edit.value), function () {
        return t("bpick.forgot", { name: name }, "Removed {name} from the list.");
      });
      else run(root.JavisBrains && root.JavisBrains.remove(edit.value, edit.text), function () {
        return t("bpick.deleted", { name: name }, "Deleted {name} (kept in the trash for 30 days).");
      });
    }
  }
  // Ask the server what a delete would stop; the form redraws when the answer lands (typing is kept by drawList).
  function loadTies(mine) {
    if (typeof fetch !== "function") return;
    fetch("/brains/ties?brain=" + encodeURIComponent(mine.value)).then(function (r) { return r.json(); }).then(function (d) {
      if (!d || !d.ok) return;
      mine.ties = d;
      if (edit === mine) drawList();
    }).catch(function () {});
  }
  function toggleEdit(kind, value, text) {
    edit = (edit && edit.kind === kind && edit.value === value) ? null : { kind: kind, value: value, text: text || "", err: "", busy: false };
    errEl.hidden = true;
    drawList();
    if (edit) {
      var box = listEl.querySelector(".bp-form");
      if (box && box.scrollIntoView) box.scrollIntoView({ block: "nearest" });
      var inp = box && box.querySelector("input");
      if (inp && !isPhone()) { inp.focus(); if (kind === "rename") inp.select(); }
    }
  }
  // One brains-ui.js call: the form shows "busy", then either closes with a line of news or shows the error under it.
  function run(promise, done) {
    if (!edit || !promise) return;
    var mine = edit;
    mine.busy = true; mine.err = "";
    drawList();
    Promise.resolve(promise).then(function (r) {
      r = r || {};
      if (!r.ok) { mine.busy = false; mine.err = r.error || t("bpick.net_err", null, "Connection lost, try again."); if (edit === mine) drawList(); return; }
      if (edit === mine) edit = null;
      if (open) say(done(r));
    }, function () {
      mine.busy = false; mine.err = t("bpick.net_err", null, "Connection lost, try again.");
      if (edit === mine) drawList();
    });
  }
  function onListInput(e) {
    var k = e.target.getAttribute && e.target.getAttribute("data-in");
    if (!k) return;
    if (k === "import-name") { imp.name = e.target.value; return; }
    if (!edit) return;
    edit.text = e.target.value;
    // Only the button that depends on the text changes; the whole list is not redrawn on each key.
    var b = null;
    if (k === "confirm") { b = listEl.querySelector('[data-act="really"]'); var x = entryOf(edit.value); if (b) b.disabled = !!edit.busy || !x || edit.text.trim() !== x.brainName; }
    if (k === "new") { b = listEl.querySelector('[data-act="create"]'); if (b) b.disabled = !!edit.busy || !edit.text.trim(); }
  }
  function onListChange(e) {
    if (!e.target.classList || !e.target.classList.contains("bp-file-in")) return;
    imp.file = (e.target.files && e.target.files[0]) || null;
    imp.msg = ""; imp.err = false;
    drawList();
  }
  function onFootClick(e) {
    var b = e.target.closest && e.target.closest("[data-foot]");
    if (!b) return;
    var k = b.getAttribute("data-foot");
    errEl.hidden = true; note = "";
    if (k === "new") { query = ""; searchEl.value = ""; toggleEdit("new", "", ""); listEl.scrollTop = 0; return; }
    if (k === "import") { edit = null; view = "import"; drawList(); return; }
    if (k === "folder") {
      // The outside-folder browser lives in app.js behind its old (now hidden) button; open it the same way.
      close();
      var fb = document.getElementById("pickFolderBtn");
      if (fb) fb.click();
    }
  }

  // Export (2026-11-09): the server packs in the background and the page polls the progress, then downloads the
  // finished file. A big brain takes longer to pack than a proxy such as Cloudflare Tunnel waits for a reply; this way
  // the download starts at once. Polling goes on with the panel closed, so the file still arrives.
  function getJson(url, opts) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, opts || {}))
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { d = d || {}; d._status = r.status; d._ok = r.ok && !!d.ok; return d; }); });
  }
  function form(fields) {
    var fd = new FormData();
    Object.keys(fields).forEach(function (k) { fd.append(k, fields[k]); });
    return { method: "POST", body: fd };
  }
  function tell(text, isErr) {
    if (!open) return;
    if (isErr) { note = ""; drawList(); fail(text); } else say(text);
  }
  function exportBrain(x) {
    tell(t("bpick.export_wait", { name: x.label }, "Getting {name} ready..."));
    getJson("/brains/export/start", form({ brain: x.value })).then(function (d) {
      if (!d._ok) { tell(d.error || t("bpick.export_err", null, "Could not export."), true); return; }
      var id = d.id, misses = 0;
      (function poll() {
        getJson("/brains/export/status?id=" + encodeURIComponent(id)).then(function (j) {
          if (!j._ok) {
            if (j._status === 404 || ++misses > 5) { tell(j.error || t("bpick.export_err", null, "Could not export."), true); return; }
            setTimeout(poll, 1500); return;
          }
          misses = 0;
          if (j.status === "error") { tell(j.error || t("bpick.export_err", null, "Could not export."), true); return; }
          if (j.status === "done") {
            tell(t("bpick.export_ready", { name: x.label, n: j.total }, "{name} is packed ({n} files); the download is starting."));
            var a = document.createElement("a");
            a.href = "/brains/export/file?id=" + encodeURIComponent(id);
            a.download = j.name || "";
            a.style.display = "none";
            document.body.appendChild(a);
            a.click();
            setTimeout(function () { a.remove(); }, 1000);
            return;
          }
          tell(j.status === "pack" && j.total
            ? t("bpick.packing", { name: x.label, done: Number(j.done).toLocaleString(), total: Number(j.total).toLocaleString() }, "Packing {name}: {done}/{total} files...")
            : t("bpick.export_wait", { name: x.label }, "Getting {name} ready..."));
          setTimeout(poll, 800);
        }, function () { if (++misses > 5) tell(t("bpick.net_err", null, "Connection lost, try again."), true); else setTimeout(poll, 1500); });
      })();
    }, function () { tell(t("bpick.net_err", null, "Connection lost, try again."), true); });
  }

  // Upload (2026-11-09): sent in pieces the server sizes (32MB), each one under the ~100MB a request may carry through
  // Cloudflare Tunnel. A piece that fails is sent again from where the server says it stands (a 409 carries
  // `received`), up to 5 tries in a row. Then the server unpacks in the background and the page polls.
  function sendPiece(id, offset, blob, onProgress) {
    return new Promise(function (resolve) {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", "/brains/import/chunk?id=" + encodeURIComponent(id) + "&offset=" + offset);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.upload.onprogress = function (e) { if (e.lengthComputable) onProgress(e.loaded); };
      xhr.onload = function () {
        var d = {};
        try { d = JSON.parse(xhr.responseText || "{}") || {}; } catch (e) {}
        resolve({ status: xhr.status, d: d });
      };
      xhr.onerror = function () { resolve({ status: 0, d: {} }); };
      xhr.send(blob);
    });
  }
  function uploadBrain() {
    if (!imp.file || imp.busy) return;
    var file = imp.file, size = file.size;
    imp.busy = true; imp.err = false;
    function show(text, isErr) {
      imp.msg = text; imp.err = !!isErr;
      if (open && view === "import") drawList();
    }
    function stop(text) { imp.busy = false; show(text || t("bpick.import_err", null, "Upload failed."), true); }
    show(t("bpick.uploading", { p: 0 }, "Uploading... {p}%"));
    getJson("/brains/import/start", form({ size: size, name: file.name })).then(function (d) {
      if (!d._ok) { stop(d.error); return; }
      var id = d.id, piece = d.chunk || 32 * 1024 * 1024, at = 0, tries = 0;
      function next() {
        if (at >= size) { finish(); return; }
        var end = Math.min(size, at + piece);
        sendPiece(id, at, file.slice(at, end), function (loaded) {
          show(t("bpick.uploading", { p: Math.min(99, Math.floor((at + loaded) * 100 / size)) }, "Uploading... {p}%"));
        }).then(function (r) {
          if (r.status === 200 && r.d.ok) { at = r.d.received; tries = 0; next(); return; }
          if (r.status === 409 && typeof r.d.received === "number") { at = r.d.received; }
          else if (r.status && r.status !== 502 && r.status !== 503 && r.status !== 504 && r.status !== 524) { stop(r.d.error); return; }
          if (++tries > 5) { stop(t("bpick.net_err", null, "Connection lost, try again.")); return; }
          setTimeout(next, 1000 * tries);
        });
      }
      function finish() {
        show(t("bpick.unpacking", null, "Unpacking..."));
        getJson("/brains/import/finish", form({ id: id, label: imp.name.trim() })).then(function (f) {
          if (!f._ok) { stop(f.error); return; }
          var misses = 0;
          (function poll() {
            getJson("/brains/import/status?id=" + encodeURIComponent(id)).then(function (j) {
              if (!j._ok) { if (j._status === 404 || ++misses > 5) stop(j.error); else setTimeout(poll, 1500); return; }
              if (j.status === "error") { stop(j.error); return; }
              if (j.status !== "done") { setTimeout(poll, 1000); return; }
              done(j.result || {});
            }, function () { if (++misses > 5) stop(t("bpick.net_err", null, "Connection lost, try again.")); else setTimeout(poll, 1500); });
          })();
        }, function () { stop(t("bpick.net_err", null, "Connection lost, try again.")); });
      }
      next();
    }, function () { stop(t("bpick.net_err", null, "Connection lost, try again.")); });

    function done(d) {
      var off = [], pz = d.paused || {};
      if (pz.plugins) off.push(t("bpick.off_plugins", { n: pz.plugins }, "{n} plugin(s)"));
      if (pz.loops) off.push(t("bpick.off_loops", { n: pz.loops }, "{n} loop(s)"));
      if (pz.reminders) off.push(t("bpick.off_reminders", { n: pz.reminders }, "{n} reminder(s)"));
      var text = t("bpick.imported", { name: d.label || d.name, n: d.files }, "Uploaded {name} ({n} files).");
      if (off.length) text += " " + t("bpick.imported_off", { what: off.join(", ") }, "{what} arrived switched off; turn them on where they live if you want them.");
      imp = { file: null, name: "", busy: false, msg: "", err: false };
      view = "list";
      Promise.resolve(root.JavisBrains && root.JavisBrains.adopt ? root.JavisBrains.adopt(d.path) : null)
        .then(function () { if (open) say(text); });
    }
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
