/* Ô chat NỞ THEO CHỮ như claude.ai (chủ yêu cầu 27/08/2026): gõ dài / xuống dòng là ô
   nhập cao lên cho thấy toàn bộ văn bản, không phải cuộn trong một ô 3 dòng.

   Lỗi gốc: app.js đã autosize theo scrollHeight từ lâu, nhưng CSS .voice-input ghim
   max-height:90px nên trên desktop autosize bị chặn cứng ở ~3 dòng dù JS tính đúng -
   nhìn như "không nở". Phải canh CẢ HAI tầng cùng lúc.

       node tests/js/test_o_chat_no_theo_chu.js
*/
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const css = read("dashboard/style.css");
const app = read("dashboard/app.js");
const html = read("dashboard/index.html");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// Bóc đúng khối .voice-input GỐC (desktop) - khối mobile trong media query là khối khác.
const base = (css.match(/\n\.voice-input \{[^}]*\}/) || [""])[0];
check("tìm thấy khối .voice-input gốc", !!base);
check("CSS gốc không còn ghim max-height:90px chặn autosize", base.indexOf("max-height: 90px") === -1);
check("CSS gốc chỉ giữ lưới đỡ theo màn hình (max-height 45vh)", base.indexOf("max-height: 45vh") !== -1);
check("hàng nhập neo nút ở đáy khi ô cao lên (align-items: flex-end)",
  /\.hud-voice \{[^}]*align-items: flex-end/s.test(css));

// JS: trần nở theo ngữ cảnh - trang Trò chuyện 40% màn hình, màn chính 200px.
check("autosize vẫn theo scrollHeight", app.indexOf("chatInput.scrollHeight") !== -1);
check("trang Trò chuyện nở tới 40% màn hình (đo lúc gõ)",
  app.indexOf("Math.round(window.innerHeight * 0.4)") !== -1);
check("màn chính trần 200px (không còn 90px)",
  /innerHeight \* 0\.4\)\s*:\s*200;/.test(app));
check("gửi xong ô nhập xẹp về một dòng (reset height)",
  app.indexOf('chatInput.style.height = "auto"') !== -1);
check("ô nhập là textarea rows=1 (xẹp được về một dòng)",
  /<textarea id="chatInput"[^>]*rows="1"/.test(html));

// cache-bust
check("app.js đã bump ?v= (>= 93)",
  Number((html.match(/app\.js\?v=(\d+)/) || [])[1] || 0) >= 93);
check("style.css đã bump ?v= (>= 67)",
  Number((html.match(/style\.css\?v=(\d+)/) || [])[1] || 0) >= 67);

console.log();
if (fails.length) {
  console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
  process.exit(1);
}
console.log("OK - test_o_chat_no_theo_chu: tat ca pass");
