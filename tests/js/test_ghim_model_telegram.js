/* Khối "Model Telegram" trên trang Models đã bỏ ở 0.351.0: Telegram theo MAIN, /model trong một chat ghim chat đó.

       node tests/js/test_ghim_model_telegram.js

   Đi kèm tests/python/test_ghim_model_telegram.py (phần server). Ở đây canh phần vẽ: khối
   phải nói rõ đang theo hay đang ghim, và bỏ ghim phải ghi provider RỖNG - ghi một provider
   mặc định vào đó là biến "theo model chính" thành một ghim ngầm. */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const JS = D("console.js");
const VI = JSON.parse(D(path.join("i18n", "vi.json")));
const EN = JSON.parse(D(path.join("i18n", "en.json")));
const fails = [];
const check = (name, cond, them) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
};
const i = JS.indexOf("async function renderModelsCloudTab(el)");
check("tìm được khung Cloud", i > 0);
const CL = JS.slice(i, JS.indexOf("\n  async function", i + 10) > 0 ? JS.indexOf("\n  async function", i + 10) : JS.length);
// 0.351.0 (docs/dev/2026-10-model-routing-spec.md 2.5, owner's call): the Models page has no Telegram box any more.
// Telegram follows MAIN; /model typed in a Telegram chat pins that chat only (server side, the .py twin of this test).
check("không còn khối Model Telegram", !/id="tgCard"/.test(CL) && !/tgPinned/.test(CL));
check("trang không còn ghi ô telegram nào", !/telegram: \{ provider:/.test(CL));
for (const k of ["models.h_tg", "models.tg_pin", "models.tg_reset", "models.tg_warn"]) {
  check("khoá cũ đã gỡ khỏi vi/en: " + k, !(k in VI) && !(k in EN));
}
console.log();
if (fails.length) { console.log("ĐỎ " + fails.length + " mục"); process.exit(1); }
console.log("Tất cả xanh.");
