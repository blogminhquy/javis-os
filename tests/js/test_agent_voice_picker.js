// Regression contract: the shared agent editor exposes and persists ChatGPT Live voice.
// Run with node tests/js/test_agent_voice_picker.js. No browser/network required.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../..");
const studio = fs.readFileSync(path.join(root, "dashboard/studio.js"), "utf8");
const en = JSON.parse(fs.readFileSync(path.join(root, "dashboard/i18n/en.json"), "utf8"));
const vi = JSON.parse(fs.readFileSync(path.join(root, "dashboard/i18n/vi.json"), "utf8"));
assert.ok(studio.includes('id="agCallVoice"'), "per-agent voice selector exists");
assert.ok(studio.includes("a.chatgpt_voice"), "saved agent voice is read");
assert.ok(studio.includes('chatgpt_voice: (box.querySelector("#agCallVoice")'), "selected voice is saved");
assert.ok(studio.includes('a && a.system ? ""'), "core does not get a misleading partner selector");
for (const lang of [en, vi]) {
  for (const key of ["studio.call_voice", "studio.call_voice_default", "studio.call_voice_hint"]) {
    assert.ok(lang[key] && lang[key].trim(), "missing translation: " + key);
  }
}
console.log("PASS: per-agent ChatGPT Live voice picker contract");
