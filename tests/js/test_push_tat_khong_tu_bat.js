// 0.223.0: tắt thông báo đẩy rồi thì tải lại trang không được tự bật lại (dashboard/push.js).
//
//     node tests/js/test_push_tat_khong_tu_bat.js
//
// Chủ repo 19/10/2026: "anh tắt thông báo đẩy ở máy tính xong nó tự bật lên". Tắt chỉ huỷ đăng ký, quyền thông báo
// của trình duyệt vẫn là "granted", và lúc tải trang push.js thấy quyền còn thì lặng lẽ đăng ký lại.
// Chạy push.js thật trong một trình duyệt giả, đếm số lần nó gọi /push/subscribe.
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "push.js"), "utf8");

const fails = [];
function check(name, ok, them) {
  console.log((ok ? "ok   " : "FAIL ") + name + (!ok && them !== undefined ? "  [" + JSON.stringify(them) + "]" : ""));
  if (!ok) fails.push(name);
}

const store = {};
const goi = [];
let sub = null;
let khoa = "";

function trinhDuyet() {
  const timers = [];
  const pushManager = {
    getSubscription: async () => sub,
    subscribe: async () => {
      sub = { endpoint: "https://push.example/1", options: {}, toJSON: () => ({ endpoint: "https://push.example/1" }),
              unsubscribe: async () => { sub = null; return true; } };
      return sub;
    },
  };
  const reg = { pushManager };
  const win = {
    isSecureContext: true,
    PushManager: function () {},
    Notification: { permission: "granted", requestPermission: async () => "granted" },
    t: (k) => k,
  };
  const ctx = {
    window: win,
    navigator: { userAgent: "test", serviceWorker: { register: async () => reg, ready: Promise.resolve(reg),
                                                      addEventListener: () => {} } },
    Notification: win.Notification,
    document: { readyState: "complete", addEventListener: () => {} },
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); },
                    removeItem: (k) => { delete store[k]; } },
    fetch: async (url) => {
      goi.push(url);
      return { json: async () => (url === "/push/key" ? { key: khoa, devices: [] } : { ok: true }) };
    },
    setTimeout: (fn) => { timers.push(fn); return timers.length; },
    atob, btoa, Uint8Array, String, JSON, Promise,
  };
  win.navigator = ctx.navigator;
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  // tuNoiLai gọi bat() mà không trả promise: chạy hẹn giờ rồi nhường vài nhịp cho chuỗi await bên trong đi hết.
  const nhuong = async () => { for (let i = 0; i < 20; i++) await new Promise((r) => setImmediate(r)); };
  return { P: win.JavisPush, chayHenGio: async () => { for (const f of timers.splice(0)) f(); await nhuong(); } };
}

// Khoá server rỗng làm bat() dừng sớm ở bước /push/key: đủ để biết push.js CÓ thử bật lại hay không.
const soLanThuBat = () => goi.filter((u) => u === "/push/key").length;

(async () => {
  // Lần tải đầu, quyền đã cấp từ trước, chưa từng bấm Tắt: vẫn tự nối lại như cũ.
  let b = trinhDuyet();
  await b.chayHenGio();
  check("chưa bấm Tắt: tải trang vẫn tự nối lại đăng ký", soLanThuBat() === 1, goi);

  // Có đăng ký, bấm Tắt.
  sub = { endpoint: "https://push.example/1", unsubscribe: async () => { sub = null; return true; } };
  const r = await b.P.tat();
  check("Tắt: huỷ đăng ký ở trình duyệt", r.ok && sub === null, r);
  check("Tắt: báo server bỏ thiết bị này", goi.includes("/push/unsubscribe"), goi);
  check("Tắt: nhớ lựa chọn ở trình duyệt này", store["javis.push.off"] === "1", store);

  // Tải lại trang: quyền vẫn "granted" nhưng không được tự bật lại.
  goi.length = 0;
  b = trinhDuyet();
  await b.chayHenGio();
  check("tải lại sau khi Tắt: KHÔNG tự bật lại", soLanThuBat() === 0 && !goi.includes("/push/subscribe"), goi);
  check("và vẫn hiện là đang tắt", (await b.P.dangBat()) === false);

  // Bấm Bật khi server chưa có khoá: bật hỏng thì vẫn giữ dấu đã tắt, lần tải sau không tự bật.
  const r2 = await b.P.bat();
  check("bấm Bật hỏng: báo lỗi, giữ nguyên trạng thái tắt", r2.ok === false && store["javis.push.off"] === "1", [r2, store]);

  // Bấm Bật được thật: bỏ dấu đã tắt, lần tải sau lại tự nối như trước.
  khoa = "QUJD";
  const r3 = await b.P.bat();
  check("bấm Bật thành công: đăng ký và bỏ dấu đã tắt",
    r3.ok === true && goi.includes("/push/subscribe") && !("javis.push.off" in store), [r3, store, goi]);
  goi.length = 0;
  b = trinhDuyet();
  await b.chayHenGio();
  check("bật lại rồi thì tải trang lại tự nối như cũ", soLanThuBat() === 1, goi);

  const nguon = SRC;
  check("chỉ bat() thành công mới bỏ dấu đã tắt", /if \(d\.ok\) nhoTat\(false\);/.test(nguon));
  check("tat() nhớ trước khi huỷ (huỷ hỏng giữa chừng cũng không tự bật lại)",
    nguon.indexOf("nhoTat(true)") > nguon.indexOf("async function tat()") &&
    nguon.indexOf("nhoTat(true)") < nguon.indexOf("pushManager.getSubscription()", nguon.indexOf("async function tat()")));

  if (fails.length) { console.log("\nFAIL " + fails.length + ": " + fails.join(", ")); process.exit(1); }
  console.log("\nOK - test_push_tat_khong_tu_bat: all pass");
})();
