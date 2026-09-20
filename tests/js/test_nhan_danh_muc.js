/* Nhãn danh mục / nhóm phải đổi theo ngôn ngữ giao diện (0.59.50).

       node tests/js/test_nhan_danh_muc.js

   Rà giao diện 20/09 thấy ba chỗ vẫn hiện tiếng Việt khi đã chọn tiếng Anh: chip lọc danh mục
   ở trang Kết nối ("Văn phòng", "Nhắn tin"...), cột nhóm bên trái Javis Store, và nhóm "Khác"
   trên thanh bên. Cả ba đều lấy chữ TỪ DỮ LIỆU (catalog, kho gói) chứ không qua từ điển, và
   chữ đó đồng thời là KHOÁ lọc nên không đổi ở nguồn được.

   Cách sửa: `JavisI18n.catLabel(raw)` tra ngược từ điển gốc - khoá `cat.*` nào có bản tiếng
   Việt bằng đúng tên gốc thì lấy bản dịch của khoá đó. Test này NẠP THẬT i18n/index.js với
   window và fetch giả, đọc đúng hai file từ điển trên đĩa, rồi gọi hàm ở cả hai ngôn ngữ. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

const TU_DIEN = {
  vi: JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/vi.json"), "utf8")),
  en: JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/en.json"), "utf8")),
};

// window / document / fetch giả vừa đủ cho index.js khởi động.
let _luu = "";
global.localStorage = { getItem: () => _luu, setItem: (k, v) => { _luu = v; } };
global.document = {
  documentElement: { setAttribute() {} },
  querySelectorAll: () => [],
};
global.window = { addEventListener() {}, dispatchEvent() {} };
global.CustomEvent = function () {};
global.fetch = (url) => {
  const m = /\/static\/i18n\/(\w+)\.json/.exec(String(url));
  const d = m && TU_DIEN[m[1]];
  return Promise.resolve({ ok: !!d, json: () => Promise.resolve(d || {}) });
};

(async () => {
  require(path.join(ROOT, "dashboard/i18n/index.js"));
  const I = global.window.JavisI18n;
  check("index.js export catLabel", I && typeof I.catLabel === "function");
  await I.init("vi");
  check("vi: 'Văn phòng' giữ nguyên", I.catLabel("Văn phòng") === "Văn phòng", I.catLabel("Văn phòng"));
  check("vi: mã máy 'ban-hang' của kho hiện thành chữ", I.catLabel("ban-hang") === "Bán hàng", I.catLabel("ban-hang"));
  check("vi: tên lạ giữ nguyên", I.catLabel("Nhóm tự đặt") === "Nhóm tự đặt");
  check("rỗng ra rỗng", I.catLabel("") === "" && I.catLabel(null) === "");

  await I.setLang("en");
  check("en: 'Văn phòng' -> Office", I.catLabel("Văn phòng") === "Office", I.catLabel("Văn phòng"));
  check("en: 'Khác' -> Other", I.catLabel("Khác") === "Other", I.catLabel("Khác"));
  check("en: 'Nhắn tin' -> Messaging", I.catLabel("Nhắn tin") === "Messaging", I.catLabel("Nhắn tin"));
  check("en: 'ban-hang' -> Sales", I.catLabel("ban-hang") === "Sales", I.catLabel("ban-hang"));
  check("en: tên lạ vẫn giữ nguyên", I.catLabel("Nhóm tự đặt") === "Nhóm tự đặt");
  check("en: nhóm 'Khác' trên thanh bên có bản dịch", I.t("nav.group.khac") === "Other", I.t("nav.group.khac"));
  check("en: lời nhắc .dmg của Ollama có bản dịch", /dmg/.test(I.t("ol.mac_hint")) && !/hoặc/.test(I.t("ol.mac_hint")));

  // Mọi tên danh mục đang có trong catalog và kho đi kèm app đều phải dịch được, để không
  // lọt một chip tiếng Việt nào giữa trang tiếng Anh.
  const cat = JSON.parse(fs.readFileSync(path.join(ROOT, "system/mcp-catalog.json"), "utf8"));
  const ds = Array.isArray(cat) ? cat : (cat.connectors || Object.values(cat)[0] || []);
  const ten = new Set(ds.map((c) => c && c.category).filter(Boolean));
  const conVi = [...ten].filter((x) => I.catLabel(x) === x && /[ăâđêôơư]/i.test(x));
  check("mọi danh mục trong mcp-catalog.json đều có bản tiếng Anh", conVi.length === 0, conVi.join(", "));

  console.log("");
  if (fails.length) { console.log("THẤT BẠI " + fails.length + " mục"); process.exit(1); }
  console.log("OK - test_nhan_danh_muc: tất cả pass");
})().catch((e) => { console.log("FAIL " + (e && e.stack || e)); process.exit(1); });
