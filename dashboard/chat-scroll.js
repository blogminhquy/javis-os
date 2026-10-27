/* chat-scroll.js - "stick to the latest message" for a chat list, shared by the main chat (app.js) and the Team chat.

   Moved out of app.js (0.180.0 and earlier) so both chats behave the same:
     - The list follows new content only while the reader is at the end (within `near` px). Reading higher up, nothing
       pulls the view down.
     - A round "jump to latest" button shows as soon as the reader leaves the end (owner, 2026-07-31: reading back a long
       chat and scrolling down by hand took too long). When something new arrives meanwhile it grows into a "New
       messages" pill. Back at the end it hides and drops the pill.
     - On a computer with a mouse, following holds while the mouse is on a message's action row or reaction (`hold`), or
       is moving over a message (moved in the last HOLD_MOVE_MS), so the Copy button does not slide away right under the
       cursor (0.180.0, owner: "bấm copy mà tin cứ chạy mất"). When the hold ends, it catches up.
     - keep(fn): run fn (which adds older messages ABOVE) and keep the reader on the same message.
     - The list getting shorter (phone keyboard, a taller composer) keeps the end in view while following (0.358.0).

   attach(area, opts) -> controller. opts: button (an existing element; one is made otherwise), buttonClass, msg (the
   message selector, ".msg"), hold (selectors that hold the follow while hovered), near (px, 90), suspended() (true while
   the caller is inserting older messages: no scrolling then), key (attribute naming a message, anchors keep()),
   followLoads (a picture loading while at the end keeps the end in view). The button must be placed by the caller (last child of the
   area, so `position: sticky; bottom` keeps it at the bottom); until it has a parent it is left alone.
   Controller: toBottom(force), update(), draw(hasNew), stuck(), setStuck(v), nearEnd(), holding(), keep(fn), detach(). */
(function () {
  "use strict";

  var HOLD_MOVE_MS = 1200;
  var NEAR_PX = 90;

  function tw(key) {
    if (typeof window !== "undefined" && window.t) return window.t(key);
    try { return require("./i18n/vi.json")[key] || key; } catch (e) { return key; }
  }

  function attach(area, opts) {
    opts = opts || {};
    var win = opts.win || (typeof window !== "undefined" ? window : null);
    var near = opts.near || NEAR_PX;
    var msgSel = opts.msg || ".msg";
    var hoverSel = msgSel.split(",").map(function (s) { return s.trim() + ":hover"; }).join(", ");
    var holdSel = opts.hold || "";
    var now = opts.now || function () { return Date.now(); };
    var btn = opts.button;
    if (!btn) {
      btn = area.ownerDocument.createElement("button");
      btn.type = "button";
      if (opts.buttonClass) btn.className = opts.buttonClass;
    }
    var icon = (win && typeof win.ic === "function") ? win.ic("chevron-down") : "↓";
    var st = { stuck: true, movedAt: 0, wait: null };

    function mounted() { return !!btn.parentNode; }
    // Two looks: only reading back (a small round arrow), or something new arrived meanwhile ("New messages").
    function draw(hasNew) {
      btn.classList.toggle("has-new", !!hasNew);
      btn.innerHTML = hasNew ? icon + " " + tw("app.new_msg") : icon;
      btn.title = hasNew ? tw("app.new_msg_title") : tw("app.scroll_bottom");
      btn.setAttribute("aria-label", btn.title);
    }
    function nearEnd() { return area.scrollHeight - area.scrollTop - area.clientHeight < near; }
    function update() {
      if (!mounted()) return;                       // no message yet: the button is not placed
      if (st.stuck) { btn.classList.remove("show"); draw(false); return; }
      btn.classList.add("show");
    }
    function mouse() {
      try { return !!(win && win.matchMedia && win.matchMedia("(hover: hover) and (pointer: fine)").matches); } catch (e) { return false; }
    }
    function holding() {
      if (!mouse()) return false;
      if (holdSel && area.querySelector(holdSel)) return true;
      return now() - st.movedAt < HOLD_MOVE_MS && !!area.querySelector(hoverSel);
    }
    function later() {
      if (st.wait) return;
      st.wait = setTimeout(function again() {
        if (holding()) { st.wait = setTimeout(again, 250); return; }
        st.wait = null;
        toBottom();
      }, 250);
    }
    // force: jump to the end and stick there (own message sent, button pressed, chat opened). Otherwise follow only when
    // stuck to the end; reading higher up, the button turns into "New messages".
    function toBottom(force) {
      if (opts.suspended && opts.suspended()) return;
      if (force) st.stuck = true;
      if (st.stuck && !force && holding()) { later(); return; }
      if (st.stuck) {
        area.scrollTop = area.scrollHeight;
        btn.classList.remove("show");
        draw(false);
      } else if (mounted()) {
        draw(true);
        btn.classList.add("show");
      }
    }
    // Older messages go in ABOVE what is on screen. With opts.key (an attribute naming each message, e.g. "data-mid")
    // the first message in view is the anchor: after fn() redraws, the view is moved so that same message sits at the
    // same height (robust when the redraw rebuilt the list and pictures below have not loaded yet). Without a key, or
    // when the anchor is gone, measure from the BOTTOM: the height grows by exactly what was added on top.
    function anchorOf() {
      if (!opts.key) return null;
      var top = area.getBoundingClientRect().top;
      var list = area.querySelectorAll(msgSel);
      for (var i = 0; i < list.length; i++) {
        var r = list[i].getBoundingClientRect();
        if (r.bottom > top) return { key: list[i].getAttribute(opts.key), y: r.top - top };
      }
      return null;
    }
    function keep(fn) {
      var fromEnd = area.scrollHeight - area.scrollTop;
      var a = anchorOf();
      try { fn(); } finally {
        var el = null;
        if (a && a.key != null) {
          var list = area.querySelectorAll(msgSel);
          for (var i = 0; i < list.length && !el; i++) if (list[i].getAttribute(opts.key) === a.key) el = list[i];
        }
        if (el) area.scrollTop += (el.getBoundingClientRect().top - area.getBoundingClientRect().top) - a.y;
        else area.scrollTop = area.scrollHeight - fromEnd;
      }
    }
    // Pictures load after the list is drawn and push the end down: when following the end, follow them too.
    function onLoad(e) {
      var t = e.target;
      if (opts.followLoads && t && t.tagName === "IMG" && st.stuck && !(opts.suspended && opts.suspended())) {
        area.scrollTop = area.scrollHeight;
      }
    }

    function onScroll() {
      st.stuck = nearEnd();
      update();                                     // leaving the end shows the button at once, no new message needed
    }
    // 0.358.0 (owner: "gửi xong không thấy hiện câu của mình"): the list gets SHORTER without any scroll event when the
    // phone keyboard opens, the composer grows (reply bar, file chips, a note line) or is drawn after the messages. The
    // browser keeps scrollTop, so the newest message slid under the composer. While following the end, stay at it.
    var lastH = area.clientHeight;
    var ro = null;
    function onResize() {
      var h = area.clientHeight;
      if (h === lastH) return;
      lastH = h;
      if (st.stuck && !(opts.suspended && opts.suspended())) area.scrollTop = area.scrollHeight;
    }
    if (win && typeof win.ResizeObserver === "function") {
      ro = new win.ResizeObserver(onResize);
      ro.observe(area);
    }
    function onMove(e) { if (e.target && e.target.closest && e.target.closest(msgSel)) st.movedAt = now(); }
    function onLeave() { st.movedAt = 0; }
    function onClick() { toBottom(true); }
    function onLang() { draw(btn.classList.contains("has-new")); }
    area.addEventListener("scroll", onScroll);
    area.addEventListener("load", onLoad, true);   // load does not bubble: capture
    area.addEventListener("mousemove", onMove);
    area.addEventListener("mouseleave", onLeave);
    btn.addEventListener("click", onClick);
    if (win && win.addEventListener) win.addEventListener("javis:i18n", onLang);
    draw(false);

    return {
      button: btn,
      toBottom: toBottom,
      update: update,
      draw: draw,
      keep: keep,
      nearEnd: nearEnd,
      holding: holding,
      stuck: function () { return st.stuck; },
      setStuck: function (v) { st.stuck = !!v; update(); },
      detach: function () {
        clearTimeout(st.wait); st.wait = null;
        area.removeEventListener("scroll", onScroll);
        area.removeEventListener("load", onLoad, true);
        area.removeEventListener("mousemove", onMove);
        area.removeEventListener("mouseleave", onLeave);
        btn.removeEventListener("click", onClick);
        if (win && win.removeEventListener) win.removeEventListener("javis:i18n", onLang);
        if (ro) { ro.disconnect(); ro = null; }
      }
    };
  }

  var API = { attach: attach, HOLD_MOVE_MS: HOLD_MOVE_MS, NEAR_PX: NEAR_PX };
  if (typeof window !== "undefined") window.JavisChatScroll = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
