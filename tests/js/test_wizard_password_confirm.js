/* Welcome wizard (2026-11-11): the admin password is typed twice, and each box has an eye to read it back.

       node tests/js/test_wizard_password_confirm.js

Owner, 11/11/2026: "trong phần popup chào mừng tạo tài khoản em phải cho nhập lại mật khẩu 2 lần và có mắt ấn để mở ra
xem mật khẩu".
*/
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const html = fs.readFileSync(path.join(D, "index.html"), "utf8");
const app = fs.readFileSync(path.join(D, "app.js"), "utf8");
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
const vi = require(path.join(D, "i18n", "vi.json")), en = require(path.join(D, "i18n", "en.json"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + extra));
  if (!cond) fails++;
}

const wz = (html.match(/<div class="modal-overlay" id="setupWizard">[\s\S]*?<div class="modal-overlay" id="authOverlay">/) || [""])[0];
check("the wizard is found", !!wz);
check("two password boxes, both hidden text and both offered as a new password",
  /<input id="wzPass" type="password"[^>]*autocomplete="new-password">/.test(wz)
  && /<input id="wzPass2" type="password"[^>]*autocomplete="new-password">/.test(wz));
check("the second box is labelled and has its own placeholder, through i18n",
  /<label for="wzPass2" data-i18n="setm\.pass2">/.test(wz) && /id="wzPass2"[^>]*data-i18n-ph="wz\.pass2_ph"/.test(wz));
const eyes = wz.match(/<button type="button" class="auth-pw-eye wz-pw-eye" aria-pressed="false"[^>]*data-i18n-aria="auth\.show_pw"><i data-ic="eye"><\/i><\/button>/g) || [];
check("each box has an eye button, named for screen readers", eyes.length === 2, String(eyes.length));
check("each box and its eye share one .auth-pw wrapper (the eye of the sign-in box)",
  (wz.match(/<div class="auth-pw">\s*<input id="wzPass2?"[^>]*>\s*<button type="button" class="auth-pw-eye wz-pw-eye"/g) || []).length === 2);
check("the box keeps room for the eye inside a settings section", css.includes(".set-sec .auth-pw input { padding-right: 44px; }"));
["setm.pass2", "wz.pass2_ph", "auth.show_pw", "app.pw_mismatch"].forEach((k) => check("key " + k + " in vi and en", !!vi[k] && !!en[k]));

// ---- the finish handler: the two boxes must match before anything is sent ----
const fin = (app.match(/getElementById\("wzFinish"\)\.addEventListener\("click", async \(\) => \{[\s\S]*?\n  \}\);/) || [""])[0];
check("the finish handler is found", !!fin);
const iMis = fin.indexOf('window.t("app.pw_mismatch")'), iSend = fin.indexOf('fetch("/auth/setup"');
check("a mismatch stops before /auth/setup is called", iMis !== -1 && iSend !== -1 && iMis < iSend);
check("compared whenever either box has text, so an empty first box with a filled second one is caught too",
  /if \(pass2El && pass !== pass2El\.value\) \{/.test(fin));
check("the screen goes to the box to fix: the second one, or the first when it was left empty",
  /_soiOTrong\(pass \? pass2El : document\.getElementById\("wzPass"\), window\.t\("app\.pw_mismatch"\)\)/.test(fin));
check("a server that demands a password also demands the second box", /const pass2 = document\.getElementById\("wzPass2"\);\s*if \(pass2\) pass2\.required = true;/.test(app));

// ---- the eye: one state for both boxes, run on a fake DOM ----
const eyeSrc = (app.match(/\/\/ Welcome wizard: one eye state[\s\S]*?\n\}\)\(\);/) || [""])[0];
check("the eye block is found", !!eyeSrc);
function fakeEl(id) {
  const ls = {};
  return { id, type: "password", textContent: "", attrs: {}, addEventListener(n, f) { ls[n] = f; }, fire(n) { if (ls[n]) ls[n]({ preventDefault() {} }); },
    setAttribute(k, v) { this.attrs[k] = v; } };
}
const els = { wzPass: fakeEl("wzPass"), wzPass2: fakeEl("wzPass2"), wzErr: fakeEl("wzErr") };
const eyeEls = [fakeEl("e1"), fakeEl("e2")];
const document = { getElementById: (id) => els[id] || null, querySelectorAll: () => eyeEls };
const window = { t: (k) => k };
new Function("document", "window", eyeSrc)(document, window);
eyeEls[0].fire("click");
check("one eye shows both boxes and marks both eyes as pressed",
  els.wzPass.type === "text" && els.wzPass2.type === "text" && eyeEls.every((e) => e.attrs["aria-pressed"] === "true"));
eyeEls[1].fire("click");
check("the other eye hides both again",
  els.wzPass.type === "password" && els.wzPass2.type === "password" && eyeEls.every((e) => e.attrs["aria-pressed"] === "false"));
els.wzErr.textContent = "app.pw_mismatch";
els.wzPass2.fire("input");
check("typing again clears the mismatch line", els.wzErr.textContent === "");
els.wzErr.textContent = "another error";
els.wzPass.fire("input");
check("but leaves any other error alone", els.wzErr.textContent === "another error");

const dash = String.fromCharCode(0x2014), nd = String.fromCharCode(0x2013);
check("no em or en dash in the new code", ![eyeSrc, vi["wz.pass2_ph"], en["wz.pass2_ph"]].some((s) => s.includes(dash) || s.includes(nd)));
if (fails) { console.log("\nFAIL - test_wizard_password_confirm: " + fails); process.exit(1); }
console.log("\nOK - test_wizard_password_confirm: all pass");
