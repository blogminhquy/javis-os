// Tasks page on a phone (owner, 06/11/2026, with a screenshot): "Nút thêm việc để thấp xuống, nó bị dính vào chỗ gạt
// cần loop". The round + sat 76px above the bottom and covered the "Đang bật" switch, the last row of a loop's detail.
//
//     node tests/js/test_nut_them_viec_dien_thoai.js
"use strict";
const fs = require("fs");
const path = require("path");
const css = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "tasks.css"), "utf8");
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}
const phone = (/@media \(max-width: 760px\) \{([\s\S]*?)\n\}/.exec(css) || [])[1] || "";
check("the phone block is found", phone.length > 0);
const px = (re) => { const m = re.exec(phone); return m ? Number(m[1]) : NaN; };
const fabBottom = px(/\.nv-fab \{ bottom: calc\((\d+)px \+ env\(safe-area-inset-bottom, 0px\)\); \}/);
const padBottom = px(/\.nv-pbody \{ padding-bottom: calc\((\d+)px \+ env\(safe-area-inset-bottom, 0px\)\); \}/);
const size = Number((/\.nv-fab \{[^}]*width: (\d+)px/.exec(css) || [])[1]);
check("phone: the + sits low, near the corner", fabBottom <= 24, String(fabBottom));
check("phone: the page ends with room for the whole button, so the last row scrolls clear of it",
  padBottom >= fabBottom + size + 12, padBottom + " < " + (fabBottom + size + 12));
check("the button still keeps clear of the iPhone home bar", /\.nv-fab \{ bottom: calc\(\d+px \+ env\(safe-area-inset-bottom/.test(phone));
process.exit(fails ? 1 : 0);
