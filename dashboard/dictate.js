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

   2026-11-05: no more "tôi tôi bị tôi bị học" on Android. Chrome on Android, on some phones and
   Google app versions (hence "only now and then"), hands every new result back as the WHOLE sentence so far: "tôi",
   "tôi bị", "tôi bị học", several of them marked final, sometimes the same one twice. Appending each piece filled the
   box with every draft of the sentence. On Android a piece that grows, repeats or trims the one before it now replaces
   that one (addPiece). A computer and an iPhone never send results like that, so they keep plain appending.

   2026-11-06: the run's text is REBUILT from the whole result list on every event (buildRun), not added up event by
   event. The list is the browser's own state of the run: a result that grows is the same entry updated, so reading
   the list again shows it once. The 2026-11-05 rule above also dropped a short piece that arrived after a longer one
   ("tôi về rồi" then "tôi" lost the second "tôi"); that rule is gone. Android keeps two narrow rules, between
   NEIGHBOUR entries of the list only, as voice.js learned on real phones: the same entry sent twice is kept once,
   and an entry that is the one before it grown ("tôi", "tôi bị") takes its place. Known limit: a new sentence that
   starts with the whole sentence right before it ("có", then "có lẽ tôi đi") is read as the same sentence grown.
   Computers and iPhones never send such neighbours, so they keep every entry.

   2026-11-06 (later the same day): the faded bubble is gone and every recording ends with a REWRITE (owner: "nói xong
   ấn Enter hoặc ấn tắt thì nó tự dùng mô hình viết lại thành câu đúng ngữ cảnh, không phải câu nghe được", and "đừng
   chỉ sửa vài từ, hãy sửa cả cấu trúc"). On a computer the words show right in the text box while speaking, as before
   0.481.9. When the recording ends (stop, Enter, Send, the 5-minute limit) the whole sentence goes to POST /stt/fix
   with `final` and a few recent messages of the chat as context: a model rewrites it into what the owner meant, any
   language, any mishearing, not a word list (server/transcript_fix.py). The run stays in "transcribing" while that
   happens, so a Send pressed during the recording sends the rewritten sentence. A phone keeps the words for the end,
   as the owner asked on 2026-11-05. Any failure or a slow answer keeps the words as heard: never lose a sentence.

   2026-11-08: a recording keeps going in the background (owner: "khi đang chép lời mà ấn Alt Tab sang một trang
   khác thì nó sẽ bị dừng lại", and wants it to run on in whatever tab or app is in front, computer or phone). The
   composer used to stop the recording the moment the tab was hidden; that is gone (composer-dictate.js). What the
   browser itself does in the background is handled here:
   - A recognizer run that ends or errors while the page is hidden is PARKED, not counted as a failure: no error note,
     no tight restart loop. A normal end in the background (a computer's browser keeps listening there) still restarts
     as before. When the page is visible again a parked run starts again, keeping every word heard so far.
   - A phone cuts the mic when its browser goes to the background, and the recorder may stop by itself. Its audio is
     kept as a segment (it used to be thrown away when the recorder was already inactive on stop), the mic reopens
     when the page comes back, and on stop every segment is sent to POST /stt and the texts are joined.
   A phone's browser cannot hear while another app is in front: that is the system's rule, not ours. The recording
   simply picks up again when the owner comes back, without pressing anything.

   joinText and buildRun are pure so node tests can run them. */
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

  // Words only, for comparing two pieces: case, punctuation and spacing differ between drafts of the same sentence.
  function wordsOf(s) {
    return String(s == null ? "" : s).toLowerCase().replace(/[.,!?;:\u2026"\u201c\u201d]/g, " ").replace(/\s+/g, " ").trim();
  }

  // The run's text from its whole result list (2026-11-06, see the note at the top). `results` is list-like:
  // results[i][0].transcript and results[i].isFinal, as SpeechRecognitionResultList gives them. With `android`, a
  // neighbour that repeats the entry before it is skipped, and one that grows it replaces it.
  function buildRun(results, android) {
    var out = [];
    var n = results && results.length ? results.length : 0;
    for (var i = 0; i < n; i++) {
      var r = results[i];
      var t = String((r && r[0] && r[0].transcript) || "").trim();
      if (!t) continue;
      if (android && out.length) {
        var prev = wordsOf(out[out.length - 1]), cur = wordsOf(t);
        if (cur === prev) continue;
        if (prev && cur.indexOf(prev + " ") === 0) { out[out.length - 1] = t; continue; }
      }
      out.push(t);
    }
    return out.reduce(joinText, "");
  }

  // Set localStorage "javis.debug.dictate" to "1" to print each result list in the console: the shape real phones
  // send is what decides the rules above.
  function debugOn() {
    try { return typeof localStorage !== "undefined" && localStorage.getItem("javis.debug.dictate") === "1"; }
    catch (e) { return false; }
  }

  function langTag() {
    try {
      var l = (document.documentElement.getAttribute("lang") || "").toLowerCase();
      if (l.indexOf("en") === 0) return "en-US";
    } catch (e) { /* node */ }
    return "vi-VN";
  }

  function pageHidden() {
    try { return typeof document !== "undefined" && !!document.hidden; } catch (e) { return false; }
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
  function isAndroid(nav) {
    nav = nav || (typeof navigator !== "undefined" ? navigator : {});
    return /Android/i.test(String(nav.userAgent || ""));
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
  // session() (optional) the id of the chat the words go to, sent with the recording so the server hears with the ear
  // of the model that chat runs on;
  // onError(code) with "unsupported", "denied", "service" (0.419.0: the device's speech service is off), "failed" or "nothing" (0.339.0: the run ended with no word at all,
  // reported only when no other error was); onStream(stream | null) when given also opens the mic for a level meter
  // even without an upload ear (0.230.0). Returns { start, stop, cancel, active, busy }.
  function create(opts) {
    opts = opts || {};
    var rec = null, media = null, stream = null, chunks = [], on = false, spoken = "", cancelled = false;
    var finishing = false;
    // Background (2026-11-08): recorder audio cut off by the phone, a recognizer run parked until the page is visible.
    var segments = [], parked = false, SRnow = null, planNow = null, mime = "audio/webm";
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

    // Every recorded segment in order, each heard on its own, the texts joined (2026-11-08).
    function uploadAll(blobs) {
      var out = "";
      return (blobs || []).reduce(function (p, b) {
        return p.then(function () { return upload(b); }).then(function (t) { out = joinText(out, t); });
      }, Promise.resolve()).then(function () { return out; });
    }

    function upload(blob) {
      if (!blob || blob.size < 2000 || cancelled) return Promise.resolve("");
      var fd = new FormData();
      var ext = /mp4/.test(blob.type) ? "m4a" : /ogg/.test(blob.type) ? "ogg" : "webm";
      fd.append("file", blob, "voice." + ext);
      fd.append("lang", "auto");
      fd.append("draft", spoken);
      // The chat being dictated into (2026-11-08): a partner's chat hears with the ear of that partner's own model.
      var sid = "";
      try { sid = typeof opts.session === "function" ? String(opts.session() || "") : ""; } catch (e) { sid = ""; }
      if (sid) fd.append("session", sid);
      var ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
      var t = ctl ? setTimeout(function () { try { ctl.abort(); } catch (e) {} }, STT_WAIT_MS) : 0;
      return fetch("/stt", { method: "POST", body: fd, credentials: "same-origin", signal: ctl ? ctl.signal : undefined })
        .then(function (r) { return r.json(); })
        .then(function (d) { clearTimeout(t); return d && d.ok ? String(d.text || "").trim() : ""; },
          function () { clearTimeout(t); return ""; });
    }

    // Opens the mic when something needs it: the recorder (upload ear) or the caller's level meter.
    function openMic(record, noMeter, quiet) {
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
          mime = media.mimeType || mime;
          media.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
          media.start();
        }
        return true;
      }, function () { if (record && !quiet) err("denied"); return false; });
    }

    // What the current recorder holds becomes one finished segment.
    function bank(m) {
      if (chunks.length) segments.push(new Blob(chunks, { type: (m && m.mimeType) || mime }));
      chunks = [];
    }

    // Resolves to every segment recorded in this run (2026-11-08: a recorder the phone already stopped in the
    // background still hands over its audio instead of losing it).
    function stopRecorder() {
      return new Promise(function (resolve) {
        var all = function () { var s = segments; segments = []; return s; };
        if (!media || media.state === "inactive") { bank(media); media = null; stopStream(); resolve(all()); return; }
        var m = media, done = false;
        var end = function () {
          if (done) return;
          done = true;
          stopStream();
          bank(m);
          resolve(all());
          media = null;
        };
        m.onstop = end;
        // Some phones never fire onstop: keep what was recorded so far instead of waiting forever.
        setTimeout(end, END_WAIT_MS);
        try { m.stop(); } catch (e) { end(); }
      });
    }

    // The last step of every recording (2026-11-06): the model rewrites the sentence with the chat as context.
    function polish(text) {
      if (!text || opts.polish === false) return Promise.resolve(text);
      var ctx = [];
      try { ctx = typeof opts.context === "function" ? (opts.context() || []) : []; } catch (e) { ctx = []; }
      return polishText(text, ctx);
    }

    function finish() {
      if (finishing) return;
      parked = false;
      if (typeof document !== "undefined" && document.removeEventListener) {
        document.removeEventListener("visibilitychange", onVisible);
      }
      var hadRecorder = !!media || segments.length > 0 || chunks.length > 0;
      on = false;
      if (cancelled || (!hadRecorder && !spoken)) {
        stopRecorder();
        // Nothing was heard and nothing can listen again: say so instead of closing the bar in silence.
        if (!cancelled && !spoken) err("nothing");
        state("idle");
        return;
      }
      finishing = true;
      state("transcribing");
      var heard = hadRecorder ? stopRecorder().then(uploadAll) : Promise.resolve("");
      heard.then(function (text) {
        if (cancelled) return "";
        // The ear's text when there is one, else what the browser heard.
        text = text || spoken;
        if (!text) return "";
        return polish(text);
      }).then(function (text) {
        finishing = false;
        if (cancelled) return;   // cancel() already reported idle
        if (text) opts.onText && opts.onText(text, true);
        else err("nothing");
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
      var fatal = false, android = isAndroid(), startedAt = Date.now(), interrupted = false;
      r.onresult = function (e) {
        if (cancelled || rec !== r) return;
        if (debugOn()) {
          try {
            var shape = [];
            for (var k = 0; k < e.results.length; k++) shape.push([e.results[k][0].transcript, !!e.results[k].isFinal]);
            console.debug("[dictate] resultIndex=" + e.resultIndex, JSON.stringify(shape));
          } catch (x) {}
        }
        // The whole list, every time: words kept from earlier runs, then this run's text.
        spoken = joinText(kept, buildRun(e.results, android));
        if (opts.onText) opts.onText(spoken, false);
      };
      r.onerror = function (e) {
        // The page is in the background: the browser cut the run, the owner did nothing wrong (2026-11-08).
        if (pageHidden() && !(e && e.error === "service-not-allowed")) { interrupted = true; return; }
        if (e && e.error === "service-not-allowed") { fatal = true; err("service"); }
        else if (e && e.error === "not-allowed") { fatal = true; err("denied"); }
        else if (e && e.error !== "no-speech" && e.error !== "aborted") { fatal = true; err("failed"); }
      };
      r.onend = function () {
        if (rec !== r) return;
        rec = null;
        if (on && !cancelled && !fatal) {
          // Cut off in the background, or ended at once: wait for the page to come back instead of looping.
          if (pageHidden() && (interrupted || Date.now() - startedAt < 1000)) { parked = true; return; }
          if (restarts < MAX_RESTARTS) {
            try { runRecognizer(SR, spoken, restarts + 1); return; }
            catch (x) { rec = null; if (pageHidden()) { parked = true; return; } }
          }
        }
        finish();
      };
      r.start();
    }

    function start() {
      if (on || finishing) return;
      on = true; spoken = ""; cancelled = false; reported = false;
      segments = []; parked = false; planNow = null;
      var SR = recognizer();
      SRnow = SR;
      if (typeof document !== "undefined" && document.addEventListener) {
        document.removeEventListener("visibilitychange", onVisible);
        document.addEventListener("visibilitychange", onVisible);
      }
      // A known answer, however old, is used NOW so the mic opens inside the tap; the refresh only serves the next
      // press (0.419.0, see the note at the top). No answer yet counts as "no ear": the browser's recognizer.
      go(earKind || "");
      warmEar();

      function go(ear) {
        if (!on) return;
        var p = plan({ phone: isPhone(), ear: ear, speech: !!SR, wantMeter: !!opts.onStream,
          mediaRecorder: typeof MediaRecorder !== "undefined" });
        planNow = p;
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

    function streamLive() {
      try {
        return !!stream && stream.getTracks().some(function (t) { return t.readyState !== "ended"; });
      } catch (e) { return false; }
    }

    // The phone stopped the recorder or cut the mic while the page was away: keep that audio as a segment and record
    // on in a new one (2026-11-08).
    function resumeRecorder() {
      if (!planNow || !planNow.record || finishing) return;
      if (media && media.state !== "inactive" && streamLive()) return;
      var old = media;
      media = null;
      // A recorder still running on a dead mic hands over its last piece of audio before it is banked.
      new Promise(function (done) {
        if (!old || old.state === "inactive") { done(); return; }
        old.onstop = done;
        setTimeout(done, END_WAIT_MS);
        try { old.stop(); } catch (e) { done(); }
      }).then(function () {
        bank(old);
        if (!on || cancelled || finishing) return;
        stopStream();
        return openMic(true, !planNow.meter, true).then(function () { if (!on || cancelled) stopRecorder(); });
      });
    }

    // Back from the background: pick up where the browser left off, no press needed.
    function onVisible() {
      if (pageHidden() || !on || cancelled || finishing) return;
      resumeRecorder();
      if (parked && SRnow && !rec) {
        parked = false;
        try { runRecognizer(SRnow, spoken, 0); } catch (x) { rec = null; on = false; finish(); }
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

  // A phone, not a tablet: iPhone, iPod or an Android phone. Only computers and tablets show the words in the box while
  // speaking; a phone keeps them for the end (owner, 2026-11-05).
  function isPhoneUA(nav) {
    nav = nav || (typeof navigator !== "undefined" ? navigator : {});
    return /iPhone|iPod|Android.*Mobile/i.test(String(nav.userAgent || ""));
  }

  // How long the rewrite may take before the words go in as heard. A subscription brain (Claude Code, Codex) starts a
  // CLI for it, which takes a few seconds; an API key answers in about one.
  var POLISH_WAIT_MS = 25000;

  // The whole recording rewritten by the server (POST /stt/fix with `final`, server/transcript_fix.py): what the owner
  // meant, in context, not just a word list. `context` is a few recent messages of the chat. Any failure, odd answer or
  // no answer in time gives the words back unchanged. Shared by every chat screen's mic.
  function polishText(text, context, waitMs) {
    var raw = String(text == null ? "" : text);
    if (!raw.trim() || typeof fetch !== "function") return Promise.resolve(raw);
    var ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = 0, gaveUp = false;
    var late = new Promise(function (resolve) {
      timer = setTimeout(function () { gaveUp = true; try { if (ctl) ctl.abort(); } catch (e) {} resolve(raw); },
        waitMs || POLISH_WAIT_MS);
    });
    var req;
    try {
      req = fetch("/stt/fix", { method: "POST", credentials: "same-origin", signal: ctl ? ctl.signal : undefined,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: raw, final: true, context: (context || []).slice(-6) }) });
    } catch (e) { clearTimeout(timer); return Promise.resolve(raw); }
    var asked = Promise.resolve(req).then(function (r) { return r.json(); })
      .then(function (d) { clearTimeout(timer); return !gaveUp && d && d.ok && d.text ? String(d.text) : raw; },
        function () { clearTimeout(timer); return raw; });
    return Promise.race([asked, late]);
  }

  // The last messages of a chat as plain text, oldest first, for the rewrite's context. `root` is the message list,
  // `selector` matches one message's text. Each is cut to 300 characters; pure apart from DOM reads.
  function recentMessages(root, selector, n) {
    var out = [];
    try {
      if (!root || !root.querySelectorAll) return out;
      var nodes = root.querySelectorAll(selector);
      for (var i = Math.max(0, nodes.length - (n || 4)); i < nodes.length; i++) {
        var t = String(nodes[i].innerText || nodes[i].textContent || "").replace(/\s+/g, " ").trim();
        if (t) out.push(t.length > 300 ? t.slice(0, 300) + "..." : t);
      }
    } catch (e) { return out; }
    return out;
  }

  // The ear the last press found: "upload" (Groq or OpenAI listens again on stop), "" (browser text only) or null.
  var api = { create: create, joinText: joinText, buildRun: buildRun, polishText: polishText,
    recentMessages: recentMessages, isPhoneUA: isPhoneUA, plan: plan, isPhone: isPhone, isIOS: isIOS,
    isAndroid: isAndroid,
    ear: function () { return earKind; }, warm: askEar };
  if (typeof window !== "undefined") window.JavisDictate = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
