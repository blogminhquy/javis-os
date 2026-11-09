---
bump: minor
title: Start-up screen, one loading look everywhere, a brain picker that exports, uploads and edits each brain
---
## vi
### Thêm mới
- **Xuất và tải lên cả bộ não bằng một file .zip:** mỗi dòng trong hộp chọn bộ não có nút Xuất. File mang theo ghi chú, ảnh, agent, skill, workflow và bộ nhớ, không mang theo token, chat thô hay lịch sử git. Nút "Tải lên bộ não (.zip)" luôn tạo một bộ não mới, không đè bộ não đang có. Plugin, vòng lặp và nhắc việc đi kèm file đều được tắt sẵn, bật lại ở trang tương ứng nếu cần.
- **Đổi tên và xoá ngay trên từng dòng của hộp chọn bộ não**, cuối hộp có ba nút Tạo bộ não, Tải lên bộ não và Mở thư mục ngoài. Bốn nút rời cạnh hộp chọn trên thanh trên cùng đã bỏ.

### Cải thiện
- **Màn hình khởi động:** mở Javis là thấy logo cùng dòng "Đang khởi động Javis…" cho tới khi trang đầu tiên đã có đủ dữ liệu. Javis vừa cập nhật hay khởi động lại thì màn này báo thêm lần mở đầu có thể lâu hơn một chút.
- **Mọi màn đang chờ tải dùng chung một hiệu ứng** như trang Cộng sự: vòng xoay nhỏ kèm chữ "Đang tải", trang lớn thì vòng xoay ở giữa. Trang đang nạp không còn hiện nhầm câu "đang phát triển".
- **Số node và liên kết trên thanh trên cùng chỉ hiện ở màn mạng nơ-ron**, các trang khác gọn hơn.
- **Hộp chọn bộ não ghi số node và số liên kết của từng bộ não**, đúng như đồ thị đếm. Số chỉ được đếm khi mở hộp, nên không làm chậm lúc tải trang.

## en
### Added
- **Export and upload a whole brain as one .zip file:** each row of the brain picker has an Export button. The file carries notes, images, agents, skills, workflows and memory, and leaves out tokens, raw chats and git history. "Upload a brain (.zip)" always makes a new brain and never overwrites one. Plugins, loops and reminders that come with the file arrive switched off; turn them on where they live if you want them.
- **Rename and delete right on each row of the brain picker**, with New brain, Upload a brain and Open an outside folder at the bottom. The four separate buttons beside the picker in the top bar are gone.

### Improved
- **Start-up screen:** opening Javis shows the logo and "Starting Javis…" until the first page has its data. Right after an update or a restart it also says the first open can take a little longer.
- **Every screen that waits for data uses the Partners page's loading look:** a small spinner with "Loading", or a centered one for a whole page. A page still loading no longer says "in development" by mistake.
- **The node and link counts in the top bar show only on the neural graph screen**, so other pages are tidier.
- **The brain picker shows each brain's node and link counts**, as its graph counts them. They are counted only when the picker opens, so page load is not slowed.
