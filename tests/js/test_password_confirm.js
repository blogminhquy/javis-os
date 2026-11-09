/* The new password is typed twice before it is saved (owner, 2026-11-09).

       node tests/js/test_password_confirm.js

   A password field hides what you type, so one slip of the finger on the only "new password"
   box sets a password nobody knows, and the owner is locked out of their own Javis. The fix is
   the usual one: a second "confirm" box, and the dashboard refuses to send anything until the
   two match.

   Javis has TWO surfaces that change the password (see test_2fa_loi_vao.js for why):

   1. The Account page (console.js renderAccount): #acPass + #acPass2.
   2. The "Login account" block of #quickSet (index.html, handled in app.js): #setAuthPass + #setAuthPass2.

   For each one this file checks that the confirm box exists right after the new-password box,
   and that the save handler compares the two BEFORE it calls /auth/password or /auth/setup
   (comparing after the fetch would save the typo first and complain later). */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8");
const html = read("dashboard", "index.html");
const consoleJs = read("dashboard", "console.js");
const appJs = read("dashboard", "app.js");
const VI = JSON.parse(read("dashboard", "i18n", "vi.json"));
const EN = JSON.parse(read("dashboard", "i18n", "en.json"));

const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// Every fetch to `url` inside `body` comes after the first `pass !== pass2` check.
function comparedBeforeEachFetch(body, url) {
  const cmp = body.indexOf("pass !== pass2");
  let at = body.indexOf(`fetch("${url}"`);
  if (cmp < 0 || at < 0) return false;
  while (at >= 0) {
    // The nearest comparison before this fetch must exist.
    if (body.lastIndexOf("pass !== pass2", at) < 0) return false;
    at = body.indexOf(`fetch("${url}"`, at + 1);
  }
  return true;
}

// ---- 1. Account page (console.js) ----
const accStart = consoleJs.indexOf("async function renderAccount(");
const accEnd = consoleJs.indexOf("// ---- Security tab", accStart);
const acc = consoleJs.slice(accStart, accEnd);
check("console.js: renderAccount found", accStart > 0 && accEnd > accStart);
check("Account page: confirm box #acPass2 is a password field",
  /id="acPass2" type="password" autocomplete="new-password"/.test(acc));
check("Account page: the confirm box sits right after the new-password box",
  acc.indexOf('id="acPass"') > 0 && acc.indexOf('id="acPass2"') > acc.indexOf('id="acPass"')
  && acc.indexOf('id="acPass2"') < acc.indexOf('id="acSave"'));
check("Account page: confirm label switches with set / change",
  /cs\.ac_new_pw2/.test(acc) && /cs\.ac_pw2"/.test(acc));
const accSave = acc.slice(acc.indexOf('getElementById("acSave").onclick'));
check("Account page: handler reads the confirm box",
  /const pass2 = document\.getElementById\("acPass2"\)\.value/.test(accSave));
check("Account page: change compares the two before /auth/password",
  comparedBeforeEachFetch(accSave, "/auth/password"));
check("Account page: first set compares the two before /auth/setup",
  accSave.lastIndexOf("pass !== pass2", accSave.indexOf('fetch("/auth/setup"'))
    > accSave.indexOf('fetch("/auth/password"'));
check("Account page: mismatch shows its own message",
  (accSave.match(/cs\.ac_pw_mismatch/g) || []).length >= 2);
check("Account page: confirm box is cleared after a successful change",
  /getElementById\("acPass2"\)\.value = ""/.test(accSave));

// ---- 2. Settings block (index.html + app.js) ----
const quick = html.slice(html.indexOf('id="quickSet"'));
const iPass = quick.indexOf('id="setAuthPass"');
const iPass2 = quick.indexOf('id="setAuthPass2"');
check("Settings block: confirm box #setAuthPass2 exists", iPass2 > 0);
check("Settings block: it sits after #setAuthPass and before the save button",
  iPass > 0 && iPass2 > iPass && iPass2 < quick.indexOf('id="savePassword"'));
check("Settings block: it is a password field with i18n label and placeholder",
  /<label data-i18n="setm\.pass2">[^<]+<\/label><input id="setAuthPass2" type="password" autocomplete="new-password"[^>]*data-i18n-ph="setm\.pass2_ph"/.test(quick));
const setStart = appJs.indexOf('getElementById("savePassword").addEventListener');
const setEnd = appJs.indexOf('getElementById("logoutBtn")', setStart);
const setSave = appJs.slice(setStart, setEnd);
check("app.js: savePassword handler found", setStart > 0 && setEnd > setStart);
check("Settings block: handler reads the confirm box",
  /getElementById\("setAuthPass2"\)/.test(setSave));
check("Settings block: change compares the two before /auth/password",
  comparedBeforeEachFetch(setSave, "/auth/password"));
check("Settings block: first set compares the two before /auth/setup",
  comparedBeforeEachFetch(setSave, "/auth/setup"));
check("Settings block: mismatch shows its own message",
  (setSave.match(/app\.pw_mismatch/g) || []).length >= 2);
check("Settings block: confirm box is cleared after saving",
  (setSave.match(/pass2El\.value = ""/g) || []).length >= 2);

// ---- 3. Words on screen, in both languages ----
for (const k of ["setm.pass2", "setm.pass2_ph", "app.pw_mismatch",
  "cs.ac_new_pw2", "cs.ac_pw2", "cs.ac_pw2_ph", "cs.ac_pw_mismatch"]) {
  check(`i18n: ${k} in vi.json and en.json`, !!VI[k] && !!EN[k]);
}
check("i18n: the Vietnamese confirm label says 'Nhập lại'", /^Nhập lại/.test(VI["cs.ac_new_pw2"] || ""));
check("i18n: the mismatch message says 'không khớp'", /không khớp/.test(VI["cs.ac_pw_mismatch"] || ""));

if (fails.length) {
  console.log(`\n${fails.length} check(s) failed`);
  process.exit(1);
}
console.log("\nall ok");
