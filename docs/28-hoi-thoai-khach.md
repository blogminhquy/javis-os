# Hội thoại khách (Hộp thư)

***Tiếng Việt** · [English](en/28-customer-conversations.md)*

Mọi tin khách nhắn cho **bot chuyên trách** (Telegram hoặc Zalo Bot) và cho **tài khoản Zalo cá nhân** đã nối đều được gom về một hộp thư trong Javis. Bạn đọc lại cuộc trò chuyện giữa khách và bot, thấy cuộc nào bot đang bí, và **tiếp quản** một cuộc chat khi cần người thật.

Đây là bản đầu tiên của lớp Hội thoại trong Chatbot V2: mới là **trình xem** cộng tiếp quản. Trả lời khách ngay từ Javis, thẻ khách, nhắc theo dõi sẽ tới ở các bản sau, trên cùng nền dữ liệu này.

## Mở ở đâu trong Javis

Thanh điều hướng bên trái, nhóm **Năng lực**, mục **Hội thoại**. Ở trang **Chatbot**, mỗi thẻ bot có nút **Hội thoại** mở thẳng hộp thư đã lọc theo bot đó.

Nói bằng lời cũng được: "mở hộp thư khách", "xem tin nhắn khách". Nói "hội thoại" trần vẫn ra trang Trò chuyện như trước.

## Mô hình

Bốn khái niệm, đọc một lần rồi khỏi đoán:

| | Là gì |
|---|---|
| **Chatbot** | Một nhân viên AI: Agent, brain riêng, mức quyền, kênh nó được đứng. |
| **Kênh** | Nơi khách nhắn tới: Telegram, Zalo Bot, Zalo cá nhân. Sau này thêm Zalo OA, Facebook, Web Chat. |
| **Hội thoại** | Một phiên trao đổi với một khách (hoặc một nhóm) trên một kênh. |
| **Hộp thư** | Nơi AI và người thật cùng vận hành hội thoại: đọc, tiếp quản, trả lại AI. |

Bên dưới, mọi kênh đều đưa tin về **một khuôn chung** rồi vào cùng một kho: tài khoản kênh, khách, hội thoại, tin. Hộp thư không cần biết tin đến từ Telegram hay Zalo.

## Trang Hội thoại

Đầu trang là bốn con số: tổng hội thoại, hội thoại có tin hôm nay, chưa đọc, và cuộc đang do người thật xử lý.

Bên trái là danh sách hội thoại, mới nhất trước. Mỗi dòng: tên khách (hoặc tên nhóm), logo kênh, tin cuối, giờ, và số tin chưa đọc. Có ô tìm theo tên hoặc nội dung, chip lọc theo kênh (chỉ hiện khi có từ hai kênh), và ô chọn bot (chỉ hiện khi có từ hai bot).

Bấm một hội thoại là lịch sử tin hiện bên phải: tin khách bên trái, câu bot và câu bạn tự nhắn từ điện thoại bên phải. Lượt bot bị gãy cũng nằm đó kèm lý do kỹ thuật, để bạn phân biệt "bot trả lời sai" với "bot đang hỏng".

Trên điện thoại trang chỉ một cột: bấm một hội thoại là mở lịch sử, có nút quay lại. Trang tự làm mới mỗi vài giây, không cần tải lại.

## Tiếp quản và trả lại AI

Ở đầu một hội thoại của bot có nút **Tiếp quản**. Bấm là bot **im** ở đúng cuộc chat đó: tin khách vẫn vào hộp thư, nhưng Javis không gọi engine trả lời nữa. Bạn trả lời khách trong app Telegram hoặc Zalo như bình thường, xong bấm **Trả lại AI**.

Hai điều nên biết:

- Lượt bot đang soạn dở đúng lúc bạn bấm Tiếp quản vẫn gửi nốt câu đó. Cắt ngang một câu đang gửi còn khó hiểu hơn với khách.
- Tiếp quản là theo **từng cuộc chat**, không tắt bot. Các khách khác vẫn được bot trả lời.

## Kênh đổ vào hộp thư

Bấm nút **Kênh** ở đầu trang để xem nguồn tin.

**Bot chuyên trách** ghi tự động khi đang bật. Không cần cài gì thêm: mỗi lượt bot trả lời khách là một tin khách và một câu bot vào kho. Lệnh `/help`, `/id`, `/nhanvien` cũng là hội thoại nên cũng được ghi. Tin trong nhóm mà bot chưa được cho phép thì **không** vào kho.

**Zalo cá nhân** là kênh quan trọng với khách Việt Nam, vì không phải ai bán hàng cũng có Zalo OA. Tài khoản đã quét QR ở trang **Kết nối** (Zalo Agent MCP) hiện ở đây với một công tắc **Ghi hội thoại**. Bật lên là Javis đọc tin mới mỗi 20 giây qua MCP và đổ vào hộp thư.

Ba điều về Zalo cá nhân, nói thẳng:

- **Mặc định tắt.** Bật là giữ phiên Zalo của bạn sống liên tục qua API không chính thức, tức tài khoản đăng nhập 24/7 trên máy chạy Javis. Đó là lựa chọn của bạn, không phải của Javis. Nên dùng tài khoản phụ.
- **Chỉ lưu từ lúc bật.** Không kéo lịch sử cũ. Tin do chính bạn gửi từ điện thoại hiện là tin "Bạn".
- **Bot chưa tự trả lời qua kênh này.** Gửi tin dưới danh tính chính bạn là chuyện phải cân nhắc riêng; ở bản này Zalo cá nhân là kênh đọc.

## Dữ liệu lưu ở đâu, giữ gì

Kho nằm trong thư mục trạng thái của Javis (`customer_conversations.sqlite3`), tách khỏi kho phiên chat. Giữ **chữ** lâu dài; ảnh, file, tin thoại chỉ giữ loại tin và mô tả, file gốc theo hạn dọn của Javis. Tin trùng (đọc lại cùng một tin sau khi khởi động lại) không sinh dòng thứ hai.

Xoá một bot **không** xoá hội thoại của nó: lịch sử khách là tài sản của bạn.

## Cho ai muốn nối thêm kênh

Một kênh mới chỉ cần đưa tin về khuôn chung (`channel`, `account_id`, `external_chat_id`, `sender_type`, `text`, `external_message_id`, `created_at`) rồi gọi kho. Hộp thư và phần tiếp quản dùng được ngay, không phải sửa giao diện. Đường API:

- `GET /conversations` danh sách kèm số liệu, lọc theo `channel`, `bot_id`, `q`.
- `GET /conversations/{id}/messages` lịch sử tin.
- `POST /conversations/{id}/read`, `POST /conversations/{id}/mode` (`ai` hoặc `human`).
- `GET /conversations/channels`, `POST /conversations/zalo/{conn_id}/watch`.

## Xử lý lỗi

- **Bot đang bật mà không thấy hội thoại nào**: kho chỉ ghi từ bản này trở đi; nhắn thử cho bot một câu. Nếu vẫn trống, xem tab Nhật ký của bot ở trang Chatbot.
- **Zalo cá nhân báo lỗi đỏ ở mục Kênh**: thường là phiên QR hết hạn hoặc máy thiếu Node.js 20. Vào trang Kết nối kiểm tra kết nối Zalo, quét QR lại nếu cần. Vòng đọc tự thử lại sau 90 giây.
- **Bấm Tiếp quản mà bot vẫn trả lời một câu**: đó là lượt đã chạy dở từ trước khi bấm. Từ tin sau bot im.

## Muốn hơn thế: gói Quản lý khách hàng (CRM)

Kho cài đặt có gói **Quản lý khách hàng (CRM)** (`javis.khach-hang-crm`, cần bản 0.60.1 trở lên) đặt lên chính hộp thư này. Cài xong hỏi Javis bằng lời: "khách nào chờ hơn 2 tiếng chưa được trả lời", "chị Lan đã hỏi gì", "gắn tag VIP cho chị Lan", "tuần này bao nhiêu khách mới", "xuất danh sách khách đã hỏi giá ra Excel". Kèm một trợ lý chăm sóc khách và một quy trình rà soát mỗi ngày. Gói chỉ đọc hộp thư và ghi tag, ghi chú lên khách; không gửi tin cho ai.

## Tham khảo

- [Chatbot (Bot chuyên trách)](25-chatbot.md)
- [Kênh Zalo Bot](26-kenh-zalo-bot.md)
- [Zalo Agent MCP](12-zalo.md)
