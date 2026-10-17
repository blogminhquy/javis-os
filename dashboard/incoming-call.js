/* incoming-call.js - Javis calls you at a set time (0.203.0).

   Idea borrowed from OpenMausBot's calendar calls: a reminder created with the "call" option rings the open
   dashboard like an incoming phone call. The server marks the pushed message's JAVIS_VIEC block with
   "call": "1" (server/reminders.py). Answering starts the ordinary voice call (the mic button, so Live when
   it is set up, the basic voice path otherwise) and its first line asks Javis to read the reminder or report
   aloud, then keep talking. Declining or not answering in 45 seconds leaves the message in the chat as usual.

   Nothing rings when no Javis tab is open: Telegram still gets the text (and the voice note when "read it
   aloud" is on). The ringtone is a short synthesized double beep, so no audio file ships with it.

   `parse` and `script` are pure (tested under node); `show` draws the card. */
(function () {
  "use strict";

  var RE = /<!--\s*JAVIS_VIEC:\s*(\{[\s\S]*?\})\s*-->/;
  var RING_MS = 45000, TEXT_MAX = 1500;

  function tr(t, key, vars) {
    var s = typeof t === "function" ? t(key, vars) : key;
    if (vars) {
      s = String(s).replace(/\{(\w+)\}/g, function (m, name) {
        return Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : m;
      });
    }
    return s;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* {title, text} when `raw` is a reminder push marked as a call, else null. `text` is what Javis reads:
     hidden blocks and the voice-note link removed, capped. */
  function parse(raw) {
    var m = RE.exec(String(raw || ""));
    if (!m) return null;
    var v;
    try { v = JSON.parse(m[1]); } catch (e) { return null; }
    if (!v || v.kind !== "reminder" || !v.call || v.status === "failed") return null;
    var text = String(raw).replace(/<!--[\s\S]*?-->/g, "").replace(/\[[^\]]*\]\([^)]*\.(?:mp3|ogg|wav|m4a)\)/gi, "")
      .replace(/\n{3,}/g, "\n\n").trim();
    if (text.length > TEXT_MAX) text = text.slice(0, TEXT_MAX - 1) + "…";
    return { title: String(v.title || "").slice(0, 160), text: text };
  }

  /* The call's first line: what Javis is asked to read. */
  function script(c, t) {
    return tr(t, "call.in_script", { title: c.title || tr(t, "call.in_title_none"), text: c.text });
  }

  var ringCtx = null, ringTimer = null;
  function beep() {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      ringCtx = ringCtx || new AC();
      if (ringCtx.state === "suspended" && ringCtx.resume) ringCtx.resume();
      [0, 0.45].forEach(function (at) {
        var o = ringCtx.createOscillator(), g = ringCtx.createGain(), t0 = ringCtx.currentTime + at;
        o.frequency.value = 440; o.connect(g); g.connect(ringCtx.destination);
        g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(0.2, t0 + 0.03);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.35);
        o.start(t0); o.stop(t0 + 0.4);
      });
    } catch (e) { /* autoplay blocked: the card still shows */ }
    try { if (navigator.vibrate) navigator.vibrate([300, 150, 300]); } catch (e) {}
  }
  function stopRing() { clearInterval(ringTimer); ringTimer = null; }

  var current = null;
  /* Draws the incoming-call card. opts: {title, t, onAnswer, onDecline, onMissed, timeoutMs}. One call at a time:
     a new one replaces an unanswered one. Returns {close}. */
  function show(opts) {
    opts = opts || {};
    if (current) current.close();
    var t = opts.t, doc = document;
    var box = doc.createElement("div");
    box.className = "jv-incoming";
    box.setAttribute("role", "alertdialog");
    box.style.cssText = "position:fixed;left:50%;top:16px;transform:translateX(-50%);z-index:9999;width:min(92vw,380px);"
      + "padding:16px;border-radius:14px;background:var(--panel,#1e1e24);color:var(--text,#fff);font-size:16px;"
      + "box-shadow:0 10px 30px rgba(0,0,0,.35);border:1px solid var(--hairline,#444)";
    box.innerHTML = '<div style="font-size:14px;color:var(--text3,#aaa)">' + esc(tr(t, "call.in_label")) + "</div>"
      + '<div style="font-size:18px;font-weight:600;margin:4px 0 14px">' + esc(opts.title || tr(t, "call.in_title_none")) + "</div>"
      + '<div style="display:flex;gap:10px">'
      + '<button type="button" class="jv-in-no" style="flex:1;min-height:44px;font-size:16px;border-radius:10px;border:0;background:var(--red,#d33);color:#fff">'
      + esc(tr(t, "call.in_decline")) + "</button>"
      + '<button type="button" class="jv-in-yes" style="flex:1;min-height:44px;font-size:16px;border-radius:10px;border:0;background:var(--green,#2a8);color:#fff">'
      + esc(tr(t, "call.in_answer")) + "</button></div>";
    doc.body.appendChild(box);
    var done = false, timer = 0;
    function close() {
      if (done) return;
      done = true; stopRing(); clearTimeout(timer);
      if (box.parentNode) box.parentNode.removeChild(box);
      if (current && current.box === box) current = null;
    }
    box.querySelector(".jv-in-yes").onclick = function () { close(); if (opts.onAnswer) opts.onAnswer(); };
    box.querySelector(".jv-in-no").onclick = function () { close(); if (opts.onDecline) opts.onDecline(); };
    timer = setTimeout(function () { close(); if (opts.onMissed) opts.onMissed(); }, opts.timeoutMs || RING_MS);
    beep(); ringTimer = setInterval(beep, 2500);
    current = { box: box, close: close };
    return current;
  }

  var API = { parse: parse, script: script, show: show, RING_MS: RING_MS };
  if (typeof window !== "undefined") window.JavisIncomingCall = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
