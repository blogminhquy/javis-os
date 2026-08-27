/* "Mở như app" phải có ở BẢN MÁY TÍNH, không chỉ mobile (chủ yêu cầu 27/08/2026).

   Vì sao trước đây desktop không cài được: manifest chỉ khai một icon PNG với
   sizes "any" - giá trị đó chỉ hợp lệ cho SVG, nên Chrome/Edge desktop coi trang là
   KHÔNG đủ điều kiện cài và không bao giờ hiện nút cài. iOS thì đi đường
   apple-touch-icon riêng nên mobile vẫn chạy dạng app được, tạo cảm giác "mobile có,
   desktop không".

   Kiểm trên SOURCE thật: manifest phải có icon PNG vuông khai sizes rõ, file icon phải
   tồn tại, và app.js phải bắt beforeinstallprompt để bày nút "Mở như app".

       node tests/js/test_cai_app_desktop.js
*/
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const manifest = JSON.parse(read("dashboard/manifest.json"));
const html = read("dashboard/index.html");
const app = read("dashboard/app.js");
const css = read("dashboard/style.css");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. Manifest đủ điều kiện cài trên desktop ----
const icons = manifest.icons || [];
const i192 = icons.find((i) => i.sizes === "192x192");
const i512 = icons.find((i) => i.sizes === "512x512");
check("manifest có icon 192x192", !!i192);
check("manifest có icon 512x512", !!i512);
check("icon khai type image/png", icons.every((i) => i.type === "image/png"));
check("không còn icon PNG khai sizes 'any' (Chrome coi là không hợp lệ)",
  !icons.some((i) => i.sizes === "any"));
check("display standalone giữ nguyên", manifest.display === "standalone");

// ---- 2. File icon tồn tại thật (khai trong manifest mà thiếu file = cũng không cài được) ----
check("dashboard/icon-192.png tồn tại", fs.existsSync(path.join(root, "dashboard", "icon-192.png")));
check("dashboard/icon-512.png tồn tại", fs.existsSync(path.join(root, "dashboard", "icon-512.png")));

// ---- 3. Nút "Mở như app" trên thanh trạng thái ----
check("index.html có nút installAppBtn", html.indexOf('id="installAppBtn"') !== -1);
check("nút ẩn mặc định (chỉ hiện khi trình duyệt báo cài được)",
  /id="installAppBtn"[^>]*hidden|hidden[^>]*id="installAppBtn"/.test(html));
check("CSS có .install-app-btn", css.indexOf(".install-app-btn") !== -1);

// ---- 4. app.js bắt đúng luồng cài của Chromium ----
check("nghe beforeinstallprompt", app.indexOf('addEventListener("beforeinstallprompt"') !== -1);
check("chặn mini-infobar tự bung (preventDefault)",
  /beforeinstallprompt[\s\S]{0,200}preventDefault\(\)/.test(app));
check("bấm nút mới bung hộp cài (prompt())", app.indexOf(".prompt()") !== -1);
check("đã chạy dạng app thì không bày nút (display-mode: standalone)",
  app.indexOf("display-mode: standalone") !== -1);
check("cài xong thì giấu nút (appinstalled)", app.indexOf('addEventListener("appinstalled"') !== -1);

// ---- cache-bust: đổi manifest phải đổi ?v= để trình duyệt đọc bản mới ----
check("manifest.json đã bump ?v= (>= 2)",
  Number((html.match(/manifest\.json\?v=(\d+)/) || [])[1] || 0) >= 2);

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_cai_app_desktop: tat ca pass");
