/* Login vault page (0.251.0, dashboard/login-vault.js).

       node tests/js/test_login_vault_ui.js

   Runs the real render helpers: a card says status and expiry in words, escapes what the owner typed,
   never has a cookie field to show, and the page is wired into the sidebar, the voice command list
   and the page watch form. */
const fs = require("fs");
const path = require("path");

const D = (f) => fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", f), "utf8");
const R = (f) => fs.readFileSync(path.join(__dirname, "..", "..", f), "utf8");
const VI = JSON.parse(D("i18n/vi.json"));
const EN = JSON.parse(D("i18n/en.json"));

global.window = { t: (k, v) => (VI[k] || k).replace(/\{(\w+)\}/g, (m, n) => (v && n in v ? String(v[n]) : m)), ic: (n) => "<i:" + n + ">" };
const LV = require("../../dashboard/login-vault.js");

const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

const NOW = 1_800_000_000;
const base = { id: "lg_1", name: "Shopee <b>", domains: ["shopee.vn", "banhang.shopee.vn"], count: 12, allow_ai: true,
  status: "ok", status_note: "", uses: 3, used_at: NOW - 60, expires_at: NOW + 40 * 86400, expired: false };

let h = LV.cardHtml(base, NOW);
check("card escapes the name", h.includes("Shopee &lt;b&gt;") && !h.includes("Shopee <b>"));
check("card shows the status in words", h.includes("Còn đăng nhập") && h.includes('class="lv-st ok"'));
check("card shows the domains", h.includes("<span>shopee.vn</span>"));
check("card shows how many cookies, not their values", h.includes("12 cookie") && !/value|SPC_/i.test(h));
check("switch is on when Javis may use it", /data-act="toggle" checked/.test(h));
check("card has Check, Update and more", h.includes('data-act="check"') && h.includes('data-act="replace"') && h.includes('data-act="more"'));

h = LV.cardHtml(Object.assign({}, base, { allow_ai: false, status: "signed_out", status_note: "Trang chuyển về màn đăng nhập" }), NOW);
check("switched-off card is dimmed", h.includes('class="lv-card off"'));
check("expired status shows red and the reason", h.includes('class="lv-st bad"') && h.includes("Trang chuyển về màn đăng nhập"));

check("expiry: plain date", LV.expiryText(base, NOW).startsWith("Hạn tới"));
check("expiry: soon", LV.expiryText(Object.assign({}, base, { expires_at: NOW + 3 * 86400 }), NOW) === "Còn 3 ngày");
check("expiry: past", LV.expiryText(Object.assign({}, base, { expires_at: NOW - 10 }), NOW) === "Cookie đã quá hạn");
check("expiry: session cookies", LV.expiryText(Object.assign({}, base, { expires_at: 0 }), NOW).includes("theo phiên"));

check("site field only for a bare header", LV.needsSite("a=1; b=2") && !LV.needsSite("[{}]") && !LV.needsSite("{}")
  && !LV.needsSite(".x.com\tTRUE\t/") && !LV.needsSite(""));
const form = LV.pasteFormHtml(true);
check("add form asks name, cookies, site and test page", ["name", "text", "site", "test_url", "save", "cancel"].every((f) => form.includes('data-f="' + f + '"')));
const intro = LV.introHtml();
check("(i) text explains export, safety and the IP caveat", intro.includes("Cookie-Editor") && intro.includes("mã hoá") && intro.includes("VPS"));
check("update form has no name field", !LV.pasteFormHtml(false).includes('data-f="name"'));

// 2026-11-21: Javis can click and fill forms with a sign-in (Playwright browser). Owner: "khi add cookies nhớ cảnh báo
// người dùng có thể chịu rủi ro". The add form says the risk in the open, before Save, and each card has its own switch.
check("add form states the risk before the Save button", form.includes('class="lv-risk"')
  && form.indexOf('class="lv-risk"') < form.indexOf('data-f="save"') && form.includes(VI["lv.risk"]));
check("the risk line fits in the open, its detail sits behind (i)", VI["lv.risk"].length <= 100 && EN["lv.risk"].length <= 100
  && ["lv.risk_key", "lv.risk_act", "lv.risk_inject", "lv.risk_seen", "lv.risk_lock", "lv.risk_own"].every((k) => LV.riskHtml().includes(VI[k]))
  && /infoPair\(riskMoreHtml\(\), tw\("lv\.risk_more"\)\)/.test(D("login-vault.js")));
check("the risk says who carries it and that Javis acts for real", /tự chịu/.test(VI["lv.risk"]) && /risk is yours/.test(EN["lv.risk"])
  && /không hoàn tác/.test(VI["lv.risk_act_h"]) && /khoá tài khoản/.test(VI["lv.risk_lock"])
  && /tài khoản riêng cho Javis/.test(VI["lv.risk_key"]));
check("update form does not repeat the risk", !LV.pasteFormHtml(false).includes("lv-risk"));
h = LV.cardHtml(Object.assign({}, base, { allow_act: true, in_browser: true }), NOW);
check("card has a second switch for clicking and filling forms", /data-act="toggle-act" checked/.test(h) && h.includes("Cho bấm và điền form"));
check("card says when the sign-in sits in Javis's browser", h.includes(VI["lv.in_browser"]));
h = LV.cardHtml(Object.assign({}, base, { allow_act: false }), NOW);
check("a sign-in stored as read-only shows the act switch off", /data-act="toggle-act">/.test(h) && !h.includes(VI["lv.in_browser"]));
h = LV.cardHtml(Object.assign({}, base, { allow_ai: false, allow_act: true }), NOW);
check("act switch is disabled while the sign-in itself is off", /class="lv-allow dis"><input type="checkbox" data-act="toggle-act" checked disabled>/.test(h));
check("turning the act switch on asks the owner to confirm the risk", /this\.checked && !confirm\(tw\("lv\.act_q"/.test(D("login-vault.js"))
  && /tự chịu/.test(VI["lv.act_q"]));
check("a session left in the browser is reported after switching off", /if \(r\.warning\) alert\(r\.warning\)/.test(D("login-vault.js")));
check("(i) text no longer promises read-only", !/chỉ đọc trang/.test(VI["lv.intro_note"]) && /Playwright/.test(VI["lv.intro_note"])
  && /Playwright/.test(EN["lv.intro_note"]));
check("both forms can take a cookie file", [true, false].every((w) => { const f = LV.pasteFormHtml(w);
  return f.includes('data-f="file"') && /type="file" data-f="filein" accept="[^"]*\.json[^"]*\.txt/.test(f); }));
check("file name suggests the entry name", LV.nameFromFile("shopee.vn.json") === "shopee.vn"
  && LV.nameFromFile("C:\\dl\\banhang.shopee.vn_cookies.txt") === "banhang.shopee.vn" && LV.nameFromFile("Shopee (2).txt") === "Shopee");
check("generic export names leave the name to the server", ["cookies.txt", "cookies (1).txt", "export.json", "cookie-editor.json"]
  .every((n) => LV.nameFromFile(n) === ""));
const lvSrc = D("login-vault.js");
check("page has an Upload file button wired to the picker", lvSrc.includes('class="s-btn-ghost lv-upload"') && /q\("\.lv-upload"\)\.onclick/.test(lvSrc));
check("upload refuses files over 1 MB", /MAX_FILE = 1024 \* 1024/.test(lvSrc) && /file\.size > MAX_FILE/.test(lvSrc));

const cons = D("console.js");
check("sidebar: Connections group has logins", /ids: \["mcp", "packs", "channels", "logins"\]/.test(cons));
// Owner, 2026-10-28: choosing the brain is Javis's own setting, not an outside connection: Models sits under System.
check("sidebar: Models is in the System group", /ids: \["models", "settings", "share", "account"\], foot: true/.test(cons));
check("sidebar: logins has the cookie icon", /logins: "cookie"/.test(cons));
check("page is called Cookies in both languages", VI["page.logins.label"] === "Cookies" && EN["page.logins.label"] === "Cookies");
check("cookie and file-up icons are vendored", /"cookie":/.test(D("vendor/lucide-icons.js")) && /"file-up":/.test(D("vendor/lucide-icons.js")));
check("page delegates to login-vault.js", /id === "logins"[\s\S]{0,200}JavisLoginVault\.mount\(el\)/.test(cons));
check("voice commands know the page", /"logins", "pet", "share"\]/.test(D("ui-actions.js")) && /"logins", "pet", "share",/.test(R("server/ui_targets.py")));
check("index.html loads the module", /login-vault\.js\?v=\d+/.test(D("index.html")));
const ww = D("web-watch.js");
check("watch form offers a sign-in", ww.includes('id="wwLogin"') && ww.includes("login_id:"));
check("watch form lists only sign-ins Javis may use", /filter\(function \(x\) \{ return x\.allow_ai; \}\)/.test(ww));

const keys = Object.keys(VI).filter((k) => k.startsWith("lv.") || k.startsWith("page.logins."));
check("every lv key exists in English", keys.length > 30 && keys.every((k) => EN[k]));
check("no long dashes in the new text", keys.every((k) => !/[–—]/.test(VI[k] + EN[k])));

if (fails.length) { console.log("\nFAIL - test_login_vault_ui: " + fails.length); process.exit(1); }
console.log("\nOK - test_login_vault_ui");
