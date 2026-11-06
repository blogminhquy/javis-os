// Tasks page sounds (owner, 2026-11-06: "nút tích nghe thật đã tai, nút phá băng cũng vậy"): wiring of the Web Audio
// sounds and the habit sparks. The sounds themselves are checked by rendering them offline (peak, length) by hand.
// Run: node tests/js/test_am_thanh_tich_viec.js
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const src = fs.readFileSync(path.join(D, "tasks.js"), "utf8");
const css = fs.readFileSync(path.join(D, "tasks.css"), "utf8");
const snd = fs.readFileSync(path.join(D, "ui-sound.js"), "utf8");
const html = fs.readFileSync(path.join(D, "index.html"), "utf8");
const style = fs.readFileSync(path.join(D, "style.css"), "utf8");
const ccss = fs.readFileSync(path.join(D, "console.css"), "utf8");
const mob = fs.readFileSync(path.join(D, "mobile-chat.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(D, "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails++; }

const play = snd.slice(snd.indexOf("function sfxPlay("), snd.indexOf("function on()"));
for (const k of ["tick", "star", "lit", "thaw", "cel"]) check("a sound for " + k, play.indexOf('kind === "' + k + '"') >= 0);
check("no sound file: everything is synthesized", !/new Audio\(|\.mp3|\.wav|\.ogg/.test(play));
check("thawing ends on the habit's flame sound", /kind === "thaw"[\s\S]*sfxPlay\(ac, dest, "lit"/.test(play));

const pl = snd.slice(snd.indexOf("function play(kind)"), snd.indexOf("function sync()"));
check("silent when switched off or on a hidden tab", /if \(!on\(\) \|\| document\.hidden\) return/.test(pl));
check("a browser without Web Audio stays silent, no error", /AC_ = false/.test(snd) && /catch \(e\) \{ \/\* no sound is fine \*\/ \}/.test(pl));
check("tasks.js plays through the shared switch", /function sfx\(kind\) \{ try \{ if \(window\.JavisSound\) window\.JavisSound\.play\(kind\)/.test(src) && !/AudioContext/.test(src));

// The switch (owner: "để bật tắt âm thanh vào chỗ gần với chỗ sáng tối, không cần có volume chỉnh chỉ cần nút thôi").
const iS = html.indexOf('id="soundToggle"'), iT = html.indexOf('id="themeToggle"');
check("the sound button sits right before the light/dark one", iS > 0 && iT > iS && iT - iS < 1600);
check("only a button, no volume slider", !/type="range"/.test(html.slice(iS, iT)));
check("ui-sound.js loads right after theme.js", /static\/theme\.js\?v=\d+"><\/script>\n  <script src="\/static\/ui-sound\.js/.test(html));
check("speaker with waves when on, crossed out when off", /\.sound-toggle\[aria-pressed="false"\] \.ic-son \{ display: none; \}/.test(style) && /\.sound-toggle \.ic-soff \{ display: none; \}/.test(style));
check("on a phone it moves to the drawer foot beside light/dark", /moveEl\(document\.getElementById\("soundToggle"\), true, true\);[^\n]*\n\s*moveEl\(document\.getElementById\("themeToggle"\)/.test(mob) && /\.rail-foot #soundToggle \+ #themeToggle/.test(ccss));
check("the setting is one key on this device, default on", /KEY = "javis\.sound"/.test(snd) && /getItem\(KEY\) !== "off"/.test(snd));
check("tooltips in vi and en", !!vi["top.sound_on"] && !!vi["top.sound_off"] && !!en["top.sound_on"] && !!en["top.sound_off"]);

const reward = src.slice(src.indexOf("async function checkWithReward"), src.indexOf("// ---- sounds"));
check("ticking a task plays tick, a priority plays star", /sfx\(star \? "star" : "tick"\)/.test(reward));
const habit = src.slice(src.indexOf('case "check": case "uncheck": {'), src.indexOf('case "run":'));
check("ticking a habit lights it, a frozen one thaws", /sfx\(hk\.frozen \? "thaw" : "lit"\)/.test(habit));
check("ice shards on thaw, embers on light", /burst\([^)]*hk\.frozen \? "ice" : "fire"\)/.test(habit));
check("celebrations play the fanfare, a thaw the ice", /sfx\(S\.sheet\.thaw \? "thaw" : "cel"\)/.test(src));
check("ice and fire spark styles exist", /\.nv-spark\.ice \{/.test(css) && /\.nv-spark\.fire \{/.test(css));

console.log(fails ? `\n${fails} failed` : "\nall passed");
process.exit(fails ? 1 : 0);
