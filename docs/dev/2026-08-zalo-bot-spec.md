# Spec: Kênh Zalo Bot (API chính thức)

> Bản spec dev, viết 2026-08-08 trên nền v0.26.3. Nguồn: tài liệu chính thức
> <https://bot.zaloplatforms.com/docs/> (đọc ngày 2026-08-08).
>
> **Trạng thái: ĐÃ LÀM XONG PHASE 1, 2, 3 (chiều vào), 4 và 5.** Bot chuyên trách chạy trên
> Zalo từ v0.26.5; kênh Zalo của CHỦ và định tuyến thông báo xong ở v0.26.8. Bốn chỗ lệch so
> với bản spec này, ghi ngay đây thay vì để người đọc tự đối chiếu:
>
> - **Làm PHASE 5 TRƯỚC PHASE 4**, theo yêu cầu của chủ repo (2026-08-08): giá trị nằm ở bot
>   chuyên trách nói chuyện với khách Việt, không ở kênh của chủ.
> - **Phần dùng chung tách ra `server/bot_gateway.py`** chứ không để `zalo_bot.py` chép lại:
>   hàng đợi lượt, luật `/stop`, cổng precheck và dòng vết công cụ là luật hành vi của Javis,
>   không phải chi tiết của một nhà cung cấp. `TelegramBot` cũng đã chuyển sang dùng nó.
> - **Danh sách trắng RỖNG = CHƯA AI ĐƯỢC PHÉP** (mục 5 chỉ nói tới hàng chờ, không nói tới
>   luật này). Bên Telegram ô trống nghĩa là mở cho tất cả; giữ nguyên nết đó ở Zalo thì chính
>   luồng "bật bot với ô trống rồi tự nhắn cho nó" mà giao diện đang hướng dẫn sẽ tạo ra một
>   con bot ai cũng chạm được vào brain, trong khoảng giữa lúc bật và lúc bấm Cho phép.
> - **Phase 0 (thăm dò API thật) mới trả lời được MỘT câu**, xem mục 7. Còn lại vẫn chờ token
>   thật. Mã viết theo hướng chịu được cả ba khuôn phản hồi `getUpdates` có thể có, và kêu ra
>   stderr khi gặp khuôn lạ.
>
> **Còn lại: Phase 3 chiều RA (gửi ảnh) và Phase 6 (webhook).** Cả hai phụ thuộc kết quả thăm
> dò và phụ thuộc Javis đang chạy ở đâu.

## 1. Quyết định cốt lõi

**Zalo Bot là KÊNH THỨ TƯ, không phải một runtime thứ hai.**

Javis đã có ba kênh đi qua đúng một lõi: dashboard, Telegram, CLI. `main.py` cấp cho
`telegram_bot.TelegramBot` đúng mấy hàm gọi ngược (`answer_fn`, `command_fn`,
`callback_fn`, `precheck_fn`, `event_fn`) rồi thôi; toàn bộ phần khớp phiên, chọn brain,
gọi engine, lưu hội thoại nằm ở nhóm hàm `_tg_*` trong `main.py` và đã nhận tham số
`channel` từ trước (CLI và bot chuyên trách dùng chung).

Nghĩa là **việc phải làm là viết một lớp vận chuyển mới, không phải một gateway mới.**
`server/zalo_bot.py` giữ đúng khế ước của `TelegramBot`, cắm vào đúng `_tg_answer` hiện
có. Không đụng `telegram_bot.py` ở giai đoạn đầu, nên kênh đang được dùng nhiều nhất
không chịu rủi ro nào.

**Zalo Bot KHÔNG thay Zalo Agent MCP.** Hai thứ khác bản chất, cùng tồn tại:

- `zalo-agent-cli` (zca-js) đăng nhập **chính tài khoản Zalo của bạn**: đọc được hội
  thoại thật, nhắn cho bất kỳ ai, và có thể bị Zalo khoá tài khoản.
- Zalo Bot là **một danh tính riêng**, chính thức, không bị khoá, nhưng chỉ thấy được
  những gì người ta nhắn thẳng cho nó.

Cái đầu để Javis **thao tác thay bạn**. Cái sau để **người khác nói chuyện với Javis**.
Ai gộp hai cái làm một sẽ mất một nửa năng lực.

## 2. Zalo Bot API: những gì tài liệu nói

Về hình dạng, đây gần như một bản sao của Telegram Bot API.

| Mục | Giá trị |
|---|---|
| Base URL | `https://bot-api.zaloplatforms.com/bot<TOKEN>/<method>` |
| Token | dạng `12345689:abc-xyz`, **không hết hạn** cho tới khi chủ tự reset |
| Lấy token ở đâu | mở app Zalo, tìm OA **Zalo Bot Manager**, chọn Tạo bot; tên bot bắt buộc mở đầu bằng chữ "Bot". Token được gửi về bằng tin nhắn Zalo |
| Vỏ phản hồi | `{ok, result, description, error_code}` |
| Nhận tin | `getUpdates` (long polling, tài liệu ghi rõ **chỉ nên dùng khi chạy local**) hoặc webhook |
| Method có | getMe, getUpdates, setWebhook, deleteWebhook, getWebhookInfo, sendMessage, sendPhoto, sendSticker, sendVoice, sendChatAction |

`sendMessage` nhận `chat_id`, `text` (1 tới 2000 ký tự), `parse_mode` (`markdown` hoặc
`html`), hoặc `text_styles` dạng mảng. Trả về `{message_id, date}`.

`sendPhoto` nhận `chat_id`, `photo` (tài liệu ghi "đường dẫn hình ảnh"), `caption` tối đa
2000 ký tự. `sendChatAction` mới có đúng `typing`, `upload_photo` ghi Coming soon.

Webhook: `setWebhook` cần `url` HTTPS và `secret_token` dài 8 tới 256 ký tự. Zalo POST
JSON về, kèm header `X-Bot-Api-Secret-Token` phải đối chiếu. Sự kiện gồm
`message.text.received`, `message.image.received`, `message.sticker.received`,
`message.voice.received`, `message.unsupported.received`. Payload thật của sự kiện chữ:

```json
{ "ok": true, "result": {
  "message": {
    "from": { "id": "6ede9afa66b88fe6d6a9", "display_name": "Ted", "is_bot": false },
    "chat": { "id": "6ede9afa66b88fe6d6a9", "chat_type": "PRIVATE" },
    "text": "Xin chào", "message_id": "2d758cb5e222177a4e35", "date": 1750316131602 },
  "event_name": "message.text.received" } }
```

Mã lỗi: 400 sai đường dẫn hoặc tên API, 401 token sai hoặc hết hạn, 403 lỗi máy chủ,
404 không tìm thấy, 408 quá thời gian, **429 vượt hạn mức**. Tài liệu không công bố con
số hạn mức, và trang Giá gói lẫn FAQ đang trả HTTP 500 tại thời điểm khảo sát.

`getMe` trả `account_type: "BASIC"` và `can_join_groups: false`.

## 3. Bảy chỗ Zalo Bot KHÁC Telegram, và chỗ nào làm gãy UX hiện tại

Đây là phần quan trọng nhất của spec. Chép nguyên hành vi Telegram sang là hỏng ngay.

1. **Không có `editMessageText`, không có `deleteMessage`.** Cái tin "🤔 Javis đang xử
   lý…" tự đổi chữ theo tiến trình rồi tự xoá, thứ đã được viết hẳn một mục trong
   `docs/11-telegram.md`, **không làm được trên Zalo**. Xem mục 3.1 bên dưới, vì đây là
   chỗ phải thiết kế lại chứ không phải chỗ cắt bớt.
2. **Không có nút bấm inline, không có callback.** Bảng chọn provider và lưới model của
   `/model`, bảng chọn brain của `/brain` đều dựa vào `callback_query`. Trên Zalo phải hạ
   xuống **danh sách đánh số** rồi đọc con số ở lượt sau. Javis đã có sẵn đường này cho
   khối `JAVIS_ASK`, tái dùng chứ đừng viết bản thứ hai.
3. **Trần chữ 2000 chứ không phải 4096.** Hằng số chia tin phải theo kênh.
4. **Không có `sendDocument`.** PDF, xlsx, docx không có cửa gửi ra. Đây là khoảng hụt
   chức năng lớn nhất so với Telegram, phải nói thẳng trong tài liệu người dùng chứ
   không được im lặng nuốt file.
5. **`sendPhoto` nhận đường dẫn ảnh, nhiều khả năng là URL công khai.** Trang "Sử dụng
   API" có liệt kê `multipart/form-data` cho upload file, nên có thể đẩy file trực tiếp
   được, nhưng tài liệu `sendPhoto` không xác nhận. **Phải thử thật trước khi thiết kế**
   (xem Phase 0). Nếu chỉ nhận URL thì máy chạy local không gửi ảnh ra được, và Javis
   phải nói thật điều đó thay vì báo thành công.
6. **`getUpdates` không có `offset` hay `update_id`.** Tham số duy nhất là `timeout`.
   Không có cơ chế xác nhận đã nhận, nên **phải tự chống trùng bằng `message_id`** (LRU
   vài nghìn id trong bộ nhớ). Đây là chỗ dễ sinh lỗi trả lời hai lần một câu.
7. **`can_join_groups: false` ở gói BASIC.** Kịch bản bot chăm sóc khách trong nhóm, thứ
   `chatbot_runtime` làm khá kỹ trên Telegram, có thể không dùng được ở gói miễn phí.
   Giao diện phải ẩn phần cấu hình nhóm khi `getMe` trả `false`, chứ không hiện ra rồi
   để nó chết lặng.

### 3.1. Hiện tiến trình mà không gửi tin rồi xoá

Chủ repo đã nói rõ (2026-08-08): **cách gửi tin trạng thái rồi xoá là sai**, thứ cần là
thấy được các trạng thái thao tác ("đang gọi công cụ X"), còn tin nhấp nháy rồi biến mất
thì không. Chốt lại thiết kế cho cả hai kênh.

Trước hết một sự thật kỹ thuật phải nắm: **`sendChatAction` không mang được chữ tuỳ ý.**
Cả Telegram lẫn Zalo đều chỉ nhận một bộ hành động cố định (typing, upload_photo...).
Nghĩa là muốn hiện tên công cụ thì **bắt buộc phải là một tin nhắn thật**, không có
đường thứ hai. Vấn đề cần giải không phải "bỏ tin nhắn" mà là "đừng để tin nào biến
mất".

**Telegram: tin trạng thái gửi im lặng rồi ở lại thành dòng vết. ĐÃ LÀM ở v0.26.4.**

`_send_status` thêm `disable_notification: true`, nên tin trạng thái hiện ra mà không
rung máy. Nó vẫn được sửa tại chỗ theo tiến trình như cũ. Xong việc thì **không xoá**:
lần sửa cuối biến nó thành một dòng vết gọn (`⚙ pos_statistics · Read · 8s`, hoặc
`✓ Trả lời trực tiếp · 3s` khi lượt không gọi công cụ nào), rồi câu trả lời đi thành một
tin MỚI có chuông. `/stop` sửa dòng đó thành `⏹ Đã dừng.`. `_del_msg` bị xoá khỏi mã.

Kết quả: mỗi lượt đúng một tiếng chuông, và thông báo trên điện thoại hiện đúng nội dung
trả lời.

**Đã cân nhắc rồi bỏ: cho tin trạng thái tự biến thành câu trả lời** (một bong bóng duy
nhất cho cả lượt). Chat gọn hơn thật, nhưng `editMessageText` **không nổ thông báo**, nên
người dùng sẽ không được báo khi câu trả lời xong. Với trợ lý cầm tay thì đó là mất mát
lớn hơn phần chat gọn. Bỏ.

**Zalo: chấm "đang nhập" cộng một dòng vết công cụ đi kèm câu trả lời.**

Zalo không sửa và không xoá được tin, nên **không có trạng thái động nào cả**. Chỉ còn
`sendChatAction typing` giữ sáng suốt lượt (Phase 0 phải đo xem chấm tắt sau bao lâu để
biết nhịp nhắc lại). Tuyệt đối không gửi tin trạng thái rời trên Zalo: gửi ra là nằm đó
vĩnh viễn.

Bù lại, kẹp **một dòng vết gọn** vào câu trả lời, kiểu `⚙ pos_statistics · Read · 8s`.
Nó nằm lại vĩnh viễn nhưng không phải rác, và là bằng chứng công cụ đã chạy thật, đúng
vai trò mà dòng "⚙ Đang gọi..." đang giữ trên Telegram. Dòng này nên làm chung cho cả
hai kênh, vì trên Telegram sau khi bong bóng hoá thành câu trả lời thì lịch sử tiến
trình cũng mất theo.

**Đã cân nhắc rồi bỏ:** thả cảm xúc lên chính tin người dùng vừa gửi (`setMessageReaction`,
Bot API 7.0) là trạng thái thật, không sinh tin nào. Nhưng chỉ chọn được trong bộ emoji
cố định nên không nói được tên công cụ. Dùng kèm thì được, dùng thay thì mất thông tin.
Zalo không có API tương đương.

## 4. Vì sao đáng làm

Ngắn gọn: **khách hàng Việt Nam không dùng Telegram.**

Kênh Telegram hiện là cửa duy nhất để hỏi Javis từ điện thoại, và là nơi mọi thông báo
nền (vòng loop, việc Kanban, nhắc hẹn) rơi về. Với một chủ cửa hàng kim khí ở Việt Nam,
Telegram là một app lạ phải cài thêm. Zalo thì đã nằm sẵn trên máy.

Hai sản phẩm mở ra từ đúng một lớp vận chuyển:

- **Kênh của chủ.** Hỏi Javis qua Zalo, nhận báo cáo loop và nhắc hẹn qua Zalo.
- **Bot chuyên trách trên Zalo.** `chatbot_store` đã có sẵn trường `"channel":
  "telegram"` từ lúc thiết kế. Cho nó nhận thêm `"zalo"` là bot tư vấn của cửa hàng nói
  chuyện được với khách thật, trên app khách thật đang mở. Đây mới là phần có giá trị
  kinh doanh, và nó gần như miễn phí về mặt kiến trúc một khi Phase 1 xong.

## 5. Ghép người dùng: đừng chép cách của Telegram

Telegram bắt chủ đi tìm Chat ID bằng @userinfobot rồi tự dán vào ô whitelist. Zalo
**không có** công cụ tương đương, và id là chuỗi hex như `6ede9afa66b88fe6d6a9`, không
ai đọc ra được nó là ai.

Phương án: **mã ghép nối**. Người lạ nhắn cho bot thì bot đáp "Bạn chưa được cấp quyền
dùng Javis. Mã ghép nối của bạn: 4821". Trang Kênh trên dashboard hiện một thẻ nhỏ liệt
kê các cuộc chat đang chờ, kèm `display_name` thật và mã, cùng nút **Cho phép**. Bấm một
cái là id vào whitelist.

Chi tiết cần chốt sẵn: hàng chờ giữ tối đa 20 mục, mỗi mục sống 30 phút rồi rụng, một
chat_id lạ chỉ được nhận đúng một câu từ chối trong 10 phút (chống người lạ bơm tin để
làm ngập hàng chờ). Mã ghép nối để chủ đối chiếu đúng người khi hai người cùng tên.

Cách này vừa đúng thói quen (`feedback_khong-bat-user-chay-lenh`: đừng bắt người dùng đi
làm phần ống nước), vừa là thứ nên đem ngược về cho Telegram sau này.

## 6. Kiến trúc và những file sẽ đụng

**File mới**

- `server/zalo_bot.py`: lớp `ZaloBot`, giữ đúng khế ước của `TelegramBot`
  (`answer_fn`, `command_fn`, `precheck_fn`, `event_fn`, `download_dir`, `commands`,
  `giau_trang_thai`). Bỏ `callback_fn` vì Zalo không có nút. Bên trong: vòng long poll,
  chống trùng theo `message_id`, hàng đợi mỗi chat như bản Telegram, chia tin ở 2000,
  giữ chấm "đang nhập" bằng `sendChatAction`.
- `tests/python/test_zalo_bot.py`: whitelist, chia tin ở 2000, chống trùng, hàng chờ
  ghép nối, đối chiếu secret webhook.
- `docs/26-zalo-bot.md`: tài liệu người dùng, tách hẳn khỏi `docs/12-zalo.md` để không
  ai lẫn hai thứ.

**File sửa**

- `server/main.py`: biến `_ZALO_BOT`, khởi động và dừng theo settings, các endpoint
  `/zalo-bot/status`, `/zalo-bot/restart`, `/zalo-bot/test`, `/zalo-bot/pending`,
  `/zalo-bot/allow`. Gọi `_tg_answer(..., channel="zalo")` với khoá phiên
  `zalo:<chat_id>` (id Zalo là hex, id Telegram là số, nhưng vẫn phải gắn tiền tố kẻo
  trùng ngẫu nhiên và trộn hai mạch hội thoại vào nhau).
- `server/config.py`: thêm khối mặc định `"zalo_bot": {"enabled": False, "token": "",
  "chat_id": "", "mode": "poll", "webhook_secret": ""}`, và thêm `zalo_bot.token` cùng
  `zalo_bot.webhook_secret` vào danh sách khoá được mã hoá (quanh dòng 381).
- `server/channel_context.py`: `build_channel_block` nhận `source="zalo"`, thêm "Zalo
  Bot" vào danh sách nền tảng. Thêm nhắc nhở về giọng văn giống Telegram (không bảng
  markdown, viết ngắn kiểu tin nhắn).
- `server/main.py` phần thông báo: `_notify_owner` và `_tg_send_to` hiện chỉ biết tiền
  tố `web:` rồi mặc định rơi về Telegram. Thêm nhánh `zalo:<chat_id>`. Việc giao từ Zalo
  phải báo kết quả về Zalo, đúng luật báo cáo mặc định trong `CLAUDE.md`.
- `server/reminders.py`: cửa `can_force` đang coi "chưa đấu Telegram" là chưa có kênh
  báo. Zalo Bot bật cũng phải tính là có kênh, nếu không nó chặn nhầm.
- `server/chatbot_store.py`: `channel` thành trường thật, nhận `"telegram"` hoặc
  `"zalo"`. `token_owner` (chặn hai poller cùng token) phải xét theo từng kênh.
- `server/chatbot_runtime.py`: `start_bot` chọn lớp vận chuyển theo `channel`.
- `dashboard/console.js`: thẻ Zalo Bot trên trang Kênh, cạnh thẻ Telegram, kèm thẻ hàng
  chờ ghép nối.
- `server/web_security.py`: miễn CSRF cho `POST /hook/zalo-bot` (Phase 6) nhưng vẫn giới
  hạn tần suất.

## 7. Các giai đoạn

### Phase 0: Thăm dò API thật

**Đã trả lời được một câu mà không cần token** (2026-08-08): gọi `getMe` với một token rác
thì Zalo trả `{"ok":false,"description":"Unauthorized","error_code":401}` kèm **HTTP 200**,
chứ không phải HTTP 401 như Telegram. Nghĩa là **bắt buộc đọc trường `ok`, không được nhìn mã
HTTP**. Mã hiện tại đang làm đúng vậy.

Năm câu còn lại vẫn cần một bot token thật:

1. `getUpdates` có trả lại tin cũ sau khi đã nhận không? Trùng ở mức nào?
2. `sendPhoto` có nhận `multipart/form-data` không, hay bắt buộc URL công khai?
3. Payload thật của `message.image.received` và `message.voice.received` có trường gì,
   URL ảnh sống được bao lâu?
4. Hạn mức thật là bao nhiêu trước khi ăn 429?
5. Bot có nhắn được cho một `chat_id` chưa từng nhắn cho nó không?
6. `parse_mode: markdown` hiện ra sao trên điện thoại thật?

Câu 2 quyết định Phase 3 có tồn tại hay không, câu 5 quyết định nhắc hẹn qua Zalo có
dùng được không. Không đoán, vì đoán sai ở đây là thiết kế lại từ đầu.

### Phase 1: Lớp vận chuyển và kênh của chủ

`server/zalo_bot.py` cộng phần cấu hình, endpoint, thẻ trên dashboard, ghép nối bằng mã.
Hết phase này là chủ nhắn cho bot Zalo và Javis trả lời bằng đúng brain, đúng engine,
đúng MCP như trên Telegram.

### Phase 2: Lệnh gõ nhanh và các tương tác đã hạ cấp

Bộ lệnh cho Zalo: `/help`, `/status`, `/stop`, `/reset`, `/retry`, `/model`, `/brain`,
`/notes`, `/skills`. `/model` và `/brain` vẽ danh sách đánh số thay cho lưới nút, đọc
con số ở lượt kế. Khối `JAVIS_ASK` dùng lại đường hạ cấp sẵn có.

Phần Telegram của chuyện này **đã làm trước, ở v0.26.4** vì nó độc lập với Zalo: tin
trạng thái gửi im lặng, không xoá, chốt thành dòng vết công cụ. Hàm dựng dòng vết
(`TelegramBot._dong_vet`) và biểu thức bóc tên công cụ (`RE_TEN_TOOL`) nên **kéo ra dùng
chung** khi viết `zalo_bot.py`, đừng chép lại. Chi tiết ở mục 3.1.

### Phase 3: Media hai chiều (phụ thuộc Phase 0)

Chiều vào: tải ảnh và voice về `inbox/zalo/` của brain đang chọn cho phiên, theo đúng
luật dọn cache 30 ngày và trần 300MB của `media_gc.py`.

Chiều ra: nếu multipart chạy thì làm giống `send_file` của Telegram. Nếu chỉ nhận URL
thì phải có một endpoint media công khai, ký, sống ngắn, và **chỉ khả dụng khi Javis
đang chạy trên máy có tên miền công khai**. Bản chạy local phải nói thẳng "chưa gửi được
ảnh qua Zalo từ máy này" chứ không được báo thành công giả. Không có `sendDocument`
nghĩa là PDF và bảng tính không gửi được, ghi rõ trong tài liệu.

### Phase 4: Định tuyến thông báo nền

Tiền tố `zalo:` cho `owner_chat`. Loop, việc Kanban và nhắc hẹn sinh ra từ Zalo báo kết
quả về Zalo. Sửa cửa `can_force` ở `reminders.py`. Nếu Phase 0 cho biết bot không nhắn
trước được thì nhắc hẹn tới giờ mà người nhận chưa từng nhắn cho bot sẽ hỏng, phải bắt
lỗi đó và nói ra, không nuốt.

### Phase 5: Bot chuyên trách trên Zalo

`channel` thành trường thật, `chatbot_runtime` chọn lớp vận chuyển theo nó. Ẩn phần cấu
hình nhóm khi `getMe` báo `can_join_groups: false`. Đây là phần đem lại giá trị kinh
doanh thật, và sau Phase 1 thì nó gần như chỉ là đấu dây.

### Phase 6: Chế độ webhook (chỉ cho VPS)

`POST /hook/zalo-bot`, đối chiếu `X-Bot-Api-Secret-Token` bằng so sánh hằng thời gian,
miễn CSRF nhưng có giới hạn tần suất. Hai chế độ loại trừ nhau nên khi chuyển phải
`deleteWebhook` trước.

Cẩn thận một chuyện: bản Zalo cũ **đã từng có** `/hook/zalo` rồi bị gỡ hẳn cùng listener
(xem mục "Khác với tích hợp Zalo cũ" trong `docs/12-zalo.md`). Đường dẫn mới phải khác
tên và khác bản chất, đừng để người đọc code sau này tưởng listener quay lại.

### Phase 7: Tài liệu và kiểm thử

`docs/26-zalo-bot.md` cho người dùng, nói rõ khi nào dùng Zalo Bot khi nào dùng Zalo
Agent MCP. Cập nhật `docs/12-zalo.md` trỏ sang. Bộ test như liệt kê ở mục 6.

## 8. Rủi ro và câu hỏi còn mở

- **Hạn mức không được công bố.** Trang Giá gói và FAQ đang lỗi 500. Phải cài lùi thời
  gian khi gặp 429 và **phơi lỗi hạn mức ra dòng trạng thái**, đừng nuốt. Gói trả phí
  xuất hiện sau có thể đổi luật chơi.
- **Bot nhiều khả năng không nhắn trước được.** Nếu đúng vậy thì mọi thông báo nền chỉ
  tới được người đã từng nhắn cho bot. Phải nói ra ở giao diện.
- **Gói BASIC không vào nhóm được**, chặn một phần kịch bản bot chuyên trách.
- **Không sửa và không xoá được tin đã gửi.** UX trạng thái khác hẳn Telegram, viết vào
  tài liệu để nó không bị đọc thành lỗi.
- **Nền tảng còn non.** `event_name` và tên trường có thể đổi. Giữ phần bóc payload gọn
  trong một hàm để chỉ phải sửa một chỗ.
- **Chống trùng là chỗ dễ chảy máu nhất**, vì không có `update_id`. Test phải phủ.

## 9. Ước lượng và thứ tự nên làm

Phase 0 nửa ngày. Phase 1 và 2 khoảng hai tới ba ngày. Phase 3 một ngày. Phase 4 nửa
ngày. Phase 5 một tới hai ngày. Phase 6 nửa ngày. Phase 7 nửa ngày. Tổng khoảng một tuần
làm tập trung.

Thứ tự đề xuất: ra **Phase 0 tới 2 trước** thành một bản dùng được (chủ hỏi Javis qua
Zalo), rồi **Phase 4** (thông báo nền về đúng Zalo), rồi **Phase 5** (bot chuyên trách,
phần mở khoá giá trị kinh doanh). Phase 3 và 6 phụ thuộc kết quả thăm dò và phụ thuộc
Javis đang chạy ở đâu, nên xếp sau.

## 10. Nguồn

- [Tài liệu Zalo Bot](https://bot.zaloplatforms.com/docs/), đọc 2026-08-08
- [Tạo bot](https://bot.zaloplatforms.com/docs/create-bot/),
  [Xác thực](https://bot.zaloplatforms.com/docs/authorize/),
  [Gọi API](https://bot.zaloplatforms.com/docs/call-api/),
  [Webhook](https://bot.zaloplatforms.com/docs/webhook/),
  [Bảng mã lỗi](https://bot.zaloplatforms.com/docs/error-code/)
- [Kênh Zalo của OpenClaw](https://docs.openclaw.ai/channels/zalo) - một bản triển khai
  thật để đối chiếu; họ mặc định long polling, chia tin ở 2000, trần media 5MB
- Trong repo: [Kênh Telegram](../11-telegram.md), [Zalo Agent MCP](../12-zalo.md),
  [Spec Javis CLI](2026-08-cli-spec.md), [Spec Bot chuyên trách](2026-08-bot-chuyen-trach-spec.md)
