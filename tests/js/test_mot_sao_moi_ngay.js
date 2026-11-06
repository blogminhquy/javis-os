// Tasks page (owner, 2026-11-06): one priority star a day, moved rather than refused, and a missed habit time gets
// Skip and Delete like any overdue repeat.
// Run: node tests/js/test_mot_sao_moi_ngay.js
"use strict";
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "tasks.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails++; }

check("one star a day", /var STAR_MAX = 1,/.test(src));
const star = src.slice(src.indexOf('case "star": {'), src.indexOf('case "tri-move":'));
check("starring when the day has its star moves it (old star cleared first)", /prevStars/.test(star) && /star: false/.test(star) && /nv\.pu\.ok_star_moved/.test(star));
check("the move can be undone (old star back)", /prevStars\.map\(function \(pid\) \{ return mine\(\{ __url: "\/my-tasks\/update", id: pid, star: true \}\)/.test(star));
check("no refusal popup left in the star action", !/star_full/.test(star));
check("the moved-star toast exists in vi and en", !!vi["nv.pu.ok_star_moved"] && !!en["nv.pu.ok_star_moved"]);
check("the old 'day is full' texts are gone", !("nv.pu.star_full" in vi) && !("nv.pu.star_full_day" in en));

const ho = src.slice(src.indexOf("function habitOverIcons"), src.indexOf("function triIcons"));
check("a missed habit time offers Skip and Delete", /tri-skip/.test(ho) && /m-del/.test(ho) && !/tri-move/.test(ho));
check("only a missed time of a habit (mo: id) gets them", /function habitOver\(it\) \{[^}]*habitOn\(it\.raw\) && it\.id\.indexOf\("mo:"\) === 0/.test(src));
check("the row draws them and reserves their width", /hOver \? habitOverIcons\(it\)/.test(src) && /hOver \? 2 : 0/.test(src));

console.log(fails ? `\n${fails} failed` : "\nall passed");
process.exit(fails ? 1 : 0);
