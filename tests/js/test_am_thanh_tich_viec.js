// Tasks page sounds (owner, 2026-11-06: "nút tích nghe thật đã tai, nút phá băng cũng vậy"): wiring of the Web Audio
// sounds and the habit sparks. The sounds themselves are checked by rendering them offline (peak, length) by hand.
// Run: node tests/js/test_am_thanh_tich_viec.js
"use strict";
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "tasks.js"), "utf8");
const css = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "tasks.css"), "utf8");

let fails = 0;
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails++; }

const play = src.slice(src.indexOf("function sfxPlay("), src.indexOf("function sfx(kind)"));
for (const k of ["tick", "star", "lit", "thaw", "cel"]) check("a sound for " + k, play.indexOf('kind === "' + k + '"') >= 0);
check("no sound file: everything is synthesized", !/new Audio\(|\.mp3|\.wav|\.ogg/.test(play));
check("thawing ends on the habit's flame sound", /kind === "thaw"[\s\S]*sfxPlay\(ac, dest, "lit"/.test(play));

const sfx = src.slice(src.indexOf("function sfx(kind)"), src.indexOf("// ---- effects"));
check("silent on a hidden tab", /document\.hidden\) return/.test(sfx));
check("a browser without Web Audio stays silent, no error", /AC_ = false/.test(src) && /catch \(e\) \{ \/\* no sound is fine \*\/ \}/.test(sfx));

const reward = src.slice(src.indexOf("async function checkWithReward"), src.indexOf("// ---- sounds"));
check("ticking a task plays tick, a priority plays star", /sfx\(star \? "star" : "tick"\)/.test(reward));
const habit = src.slice(src.indexOf('case "check": case "uncheck": {'), src.indexOf('case "run":'));
check("ticking a habit lights it, a frozen one thaws", /sfx\(hk\.frozen \? "thaw" : "lit"\)/.test(habit));
check("ice shards on thaw, embers on light", /burst\([^)]*hk\.frozen \? "ice" : "fire"\)/.test(habit));
check("celebrations play the fanfare, a thaw the ice", /sfx\(S\.sheet\.thaw \? "thaw" : "cel"\)/.test(src));
check("ice and fire spark styles exist", /\.nv-spark\.ice \{/.test(css) && /\.nv-spark\.fire \{/.test(css));

console.log(fails ? `\n${fails} failed` : "\nall passed");
process.exit(fails ? 1 : 0);
