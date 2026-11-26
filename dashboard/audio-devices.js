/* audio-devices.js - which microphone and which speaker a voice call uses (Settings > Voice, 26/11/2026).

   The pickers sit in the voice card next to "Test mic" and "Test speaker". The choice lives in this browser only
   (localStorage "javis.mic" / "javis.speaker", every access in try/catch: a private window simply keeps the defaults),
   because a device id means nothing on another machine.

   - Microphone: getMic() opens the saved device with deviceId exact. When it is gone (headset unplugged, another app
     holds it) the call opens the default mic instead of failing. Used by the Live call (voice-live.js), the Basic call
     (voice.js), the wake-by-voice level check (app.js) and the mic test, so the meter shows what the call hears. The
     Basic call's browser recognition cannot pick a device and keeps the system default.
   - Speaker: applySpeaker() calls setSinkId on an <audio> element (ChatGPT Live, read-aloud) or an AudioContext that
     has it (Live over an API key, the speaker test). A browser without HTMLMediaElement.setSinkId (Safari, iPhone)
     shows no speaker picker: the phone decides where sound goes. A changed speaker reaches a running call at once
     (event "javis:audio-devices"); a changed mic is used from the next time the call opens the mic.

   Pure helpers are exported for node tests (tests/js/test_audio_devices.js). */
(function (root) {
  "use strict";

  var MIC_KEY = "javis.mic", SPEAKER_KEY = "javis.speaker";
  var EVENT = "javis:audio-devices";
  // Chrome on Windows adds these two aliases of a real device; "System default" already stands for them.
  var ALIASES = { "default": true, communications: true };

  function read(key) {
    try { return String((root.localStorage && root.localStorage.getItem(key)) || ""); } catch (e) { return ""; }
  }
  function write(key, value) {
    try {
      if (!root.localStorage) return;
      if (value) root.localStorage.setItem(key, String(value)); else root.localStorage.removeItem(key);
    } catch (e) {}
  }

  // Audio constraints of a call: `base` plus the chosen device, when there is one.
  function micConstraints(base, deviceId) {
    var out = {};
    Object.keys(base || {}).forEach(function (k) { out[k] = base[k]; });
    if (deviceId) out.deviceId = { exact: deviceId };
    return out;
  }

  // The failure means "that device cannot be used", not "no permission": try the default mic.
  function deviceGone(err) {
    var name = err && err.name;
    return name === "OverconstrainedError" || name === "NotFoundError" || name === "NotReadableError";
  }

  // The microphone stream of a call. `media` is navigator.mediaDevices (tests pass a fake).
  function getMic(base, media) {
    var md = media || (root.navigator && root.navigator.mediaDevices);
    var id = read(MIC_KEY);
    if (!id) return md.getUserMedia({ audio: micConstraints(base) });
    return md.getUserMedia({ audio: micConstraints(base, id) }).catch(function (e) {
      if (!deviceGone(e)) throw e;
      return md.getUserMedia({ audio: micConstraints(base) });
    });
  }

  function canPickSpeaker() {
    var M = root.HTMLMediaElement;
    return !!(M && M.prototype && typeof M.prototype.setSinkId === "function");
  }

  // Send `target` (an <audio> element or an AudioContext) to the chosen speaker. Resolves true when a chosen speaker
  // is in use, false when the default is. Never rejects: a speaker that is gone leaves the default.
  function applySpeaker(target) {
    if (!target || typeof target.setSinkId !== "function") return Promise.resolve(false);
    var id = read(SPEAKER_KEY);
    var current = typeof target.sinkId === "string" ? target.sinkId : "";
    if (current === id) return Promise.resolve(!!id);
    function backToDefault() {
      if (!current) return false;
      try { return Promise.resolve(target.setSinkId("")).then(function () { return false; }, function () { return false; }); }
      catch (e) { return false; }
    }
    try {
      return Promise.resolve(target.setSinkId(id)).then(function () { return !!id; }, backToDefault);
    } catch (e) { return Promise.resolve(backToDefault()); }
  }

  // Options of one picker: "System default" first, then each device by its name. The saved device is selected while
  // it is plugged in; once it is gone the default shows (and is what the call uses).
  function options(devices, kind, saved, defaultLabel, unnamedLabel) {
    var list = [{ value: "", label: defaultLabel }], n = 0, seen = {};
    (devices || []).forEach(function (d) {
      if (!d || d.kind !== kind || !d.deviceId || ALIASES[d.deviceId] || seen[d.deviceId]) return;
      seen[d.deviceId] = true;
      n++;
      list.push({ value: d.deviceId, label: d.label || (unnamedLabel + " " + n) });
    });
    var found = !!saved && list.some(function (o) { return o.value === saved; });
    list.forEach(function (o) { o.selected = found ? o.value === saved : o.value === ""; });
    return list;
  }

  // Before the mic permission is granted the browser lists devices without names (or not at all).
  function needsPermission(devices) {
    return !(devices || []).some(function (d) { return d && d.kind === "audioinput" && d.label; });
  }

  var api = {
    MIC_KEY: MIC_KEY, SPEAKER_KEY: SPEAKER_KEY, EVENT: EVENT,
    micConstraints: micConstraints, deviceGone: deviceGone, getMic: getMic, canPickSpeaker: canPickSpeaker,
    applySpeaker: applySpeaker, options: options, needsPermission: needsPermission,
    mic: function () { return read(MIC_KEY); }, speaker: function () { return read(SPEAKER_KEY); },
    refresh: function () { return Promise.resolve(); },
  };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.JavisAudioDevices = api;
  var doc = root.document;
  if (!doc || !doc.getElementById) return;

  // ---- The two pickers in the voice card -------------------------------------------------------------------------
  var t = function (k, p) { try { return root.t ? root.t(k, p) : k; } catch (e) { return k; } };
  function el(id) { return doc.getElementById(id); }

  function fill(sel, list) {
    var sig = JSON.stringify(list);
    if (sel._devSig === sig) return;
    sel._devSig = sig;
    while (sel.firstChild) sel.removeChild(sel.firstChild);
    list.forEach(function (o) {
      var op = doc.createElement("option");
      op.value = o.value;
      op.textContent = o.label;
      op.selected = !!o.selected;
      sel.appendChild(op);
    });
  }

  function refresh() {
    var md = root.navigator && root.navigator.mediaDevices;
    var mic = el("vcMicSel"), spk = el("vcSpkSel"), hint = el("vcDevHint");
    if (!mic && !spk) return Promise.resolve();
    if (!md || typeof md.enumerateDevices !== "function") {
      if (mic) mic.hidden = true;
      if (spk) spk.hidden = true;
      return Promise.resolve();
    }
    return md.enumerateDevices().then(function (devices) {
      if (mic) fill(mic, options(devices, "audioinput", read(MIC_KEY), t("settings.vc_dev_default"), t("settings.vc_dev_mic")));
      if (spk) {
        spk.hidden = !canPickSpeaker();
        if (!spk.hidden) fill(spk, options(devices, "audiooutput", read(SPEAKER_KEY), t("settings.vc_dev_default"), t("settings.vc_dev_spk")));
      }
      if (hint) hint.hidden = !needsPermission(devices);
    }, function () {});
  }
  api.refresh = refresh;

  function announce(kind) {
    try { root.dispatchEvent(new root.CustomEvent(EVENT, { detail: { kind: kind } })); } catch (e) {}
  }

  function wire() {
    var mic = el("vcMicSel"), spk = el("vcSpkSel");
    if (mic && !mic._devWired) {
      mic._devWired = true;
      mic.addEventListener("change", function () { write(MIC_KEY, mic.value); announce("mic"); });
    }
    if (spk && !spk._devWired) {
      spk._devWired = true;
      spk.addEventListener("change", function () { write(SPEAKER_KEY, spk.value); announce("speaker"); });
    }
    var md = root.navigator && root.navigator.mediaDevices;
    if (!api._watching) {
      api._watching = true;
      if (md && typeof md.addEventListener === "function") md.addEventListener("devicechange", refresh);
      // The option names come from the dictionary, which may arrive after this file ran.
      try { root.addEventListener("javis:i18n", refresh); } catch (e) {}
    }
    refresh();
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", wire); else wire();
})(typeof window !== "undefined" ? window : globalThis);
