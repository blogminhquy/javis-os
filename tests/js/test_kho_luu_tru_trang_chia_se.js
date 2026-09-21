/* Bản vá kho lưu trữ cho trang .html chia sẻ - CHẠY THẬT đoạn script đó, không soi chữ.
 *
 *       node tests/js/test_kho_luu_tru_trang_chia_se.js
 *
 * Đoạn script nằm trong `server/share_render.py` (POLYFILL_LUU_TRU) vì nó do máy chủ chèn vào
 * trang lúc phục vụ. Nhưng nó là JavaScript, và thứ đáng canh ở đây là HÀNH VI chứ không phải
 * sự có mặt của một chuỗi ký tự:
 *
 *   - Kho hỏng (gốc "null" trong hộp cách ly) thì phải thay bằng kho tạm ĐẦY ĐỦ. Thiếu một
 *     hàm như `key` hay `length` là thư viện nào đó duyệt kho sẽ nổ, và nổ đúng kiểu khó truy
 *     ra vì mọi thứ khác chạy bình thường.
 *   - Kho THẬT dùng được thì phải giữ nguyên. Vá đè lên kho thật là dữ liệu người dùng đã lưu
 *     bỗng biến mất sau một bản cập nhật, không một lời báo nào.
 *   - Lượt thăm dò không được để lại rác trong kho của người ta.
 *
 * Phần chèn vào đâu trong trang, và route /s/ có dùng nó không, do
 * tests/python/test_chia_se_kho_luu_tru.py canh. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const PY = fs.readFileSync(path.join(ROOT, "server", "share_render.py"), "utf8");

const fails = [];
const check = (ten, ok, them) => {
  console.log((ok ? "ok   " : "FAIL ") + ten + (ok || them === undefined ? "" : "  [" + them + "]"));
  if (!ok) fails.push(ten);
};

// Bóc đoạn script ra khỏi hằng Python. Canary ngay dưới: bóc hụt thì mọi phép thử sau đều
// chạy trên chuỗi rỗng và báo xanh mãi mãi.
const m = PY.match(/POLYFILL_LUU_TRU = """<script>[\s\S]*?\n([\s\S]*?)<\/script>\n"""/);
const JS = m ? m[1] : "";
check("bóc được đoạn script trong share_render.py", JS.length > 200, JS.length + " ký tự");
check("CANARY: đoạn bóc ra đúng là bản vá (có lượt thăm dò)", JS.includes("__javis_thu__"));

/** Chạy bản vá trong một `window` giả rồi trả lại chính window đó. */
function chay(window) {
  const ctx = vm.createContext({ window: window, Object: Object });
  ctx.globalThis = ctx;
  vm.runInContext(JS, ctx);
  return window;
}

// ============================================================
// 1. Kho HỎNG (gốc "null"): thay bằng kho tạm trong bộ nhớ
// ============================================================
const hong = {};
for (const ten of ["localStorage", "sessionStorage"]) {
  Object.defineProperty(hong, ten, {
    get() { throw new Error("SecurityError: Access is denied for this document"); },
    configurable: true,
  });
}
let nem = false;
try { void hong.localStorage; } catch (e) { nem = true; }
check("CANARY: window giả thật sự ném lỗi khi chạm vào kho", nem);

chay(hong);
let sauKhiVa = true;
try { void hong.localStorage; } catch (e) { sauKhiVa = false; }
check("vá xong thì chạm vào localStorage KHÔNG còn ném lỗi", sauKhiVa);
check("sessionStorage cũng được vá", (() => {
  try { return !!hong.sessionStorage; } catch (e) { return false; }
})());

const kho = hong.localStorage;
kho.setItem("tong", "toi");
kho.setItem("loc", "tuan-nay");
check("ghi rồi đọc lại đúng giá trị", kho.getItem("tong") === "toi");
check("khoá chưa có trả về null (không phải undefined)", kho.getItem("chua-co") === null);
check("length đếm đúng", kho.length === 2, kho.length);
check("key(i) trả về tên khoá", kho.key(0) === "tong" && kho.key(1) === "loc");
check("key ngoài phạm vi trả về null", kho.key(9) === null && kho.key(-1) === null);
kho.setItem("tong", "sang");
check("ghi đè không đẻ thêm khoá", kho.getItem("tong") === "sang" && kho.length === 2);
kho.setItem("so", 12);
check("giá trị luôn thành chuỗi (đúng như kho thật)", kho.getItem("so") === "12");
kho.removeItem("loc");   // còn lại "tong" và "so"
check("xoá được một khoá", kho.getItem("loc") === null && kho.length === 2, kho.length);
kho.clear();
check("clear dọn sạch", kho.length === 0 && kho.getItem("tong") === null);
// Hai kho phải TÁCH BIỆT: chung một túi thì đóng tab xong dữ liệu "phiên" vẫn còn lẫn sang.
hong.localStorage.setItem("chung", "a");
check("localStorage và sessionStorage là hai kho riêng",
      hong.sessionStorage.getItem("chung") === null);
// Kho thật không có prototype chung với Object nên `"toString" in kho` là false. Dùng một
// object thường làm túi chứa thì `getItem("toString")` trả về một HÀM - đủ để một đoạn mã
// vô tội nhận nhầm là dữ liệu đã lưu.
check("khoá lạ trùng tên thuộc tính của Object vẫn trả null",
      hong.localStorage.getItem("toString") === null
      && hong.localStorage.getItem("__proto__") === null);

// ============================================================
// 2. Kho THẬT dùng được: không đụng vào
// ============================================================
function khoThat() {
  const m2 = {};
  return {
    THAT: true,
    setItem(k, v) { m2[k] = String(v); },
    getItem(k) { return k in m2 ? m2[k] : null; },
    removeItem(k) { delete m2[k]; },
    _soKhoa() { return Object.keys(m2).length; },
  };
}
const tot = { localStorage: khoThat(), sessionStorage: khoThat() };
tot.localStorage.setItem("da-luu-tu-truoc", "quan-trong");
chay(tot);
check("kho thật được GIỮ NGUYÊN, không bị thay bằng kho tạm", tot.localStorage.THAT === true);
check("dữ liệu đã lưu còn nguyên", tot.localStorage.getItem("da-luu-tu-truoc") === "quan-trong");
check("lượt thăm dò không để lại rác", tot.localStorage.getItem("__javis_thu__") === null
      && tot.localStorage._soKhoa() === 1, tot.localStorage._soKhoa());

// ============================================================
// 3. Kho có mặt nhưng GHI THÌ NỔ (Safari riêng tư, hết hạn mức)
// ============================================================
// Chỉ kiểm tra `window.localStorage` tồn tại là bỏ lọt đúng ca này, và bỏ lọt thì script của
// trang vẫn chết y như cũ - lần này ở câu setItem đầu tiên.
const dayTui = {
  localStorage: { getItem() { return null; }, setItem() { throw new Error("QuotaExceededError"); },
                  removeItem() {}, HONG: true },
  sessionStorage: { getItem() { return null; }, setItem() { throw new Error("QuotaExceededError"); },
                    removeItem() {}, HONG: true },
};
chay(dayTui);
check("kho ghi vào là nổ cũng được thay bằng kho tạm", dayTui.localStorage.HONG === undefined);
dayTui.localStorage.setItem("a", "1");
check("và kho tạm đó ghi được thật", dayTui.localStorage.getItem("a") === "1");

if (fails.length) {
  console.log(`\nFAIL ${fails.length} muc: ` + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_kho_luu_tru_trang_chia_se: tat ca pass");
