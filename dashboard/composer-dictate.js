/* composer-dictate.js - the main chat's "record, it becomes text" mic (0.230.0).

   The owner asked on 2026-10-19 for two separate voice buttons in the composer, like Codex and ChatGPT: the sound-wave
   button (#voiceBtn) stays the live voice chat, and a new mic (#dictBtn) only records. While recording, the button row
   turns into a bar: X drops the recording, a meter shows the mic level, a timer runs, the square stops and leaves the
   text in the box to edit, and the send button stops and sends in one press. Nothing is sent by itself.

   The speech work is dictate.js (Web Speech live text, Groq Whisper on stop when the server has an upload ear); this
   file only draws the composer around it. fmtTime and levelOf are pure so node tests can run them.

   0.409.0, phone (owner report 2026-10-30, iPhone): the first recording worked, after that X and stop did nothing and
   the timer ran on. The trap: stop focused the text box, so the keyboard came up; the next press of the mic made the
   still focused box read-only, iOS dropped the keyboard but kept the focus and left the page slid up, and on that slid
   page iOS hit-tests a fixed layer away from where it draws it: a tap on X or stop landed on the box instead (the
   "AutoFill" bubble in the owner's screenshot). On a touch screen the box now gives up focus while recording (and
   cannot take it back), stop no longer pops the keyboard, and mobile-chat.js slides the page back once the keyboard
   is down even when something is still focused. */
(function () {
  "use strict";

  var MAX_SECONDS = 300;   // a voice note, not a meeting recorder: stop by itself after 5 minutes

  function fmtTime(sec) {
    sec = Math.max(0, Math.floor(Number(sec) || 0));
    var s = sec % 60;
    return Math.floor(sec / 60) + ":" + (s < 10 ? "0" : "") + s;
  }

  // Loudness of one time-domain frame (bytes, 128 = silence) as 0..1. The square root lifts quiet speech so it still
  // draws a visible bar, and the floor keeps room hiss flat.
  function levelOf(bytes) {
    if (!bytes || !bytes.length) return 0;
    var sum = 0;
    for (var i = 0; i < bytes.length; i++) { var x = (bytes[i] - 128) / 128; sum += x * x; }
    var v = Math.sqrt(Math.sqrt(sum / bytes.length)) * 1.6 - 0.12;
    return v < 0 ? 0 : v > 1 ? 1 : v;
  }

  var pure = { fmtTime: fmtTime, levelOf: levelOf, MAX_SECONDS: MAX_SECONDS };
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
  if (typeof document === "undefined") return;
  window.JavisComposerDictate = pure;

  function tw(k) { return window.t ? window.t(k) : k; }
  // A finger, not a mouse: no Shift+Enter, an on-screen keyboard that comes up with focus.
  function touch() {
    try { return !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches); } catch (e) { return false; }
  }
  // Drop the focus of the text box so iOS puts the keyboard away and the page settles before the bar is used.
  function letGo(inp) {
    if (inp && touch() && document.activeElement === inp) { try { inp.blur(); } catch (e) {} }
  }
  function $(id) { return document.getElementById(id); }

  // state: "idle" | "listening" | "transcribing"
  var S = { dict: null, state: "idle", base: "", sendAfter: false, startedAt: 0, clock: null,
    ctx: null, src: null, analyser: null, buf: null, raf: 0, levels: [], lastPush: 0 };

  function note(key) {
    try { if (window.JavisNoteFlash) window.JavisNoteFlash(tw(key)); } catch (e) {}
  }

  function inCall() {
    var v = $("voiceBtn");
    return !!(v && (v.classList.contains("handsfree") || v.classList.contains("in-call")));
  }

  function writeInput(value) {
    var inp = $("chatInput");
    if (!inp) return;
    inp.value = value;
    // app.js grows the box and shows the send button on "input".
    inp.dispatchEvent(new Event("input", { bubbles: true }));
    inp.scrollTop = inp.scrollHeight;
  }

  // ───────────── level meter ─────────────

  function onStream(stream) {
    stopMeter();
    if (!stream) return;
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      if (!S.ctx) S.ctx = new AC();
      if (S.ctx.state === "suspended" && S.ctx.resume) S.ctx.resume();
      S.src = S.ctx.createMediaStreamSource(stream);
      S.analyser = S.ctx.createAnalyser();
      S.analyser.fftSize = 512;
      S.buf = new Uint8Array(S.analyser.fftSize);
      S.src.connect(S.analyser);
    } catch (e) { S.src = null; S.analyser = null; }
  }

  function stopMeter() {
    try { if (S.src) S.src.disconnect(); } catch (e) {}
    S.src = null; S.analyser = null;
  }

  function draw(now) {
    S.raf = 0;
    if (S.state !== "listening") return;
    var cv = $("dictWave");
    if (cv && cv.clientWidth) {
      if (S.analyser && now - S.lastPush > 70) {
        S.analyser.getByteTimeDomainData(S.buf);
        S.levels.push(levelOf(S.buf));
        S.lastPush = now;
      }
      var dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight || 28;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      }
      var g = cv.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      g.fillStyle = getComputedStyle(cv).color;
      var step = 5, slots = Math.floor(w / step);
      if (S.levels.length > slots) S.levels.splice(0, S.levels.length - slots);
      var empty = slots - S.levels.length;
      for (var i = 0; i < slots; i++) {
        var lv = i < empty ? 0 : S.levels[i - empty];
        var bh = Math.max(2, lv * (h - 2));
        g.globalAlpha = lv > 0 ? 1 : 0.45;
        g.fillRect(i * step + 1.5, (h - bh) / 2, 2, bh);
      }
      g.globalAlpha = 1;
    }
    S.raf = requestAnimationFrame(draw);
  }

  // ───────────── clock ─────────────

  function tick() {
    var sec = (Date.now() - S.startedAt) / 1000;
    var el = $("dictTime");
    if (el) el.textContent = fmtTime(sec);
    if (sec >= MAX_SECONDS && S.dict && S.state === "listening") S.dict.stop();
  }

  function stopClock() {
    if (S.clock) clearInterval(S.clock);
    S.clock = null;
    if (S.raf) cancelAnimationFrame(S.raf);
    S.raf = 0;
  }

  // ───────────── states ─────────────

  function drawState(st) {
    var card = $("hudVoice"), inp = $("chatInput"), busy = $("dictBusy"), stopB = $("dictStop"), btn = $("dictBtn");
    var on = st !== "idle";
    if (card) {
      card.classList.toggle("dictating", on);
      card.classList.toggle("dict-busy-on", st === "transcribing");
    }
    if (busy) busy.hidden = st !== "transcribing";
    if (stopB) stopB.disabled = st === "transcribing";
    if (btn) btn.setAttribute("aria-pressed", on ? "true" : "false");
    // The words arrive by themselves; typing at the same time would be overwritten by the next result.
    if (inp) inp.readOnly = on;
    if (st === "listening" && !S.clock) {
      S.startedAt = Date.now();
      tick();
      S.clock = setInterval(tick, 250);
      if (!S.raf) S.raf = requestAnimationFrame(draw);
    }
    if (st !== "listening") stopClock();
    if (!on) stopMeter();
  }

  // Browser speech hears one language only, so a Vietnamese sentence with English words comes out wrong. Only an ear
  // (a model listening to the audio again) fixes that; say once per page how to get one when the machine has none.
  var earTipShown = false;
  // 0.419.0: off. The owner (2026-10-30): ordinary users never set Groq up, so a tip pointing at an API key is noise.
  var EAR_TIP = false;
  function earTip(D, inp) {
    if (!EAR_TIP || earTipShown || !D || !D.ear || D.ear() !== "" || !inp || inp.value === S.base) return;
    earTipShown = true;
    note("dict.no_ear");
  }

  function finished() {
    var inp = $("chatInput"), send = S.sendAfter;
    S.dict = null;
    S.sendAfter = false;
    earTip(window.JavisDictate, inp);
    if (!inp) return;
    inp.readOnly = false;
    if (send && inp.value.trim()) {
      var b = $("sendBtn");
      if (b && !b.disabled) { b.click(); return; }
    }
    // A phone keeps the keyboard down: it would cover the text and start the trap described at the top. One tap on the
    // box brings it up when the owner wants to edit.
    if (touch()) return;
    try { inp.focus(); var n = inp.value.length; inp.setSelectionRange(n, n); } catch (e) {}
  }

  function start() {
    var D = window.JavisDictate;
    if (!D) { note("dict.unsupported"); return; }
    if (S.state !== "idle") return;
    if (inCall()) { note("dict.in_call"); return; }
    var inp = $("chatInput");
    letGo(inp);
    S.base = inp ? inp.value : "";
    S.sendAfter = false;
    S.levels = [];
    S.dict = D.create({
      onText: function (text) {
        if (S.state === "idle") return;
        writeInput(D.joinText(S.base, text));
      },
      onState: function (st) {
        var was = S.state;
        S.state = st;
        drawState(st);
        if (st === "idle" && was !== "idle") finished();
      },
      onError: function (code) {
        // 0.419.0: Safari on an iPhone has no padlock in the address bar; say where its mic switch really is.
        var ios = D.isIOS && D.isIOS();
        note(code === "denied" ? (ios ? "dict.denied_ios" : "dict.denied")
          : code === "service" ? (ios ? "dict.service_ios" : "dict.service") : code === "unsupported" ? "dict.unsupported"
          : code === "nothing" ? "dict.nothing" : "dict.failed");
      },
      onStream: onStream
    });
    // iOS only lets an AudioContext run when it is made inside the press; the mic stream arrives a moment later,
    // outside it, and a context made then stays suspended (a flat meter). Make or wake it here (0.339.0).
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (AC && !S.ctx) S.ctx = new AC();
      if (S.ctx && S.ctx.state !== "running" && S.ctx.resume) S.ctx.resume();
    } catch (e) {}
    // Show the bar at once; the mic and the ear answer a moment later.
    S.state = "listening";
    drawState("listening");
    S.dict.start();
  }

  function stop() { if (S.dict && S.state === "listening") S.dict.stop(); }

  function sendNow() {
    if (!S.dict) return;
    S.sendAfter = true;
    if (S.state === "listening") S.dict.stop();
  }

  function cancel() {
    if (!S.dict) return;
    var base = S.base;
    S.sendAfter = false;
    writeInput(base);
    S.dict.cancel();
    writeInput(base);
  }

  function init() {
    var card = $("hudVoice"), btn = $("dictBtn");
    if (!card || !btn) return;
    btn.addEventListener("click", function () { if (S.state === "idle") start(); else stop(); });
    // While recording the box only shows the words; on a phone a tap must not focus it again (keyboard, AutoFill).
    var inp = $("chatInput");
    if (inp) inp.addEventListener("focus", function () { if (S.state !== "idle") letGo(inp); });
    var c = $("dictCancel"), s = $("dictStop");
    if (c) c.addEventListener("click", cancel);
    if (s) s.addEventListener("click", stop);
    // Send while recording: stop, wait for the final text, then send it. Captured on the card so app.js's own send
    // handler never sees a half-heard sentence.
    card.addEventListener("click", function (e) {
      if (S.state === "idle") return;
      var t = e.target && e.target.closest ? e.target.closest("#sendBtn") : null;
      if (!t) return;
      e.preventDefault(); e.stopPropagation();
      sendNow();
    }, true);
    // Enter sends, Esc drops the recording (and does not stop a running answer, which is what Esc does otherwise).
    window.addEventListener("keydown", function (e) {
      if (S.state === "idle") return;
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cancel(); return; }
      // Enter follows the chat's own rule (JavisActs.enterSends): a phone's Enter stays a new line here too.
      var sends = window.JavisActs ? window.JavisActs.enterSends(e, false) : e.key === "Enter" && !e.shiftKey;
      if (sends && e.target === $("chatInput")) {
        e.preventDefault(); e.stopPropagation(); sendNow();
      }
    }, true);
    // A phone that locks or a tab switched away cuts the mic: keep what was heard instead of losing it.
    document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
