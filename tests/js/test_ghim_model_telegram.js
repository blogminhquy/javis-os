/* Khối "Model Telegram" trên trang Models: mặc định theo model chính, ghim khi chọn.

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
check("có khối Model Telegram", /id="tgCard"/.test(CL));
check("khối nằm SAU khối việc nền (cùng họ 'model theo làn')", CL.indexOf('id="tgCard"') > CL.indexOf('id="auxChange"'));
check("chưa ghim thì hiện 'theo model chính', không hiện tên model như thể đã ghim",
  /tgPinned \? esc\(tgModel \|\| "-"\) : esc\(t\("models\.tg_follow"\)\)/.test(CL));
check("nút đổi khi chưa ghim ghi là GHIM, đã ghim thì là Đổi model",
  /tgPinned \? t\("models\.change_model"\) : t\("models\.tg_pin"\)/.test(CL));
check("CANARY: bỏ ghim ghi provider RỖNG", /telegram: \{ provider: "", model: "" \}/.test(CL));
check("ghim lưu đúng ô telegram", /telegram: \{ provider: prov, model: mod \}/.test(CL));
check("cảnh báo khi provider ghim chưa kết nối", /models\.tg_warn/.test(CL) && /tgReady/.test(CL));
for (const k of ["models.h_tg", "models.h_tg_sub", "models.tg_meta", "models.tg_follow", "models.tg_follow_sub",
                 "models.tg_pin", "models.tg_reset", "models.tg_warn", "models.tg_note", "models.tg_title", "models.tg_note2"]) {
  check("vi có " + k, !!VI[k]);
  check("en có " + k, !!EN[k]);
}
check("chữ nhắc /status vì điện thoại không có banner", /\/status/.test(VI["models.tg_note"] || ""));
console.log();
if (fails.length) { console.log("ĐỎ " + fails.length + " mục"); process.exit(1); }
console.log("Tất cả xanh.");
