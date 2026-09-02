/* Bỏ nút loa (bật/tắt giọng Javis) - trước ở thanh tiêu đề, nay cả trên thanh nhập.

       node tests/js/test_bo_nut_loa_header.js

   27/08/2026: cùng MỘT công tắc giọng mà có tới ba chỗ bấm - nút loa ở header, nút loa trên
   thanh nhập chat, và công tắc trong Cài đặt nhanh. Bỏ nút header để lấy chỗ cho hòm thư.
   02/09/2026: chủ repo chốt "không cần nút bật tắt loa nữa, chỉ cần mic, bật mic là bật loa".
   Nút thanh nhập (#ttsToggleBar) bỏ nốt; app.js gọi window.JavisTts.set() theo mic. Công tắc
   trong Cài đặt nhanh giữ lại làm chỗ tắt tiếng thủ công.

   Bẫy của việc gỡ một element: app.js giữ nó ở một `const` cấp module rồi gọi thẳng
   `ttsToggle.addEventListener(...)` KHÔNG có chốt null. Gỡ nút mà quên dòng đó thì
   getElementById trả null -> TypeError ngay lúc nạp -> app.js CHẾT TỪ GIỮA FILE, tức là
   mất luôn chat, giọng nói, badge model... chứ không phải chỉ mất một cái nút. Nên test
   này soi cả ba nơi từng cầm id đó: app.js, quick-settings.js, mobile-chat.js. */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const html = read("dashboard/index.html");
const app = read("dashboard/app.js");
const qs = read("dashboard/quick-settings.js");
const mob = read("dashboard/mobile-chat.js");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. Nút header biến mất, nút trên thanh nhập ở lại ----
check("thanh tiêu đề KHÔNG còn nút loa", html.indexOf('id="ttsToggle"') === -1);
check("nút loa trên THANH NHẬP cũng KHÔNG còn (02/09: loa đi theo mic)",
  html.indexOf('id="ttsToggleBar"') === -1);
check("công tắc giọng trong Cài đặt nhanh vẫn còn", html.indexOf('id="qsTts"') !== -1);

// ---- 2. CANARY: không file JS nào còn cầm id đã gỡ ----
// Đây là chốt thật. `ttsToggle.addEventListener` trên một null là TypeError, và app.js
// không có try/catch quanh đó nên nửa cuối file không bao giờ chạy.
const cam = (src) => (src.match(/getElementById\(\s*["']ttsToggle["']\s*\)/g) || []).length;
check("app.js không còn tra cứu #ttsToggle", cam(app) === 0, cam(app));
check("quick-settings.js không còn tra cứu #ttsToggle", cam(qs) === 0, cam(qs));
check("mobile-chat.js không còn mang #ttsToggle sang rail màn hẹp", cam(mob) === 0, cam(mob));
check("CANARY: app.js không còn gọi thẳng ttsToggle.<gì đó> (null là chết cả file)",
  !/(^|[^.\w])ttsToggle\s*\./m.test(app));
check("app.js không còn khai const ttsToggle", !/const\s+ttsToggle\s*=/.test(app));

// ---- 3. Công tắc còn lại phải chạy đủ: mic điều khiển được, nhớ được, đồng bộ Cài đặt nhanh ----
check("quick-settings KHÔNG còn tra cứu #ttsToggleBar (nút đã gỡ, tra cứu là null)",
  !/\$\("ttsToggleBar"\)/.test(qs));
check("mobile-chat.js không còn nhắc tới #ttsToggleBar như một nút thật", !/getElementById\("ttsToggleBar"\)/.test(mob));
check("quick-settings phơi window.JavisTts.set cho mic gọi", /window\.JavisTts = \{ set: applyState/.test(qs));
check("vẫn nhớ trạng thái qua reload (localStorage javis.ttsEnabled)",
  qs.indexOf("javis.ttsEnabled") !== -1);
check("vẫn đồng bộ với công tắc trong Cài đặt nhanh", /\$\("qsTts"\)/.test(qs));
check("app.js bật loa theo mic", /window\.JavisTts\.set\(handsFree\)/.test(app));

// ---- 4. cache-bust: sửa file nào thì bump file đó, không thì trình duyệt xài bản cũ ----
const v = (f) => Number((html.match(new RegExp(f.replace(/\./g, "\\.").replace("-", "\\-") + "\\?v=(\\d+)")) || [])[1] || 0);
check("app.js đã bump ?v= (>= 94)", v("app.js") >= 94, v("app.js"));
check("quick-settings.js đã bump ?v= (>= 6)", v("quick-settings.js") >= 6, v("quick-settings.js"));
check("mobile-chat.js đã bump ?v= (>= 6)", v("mobile-chat.js") >= 6, v("mobile-chat.js"));

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_bo_nut_loa_header: tat ca pass");
