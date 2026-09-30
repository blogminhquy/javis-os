# Chatbot (hòm thư bot, tài khoản bot, tạo chatbot)

***Tiếng Việt** · [English](en/28-customer-conversations.md)*

Mọi tin khách nhắn cho **bot chuyên trách** (Telegram hoặc Zalo Bot) và cho **tài khoản Zalo cá nhân** đã nối đều được gom về một hộp thư trong Javis. Bạn đọc lại cuộc trò chuyện giữa khách và bot, thấy cuộc nào bot đang bí, và **tiếp quản** một cuộc chat khi cần người thật.

Từ bản 0.61.0 trang này gộp luôn phần Chatbot: **một mục trên thanh bên, hai tab** (Hòm thư bot và Bot; từ 0.65.9, trước đó là ba tab Hòm thư bot, Tài khoản bot, Tạo chatbot), và bạn **trả lời khách ngay trong Hòm thư bot**.

## Mở ở đâu trong Javis

Thanh điều hướng bên trái, nhóm **Năng lực**, mục **Chatbot**. Trong trang có hai tab:

- **Hòm thư bot**: mọi tin khách, đọc lại, tiếp quản, trả lời.
- **Bot**: nhân viên AI đứng trực các kênh, kèm mục **Kênh chưa có bot** ngay dưới (bot Telegram, bot Zalo, Zalo cá nhân... trong brain đang mở, thêm kênh, bật ghi). Kênh đã có bot hiện thành chip trên thẻ bot; bấm chip để sửa hoặc xoá kênh đó. Xem [Chatbot](25-chatbot.md).

Nói bằng lời cũng được: "mở hộp thư khách", "hòm thư bot", "tài khoản bot", và "mở chatbot" vẫn tới đúng tab Bot. Nói "hội thoại" trần vẫn ra trang Trò chuyện như trước.

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

Từ 0.65.10 đầu trang gọn hơn để khung làm việc chiếm gần hết màn hình: tiêu đề **Chatbot**, hai tab, ô tìm và hàng lọc nằm trên cùng, còn danh sách và khung tin lấp đầy phần còn lại, mỗi bên cuộn riêng và ô soạn tin ghim ở đáy. Bốn thẻ số liệu và dòng phụ đề đã bỏ. Số **chưa đọc** vẫn hiện thành huy hiệu trên tab, và "người thật đang xử lý" xem bằng ô lọc **Tình trạng**.

Bên trái là danh sách hội thoại, mới nhất trước. Mỗi dòng: tên khách (hoặc tên nhóm), logo kênh, tin cuối, giờ, và số tin chưa đọc. Phía trên có ô tìm theo tên hoặc nội dung và **một hàng dropdown lọc** (từ 0.65.3, thay cho hàng chip): **Bot**, **Tình trạng** (chưa đọc, cần trả lời, tôi tiếp quản), **Loại** (chỉ nhóm hay chỉ chat riêng), và **Kênh** (chỉ hiện khi có từ hai kênh). Số hội thoại nằm ngay trong từng lựa chọn, tính trên cả hòm thư nên không nhảy khi lọc. Bộ lọc được nhớ ở trình duyệt; dòng ngay trên danh sách ghi "N hội thoại · M bộ lọc" kèm nút **Xoá lọc**. Khi có từ hai bot, mỗi dòng có thẻ tên bot (mỗi bot một màu cố định), và dòng đáng chú ý có thẻ **Cần trả lời** hoặc **Người thật**.

**"Cần trả lời" nghĩa là gì.** Khách nhắn cuối, chưa ai đáp, chưa có người tiếp quản, và: là chat riêng, hoặc là nhóm mà bot vừa **cân nhắc nói rồi im** (chưa chắc, hết hạn mức tự nói, hay bộ phán xử lỗi, trong 24 giờ qua và bạn chưa bấm Đúng/Sai). Nhóm thì phải có điều kiện thứ hai, vì bot chỉ nói khi được gọi thì khách nhắn cuối trong nhóm là chuyện bình thường; đếm hết vào thì bộ lọc đầy rác. Cần bật Tự đánh giá thì mới có dấu "bot cân nhắc" này (xem [Bộ phán xử](25-chatbot.md#bộ-phán-xử-bot-tự-quyết-nói-hay-im-và-học-từ-nhóm)).

Bấm một hội thoại là lịch sử tin hiện bên phải: tin khách bên trái, câu bot và câu bạn tự nhắn từ điện thoại bên phải. Lượt bot bị gãy cũng nằm đó kèm lý do kỹ thuật, để bạn phân biệt "bot trả lời sai" với "bot đang hỏng".

Trên điện thoại trang chỉ một cột: bấm một hội thoại là mở lịch sử, có nút quay lại. Trang tự làm mới mỗi vài giây, không cần tải lại.

## Trả lời khách, tiếp quản và trả lại AI

**Công tắc Tự động | Tôi trả lời** (từ 0.65.4) nằm ở đầu mỗi cuộc chat có bot, thay cho nút Tiếp quản nhỏ. Gạt sang **Tôi trả lời** là bạn tiếp quản; gạt về **Tự động** là trả cuộc chat lại cho bot. Bấm đúng nấc đang bật thì không làm gì. Trên điện thoại công tắc xuống một hàng riêng, rộng hết chiều ngang. Ngay trên ô nhập có **một dòng trạng thái** nói ai đang trực ("Nhi Mai đang trực cuộc chat này" hoặc "Bạn đang tiếp quản, bot im"), đứng riêng một dòng nên không lệch với ô nhập.

**Hai nút hành động** nằm ngay dưới dòng trạng thái (từ 0.65.5), cùng cao và chia đôi bề ngang:

- **Trả lời giúp tin này**: bot trả lời NGAY tin khách cuối bằng đúng Agent của nó, dù lúc nãy bộ phán xử đã chọn im. Câu trả lời được gửi qua kênh (nhóm Zalo đi đúng kiểu nhóm), ghi vào Hộp thư như lời của bot, và cuộc chat **vẫn ở Tự động** (khác gõ tay là tiếp quản). Nếu đó đúng là tin bộ phán xử đã im, bot còn **học thêm một ca** (nhãn "im nhầm" nặng nhất): lần sau gặp tin giống vậy bot sẽ nói. Không đi qua cổng "có nên nói", bộ phán xử hay hạn mức tự nói, vì đây là lời nhờ của chính bạn; quyền và giới hạn của Agent thì nguyên vẹn.
- **Gợi ý câu trả lời**: bot soạn nháp vào ô nhập, chưa gửi. Bạn sửa rồi bấm Gửi (gửi là tiếp quản). Bản nháp **không để lại dấu vết**: không vào kho phiên, không vào Hộp thư, lịch sử tạm của bot được dọn, nên nháp bỏ đi thì bot không "nhớ" mình từng nói câu đó với khách. Dùng được cả lúc bạn đang tiếp quản; ô nhập đang có chữ thì hỏi trước khi thay.
- Chế độ **Tôi trả lời** thì nút thứ nhất thành **Trả lại cho bot**.

**Nút chưa dùng được vẫn hiện** (viền đứt) và chạm vào thì nói lý do: đang tiếp quản, bot đang tắt (dòng trạng thái cũng nói thẳng "đang tắt nên không tự trả lời"), tin cuối không phải của khách, hay kênh chưa gửi được từ Javis. Bot soạn xong mà gửi hỏng thì câu đã soạn nằm trong ô nhập để bạn gửi tay. Agent chọn im thì báo, không gửi gì. Mỗi cuộc chat chỉ chạy một lượt nhờ-bot một lúc. Tệp đính kèm bot soạn không đi kèm (chỉ chữ).

Dưới tin khách cuối có dòng **"Bot im: lý do"** khi bộ phán xử đã ghi lý do (ví dụ "Điểm thấp hơn ngưỡng (0.52 / 0.60)"), kèm nút **Vì sao** mở thẳng bảng Bộ phán xử của bot đó. Dòng này chỉ hiện khi cuộc chat đang ở Tự động, tin cuối là của khách và quyết định gần nhất là im cho đúng tin đó; người thật đang tiếp quản thì bot im là hiển nhiên nên không nói.

Dưới cùng một hội thoại là ô soạn tin: gõ rồi **Enter** để gửi (Shift+Enter xuống dòng). Tin đi qua đúng kênh của cuộc chat: bot Telegram hay Zalo Bot gửi bằng token của tài khoản đó, Zalo cá nhân gửi qua chính tài khoản bạn đã quét QR, **dưới tên bạn** (ô soạn tin nói rõ điều này). Kênh nào chưa gửi được từ Javis thì ô soạn tin thay bằng một dòng nói vậy.

Gửi từ đây ở một cuộc chat có bot là bạn **tiếp quản** cuộc đó: bot im với khách này cho tới khi bạn gạt về **Tự động**. Không thì khách đọc hai giọng một lúc. Gạt công tắc sang **Tôi trả lời** làm y như vậy mà không cần gửi gì; gạt xong bạn trả lời trong app của kênh cũng được.

Hai điều nên biết:

- Lượt bot đang soạn dở đúng lúc bạn tiếp quản vẫn gửi nốt câu đó. Cắt ngang một câu đang gửi còn khó hiểu hơn với khách.
- Tiếp quản là theo **từng cuộc chat**, không tắt bot. Các khách khác vẫn được bot trả lời.

## Kênh chưa có bot (tab Bot)

Mọi tài khoản khách nhắn tới hiện thành **cùng một kiểu thẻ**, bất kể kênh: logo và tên kênh, tên tài khoản, trạng thái (đang chạy, đang tắt, lỗi kèm lý do), bot đang trực, số hội thoại và số chưa đọc, và các năng lực của kênh đó (vào nhóm, gửi file, trả lời từ Javis). Không kênh nào có mục riêng, kể cả Zalo. Kênh thêm về sau chỉ việc xuất hiện thêm một thẻ.

Có hai loại tài khoản, khác nhau ở cách có nó chứ không ở cách hiện ra:

**Tài khoản bot** (Telegram, Zalo Bot) là một token. Bấm **Thêm kênh**, chọn loại kênh, dán token, bấm **Kiểm tra** để Javis hỏi đúng nền tảng token đó là bot nào, đặt tên gợi nhớ rồi Lưu. Tài khoản bot ghi vào hộp thư khi bot trực nó đang bật; chưa có bot trực thì thẻ nói thẳng và có nút **Tạo bot cho kênh này** mở sẵn form Bot mới với kênh đó được tick. Mục **Kênh chưa có bot** chỉ liệt kê kênh chưa có bot; tự mở khi có kênh cần xử lý, tự gập khi hết.

### Tài khoản bot thuộc về một brain (0.62.4)

Trước 0.62.4 mục này hiện tài khoản của **mọi** brain, vì một token Telegram là tài khoản có thật ngoài đời nên nó không thuộc brain nào cả. Đúng về kỹ thuật nhưng khó dùng: đứng ở brain của mình mà nhìn một danh sách trộn lẫn thì không biết cái nào là của mình.

Từ 0.62.4 mỗi tài khoản có một **brain chủ**:

- **Thêm ở brain nào thì thuộc brain đó.** Mục chỉ hiện tài khoản của brain đang mở.
- **Form tạo bot cũng chỉ cho chọn tài khoản trong brain đó**, nên không còn tạo ra liên kết chéo brain.
- **Công tắc "Xem mọi brain"** ở đầu mục để tìm lại một tài khoản lỡ thêm nhầm chỗ. Khi đó mỗi thẻ tự ghi brain của nó, và mục liệt kê cả kênh đang do bot của brain khác trực (bot đó không hiện ở trang này, nên đây là chỗ duy nhất để sửa hoặc xoá kênh ấy). Zalo cá nhân là kết nối ở trang Kết nối nên không thuộc brain nào và brain nào cũng thấy.
- **Đổi chủ:** bấm **Sửa**, chọn lại ở mục **Brain của tài khoản**. Lịch sử hội thoại giữ nguyên, vì nó khoá theo id tài khoản chứ không theo brain.
- **Tài khoản cũ không đoán ra được chủ** (lúc nâng cấp không có bot nào trực nó) thì để **chưa gán** và hiện ở **mọi** brain kèm ghi chú. Chủ ý: thà thấy thừa một thẻ còn hơn có một token tồn tại mà không màn hình nào hiện ra, không ai xoá hay gắn lại được. Gắn nó vào một bot là nó nhận brain của bot đó.

Zalo cá nhân (`kind: account`) không bị lọc: nó là một kết nối ở trang **Kết nối**, không thuộc brain nào, nên luôn hiện.

Đây là bước đầu của hướng dài hơn: chia quyền quản lý tài khoản cho brain, rồi tới agent, skill, workflow và chatbot, để sau này lên được bản nhiều người dùng.

**Xoá một tài khoản:** bấm **Xoá**. Nếu đang có bot trực nó, Javis nói rõ bot nào, ở brain nào, rồi hỏi một câu duy nhất: gỡ khỏi bot đó rồi xoá luôn? Đồng ý là xong trong một lần, không phải đổi brain rồi đi tìm bot để tự gỡ. Bot vẫn còn và vẫn trực các tài khoản khác của nó. Nếu đó là tài khoản **duy nhất** của bot thì Javis nói trước, và sau khi xoá sẽ tắt bot đó đi (bản ghi bot vẫn còn, gắn tài khoản khác vào là bật lại được). Hội thoại đã ghi vẫn nằm nguyên trong hộp thư.

**Tài khoản của chính bạn** (Zalo cá nhân) đến từ trang **Kết nối** (quét QR ở Zalo Agent MCP) và hiện ở đây với công tắc **Ghi hội thoại**. Bật lên là Javis đọc tin mới mỗi 20 giây qua MCP và đổ vào hộp thư. Ba điều về kênh này, nói thẳng:

- **Mặc định tắt.** Bật là giữ phiên Zalo của bạn sống liên tục qua API không chính thức, tức tài khoản đăng nhập 24/7 trên máy chạy Javis. Đó là lựa chọn của bạn, không phải của Javis. Nên dùng tài khoản phụ.
- **Chỉ lưu từ lúc bật.** Không kéo lịch sử cũ. Tin do chính bạn gửi từ điện thoại hiện là tin "Bạn".
- **Không có bot trực.** Trả lời từ Hòm thư bot là gửi dưới tên bạn. Muốn nick này tự trả lời khách thì tạo một Bot chuyên trách và chọn kênh Zalo cá nhân (chat riêng từ 0.64.80, nhóm và chế độ Tự đánh giá từ 0.64.82), xem [Chatbot](25-chatbot.md).

## Dữ liệu lưu ở đâu, giữ gì

Kho nằm trong thư mục trạng thái của Javis (`customer_conversations.sqlite3`), tách khỏi kho phiên chat. Giữ **chữ** lâu dài; ảnh, file, tin thoại chỉ giữ loại tin và mô tả, file gốc theo hạn dọn của Javis. Tin trùng (đọc lại cùng một tin sau khi khởi động lại) không sinh dòng thứ hai.

Xoá một bot **không** xoá hội thoại của nó, và cũng không xoá tài khoản kênh nó trực: lịch sử khách là tài sản của bạn, token là thứ dùng lại được. Bot tạo trước 0.61.0 (token nằm trong bot) tự chuyển sang mô hình tài khoản khi bạn cập nhật; token, hội thoại, nhóm cho phép đều giữ nguyên.

## Cho ai muốn nối thêm kênh

Từ 0.61.0 mọi thứ lõi biết về một kênh nằm trong **sổ đăng ký kênh** (`server/channels/`, mỗi kênh một file). Một file kênh khai: id, tên, khoá logo, loại (`bot` dùng token, `account` dùng phiên đăng nhập sẵn có, `webhook` cho nền tảng gọi ngược), năng lực (nhóm, gửi chữ, gửi file), cách lấy token; và một bộ hàm: kiểm token và lớp long-poll (loại bot), liệt kê tài khoản và bật ghi (loại account), `gui` để trả lời từ Javis. Tin nhận về thì đưa về khuôn chung (`channel`, `account_id`, `external_chat_id`, `sender_type`, `text`, `external_message_id`, `created_at`) rồi gọi kho.

Thêm một kênh = thêm một file ở sổ, một dòng đăng ký, một logo trong `icons.js`. Kho bot, bộ giám sát, API và cả hai tab tự nhận, không sửa gì khác. Chi tiết ở `docs/dev/2026-09-kenh-hoi-thoai-spec.md`. Đường API:

- `GET /channels` các loại kênh và năng lực; `GET /channels/accounts` mọi tài khoản, một khuôn.
- `POST /channels/verify-token`, `POST /channels/accounts`, `POST /channels/accounts/{id}/update`, `.../watch` (loại account), `.../delete`.
- `POST /conversations/{id}/ai-reply` (từ 0.65.5): `mode=send` hoặc `draft`; lỗi trả `code` (`human`, `bot_off`, `no_bot`, `already_answered`, `busy`, `no_message`, `send_failed`, `engine`).
- `GET /conversations` danh sách kèm số liệu, lọc theo `channel`, `bot_id` (`-` = cuộc chat không có bot), `account_id`, `q`, và từ 0.65.3 `status` (`unread`, `need_reply`, `human`) và `chat_type` (`group`, `private`; giá trị lạ thì bỏ qua bộ lọc đó). Trả thêm `bot_name` và `need_reply` cho từng dòng, `facets` (số đếm cho dropdown, toàn hòm thư) và `bots` (bot có hội thoại, kèm tên).
- `GET /conversations/{id}/messages` lịch sử tin; `POST /conversations/{id}/reply` trả lời qua kênh.
- `POST /conversations/{id}/read`, `POST /conversations/{id}/mode` (`ai` hoặc `human`).
- `GET /conversations/channels` và `POST /conversations/zalo/{conn_id}/watch` là bí danh cũ, còn giữ.

## Xử lý lỗi

- **Bot đang bật mà không thấy hội thoại nào**: kho chỉ ghi từ lúc kênh được nối; nhắn thử cho bot một câu. Nếu vẫn trống, bấm Nhật ký trên thẻ bot ở tab Bot.
- **Thẻ bot báo "chưa có tài khoản kênh nào"**: bot chưa trực token nào. Bấm Sửa, tích một tài khoản có sẵn hoặc dán token mới.
- **Gửi từ Hòm thư bot báo lỗi**: câu lỗi là của chính nền tảng (token bị thu hồi, khách đã chặn bot, phiên Zalo hết hạn). Tin không đi thì không được ghi vào kho.
- **Zalo cá nhân báo lỗi đỏ ở mục Kênh chưa có bot**: thường là phiên QR hết hạn hoặc máy thiếu Node.js 20. Vào trang Kết nối kiểm tra kết nối Zalo, quét QR lại nếu cần. Vòng đọc tự thử lại sau 90 giây.
- **Gạt sang Tôi trả lời mà bot vẫn trả lời một câu**: đó là lượt đã chạy dở từ trước khi bấm. Từ tin sau bot im.

## Muốn hơn thế: gói Quản lý khách hàng (CRM)

Kho cài đặt có gói **Quản lý khách hàng (CRM)** (`javis.khach-hang-crm`, cần bản 0.60.1 trở lên) đặt lên chính hộp thư này. Cài xong hỏi Javis bằng lời: "khách nào chờ hơn 2 tiếng chưa được trả lời", "chị Lan đã hỏi gì", "gắn tag VIP cho chị Lan", "tuần này bao nhiêu khách mới", "xuất danh sách khách đã hỏi giá ra Excel". Kèm một trợ lý chăm sóc khách và một quy trình rà soát mỗi ngày. Gói chỉ đọc hộp thư và ghi tag, ghi chú lên khách; không gửi tin cho ai.

## Tham khảo

- [Chatbot (Bot chuyên trách)](25-chatbot.md)
- [Kênh Zalo Bot](26-kenh-zalo-bot.md)
- [Zalo Agent MCP](12-zalo.md)
