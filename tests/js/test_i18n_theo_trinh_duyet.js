/* Giao diện theo ngôn ngữ trình duyệt khi chưa ai chọn (0.66.0).

    python tests/run.py i18n_theo_trinh_duyet

   Từ 0.66.0 Javis lấy tiếng Anh làm mặt tiền: người lạ mở dashboard lần đầu phải thấy ngôn
   ngữ của trình duyệt họ (có từ điển thì dùng, không thì tiếng Anh), chứ không phải tiếng Việt.

   Ba chỗ dễ hỏng mà test này canh:
     1. Người dùng Việt CŨ có trình duyệt để tiếng Anh bị đổi ngôn ngữ trong im lặng. Chặn ở
        console.js: máy chưa chọn thì `ui_lang` đã lưu trên server thắng phần đoán.
     2. Lượt init() đoán trình duyệt (bất đồng bộ, chậm) về SAU lượt init("vi") rồi ghi đè nó.
     3. Thứ tiếng thứ ba dịch dở rơi thẳng về tiếng Việt, thứ người đọc không hiểu.

   NẠP THẬT i18n/index.js với window, navigator, fetch giả, đọc từ điển thật trên đĩa. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const INDEX = path.join(ROOT, "dashboard/i18n/index.js");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/en.json"), "utf8"));

// Một khoá có ở cả hai bản và hai bản khác nhau, để biết chữ đến từ từ điển nào.
const KHOA = Object.keys(VI).find((k) => k in EN && VI[k] !== EN[k] && !/[{}]/.test(VI[k]));

/* Dựng môi trường mới rồi nạp lại index.js. `tuDien` quyết định file nào "có trên server". */
function nap({ trinhDuyet = [], luu = "", tuDien = { vi: VI, en: EN }, treVi = 0 } = {}) {
  const kho = { v: luu };
  global.localStorage = { getItem: () => kho.v, setItem: (k, v) => { kho.v = v; } };
  global.document = { documentElement: { setAttribute() {} }, querySelectorAll: () => [] };
  global.window = { addEventListener() {}, dispatchEvent() {} };
  global.CustomEvent = function () {};
  // Node 21+ có sẵn `navigator` dạng getter chỉ đọc (language luôn "en-US"): gán thẳng thì
  // im lặng không ăn, nên phải định nghĩa lại.
  Object.defineProperty(global, "navigator", {
    value: { languages: trinhDuyet, language: trinhDuyet[0] || "" },
    configurable: true, writable: true,
  });
  global.fetch = (url) => {
    const m = /\/static\/i18n\/(\w+)\.json/.exec(String(url));
    const d = m && tuDien[m[1]];
    const tra = { ok: !!d, json: () => Promise.resolve(d || {}) };
    // Cho một file về chậm để tái hiện hai lượt init chồng nhau.
    if (m && m[1] === "vi" && treVi) return new Promise((r) => setTimeout(() => r(tra), treVi));
    return Promise.resolve(tra);
  };
  delete require.cache[require.resolve(INDEX)];
  require(INDEX);
  return { I: global.window.JavisI18n, kho };
}
const cho = (ms = 30) => new Promise((r) => setTimeout(r, ms));

(async () => {
  check("tìm được một khoá khác nhau giữa vi và en để làm mốc", !!KHOA);

  // ---- 1. Chưa chọn: theo trình duyệt ----
  let { I, kho } = nap({ trinhDuyet: ["vi-VN", "en-US"] });
  await cho();
  check("trình duyệt vi-VN -> giao diện tiếng Việt", I.lang() === "vi", I.lang());
  check("đoán từ trình duyệt thì daChon() = false", I.daChon() === false);
  check("đoán thì KHÔNG ghi localStorage (chưa phải lựa chọn)", kho.v === "");

  ({ I } = nap({ trinhDuyet: ["en-GB"] }));
  await cho();
  check("trình duyệt en-GB -> tiếng Anh", I.lang() === "en", I.lang());
  check("tiếng Anh thì chữ ra đúng bản tiếng Anh", I.t(KHOA) === EN[KHOA], I.t(KHOA));

  ({ I } = nap({ trinhDuyet: ["fr-FR", "de"] }));
  await cho();
  check("trình duyệt không có từ điển nào -> tiếng Anh, không phải tiếng Việt", I.lang() === "en", I.lang());

  ({ I } = nap({ trinhDuyet: ["ja", "vi"] }));
  await cho();
  check("bỏ qua thứ tiếng chưa có, lấy cái kế tiếp có từ điển", I.lang() === "vi", I.lang());

  ({ I } = nap({ trinhDuyet: [] }));
  await cho();
  check("không biết gì về trình duyệt -> tiếng Anh", I.lang() === "en", I.lang());

  // ---- 2. Đã chọn thì giữ, bất kể trình duyệt ----
  ({ I } = nap({ trinhDuyet: ["en-US"], luu: "vi" }));
  await cho();
  check("đã lưu vi trên máy -> vẫn tiếng Việt dù trình duyệt tiếng Anh", I.lang() === "vi", I.lang());
  check("đã lưu thì daChon() = true", I.daChon() === true);

  // Chọn đúng ngôn ngữ đang đoán: vẫn phải ghi lại thành lựa chọn.
  ({ I, kho } = nap({ trinhDuyet: ["en-US"] }));
  await cho();
  await I.setLang("en");
  check("chọn đúng ngôn ngữ đang đoán -> ghi localStorage", kho.v === "en", kho.v);
  check("... và daChon() thành true", I.daChon() === true);

  // ---- 3. Suy biến: thứ tiếng thứ ba -> en -> vi -> khoá ----
  const xx = { [KHOA]: "XX!" };
  const chiVi = Object.keys(VI).find((k) => !(k in EN));   // thường là không có
  ({ I } = nap({ trinhDuyet: ["xx"], tuDien: { vi: VI, en: EN, xx } }));
  await cho();
  check("trình duyệt xx có từ điển xx.json -> chọn xx", I.lang() === "xx", I.lang());
  check("khoá có trong xx dùng bản xx", I.t(KHOA) === "XX!", I.t(KHOA));
  const khac = Object.keys(EN).find((k) => k !== KHOA && VI[k] !== EN[k] && !/[{}]/.test(EN[k]));
  check("khoá xx chưa dịch rơi về TIẾNG ANH, không phải tiếng Việt", I.t(khac) === EN[khac], I.t(khac));
  if (chiVi) check("khoá chỉ có ở vi vẫn ra chữ, không ra mã khoá", I.t(chiVi) === VI[chiVi]);
  check("khoá không tồn tại ở đâu thì trả chính khoá", I.t("khong.ton.tai") === "khong.ton.tai");

  // ---- 4. Hai lượt init chồng nhau: lượt mới nhất thắng ----
  ({ I } = nap({ trinhDuyet: ["en-US"], treVi: 40 }));
  await I.init("vi");      // lượt init() tự chạy lúc nạp file (đoán en) còn đang bay
  await cho(80);
  check("init('vi') gọi sau không bị lượt đoán trình duyệt ghi đè", I.lang() === "vi", I.lang());
  check("... và chữ là tiếng Việt", I.t(KHOA) === VI[KHOA], I.t(KHOA));

  delete global.window;

  // ---- 5. Hai mảnh còn lại của cơ chế nằm ngoài index.js ----
  const con = fs.readFileSync(path.join(ROOT, "dashboard/console.js"), "utf8");
  check("console.js: máy chưa chọn thì áp ui_lang của server (giữ người dùng cũ)",
        /!I\.daChon\(\)/.test(con) && /s\.locale && s\.locale\.ui_lang/.test(con) && /await I\.setLang\(srv\)/.test(con));
  check("console.js: server chưa có ui_lang thì ghi ngôn ngữ vừa đoán lên",
        /saveSetting\("locale", \{ ui_lang: I\.lang\(\) \}\)/.test(con));
  const cfg = fs.readFileSync(path.join(ROOT, "server/config.py"), "utf8");
  check("config.py: ui_lang mặc định rỗng cho bản cài mới", /"ui_lang": "",/.test(cfg));

  console.log("");
  if (fails.length) { console.log("THẤT BẠI " + fails.length + " mục"); process.exit(1); }
  console.log("OK - test_i18n_theo_trinh_duyet: tất cả pass");
})().catch((e) => { console.log("FAIL " + (e && e.stack || e)); process.exit(1); });
