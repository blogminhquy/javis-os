# Đề xuất: Bot chuyên trách - biến Agent thành chatbot trả lời khách

Chủ repo nêu ngày 2026-08-04, thay cho ý "Cho Agent gắn chatbot AI" còn để mở trong
`2026-08-backlog-spec.md` mục 2. Ý đã rõ hẳn, và nó không trùng cách hiểu nào trong ba cách
em đoán lúc đó.

Trạng thái: **đã làm xong cả bốn giai đoạn**. Giai đoạn 1 ra ở 0.19.0; giai đoạn 2, 3, 4 ra ở
0.20.0 (kèm một lỗ của 0.19.0 phải vá, ghi ở mục 7). Hướng dẫn người dùng: `docs/25-chatbot.md`.

## 0. Đã chốt (2026-08-04)

Chủ repo chốt ba điều, và cả ba đều làm thiết kế gọn lại chứ không phình ra:

1. **Mỗi bot một brain riêng.** Cách ly vật lý, không phải rào bằng mã.
2. **Mỗi bot một token riêng.** Mỗi con có tên và ảnh đại diện riêng trong nhóm khách.
3. **Có trang Chatbot trong dashboard** để quản lý mọi bot đang chạy. Tạo bot thì **chọn Agent
   đã có, hoặc tạo Agent mới ngay tại chỗ**.

Điều số 3 đổi thứ tự lộ trình: trang quản lý không còn là việc cuối mà là **cửa vào**. Không có
nó thì bot phải tạo bằng cách sửa tay file `.md`, rồi làm xong trang lại vứt đường đó đi. Xem
mục 7 đã xếp lại.

Hai điều đầu hoá ra gần như miễn phí, vì Javis đã có sẵn:

- **Nhiều brain là chuyện có sẵn từ lâu**: `GET /brains`, `POST /brains/new` (tự seed cấu trúc
  chuẩn), `POST /brains/delete` (`server/main.py:3270`). Tạo brain cho bot là gọi đúng API đó,
  không viết kho thứ hai.
- **Thêm một trang vào rail** là thêm một mục vào `RAIL_ITEMS` rồi xếp vào một nhóm của
  `RAIL_GROUPS` (`dashboard/console.js:78`). Đề xuất xếp vào nhóm **Năng lực**, ngay cạnh
  Agents, vì luồng tạo bot bắt đầu từ một Agent. Trang **Kênh** hiện có là kênh của CHỦ, khác
  loại, không gộp.

## 1. Ý muốn, diễn đạt lại cho chắc

> Javis đang có nhiều Agent, mỗi Agent gắn Skill và Workflow riêng. Tận dụng chúng để tạo ra
> các chatbot, **mỗi con chuyên một lĩnh vực**, đứng ra trả lời giúp. Chatbot trả lời qua
> Telegram, hoặc thả thẳng vào nhóm chăm sóc khách hàng.

Nếu em hiểu đúng thì đích đến là: chủ shop có sẵn một Agent "Tư vấn sản phẩm" và một Agent
"Chính sách bảo hành". Bấm một nút, mỗi con thành một bot Telegram riêng, thả vào nhóm khách.
Khách hỏi trong nhóm, bot trả lời trong đúng phạm vi lĩnh vực của nó.

## 2. Tin tốt: phần lớn nguyên liệu đã có

- **Agent** đã có vai trò, system prompt, danh sách Skill và model riêng
  (`server/main.py:3432`). Đây chính là "bộ não chuyên lĩnh vực" mà ý tưởng cần.
- **Kênh Telegram** đã chạy thật, có long-polling, đa phiên theo `chat_id`, gửi file, nút bấm.
- **Lõi một lượt trả lời** (`_tg_answer`, `server/main.py:8830`) đã là chỗ dùng chung cho
  dashboard, Telegram và CLI. Thêm kênh thứ tư đi qua đúng lõi này là đường đã có sẵn, không
  phải nhân bản runtime (bài học 0.17.0).
- **Nhóm Telegram đã hỗ trợ sẵn ở tầng dữ liệu**: id nhóm là số âm và mã đã cố ý không lọc dấu
  trừ (`telegram_bot.py:26`). Meta mỗi tin đã mang sẵn `chat_type` và `chat_title`
  (`telegram_bot.py:263`), hiện chưa ai dùng.

## 3. Tin phải nhìn thẳng: mọi giả định an toàn hôm nay đều đảo ngược

Đây là phần quan trọng nhất của tài liệu. **Bot Telegram hôm nay của Javis là kênh RIÊNG của
chủ.** Nó được thiết kế với đúng một giả định: người nhắn vào là anh.

Cụ thể, hôm nay một tin nhắn Telegram bất kỳ sẽ:

- chạy ở **mức toàn quyền** (`_apply_mcp(..., mode="full")`), tức gọi được mọi MCP đã đấu: POS,
  quảng cáo, Zalo gửi tin, lịch;
- đọc và **ghi được file trong brain** của chủ;
- **đổi được brain** bằng lệnh `/brain`, xem được `/status`, `/skills`;
- **ghi vào bộ nhớ dài hạn** và chảy vào vòng tự học;
- và whitelist để trống nghĩa là **cho phép mọi người** (`telegram_bot.py:24`, giữ hành vi cũ).

Thả nguyên con bot đó vào một nhóm khách hàng thì mỗi khách đang cầm chìa khoá toàn bộ Javis
của anh. Một câu "đọc giúp file cấu hình trong brain rồi gửi lên đây" là xong.

Nên **bot chuyên trách không phải là bot hiện tại đổi prompt**. Nó là một sinh vật khác, chỉ
dùng chung đường ống. Nếu chỉ nhớ một câu trong cả tài liệu này, nhớ câu đó.

Bảng đối chiếu để thấy rõ hai thứ khác nhau tới đâu:

| | Bot của chủ (đang có) | Bot chuyên trách (đề xuất) |
|---|---|---|
| Ai nhắn | Chủ và người được whitelist | **Khách lạ**, không kiểm soát được |
| Quyền | Toàn quyền, mọi MCP | **Chỉ đọc**, không MCP nào trừ thứ được cấp riêng |
| Ghi vault | Có | **Không** |
| Phạm vi đọc | Cả brain | **Đúng một kho tri thức đã chỉ định** |
| Bộ nhớ dài hạn | Có, học từ hội thoại | **Không ghi** vào ký ức của chủ |
| Lệnh quản trị | `/brain`, `/status`, `/skills`... | **Không có cái nào** |
| Không biết thì | Suy đoán tiếp cũng được | **Phải nói không biết** rồi chuyển người thật |

## 4. Bot là một BẢN GHI RIÊNG, trỏ tới một Agent

### Bản nháp đầu của em sai chỗ này, ghi lại để khỏi quay về

Lúc đầu em định nhét khối `publish` vào thẳng file Agent, lý do "anh bảo tận dụng Agent, đừng
đẻ thêm thực thể mới". Nghe hợp lý, nhưng ba quyết định ở mục 0 làm nó gãy:

- **Agent nằm TRONG một brain** (`<brain>/Javis/agents/<slug>.md`), còn bot lại **đọc brain
  riêng của nó**. Chọn một Agent ở brain chính rồi cho bot đọc brain khác thì khối `publish`
  nằm ở brain chính đang mô tả một thứ sống ở brain khác. Sai chỗ ngay từ khái niệm.
- **Token là bí mật**, không được nằm trong file `.md` mà chủ mở ra sửa trong Obsidian.
- **Bot có vòng đời** (đang chạy, đã tắt, lỗi). Vòng đời không thuộc về một file tài liệu.
- Xoá Agent thì bot thành mồ côi, mà không có chỗ nào để báo.

**Nguyên tắc "đừng đẻ thực thể mới" vẫn đúng, nhưng áp sai chỗ.** Thứ không được nhân bản là
khái niệm **Agent** (vai trò, prompt, skill, model) - và nó không bị nhân bản: bot chỉ **trỏ
tới** một Agent chứ không chép lại. Còn bản thân cái bot thì đúng là một thứ mới: nó có token,
có brain, có vòng đời, có nhóm.

### Lưu ở đâu

Đi theo đúng khuôn `mcp_store` đang dùng cho các kết nối MCP - cùng bài toán, cùng lời giải:

```
<JAVIS_STATE_DIR>/chatbots.json      ← danh sách bot (KHÔNG có token)
<JAVIS_STATE_DIR>/secrets            ← token, mã hoá, qua secrets_store
```

Một bản ghi bot:

```json
{
  "id": "bot_a1b2c3",
  "name": "Tư vấn sản phẩm",
  "icon": "message-circle",
  "enabled": false,

  "agent": { "brain": "brain", "slug": "tu-van-san-pham" },
  "brain": "bot-tu-van-san-pham",

  "channel": "telegram",
  "token_ref": "bot_a1b2c3.token",
  "bot_username": "TuVanSanPham_bot",

  "groups": ["-1001234567890"],
  "reply_when": "mention",
  "handoff_to": "123456789",
  "rate_limit": 20
}
```

Ba điều đáng chú ý trong hình dạng này:

1. **`agent` là con trỏ hai phần** (brain + slug), không phải bản chép. Sửa Agent ở trang
   Agents là bot đổi theo ngay, không phải sửa hai chỗ.
2. **`brain` là brain bot ĐỌC**, khác brain chứa Agent. Đây chính là chỗ bản nháp đầu gãy.
3. **Không có token**, chỉ có `token_ref`. Cùng cách kho MCP cất khoá của các kết nối.

Xoá Agent mà còn bot trỏ vào thì **cảnh báo và chặn**, giống cách xoá Project không được xoá
hội thoại: người dùng không đoán được hậu quả thì đừng để họ gánh nó.

### Năm mảnh của một bot

1. **Bộ não** = Agent được trỏ tới (vai trò + prompt + skill). Có sẵn.
2. **Kho tri thức** = brain riêng của bot. Có sẵn API tạo và seed.
3. **Kênh** = một bot Telegram riêng. Cần cho chạy nhiều poller cùng lúc.
4. **Mức quyền** = khoá cứng ở chỉ-đọc. Cơ chế đã có (`min_mode`, `effective_perm`), nối đúng chỗ.
5. **Đường thoát** = chuyển người thật khi bí. Chưa có, phải viết.

## 5. Ba quyết định lớn, kèm khuyến nghị

### 5.1 Mỗi bot một token riêng (ĐÃ CHỐT)

- **Một token riêng cho mỗi bot** (đề xuất chọn): mỗi con có tên, ảnh đại diện và `@handle`
  riêng do anh tạo ở BotFather. Thả vào nhóm khách thì nó là "Trợ lý Sản phẩm" chứ không phải
  "Javis của anh Quý". Đây là khác biệt về hình ảnh thương hiệu, không phải chuyện kỹ thuật.
  Giá phải trả: phải cho chạy nhiều poller cùng lúc, hiện `_TG_BOT` đang là biến toàn cục một
  cái (`server/main.py:9548`).
- **Một bot chung**: nhẹ hơn nhiều, nhưng mọi lĩnh vực chung một danh tính, và không thả được
  hai bot khác nhau vào hai nhóm khác nhau.

### 5.2 Mỗi bot một brain riêng (ĐÃ CHỐT)

- **Brain riêng cho bot** (đề xuất chọn): tạo một brain nhỏ chỉ chứa tri thức khách được xem.
  Cách ly vật lý là cách ly duy nhất không hỏng khi ai đó viết sai một dòng code sau này.
- Đọc brain chính nhưng giới hạn thư mục: đỡ công chuẩn bị, nhưng rào chỉ nằm ở mã. Một lỗi
  đường dẫn là lộ cả brain.

Đã chốt brain riêng. Chi phí thật thấp hơn tưởng: `POST /brains/new` đã tự seed cấu trúc
chuẩn, nên trang Chatbot chỉ việc gọi nó rồi mở trình sửa cho chủ đổ tri thức vào.

### 5.3 Trong nhóm thì khi nào bot mở miệng?

Bot trả lời mọi tin trong nhóm khách là thảm hoạ: khách nói chuyện với nhau cũng bị chen vào.

- **Chỉ khi được gọi tên hoặc reply thẳng vào bot** (đề xuất mặc định). Telegram còn giúp một
  tay: bot mặc định bật chế độ riêng tư, trong nhóm chỉ nhận được tin nhắc tên nó, tin reply
  nó, và lệnh. Nghĩa là hành vi đúng gần như miễn phí, miễn đừng tắt chế độ đó ở BotFather.
- Trả lời mọi tin: chỉ nên cho nhóm nhỏ, và phải là lựa chọn chủ động.
- Trả lời khi câu có dấu hỏi: nghe thông minh nhưng đoán sai nhiều, không nên.

## 6. Rào an toàn bắt buộc, không phải tuỳ chọn

Sáu thứ dưới đây nếu thiếu một cái thì đừng phát hành.

1. **Khoá mức quyền ở tầng mã, không phải ở prompt.** Lượt của bot chuyên trách luôn chạy
   `mode=suggest`, bất kể prompt nói gì. Prompt là thứ khách nói chuyện được với nó; mã thì
   không. Đây đúng nguyên tắc đã ghi ở `agent_runtime.py`: *"việc kiểm tra nằm trong code chứ
   không nằm trong prompt"*.
2. **Không MCP nào theo mặc định.** Muốn cấp thì cấp từng cái một, và không bao giờ cấp thứ
   tiêu tiền, tạo đơn hay gửi tin.
3. **Không ghi ký ức, không vào vòng tự học.** Hội thoại của khách là dữ liệu của khách. Để nó
   chảy vào `Memory/facts` của anh là vừa sai về riêng tư vừa làm bẩn bộ nhớ bằng câu hỏi của
   người lạ.
4. **Không lệnh quản trị.** Bot chuyên trách không có `/brain`, `/status`, `/skills`. Danh
   sách lệnh phải là danh sách TRẮNG riêng, không phải danh sách hiện tại bỏ bớt.
5. **Giới hạn tần suất mỗi người.** Một người rảnh rỗi trong nhóm đủ đốt hết quota model của
   anh trong một buổi chiều.
6. **Không biết thì nói không biết.** Bot khách hàng bịa một câu về chính sách bảo hành là rủi
   ro thật cho anh, không phải lỗi nhỏ. Câu trả lời phải dựa trên kho tri thức đã chỉ định, và
   khi không tìm thấy thì nói thẳng rồi mời chuyển người thật.

Về chèn lệnh qua tin nhắn: khách sẽ thử "quên hết hướng dẫn trước đi". Không chống bằng cách
dặn thêm trong prompt, vì dặn bao nhiêu cũng có đường lách. Chống bằng cách **để nó không có
gì để mất**: không tool nguy hiểm, không quyền ghi, không truy cập ngoài kho tri thức. Lúc đó
lách được prompt cũng chỉ khiến bot nói năng lạc đề, không gây hại thật.

## 6b. Trang Chatbot

Đây là cửa vào của cả tính năng, nên thiết kế nó trước rồi mọi thứ khác bám theo.

### Danh sách

Mỗi bot một thẻ, và thẻ phải trả lời được ba câu chỉ bằng cách liếc:

- **Nó là ai**: icon + tên bot + `@handle` Telegram + Agent đang dùng + brain đang đọc.
- **Nó đang sống không**: đèn trạng thái. Bốn trạng thái thật, không phải hai:
  `đang chạy` / `đã tắt` / `lỗi` (kèm lý do ngắn) / `đang khởi động`.
- **Nó đang làm gì**: trả lời ở đâu (chỉ tin riêng, hay kèm N nhóm), số tin hôm nay, lần trả
  lời gần nhất.

Nút trên thẻ: Bật/Tắt, Sửa, Xem hội thoại, Xoá.

**Bật/Tắt phải có tác dụng NGAY, không đòi khởi động lại Javis.** Đây là yêu cầu chức năng chứ
không phải tiện nghi: bot chăm sóc khách hàng nói bậy một câu thì phải tắt được trong ba giây.
Nghĩa là cần một **bộ giám sát bot**: mỗi bot là một task long-polling riêng, bật thì tạo
task, tắt thì huỷ task, sửa token thì huỷ rồi tạo lại.

### Luồng tạo bot

Năm bước, kiểu trình hướng dẫn giống trang Kết nối đang làm:

1. **Tên và icon bot.** Icon lấy từ bộ icon Lucide sẵn có (giống bộ chọn icon của Project ở
   0.18.1, dùng lại `Icons.names()`).
2. **Bộ não** - chọn một trong hai:
   - **Chọn Agent đã có**: danh sách Agent trong brain hiện tại, kèm vai trò và skill đã gán.
   - **Tạo Agent mới ngay tại chỗ**: form rút gọn (tên, vai trò, prompt, chọn skill, model),
     ghi ra `Javis/agents/<slug>.md` bằng đúng `POST /agents` đang có. **Không viết đường tạo
     agent thứ hai** - form này chỉ là lối tắt tới cùng một endpoint.
3. **Brain riêng.** Mặc định đề xuất tạo brain mới tên `bot-<slug>` qua `POST /brains/new`
   (đã tự seed cấu trúc chuẩn). Cho phép chọn brain có sẵn nếu chủ muốn hai bot dùng chung.
   Sau khi tạo, mở thẳng trình sửa để đổ tri thức vào, kèm một câu nhắc: **bot chỉ biết những
   gì nằm trong brain này**.
4. **Token Telegram.** Dán token lấy từ BotFather, kèm nút **Kiểm tra**: gọi `getMe`, hiện ra
   tên bot và `@handle` để chủ biết mình vừa dán đúng con nào. Token cất vào kho bí mật đã mã
   hoá (`secrets_store`), **không bao giờ ghi vào file `.md`** và không bao giờ trả ngược ra
   giao diện.
5. **Soát lại rồi tạo.** Bot tạo ra luôn ở trạng thái **TẮT**. Chủ tự bật sau khi đã thử nhắn
   riêng cho nó.

Thêm nhóm thì làm sau, ở màn Sửa, vì lấy id nhóm phải mời bot vào nhóm trước đã. Kèm một mẹo
ngay trên màn hình: mời bot vào nhóm rồi gõ `/id`, bot trả lại id nhóm để dán vào đây.

### Ba cái bẫy phải xử ngay từ đầu

1. **Trùng token = Telegram trả 409 và cả hai bot cùng chết.** Một token chỉ được một tiến
   trình long-polling. Nên phải chặn ở tầng lưu: không cho hai bot dùng chung token, và không
   cho dùng lại token của bot chính của chủ. Kiểm bằng cách so `getMe` chứ đừng so chuỗi token
   (cùng một bot vẫn có thể dán vào hai lần với khoảng trắng khác nhau).
2. **Sửa token khi bot đang chạy.** Phải huỷ task cũ TRƯỚC khi tạo task mới, không thì có lúc
   hai poller cùng sống và rơi vào bẫy 1.
3. **Bot chết âm thầm.** Token bị thu hồi ở BotFather, mạng rớt, Telegram đổi lỗi. Poller phải
   ghi lại lỗi cuối và đẩy lên thẻ, vì "bot không trả lời khách" là thứ chủ chỉ phát hiện khi
   khách phàn nàn. Đây đúng loại hỏng im lặng repo này đã vá hai lần trong tháng.

### Xem hội thoại khách

Dùng lại đúng kho hội thoại sẵn có: cột `channel` đã có trong `sessions`, đặt
`channel = "bot:<slug>"`. Nghĩa là hội thoại khách tự động có tìm kiếm toàn văn, phân trang và
ghim - không viết kho thứ hai. Và vì `list_sessions` lọc theo brain, hội thoại của bot nằm ở
brain riêng của nó nên **không lẫn vào Lịch sử của chủ**.

## 7. Lộ trình bốn giai đoạn

Xếp lại sau khi chốt trang Chatbot là cửa vào. Nguyên tắc giữ nguyên: mỗi giai đoạn xong là
**có thứ dùng được thật**, không phải xong hết mới thấy gì.

**Giai đoạn 1 - Tạo và chạy được một bot, chỉ nhắn riêng.** XONG, 0.19.0.
Kho bot + bộ giám sát nhiều poller (gỡ `_TG_BOT` khỏi thế biến toàn cục một cái) + trang
Chatbot đủ dùng: danh sách, trình tạo năm bước, bật/tắt không cần khởi động lại. Lượt của bot
đi qua `_tg_answer` với mức khoá cứng chỉ-đọc, không MCP, không lệnh quản trị.
*Xong là*: tạo bot trên dashboard, nhắn riêng cho nó, nó trả lời đúng vai trò Agent và không
đụng được gì ngoài brain của chính nó.

**Giai đoạn 2 - Trả lời có căn cứ.** XONG, 0.20.0 (`server/chatbot_grounding.py`).
Giới hạn phạm vi đọc trong brain của bot. Bắt dựa trên tài liệu, không tìm thấy thì nói không
biết thay vì suy đoán.
*Xong là*: bot trả lời theo tài liệu của anh thay vì theo trí nhớ chung của model.

Ba điều học được khi làm thật, đáng ghi lại vì không đoán ra từ trên giấy:

- **Chỉ giới hạn phạm vi đọc là chưa đủ.** Bot đã có tool đọc trỏ đúng brain của nó từ giai
  đoạn 1, nhưng có tool đọc không bằng có đọc: model trả lời thẳng bằng trí nhớ chung thì câu
  vẫn trôi chảy y hệt và chủ không phân biệt được từ bên ngoài. Nên tài liệu phải được tra
  TRƯỚC và nhét sẵn vào prompt, không giao việc đó cho model tự quyết.
- **Ngưỡng "coi như tìm thấy" phải đo bằng ĐỘ PHỦ câu hỏi, không phải điểm tuyệt đối.** "Cửa
  hàng có tuyển lập trình viên Rust không" trúng đúng chữ "hàng" trong mục Giao hàng, mà "hàng"
  hiếm nên IDF cao, nên điểm vượt ngưỡng. Thêm luật câu từ ba chữ có nghĩa trở lên phải trúng
  ít nhất hai chữ.
- **Từ dừng phải soạn riêng cho tiếng Việt BỎ DẤU.** "bán" và "bạn" cùng ra "ban"; loại "ban"
  theo thói quen là mất luôn chữ có nghĩa nhất của một bot bán hàng.

**Giai đoạn 3 - Vào nhóm.** XONG, 0.20.0.
Dùng `chat_type` sẵn có. Chỉ trả lời khi được gọi tên hoặc reply. Lệnh `/id` lấy id nhóm.
Chuyển người thật. Giới hạn tần suất mỗi người.
*Xong là*: thả vào nhóm khách hàng dùng thật được.

**Lỗ của 0.19.0 phát hiện khi rà lại giai đoạn này, ghi lại để đừng lặp:** luật mở miệng đọc
hai cờ `mentioned`/`reply_to_bot`, mà `TelegramBot._build_meta` không hề gắn chúng. Điều kiện
luôn sai nên bot IM trong MỌI nhóm. Bản 0.19.0 còn có test khẳng định đúng hành vi đó, và test
vẫn xanh - vì nó kiểm HỢP ĐỒNG của hàm `_nen_tra_loi` (cho cờ vào thì ra gì) chứ không kiểm ai
là người gắn cờ. Bài học: một luật đọc dữ liệu do NƠI KHÁC gắn thì phải có ít nhất một test đi
từ đầu vào thô (ở đây là JSON update của Telegram) tới quyết định cuối, chứ test từng mảnh xanh
hết vẫn hở đúng chỗ nối.

**Giai đoạn 4 - Đo lường.** XONG, 0.20.0 (`server/chatbot_log.py`).
Nhật ký hội thoại khách trên thẻ bot, và thống kê **câu hỏi bot trả lời không nổi**. Cái sau
là thứ có giá trị kinh doanh thật: nó chỉ đúng chỗ tài liệu của anh đang thiếu.

Làm rồi mới thấy: "bí" có hai loại, và loại thứ hai mới đáng chú ý. Không tìm ra tài liệu nào
là loại dễ thấy. Tìm ra tài liệu rồi mà vẫn phải nói chưa có thông tin mới là loại tinh vi -
tài liệu CÓ nhưng THIẾU Ý khách cần, và đó thường là chỗ đáng sửa nhất.

## 8. Những gì em khuyên KHÔNG làm

- **Đừng cho bot chuyên trách chạy Workflow ngay ở giai đoạn đầu.** Workflow chạy nhiều bước,
  tốn thời gian và token; khách hỏi trong nhóm cần câu trả lời trong vài giây. Skill thì có,
  Workflow để sau khi đã chạy ổn.
- **Đừng dùng chung `chat_id` whitelist làm cơ chế phân quyền.** Whitelist là danh sách người
  được nói chuyện, không phải danh sách người được làm gì. Hai thứ khác nhau, gộp là có ngày
  nhầm.
- **Đừng để bot tự gửi tin chủ động cho khách.** Trả lời khi được hỏi thì được, tự nhắn trước
  là chạm vào cả rào an toàn của Javis lẫn luật chống spam của Telegram.
- **Đừng làm Zalo trước Telegram.** Zalo cá nhân đi qua thư viện không chính thức, tài khoản
  có thể bị khoá; đem một tài khoản Zalo ra làm bot chăm sóc khách hàng là đặt cược vào thứ
  không kiểm soát được. Telegram có API bot chính thức, làm xong ổn rồi hãy tính Zalo OA.

### Cập nhật 2026-08-05: mục "khoá cứng ở chỉ-đọc" không còn đúng nữa

Mục 4 (mảnh số 4), mục 6 (rào số 1 và số 2) và bảng ở mục 3 đều viết trên giả định **bot luôn
chỉ đọc**. Chủ repo bỏ giả định đó: *"anh vẫn muốn có thể thực hiện nhiều task, nhưng em thêm
phần thông báo cho anh để hiểu rõ nguy cơ khi sử dụng."* Xem mục 10.

Giữ nguyên văn ba mục kia thay vì sửa lại, vì lý lẽ trong đó vẫn đúng cho mức mặc định - và
đọc được vì sao mặc định phải là chỉ-đọc thì mới hiểu được cái giá của việc nâng mức.

## 9. Còn cần anh chốt

Hai câu đầu đã trả lời rồi (brain riêng, token riêng, có trang quản lý). Còn hai:

1. **Bao nhiêu bot cho lần đầu?** Em khuyên **một con, một lĩnh vực hẹp, một nhóm**. Chạy thật
   một tuần sẽ lộ ra nhiều thứ hơn là bàn tiếp trên giấy, và giai đoạn 1 vốn đã đủ để thử.
2. **Khách hỏi ngoài phạm vi thì bot làm gì?** Im lặng, hay nói "để em chuyển anh chị cho nhân
   viên"? Cái sau cần có người thật trực, nên phụ thuộc anh có người hay không. Nếu chưa có
   thì mặc định nên là nói thẳng "cái này em chưa có thông tin" rồi dừng, chứ đừng đoán.

## 10. Mở phạm vi (2026-08-05): ba mức quyền

Chủ repo: *"ở chức năng tạo bot đang là chỉ đọc, anh muốn thêm chức năng được ghi và toàn
quyền. Vì cơ bản anh vẫn muốn có thể thực hiện nhiều task, nhưng em thêm phần thông báo cho
anh để hiểu rõ nguy cơ khi sử dụng."* Ra ở 0.24.0.

### Bài toán thật nằm ở đâu

Không phải "làm sao cấp tool cho bot" - cấp tool là chuyện dễ. Bài toán là **cấp tool mà không
đánh mất hai rào đã có**, vì hai rào đó chính là lý do 0.21.0 tồn tại:

1. **Cách ly brain.** Bot chỉ thấy brain của nó.
2. **Không lệnh máy.** Không Bash, không web, không agent con.

Đường dễ nhất - mở CLI cho bot rồi giới hạn bằng `allowed_tools` như loop đang làm - **mất cả
hai cùng lúc**. `Read` của Claude Code nhận đường dẫn TUYỆT ĐỐI, nên một allowlist có `Read`
là bot đọc được mọi brain và cả `/etc/passwd`. Đúng lỗ 0.21.0 đã phải vá, và vá bằng cách bỏ
tool hẳn.

### Lời giải: tool CHỈ đến từ hub, trên cả tám bộ não

Bot không bao giờ mở CLI. Ở mức nới quyền nó đi vòng gọi tool kiểu API (`*_chat_with_mcp`) với
tool lấy từ `mcp_hub.discover_all(muc_quyen, vault_root=<brain của bot>)`. Ba hệ quả, và cả ba
đều là hệ quả của KIẾN TRÚC chứ không phải một rào phải canh:

- Tool file đi qua `_safe_path(vault_root)` → cách ly brain giữ nguyên **kể cả ở mức full**.
- Hub không có Bash/WebFetch/WebSearch/Task → rào số 2 giữ nguyên.
- `muc_quyen` thành `mode` của hub → `mcp_catalog.allowed()` chặn nhóm nguy hiểm ở mức `auto`
  ngay tại chỗ gọi, không phụ thuộc prompt.

Hai gói thuê bao không bị bỏ lại (lời hứa "đổi bộ não không đổi năng lực"): ChatGPT đi
`responses_with_mcp`, Claude Code đi `anthropic_chat_with_mcp` với `oauth_token` - tham số mới
thêm ở bản này, mirror đúng cặp header mà `anthropic_stream` đã dùng.

### Vì sao hai đường tách hẳn nhau

`_bot_tra_loi` (không tool) và `_bot_tra_loi_co_tool` (có tool) là hai hàm riêng, dùng chung
mấy mảnh nhỏ (lịch sử, đọc stream, ghim đường đo). Cố ý:

- Đường không-tool phải **soi được bằng mắt** là không có tool nào, và có test cắt đúng thân
  hàm đó ra kiểm (`test_chatbot_cach_ly.py` mục B2). Nhét cả hai vào một hàm với một cái `if`
  thì canary ấy không viết được nữa.
- Mức Chỉ đọc là mặc định, tức đường đi của gần như mọi bot. Nó không được động vào khi thêm
  tính năng cho hai mức kia.

### Chỗ dễ hỏng nhất, ghi lại để đừng lặp

- **Rẽ nhánh phải fail-closed.** `if _muc in MUC_NANG` chứ không phải `if _muc != "suggest"`.
  Vế sau thì một lỗi chính tả trong `chatbots.json`, hay một bản ghi cũ thiếu khoá, cũng đủ
  cấp tool cho bot đang chat với người lạ.
- **Giá trị lạ khi SỬA thì giữ mức cũ**, không rơi về mặc định. Rơi về mặc định là hạ quyền
  im lặng: chủ tưởng bot vẫn làm việc, còn nó thì từ chối mọi tool mà không ai biết.
- **Rào xác nhận phải ở KHO, không chỉ ở route.** Route là một trong nhiều đường vào (giao
  diện, chat tự tạo bot, script của chủ). Đặt ở kho thì đường nào cũng đi qua.
- **Chỉ chặn lúc NÂNG.** Bắt xác nhận lúc hạ mức là dựng rào đúng lúc chủ đang dập sự cố.
- **Cảnh báo do server cấp, giao diện không chép.** Chép rồi thì một hôm server siết thêm rào
  mà ô cảnh báo vẫn hứa như cũ, và chủ bấm đồng ý dựa trên một câu đã sai.

### Cái KHÔNG giải được bằng mã, và phải nói thẳng với chủ

Ở mức `full`, người điều khiển tool là **người nhắn cho bot**. Rào còn lại đúng bằng file Agent chủ viết,
mà chữ thì lách được - đây chính là điều mục 6 đã cảnh báo ("không chống chèn lệnh bằng cách
dặn thêm trong prompt"), chỉ khác là giờ bot CÓ thứ để mất.

Nên phần "thông báo nguy cơ" chủ repo yêu cầu không phải là tính năng phụ, nó là **nửa còn lại
của lời giải**: mã chặn được cái chặn được, phần còn lại chủ phải biết trước khi bấm. Vì thế
cảnh báo kể ra cái MẤT ĐƯỢC (loại thao tác, không hoàn tác, ai điều khiển) chứ không phải một
câu "hãy cẩn thận" - và nó xuất hiện ba lần: lúc chọn mức, lúc lưu mức `full`, lúc Bật bot.

Một chỗ nữa phải giữ, vì bản đầu sai đúng chỗ này: cảnh báo tả theo **LOẠI THAO TÁC** (gửi đi,
thanh toán, đặt/huỷ, xoá, công bố), KHÔNG kể tên việc của một ngành. Bản đầu viết "tạo đơn,
tiêu tiền quảng cáo, đăng bài" - lọt tai người bán hàng, vô nghĩa với người dùng Javis để quản
lý dự án, chăm sức khoẻ hay dạy học. Tệ hơn: người đó đọc xong tưởng cảnh báo không áp cho
mình rồi bật Toàn quyền vì nghĩ mình không có gì để mất. Chủ repo bác (2026-08-05): "nó cá
nhân hóa với anh quá". Có canary ở cả test Python lẫn test JS.
