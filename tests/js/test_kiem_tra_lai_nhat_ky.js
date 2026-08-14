/* Nút "Kiểm tra lại" ở trang Cập nhật phải làm mới CẢ danh sách phiên bản.

       node tests/js/test_kiem_tra_lai_nhat_ky.js

   Chủ repo báo (2026-08-12): "trên bản update anh chưa thấy bản 28 check lại giúp anh".

   Kiểm rồi: main ĐÚNG (VERSION 0.28.0, CHANGELOG có mục 0.28.0 trên cùng), GitHub raw cũng
   đã trả 0.28.0. Lỗi nằm ở trang.

   Trang Cập nhật có HAI phần đọc hai đường khác nhau:
     - Khung trên (phiên bản + nút Cập nhật ngay) gọi /version, có cache no-store, bấm
       "Kiểm tra lại" là nạp lại.
     - Danh sách phiên bản bên dưới gọi /changelog, và nó chỉ được nạp ĐÚNG MỘT LẦN lúc mở
       trang. Nút "Kiểm tra lại" trước đây chỉ gọi loadVersion, không đụng gì tới danh sách.

   Nên bấm bao nhiêu lần cũng không thấy bản mới hiện ra, phải rời trang rồi quay lại hoặc F5.
   Không lỗi nào hiện ra, và khung trên thì vẫn báo "có bản mới" đàng hoàng - nên nhìn như là
   dữ liệu sai chứ không phải nút hỏng.

   Cộng thêm một chỗ nữa cùng loại: lời gọi /changelog là lời gọi DUY NHẤT ở trang này quên
   cache:"no-store", tức là chỗ duy nhất có thể ăn bản cũ trong bộ nhớ đệm trình duyệt.

   ĐÃ ĐO TRÊN TRANG THẬT, server thật (uvicorn + dashboard thật, chặn /changelog để dựng đúng
   tình huống "lúc mở chưa có 0.28.0, bấm nút sau khi nó đã lên"):
     - code MỚI: bấm nút -> danh sách hiện v0.28.0, /changelog được gọi 2 lần.
     - code CŨ:  bấm nút -> danh sách vẫn chỉ v0.27.2, /changelog gọi đúng 1 lần.
   CI chỉ có node nên file này khoá phần hợp đồng đọc được từ mã nguồn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const CON = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Nút phải nạp lại CẢ HAI phần
// ============================================================
check("có hàm nạp riêng cho danh sách phiên bản", /async function napTimeline\(\)/.test(CON));
check("CANARY: hàm đó được truyền vào bộ máy nút bấm",
  /wireUpdateManager\(el, napTimeline\)/.test(CON));
check("CANARY: bấm 'Kiểm tra lại' gọi CẢ loadVersion LẪN nạp danh sách",
  /check\.onclick = async \(\) => \{[\s\S]{0,160}await loadVersion\(\);[\s\S]{0,160}await napLai\(\);/.test(CON));
// Bản cũ gán thẳng loadVersion vào onclick - đó chính là cả cái lỗi.
check("CANARY: không còn gán thẳng loadVersion vào nút",
  !/check\.onclick = loadVersion;/.test(CON));

// ============================================================
// 2. Không được ăn bản cũ trong bộ nhớ đệm
// ============================================================
// Mọi lời gọi khác ở trang này đều đã no-store; sót một chỗ là chỗ đó thành nguồn dữ liệu cũ,
// mà lại đúng chỗ hiển thị danh sách phiên bản.
check("CANARY: /changelog nạp với cache no-store",
  /fetch\("\/changelog", \{ cache: "no-store" \}\)/.test(CON));
check("CANARY: không còn lời gọi /changelog trần", !/fetch\("\/changelog"\)/.test(CON));
check("/version vẫn giữ no-store như cũ", /fetch\("\/version", \{ cache: "no-store" \}\)/.test(CON));

// ============================================================
// 3. Đổi trang giữa chừng thì đừng vẽ đè
// ============================================================
// napTimeline chạy bất đồng bộ; người dùng bấm nút rồi đi trang khác là kết quả về muộn và vẽ
// đè lên trang mới. Bộ đếm _renderGen có sẵn để chặn - phải giữ nó trong hàm mới.
check("CANARY: vẫn kiểm _renderGen trước khi vẽ", /myGen !== _renderGen/.test(CON));

console.log("");
if (fails.length) { console.log("THẤT BẠI " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("OK - test_kiem_tra_lai_nhat_ky: tất cả pass");
