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
check("both forms can take a cookie file", [true, false].every((w) => { const f = LV.pasteFormHtml(w);
  return f.includes('data-f="file"') && /type="file" data-f="filein" accept="[^"]*\.json[^"]*\.txt/.test(f); }));
check("file name suggests the entry name", LV.nameFromFile("shopee.vn.json") === "shopee.vn"
  && LV.nameFromFile("C:\\dl\\banhang.shopee.vn_cookies.txt") === "banhang.shopee.vn" && LV.nameFromFile("Shopee (2).txt") === "Shopee");
check("generic export names leave the name to the server", ["cookies.txt", "cookies (1).txt", "export.json", "cookie-editor.json"]
  .every((n) => LV.nameFromFile(n) === ""));
const lvSrc = D("login-vault.js");
check("page has an Upload file button wired to the picker", lvSrc.includes('class="s-btn-ghost lv-upload"') && /q\("\.lv-upload"\)\.onclick/.test(lvSrc));
check("upload refuses files over 1 MB", /MAX_FILE = 1024 \* 1024/.test(lvSrc) && /file\.size > MAX_FILE/.test(lvSrc));

// Operate controls (can_act, approval) and the "waiting for you" panel.
h = LV.cardHtml(Object.assign({}, base, { can_act: true, approval: "ask" }), NOW);
check("card has the operate switch, on", /data-act="canact" checked/.test(h) && h.includes("Cho agent thao tác"));
check("card approval select defaults to Ask me", /<option data-v="ask" selected>Hỏi tôi/.test(h) && /<option data-v="auto">Tự động/.test(h));
h = LV.cardHtml(Object.assign({}, base, { can_act: false, approval: "auto" }), NOW);
check("operate switch off and approval auto are shown", !/data-act="canact" checked/.test(h) && /<option data-v="auto" selected>/.test(h));
check("old server view without the fields still renders as operate on, ask", /data-act="canact" checked/.test(LV.cardHtml(base, NOW))
  && /<option data-v="ask" selected>/.test(LV.cardHtml(base, NOW)));
check("no pending approvals draws nothing", LV.approvalsHtml([]) === "" && LV.approvalsHtml(null) === "");
const pend = LV.approvalsHtml([{ id: "ap_1", summary: "Shopee · https://x.vn/ · bấm <img src=x onerror=1>" }, { id: "ap_2", summary: "Lazada" }]);
check("pending panel counts them and escapes the summary", pend.includes("Chờ bạn duyệt (2)") && !pend.includes("<img") && pend.includes("&lt;img"));
check("each pending row has once, always and deny", ["once", "always", "deny"].every((d) => (pend.match(new RegExp('data-d="' + d + '"', "g")) || []).length === 2)
  && pend.includes("Duyệt lần này") && pend.includes("Duyệt toàn quyền") && pend.includes("Từ chối"));
check("page polls approvals and posts decisions", /api\("\/logins\/approvals"\)/.test(lvSrc) && /\/logins\/approvals\/decide/.test(lvSrc));

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
