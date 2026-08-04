# Đề xuất: Bot chuyên trách - biến Agent thành chatbot trả lời khách

Chủ repo nêu ngày 2026-08-04, thay cho ý "Cho Agent gắn chatbot AI" còn để mở trong
`2026-08-backlog-spec.md` mục 2. Ý đã rõ hẳn, và nó không trùng cách hiểu nào trong ba cách
em đoán lúc đó.

Trạng thái: **đang bàn, chưa làm gì**.

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

## 4. Đề xuất: thêm một lớp "xuất bản", KHÔNG thêm một loại thực thể mới

Anh nói "tận dụng Agent sẵn có", nên đừng đẻ ra khái niệm Bot song song với Agent rồi phải
nuôi hai chỗ. Thay vào đó, **Agent có thêm phần khai báo xuất bản**:

```yaml
---
type: agent
name: Tư vấn sản phẩm
slug: tu-van-san-pham
role: Trả lời khách về công dụng, giá, cách dùng
skills: [tu-van-ban-hang, chinh-sach-doi-tra]
model: sonnet

# ── phần MỚI: xuất bản thành chatbot ──
publish:
  enabled: false            # luôn tắt lúc tạo, chủ tự bật
  channel: telegram
  bot_token_ref: tuvan      # trỏ tới token cất trong kho bí mật, KHÔNG ghi token vào .md
  knowledge:                # phạm vi ĐỌC, đường dẫn trong brain
    - wiki/san-pham
    - sources/bang-gia.md
  groups: ["-1001234567890"]   # nhóm được phép; rỗng = chỉ trả lời tin nhắn riêng
  reply_when: mention          # mention | always | question
  handoff_to: "123456789"      # chat_id người thật để chuyển khi bí
  rate_limit: 20               # tin mỗi người mỗi giờ
---
```

Năm mảnh của một bot chuyên trách, và mảnh nào cũng đã có sẵn ba phần tư:

1. **Bộ não** = Agent (vai trò + prompt + skill). Có sẵn.
2. **Kho tri thức** = vài đường dẫn trong brain. Cần thêm phần giới hạn phạm vi đọc.
3. **Kênh** = một bot Telegram riêng. Cần cho chạy nhiều bot cùng lúc.
4. **Mức quyền** = khoá cứng ở chỉ-đọc. Cơ chế đã có (`min_mode`, `effective_perm`), chỉ cần
   nối đúng chỗ.
5. **Đường thoát** = chuyển người thật khi bí. Chưa có, phải viết.

## 5. Ba quyết định lớn, kèm khuyến nghị

### 5.1 Mỗi bot một token riêng, hay một bot chung định tuyến theo nhóm?

- **Một token riêng cho mỗi bot** (đề xuất chọn): mỗi con có tên, ảnh đại diện và `@handle`
  riêng do anh tạo ở BotFather. Thả vào nhóm khách thì nó là "Trợ lý Sản phẩm" chứ không phải
  "Javis của anh Quý". Đây là khác biệt về hình ảnh thương hiệu, không phải chuyện kỹ thuật.
  Giá phải trả: phải cho chạy nhiều poller cùng lúc, hiện `_TG_BOT` đang là biến toàn cục một
  cái (`server/main.py:9548`).
- **Một bot chung**: nhẹ hơn nhiều, nhưng mọi lĩnh vực chung một danh tính, và không thả được
  hai bot khác nhau vào hai nhóm khác nhau.

### 5.2 Bot đọc brain nào?

- **Brain riêng cho bot** (đề xuất chọn): tạo một brain nhỏ chỉ chứa tri thức khách được xem.
  Cách ly vật lý là cách ly duy nhất không hỏng khi ai đó viết sai một dòng code sau này.
- Đọc brain chính nhưng giới hạn thư mục: đỡ công chuẩn bị, nhưng rào chỉ nằm ở mã. Một lỗi
  đường dẫn là lộ cả brain.

Bắt đầu bằng brain riêng. Nếu sau này thấy phiền vì phải chép tri thức sang, tính tiếp.

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

## 7. Lộ trình bốn giai đoạn

Chia theo nguyên tắc: mỗi giai đoạn xong là **có thứ dùng được thật**, không phải xong hết mới
thấy gì.

**Giai đoạn 1 - Một Agent thành một bot, chỉ nhắn riêng.**
Gỡ `_TG_BOT` khỏi thế biến toàn cục một cái, cho chạy nhiều bot. Thêm khối `publish` vào
Agent. Lượt của bot đi qua `_tg_answer` với mức khoá cứng chỉ-đọc và không MCP.
*Xong là*: nhắn riêng cho bot, nó trả lời đúng vai trò Agent, không đụng được gì.

**Giai đoạn 2 - Kho tri thức và trả lời có căn cứ.**
Giới hạn phạm vi đọc. Bắt trích nguồn trong nội bộ. Không tìm thấy thì nói không biết.
*Xong là*: bot trả lời đúng theo tài liệu của anh thay vì theo trí nhớ chung của model.

**Giai đoạn 3 - Vào nhóm.**
Dùng `chat_type` sẵn có. Chỉ trả lời khi được gọi tên hoặc reply. Chuyển người thật. Giới hạn
tần suất.
*Xong là*: thả vào nhóm khách hàng dùng thật được.

**Giai đoạn 4 - Quản lý và đo lường.**
Trang quản lý bot trong dashboard, nhật ký hội thoại khách (tách khỏi hội thoại của anh, dùng
được chính cột `channel` và khái niệm Project vừa thêm ở 0.18.0), thống kê câu hỏi hay gặp mà
bot trả lời không nổi. Cái cuối là thứ có giá trị kinh doanh thật: nó chỉ ra tài liệu của anh
đang thiếu chỗ nào.

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

## 9. Cần anh chốt

1. **Một bot một token, hay một bot chung?** (Em nghiêng mỗi bot một token: thả vào nhóm khách
   thì danh tính riêng mới ra dáng.)
2. **Brain riêng cho bot, hay giới hạn thư mục trong brain chính?** (Em nghiêng brain riêng.)
3. **Bao nhiêu bot cho lần đầu?** Làm một con chạy thật với một lĩnh vực hẹp sẽ lộ ra nhiều
   thứ hơn là bàn tiếp trên giấy. Anh chọn giúp một lĩnh vực và một nhóm để thử.
4. **Khách hỏi ngoài phạm vi thì bot làm gì?** Im lặng, hay nói "để em chuyển anh chị cho nhân
   viên"? Cái sau cần một người thật trực, nên phụ thuộc anh có người hay không.
