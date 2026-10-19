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

  var earKind = null;   // cached answer of GET /voice/ear: "upload", "" (none) or null (not asked yet)
  var earAt = 0;        // asked again after a minute, so a key added on the Models page counts without a reload
  function askEar() {
    var fresh = earKind !== null && Date.now() - earAt < 60000;
    if (fresh || typeof fetch !== "function") return Promise.resolve(earKind || "");
    return fetch("/voice/ear", { credentials: "same-origin" }).then(function (r) { return r.json(); })
      .then(function (j) { earKind = j && j.kind === "upload" ? "upload" : ""; earAt = Date.now(); return earKind; },
        function () { earKind = ""; earAt = Date.now(); return ""; });
  }

  function recognizer() {
    return (typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition)) || null;
  }

  // opts: onText(text, final) gets the WHOLE spoken text so far; onState("listening" | "transcribing" | "idle");
  // onError(code) with "unsupported", "denied" or "failed"; onStream(stream | null) when given also opens the mic
  // for a level meter even without an upload ear (0.230.0). Returns { start, stop, cancel, active, busy }.
  function create(opts) {
    opts = opts || {};
    var rec = null, media = null, stream = null, chunks = [], on = false, spoken = "", cancelled = false;
    var finishing = false;
    var state = function (s) { if (opts.onState) opts.onState(s); };
    var err = function (c) { if (opts.onError) opts.onError(c); };

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
      return fetch("/stt", { method: "POST", body: fd, credentials: "same-origin" }).then(function (r) { return r.json(); })
        .then(function (d) { return d && d.ok ? String(d.text || "").trim() : ""; }, function () { return ""; });
    }

    // Opens the mic when something needs it: the recorder (upload ear) or the caller's level meter.
    function openMic(record) {
      if (typeof navigator === "undefined" || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        return Promise.resolve(false);
      }
      if (record && typeof MediaRecorder === "undefined") record = false;
      if (!record && !opts.onStream) return Promise.resolve(false);
      return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
        stream = s; chunks = [];
        if (opts.onStream) opts.onStream(s);
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
        var m = media;
        m.onstop = function () {
          stopStream();
          resolve(chunks.length ? new Blob(chunks, { type: m.mimeType || "audio/webm" }) : null);
          media = null;
        };
        try { m.stop(); } catch (e) { media = null; stopStream(); resolve(null); }
      });
    }

    function finish() {
      if (finishing) return;
      var hadRecorder = !!media;
      on = false;
      if (cancelled || !hadRecorder) { stopRecorder(); state("idle"); return; }
      finishing = true;
      state("transcribing");
      stopRecorder().then(upload).then(function (text) {
        finishing = false;
        if (cancelled) { state("idle"); return; }
        if (text) opts.onText && opts.onText(text, true);
        else if (!spoken && !recognizer()) err("unsupported");
        state("idle");
      });
    }

    // One recognizer run. Browsers end a continuous run on their own (silence, about a minute on Chrome, sooner on
    // Safari); while the owner has not pressed stop, a new run starts and keeps the words heard so far.
    function runRecognizer(SR, kept, restarts) {
      var r = new SR();
      rec = r;
      r.lang = langTag();
      r.continuous = true;
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
        if (e && (e.error === "not-allowed" || e.error === "service-not-allowed")) { fatal = true; err("denied"); }
        else if (e && e.error !== "no-speech" && e.error !== "aborted") { fatal = true; err("failed"); }
      };
      r.onend = function () {
        if (rec !== r) return;
        rec = null;
        if (on && !cancelled && !fatal && restarts < 30) {
          try { runRecognizer(SR, spoken, restarts + 1); return; } catch (x) { rec = null; }
        }
        finish();
      };
      r.start();
    }

    function start() {
      if (on || finishing) return;
      on = true; spoken = ""; cancelled = false;
      var SR = recognizer();
      askEar().then(function (ear) {
        if (!on) return;
        if (!SR && ear !== "upload") { on = false; err("unsupported"); state("idle"); return; }
        openMic(ear === "upload").then(function () {
          if (!on) { stopRecorder(); return; }
          if (!SR) {
            if (!media) { on = false; stopRecorder(); state("idle"); return; }
            state("listening"); return;
          }
          try { runRecognizer(SR, "", 0); state("listening"); }
          catch (x) { rec = null; on = false; stopRecorder(); err("failed"); state("idle"); }
        });
      });
    }

    function stop() {
      if (!on) return;
      on = false;
      if (rec) { try { rec.stop(); } catch (e) { rec = null; finish(); } return; }
      finish();
    }

    // Drops everything: nothing more reaches onText, the recording is not uploaded.
    function cancel() {
      if (!on && !finishing && !rec) return;   // a stopped run still waiting for its last result counts
      cancelled = true;
      on = false;
      if (finishing) return;   // the pending upload sees `cancelled` and reports idle itself
      var r = rec;
      rec = null;
      if (r) { r.onend = null; try { r.abort(); } catch (e) {} }
      finish();
    }

    return { start: start, stop: stop, cancel: cancel, active: function () { return on; },
      busy: function () { return finishing; } };
  }

  // The ear the last press found: "upload" (Groq or OpenAI listens again on stop), "" (browser text only) or null.
  var api = { create: create, joinText: joinText, ear: function () { return earKind; } };
  if (typeof window !== "undefined") window.JavisDictate = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
