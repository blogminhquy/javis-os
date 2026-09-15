const assert = require("assert");
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const code = fs.readFileSync(path.join(__dirname, "../../dashboard/quick-settings.js"), "utf8");
for (const saved of ["1", "0", null]) {
  let stored = saved, stopped = 0, mic = false;
  const toggle = {checked: true, addEventListener(name, fn) {this.change = fn;}};
  const context = {window: {}, voice: {ttsEnabled: false, stopSpeaking() {stopped++;}},
    handsFreeActive: () => mic,
    localStorage: {getItem: () => stored, setItem(k, v) {stored = v;}},
    document: {readyState: "complete", getElementById: () => toggle}};
  vm.runInNewContext(code, context);
  assert.strictEqual(context.voice.ttsEnabled, false);
  assert.strictEqual(toggle.checked, false);
  toggle.checked = true; toggle.change();
  assert.strictEqual(context.voice.ttsEnabled, false, "settings cannot enable speech while mic is off");
  mic = true; context.window.JavisTts.set(true);
  assert.strictEqual(context.voice.ttsEnabled, true);
  context.window.JavisTts.set(false);
  assert.strictEqual(context.voice.ttsEnabled, false);
  assert.ok(stopped > 0);
}
console.log("TTS starts off even with a saved enabled preference; follows mic activation.");
