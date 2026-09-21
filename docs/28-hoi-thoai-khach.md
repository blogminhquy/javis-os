# Chatbot (hòm thư bot, tài khoản bot, tạo chatbot)

***Tiếng Việt** · [English](en/28-customer-conversations.md)*

Mọi tin khách nhắn cho **bot chuyên trách** (Telegram hoặc Zalo Bot) và cho **tài khoản Zalo cá nhân** đã nối đều được gom về một hộp thư trong Javis. Bạn đọc lại cuộc trò chuyện giữa khách và bot, thấy cuộc nào bot đang bí, và **tiếp quản** một cuộc chat khi cần người thật.

Từ bản 0.61.0 trang này gộp luôn phần Chatbot: **một mục trên thanh bên, ba tab** (Hòm thư bot, Tài khoản bot, Tạo chatbot), và bạn **trả lời khách ngay trong Hòm thư bot**.

## Mở ở đâu trong Javis

Thanh điều hướng bên trái, nhóm **Năng lực**, mục **Chatbot**. Trong trang có ba tab:

- **Hòm thư bot**: mọi tin khách, đọc lại, tiếp quản, trả lời.
- **Tài khoản bot**: mọi tài khoản khách nhắn tới (bot Telegram, bot Zalo, Zalo cá nhân...) trong brain đang mở, thêm tài khoản, bật ghi.
- **Tạo chatbot**: nhân viên AI đứng trực các tài khoản đó. Xem [Chatbot](25-chatbot.md).

Nói bằng lời cũng được: "mở hộp thư khách", "hòm thư bot", "tài khoản bot", và "mở chatbot" vẫn tới đúng tab Tạo chatbot. Nói "hội thoại" trần vẫn ra trang Trò chuyện như trước.

## Mô hình

Bốn khái niệm, đọc một lần rồi khỏi đoán:

| | Là gì |
|---|---|
| **Chatbot** | Một nhân viên AI: Agent, brain riêng, mức quyền, và những tài khoản kênh nó đứng trực (một bot trực được nhiều tài khoản). |
| **Kênh** | Nơi khách nhắn tới. Mỗi kênh có nhiều **tài khoản**: một token bot Telegram, một token Zalo Bot, một tài khoản Zalo cá nhân đã quét QR. Sau này thêm Zalo OA, Facebook, Web Chat. |
| **Hội thoại** | Một phiên trao đổi với một khách (hoặc một nhóm) trên một kênh. |
| **Hòm thư bot** | Nơi AI và người thật cùng vận hành hội thoại: đọc, tiếp quản, trả lại AI. |

Bên dưới, mọi kênh đều đưa tin về **một khuôn chung** rồi vào cùng một kho: tài khoản kênh, khách, hội thoại, tin. Hòm thư bot không cần biết tin đến từ Telegram hay Zalo.

## Tab Hòm thư bot

Đầu tab là bốn con số: tổng hội thoại, hội thoại có tin hôm nay, chưa đọc, và cuộc đang do người thật xử lý.

Bên trái là danh sách hội thoại, mới nhất trước. Mỗi dòng: tên khách (hoặc tên nhóm), logo kênh, tin cuối, giờ, và số tin chưa đọc. Có ô tìm theo tên hoặc nội dung, chip lọc theo kênh (chỉ hiện khi có từ hai kênh), và ô chọn bot (chỉ hiện khi có từ hai bot).

Bấm một hội thoại là lịch sử tin hiện bên phải: tin khách bên trái, câu bot và câu bạn tự nhắn từ điện thoại bên phải. Lượt bot bị gãy cũng nằm đó kèm lý do kỹ thuật, để bạn phân biệt "bot trả lời sai" với "bot đang hỏng".

Trên điện thoại trang chỉ một cột: bấm một hội thoại là mở lịch sử, có nút quay lại. Trang tự làm mới mỗi vài giây, không cần tải lại.

## Trả lời khách, tiếp quản và trả lại AI

Dưới cùng một hội thoại là ô soạn tin: gõ rồi **Enter** để gửi (Shift+Enter xuống dòng). Tin đi qua đúng kênh của cuộc chat: bot Telegram hay Zalo Bot gửi bằng token của tài khoản đó, Zalo cá nhân gửi qua chính tài khoản bạn đã quét QR, **dưới tên bạn** (ô soạn tin nói rõ điều này). Kênh nào chưa gửi được từ Javis thì ô soạn tin thay bằng một dòng nói vậy.

Gửi từ đây ở một cuộc chat có bot là bạn **tiếp quản** cuộc đó: bot im với khách này cho tới khi bạn bấm **Trả lại AI**. Không thì khách đọc hai giọng một lúc. Nút **Tiếp quản** ở đầu hội thoại làm y như vậy mà không cần gửi gì; bấm xong bạn trả lời trong app của kênh cũng được.

Hai điều nên biết:

- Lượt bot đang soạn dở đúng lúc bạn bấm Tiếp quản vẫn gửi nốt câu đó. Cắt ngang một câu đang gửi còn khó hiểu hơn với khách.
- Tiếp quản là theo **từng cuộc chat**, không tắt bot. Các khách khác vẫn được bot trả lời.

## Tab Tài khoản bot

Mọi tài khoản khách nhắn tới hiện thành **cùng một kiểu thẻ**, bất kể kênh: logo và tên kênh, tên tài khoản, trạng thái (đang chạy, đang tắt, lỗi kèm lý do), bot đang trực, số hội thoại và số chưa đọc, và các năng lực của kênh đó (vào nhóm, gửi file, trả lời từ Javis). Không kênh nào có mục riêng, kể cả Zalo. Kênh thêm về sau chỉ việc xuất hiện thêm một thẻ.

Có hai loại tài khoản, khác nhau ở cách có nó chứ không ở cách hiện ra:

**Tài khoản bot** (Telegram, Zalo Bot) là một token. Bấm **Thêm tài khoản**, chọn loại kênh, dán token, bấm **Kiểm tra** để Javis hỏi đúng nền tảng token đó là bot nào, đặt tên gợi nhớ rồi Lưu. Tài khoản bot ghi vào hộp thư khi bot trực nó đang bật; chưa có bot trực thì thẻ nói thẳng và có nút **Tạo bot trực** mở sẵn form ở tab Tạo chatbot.

### Tài khoản bot thuộc về một brain (0.62.4)

Trước 0.62.4 tab này hiện tài khoản của **mọi** brain, vì một token Telegram là tài khoản có thật ngoài đời nên nó không thuộc brain nào cả. Đúng về kỹ thuật nhưng khó dùng: đứng ở brain của mình mà nhìn một danh sách trộn lẫn thì không biết cái nào là của mình.

Từ 0.62.4 mỗi tài khoản có một **brain chủ**:

- **Thêm ở brain nào thì thuộc brain đó.** Tab chỉ hiện tài khoản của brain đang mở.
- **Form tạo bot cũng chỉ cho chọn tài khoản trong brain đó**, nên không còn tạo ra liên kết chéo brain.
- **Nút "Xem mọi brain"** ở đầu danh sách để tìm lại một tài khoản lỡ thêm nhầm chỗ. Khi đó mỗi thẻ tự ghi brain của nó.
- **Đổi chủ:** bấm **Sửa**, chọn lại ở mục **Brain của tài khoản**. Lịch sử hội thoại giữ nguyên, vì nó khoá theo id tài khoản chứ không theo brain.
- **Tài khoản cũ không đoán ra được chủ** (lúc nâng cấp không có bot nào trực nó) thì để **chưa gán** và hiện ở **mọi** brain kèm ghi chú. Chủ ý: thà thấy thừa một thẻ còn hơn có một token tồn tại mà không màn hình nào hiện ra, không ai xoá hay gắn lại được. Gắn nó vào một bot là nó nhận brain của bot đó.

Zalo cá nhân (`kind: account`) không bị lọc: nó là một kết nối ở trang **Kết nối**, không thuộc brain nào, nên luôn hiện.

Đây là bước đầu của hướng dài hơn: chia quyền quản lý tài khoản cho brain, rồi tới agent, skill, workflow và chatbot, để sau này lên được bản nhiều người dùng.

**Xoá một tài khoản:** bấm **Xoá**. Nếu đang có bot trực nó, Javis nói rõ bot nào, ở brain nào, rồi hỏi một câu duy nhất: gỡ khỏi bot đó rồi xoá luôn? Đồng ý là xong trong một lần, không phải đổi brain rồi đi tìm bot để tự gỡ. Bot vẫn còn và vẫn trực các tài khoản khác của nó. Nếu đó là tài khoản **duy nhất** của bot thì Javis nói trước, và sau khi xoá sẽ tắt bot đó đi (bản ghi bot vẫn còn, gắn tài khoản khác vào là bật lại được). Hội thoại đã ghi vẫn nằm nguyên trong hộp thư.

**Tài khoản của chính bạn** (Zalo cá nhân) đến từ trang **Kết nối** (quét QR ở Zalo Agent MCP) và hiện ở đây với công tắc **Ghi hội thoại**. Bật lên là Javis đọc tin mới mỗi 20 giây qua MCP và đổ vào hộp thư. Ba điều về kênh này, nói thẳng:

- **Mặc định tắt.** Bật là giữ phiên Zalo của bạn sống liên tục qua API không chính thức, tức tài khoản đăng nhập 24/7 trên máy chạy Javis. Đó là lựa chọn của bạn, không phải của Javis. Nên dùng tài khoản phụ.
- **Chỉ lưu từ lúc bật.** Không kéo lịch sử cũ. Tin do chính bạn gửi từ điện thoại hiện là tin "Bạn".
- **Không có bot trực.** Trả lời từ Hòm thư bot là gửi dưới tên bạn; bot tự trả lời qua kênh này là chuyện phải cân nhắc riêng.

## Dữ liệu lưu ở đâu, giữ gì

Kho nằm trong thư mục trạng thái của Javis (`customer_conversations.sqlite3`), tách khỏi kho phiên chat. Giữ **chữ** lâu dài; ảnh, file, tin thoại chỉ giữ loại tin và mô tả, file gốc theo hạn dọn của Javis. Tin trùng (đọc lại cùng một tin sau khi khởi động lại) không sinh dòng thứ hai.

Xoá một bot **không** xoá hội thoại của nó, và cũng không xoá tài khoản kênh nó trực: lịch sử khách là tài sản của bạn, token là thứ dùng lại được. Bot tạo trước 0.61.0 (token nằm trong bot) tự chuyển sang mô hình tài khoản khi bạn cập nhật; token, hội thoại, nhóm cho phép đều giữ nguyên.

## Cho ai muốn nối thêm kênh

Từ 0.61.0 mọi thứ lõi biết về một kênh nằm trong **sổ đăng ký kênh** (`server/channels/`, mỗi kênh một file). Một file kênh khai: id, tên, khoá logo, loại (`bot` dùng token, `account` dùng phiên đăng nhập sẵn có, `webhook` cho nền tảng gọi ngược), năng lực (nhóm, gửi chữ, gửi file), cách lấy token; và một bộ hàm: kiểm token và lớp long-poll (loại bot), liệt kê tài khoản và bật ghi (loại account), `gui` để trả lời từ Javis. Tin nhận về thì đưa về khuôn chung (`channel`, `account_id`, `external_chat_id`, `sender_type`, `text`, `external_message_id`, `created_at`) rồi gọi kho.

Thêm một kênh = thêm một file ở sổ, một dòng đăng ký, một logo trong `icons.js`. Kho bot, bộ giám sát, API và cả ba tab tự nhận, không sửa gì khác. Chi tiết ở `docs/dev/2026-09-kenh-hoi-thoai-spec.md`. Đường API:

- `GET /channels` các loại kênh và năng lực; `GET /channels/accounts` mọi tài khoản, một khuôn.
- `POST /channels/verify-token`, `POST /channels/accounts`, `POST /channels/accounts/{id}/update`, `.../watch` (loại account), `.../delete`.
- `GET /conversations` danh sách kèm số liệu, lọc theo `channel`, `bot_id`, `account_id`, `q`.
- `GET /conversations/{id}/messages` lịch sử tin; `POST /conversations/{id}/reply` trả lời qua kênh.
- `POST /conversations/{id}/read`, `POST /conversations/{id}/mode` (`ai` hoặc `human`).
- `GET /conversations/channels` và `POST /conversations/zalo/{conn_id}/watch` là bí danh cũ, còn giữ.

## Xử lý lỗi

- **Bot đang bật mà không thấy hội thoại nào**: kho chỉ ghi từ lúc kênh được nối; nhắn thử cho bot một câu. Nếu vẫn trống, xem tab Nhật ký của bot ở tab Tạo chatbot.
- **Thẻ bot báo "chưa có tài khoản kênh nào"**: bot chưa trực token nào. Bấm Sửa, tích một tài khoản có sẵn hoặc dán token mới.
- **Gửi từ Hòm thư bot báo lỗi**: câu lỗi là của chính nền tảng (token bị thu hồi, khách đã chặn bot, phiên Zalo hết hạn). Tin không đi thì không được ghi vào kho.
- **Zalo cá nhân báo lỗi đỏ ở tab Tài khoản bot**: thường là phiên QR hết hạn hoặc máy thiếu Node.js 20. Vào trang Kết nối kiểm tra kết nối Zalo, quét QR lại nếu cần. Vòng đọc tự thử lại sau 90 giây.
- **Bấm Tiếp quản mà bot vẫn trả lời một câu**: đó là lượt đã chạy dở từ trước khi bấm. Từ tin sau bot im.

## Muốn hơn thế: gói Quản lý khách hàng (CRM)

Kho cài đặt có gói **Quản lý khách hàng (CRM)** (`javis.khach-hang-crm`, cần bản 0.60.1 trở lên) đặt lên chính hộp thư này. Cài xong hỏi Javis bằng lời: "khách nào chờ hơn 2 tiếng chưa được trả lời", "chị Lan đã hỏi gì", "gắn tag VIP cho chị Lan", "tuần này bao nhiêu khách mới", "xuất danh sách khách đã hỏi giá ra Excel". Kèm một trợ lý chăm sóc khách và một quy trình rà soát mỗi ngày. Gói chỉ đọc hộp thư và ghi tag, ghi chú lên khách; không gửi tin cho ai.

## Tham khảo

- [Chatbot (Bot chuyên trách)](25-chatbot.md)
- [Kênh Zalo Bot](26-kenh-zalo-bot.md)
- [Zalo Agent MCP](12-zalo.md)
