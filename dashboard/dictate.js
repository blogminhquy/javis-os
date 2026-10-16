/* dictate.js - the mic button of a text composer: speak, the words land in the input (0.176.0).

   Team chat has no voice call, yet the owner still wants to talk instead of type (2026-10-16). This is NOT the
   voice call of the main chat (voice.js): no turn taking, no reading aloud, nothing is sent by itself. It only
   turns speech into text inside the box, the owner reads it and presses Send.

   Two engines, picked per press:
   - Web Speech (Chrome, Edge, Safari): live text while speaking. When the server has an upload ear (GET
     /voice/ear says kind "upload", Groq Whisper), the same audio is also recorded and sent to POST /stt on stop;
     its text replaces the browser's draft, the same rule the main chat uses (Vietnamese reads much better).
   - No Web Speech (Firefox): record only, POST /stt on stop. No upload ear either: report "unsupported".

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
  function askEar() {
    if (earKind !== null || typeof fetch !== "function") return Promise.resolve(earKind || "");
    return fetch("/voice/ear", { credentials: "same-origin" }).then(function (r) { return r.json(); })
      .then(function (j) { earKind = j && j.kind === "upload" ? "upload" : ""; return earKind; },
        function () { earKind = ""; return ""; });
  }

  function recognizer() {
    return (typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition)) || null;
  }

  // opts: onText(text, final) gets the WHOLE spoken text so far; onState("listening" | "transcribing" | "idle");
  // onError(code) with "unsupported", "denied" or "failed". Returns { start, stop, active }.
  function create(opts) {
    opts = opts || {};
    var rec = null, media = null, stream = null, chunks = [], on = false, spoken = "";
    var state = function (s) { if (opts.onState) opts.onState(s); };
    var err = function (c) { if (opts.onError) opts.onError(c); };

    function stopStream() {
      if (stream) { try { stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {} }
      stream = null;
    }

    function upload(blob) {
      if (!blob || blob.size < 2000) return Promise.resolve("");
      var fd = new FormData();
      var ext = /mp4/.test(blob.type) ? "m4a" : /ogg/.test(blob.type) ? "ogg" : "webm";
      fd.append("file", blob, "voice." + ext);
      fd.append("lang", "auto");
      fd.append("draft", spoken);
      return fetch("/stt", { method: "POST", body: fd, credentials: "same-origin" }).then(function (r) { return r.json(); })
        .then(function (d) { return d && d.ok ? String(d.text || "").trim() : ""; }, function () { return ""; });
    }

    function startRecorder() {
      if (typeof navigator === "undefined" || !navigator.mediaDevices || typeof MediaRecorder === "undefined") {
        return Promise.resolve(false);
      }
      return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
        stream = s; chunks = [];
        media = new MediaRecorder(s);
        media.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
        media.start();
        return true;
      }, function () { err("denied"); return false; });
    }

    function stopRecorder() {
      return new Promise(function (resolve) {
        if (!media || media.state === "inactive") { stopStream(); resolve(null); return; }
        media.onstop = function () {
          stopStream();
          resolve(chunks.length ? new Blob(chunks, { type: media.mimeType || "audio/webm" }) : null);
          media = null;
        };
        try { media.stop(); } catch (e) { stopStream(); resolve(null); }
      });
    }

    var finishing = false;
    function finish() {
      if (finishing) return;
      var hadRecorder = !!media;
      on = false;
      if (!hadRecorder) { state("idle"); return; }
      finishing = true;
      state("transcribing");
      stopRecorder().then(upload).then(function (text) {
        if (text) opts.onText && opts.onText(text, true);
        else if (!spoken && !recognizer()) err("unsupported");
        finishing = false;
        state("idle");
      });
    }

    function start() {
      if (on) return;
      on = true; spoken = "";
      var SR = recognizer();
      askEar().then(function (ear) {
        if (!on) return;
        if (!SR && ear !== "upload") { on = false; err("unsupported"); state("idle"); return; }
        var rp = ear === "upload" ? startRecorder() : Promise.resolve(false);
        rp.then(function () {
          if (!on) { stopRecorder(); return; }
          if (!SR) { state("listening"); return; }
          rec = new SR();
          rec.lang = langTag();
          rec.continuous = true;
          rec.interimResults = true;
          var done = "";
          rec.onresult = function (e) {
            var interim = "";
            for (var i = e.resultIndex; i < e.results.length; i++) {
              var t = e.results[i][0].transcript;
              if (e.results[i].isFinal) done = joinText(done, t); else interim = joinText(interim, t);
            }
            spoken = joinText(done, interim);
            if (opts.onText) opts.onText(spoken, false);
          };
          rec.onerror = function (e) {
            if (e && (e.error === "not-allowed" || e.error === "service-not-allowed")) err("denied");
            else if (e && e.error !== "no-speech" && e.error !== "aborted") err("failed");
          };
          rec.onend = function () { rec = null; finish(); };
          try { rec.start(); state("listening"); } catch (x) { rec = null; on = false; stopRecorder(); err("failed"); state("idle"); }
        });
      });
    }

    function stop() {
      if (!on) return;
      on = false;
      if (rec) { try { rec.stop(); } catch (e) { rec = null; finish(); } return; }
      finish();
    }

    return { start: start, stop: stop, active: function () { return on; } };
  }

  var api = { create: create, joinText: joinText };
  if (typeof window !== "undefined") window.JavisDictate = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
