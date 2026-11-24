// Owner, 24/11/2026 (Teams on an iPhone app, a long empty band under the input): the page layer (.cview) was pinned with
// bottom: 0, which in an app installed on iPhone can sit well above the real bottom of the screen. On a phone it now
// takes the measured height the main chat uses (--app-h from mobile-chat.js), and the keyboard rule still wins.
//
//     node tests/js/test_cview_app_height.js
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const mc = fs.readFileSync(path.join(ROOT, "dashboard", "mobile-chat.js"), "utf8");

let fails = 0;
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails++;
}

// The phone block that holds the page layer rule (several "max-width: 860px" blocks exist).
const at = css.search(/\n\s+\.cview \{ left: 0;/);
const phone = css.lastIndexOf("@media (max-width: 860px) {", at);
const block = at >= 0 && phone >= 0 ? css.slice(phone, css.indexOf("\n@media", at)) : "";
const rule = (block.match(/\n\s*\.cview \{([^}]*)\}/) || [])[1] || "";
check("phone: .cview is sized by the measured height, not pinned to the bottom edge",
  /bottom:\s*auto/.test(rule) && /height:\s*calc\(var\(--app-h,\s*100dvh\)\s*-\s*var\(--topbar-h\)\)/.test(rule), rule);
check("the main chat uses the same measured height", /\.hud \{[^}]*height:\s*var\(--app-h, 100dvh\)/.test(block));
check("the keyboard rule still sets the page layer to the visible part", /body\.kb-open \.cview \{[^}]*height:\s*calc\(var\(--vv-h/.test(css));
check("mobile-chat.js still measures --app-h", mc.includes('rootStyle.setProperty("--app-h"'));

if (fails) { console.log(fails + " FAIL"); process.exit(1); }
console.log("all ok");
