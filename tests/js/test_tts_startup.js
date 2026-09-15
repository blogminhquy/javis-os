/* Loa khởi động TẮT và chỉ mic bật được nó (dashboard/quick-settings.js).

       node tests/js/test_tts_startup.js

   Chạy với cả ba giá trị từng lưu trong localStorage để chốt: lựa chọn cũ KHÔNG còn ảnh
   hưởng gì nữa. Và công tắc trong Cài đặt nhanh phải KHOÁ khi mic tắt, kèm câu giải thích -
   để nó bấm được rồi tự nảy về là người dùng tưởng nút hỏng. */
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const code = fs.readFileSync(path.join(__dirname, "../../dashboard/quick-settings.js"), "utf8");
for (const saved of ["1", "0", null]) {
  let stored = saved, stopped = 0, mic = false;
  const toggle = {checked: true, disabled: false, title: "",
    addEventListener(name, fn) {this.change = fn;},
    removeAttribute(k) { if (k === "title") this.title = ""; }};
  const context = {window: {t: (k) => "T:" + k}, voice: {ttsEnabled: false, stopSpeaking() {stopped++;}},
    handsFreeActive: () => mic,
    localStorage: {getItem: () => stored, setItem(k, v) {stored = v;}},
    document: {readyState: "complete", getElementById: () => toggle}};
  vm.runInNewContext(code, context);
  assert.strictEqual(context.voice.ttsEnabled, false);
  assert.strictEqual(toggle.checked, false);
  // Mic đang tắt: công tắc khoá và nói rõ vì sao, chứ không im lặng nảy về.
  assert.strictEqual(toggle.disabled, true, "switch is locked while the mic is off");
  assert.strictEqual(toggle.title, "T:qs.tts_can_mic");
  toggle.checked = true; toggle.change();
  assert.strictEqual(context.voice.ttsEnabled, false, "settings cannot enable speech while mic is off");
  assert.strictEqual(toggle.disabled, true);
  mic = true; context.window.JavisTts.set(true);
  assert.strictEqual(context.voice.ttsEnabled, true);
  assert.strictEqual(toggle.disabled, false, "mic on unlocks the manual mute switch");
  assert.strictEqual(toggle.title, "");
  context.window.JavisTts.set(false);
  assert.strictEqual(context.voice.ttsEnabled, false);
  assert.ok(stopped > 0);
  // Tắt tiếng thủ công trong lúc mic vẫn mở: bấm lại được ngay, không bị khoá.
  assert.strictEqual(toggle.disabled, false);
  assert.strictEqual(stored, saved, "no longer writes the old preference key");
}
console.log("TTS starts off even with a saved enabled preference; follows mic activation.");
