/* Trang Cộng sự không được kẹt nhãn ở dạng mã khoá (`ws.tab_agent`, `sess.new_chat`...).

       node tests/js/test_cong_su_nhan_tho.js

   Chủ dự án báo 30/09/2026 kèm ảnh chụp: "thi thoảng load lại phiên bản mới là các nút trên trang
   bị mất" - các nút vẫn còn đó nhưng nhãn là `ws.tab_agent`, `ws.tab_workflow`, `ws.files_links`,
   `sess.new_chat`, `ws.tab_history`, `sess.tab_files`, `ws.tab_settings`.

   Gốc: console.js khôi phục trang cuối (Trò chuyện hoặc Cộng sự) NGAY lúc khởi động, còn từ điển
   i18n được nạp bất đồng bộ (i18n/index.js). Từ điển về chậm hơn một nhịp (máy vừa cập nhật, server
   vừa khởi động lại, mạng chậm) thì workspace.js dựng khung bằng t() trong lúc từ điển còn rỗng, và
   t() trả về chính cái khoá. Trang Trò chuyện không dính vì nó dùng `data-i18n` + nghe "javis:i18n";
   workspace.js không có cả hai nên nhãn kẹt mãi, dù phần danh sách vẽ sau (sau khi tải dữ liệu, lúc
   từ điển đã về) vẫn ra chữ đúng - đó là lý do ảnh chụp trông "nửa Việt nửa mã khoá".

   Tái hiện thật: làm chậm /static/i18n/vi.json 1,5 giây rồi mở lại trang Cộng sự; 4,7 giây sau nhãn
   vẫn là mã khoá.

   Cách sửa: workspace.js nhớ "khung này dựng khi từ điển chưa sẵn sàng", console.js nghe
   "javis:i18n" và dựng lại trang Cộng sự đúng một lần khi từ điển về. Dựng lại tại chỗ là đường đã
   có sẵn (đổi brain cũng gọi renderPage thẳng), nên không thêm đường mới. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const doc = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const WS = doc("workspace.js"), CON = doc("console.js"), APP = doc("app.js");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ---- 1. workspace.js nhớ khung dựng khi chưa có từ điển (chạy thật, DOM giả) ----
// Phần tử giả nhận mọi thuộc tính và mọi lời gọi: render() có thể ngã ở giữa vì DOM giả thiếu chỗ
// này chỗ kia, nhưng cờ phải được đặt TRƯỚC khi nó chạm tới DOM nên test vẫn đo được.
function phanTuGia() {
  const p = new Proxy(function () {}, {
    get: (t, k) => (k === Symbol.toPrimitive ? () => "" : k === "length" ? 0 : k === "classList" ? { add() {}, remove() {}, toggle() {}, contains: () => false } : p),
    set: () => true,
    apply: () => p,
  });
  return p;
}
function dungVoi(tuDienSan) {
  const ctx = {
    console,
    window: { t: (k) => k, ic: () => "", addEventListener() {}, removeEventListener() {},
              matchMedia: () => ({ matches: false }),
              JavisI18n: { ready: () => tuDienSan } },
    document: { getElementById: () => null, createElement: () => phanTuGia(), body: { classList: { add() {}, remove() {}, toggle() {} } },
                addEventListener() {}, removeEventListener() {}, querySelector: () => null, querySelectorAll: () => [] },
    localStorage: { getItem: () => null, setItem() {} },
    setTimeout, clearTimeout, Promise, Date, Math, JSON, Object, Array, String, Number, RegExp, Error,
  };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(WS, ctx);
  const W = ctx.window.JavisWorkspace;
  try { W.render(phanTuGia(), {}); } catch (e) { /* DOM giả không đủ để dựng hết, không sao */ }
  return W;
}
{
  const W1 = dungVoi(false);
  check("workspace.js phơi dungKhiChuaCoTuDien()", typeof W1.dungKhiChuaCoTuDien === "function");
  check("dựng lúc từ điển CHƯA về thì ghi nhận (để dựng lại khi từ điển về)",
    typeof W1.dungKhiChuaCoTuDien === "function" && W1.dungKhiChuaCoTuDien() === true);
  const W2 = dungVoi(true);
  check("dựng lúc từ điển đã về thì KHÔNG đòi dựng lại (khỏi dựng lại vô ích mỗi lần vào trang)",
    typeof W2.dungKhiChuaCoTuDien === "function" && W2.dungKhiChuaCoTuDien() === false);
  // Không có JavisI18n (trang lỗi tải) thì đừng đòi dựng lại: không bao giờ có sự kiện để gọi.
  const ctx3 = { console, window: { t: (k) => k, ic: () => "", addEventListener() {}, removeEventListener() {}, matchMedia: () => ({ matches: false }) },
                 document: { getElementById: () => null, createElement: () => phanTuGia(), body: { classList: { add() {}, remove() {}, toggle() {} } }, addEventListener() {}, querySelector: () => null, querySelectorAll: () => [] },
                 localStorage: { getItem: () => null, setItem() {} }, setTimeout, clearTimeout, Promise, Date, Math, JSON, Object, Array, String, Number, RegExp, Error };
  ctx3.globalThis = ctx3; vm.createContext(ctx3); vm.runInContext(WS, ctx3);
  try { ctx3.window.JavisWorkspace.render(phanTuGia(), {}); } catch (e) { /* như trên */ }
  check("thiếu JavisI18n thì không đòi dựng lại", ctx3.window.JavisWorkspace.dungKhiChuaCoTuDien && ctx3.window.JavisWorkspace.dungKhiChuaCoTuDien() === false);
}

// ---- 2. console.js dựng lại trang Cộng sự khi từ điển về ----
const i = CON.indexOf('window.addEventListener("javis:i18n", () => {');
const NGHE = i === -1 ? "" : CON.slice(i, CON.indexOf("\n  });", i));
check("tìm thấy bộ nghe javis:i18n của console.js", NGHE.length > 0);
check("bộ nghe hỏi workspace.js xem khung có dựng khi chưa có từ điển không",
  /JavisWorkspace\.dungKhiChuaCoTuDien\(\)/.test(NGHE));
check("chỉ dựng lại khi đang đứng ở trang Cộng sự",
  /\.active === "workspace"/.test(NGHE));
check("dựng lại bằng renderPage (đường tại chỗ đã có, giống lúc đổi brain)",
  /renderPage\("workspace"\)/.test(NGHE));
// Lỗi ở đây không được làm hỏng phần còn lại của bộ nghe (đổi ô ngôn ngữ, quét nhãn tĩnh).
const iw = NGHE.indexOf("dungKhiChuaCoTuDien");
check("nằm trong try/catch riêng để không chặn phần quét nhãn tĩnh phía sau",
  iw !== -1 && /try \{[^]*dungKhiChuaCoTuDien[^]*\} catch/.test(NGHE) && NGHE.indexOf("applyDom") > iw);

// ---- 3. Số note/liên kết ở thanh trên (app.graph_stats) cũng không được kẹt ở mã khoá ----
// Cùng gốc: số liệu đồ thị về trước từ điển thì t() trả về chính khoá. Thấy trong lúc tái hiện.
check("chỉ còn đúng hai chỗ ghi app.graph_stats vào graphStats: veGraphStats và bộ nghe i18n",
  (APP.match(/graphStats\.textContent = window\.t\("app\.graph_stats"/g) || []).length === 2);
check("veGraphStats nhớ số cuối", /function veGraphStats\(n, l\) \{\s*_graphStatsCuoi = \{ n: n, l: l \};/.test(APP));
check("cả hai đường cập nhật (tải đồ thị, note mới sinh) đều đi qua veGraphStats",
  /veGraphStats\(stats\.total_notes, stats\.total_links\)/.test(APP) && /veGraphStats\(s\.nodes, s\.links\)/.test(APP));
check("nghe javis:i18n để vẽ lại số đã nhớ",
  /addEventListener\("javis:i18n", \(\) => \{\s*if \(_graphStatsCuoi\) graphStats\.textContent = window\.t\("app\.graph_stats", _graphStatsCuoi\);/.test(APP));
check("tải đồ thị lỗi thì xoá số đã nhớ (chuỗi lỗi không bị vẽ đè khi từ điển về)",
  /catch \(e\) \{ _graphStatsCuoi = null; graphStats\.textContent = window\.t\("models\.err"\)/.test(APP));

// ---- 4. Không dùng em dash (luật CLAUDE.md) ----
check("không dùng em dash trong file test này", !fs.readFileSync(__filename, "utf8").includes(String.fromCharCode(0x2014)));

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_cong_su_nhan_tho: tất cả pass");
