# Dùng Javis ngay trong ChatGPT

Bạn chat trên **chatgpt.com** bằng gói ChatGPT của mình, và ChatGPT tự gọi công cụ của Javis khi cần: xem doanh thu, đọc brain, tạo nhắc lịch, giao việc, gửi Zalo...

Phần suy nghĩ chạy bằng gói ChatGPT của bạn, **không tốn hạn mức Codex**. Javis chỉ lo phần làm.

> Tính năng này thay cho model "ChatGPT Web" cũ (đã gỡ ở bản 0.64.20). Model cũ bắt Javis mở một trình duyệt vào chatgpt.com, và trên máy chủ thuê thì trang đó chặn. Cách mới đi theo chiều ngược lại, qua tính năng chính thức của ChatGPT, nên không bị chặn.

---

## Cần có gì

- **Gói ChatGPT** Plus, Pro, Business (Team), Enterprise hoặc Edu. Gói miễn phí không có tính năng này.
- **Máy tính.** Bước cài đặt (Developer mode) chỉ làm được trên bản web chatgpt.com, không làm được trong app điện thoại.
- **Javis có địa chỉ https.** ChatGPT không nhận địa chỉ kiểu `http://12.34.56.78:7777`. Gắn tên miền riêng theo [trang 15](15-thuong-hieu-ten-mien.md) trước.
- **Javis đã đặt mật khẩu quản trị.** Bước cho phép dựa vào đăng nhập dashboard.

---

## Bước 1: Bật trong Javis

1. Mở **Models**, tìm thẻ **ChatGPT**.
2. Ở khối **Dùng Javis ngay trong ChatGPT**, bấm **Bật**.
3. Bấm **Chép** để chép địa chỉ hiện ra. Nó có dạng `https://ten-mien-cua-ban/chatgpt/mcp`.

Nếu khối báo "ChatGPT chỉ nhận địa chỉ https", xem lại phần tên miền ở trên.

## Bước 2: Chỉ khi dùng gói Business (Team)

Quản trị viên của workspace phải cho phép tạo connector riêng. Trên chatgpt.com vào **Workspace settings → Permissions & roles → Connected data**, bật **Create custom MCP connectors**.

Nếu bạn là người tạo workspace thì bạn chính là quản trị viên.

## Bước 3: Bật Developer mode trên ChatGPT

Trên chatgpt.com (máy tính): **Settings → Apps & Connectors → Advanced settings**, bật **Developer mode**.

> Tên các mục có thể hơi khác theo phiên bản ChatGPT. Tìm chữ "Developer mode" trong phần Settings.

## Bước 4: Tạo connector

Vẫn trong **Settings → Apps & Connectors**, bấm **Create** (hoặc **Add**), rồi điền:

| Ô | Điền gì |
|---|---|
| Name | `Javis` |
| Description | `Trợ lý Javis của tôi: số liệu, brain, nhắc việc, Zalo` |
| MCP Server URL | địa chỉ đã chép ở bước 1 |
| Authentication | **OAuth** |

Tích ô xác nhận tin tưởng connector, rồi bấm **Create**.

## Bước 5: Cho phép

ChatGPT mở một trang của Javis.

- Nếu trình duyệt chưa đăng nhập Javis, trang hiện ô đăng nhập ngay tại chỗ (có cả ô mã 2 lớp nếu bạn đã bật).
- Trang tiếp theo nói rõ ChatGPT được làm gì và đang ở mức quyền nào. Bấm **Cho phép**.

Xong. Quay lại ChatGPT là thấy Javis đã kết nối.

## Bước 6: Dùng

Trong khung chat của ChatGPT, bấm dấu **+** (hoặc biểu tượng công cụ), chọn **Developer mode**, rồi bật **Javis**. Thử:

- "Dùng Javis: có những công cụ gì?"
- "Doanh thu tuần này so với tuần trước thế nào?"
- "Nhắc tôi 8 giờ sáng mai gọi nhà cung cấp."

Mỗi lần ChatGPT định làm một việc có tác động thật (gửi tin, tạo đơn...), nó sẽ **hỏi bạn xác nhận** trước khi gọi.

---

## Mức quyền

Chọn ở khối **Dùng Javis ngay trong ChatGPT** trên thẻ ChatGPT. Đổi xong có hiệu lực ngay, không cần kết nối lại.

| Mức | ChatGPT được làm gì |
|---|---|
| **Toàn quyền** (mặc định) | Đọc dữ liệu và làm việc thật: gửi tin, tạo đơn, đăng bài |
| **Tự làm có giới hạn** | Đọc dữ liệu và viết nháp, không làm việc ra bên ngoài |
| **Chỉ đọc và gợi ý** | Chỉ đọc, không ghi file, không làm việc ra bên ngoài |

Javis tự chặn ở phía mình theo mức đã chọn. ChatGPT không tự nâng quyền được.

## Ngắt kết nối

- **Tạm dừng:** bấm **Tắt** trên khối. Kết nối cũ giữ nguyên, bật lại là dùng tiếp.
- **Ngắt hẳn:** bấm **Ngắt mọi kết nối**. Muốn dùng lại thì làm lại từ bước 4.

---

## Điều cần biết trước

- **Bạn chat trong ChatGPT, không phải trong Javis.** Cuộc chat nằm ở lịch sử của ChatGPT. Đây không phải một model trong ô chọn model của Javis.
- **Việc nền vẫn chạy bằng model của Javis.** Nhắc lịch tự chạy, vòng lặp, bot Telegram không có ai gõ vào ChatGPT, nên chúng vẫn dùng model bạn chọn ở trang Models (ví dụ ChatGPT qua Codex).
- **Javis làm việc trên brain đang mở gần nhất** (brain của cuộc trò chuyện gần nhất trên dashboard). Kết quả mỗi công cụ có ghi rõ đang ở brain nào.
- **Developer mode là tính năng OpenAI còn gắn nhãn thử nghiệm.** Giao diện và tên mục của nó có thể đổi.

## Khi không chạy

| Bạn thấy | Nguyên nhân | Làm gì |
|---|---|---|
| Không có mục Developer mode | Gói miễn phí, hoặc đang ở app điện thoại | Dùng gói trả phí, mở chatgpt.com trên máy tính |
| Không có nút Create connector (gói Business) | Quản trị viên chưa cho phép | Làm bước 2 |
| ChatGPT báo không kết nối được server | Địa chỉ không phải https, hoặc khối đang Tắt | Xem lại "Cần có gì" và bước 1 |
| Trang Javis báo "Kết nối ChatGPT đang tắt" | Khối đang Tắt | Bấm Bật rồi kết nối lại từ ChatGPT |
| Trang Javis báo "Yêu cầu này đã quá hạn" | Để trang Cho phép mở quá 10 phút | Kết nối lại từ ChatGPT |
| Đang dùng tốt bỗng bắt kết nối lại | 30 ngày không dùng, hoặc đã bấm Ngắt mọi kết nối | Kết nối lại từ ChatGPT |
