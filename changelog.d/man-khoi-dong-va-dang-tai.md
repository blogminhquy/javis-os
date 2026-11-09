---
bump: minor
title: Start-up screen, one loading look everywhere, node and link counts in the brain picker
---
## vi
### Cải thiện
- **Màn hình khởi động:** mở Javis là thấy logo cùng dòng "Đang khởi động Javis…" cho tới khi trang đầu tiên đã có đủ dữ liệu. Javis vừa cập nhật hay khởi động lại thì màn này báo thêm lần mở đầu có thể lâu hơn một chút.
- **Mọi màn đang chờ tải dùng chung một hiệu ứng** như trang Cộng sự: vòng xoay nhỏ kèm chữ "Đang tải", trang lớn thì vòng xoay ở giữa. Trang đang nạp không còn hiện nhầm câu "đang phát triển".
- **Số node và liên kết trên thanh trên cùng chỉ hiện ở màn mạng nơ-ron**, các trang khác gọn hơn.
- **Hộp chọn bộ não ghi số node và số liên kết của từng bộ não**, đúng như đồ thị đếm. Số chỉ được đếm khi mở hộp, nên không làm chậm lúc tải trang.

## en
### Improved
- **Start-up screen:** opening Javis shows the logo and "Starting Javis…" until the first page has its data. Right after an update or a restart it also says the first open can take a little longer.
- **Every screen that waits for data uses the Partners page's loading look:** a small spinner with "Loading", or a centered one for a whole page. A page still loading no longer says "in development" by mistake.
- **The node and link counts in the top bar show only on the neural graph screen**, so other pages are tidier.
- **The brain picker shows each brain's node and link counts**, as its graph counts them. They are counted only when the picker opens, so page load is not slowed.
