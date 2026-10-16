/* composer-folder.js - pin a working folder for the open conversation (0.158.0).
 *
 * The server runs the conversation's turns inside the pinned folder (coding_store binding,
 * POST /coding/session/{sid}/pin). The "+" menu gets a "Pin working folder" panel: brain
 * folders first, a search box, and "Browse another folder..." through JavisFolderPicker.
 * A small chip after the Fast mode bolt shows the pinned folder; nothing shows when unpinned.
 * Pure helpers are exported for node tests. Never use the em dash character here.
 */
(function () {
  "use strict";
  var HIDDEN = /^(\.|node_modules$|__pycache__$)/;

  function folderRows(items, listPath) {
    return (items || []).filter(function (x) { return x && x.type === "dir" && !HIDDEN.test(String(x.name || "")); })
      .map(function (x) { return { name: x.name, path: x.path || ((listPath ? listPath + "/" : "") + x.name), dirs: !!x.dirs }; });
  }
  // Row hint: the path inside the brain ("home" from /files/list), not from the browse ceiling.
  function displayPath(path, home) {
    var p = String(path || ""), h = String(home || "");
    return h && p.indexOf(h + "/") === 0 ? p.slice(h.length + 1) : p;
  }
  function chipLabel(name, max) {
    var s = String(name || "");
    return s.length <= max ? s : s.slice(0, max - 1) + "…";
  }
  // Only the newest request for the conversation that is still open may update the chip.
  function createPinState() {
    var seq = 0, openSid = "", pending = null;
    return {
      request: function (sid) { openSid = sid; return ++seq; },
      accept: function (n, sid) { return n === seq && sid === openSid; },
      hold: function (p) { pending = p; },
      takePending: function () { var p = pending; pending = null; return p; },
    };
  }

  var pure = { folderRows: folderRows, displayPath: displayPath, chipLabel: chipLabel, createPinState: createPinState };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;

  var state = createPinState(), folder = null, inBrain = false, extras = [];
  function tw(k, v) { return window.t ? window.t(k, v) : k; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function brain() { try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; } catch (e) { return "brain"; } }
  function sid() { try { return (window.JavisSessions && window.JavisSessions.current()) || ""; } catch (e) { return ""; } }
  function icon() { return (window.JavisComposerMenu && window.JavisComposerMenu.icon && window.JavisComposerMenu.icon.folder) || ""; }
  function narrow() { return !!(window.matchMedia && window.matchMedia("(max-width: 860px)").matches); }
  function getJson(url, opt) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, opt || {}))
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .catch(function () { return { ok: false, error: tw("cp.pin_failed") }; });
  }
  function pinUrl(id) { return "/coding/session/" + encodeURIComponent(id) + "/pin"; }
  function pinBody(p) { var b = new FormData(); b.append("path", p); b.append("brain", brain()); return b; }
  function isAbs(p) { return /^([A-Za-z]:[\\/]|\/|\\\\)/.test(String(p || "")); }
  function norm(p) { return String(p || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase(); }
  // Is a path inside the open brain? Relative paths come from the brain list or search, so yes.
  // An absolute path is compared with the brain path when that is absolute; when the brain is only
  // known by an alias, the answer is unknown and the chip does not warn.
  function inBrainPath(p) {
    if (!isAbs(p)) return true;
    var b = brain();
    if (!isAbs(b)) return true;
    var np = norm(p), nb = norm(b);
    return np === nb || np.indexOf(nb + "/") === 0;
  }

  function announce() {
    try { window.dispatchEvent(new CustomEvent("javis:pinned-folder-changed", { detail: { sid: sid(), folder: folder } })); } catch (e) {}
  }
  function renderChip() {
    var host = document.getElementById("cpChips");
    if (!host) return;
    var chip = document.getElementById("pinChip");
    if (!folder) { if (chip) chip.remove(); return; }
    if (!chip) {
      chip = document.createElement("button");
      chip.type = "button"; chip.id = "pinChip"; chip.className = "cp-pin";
      chip.addEventListener("click", function (e) {
        e.stopPropagation();
        if (window.JavisComposerMenu) window.JavisComposerMenu.openItem("folder");
      });
    }
    var fast = document.getElementById("fastBtn");
    if (chip.parentElement !== host || chip.previousElementSibling !== fast) host.insertBefore(chip, fast ? fast.nextSibling : null);
    chip.classList.toggle("cp-pin-gone", folder.exists === false);
    chip.title = folder.path + (folder.exists === false ? "\n" + tw("cp.pin_gone") : "") + (inBrain ? "" : "\n" + tw("cp.pin_outside")) +
      (extras.length ? "\n" + tw("cp.pin_extra", { names: extras.join(", ") }) : "");
    chip.setAttribute("aria-label", tw("cp.pin_folder") + ": " + folder.name);
    // Extra folders bound before 0.158.0 still reach the prompt: show them as +N instead of hiding them.
    chip.innerHTML = icon() + "<span>" + esc(chipLabel(folder.name, narrow() ? 10 : 18)) + "</span>" +
      (extras.length ? '<span class="cp-pin-more">+' + extras.length + "</span>" : "");
  }
  function apply(d) {
    folder = (d && d.folder) || null;
    inBrain = !!(d && d.in_brain);
    extras = (folder && d && Array.isArray(d.extra_folders)) ? d.extra_folders : [];
    renderChip();
    announce();
  }
  function refresh() {
    var id = sid(), n = state.request(id);
    if (!id) {
      if (held && heldBrain !== brain()) dropHeld();   // the brain changed: the held pin belonged to the old one
      apply(heldView());
      return Promise.resolve();
    }
    // Opening an existing conversation drops a pin held for an empty chat: it belonged there.
    held = null; state.takePending();
    return getJson("/coding/session/" + encodeURIComponent(id) + "?brain=" + encodeURIComponent(brain())).then(function (d) {
      if (state.accept(n, id)) apply(d);
    });
  }
  // A pin chosen on an empty chat is held until the first message mints the session id.
  var held = null, heldBrain = "";
  function dropHeld() { held = null; heldBrain = ""; state.takePending(); }
  function heldView() {
    if (!held) return null;
    return { folder: { name: String(held).split(/[\\/]/).filter(Boolean).pop() || held, path: held, exists: true }, in_brain: inBrainPath(held) };
  }
  function pin(p) {
    var id = sid();
    if (!id) {
      dropHeld();
      held = p || null;
      if (held) { heldBrain = brain(); state.hold(held); }
      apply(heldView());
      return Promise.resolve("");
    }
    var n = state.request(id);
    return getJson(pinUrl(id), { method: "POST", body: pinBody(p) }).then(function (d) {
      if (!d || d.ok === false) return (d && d.error) || tw("cp.pin_failed");
      if (state.accept(n, id)) apply(d);
      return "";
    });
  }
  function claimPending(newSid) {
    if (!newSid) return null;                      // keep the held pin until a real session id exists
    var sameBrain = heldBrain === brain();
    var p = state.takePending();
    held = null; heldBrain = "";
    if (!p) return null;                           // nothing held: the caller sends right away
    if (!sameBrain) { apply(null); return null; }  // the brain changed since the pin was chosen
    // app.js waits for this promise before sending the first turn, so the turn runs in the folder.
    var n = state.request(newSid);
    return getJson(pinUrl(newSid), { method: "POST", body: pinBody(p) }).then(function (d) {
      if (d && d.ok !== false) { if (state.accept(n, newSid)) apply(d); return; }
      // The pin failed (folder gone, path unreadable): drop the chip and say why, the turn runs in the brain.
      apply(null);
      if (window.JavisAttach) window.JavisAttach.note((d && d.error) || tw("cp.pin_failed"));
    });
  }

  // The panel, for any conversation: the main chat (defaults below) and a team chat (teams.js passes its own
  // brain, current folder and pin). 0.191.0 (owner, 16/10/2026): a folder with folders inside has a ">" button;
  // ">" goes inside, the name pins that folder; inside a folder the first row pins the folder you are in.
  function makePanel(o) {
    o = o || {};
    var brainOf = o.brain || brain, currentOf = o.current || function () { return folder; }, pinTo = o.pin || pin;
    return function (box, api) {
      var cur = currentOf();
      // The current folder is its own (non-clickable) row, Unpin a separate button (spec).
      var head = cur ? '<div class="cp-mi cp-pin-current" aria-current="true">' + icon() + '<span class="cp-mi-lbl">' + esc(cur.name) +
        '</span><span class="cp-mi-hint">' + esc(tw("cp.pin_current")) + "</span></div>" +
        '<button type="button" class="cp-mi" data-unpin="1"><span class="cp-mi-lbl">' + esc(tw("cp.pin_unpin")) + "</span></button>" +
        '<div class="cp-sep"></div>' : "";
      box.innerHTML = head + '<input type="search" class="cp-search" placeholder="' + esc(tw("cp.pin_search_ph")) + '" aria-label="' +
        esc(tw("cp.pin_search_ph")) + '"><div class="cp-results"></div><div class="cp-sep"></div>' +
        '<button type="button" class="cp-mi" data-browse="1">' + icon() + '<span class="cp-mi-lbl">' + esc(tw("cp.pin_browse")) + "</span></button>" +
        '<div class="cp-pin-err" role="status"></div>';
      var input = box.querySelector(".cp-search"), out = box.querySelector(".cp-results"), err = box.querySelector(".cp-pin-err");
      var list = [], timer = 0, seq = 0, home = "", trail = [];   // trail: the folders gone into, [{name, path}]
      function inner() { return trail.length ? trail[trail.length - 1] : null; }
      // Top-level rows need no hint; search results show where they sit inside the brain.
      function show(items, withHint) {
        list = items;
        var here = inner();
        var top = here ? '<button type="button" class="cp-mi cp-back" data-back="1"><span class="cp-mi-lbl">‹ ' +
          esc(trail.length > 1 ? trail[trail.length - 2].name : tw("cp.pin_top")) + "</span></button>" +
          '<button type="button" class="cp-mi cp-pin-here" data-pin-here="1">' + icon() + '<span class="cp-mi-lbl">' +
          esc(tw("cp.pin_here", { name: here.name })) + "</span></button>" : "";
        out.innerHTML = top + (items.length ? items.map(function (r, i) {
          var hint = withHint ? displayPath(r.path, home) : "";
          return '<div class="cp-row"><button type="button" class="cp-mi" data-pin="' + i + '">' + icon() + '<span class="cp-mi-lbl">' +
            esc(r.name) + "</span>" + (hint && hint !== r.name ? '<span class="cp-mi-hint">' + esc(hint) + "</span>" : "") + "</button>" +
            (r.dirs ? '<button type="button" class="cp-in" data-in="' + i + '" title="' + esc(tw("cp.pin_open", { name: r.name })) +
              '" aria-label="' + esc(tw("cp.pin_open", { name: r.name })) + '">›</button>' : "") + "</div>";
        }).join("") : '<div class="cp-empty">' + esc(tw(here ? "cp.pin_no_sub" : "cp.pin_empty")) + "</div>");
      }
      function load() {
        var q = input.value.trim(), n = ++seq, here = inner();
        var url = q ? "/files/search?mode=name&only_dirs=true&limit=30&brain=" + encodeURIComponent(brainOf()) + "&q=" + encodeURIComponent(q)
          : "/files/list?subdirs=1&brain=" + encodeURIComponent(brainOf()) + (here ? "&path=" + encodeURIComponent(here.path) : "");
        getJson(url).then(function (d) {
          if (!q && d && d.home) home = d.home;
          if (n === seq) show(folderRows((d && d.items) || [], (d && d.path) || ""), !!q);
        });
      }
      function done(msg) {
        if (msg) { err.textContent = msg; return; }
        api.close();
        if (o.focus) o.focus(); else { var i = document.getElementById("chatInput"); if (i) i.focus(); }
      }
      box.addEventListener("click", function (e) {
        var b = e.target.closest ? e.target.closest("button") : null;
        if (!b) return;
        if (b.dataset.unpin) { pinTo("").then(done); return; }
        if (b.dataset.browse) {
          api.close();
          if (window.JavisFolderPicker) window.JavisFolderPicker.open({ tieuDe: tw("cp.pin_folder"), nhanDung: tw("cp.pin_folder"), demMd: false,
            brain: brainOf(), batDau: cur && isAbs(cur.path) ? cur.path : "", chon: function (p) { return pinTo(p); } });
          return;
        }
        if (b.dataset.back) { trail.pop(); input.value = ""; load(); return; }
        if (b.dataset.pinHere) { var h = inner(); if (h) pinTo(h.path).then(done); return; }
        if (b.dataset.in !== undefined) {
          var d = list[+b.dataset.in];
          if (d) { trail.push({ name: d.name, path: d.path }); input.value = ""; load(); }
          return;
        }
        if (b.dataset.pin !== undefined) { var r = list[+b.dataset.pin]; if (r) pinTo(r.path).then(done); }
      });
      input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(load, 180); });
      input.focus();
      load();
    };
  }
  var panel = makePanel();

  function init() {
    if (!window.JavisComposerMenu) return;
    window.JavisComposerMenu.register({ id: "folder", order: 20, icon: icon(), label: "cp.pin_folder",
      hint: function () { return folder ? chipLabel(folder.name, 18) : ""; }, panel: panel });
    window.addEventListener("javis:sessions-changed", refresh);
    window.addEventListener("resize", renderChip);
    window.addEventListener("javis:i18n", renderChip);
    refresh();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();

  window.JavisPinnedFolder = { claimPending: claimPending, current: function () { return folder; }, refresh: refresh, pin: pin,
    panelFor: makePanel };
})();
