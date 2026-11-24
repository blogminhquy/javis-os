/* chat-pins.js - the pinned messages bar above the main chat: Partners (Cộng sự) and Chat (2026-11-24).

   Owner, 2026-11-24, Zalo screenshots and then "cả cộng sự cả hội thoại": the bar the Chatbot page's customer chats got
   (pin-bar.js) also sits above the main chat, so a pinned answer is found again with one tap. Answers were pinnable
   since 0.374.0 (the pin under an answer, app.js doiGhim) and showed only as marks in the outline rail (chat-marks.js);
   the bar adds the Zalo view of them: the newest pin, "+N pinned" opening all of them, "..." with "Move to top" and
   "Unpin", and a tap that goes to the answer, paging back through older messages when it is not loaded yet.

   The list comes from GET /sessions/<id>/pins (newest pin first), so pins older than what the chat has loaded show too.
   It is read again when the open chat changes and when a pin is saved (app.js fires "jv-pins-saved" on #chatArea).

   Where it sits: INSIDE #chatArea, sticky at the top, like the outline rail (chat-marks.js decision 2): #chatArea is the
   one chat node that Partners and Chat borrow from each other, so the bar travels with it and needs no path back. It is
   put in only when the chat has a pin: `.transcript:empty::after` is the "type to start" hint, and a standing child
   would hide it (same trap as #newMsgBtn). app.js gives what it alone knows through window.JavisChatPinHost. */
(function () {
  "use strict";

  var api = null;
  var S = { sid: null, pins: [], open: false, menu: "", seq: 0, sig: null };

  function tw(k, v) { return window.t ? window.t(k, v) : k; }
  function ic(n) { return window.ic ? window.ic(n) : ""; }
  function host() { return window.JavisChatPinHost || null; }
  function area() { return document.getElementById("chatArea"); }
  function bar() { var a = area(); return a ? a.querySelector(":scope > .chat-pinbar") : null; }

  // Who wrote a pin: the partner open on the Partners page, else Javis.
  function who(p) {
    if (p.role === "user") return tw("ht.ban");
    var W = window.JavisWorkspace;
    var n = W && W.currentName ? W.currentName() : "";
    return n || "Javis";
  }
  function preview(p) { return { icon: "", text: window.JavisPinBar ? window.JavisPinBar.plain(p.text) : String(p.text || "") }; }

  function sigNow() {
    var P = window.JavisPinBar;
    return (P ? P.sig(S.pins) : "") + "|" + (S.open ? 1 : 0) + "|" + S.menu + "|" + who({});
  }

  // Draw (or take away) the bar. A reader at the bottom of the chat stays at the bottom.
  function draw(force) {
    var a = area(), P = window.JavisPinBar;
    if (!a || !P) return;
    var b = bar();
    if (!S.pins.length) { if (b) b.remove(); S.sig = null; return; }
    if (b && !force && S.sig === sigNow()) return;
    var atBottom = a.scrollHeight - a.scrollTop - a.clientHeight < 80;
    if (!b) {
      b = document.createElement("div");
      b.className = "chat-pinbar";
      b.addEventListener("click", onClick);
      b.addEventListener("keydown", onKey);
      a.insertBefore(b, a.firstChild);
    }
    S.sig = sigNow();
    b.innerHTML = P.barHtml(S.pins, { open: S.open, menu: S.menu, ic: ic, who: who, preview: preview });
    b.classList.toggle("open", S.open && S.pins.length > 1);
    if (atBottom) a.scrollTop = a.scrollHeight;
  }

  // Read the open chat's pins. A newer read (another chat opened meanwhile) wins.
  function load() {
    var H = host();
    var sid = H ? H.sid() : null;
    var seq = ++S.seq;
    if (sid !== S.sid) { S.open = false; S.menu = ""; }
    S.sid = sid;
    if (!sid) { S.pins = []; draw(); return Promise.resolve(); }
    return fetch("/sessions/" + encodeURIComponent(sid) + "/pins").then(function (r) { return r.ok ? r.json() : { pins: [] }; })
      .then(function (d) {
        if (seq !== S.seq) return;
        S.pins = (d && d.pins) || [];
        if (S.pins.length < 2) S.open = false;
        draw();
      }).catch(function () { /* offline: keep what is shown */ });
  }

  function post(mid, body) {
    return fetch("/sessions/" + encodeURIComponent(S.sid) + "/messages/" + encodeURIComponent(mid) + "/pin", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return r.ok && d.ok ? d : Promise.reject(d.error || r.status); }); });
  }

  function act(mid, what) {
    var H = host();
    S.menu = "";
    var body = what === "unpin" ? { pinned: false } : { pinned: true, top: true };
    post(mid, body).then(function () {
      if (H && what === "unpin") H.mark(mid, false);
      return load();
    }, function (err) {
      draw(true);
      try { alert(tw("pin.err", { err: String(err) })); } catch (e) { /* no dialogs */ }
    });
  }

  function findMsg(mid) {
    var a = area();
    if (!a) return null;
    var ds = a.querySelectorAll(".msg[data-mid]");
    for (var i = 0; i < ds.length; i++) if (String(ds[i].dataset.mid) === String(mid)) return ds[i];
    return null;
  }

  // Go to a pinned answer: older pages load until it is in the chat, then it is centred and lit up for a moment.
  function goTo(mid) {
    var H = host(), sid = S.sid, tries = 0;
    function step() {
      if (S.sid !== sid) return;
      var el = findMsg(mid);
      if (el) {
        el.scrollIntoView({ block: "center", behavior: "smooth" });
        el.classList.remove("pin-flash");
        void el.offsetWidth;          // restart the light when the same pin is tapped twice
        el.classList.add("pin-flash");
        setTimeout(function () { el.classList.remove("pin-flash"); }, 2000);
        return;
      }
      if (!H || !H.hasOlder() || tries++ > 60) return;
      var wait = H.busy() ? new Promise(function (ok) { setTimeout(ok, 150); }) : Promise.resolve(H.loadOlder());
      wait.then(step, step);
    }
    step();
  }

  function onClick(e) {
    var t = e.target.closest && e.target.closest("[data-pin-go],.pb-more,.pb-less,[data-pin-menu],[data-pin-act]");
    if (!t) return;
    e.preventDefault();
    if (t.hasAttribute("data-pin-act")) return act(t.dataset.mid, t.dataset.pinAct);
    if (t.hasAttribute("data-pin-menu")) {
      S.menu = S.menu === t.dataset.pinMenu ? "" : t.dataset.pinMenu;
      draw(true);
      var first = S.menu && bar() && bar().querySelector(".pb-menu .pb-mi");
      if (first && e.detail === 0) first.focus();
      return;
    }
    if (t.classList.contains("pb-more")) { S.open = !S.open; S.menu = ""; draw(true); return; }
    if (t.classList.contains("pb-less")) {
      S.open = false; S.menu = ""; draw(true);
      var more = bar() && bar().querySelector(".pb-more");
      if (more) more.focus();
      return;
    }
    var go = t.dataset.pinGo;
    if (S.open || S.menu) { S.open = false; S.menu = ""; draw(true); }
    goTo(go);
  }

  function onKey(e) {
    if (e.key !== "Escape" || !(S.menu || S.open)) return;
    e.preventDefault(); e.stopPropagation();
    var back = S.menu;
    S.menu = "";
    if (!back) S.open = false;
    draw(true);
    var f = back && bar() && bar().querySelector('[data-pin-menu="' + back + '"]');
    if (f) f.focus();
  }

  // A click anywhere else closes the menu and the open list.
  function onOutside(ev) {
    if (!(S.menu || S.open)) return;
    var b = bar();
    if (b && b.contains(ev.target)) {
      if (S.menu && !(ev.target.closest && ev.target.closest(".pb-menu, [data-pin-menu]"))) { S.menu = ""; draw(true); }
      return;
    }
    S.menu = ""; S.open = false; draw(true);
  }

  // The chat's children change when a chat is opened, cleared or redrawn: another chat is read afresh, the same chat
  // gets its bar back if a redraw took it away.
  var _t = null;
  function onMutate() {
    clearTimeout(_t);
    _t = setTimeout(function () {
      var H = host();
      if ((H ? H.sid() : null) !== S.sid) load();
      else if (S.pins.length && !bar()) draw(true);
    }, 120);
  }

  function start() {
    var a = area();
    if (!a || api) return;
    api = { load: load };
    try { new MutationObserver(onMutate).observe(a, { childList: true }); } catch (e) { /* old browser: no bar */ }
    a.addEventListener("jv-pins-saved", function () { load(); });
    document.addEventListener("mousedown", onOutside, true);
    load();
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
  }
  if (typeof window !== "undefined") window.JavisChatPins = { reload: function () { return load(); } };
})();
