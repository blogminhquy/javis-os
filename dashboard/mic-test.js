/* mic-test.js - "Test mic" and "Test speaker" in Settings > Voice (0.222.0).

   Every automatic check runs on silence, so a muted mic, a level slider at zero or a privacy
   shutter all pass and the call simply hears nothing. Only a person speaking can settle that: the
   meter moves for 5 seconds and the peak is reported, with a hint when it stayed near zero. The
   mic is opened with the same options as a call (echo cancellation, noise suppression, gain), so
   what the meter shows is what Javis hears. Since 26/11/2026 both tests use the mic and speaker picked right beside
   them (audio-devices.js), and a finished mic test fills the pickers (the browser names devices only once allowed).

   Pure helpers (level, verdict) are exported for node tests; the button wiring runs only in a page. */
(function () {
  "use strict";

  var TEST_MS = 5000;
  var QUIET = 0.04, LOW = 0.12;   // peak level under QUIET = nothing heard; under LOW = very faint

  // RMS of a block of float samples, scaled so ordinary speech sits mid-meter (0..1).
  function level(samples) {
    var n = samples ? samples.length : 0;
    if (!n) return 0;
    var sum = 0;
    for (var i = 0; i < n; i++) sum += samples[i] * samples[i];
    return Math.min(1, Math.sqrt(sum / n) * 4);
  }

  // "silent" | "low" | "ok" for the loudest level seen during the test.
  function verdict(peak) {
    if (!(peak >= QUIET)) return "silent";
    return peak < LOW ? "low" : "ok";
  }

  var api = { level: level, verdict: verdict, TEST_MS: TEST_MS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined" || typeof document === "undefined") return;
  window.JavisMicTest = api;

  var t = function (k, p) { try { return window.t ? window.t(k, p) : k; } catch (e) { return k; } };
  var running = false;

  function el(id) { return document.getElementById(id); }

  async function testMic() {
    if (running) return;
    var bar = el("vcMicBar"), out = el("vcMicResult"), btn = el("vcMicTest");
    if (!bar || !out) return;
    running = true;
    if (btn) btn.disabled = true;
    out.textContent = t("settings.vc_mic_speak");
    var stream = null, ctx = null, peak = 0;
    try {
      var micOptions = { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 };
      var dev = window.JavisAudioDevices;
      stream = await (dev ? dev.getMic(micOptions) : navigator.mediaDevices.getUserMedia({ audio: micOptions }));
      var AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC();
      var an = ctx.createAnalyser();
      an.fftSize = 2048;
      ctx.createMediaStreamSource(stream).connect(an);
      var buf = new Float32Array(an.fftSize);
      var end = Date.now() + TEST_MS;
      await new Promise(function (done) {
        (function frame() {
          an.getFloatTimeDomainData(buf);
          var lv = level(buf);
          if (lv > peak) peak = lv;
          bar.style.width = Math.round(lv * 100) + "%";
          if (Date.now() < end) requestAnimationFrame(frame); else done();
        })();
      });
      var pct = { pct: Math.round(peak * 100) };
      var v = verdict(peak);
      out.textContent = v === "ok" ? t("settings.vc_mic_ok", pct)
        : v === "low" ? t("settings.vc_mic_low", pct) : t("settings.vc_mic_silent", pct);
    } catch (e) {
      out.textContent = t("settings.vc_mic_denied", { err: (e && e.name) || "error" });
    } finally {
      try { if (stream) stream.getTracks().forEach(function (tr) { tr.stop(); }); } catch (e) {}
      try { if (ctx) ctx.close(); } catch (e) {}
      bar.style.width = "0%";
      if (btn) btn.disabled = false;
      running = false;
      try { if (window.JavisAudioDevices) window.JavisAudioDevices.refresh(); } catch (e) {}
    }
  }

  // A short two-note chime on the default output, so "I hear nothing" can be told apart from
  // "the speaker is off".
  function testSpeaker() {
    var out = el("vcMicResult");
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      var ctx = new AC();   // made inside the press: an iPhone only lets a context made by one sound
      var chime = function () {
        try {
          var g = ctx.createGain();
          g.connect(ctx.destination);
          [[660, 0], [880, 0.25]].forEach(function (note) {
            var o = ctx.createOscillator();
            o.frequency.value = note[0];
            o.connect(g);
            o.start(ctx.currentTime + note[1]);
            o.stop(ctx.currentTime + note[1] + 0.22);
          });
          g.gain.setValueAtTime(0.0001, ctx.currentTime);
          g.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + 0.03);
          g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.5);
          setTimeout(function () { try { ctx.close(); } catch (e) {} }, 800);
          if (out) out.textContent = t("settings.vc_spk_played");
        } catch (e) {
          if (out) out.textContent = t("settings.vc_spk_fail");
        }
      };
      var dev = window.JavisAudioDevices;
      // Where the context can be routed, the chime waits for the picked speaker, or it would start on the default
      // one. Elsewhere (Safari, iPhone) it plays at once, still inside the press, as before.
      if (dev && dev.applySpeaker && typeof ctx.setSinkId === "function") dev.applySpeaker(ctx).then(chime, chime);
      else chime();
    } catch (e) {
      if (out) out.textContent = t("settings.vc_spk_fail");
    }
  }

  function wire() {
    var m = el("vcMicTest"), s = el("vcSpkTest");
    if (m && !m._wired) { m._wired = true; m.addEventListener("click", testMic); }
    if (s && !s._wired) { s._wired = true; s.addEventListener("click", testSpeaker); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire); else wire();
})();
