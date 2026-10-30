/* dictate.js - the mic button of a text composer: speak, the words land in the input (0.176.0).

   Team chat has no voice call, yet the owner still wants to talk instead of type (2026-10-16). This is NOT the
   voice call of the main chat (voice.js): no turn taking, no reading aloud, nothing is sent by itself. It only
   turns speech into text inside the box, the owner reads it and presses Send.

   Two engines, picked per press:
   - Web Speech (Chrome, Edge, Safari): live text while speaking. When the server has an upload ear (GET
     /voice/ear says kind "upload", Groq Whisper), the same audio is also recorded and sent to POST /stt on stop;
     its text replaces the browser's draft, the same rule the main chat uses (Vietnamese reads much better).
   - No Web Speech (Firefox): record only, POST /stt on stop. No upload ear either: report "unsupported".

   0.230.0: the main chat composer uses it too (composer-dictate.js), with cancel() and a level meter (onStream),
   and a run the browser ends on its own restarts until the owner presses stop.

   0.339.0: a PHONE lets only ONE thing capture the mic (the rule voice.js learned in 0.59.35, see _nhaMicStream).
   Opening the recorder (or the level meter) next to Web Speech left both deaf on an iPhone: the timer ran, the meter
   stayed flat and no word ever arrived (owner report 2026-10-26). On a phone a press now uses one engine only:
   with an upload ear, record only (the text arrives on stop, the meter works); without one, Web Speech only (no
   meter, no recorder). iOS also gets non-continuous runs, the restart loop strings them together.

   0.409.0: stop and X always close the bar (owner report 2026-10-30, iPhone: the timer ran on and neither button did
   anything). A browser that never answers rec.stop() with onend, a MediaRecorder that never fires onstop, or a /stt
   call that hangs used to leave the run waiting forever with nothing left to press: stop only worked while `on`, and
   X during "transcribing" waited for the upload. Each wait now has a watchdog, a second stop forces the end, and X
   closes the bar at once.

   0.419.0: the mic opens INSIDE the tap on an iPhone (owner report 2026-10-30, iPhone 15 Pro Max: press the mic, the
   bar flashes and closes). Safari only lets a page start the mic or its speech recognizer during the brief moment that
   follows a tap. start() first asked GET /voice/ear and only then opened the mic; the answer is cached for a minute, so
   nearly every real press went to the network first (through Cloudflare, and since 0.416 through fetch-gop.js and the
   service worker), and by the time it came back the tap no longer counted: Safari refused, the run reported "denied"
   or "failed" and the bar closed. The ear is now asked in the background (on load, when the tab comes back, after each
   press), and a press opens the mic synchronously: with the known answer, whatever its age, and with "no ear" when there
   is none yet (owner, same day: ordinary users never set up Groq, so the browser's own recognizer is the path that must
   always work; a Groq user only loses the re-listen on a press made before the first answer came). A failed refresh
   keeps the last known answer. A recognizer the phone itself has switched off (iOS "service-not-allowed": Dictation
   off in Settings) is reported as "service", not as a blocked mic, so the note can say where to turn it on.

   joinText is pure so node tests can run it. */
(function () {
  "use strict";

  // The words go after what was already typed, separated by one space (none when the box was empty or already ends
  // in whitespace).
  function joinText(base, spoken) {
    base = String(base == null ? "" : base);
    spoken = String(spoken == null ? "" : spoken).trim();
    if (!spoken) return base;
    if (!base) return spoken;
    return base + (/\s$/.test(base) ? "" : " ") + spoken;
  }

  function langTag() {
    try {
      var l = (document.documentElement.getAttribute("lang") || "").toLowerCase();
      if (l.indexOf("en") === 0) return "en-US";
    } catch (e) { /* node */ }
    return "vi-VN";
  }

  // Restarts of a run the browser ended by itself. iOS ends a run after every utterance, so the cap is generous; the
  // composer stops the whole recording after five minutes anyway.
  var MAX_RESTARTS = 200;

  // How long a run waits for the browser before it ends by itself (0.409.0): onend after rec.stop(), onstop after
  // MediaRecorder.stop(), and the answer of POST /stt.
  var END_WAIT_MS = 1500;
  var STT_WAIT_MS = 45000;

  var earKind = null;   // cached answer of GET /voice/ear: "upload", "" (none) or null (not asked yet)
  var earAt = 0;        // asked again after a minute, so a key added on the Models page counts without a reload
  function askEar() {
    var fresh = earKind !== null && Date.now() - earAt < 60000;
    if (fresh || typeof fetch !== "function") return Promise.resolve(earKind || "");
    return fetch("/voice/ear", { credentials: "same-origin" }).then(function (r) { return r.json(); })
      .then(function (j) { earKind = j && j.kind === "upload" ? "upload" : ""; earAt = Date.now(); return earKind; },
        // A network hiccup is not "the server has no ear": keep what we knew (0.419.0).
        function () { if (earKind === null) earKind = ""; earAt = Date.now(); return earKind; });
  }

  // Ask in the background so a press finds the answer already there and can open the mic inside the tap (0.419.0).
  function warmEar() { try { askEar(); } catch (e) { /* the next press asks again */ } }
  if (typeof document !== "undefined" && typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("load", function () { setTimeout(warmEar, 1500); });
    document.addEventListener("visibilitychange", function () { if (!document.hidden) warmEar(); });
  }

  function recognizer() {
    return (typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition)) || null;
  }

  // iPhone, iPad (iPadOS reports itself as a Mac with touch) or Android. `nav` is injectable for node tests.
  function isIOS(nav) {
    nav = nav || (typeof navigator !== "undefined" ? navigator : {});
    var ua = String(nav.userAgent || "");
    return /iP(hone|ad|od)/.test(ua) || (nav.platform === "MacIntel" && (nav.maxTouchPoints || 0) > 1);
  }
  function isPhone(nav) {
    nav = nav || (typeof navigator !== "undefined" ? navigator : {});
    return isIOS(nav) || /Android/i.test(String(nav.userAgent || ""));
  }

  // Which engines one press runs: { speech, record, meter }. A computer runs Web Speech and the recorder side by
  // side; a phone runs exactly one capture (see the 0.339.0 note at the top). Pure, for node tests.
  function plan(o) {
    var canRecord = !!(o.ear === "upload" && o.mediaRecorder);
    if (!o.phone) return { speech: !!o.speech, record: canRecord, meter: !!o.wantMeter };
    if (canRecord) return { speech: false, record: true, meter: !!o.wantMeter };
    return { speech: !!o.speech, record: false, meter: false };
  }

  // opts: onText(text, final) gets the WHOLE spoken text so far; onState("listening" | "transcribing" | "idle");
  // onError(code) with "unsupported", "denied", "service" (0.419.0: the device's speech service is off), "failed" or "nothing" (0.339.0: the run ended with no word at all,
  // reported only when no other error was); onStream(stream | null) when given also opens the mic for a level meter
  // even without an upload ear (0.230.0). Returns { start, stop, cancel, active, busy }.
  function create(opts) {
    opts = opts || {};
    var rec = null, media = null, stream = null, chunks = [], on = false, spoken = "", cancelled = false;
    var finishing = false;
    var state = function (s) { if (opts.onState) opts.onState(s); };
    var reported = false;   // an error was already shown for this press: "nothing" would only hide it
    var err = function (c) {
      if (c === "nothing" && reported) return;
      reported = true;
      if (opts.onError) opts.onError(c);
    };

    function stopStream() {
      if (stream) {
        try { stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
        if (opts.onStream) opts.onStream(null);
      }
      stream = null;
    }

    function upload(blob) {
      if (!blob || blob.size < 2000 || cancelled) return Promise.resolve("");
      var fd = new FormData();
      var ext = /mp4/.test(blob.type) ? "m4a" : /ogg/.test(blob.type) ? "ogg" : "webm";
      fd.append("file", blob, "voice." + ext);
      fd.append("lang", "auto");
      fd.append("draft", spoken);
      var ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
      var t = ctl ? setTimeout(function () { try { ctl.abort(); } catch (e) {} }, STT_WAIT_MS) : 0;
      return fetch("/stt", { method: "POST", body: fd, credentials: "same-origin", signal: ctl ? ctl.signal : undefined })
        .then(function (r) { return r.json(); })
        .then(function (d) { clearTimeout(t); return d && d.ok ? String(d.text || "").trim() : ""; },
          function () { clearTimeout(t); return ""; });
    }

    // Opens the mic when something needs it: the recorder (upload ear) or the caller's level meter.
    function openMic(record, noMeter) {
      if (typeof navigator === "undefined" || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        return Promise.resolve(false);
      }
      if (record && typeof MediaRecorder === "undefined") record = false;
      var meter = !!opts.onStream && !noMeter;
      if (!record && !meter) return Promise.resolve(false);
      return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
        stream = s; chunks = [];
        if (meter) opts.onStream(s);
        if (record) {
          media = new MediaRecorder(s);
          media.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
          media.start();
        }
        return true;
      }, function () { if (record) err("denied"); return false; });
    }

    function stopRecorder() {
      return new Promise(function (resolve) {
        if (!media || media.state === "inactive") { media = null; stopStream(); resolve(null); return; }
        var m = media, done = false;
        var end = function () {
          if (done) return;
          done = true;
          stopStream();
          resolve(chunks.length ? new Blob(chunks, { type: m.mimeType || "audio/webm" }) : null);
          media = null;
        };
        m.onstop = end;
        // Some phones never fire onstop: keep what was recorded so far instead of waiting forever.
        setTimeout(end, END_WAIT_MS);
        try { m.stop(); } catch (e) { end(); }
      });
    }

    function finish() {
      if (finishing) return;
      var hadRecorder = !!media;
      on = false;
      if (cancelled || !hadRecorder) {
        stopRecorder();
        // Nothing was heard and nothing can listen again: say so instead of closing the bar in silence.
        if (!cancelled && !spoken) err("nothing");
        state("idle");
        return;
      }
      finishing = true;
      state("transcribing");
      stopRecorder().then(upload).then(function (text) {
        finishing = false;
        if (cancelled) return;   // cancel() already reported idle
        if (text) opts.onText && opts.onText(text, true);
        else if (!spoken) err("nothing");
        state("idle");
      });
    }

    // One recognizer run. Browsers end a continuous run on their own (silence, about a minute on Chrome, sooner on
    // Safari); while the owner has not pressed stop, a new run starts and keeps the words heard so far.
    function runRecognizer(SR, kept, restarts) {
      var r = new SR();
      rec = r;
      r.lang = langTag();
      // iOS cannot run a continuous session: it turns into an endless "recording" that never yields text (voice.js
      // learned this in 0.59.x). One utterance per run there; onend below starts the next one.
      r.continuous = !isIOS();
      r.interimResults = true;
      var done = kept, fatal = false;
      r.onresult = function (e) {
        if (cancelled || rec !== r) return;
        var interim = "";
        for (var i = e.resultIndex; i < e.results.length; i++) {
          var t = e.results[i][0].transcript;
          if (e.results[i].isFinal) done = joinText(done, t); else interim = joinText(interim, t);
        }
        spoken = joinText(done, interim);
        if (opts.onText) opts.onText(spoken, false);
      };
      r.onerror = function (e) {
        if (e && e.error === "service-not-allowed") { fatal = true; err("service"); }
        else if (e && e.error === "not-allowed") { fatal = true; err("denied"); }
        else if (e && e.error !== "no-speech" && e.error !== "aborted") { fatal = true; err("failed"); }
      };
      r.onend = function () {
        if (rec !== r) return;
        rec = null;
        if (on && !cancelled && !fatal && restarts < MAX_RESTARTS) {
          try { runRecognizer(SR, spoken, restarts + 1); return; } catch (x) { rec = null; }
        }
        finish();
      };
      r.start();
    }

    function start() {
      if (on || finishing) return;
      on = true; spoken = ""; cancelled = false; reported = false;
      var SR = recognizer();
      // A known answer, however old, is used NOW so the mic opens inside the tap; the refresh only serves the next
      // press (0.419.0, see the note at the top). No answer yet counts as "no ear": the browser's recognizer.
      go(earKind || "");
      warmEar();

      function go(ear) {
        if (!on) return;
        var p = plan({ phone: isPhone(), ear: ear, speech: !!SR, wantMeter: !!opts.onStream,
          mediaRecorder: typeof MediaRecorder !== "undefined" });
        if (!p.speech && !p.record) { on = false; err("unsupported"); state("idle"); return; }
        // Web Speech alone (a phone without an ear): start it right here, still inside the tap, not a promise later.
        if (!p.record && !p.meter) {
          try { runRecognizer(SR, "", 0); state("listening"); }
          catch (x) { rec = null; on = false; err("failed"); state("idle"); }
          return;
        }
        var micUp = openMic(p.record, !p.meter);
        micUp.then(function () {
          if (!on) { stopRecorder(); return; }
          if (!p.speech) {
            if (!media) { on = false; stopRecorder(); state("idle"); return; }
            state("listening"); return;
          }
          try { runRecognizer(SR, "", 0); state("listening"); }
          catch (x) { rec = null; on = false; stopRecorder(); err("failed"); state("idle"); }
        });
      }
    }

    // A second press while the browser still owes onend forces the end (0.409.0).
    function stop() {
      if (!on) {
        if (rec && !finishing) { var r0 = rec; rec = null; r0.onend = null; try { r0.abort(); } catch (e) {} finish(); }
        return;
      }
      on = false;
      if (!rec) { finish(); return; }
      var r = rec;
      try { r.stop(); } catch (e) { rec = null; finish(); return; }
      // iOS sometimes never answers stop() with onend: end the run ourselves, keeping the words heard so far.
      setTimeout(function () {
        if (rec !== r) return;
        rec = null; r.onend = null;
        try { r.abort(); } catch (e) {}
        finish();
      }, END_WAIT_MS);
    }

    // Drops everything: nothing more reaches onText, the recording is not uploaded.
    function cancel() {
      if (!on && !finishing && !rec) return;   // a stopped run still waiting for its last result counts
      cancelled = true;
      on = false;
      // The pending upload sees `cancelled` and drops its text; the bar closes now instead of waiting for it.
      if (finishing) { state("idle"); return; }
      var r = rec;
      rec = null;
      if (r) { r.onend = null; try { r.abort(); } catch (e) {} }
      finish();
    }

    return { start: start, stop: stop, cancel: cancel, active: function () { return on; },
      busy: function () { return finishing; } };
  }

  // The ear the last press found: "upload" (Groq or OpenAI listens again on stop), "" (browser text only) or null.
  var api = { create: create, joinText: joinText, plan: plan, isPhone: isPhone, isIOS: isIOS,
    ear: function () { return earKind; }, warm: askEar };
  if (typeof window !== "undefined") window.JavisDictate = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
