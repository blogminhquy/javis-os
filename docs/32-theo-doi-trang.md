# 32 - Theo dõi trang web (không tốn token)

***Tiếng Việt** · [English](en/32-page-watch.md)*

Từ 0.239.0 Javis canh được một trang web theo lịch mà **không tốn token**. Mỗi lượt canh Javis chỉ tải trang và so chữ với lần trước, không gọi AI. Có chuyện mới thì báo về khung chat và hòm thư.

Dùng khi việc cần làm chỉ là canh một trang: giá bên đối thủ, offer mới trên WarriorPlus, trang chính sách quảng cáo, hàng về. Trước đây phải dựng loop, mà mỗi vòng loop là một lượt gọi AI.

| Báo khi | Nghĩa |
|---|---|
| **Trang thay đổi** | Có dòng mới, dòng đổi số (giá, tồn kho) hoặc dòng bị xoá |
| **Xuất hiện cụm chữ** | Ví dụ "Còn hàng". Báo một lần khi nó xuất hiện, không báo lại khi nó vẫn còn đó |
| **Có giá dưới ngưỡng** | Ví dụ ngưỡng "1 triệu": báo khi trang có giá thấp hơn 1.000.000đ |

## Tạo bằng lời trong chat

Nói với Javis như: "canh giúp anh trang này, giá áo xuống dưới 900k thì báo" kèm đường link. Javis dùng tool `javis_watch` và báo lại mã mục theo dõi. Mọi engine đều dùng được.

## Tạo trên trang Việc định kỳ

1. Vào **Việc định kỳ**, mở tab **Theo dõi trang**.
2. Dán **Địa chỉ trang**, chọn **Báo khi**, điền cụm chữ hoặc ngưỡng giá nếu cần.
3. Đặt **Canh mỗi** (từ 5 phút tới 7 ngày, mặc định 60 phút) và một tên dễ nhớ.
4. Bấm **Bắt đầu theo dõi**. Lượt canh đầu chạy trong vòng 30 giây.

Mỗi mục có nút **Canh ngay**, **Tạm dừng** / **Mở lại** và **Xoá**. Thẻ hiện số lần đã canh, lần báo gần nhất và lỗi gần nhất nếu có.

## Javis đọc được những kiểu giá nào

`1.250.000đ`, `990.000 ₫`, `2.000.000 VND`, `4.500.000 đồng`, `1,25 triệu`, `1tr2`, `250k`, `99K`, `$12.99`, `1,299.00 USD`. Ngưỡng ghi theo kiểu nào cũng được. Ngưỡng bằng đồng chỉ so với giá bằng đồng, ngưỡng bằng đô chỉ so với giá bằng đô.

## Vì sao không báo rác

- **Thời gian tự nhảy không tính là đổi:** "3 phút trước", "1 giờ trước", "hôm qua", "vừa xong", "posted 2 hours ago".
- **Dòng chỉ đổi con số** được báo là "Cập nhật", tách khỏi "Mới" và "Đã xoá", để nhìn là thấy giá nào đổi.
- **Mỗi lần báo có khoá riêng:** máy chủ khởi động lại cũng không báo trùng.
- **Lượt đầu chỉ ghi mốc** với kiểu "Trang thay đổi", từ lượt sau mới báo.

## Khi trang lỗi

Javis giãn dần lần thử: 2, 4, 8, 16 phút, tối đa 60 phút. Lỗi **5 lần liền** thì tự tạm dừng mục đó và báo bạn **đúng một lần**. Trang chạy lại thì bấm **Mở lại**.

## Tóm tắt bằng AI (tuỳ chọn)

Tick **Tóm tắt thay đổi bằng AI** thì mỗi lần có thay đổi Javis gọi model nền **một lần** để nói thay đổi đó có ý nghĩa gì. Mặc định tắt. Model chỉ nhận chữ, không có công cụ nào, và được dặn coi nội dung trang là dữ liệu chứ không phải chỉ dẫn.

## Giới hạn

- Javis đọc chữ của trang như trình duyệt tải về lần đầu. Trang chỉ hiện nội dung sau khi chạy JavaScript (một số sàn, trang cần đăng nhập) thì Javis không thấy phần đó. Khi ấy dùng loop với công cụ trình duyệt.
- Trang có đồng hồ, mã chống bot hay quảng cáo đổi liên tục có thể báo "thay đổi" khá thường. Chuyển sang kiểu **Xuất hiện cụm chữ** hoặc **Có giá dưới ngưỡng** cho chắc.
- Chỉ theo dõi được trang công khai ở cổng 80 hoặc 443. Địa chỉ trỏ vào mạng nội bộ (máy chủ của bạn, router, máy ảo đám mây) bị chặn, kể cả khi trang công khai chuyển hướng vào đó.
- Báo về khung chat web và hòm thư. Muốn nhận trên điện thoại thì nối Telegram hoặc Zalo, xem [Telegram](11-telegram.md).

## Dữ liệu nằm ở đâu

File `web_watch.sqlite3` trong thư mục state của Javis (`JAVIS_STATE_DIR`), cạnh `kanban.sqlite3`.

## Liên quan

- [Việc định kỳ](08-viec-dinh-ky.md)
- [Việc (Kanban)](21-viec-kanban.md)
