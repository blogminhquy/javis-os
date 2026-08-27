/* Bỏ nút loa (bật/tắt giọng Javis) trên thanh tiêu đề.

       node tests/js/test_bo_nut_loa_header.js

   Chủ repo yêu cầu 27/08/2026: cùng MỘT công tắc giọng mà có tới ba chỗ bấm - nút loa ở
   header, nút loa trên thanh nhập chat, và công tắc trong Cài đặt nhanh. Giữ lại nút trên
   THANH NHẬP (nó nằm ngay cạnh chỗ người ta gõ, thấy được ở cả màn Javis lẫn trang Trò
   chuyện, và có sẵn trên màn hẹp); bỏ nút header đi để lấy chỗ cho hòm thư.

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
check("nút loa trên THANH NHẬP vẫn còn (đây là chỗ giữ lại)",
  html.indexOf('id="ttsToggleBar"') !== -1);
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

// ---- 3. Công tắc còn lại phải chạy đủ: bấm được, nhớ được, đồng bộ hai chiều ----
check("quick-settings vẫn gắn click cho nút trên thanh nhập",
  /\$\("ttsToggleBar"\)/.test(qs) && qs.indexOf('bar.addEventListener("click"') !== -1);
check("vẫn nhớ trạng thái qua reload (localStorage javis.ttsEnabled)",
  qs.indexOf("javis.ttsEnabled") !== -1);
check("vẫn đồng bộ với công tắc trong Cài đặt nhanh", /\$\("qsTts"\)/.test(qs));
check("reflect() vẫn cập nhật nút trên thanh nhập (class muted + title)",
  /bar\.classList\.toggle\("muted", !on\)/.test(qs));

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
