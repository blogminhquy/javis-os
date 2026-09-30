# Zalo: tag đúng người, ghi chú, nhắc hẹn, poll (0.65.6)

## Vấn đề

Chủ dự án (30/09/2026): trong nhóm Zalo, Javis không tag được tên chính xác người cần phản hồi (kiểu "@minhquy"), và chưa tạo được
ghi chú, nhắc hẹn hay poll trên Zalo.

MCP của `zalo-agent-cli` bản 1.6.2 chỉ phơi bảy tool và tool gửi tin (`zalo_send_message`) chỉ nhận chữ. Nhưng chính CLI đó đã có đủ bốn
việc: `msg send --mention`, `group note-create`, `reminder create`, `poll create` (đọc mã nguồn và chạy thử với Commander 14.0.3 mà CLI đóng gói).
Bản 1.6.2 là bản mới nhất trên npm, nên chờ upstream phơi thêm tool là chờ vô hạn.

## Cách làm

Cùng khuôn với `zalo-image` (0.36): một plugin đi kèm mới `zalo-group`, gọi lại chính CLI bằng phiên Zalo đã đăng nhập (đặt `HOME` vào thư mục
phiên của kết nối), không fork package, không quét QR lần hai. Năm tool, mọi engine đều gọi được qua MCP Hub:

| Tool | Việc | Mức tối thiểu |
|---|---|---|
| `zalo_group_members` | thành viên nhóm (uid + tên), hoặc tra theo tên | chỉ đọc |
| `zalo_send_mention` | gửi tin nhóm, tag đúng người | full |
| `zalo_create_note` | ghi chú nhóm, ghim được | full |
| `zalo_create_reminder` | nhắc hẹn hiện trong Zalo, có lặp | full |
| `zalo_create_poll` | poll cho nhóm | full |

Phần chạy CLI dùng chung được tách ra `server/zalo_cli.py` cho cả `zalo-image` và `zalo-group`.

## Những chỗ dễ hỏng (đã có canary trong test)

1. **Tag nhầm người.** Zalo tag bằng uid, người dùng chỉ nói tên. Tìm ở hai nơi: người đã nhắn trong nhóm (Hộp thư,
   `conversations.group_speakers`) rồi danh sách thành viên Zalo (`group info` + `group members-info`). Chuẩn hoá không phân biệt hoa thường, dấu, dấu cách.
   Khớp chính xác thắng khớp chứa. **Trùng tên hoặc không thấy thì trả lỗi kèm ứng viên, không đoán**: tag nhầm không rút lại được.
2. **Vị trí chữ.** Zalo đọc `pos:uid:len` theo đơn vị UTF-16 như JavaScript (emoji chiếm 2). Tính theo ký tự Python là vệt tô lệch.
   `@Quý` không được ăn vào `@Quýnh` (`(?!\w)`).
3. **Thứ tự tham số.** Cờ nhiều giá trị `--mention` nuốt mọi tham số đứng sau, nên tham số vị trí đứng trước, cờ đứng sau.
   Tham số bắt đầu bằng `-` bị coi là cờ, khi đó cờ đứng trước rồi `--`.
4. **Mã thoát nói dối.** CLI không thoát mã khác 0 khi Zalo từ chối (`error()` chỉ in "✗ ..." ra stderr). Thành công = mã 0 **và** có JSON ở stdout.
   Cũng vá luôn cho `zalo_send_image`, trước đó báo "đã gửi" cả khi Zalo từ chối.
5. **Giờ nhắc hẹn.** CLI đọc `--time` theo múi giờ của MÁY; người dùng nói theo giờ Javis. VPS ở UTC thì "9 giờ sáng" thành 16 giờ nếu gửi nguyên chữ.
   Đổi qua đồng hồ máy trước khi gọi, từ chối giờ đã qua.
6. **Windows + cmd.exe.** `npx.cmd` chạy qua `cmd /c` thì `& | ^ %` trong nội dung tin bị cmd diễn giải (hỏng tin và là lỗ hổng chèn lệnh).
   Chạy `node npx-cli.js` thẳng; rơi về cmd thì từ chối tham số nguy hiểm.
7. **Quá giờ = kết cục không rõ.** CLI có thể đã tạo xong rồi mới bị giết. Lỗi nói "không rõ đã tạo chưa, xem lại nhóm rồi mới thử lại", để khỏi ra hai poll.
8. **Nhiều tài khoản Zalo.** Không nêu `connection_id` thì từ chối và liệt kê, không đoán (gửi nhầm tài khoản là gửi dưới danh tính người khác).

## Ngoài phạm vi

- Bot tự tag người nó đang trả lời: làm ở 0.65.7 (đổi đường gửi của bot sang CLI, chậm thêm vài giây mỗi câu).
- Sửa hoặc xoá ghi chú, nhắc hẹn, poll; bình chọn poll; khoá poll. CLI có, chưa ai đòi.
- Thêm chỉ dẫn dài vào system prompt: chỉ một dòng ngắn ở `CLAUDE.md`, chi tiết nằm trong mô tả tool.

## Kiểm

`tests/python/test_zalo_group.py` (chạy bằng CLI giả: kiểm đúng lệnh dựng ra, vị trí tag, tìm tên, trùng tên, giờ nhắc, lỗi Zalo, nhiều tài khoản,
khai báo plugin) và `tests/python/test_zalo_cli.py` (thứ tự tham số, Windows, đọc kết quả, HOME, hết giờ). Việc gửi thật vào nhóm Zalo phải do
chủ thử trên tài khoản thật, sandbox không có nick.
