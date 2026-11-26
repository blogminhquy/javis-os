/* Mic and speaker of a voice call, picked in Settings > Voice (dashboard/audio-devices.js, 26/11/2026).

       node tests/js/test_audio_devices.js      (no microphone, no network)

   Pins: the picked mic goes into getUserMedia as deviceId exact, and a mic that is gone falls back to the default
   instead of failing the call (a refused permission still fails); the picked speaker reaches setSinkId and a speaker
   that is gone leaves the default; the lists start with "System default" and show it once the saved device is gone;
   a browser without setSinkId (Safari, iPhone) gets no speaker list; storage that throws (private window) keeps the
   defaults; the Live call (voice-live.js) opens the mic and routes sound through this module; the voice card has the
   two pickers beside their tests, i18n in vi and en, readable sizes. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..", "..");
const src = fs.readFileSync(path.join(root, "dashboard/audio-devices.js"), "utf8");
const fails = [];
function check(name, cond, detail) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || detail === undefined ? "" : "  [" + JSON.stringify(detail) + "]"));
  if (!cond) fails.push(name);
}
const tick = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };

function storage(init, broken) {
  const m = new Map(Object.entries(init || {}));
  if (broken) return { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); }, removeItem() { throw new Error("denied"); } };
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k), m };
}

// A page-less load: only the pure part and getMic/applySpeaker.
function load(opts = {}) {
  const box = { window: null, localStorage: storage(opts.saved, opts.broken), navigator: opts.navigator || {} };
  if (opts.sink !== false) box.HTMLMediaElement = function () {};
  if (opts.sink !== false) box.HTMLMediaElement.prototype.setSinkId = function () {};
  box.window = box;
  vm.runInNewContext(src, box);
  return box.JavisAudioDevices;
}

function fakeMedia(behaviour) {
  const calls = [];
  return {
    calls,
    getUserMedia(c) {
      calls.push(c);
      const r = behaviour(c, calls.length);
      return r instanceof Error ? Promise.reject(r) : Promise.resolve(r);
    },
  };
}
function err(name) { const e = new Error(name); e.name = name; return e; }

(async () => {
  const BASE = { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 };

  // ---- Microphone ----
  let D = load({ saved: { "javis.mic": "usb-mic" } });
  let md = fakeMedia(() => "stream-usb");
  check("picked mic goes in as deviceId exact, call options kept",
        (await D.getMic(BASE, md)) === "stream-usb" && md.calls[0].audio.deviceId.exact === "usb-mic"
        && md.calls[0].audio.echoCancellation === true && md.calls[0].audio.channelCount === 1, md.calls);
  check("the caller's options object is not changed", !("deviceId" in BASE));

  md = fakeMedia((c, n) => (n === 1 ? err("OverconstrainedError") : "stream-default"));
  check("picked mic unplugged: the call opens the default mic",
        (await D.getMic(BASE, md)) === "stream-default" && md.calls.length === 2 && !md.calls[1].audio.deviceId, md.calls);
  md = fakeMedia((c, n) => (n === 1 ? err("NotFoundError") : "stream-default"));
  check("picked mic not found: default mic", (await D.getMic(BASE, md)) === "stream-default");

  md = fakeMedia(() => err("NotAllowedError"));
  let caught = null;
  try { await D.getMic(BASE, md); } catch (e) { caught = e.name; }
  check("a refused permission still fails (no second prompt)", caught === "NotAllowedError" && md.calls.length === 1, caught);

  D = load();
  md = fakeMedia(() => "stream");
  await D.getMic(BASE, md);
  check("nothing picked: the default mic, no deviceId", md.calls.length === 1 && !md.calls[0].audio.deviceId, md.calls);

  D = load({ saved: { "javis.mic": "usb-mic" }, broken: true });
  md = fakeMedia(() => "stream");
  await D.getMic(BASE, md);
  check("storage that throws (private window): defaults, no error", !md.calls[0].audio.deviceId && D.mic() === "");

  // ---- Speaker ----
  D = load({ saved: { "javis.speaker": "headset" } });
  const el = { sinkId: "", setSinkId(id) { this.calls = (this.calls || []).concat(id); this.sinkId = id; return Promise.resolve(); } };
  check("picked speaker reaches setSinkId", (await D.applySpeaker(el)) === true && el.sinkId === "headset", el.calls);
  await D.applySpeaker(el);
  check("already on it: not set twice", el.calls.length === 1, el.calls);

  const gone = { sinkId: "old", setSinkId(id) { this.calls = (this.calls || []).concat(id); if (id) return Promise.reject(err("NotFoundError")); this.sinkId = ""; return Promise.resolve(); } };
  check("picked speaker gone: back to the default, never throws",
        (await D.applySpeaker(gone)) === false && gone.sinkId === "" && gone.calls.join(",") === "headset,", gone.calls);
  const throwsSync = { sinkId: "", setSinkId() { throw new Error("boom"); } };
  check("a setSinkId that throws is swallowed", (await D.applySpeaker(throwsSync)) === false);
  check("no setSinkId on the target (Safari): nothing happens", (await D.applySpeaker({})) === false && (await D.applySpeaker(null)) === false);
  D = load();
  const back = { sinkId: "headset", setSinkId(id) { this.sinkId = id; return Promise.resolve(); } };
  await D.applySpeaker(back);
  check("default picked again: the element goes back to the default", back.sinkId === "", back.sinkId);

  check("speaker list offered where setSinkId exists", load().canPickSpeaker() === true);
  check("no speaker list without setSinkId (Safari, iPhone)", load({ sink: false }).canPickSpeaker() === false);

  // ---- Lists ----
  const devices = [
    { kind: "audioinput", deviceId: "default", label: "Default - Laptop Mic" },
    { kind: "audioinput", deviceId: "communications", label: "Communications - Headset" },
    { kind: "audioinput", deviceId: "laptop", label: "Laptop Mic" },
    { kind: "audioinput", deviceId: "usb", label: "" },
    { kind: "audiooutput", deviceId: "spk", label: "Speakers" },
    { kind: "videoinput", deviceId: "cam", label: "Camera" },
  ];
  let list = D.options(devices, "audioinput", "laptop", "System default", "Mic");
  check("default first, browser aliases and other kinds left out",
        JSON.stringify(list.map(o => o.value)) === JSON.stringify(["", "laptop", "usb"]), list);
  check("a device without a name gets a numbered one", list[2].label === "Mic 2", list[2]);
  check("saved device selected", list.filter(o => o.selected).map(o => o.value).join() === "laptop");
  list = D.options(devices, "audioinput", "unplugged", "System default", "Mic");
  check("saved device gone: the default shows as selected", list.filter(o => o.selected).map(o => o.value).join() === "");
  check("permission not granted yet: names are missing",
        D.needsPermission([{ kind: "audioinput", deviceId: "", label: "" }]) === true && D.needsPermission([]) === true
        && D.needsPermission(devices) === false);

  // ---- The picker in a page ----
  {
    const els = {}, listeners = {};
    function node(id) {
      return { id, hidden: false, value: "", children: [], _l: {},
        get firstChild() { return this.children[0] || null; },
        removeChild(c) { this.children.splice(this.children.indexOf(c), 1); },
        appendChild(c) { this.children.push(c); if (c.selected) this.value = c.value; },
        addEventListener(ev, fn) { this._l[ev] = fn; } };
    }
    ["vcMicSel", "vcSpkSel", "vcDevHint"].forEach(id => { els[id] = node(id); });
    const ls = storage({});
    const box = {
      localStorage: ls,
      t: k => ({ "settings.vc_dev_default": "System default", "settings.vc_dev_mic": "Mic", "settings.vc_dev_spk": "Speaker" }[k] || k),
      navigator: { mediaDevices: { enumerateDevices: async () => devices, addEventListener(ev, fn) { listeners[ev] = fn; } } },
      document: { readyState: "complete", getElementById: id => els[id] || null, createElement: () => ({}) },
      addEventListener(ev, fn) { listeners["win:" + ev] = fn; },
      dispatchEvent(e) { (box.sent = box.sent || []).push(e); },
      CustomEvent: function (type, init) { this.type = type; this.detail = init && init.detail; },
    };
    box.HTMLMediaElement = function () {};
    box.HTMLMediaElement.prototype.setSinkId = function () {};
    box.window = box;
    vm.runInNewContext(src, box);
    await tick();
    const mic = els.vcMicSel, spk = els.vcSpkSel;
    check("page: mic list filled, default first",
          mic.children.map(o => o.label || o.textContent).join("|") === "System default|Laptop Mic|Mic 2",
          mic.children.map(o => o.textContent));
    check("page: speaker list shown and filled", !spk.hidden && spk.children.length === 2);
    check("page: no permission hint once names are known", els.vcDevHint.hidden === true);
    check("page: lists follow plugged devices and the dictionary", typeof listeners.devicechange === "function"
          && typeof listeners["win:javis:i18n"] === "function");
    mic.value = "usb"; mic._l.change();
    spk.value = "spk"; spk._l.change();
    check("page: choices remembered in this browser", ls.m.get("javis.mic") === "usb" && ls.m.get("javis.speaker") === "spk");
    check("page: a running call hears about the change",
          (box.sent || []).map(e => e.type + ":" + e.detail.kind).join() === "javis:audio-devices:mic,javis:audio-devices:speaker");
    mic.value = ""; mic._l.change();
    check("page: back to the default forgets the device", !ls.m.has("javis.mic"));

    // Safari: no setSinkId, the speaker list hides; its test button stays (HTML below).
    const els2 = {};
    ["vcMicSel", "vcSpkSel", "vcDevHint"].forEach(id => { els2[id] = node(id); });
    const box2 = Object.assign({}, box, { document: { readyState: "complete", getElementById: id => els2[id] || null, createElement: () => ({}) },
      navigator: { mediaDevices: { enumerateDevices: async () => [{ kind: "audioinput", deviceId: "", label: "" }] } } });
    delete box2.HTMLMediaElement;
    box2.window = box2;
    vm.runInNewContext(src, box2);
    await tick();
    check("page without setSinkId: speaker list hidden", els2.vcSpkSel.hidden === true);
    check("page before the mic is allowed: hint shown, only the default listed",
          els2.vcDevHint.hidden === false && els2.vcMicSel.children.length === 1);
  }

  // ---- The Live call uses it ----
  {
    const live = fs.readFileSync(path.join(root, "dashboard/voice-live.js"), "utf8");
    const seen = { mic: null, sinks: [] };
    class AudioContext {
      constructor() { this.destination = {}; this.currentTime = 0; this.sinkId = ""; }
      resume() { return Promise.resolve(); } suspend() { return Promise.resolve(); } close() { return Promise.resolve(); }
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
      createScriptProcessor() { return { connect() {}, disconnect() {} }; }
    }
    class WebSocket { static OPEN = 1; constructor() { this.readyState = 0; } send() {} close() {} }
    const winListeners = {};
    const box = {
      window: { AudioContext, addEventListener(ev, fn) { winListeners[ev] = fn; },
        JavisAudioDevices: { getMic(opts) { seen.mic = opts; return new Promise(() => {}); },
                             applySpeaker(target) { seen.sinks.push(target); return Promise.resolve(true); } } },
      navigator: { mediaDevices: { getUserMedia() { seen.direct = true; return new Promise(() => {}); } } },
      location: { protocol: "http:", host: "localhost" }, WebSocket, Audio: function () { this.setAttribute = () => {}; },
      ArrayBuffer, Int16Array, Float32Array, setTimeout, clearTimeout, setInterval() { return 0; }, clearInterval() {},
    };
    vm.runInNewContext(live, box);
    box.window.JavisVoiceLive.start({});
    await tick();
    check("Live call opens the picked mic with its call options",
          seen.mic && seen.mic.echoCancellation === true && seen.mic.channelCount === 1 && !seen.direct, seen.mic);
    check("Live call routes its playback context to the picked speaker",
          seen.sinks.some(s => s instanceof AudioContext), seen.sinks.length);
    box.window.JavisVoiceLive.unlock();
    const n = seen.sinks.length;
    check("Live call's <audio> element goes to the picked speaker too", seen.sinks.some(s => s instanceof box.Audio));
    winListeners["javis:audio-devices"]({ detail: { kind: "speaker" } });
    check("a speaker changed mid-call is applied at once", seen.sinks.length > n);
    box.window.JavisVoiceLive.stop();
  }

  // ---- Voice card ----
  const html = fs.readFileSync(path.join(root, "dashboard/index.html"), "utf8");
  const card = html.slice(html.indexOf('id="voiceCard"'), html.indexOf("<!-- THƯƠNG HIỆU."));
  for (const id of ["vcMicSel", "vcSpkSel", "vcDevHint", "vcMicTest", "vcSpkTest", "vcMicBar", "vcMicResult"])
    check(`voice card has #${id}`, card.includes(`id="${id}"`));
  const micRow = card.slice(card.indexOf('for="vcMicSel"'), card.indexOf('id="vcMicTest"'));
  check("mic list sits beside Test mic, explanation behind (i)",
        micRow.includes('id="vcMicSel"') && micRow.includes('class="info-i"') && micRow.includes('class="info-body" hidden'));
  check("speaker list sits beside Test speaker, hidden until the page knows it can route sound",
        /<select class="js-input" id="vcSpkSel" hidden><\/select>\s*<button[^>]*id="vcSpkTest"/.test(card));
  check("audio-devices.js is loaded", html.includes("/static/audio-devices.js"));
  const vi = JSON.parse(fs.readFileSync(path.join(root, "dashboard/i18n/vi.json"), "utf8"));
  const en = JSON.parse(fs.readFileSync(path.join(root, "dashboard/i18n/en.json"), "utf8"));
  for (const k of ["settings.vc_dev_mic", "settings.vc_dev_spk", "settings.vc_dev_default", "settings.vc_dev_need_perm", "settings.vc_dev_info"])
    check(`i18n vi+en has ${k}`, typeof vi[k] === "string" && typeof en[k] === "string");
  check("no em dash or en dash", !/[\u2013\u2014]/.test(src + vi["settings.vc_dev_info"] + en["settings.vc_dev_info"]));
  const css = fs.readFileSync(path.join(root, "dashboard/console.css"), "utf8");
  check("pickers: 16px text, 48px tap targets",
        /#voiceCard \.vc-dev \.qs-lbl \{ font-size: 16px; \}/.test(css) && /#voiceCard \.vc-dev \.vc-sub \{ font-size: 16px;/.test(css)
        && /min-height: 48px; font-size: 16px;/.test(css));

  if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
  console.log("\nOK - audio devices");
})().catch(e => { console.error(e); process.exit(1); });
