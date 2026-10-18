/* msg-swipe.js - swipe a chat message to the left to quote it, on a touch screen (0.216.0).

   Owner, 2026-10-18 (iPhone): "các khung chat khi kéo sang trái 1 bong bóng trò chuyện thì sẽ thành quote lại tin đấy
   luôn", so on a phone quoting a message does not need the long-press menu or the small Quote button. Like Zalo and
   Messenger: the bubble follows the finger to the left, a quote mark appears on the right once the swipe is far enough
   (SWIPE_AT), and lifting the finger there quotes the message. Lifting earlier, or moving mostly up or down (scrolling the
   chat), springs the bubble back and does nothing.

   bind(root, opts) is generic: opts.selector (the messages), opts.bubble (the part that moves), opts.can(msg) (may this
   message be swiped), opts.run(msg) (what a full swipe does). The mouse is left alone: on a computer dragging selects
   text. A touch that starts in a box that scrolls sideways (a wide code block or table) scrolls that box instead.
   decide() is pure so node tests can run it: tests/js/test_msg_swipe.js. */
(function () {
  "use strict";

  var SWIPE_AT = 60;      // px to the left that counts as "quote this"
  var MAX_PULL = 90;      // the bubble never travels further than this
  var START = 12;         // px of movement before a swipe or a scroll is told apart

  // One move of the finger, `dx`/`dy` from where it went down. `on` = the swipe already started.
  // Returns "wait" (too small to tell), "scroll" (vertical: give up), "swipe" (follow the finger) or "ignore" (to the right).
  function decide(dx, dy, on) {
    if (on) return "swipe";
    var ax = Math.abs(dx), ay = Math.abs(dy);
    if (ay > START && ay > ax) return "scroll";
    if (ax <= START || ax <= ay) return "wait";
    return dx < 0 ? "swipe" : "ignore";
  }
  function pull(dx) { return Math.max(-MAX_PULL, Math.min(0, dx)); }
  function armed(dx) { return dx <= -SWIPE_AT; }

  // The touch started inside something that scrolls sideways (a wide code block or table): that box gets the gesture.
  function inSideScroller(t, stop) {
    for (var el = t; el && el !== stop && el.nodeType === 1; el = el.parentElement) {
      if (el.scrollWidth > el.clientWidth + 1) {
        var ox = "";
        try { ox = getComputedStyle(el).overflowX; } catch (e) {}
        if (ox === "auto" || ox === "scroll") return true;
      }
    }
    return false;
  }

  function bind(root, opts) {
    if (!root || !opts) return function () {};
    var s = null;
    var ic = function (n) { return (typeof window !== "undefined" && window.ic) ? window.ic(n) : ""; };
    function end(fire) {
      if (!s) return;
      var sw = s;
      s = null;
      if (sw.bubble) {
        sw.bubble.style.transition = "transform .15s ease";
        sw.bubble.style.transform = "";
        setTimeout(function () { if (sw.bubble) sw.bubble.style.transition = ""; }, 200);
      }
      if (sw.mark && sw.mark.parentNode) sw.mark.parentNode.removeChild(sw.mark);
      sw.el.classList.remove("is-swiping", "is-armed");
      if (fire && sw.on && armed(sw.dx)) { try { opts.run(sw.el); } catch (e) {} }
    }
    function down(e) {
      if (e.pointerType === "mouse") return;
      var msg = e.target.closest && e.target.closest(opts.selector);
      if (!msg || !root.contains(msg)) return;
      if (e.target.closest("button, a, input, textarea, select, summary, [contenteditable]")) return;
      if (opts.can && !opts.can(msg)) return;
      if (inSideScroller(e.target, msg)) return;
      s = { el: msg, bubble: msg.querySelector(opts.bubble) || msg, x: e.clientX, y: e.clientY, dx: 0, on: false, mark: null };
    }
    function move(e) {
      if (!s) return;
      // The long-press menu (msg-press.js) opened: the finger is choosing there, not swiping.
      if (document.querySelector(".mp-layer")) { end(false); return; }
      var dx = e.clientX - s.x, dy = e.clientY - s.y;
      var d = decide(dx, dy, s.on);
      if (d === "scroll" || d === "ignore") { end(false); return; }
      if (d === "wait") return;
      if (!s.on) {
        s.on = true;
        s.el.classList.add("is-swiping");
        var m = document.createElement("span");
        m.className = "msg-swipe-mark";
        m.setAttribute("aria-hidden", "true");
        m.innerHTML = ic("quote");
        s.el.appendChild(m);
        s.mark = m;
      }
      s.dx = pull(dx);
      s.bubble.style.transform = "translateX(" + s.dx + "px)";
      var was = s.el.classList.contains("is-armed");
      s.el.classList.toggle("is-armed", armed(s.dx));
      if (!was && armed(s.dx) && navigator.vibrate) { try { navigator.vibrate(8); } catch (err) {} }
      if (s.mark) s.mark.style.opacity = String(Math.min(1, -s.dx / SWIPE_AT));
    }
    function up() { end(true); }
    function cancel() { end(false); }
    root.addEventListener("pointerdown", down);
    root.addEventListener("pointermove", move);
    root.addEventListener("pointerup", up);
    root.addEventListener("pointercancel", cancel);
    return function unbind() {
      end(false);
      root.removeEventListener("pointerdown", down);
      root.removeEventListener("pointermove", move);
      root.removeEventListener("pointerup", up);
      root.removeEventListener("pointercancel", cancel);
    };
  }

  var api = { bind: bind, decide: decide, pull: pull, armed: armed, SWIPE_AT: SWIPE_AT, MAX_PULL: MAX_PULL };
  if (typeof window !== "undefined") window.JavisMsgSwipe = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
