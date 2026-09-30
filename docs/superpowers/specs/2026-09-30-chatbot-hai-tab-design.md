# Trang Chatbot còn hai tab: Hòm thư và Bot (0.65.9)

## Vấn đề

Chủ dự án (30/09/2026): phần "Kênh của bot" và phần "Tạo chatbot" nên gộp làm một, "để đỡ phải lựa chọn chatbot vào kênh nào đó, nó bị khó
hiểu". Trang có ba tab (Hòm thư bot, Kênh của bot, Tạo chatbot). Muốn có một bot trả lời trên Zalo thì phải: sang tab Kênh, Thêm kênh; sang tab
Tạo chatbot, Bot mới; tick lại đúng kênh vừa thêm. Hai tab còn dặn qua lại nhau ("Tạo bot trực" bên kênh, "Kết nối kênh mới" bên form).

## Quyết định (đã duyệt qua mockup hai vòng)

- **Hai tab**: Hòm thư bot và Bot. Id tab cũ `kenh`, `chatbot` vẫn dẫn về Bot (`TAB_CU`), vì `console.js`, thông báo và bookmark còn gọi chúng.
- **Tab Bot = danh sách bot (chatbots.js) + mục "Kênh chưa có bot" (conversations.js)** ngay dưới.
  - Kênh ĐÃ có bot hiện thành chip trên thẻ bot. Chip Telegram/Zalo Bot bấm được: mở bảng sửa kênh (nhãn, token, brain) có thêm nút **Xoá kênh**
    (trước đây nằm ở thẻ kênh, mà thẻ kênh đã có bot giờ không còn). Chip Zalo cá nhân chỉ để đọc (nó là kết nối ở trang Kết nối).
  - Chip "Thêm kênh" trên thẻ bot mở form Sửa ngay ở bước chọn kênh.
  - Mục kênh: kênh chưa có bot, công tắc "Xem mọi brain", nút Thêm kênh. Tự mở khi có kênh cần xử lý, tự gập khi hết; người dùng bấm thì theo họ.
- **Form Bot mới**: kênh đang do bot khác trực hiện MỜ kèm ổ khoá, ghi tên bot đang giữ (và brain nếu khác brain đang mở). Trước đây form giấu hẳn.
  Server cấp thêm `tai_khoan_ban` trong `GET /chatbots`. Dòng khoá không có ô tick và không mang lớp `cb-tk-o`, nếu không sẽ bị đếm là kênh đã chọn.
- **Icon**: robot bị chê xấu. Tab dùng `headset` (icon "Tạo chatbot" đã dùng), chip Agent dùng `user-round`, nút "Tự động" ở Hòm thư dùng `sparkles`,
  màn trống dùng `headset`. Studio và Cộng sự giữ nguyên.
- **Giữ nguyên mô hình brain** (chủ chốt): bot thuộc đúng một brain; Telegram/Zalo Bot có brain chủ; Zalo cá nhân là kết nối toàn cục nên brain nào cũng thấy;
  mỗi kênh chỉ một bot trực dù bot ở brain nào.

## Chỗ dễ mất chức năng (đã có canary trong `tests/js/test_chatbot_hai_tab.js`)

1. Sửa/xoá kênh đã có bot phải còn đường vào (chip bấm được), nếu không token không đổi được nữa.
2. Đang "Xem mọi brain" thì mục kênh liệt kê cả kênh do bot của brain KHÁC trực: bot đó không hiện ở trang này nên không còn chỗ nào khác để sửa hay xoá.
3. Xoá kênh xong phải dựng lại tab để chip của kênh vừa xoá biến mất.
4. `ht-bot` là tên lớp cũ của ô chọn bot ở Hòm thư (test canh nó không quay lại), nên ô bao tab Bot đặt tên `ht-tab-bot`.

## Ngoài phạm vi

- Không đổi API kênh/bot, không đổi mô hình brain, không gộp kho dữ liệu.
- Thẻ kênh (`theTK`) giữ nguyên khuôn cũ trong mục "Kênh chưa có bot".

## Kiểm

`test_chatbot_hai_tab.js` (canary nguồn), `test_chatbot_tai_khoan_ban.py` (server), các test JS cũ cập nhật theo tên tab mới; chạy thật trên bản
sandbox với bot và kênh mẫu: hai tab, chip sửa kênh, chip Thêm kênh mở form bước chọn kênh với dòng khoá, "Tạo bot cho kênh này", gập/mở, tự gập khi hết kênh,
"Xem mọi brain", id tab cũ, hộp thư trống sang tab Bot, và bố cục điện thoại 375px không tràn ngang.
