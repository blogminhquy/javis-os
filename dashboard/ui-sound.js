// Javis UI sounds and their on/off switch (owner, 2026-11-06: "nút tích nghe thật đã tai, nút phá băng cũng vậy",
// then "để bật tắt âm thanh vào chỗ gần với chỗ sáng tối, không cần có volume chỉnh chỉ cần nút thôi").
// Sounds are made on the spot with Web Audio, no sound file: a crisp click and a bright ding for a tick, a rising
// sparkle for a priority, a whoosh into a warm chord when a habit lights, ice cracking then glass chimes when it thaws,
// a short fanfare for a celebration. The switch (#soundToggle, next to #themeToggle) is one setting for this device;
// off means silent everywhere. Quiet on a hidden tab; a browser without Web Audio simply stays silent.
(function () {
  "use strict";
  var KEY = "javis.sound";
  var AC_ = null, NOISE_ = null;
  function audioCtx() {
    if (AC_ === false) return null;
    try {
      if (!AC_) { var C = window.AudioContext || window.webkitAudioContext; if (!C) { AC_ = false; return null; } AC_ = new C(); }
      if (AC_.state === "suspended" && AC_.resume) AC_.resume();
      return AC_;
    } catch (e) { AC_ = false; return null; }
  }  function sfxTone(ac, out, f, t, dur, type, vol, f2) {
    var o = ac.createOscillator(), g = ac.createGain();
    o.type = type || "sine"; o.frequency.setValueAtTime(f, t);
    if (f2) o.frequency.exponentialRampToValueAtTime(f2, t + dur * 0.6);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + 0.006); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(out); o.start(t); o.stop(t + dur + 0.03);
  }  function sfxNoise(ac, out, t, dur, vol, kind, f, f2, q) {
    if (!NOISE_ || NOISE_.sampleRate !== ac.sampleRate) {
      NOISE_ = ac.createBuffer(1, Math.floor(ac.sampleRate * 0.5), ac.sampleRate);
      var d = NOISE_.getChannelData(0); for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    }
    var src = ac.createBufferSource(), fl = ac.createBiquadFilter(), g = ac.createGain();
    src.buffer = NOISE_; fl.type = kind; fl.Q.value = q || 1; fl.frequency.setValueAtTime(f, t);
    if (f2) fl.frequency.exponentialRampToValueAtTime(f2, t + dur);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + Math.min(0.01, dur / 4)); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(fl); fl.connect(g); g.connect(out); src.start(t); src.stop(t + dur + 0.02);
  }  // Pure scheduling on any context (a live one, or an OfflineAudioContext in a test).
  function sfxPlay(ac, dest, kind, t) {
    var out = ac.createGain(); out.gain.value = 0.55; out.connect(dest);
    var i, ARP;
    if (kind === "tick" || kind === "star") {
      sfxNoise(ac, out, t, 0.03, 0.3, "bandpass", 3200, 1800, 1.4);          // the click
      sfxTone(ac, out, 520, t, 0.07, "sine", 0.32, 1250);                     // the pop
      sfxTone(ac, out, 1568, t + 0.035, 0.42, "triangle", 0.2);               // the ding (G6 + D7)
      sfxTone(ac, out, 2349, t + 0.035, 0.3, "sine", 0.07);
      if (kind === "star") {
        ARP = [1047, 1319, 1568, 2093, 2637];
        for (i = 0; i < ARP.length; i++) sfxTone(ac, out, ARP[i], t + 0.09 + i * 0.05, 0.34, "triangle", 0.12);
        sfxTone(ac, out, 4186, t + 0.36, 0.5, "sine", 0.05);
      }
    } else if (kind === "lit") {
      sfxNoise(ac, out, t, 0.3, 0.3, "bandpass", 260, 2600, 0.9);            // the whoosh of the flame
      sfxTone(ac, out, 196, t, 0.3, "sine", 0.24, 392);
      sfxTone(ac, out, 784, t + 0.17, 0.55, "triangle", 0.2);                // a warm chord
      sfxTone(ac, out, 988, t + 0.19, 0.55, "triangle", 0.15);
      sfxTone(ac, out, 1175, t + 0.21, 0.6, "sine", 0.13);
    } else if (kind === "thaw") {
      sfxNoise(ac, out, t, 0.035, 0.36, "highpass", 2600, 0, 0.7);            // the ice cracks
      sfxNoise(ac, out, t + 0.05, 0.03, 0.32, "highpass", 3400, 0, 0.7);
      sfxNoise(ac, out, t + 0.11, 0.05, 0.38, "highpass", 2200, 0, 0.7);
      sfxTone(ac, out, 170, t, 0.16, "sine", 0.22, 80);
      ARP = [2637, 3136, 3520, 4186, 5274];                                    // then glass chimes as it melts
      for (i = 0; i < ARP.length; i++) sfxTone(ac, out, ARP[i], t + 0.17 + i * 0.055, 0.45, "sine", 0.09);
      sfxPlay(ac, dest, "lit", t + 0.42);                                       // and the fire comes back
    } else if (kind === "cel") {
      ARP = [523, 659, 784, 1047];
      for (i = 0; i < ARP.length; i++) sfxTone(ac, out, ARP[i], t + i * 0.09, i === 3 ? 0.9 : 0.32, "triangle", 0.21);
      sfxTone(ac, out, 1319, t + 0.27, 0.9, "sine", 0.08);
      sfxTone(ac, out, 1568, t + 0.27, 0.9, "sine", 0.06);
    }
  }
  function on() { try { return localStorage.getItem(KEY) !== "off"; } catch (e) { return true; } }
  function play(kind) {
    if (!on() || document.hidden) return;
    var ac = audioCtx(); if (!ac) return;
    try { sfxPlay(ac, ac.destination, kind, ac.currentTime + 0.01); } catch (e) { /* no sound is fine */ }
  }
  // The button says what is true NOW (like the light/dark one): a speaker with waves when on, crossed out when off.
  function sync() {
    var b = document.getElementById("soundToggle");
    if (!b) return;
    var o = on(), key = o ? "top.sound_on" : "top.sound_off", txt = window.t ? window.t(key) : key;
    if (txt === key) txt = o ? "Sound effects are on - click to turn them off" : "Sound effects are off - click to turn them on";
    b.setAttribute("aria-pressed", o ? "true" : "false");
    b.title = txt;
    b.setAttribute("aria-label", txt);
  }
  function set(v) {
    try { localStorage.setItem(KEY, v ? "on" : "off"); } catch (e) { /* private mode: this page only */ }
    sync();
  }
  function toggle() {
    var v = !on();
    set(v);
    if (v) play("tick");   // turning it on answers with the tick itself
  }
  function init() {
    var b = document.getElementById("soundToggle");
    if (b) b.addEventListener("click", toggle);
    sync();
    window.addEventListener("javis:i18n", sync);
    window.addEventListener("storage", function (e) { if (e.key === KEY) sync(); });   // other tabs follow
  }
  window.JavisSound = { on: on, set: set, play: play, _sfxPlay: sfxPlay };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
