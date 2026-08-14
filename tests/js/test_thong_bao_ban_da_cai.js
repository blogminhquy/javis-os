/* Bản ĐÃ CÀI thì chuông không nhắc nữa.

       node tests/js/test_thong_bao_ban_da_cai.js

   Chủ repo báo (2026-08-12): "ở phần cập nhật khi ấn đọc tất cả rồi, nâng cấp bản mới vẫn hiện
   các số như là chưa đọc".

   Đo trước khi sửa, trên trang thật chạy bằng server thật: cơ chế "Đọc tất cả" KHÔNG hỏng - bấm
   xong số tắt, tải lại trang vẫn tắt, trạng thái nằm nguyên trong localStorage. Nên nếu tin ngay
   báo cáo mà đi vá chỗ đánh dấu đã đọc thì vá nhầm chỗ.

   Chuyện thật sự xảy ra: giữa lúc bấm "Đọc tất cả" và lúc nâng cấp có thêm vài bản phát hành
   mới. Chúng chưa từng được đọc nên vào hàng chưa đọc - đúng luật. Rồi người dùng CÀI CHÍNH
   CHÚNG, mà chuông vẫn nhắc y nguyên. Nhắc một bản đang nằm sẵn trong máy là vô nghĩa: thông
   báo phát hành chỉ đáng chú ý khi nó là thứ mình CHƯA có.

   ĐÃ ĐO TRÊN TRANG THẬT (uvicorn + dashboard thật, chặn /notifications để dựng đúng kịch bản):
     - chạy 0.27.2, có 2 bản chưa cài  -> chuông báo 2   (cả code cũ lẫn mới đều phải báo)
     - nâng cấp lên 0.28.1             -> MỚI: 0  |  CŨ: 3
     - thẻ trong danh sách              -> MỚI: 0  |  CŨ: 3 thẻ vẫn tô kiểu chưa đọc
     - xuất hiện 0.29.0 chưa cài        -> cả hai đều báo 1 (không được vá quá tay thành câm)
   CI chỉ có node nên file này khoá phần hợp đồng đọc được từ mã nguồn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "dashboard", "notifications.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Luật: đã cài = không còn chưa đọc
// ============================================================
check("có hàm quyết định 'chưa đọc'", /function chuaDoc\(item\)/.test(JS));
check("CANARY: bản cập nhật ĐÃ CÀI thì không tính là chưa đọc",
  /if \(item\.kind === "update" && item\.installed\) return false;/.test(JS));
check("con số trên chuông đi qua đúng hàm đó", /return state\.items\.filter\(chuaDoc\);/.test(JS));

// ============================================================
// 2. Chuông và thẻ phải dùng CHUNG một luật
// ============================================================
// Trước đây thẻ tự soi state.read còn chuông soi unreadItems(). Hai chỗ tính hai kiểu thì chỉ
// cần lệch một chút là chuông báo 0 mà thẻ vẫn tô đậm - người dùng không biết tin ai.
check("CANARY: thẻ trong danh sách dùng chung hàm với chuông",
  /var unreadClass = chuaDoc\(item\) \? " unread" : "";/.test(JS));
check("CANARY: thẻ KHÔNG còn tự soi state.read", !/state\.read\.has\(id\) \? "" : " unread"/.test(JS));

// ============================================================
// 3. Không được vá quá tay thành câm hẳn
// ============================================================
// Bản CHƯA cài vẫn phải báo - đó là toàn bộ lý do cái chuông tồn tại. Và tin cộng đồng /
// marketing không có khái niệm "đã cài" nên vẫn theo luật đọc/chưa đọc như cũ.
check("luật chỉ áp cho tin kiểu 'update'", /item\.kind === "update" && item\.installed/.test(JS));
check("vẫn còn đường đánh dấu đã đọc thủ công", /function markAll\(\)/.test(JS) && /function markRead\(/.test(JS));
check("trạng thái đã đọc vẫn được lưu lại", /localStorage\.setItem\(READ_KEY/.test(JS));

console.log("");
if (fails.length) { console.log("THẤT BẠI " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("OK - test_thong_bao_ban_da_cai: tất cả pass");
