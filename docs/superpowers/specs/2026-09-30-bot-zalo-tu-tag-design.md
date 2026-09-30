# Bot trong nhóm Zalo tự tag người nó đang trả lời (0.65.7)

## Vấn đề

Chủ dự án (30/09/2026): trong nhóm Zalo, khách hỏi thì bot nên mở đầu câu trả lời bằng "@Minh Quý ...", để người hỏi được báo và cả nhóm biết
bot đang nói với ai. Tool gửi tin của MCP `zalo-agent-cli` chỉ nhận chữ nên không tag được; chính CLI đó thì có `msg send --mention` (đã
dùng ở 0.65.6 cho tool `zalo_send_mention`, xem `2026-09-30-zalo-tag-ghi-chu-poll-design.md`).

## Quyết định

- **Không có ô cài đặt.** Bật mặc định cho mọi nhóm Zalo cá nhân mà bot đang đứng (chủ muốn ít cài đặt, máy tự lo).
- **Chỉ trong nhóm.** Chat riêng không cần tag.
- **Người được tag = người gửi tin bot đang trả lời** (`meta["user_id"]`, `meta["user_name"]` do vòng đọc cấp). Nút "Trả lời giúp tin này"
  ở Hòm thư cũng tag người gửi tin khách cuối, cho khớp với bot tự trả lời. Chủ gõ tay thì không tag.
- **Chậm thêm 2 đến 4 giây mỗi câu** (chạy thêm một tiến trình CLI). Chủ đã chấp nhận.

## Cách làm

`channels.zalo_personal.gui(tk, chat_id, text, chat_type, mention=None)`: khi là nhóm và có `mention={"uid","name"}` thì gửi bằng
`zalo_cli.run_cli` (`msg send <nhóm> <chữ> -t 1 --mention pos:uid:len`). `channels.gui` chuyển `**extra` cho kênh (chỉ Zalo cá nhân dùng).
`Transport._gui` và route `POST /conversations/{id}/ai-reply` là hai nơi truyền người cần tag.

Chữ: model đã tự viết "@Tên" thì tag đúng chỗ đó, chưa thì đặt "@Tên " ở đầu tin. Vị trí đo theo UTF-16 (emoji chiếm 2);
"@Quý" không ăn vào "@Quýnh".

## Những chỗ dễ hỏng (đã có canary trong `test_bot_zalo_tag.py` và `test_bot_zalo_nhom.py`)

1. **Hai tin dưới tên chủ.** Hết giờ là kết cục không rõ (CLI có thể đã gửi xong mới bị giết). Chỉ khi CLI thất bại RÕ RÀNG mới rơi về gửi
   thường bằng MCP. Quá giờ thì trả lỗi (ghi nhật ký bot), không gửi lại.
2. **Bot tự khoá miệng.** Tiếng vọng của tin có tag mang cả "@Tên" nên không khớp câu bot đã nhớ; vòng đọc tưởng chủ vừa tự nhắn và bot im
   10 phút. Nhớ luôn bản đã tag (`ghi_da_gui`) TRƯỚC khi gửi. Thử cả kiểu có cờ isSelf lẫn không có.
3. **Tag hỏng mãi làm chậm mọi câu.** Hỏng 3 lần liên tiếp thì nghỉ tag 10 phút; tin vẫn đi bằng MCP như cũ. Một lần thành công thì đếm lại.
4. **uid vào tham số lệnh.** Chỉ nhận uid toàn số; chưa biết tên người hỏi thì gửi thường.

## Ngoài phạm vi

- Tag nhiều người, tag người được nhắc trong câu trả lời (đã có `zalo_send_mention` cho việc đó, do model chủ động gọi).
- Tag ở nhóm Zalo Bot (OA) hay Telegram: kênh khác, cơ chế khác.
- Dùng Zalo "reply" (trích dẫn) thay vì tag: CLI 1.6.2 không có cho `msg send`.

## Kiểm

CLI giả và MCP giả. Việc gửi thật vào nhóm Zalo phải do chủ thử trên nick thật (sandbox không có nick): khách hỏi trong nhóm, bot trả lời
"@Tên ...", người hỏi nhận thông báo, và bot không tự trả lời chính nó sau đó.
