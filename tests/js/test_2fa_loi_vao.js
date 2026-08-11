/* Xác thực 2 lớp phải TÌM THẤY ĐƯỢC từ trang Cài đặt, không chỉ từ trang Tài khoản.

       node tests/js/test_2fa_loi_vao.js

   Javis có HAI bề mặt cài đặt tài khoản, và đó là lịch sử chứ không phải thiết kế:

   1. Trang **Tài khoản** (console.js renderAccount) - đủ thứ, gồm cả luồng bật 2FA có QR.
   2. Khối **"Tài khoản đăng nhập"** trong #quickSet (index.html), được nhúng vào trang
      **Cài đặt** lúc render - chỉ có đổi mật khẩu / đăng xuất / tắt đăng nhập.

   0.26.20 thêm 2FA vào chỗ (1) mà quên chỗ (2). Hậu quả không phải "thiếu một nút": chủ repo
   mở trang Cài đặt, thấy một khối tài khoản không nhắc gì tới 2FA, và kết luận Javis chưa có
   tính năng đó - trong khi nó đã chạy được cả ngày. Tính năng bảo mật mà người dùng không tìm
   ra thì bằng không.

   File này canh ba thứ:

   1. **Có lối vào ở chỗ (2).** Đây là nội dung chính.
   2. **Chỉ là LỐI ĐI, không phải bản sao.** Luồng quét QR phải nằm đúng một chỗ. Hai bản sao
      của một luồng bảo mật là hai chỗ phải sửa mỗi lần đổi, và chỗ nào quên sửa thì thành lỗ.
   3. **Cache-busting đã bump.** console.js/console.css đổi mà quên tăng ?v= thì trình duyệt
      người dùng giữ bản cũ, và bản vá này đơn giản là không tới nơi. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
const js = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");

const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. Lối vào tồn tại, và nằm ĐÚNG trong khối tài khoản của #quickSet ----
check("index.html có điểm neo #setTfaRow", /id="setTfaRow"/.test(html));
const quick = html.slice(html.indexOf('id="quickSet"'));
const khoiTk = quick.slice(quick.indexOf("Tài khoản đăng nhập"));
check("điểm neo nằm trong khối 'Tài khoản đăng nhập', không lạc sang khối khác",
  khoiTk.indexOf('id="setTfaRow"') >= 0
  && khoiTk.indexOf('id="setTfaRow"') < khoiTk.indexOf("</div>\n      </div>") + 4000);
check("console.js có hàm đổ nội dung cho nó", /async function renderTfaRow\(/.test(js));

// Phải gọi TRƯỚC vòng nối [data-settings-go]: nút nằm trong khối vừa nhúng và dựa vào chính
// vòng đó để có hành động. Gọi sau là nút hiện ra nhưng bấm không ăn - loại hỏng im lặng nhất.
const iGoi = js.indexOf("await renderTfaRow()");
const iNoi = js.indexOf('el.querySelectorAll("[data-settings-go]")');
check("renderTfaRow được gọi trong renderSettings", iGoi > 0);
check("CANARY: gọi TRƯỚC vòng nối [data-settings-go], nếu không nút bấm sẽ không ăn",
  iGoi > 0 && iNoi > 0 && iGoi < iNoi);

// ---- 2. Chỉ là lối đi, KHÔNG nhân đôi luồng bật ----
const ham = js.slice(js.indexOf("async function renderTfaRow("),
  js.indexOf("async function renderSettings("));
check("nút dùng chung đường chuyển trang sẵn có", /data-settings-go="account"/.test(ham));
// Cấm theo ENDPOINT chứ không theo chữ trần: dòng trạng thái CÓ đọc `totp_recovery_left` để
// khoe còn mấy mã, và đó là đọc trạng thái chứ không phải nhân đôi luồng. Cấm chữ "recovery"
// trần thì canary đỏ vì chính cái nó nên cho phép.
for (const cam of ["/auth/2fa/start", "/auth/2fa/enable", "/auth/2fa/disable",
                   "/auth/2fa/recovery", "qr_svg", "hienMaKhoiPhuc"]) {
  check(`CANARY: KHÔNG nhân đôi luồng bật ('${cam}' không nằm trong dòng trạng thái)`,
    !ham.includes(cam));
}
check("chỉ đọc trạng thái qua /auth/status", /fetch\("\/auth\/status"\)/.test(ham));
// Chưa có mật khẩu thì chưa có gì để chồng lớp hai lên - phải nói thứ tự, đừng đưa nút chết.
check("chưa đặt mật khẩu -> nói phải đặt mật khẩu trước", /needs_setup/.test(ham));
check("và không đưa nút bấm ở trạng thái đó",
  ham.indexOf("needs_setup") < ham.indexOf('data-settings-go="account"'));
check("có cảnh báo khi mã khôi phục sắp hết", /sắp hết/.test(ham));

// Luồng bật thật vẫn phải còn nguyên ở trang Tài khoản - đừng dời nhầm sang đây.
check("luồng quét QR vẫn nằm ở trang Tài khoản", js.includes("/auth/2fa/start"));

// ---- 3. Kiểu dáng + cache-busting ----
check("console.css có kiểu cho dòng trạng thái", /\.set-tfa\s*\{/.test(css));
const v = (re) => { const m = html.match(re); return m ? Number(m[1]) : -1; };
check("index.html bump ?v= của console.js (nếu không, người dùng giữ bản cũ)",
  v(/console\.js\?v=(\d+)/) >= 99);
check("index.html bump ?v= của console.css", v(/console\.css\?v=(\d+)/) >= 42);

console.log("");
if (fails.length) {
  console.log(`${fails.length} test HỎNG: ` + fails.join(", "));
  process.exit(1);
}
console.log("Tất cả test 2fa_loi_vao đã qua.");
