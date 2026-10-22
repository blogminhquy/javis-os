/* msg-press.js - long press a chat message on a touch screen (0.179.0).

   Owner, 2026-10-16: on a phone the long press did not open anything. iOS starts its own long-press gesture (text
   selection, the copy callout) at about the same moment as our timer and cancels the pointer stream, so the old
   pointer-based timer (reactions.js bindLongPress) never fired there. The owner asked for the Zalo / Facebook feel:

   - Hold a message ~0.35 s: the screen dims, a row of six emoji pops up right above the finger and a card of actions
     (Reply, Copy, ...) sits at the bottom, like Zalo.
   - Without lifting the finger, SLIDE across the emoji: the one under the finger grows and shows its name, like
     Facebook; lift on it to react. Lift elsewhere: the card stays open to tap an action.
   - Tap the dim area to close.

   Messages are made unselectable on touch screens (CSS, .mp-host) so iOS does not start its own gesture; copying goes
   through the Copy action instead, which copies the whole message like Zalo does. 0.184.0: iOS still picked the nearest
   selectable text (the card, under the finger once it opened), so while a hold runs or the card is open, selectstart is
   refused and any selection already made is cleared. Android (owner, same day): Chrome there fires contextmenu at the
   spot under the finger, which by then is the card, outside root, so contextmenu is now refused on the whole document;
   and html.mp-holding switches selection off on the whole page while the card is open (style.css).

   0.240.0 (owner, Zalo screenshot): Copy only took the whole message; a short part could not be copied. Like Zalo, once
   the finger has lifted after the first hold, the bright copy of the message above the dim layer becomes selectable:
   hold it a second time and the phone's own selection starts, with its handles and its Copy / Translate callout. Not
   while the first finger is still down, or the 0.184.0 bug comes back (iOS selecting text under that finger). A long
   message is shown in a box that fits between the top of the screen and the card, scrolled to where it sat, so every
   line can be reached and selected.

   0.266.0 (owner, iPhone): in the main chat the dimmed card with emoji and Reply / Copy made copying harder, not
   easier. opts.holdOnly: only a hold on the `holdOn` buttons (the reaction corner) opens the menu; holding the message
   itself is left to the phone, so its own selection handles and Copy callout come back. The main chat passes it; Teams
   keeps the full menu because on a touch screen its card is the only place for Pin.

   bind(root, opts) is generic: the main chat (chat-reactions.js / app.js) and the Teams page (teams.js) pass their own
   selector, emoji, actions and callbacks. place() is pure so node tests can run it. */
(function () {
  "use strict";

  var HOLD_MS = 350;
  var MOVE_TOL = 10;

  function tw(k, v) {
    if (typeof window !== "undefined" && window.t) return window.t(k, v);
    try {
      var s = require("./i18n/vi.json")[k] || k;
      return String(s).replace(/\{(\w+)\}/g, function (m, n) { return (v && v[n] != null) ? String(v[n]) : m; });
    } catch (e) { return k; }
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  var ic = function (n) { return (typeof window !== "undefined" && window.ic) ? window.ic(n) : ""; };

  // Where the emoji row goes: centred on the finger, just above it, kept inside the screen and above the action card.
  function place(x, y, w, h, vw, vh, sheetH) {
    var left = Math.max(8, Math.min(x - w / 2, vw - w - 8));
    var top = y - h - 28;
    var floor = vh - (sheetH || 0) - h - 12;
    if (top > floor) top = floor;
    if (top < 8) top = Math.min(y + 28, floor);
    return { left: Math.round(left), top: Math.round(Math.max(8, top)) };
  }

  // Where the lifted copy of the message goes: where the bubble sits, kept between the top of the screen and the
  // action card. A bubble taller than that space gets a box filling it, scrolled so its lines stay where they were.
  function frame(top, height, floor) {
    var room = Math.max(40, floor - 8);
    if (height <= room) return { top: Math.round(Math.max(8, Math.min(top, floor - height))), height: Math.round(height), scroll: 0 };
    return { top: 8, height: Math.round(room), scroll: Math.round(Math.max(0, Math.min(8 - top, height - room))) };
  }

  function layerHtml(emoji, cur, actions) {
    var bar = emoji && emoji.length ? '<div class="mp-bar" role="toolbar" aria-label="' + esc(tw("teams.react")) + '">' +
      emoji.map(function (r) {
        return '<button type="button" class="mp-pick' + (cur === r.value ? " is-on" : "") + '" data-mp-react="' + r.value +
          '" aria-label="' + esc(tw(r.key)) + '"><span class="mp-tip">' + esc(tw(r.key)) + '</span><span class="mp-emoji">' +
          r.emoji + "</span></button>";
      }).join("") + "</div>" : "";
    var sheet = (actions || []).length ? '<div class="mp-sheet" role="menu">' + actions.map(function (a, i) {
      return '<button type="button" class="mp-act' + (a.danger ? " is-danger" : "") + '" role="menuitem" data-mp-act="' + i + '">' +
        '<span class="mp-act-ic">' + ic(a.icon) + "</span><span>" + esc(a.label) + "</span></button>";
    }).join("") + "</div>" : "";
    return '<div class="mp-scrim" data-mp-close="1"></div>' + bar + sheet;
  }

  function bind(root, opts) {
    if (!root || !root.addEventListener || typeof document === "undefined") return function () {};
    opts = opts || {};
    var timer = null, sx = 0, sy = 0, target = null, layer = null, sliding = false, hot = null, openedAt = 0, cur = null;
    var free = false;

    function stop() { clearTimeout(timer); timer = null; }

    // html.mp-holding while the card is open: no text selection anywhere on the page (style.css). Not during the
    // 0.35 s wait: that runs on every scroll that starts on a message, and a page-wide class costs a full restyle; the
    // browsers' own long press (about 0.5 s) comes after the card is open anyway.
    function holding() {
      try { document.documentElement.classList.toggle("mp-holding", !!layer); } catch (e) { /* no DOM */ }
    }

    function setHot(btn) {
      if (hot === btn) return;
      if (hot) hot.classList.remove("is-hot");
      hot = btn;
      if (hot) hot.classList.add("is-hot");
      if (layer) layer.classList.toggle("is-picking", !!hot);
    }

    function close() {
      stop();
      sliding = false;
      setHot(null);
      if (layer) { layer.remove(); layer = null; unselect(); }
      free = false;
      if (cur && cur.el) cur.el.classList.remove("mp-target");
      cur = null;
      document.removeEventListener("keydown", onEsc, true);
      holding();
    }

    function onEsc(e) { if (e.key === "Escape") { e.preventDefault(); close(); } }

    function unselect() {
      try { var s = window.getSelection && window.getSelection(); if (s && s.rangeCount) s.removeAllRanges(); } catch (e) { /* old browser */ }
    }

    function open(el, x, y) {
      close();
      var react = opts.canReact ? !!opts.canReact(el) : false;
      var actions = opts.actions ? (opts.actions(el) || []) : [];
      if (!react && !actions.length) return;
      cur = { el: el, actions: actions };
      layer = document.createElement("div");
      layer.className = "mp-layer";
      layer.innerHTML = layerHtml(react ? opts.emoji : null, react && opts.current ? opts.current(el) : "", actions);
      document.body.appendChild(layer);
      el.classList.add("mp-target");
      lift(el);
      var bar = layer.querySelector(".mp-bar"), sheet = layer.querySelector(".mp-sheet");
      if (bar) {
        var vw = window.innerWidth, vh = (window.visualViewport && window.visualViewport.height) || window.innerHeight;
        var pos = place(x, y, bar.offsetWidth, bar.offsetHeight, vw, vh, sheet ? sheet.offsetHeight + 16 : 0);
        bar.style.left = pos.left + "px";
        bar.style.top = pos.top + "px";
      }
      layer.addEventListener("click", onLayerClick);
      document.addEventListener("keydown", onEsc, true);
      openedAt = Date.now();
      free = false;
      sliding = !!bar;
      unselect();
      holding();
      try { if (navigator.vibrate) navigator.vibrate(8); } catch (e) { /* not supported */ }
    }

    // The held message stays bright above the dim layer (Zalo): a copy of its bubble, drawn at the same spot.
    function lift(el) {
      var src = (opts.bubble && el.querySelector(opts.bubble)) || el;
      var r = src.getBoundingClientRect && src.getBoundingClientRect();
      if (!r || !r.width || r.bottom < 0 || r.top > window.innerHeight) return;
      var sheet = layer.querySelector(".mp-sheet");
      var f = frame(r.top, r.height, sheet ? sheet.offsetTop - 8 : window.innerHeight - 8);
      // Wrapped in a box with the message's own classes so the bubble keeps its colours (.msg-javis .bubble ...).
      var copy = document.createElement("div");
      copy.className = String(el.className).replace(/\bmp-target\b/, "") + " mp-lift";
      copy.setAttribute("aria-hidden", "true");
      var inner = src.cloneNode(true);
      inner.removeAttribute("id");
      inner.style.width = r.width + "px"; inner.style.maxWidth = "none"; inner.style.margin = "0";
      copy.appendChild(inner);
      copy.style.left = r.left + "px"; copy.style.top = f.top + "px"; copy.style.width = r.width + "px";
      copy.style.height = f.height + "px";
      // Bubbles use a see-through tint; the box underneath is solid page colour cut to the same corners.
      try { copy.style.borderRadius = window.getComputedStyle(src).borderRadius; } catch (e) { /* old browser */ }
      layer.insertBefore(copy, layer.firstChild.nextSibling);
      if (f.scroll) copy.scrollTop = f.scroll;
    }

    // The first finger has lifted: the lifted copy may now be held again to select part of it (CSS .mp-layer.is-free).
    function setFree() {
      if (!layer || free) return;
      free = true;
      layer.classList.add("is-free");
    }

    function inLift(node) {
      if (node && node.nodeType !== 1) node = node.parentNode;
      return !!(free && node && node.closest && node.closest(".mp-lift"));
    }

    function toast(text) {
      if (!text) return;
      var n = document.createElement("div");
      n.className = "mp-toast";
      n.setAttribute("role", "status");
      n.textContent = text;
      document.body.appendChild(n);
      setTimeout(function () { n.remove(); }, 1400);
    }

    function pick(value) {
      var c = cur;
      close();
      if (c && opts.react) opts.react(c.el, value);
    }

    function onLayerClick(e) {
      // A tap inside the lifted copy only moves or clears the selection: its links and buttons are a picture.
      if (inLift(e.target)) { e.preventDefault(); e.stopPropagation(); return; }
      var t = e.target.closest && e.target.closest("[data-mp-react],[data-mp-act],[data-mp-close]");
      if (!t) return;
      // The click that iOS fires right after the finger lifts must not close the card it just opened.
      if (t.hasAttribute("data-mp-close")) { if (Date.now() - openedAt > 350) close(); return; }
      if (t.hasAttribute("data-mp-react")) return pick(t.getAttribute("data-mp-react"));
      var a = cur && cur.actions[Number(t.getAttribute("data-mp-act"))];
      var el = cur && cur.el;
      close();
      if (a && a.run) { a.run(el); toast(a.done); }
    }

    function point(e) { var p = (e.touches && e.touches[0]) || (e.changedTouches && e.changedTouches[0]); return p || null; }

    // Any new touch while the card is open means the first finger is off the screen (touchend may not come on iOS
    // when its own gesture cancelled the stream).
    function onAnyStart() { if (layer && !timer && Date.now() - openedAt > 50) setFree(); }

    function onStart(e) {
      if (layer || !e.touches || e.touches.length !== 1) { stop(); return; }
      var t = e.target;
      var el = t && t.closest && t.closest(opts.selector);
      if (!el || !root.contains(el)) return;
      // Buttons keep their own tap, except the ones listed in `holdOn` (the reaction button at the bubble's corner, owner
      // 16/10/2026: "ấn giữ vào icon mép phải bên dưới cũng phải hiện emoji"). Holding one opens the same menu; the tap it
      // would have made is swallowed by onEnd (preventDefault), so the hold does not also toggle a like.
      var onBtn = opts.holdOn && t.closest(opts.holdOn);
      if (opts.holdOnly && !onBtn) return;
      if (!onBtn && t.closest("button, a, input, textarea, select, label, summary, .mp-layer")) return;
      if (opts.accept && !opts.accept(el)) return;
      var p = point(e);
      sx = p.clientX; sy = p.clientY; target = el;
      stop();
      timer = setTimeout(function () { timer = null; open(target, sx, sy); }, HOLD_MS);
    }

    function onMove(e) {
      var p = point(e);
      if (!p) return;
      if (timer && (Math.abs(p.clientX - sx) > MOVE_TOL || Math.abs(p.clientY - sy) > MOVE_TOL)) stop();
      if (!layer || !sliding) return;
      // Sliding over the emoji row: no scrolling, the emoji under the finger grows (Facebook style).
      if (e.cancelable) e.preventDefault();
      var under = document.elementFromPoint(p.clientX, p.clientY);
      setHot(under && under.closest ? under.closest(".mp-pick") : null);
    }

    function onEnd(e) {
      stop();
      if (layer && (!e.touches || !e.touches.length)) setFree();
      if (!layer || !sliding) return;
      sliding = false;
      if (e.cancelable) e.preventDefault();   // no ghost click on whatever sits under the finger
      if (hot) return pick(hot.getAttribute("data-mp-react"));
      setHot(null);
    }

    function onCancel() { stop(); if (layer) { sliding = false; setHot(null); } }

    // A long press that opened the card must not also open the browser's own menu. On the document: on Android the
    // menu event lands on the card under the finger, not on root.
    // A second hold on the lifted copy is the exception: that is the selection the owner asked for.
    function onMenu(e) { if (timer || (layer && !inLift(e.target))) e.preventDefault(); }

    // Nor iOS's text selection: a hold in progress or an open card refuses it (owner, iPhone, 16/10/2026).
    function onSelect(e) { if (timer || (layer && !inLift(e.target))) e.preventDefault(); }

    root.classList.add("mp-host");
    root.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchstart", onAnyStart, { passive: true });
    document.addEventListener("touchmove", onMove, { passive: false });
    document.addEventListener("touchend", onEnd, { passive: false });
    document.addEventListener("touchcancel", onCancel);
    document.addEventListener("contextmenu", onMenu);
    document.addEventListener("selectstart", onSelect);
    return function unbind() {
      close();
      root.classList.remove("mp-host");
      root.removeEventListener("touchstart", onStart);
      document.removeEventListener("touchstart", onAnyStart);
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onEnd);
      document.removeEventListener("touchcancel", onCancel);
      document.removeEventListener("contextmenu", onMenu);
      document.removeEventListener("selectstart", onSelect);
    };
  }

  var api = { bind: bind, place: place, frame: frame, layerHtml: layerHtml, HOLD_MS: HOLD_MS };
  if (typeof window !== "undefined") window.JavisMsgPress = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
