/* Đồ thị bộ não trên điện thoại (0.422.0): hiện ra, kéo tự do, buông tay vài giây thì tự về giữa.

       node tests/js/test_do_thi_dien_thoai.js

   Chủ repo báo 30/10/2026: trên điện thoại khoang não không thấy đồ thị, chỉ còn tên các cụm. Nguyên nhân: console.js coi
   màn hẹp là "lite" và dừng đồ thị; từ 0.415.0 lệnh dừng chạy ngay sau khi đồ thị dựng xong, tức là TRƯỚC khung vẽ đầu
   tiên, nên khung vẽ trống trơn (đo bằng Playwright: 0 điểm ảnh). Cùng lần đó chủ repo xin: kéo tự do, vài giây sau tự về
   giữa.

   Phần đầu khoá hợp đồng đọc từ mã nguồn. Phần sau chạy THẬT lớp JavisGraph với đồng hồ giả: kéo, buông, đợi. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ── 1. Màn hẹp không còn tự tắt đồ thị ──
const con = read("dashboard/console.js");
check("CANARY: liteMode chỉ còn theo công tắc Đồ thị, không theo bề ngang màn hình",
  /const liteMode = \(\) => !graphEnabled;/.test(con) && !/const liteMode = \(\) => !graphEnabled \|\| isNarrow\(\)/.test(con));
check("CANARY: không còn lệnh dừng đồ thị sớm cho màn hẹp", !/if \(isNarrow\(\) && window\.__javisGraph\) \{ try \{ window\.__javisGraph\.pause\(\)/.test(con));
check("thẻ Đồ thị trong Cài đặt thôi báo 'màn hẹp đang ép lite-mode'", !/cs\.ov_lite/.test(con));
for (const lang of ["vi", "en"]) {
  check(`khoá cs.ov_lite đã gỡ khỏi ${lang}.json`, !("cs.ov_lite" in JSON.parse(read(`dashboard/i18n/${lang}.json`))));
}

// ── 2. Kéo tự do, tự về giữa: chạy thật với đồng hồ giả ──
let gio = 0, hen = [];
const setT = (fn, ms) => { const h = { fn, luc: gio + ms, id: hen.length + 1 }; hen.push(h); return h.id; };
const clearT = (id) => { hen = hen.filter(h => h.id !== id); };
const troiToi = (ms) => {
  const het = gio + ms;
  for (;;) {
    hen.sort((a, b) => a.luc - b.luc);
    const h = hen[0];
    if (!h || h.luc > het) break;
    hen.shift(); gio = h.luc; h.fn();
  }
  gio = het;
};
function phanTu() {
  const nghe = {};
  return {
    nghe, clientWidth: 390, clientHeight: 210, style: {}, parentElement: null,
    addEventListener: (ten, fn) => { (nghe[ten] = nghe[ten] || []).push(fn); },
    phat: (ten, e) => (nghe[ten] || []).forEach(fn => fn(e || {})),
  };
}
const win = phanTu();
win.dispatchEvent = () => {};
const ctx = vm.createContext({ window: win, document: { createElement: () => ({ getContext: () => ({}) }) }, performance: { now: () => gio },
  setTimeout: setT, clearTimeout: clearT, Event: function () {}, Math, Set, Date, console });
vm.runInContext(read("dashboard/graph.js") + "\n;window.__JG = JavisGraph;", ctx);
const JG = win.__JG;
const el = phanTu();
const g = new JG(el);
let lanFit = 0;
g.graph = { autoPauseRedraw() { return this; }, minZoom() { return this; }, zoom: () => 1, zoomToFit: () => { lanFit++; }, width() { return this; }, height() { return this; } };
g._ngheChuot();

check("thời gian chờ về giữa là 3 giây", JG.VE_GIUA_MS === 3000);

// Ngón tay kéo 60px rồi nhấc ra
el.phat("pointerdown", { pointerType: "touch", clientX: 100, clientY: 100 });
el.phat("pointermove", { pointerType: "touch", clientX: 160, clientY: 120 });
win.phat("pointerup", {});
troiToi(2900);
check("buông tay chưa tới 3 giây: camera vẫn ở chỗ người dùng kéo tới", lanFit === 0);
troiToi(200);
check("CANARY: buông tay 3 giây: tự canh về giữa", lanFit === 1);

// Kéo, rồi chạm lại trước khi hết giờ: huỷ hẹn, chỉ về giữa sau lần thả CUỐI
lanFit = 0;
el.phat("pointerdown", { pointerType: "touch", clientX: 100, clientY: 100 });
el.phat("pointermove", { pointerType: "touch", clientX: 200, clientY: 100 });
win.phat("pointerup", {});
troiToi(2000);
el.phat("pointerdown", { pointerType: "touch", clientX: 200, clientY: 100 });
troiToi(2000);
check("đang giữ tay thì không giật camera về giữa", lanFit === 0);
win.phat("pointerup", {});
troiToi(3100);
check("thả lần cuối 3 giây thì mới về giữa, một lần", lanFit === 1);

// Chạm một chấm (không di chuyển) không làm camera chạy
lanFit = 0;
el.phat("pointerdown", { pointerType: "touch", clientX: 50, clientY: 50 });
el.phat("pointermove", { pointerType: "touch", clientX: 52, clientY: 51 });
win.phat("pointerup", {});
troiToi(5000);
check("CANARY: chạm một chấm để mở note thì không tự về giữa", lanFit === 0);

// Không ai đụng vào thì không bao giờ tự canh
troiToi(60000);
check("không ai đụng vào thì camera đứng yên", lanFit === 0);

// Máy tính: chuột kéo xong còn nằm trên quả cầu thì chờ nó rời đi
lanFit = 0;
el.phat("pointerenter", { pointerType: "mouse" });
el.phat("pointerdown", { pointerType: "mouse", clientX: 100, clientY: 100 });
el.phat("pointermove", { pointerType: "mouse", clientX: 180, clientY: 140 });
win.phat("pointerup", {});
troiToi(5000);
check("chuột còn trên quả cầu (đang soi một vùng): chưa về giữa", lanFit === 0);
el.phat("pointerleave", { pointerType: "mouse" });
troiToi(3100);
check("chuột rời quả cầu 3 giây: về giữa", lanFit === 1);

// Lăn chuột để phóng cũng tính là một lần kéo
lanFit = 0;
el.phat("wheel", {});
troiToi(3100);
check("lăn chuột phóng to rồi để yên 3 giây: về giữa", lanFit === 1);

console.log("");
if (fails.length) { console.log("THẤT BẠI " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("OK - test_do_thi_dien_thoai: tất cả pass");
