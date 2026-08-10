# Kênh Telegram

Bật bot Telegram để hỏi Javis ngay từ điện thoại, không cần mở dashboard. Bạn nhắn cho bot như nhắn cho một người, Javis trả lời bằng chính bộ não và bộ nhớ đang chạy trên máy/VPS của bạn.

## Tính năng này là gì

- Bạn tạo một bot Telegram riêng (miễn phí), dán token vào Javis, giới hạn chỉ tài khoản của bạn được dùng.
- Sau khi bật, mọi tin nhắn thường bạn gửi cho bot sẽ được Javis trả lời. Bot vừa bật chỉ báo "đang gõ" của Telegram, vừa gửi một tin trạng thái tự đổi chữ theo tiến trình rồi tự xoá khi có câu trả lời.
- Có sẵn các lệnh gõ nhanh (bắt đầu bằng dấu `/`) để xem trạng thái, đổi model, dừng câu đang chạy, bắt đầu hội thoại mới, lưu note vào brain.
- Qua Telegram Javis vẫn có đủ MCP và skill: hỏi số liệu bán hàng, quảng cáo, đọc và ghi file trong vault đều được. Điều này đúng với MỌI engine (Claude Code, ChatGPT/Codex, OpenRouter, Claude API, OpenAI API) vì công cụ của Javis đi qua MCP Hub chứ không gắn riêng vào engine nào.
- Gửi file được cả hai chiều: bạn gửi ảnh/tài liệu cho bot để Javis đọc, và file Javis tạo ra trong lượt sẽ tự gửi ngược về cho bạn.
- **Ra lệnh bằng ghi âm**: bấm giữ micro nói một câu, Javis nghe thành chữ rồi làm như bạn gõ tay. Cần dán API key Groq ở trang Models một lần.
- Trả lời chạy nền: đang trả lời câu này bạn vẫn gửi được `/stop` để cắt ngang.

Xem thêm engine và model ở [Models & engine](10-models-va-engine.md), công cụ MCP ở [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md).

## Mở ở đâu trong Javis

1. Mở dashboard Javis (mặc định `http://localhost:7777`).
2. Nhìn thanh điều hướng bên trái, mở nhóm **Kết nối** rồi bấm mục **Kênh**.
3. Bạn sẽ thấy thẻ **Telegram** với các ô: bật/tắt bot, Bot token, Chat ID được phép dùng, và 2 nút **Lưu & bật** / **Gửi test**.

## Chuẩn bị: lấy Bot token và Chat ID

Đây là 2 thông tin bắt buộc. Làm trên app Telegram (điện thoại hoặc máy tính).

### Lấy Bot token (từ BotFather)

1. Trong Telegram, tìm tài khoản tên **@BotFather** (có tick xanh) và mở chat.
2. Gõ `/newbot` rồi làm theo hướng dẫn: đặt tên hiển thị cho bot, rồi đặt username kết thúc bằng `bot` (vd `javis_cua_toi_bot`).
3. BotFather trả về một chuỗi token dạng `123456789:ABCdef...`. Đây chính là **Bot token**. Giữ kín, ai có token này là điều khiển được bot.

### Lấy Chat ID của bạn (và của những người dùng chung)

Chat ID là số định danh tài khoản Telegram. Javis dùng nó làm danh sách cho phép: chỉ những ID trong danh sách mới nhắn được với bot.

1. Trong Telegram tìm bot tên **@userinfobot** và mở chat, bấm Start.
2. Nó trả về dòng `Id: 123456789`. Con số đó là **Chat ID** của bạn.
3. Ghi lại con số này để dán vào Javis ở bước sau.

Muốn cho người khác (vợ/chồng, nhân viên...) dùng chung bot: nhờ từng người làm đúng 2 bước trên để lấy Chat ID của họ, và nhớ mỗi người phải mở bot của bạn bấm **Start** một lần (Telegram chỉ cho bot nhắn với người đã Start).

## Cách dùng (từng bước)

### Bước 1: Cấu hình và bật bot

1. Vào **Kênh** (nhóm **Kết nối**) trên dashboard, tới thẻ **Telegram**.
2. Tích ô **Bật bot Telegram**.
3. Dán chuỗi token vào ô **Bot token**. (Nếu trước đó đã đặt token, cạnh nhãn hiện chữ "(đã đặt)"; để trống ô này nếu không muốn đổi token.)
4. Dán Chat ID vào ô **Chat ID được phép dùng**. Nhiều người dùng chung thì dán nhiều ID cách nhau dấu phẩy, ví dụ `123456789, 987654321`.
5. Bấm **Lưu & bật**.

Javis lưu cấu hình và tự khởi động lại bot ngay sau khi bấm Lưu (bạn không cần bấm nút riêng để restart). Dòng trạng thái dưới thẻ sẽ báo "✅ Đã lưu, đang khởi động bot…" rồi tự cập nhật sau gần 2 giây.

### Bước 2: Kiểm tra bot đã nhận tin

Dòng chữ nhỏ ngay dưới 2 nút là trạng thái thật của bot. Ý nghĩa từng dòng:

| Dòng trạng thái | Nghĩa |
|---|---|
| 🟢 Bot đang nhận tin | Bot chạy tốt, nhắn cho bot là Javis trả lời. Dòng này kèm số chat ID được phép, hoặc cảnh báo "MỌI NGƯỜI nhắn được (chưa giới hạn ID)" |
| ⚪ Bot CHƯA bật | Chưa tích "Bật bot Telegram" rồi Lưu |
| ⚪ Chưa có bot token | Đã bật nhưng chưa dán token |
| ⏳ Đang khởi động bot | Bot vừa được bật, chờ vài giây |
| 🔴 409 | Cùng token này đang bị chạy (poll) ở nơi khác, hoặc còn webhook. Xem mục Sự cố bên dưới |
| ⚠ Lỗi bot | Có lỗi khác, dòng sẽ kèm mô tả chi tiết |
| ⚪ Bot đã tắt | Bot đã dừng (chưa bật lại) |

Lưu ý quan trọng: gửi test thành công KHÔNG có nghĩa bot đang nhận tin. Test chỉ chứng minh token và Chat ID đúng. Muốn biết bot có nhận tin hay không, hãy xem dòng trạng thái phải là 🟢 **Bot đang nhận tin**.

### Bước 3: Gửi tin test (tùy chọn)

1. Bấm nút **Gửi test**.
2. Nếu token và Chat ID hợp lệ, Javis gửi vào chat Telegram của bạn một tin: "✅ Javis Telegram đã kết nối. Nhắn câu hỏi bất kỳ nhé." Dòng trạng thái báo "✅ Đã gửi tin test." (nhiều ID thì báo "✅ Đã gửi tin test tới 2/3 ID." kèm lỗi của ID hỏng).
3. Nếu chưa lưu đủ token và Chat ID, nút test báo thiếu cấu hình. Hãy Lưu & bật trước rồi thử lại.

### Bước 4: Hỏi Javis qua Telegram

1. Mở chat với bot của bạn trên Telegram.
2. Gõ một câu hỏi bất kỳ như đang chat bình thường, vd "Hôm nay có task gì cần làm?" hoặc "Tóm tắt vault giúp tôi".
3. Bot hiện chỉ báo "đang gõ" kèm một tin trạng thái tạm, rồi gửi câu trả lời. Câu trả lời dài sẽ được tự chia thành nhiều tin.
4. Trong lúc bot đang trả lời, nếu bạn gửi câu mới, bot báo "⏳ Đang xử lý câu trước. Gửi /stop để dừng rồi hỏi lại." Mỗi lúc chỉ chạy 1 lượt cho mỗi người.

## Tin trạng thái tự đổi chữ rồi ở lại thành dòng vết

Ngay khi nhận câu hỏi, bot gửi cho bạn một tin thật: **🤔 Javis đang xử lý…**. Tin đó KHÔNG bị gửi thêm lần nữa, nó được **sửa nội dung tại chỗ** theo tiến trình, luôn mở đầu bằng ⏳:

| Chữ bạn thấy | Javis đang làm gì |
|---|---|
| 🤔 Javis đang xử lý… | Vừa nhận câu hỏi, đang khởi động lượt |
| ⏳ ⚙ Đang gọi: `<tên tool>` | Engine Claude đang gọi một công cụ (Read, Write, tool MCP...) |
| ⏳ ⚙ Đang gọi công cụ: `<tên tool>` | Engine API (OpenRouter, OpenAI API, Claude API) đang gọi công cụ qua MCP Hub |
| ⏳ ✓ Nhận kết quả - đang phân tích… | Công cụ trả dữ liệu về, engine đang đọc |
| ⏳ ✍ Đang soạn câu trả lời… | Đã bắt đầu sinh chữ |

Vài điểm cần biết:

- Tin trạng thái chỉ cập nhật tối đa **2,5 giây một lần**, nên đừng chờ nó nhảy liên tục. Giới hạn này để Telegram không chặn bot vì gửi quá dày.
- Tin này **gửi im lặng, không rung điện thoại**. Nó chỉ để bạn nhìn khi đang mở chat chờ. Cả lượt hỏi chỉ có đúng một tiếng chuông: lúc câu trả lời thật tới, và thông báo hiện đúng nội dung trả lời.
- Xong việc, bot **không xoá tin trạng thái nữa**. Lần sửa cuối biến nó thành một dòng vết gọn, còn câu trả lời là tin mới nằm ngay dưới. Từ **0.26.4** mới như vậy; trước đó tin này bị xoá hẳn nên nhiều người tưởng bot lỗi.
- Dòng vết ghi lượt đó đã gọi công cụ nào và mất bao lâu, ví dụ `⚙ pos_statistics · Read · 8s`. Lượt không cần công cụ nào thì ghi `✓ Trả lời trực tiếp · 3s`. Đây là cách phân biệt một con số vừa lấy từ POS thật với một câu trả lời chay, và nó nằm lại trong lịch sử để sau tra lại được.
- Gõ `/stop` giữa chừng: tin trạng thái đổi thành **⏹ Đã dừng.** và bot không gửi thêm câu trả lời nào cho lượt đó.
- Dòng "⚙ Đang gọi..." chính là bằng chứng Javis đang chạm vào MCP thật (POS, quảng cáo, lịch, file...) chứ không phải trả lời chay.
- Mấy tin trạng thái này chỉ có ở **bot Javis của bạn**. [Bot chuyên trách](25-chatbot.md) nói chuyện với khách thì giấu sạch, chỉ để lại chấm "đang nhập…" cho giống người thật.

## Gửi file cho bot, nhận file từ bot

Bot chạy được cả hai chiều file. Đây là cách nhanh nhất để đưa một tấm ảnh hay tài liệu vào brain khi đang ở ngoài đường.

### Bạn gửi ảnh/file cho bot

1. Gửi thẳng ảnh hoặc file tài liệu vào chat với bot, kèm caption nếu muốn nói rõ ý.
2. Gateway tải file về `inbox/telegram/` **của brain đang chọn cho phiên Telegram của bạn** (đổi bằng `/brain`), rồi đưa đường dẫn đó vào tin nhắn cho engine đọc.
3. Javis đọc file tại chỗ và trả lời như bình thường. File trùng tên không bị đè: Javis thêm hậu tố `_1`, `_2`.

Giới hạn cần nhớ:

- **Trần tải về là 20MB** (giới hạn của Telegram bot API, không phải của Javis). File to hơn, bot báo lại là không tải về được và gợi ý cách gửi khác.
- **Tin thoại (ghi âm) thì Javis nghe được** - xem mục ngay dưới đây.
- **Video và video note: Javis chưa xem được.** Bot sẽ lịch sự nhờ bạn gõ chữ, gửi tin thoại, hoặc gửi lại dạng file tài liệu.
- Caption là một lệnh cũng được nhận đúng. Ví dụ chộp ảnh hoá đơn rồi đặt caption `/notes hoá đơn thép hộp hôm nay` thì Javis chạy lệnh `/notes` với đúng tấm ảnh đó, chứ không coi cả cụm là chữ thường.
- `inbox/` là **vùng cache**, không phải kho tri thức: file quá **30 ngày** hoặc khi vùng cache vượt **300MB** sẽ bị dọn tự động. Cần giữ lâu dài thì bảo Javis rút nội dung thành ghi chú `.md` hoặc chuyển sang thư mục khác trong brain. Xem [Quản lý tệp tin](05-quan-ly-tep-tin.md).

### Ra lệnh bằng ghi âm (tin thoại)

Bấm giữ nút micro trong Telegram, nói, rồi thả tay. Javis nghe câu đó thành chữ và làm y như bạn gõ tay - tiện nhất lúc đang lái xe hoặc tay bận.

**Cần một thứ: API key của Groq.** Groq là chỗ Javis mượn để chuyển giọng nói thành chữ (model Whisper). Chưa đấu thì gửi tin thoại Javis sẽ trả lời là cần dán key, kèm chỉ dẫn - chứ không im lặng.

Cách đấu, làm một lần:

1. Vào [console.groq.com](https://console.groq.com), đăng nhập, tạo một API key.
2. Mở dashboard Javis, vào trang **Models**, tìm nhà cung cấp **Groq (API)**, dán key vào rồi lưu.
3. Xong. Gửi tin thoại tiếp theo là nghe được ngay, **không cần tắt bật lại bot**.

Vài điều nên biết:

- **Key này dùng chung với phần chat.** Đã đấu Groq làm bộ não thì tin thoại chạy luôn, không phải làm gì thêm. Ngược lại, đấu key chỉ để nghe giọng cũng được - không bắt buộc phải đổi model chính sang Groq.
- **Javis nghe tiếng Việt** (có gợi ý ngôn ngữ cho Whisper nên câu ngắn không bị đoán nhầm sang tiếng khác rồi dịch luôn).
- **Việc có tác động ra ngoài thì Javis hỏi lại trước.** Gửi tin, đăng bài, đặt lịch, tiêu tiền, sửa file: Javis mở đầu bằng một dòng "Em nghe: ..." rồi chờ bạn xác nhận. Máy vẫn nghe nhầm được, mà mấy việc đó lỡ làm rồi thì không rút lại. Hỏi số liệu, tra cứu, tóm tắt thì làm thẳng, không hỏi lại.
- **File ghi âm không được lưu vào brain.** Javis nghe xong lấy chữ, không để lại file `.ogg` trong `inbox/`.
- Gửi tin thoại kèm caption `/notes` vẫn chạy đúng lệnh, với nội dung là câu bạn vừa nói.
- Nghe không ra chữ (im lặng, quá ồn) hay Groq trả lỗi thì bot nói rõ lý do và nhờ bạn gõ chữ. Không có ngả nào im lặng.

Kênh Zalo cũng nghe được tin thoại, dùng **chung một key Groq** - đấu một lần là hai kênh cùng chạy. Xem [Kênh Zalo Bot](26-kenh-zalo-bot.md).

### Bot gửi file về cho bạn

File Javis tạo ra trong lượt được **tự đính kèm ngay sau câu trả lời**, không cần bạn xin. Ba nguồn được nhận:

- File Javis ghi bằng công cụ Write trong chính lượt đó.
- File có đường dẫn tuyệt đối nhắc trong câu trả lời cuối.
- Ảnh/tệp trong vault nhúng kiểu markdown tương đối, vd `![](attachments/anh.png)` - đúng cách ảnh Javis vừa tạo được trả về.

Giới hạn và hành vi:

- Tối đa **10 file một lượt**, mỗi file dưới **50MB** (trần gửi tài liệu của Telegram).
- Chỉ file **vừa tạo hoặc vừa sửa trong lượt đó** mới được gửi. Nhắc tên một file cũ sẽ không làm bot gửi lại nó, để tránh spam.
- Ảnh `.jpg .jpeg .png .webp .gif` dưới **10MB** được gửi dạng ảnh (xem preview ngay trong chat); còn lại gửi dạng tài liệu. Ảnh bị Telegram từ chối thì tự rơi xuống gửi dạng tài liệu.
- Nếu ảnh đã được gửi riêng, dòng markdown `![...](...)` tương ứng bị bóc khỏi câu trả lời để bạn không thấy một cụm chữ trơ nằm cạnh tấm ảnh thật.
- Gửi hỏng thì bot nói thẳng: "⚠ Không gửi được file `<tên>`: `<lý do>`".
- Text đi trước, file đi sau, để thứ tự đọc tự nhiên.

## Khi Javis hỏi lại bằng lựa chọn đánh số

Trên dashboard, khi phải hỏi lại một tham số quan trọng (kỳ thời gian, chọn shop nào...), Javis vẽ ra mấy cái nút bấm. Telegram là kênh chữ thuần, không vẽ nút kiểu đó được, nên Javis tự hạ khối lựa chọn xuống thành **câu hỏi kèm danh sách đánh số** (tối đa 4 lựa chọn):

```
Anh muốn xem doanh thu kỳ nào?
1. Tuần này
2. Tháng này
3. So tháng trước
```

Trả lời bằng cách nhắn đúng con số, vd `2`, hoặc gõ hẳn điều bạn muốn. Javis đọc con số trong ngữ cảnh câu vừa hỏi nên hiểu ngay, không cần cú pháp gì đặc biệt.

## Các lệnh gõ nhanh trong Telegram

Gõ dấu `/` trong chat (hoặc bấm nút Menu của bot) sẽ hiện danh sách lệnh. Các lệnh có sẵn:

| Lệnh | Tác dụng |
|---|---|
| `/help` | Xem hướng dẫn và danh sách lệnh |
| `/status` | Xem provider, model, brain đang dùng và bot có đang bận trả lời không |
| `/skills` | Liệt kê các skill có trong vault (gõ `/tên-skill` để gọi) |
| `/notes` | Lưu tin nhắn (kèm ảnh) vào Sources của brain. Gõ `/notes <nội dung>`, hoặc gửi ảnh với caption `/notes ...` |
| `/agents` | Liệt kê agent và cho biết có lượt nào đang chạy không |
| `/workflows` | Liệt kê workflow |
| `/model` | Xem hoặc đổi model. Gõ `/model` không kèm gì để mở bảng nút bấm chọn; hoặc gõ thẳng tên (vd `/model sonnet`) |
| `/brain` | Xem hoặc đổi brain (vault) cho RIÊNG phiên của bạn. Gõ `/brain` để mở bảng nút chọn; hoặc gõ thẳng tên (vd `/brain Kim Khí`). Đổi xong hội thoại reset để nạp đúng bộ nhớ brain mới; người khác và dashboard không bị ảnh hưởng. File bạn gửi lên cũng rơi vào inbox của brain đã chọn |
| `/retry` | Gửi lại câu hỏi gần nhất |
| `/stop` | Dừng ngay câu đang trả lời |
| `/reset` | Bắt đầu hội thoại mới (quên ngữ cảnh cũ) |
| `/cli` | Chuyển sang engine Claude (Claude Code) |
| `/or` | Chuyển sang engine OpenRouter (chat + MCP đa-model) |

`/notes` không có nhánh xử lý riêng trong bot: nó chạy qua đúng đường của một skill, nên cũng cần engine khác OpenRouter (xem mục dưới). Chi tiết skill này ở [Skills](06-skills.md).

Chi tiết cách gõ `/model`:

- Bảng nút bấm khi gõ `/model`: chọn provider ĐÃ KẾT NỐI (Claude Code, ChatGPT, OpenRouter, Claude API, OpenAI API - provider đang dùng có dấu ✓ kèm số model), rồi tới lưới model 2 cột, 8 model một trang, nút ◀ ▶ lật trang. Danh sách model lấy TRỰC TIẾP từ provider (OpenRouter hiện đầy đủ vài trăm model, ChatGPT hiện model Codex), không phải danh sách cứng.
- Gõ thẳng tên cũng được: tên có dấu `/` (vd `openai/gpt-4o`) là model OpenRouter; `gpt-...` hoặc `...-codex` là model ChatGPT (cần đã kết nối OAuth); còn lại (vd `opus`, `sonnet`, `fable`) là model Claude.
- Bảng nút của `/model` chỉ có 5 provider trên. Trang **Models** trên dashboard còn thêm Google Gemini (API); muốn dùng Gemini thì chọn ở dashboard.

## MCP và skill qua Telegram

- **Mọi engine đều dùng được MCP của Javis qua Telegram**, vì công cụ đi qua MCP Hub chứ không gắn cứng vào một engine. Chính text `/help` của bot cũng ghi: "ChatGPT/Codex và OpenRouter đều dùng được MCP của Javis." Bạn thấy nó chạy thật khi tin trạng thái hiện dòng "⚙ Đang gọi công cụ: ...".
- Gọi skill bằng cú pháp `/tên-skill`. Cửa này CÓ chặn một trường hợp: đang ở engine OpenRouter mà gõ `/tên-skill` thì bot nhắc "⚠ Skill cần engine Claude CLI. Gửi /cli để đổi, rồi /tên-skill lại."
- Đổi engine ngay trong Telegram: gõ `/cli` để về Claude (bot đáp "✅ Provider: Anthropic (Claude Code) - đầy đủ MCP, hỏi POS/Ads/vault được."), `/or` để sang OpenRouter (bot đáp "✅ Provider: OpenRouter (`<model>`) - chat + MCP đa-model."). Đổi ở đây cũng đổi luôn cho toàn hệ Javis (dashboard và bot dùng chung một cấu hình model).
- Muốn dùng `/or` thì cần đã đặt OpenRouter key trong trang [Models & engine](10-models-va-engine.md); chưa có key bot sẽ nhắc "⚠ Chưa có OpenRouter key - đặt trong Models trên dashboard trước."

## Giới hạn quyền: chỉ mình bạn dùng bot

- Ô **Chat ID được phép dùng** chính là whitelist. Chỉ các tài khoản Telegram có ID trong danh sách mới nhắn được với bot. Người lạ nhắn vào sẽ nhận: "Bạn không có quyền dùng bot Javis này."
- Nếu để trống ô Chat ID: bất kỳ ai tìm ra bot đều dùng được. Không nên để trống, vì bot có thể chạm vào vault và số liệu của bạn. Luôn đặt ít nhất 1 Chat ID.
- Cho thêm người dùng chung 1 bot: thêm Chat ID của họ vào ô, cách nhau dấu phẩy, rồi **Lưu & bật**. Nút **Gửi test** sẽ gửi tin thử tới TẤT CẢ ID và báo rõ ID nào lỗi (thường do người đó chưa bấm Start bot).
- Mỗi người có **mạch hội thoại riêng**: ngữ cảnh của từng Chat ID tách biệt, không lẫn sang người khác, và hai người có thể nhắn cùng lúc mà không phải chờ nhau. `/reset` và `/stop` chỉ tác động phiên của chính người gõ. Tuy vậy tất cả vẫn **chung một vault và cùng quyền** (ai cũng đọc/ghi được dữ liệu, số liệu, brain của bạn) - chỉ thêm ID người bạn tin tưởng. Cần tách bạch hoàn toàn cả dữ liệu thì dựng Javis + bot riêng cho mỗi người.

## Ai nhận thông báo nền

Dùng chung bot nhiều người thì phải biết mỗi loại thông báo rơi vào máy ai. Không phải cái gì cũng gửi cho tất cả.

| Loại thông báo | Gửi cho ai |
|---|---|
| Kết quả mỗi vòng loop ở [Việc định kỳ](08-viec-dinh-ky.md) chạy xong | ĐÚNG người yêu cầu loop, nếu ID đó nằm trong whitelist. Không rõ người yêu cầu (vd loop tạo trên bản web) thì gửi **ID đầu tiên** trong danh sách |
| Việc Kanban chạy xong, xem [Việc / Kanban](21-viec-kanban.md) | Giống trên: đúng người yêu cầu, không rõ thì ID đầu tiên |
| Nhắc hẹn tới giờ | Đúng chat_id đã đặt lịch. Nếu nhắc hẹn không gắn chat_id hoặc chat_id đó không còn trong whitelist thì gửi cho TẤT CẢ ID |
| Loop tự tạm dừng | TẤT CẢ ID trong whitelist |
| Đèn báo engine chết (bộ não không phản hồi) | TẤT CẢ ID trong whitelist, mỗi đợt chết chỉ báo một lần |
| Báo tin Zalo lọt luật, xem [Kênh Zalo](12-zalo.md) | Chủ theo cấu hình listener; không đặt thì ID đầu tiên |

Nói gọn: **kết quả công việc đi về đúng người đặt việc**, còn **cảnh báo hệ thống thì báo cho cả nhà**.

## Hội thoại Telegram nằm chung với lịch sử trên dashboard

Mọi lượt hỏi đáp qua Telegram đều được lưu giống hệt khi bạn chat trên dashboard: vào lịch sử hội thoại, vào nhật ký bộ nhớ của brain, và vào vòng tự học. Trong sidebar 🕘 Lịch sử, cuộc đến từ bot mang nhãn **TG** để bạn không lẫn với cuộc tự mở trên web. Xem thêm ở [Phiên hội thoại](04-phien-hoi-thoai.md).

Hội thoại được gắn theo **brain đang chọn cho phiên Telegram của bạn** (đổi bằng `/brain`), nên nó chỉ hiện khi dashboard đang xem đúng brain đó.

### Vì sao cuộc trò chuyện Telegram bị cắt thành nhiều khúc

Trên dashboard bạn tự bấm "＋ Hội thoại mới" nên một cuộc không bao giờ dài mãi. Trên Telegram thì gần như không ai gõ `/reset`, nên nếu để nguyên thì một Chat ID sẽ dính vào một cuộc dài vô tận, mở ra đọc rất nặng. Javis tự **sang cuộc mới** khi:

- bạn nghỉ không nhắn quá **12 tiếng**, hoặc
- cuộc hiện tại đã đủ dài (khoảng **100 lượt** hỏi đáp), hoặc
- bạn gõ `/reset`, đổi brain bằng `/brain`, hoặc máy chủ khởi động lại.

Điều quan trọng: việc cắt khúc này chỉ áp dụng cho **bản lưu để đọc lại**, hoàn toàn **không đụng tới trí nhớ của Javis trong lúc trò chuyện**. Bạn nhắn tiếp bình thường và Javis vẫn nhớ mạch như cũ; chỉ có bên dashboard là thấy lịch sử được chia thành từng khúc dễ đọc thay vì một cục dài.

Các khúc Telegram cũ hơn **30 ngày** được tự cất vào kho lưu để danh sách không bị ngập. Cất chứ không xoá: nội dung vẫn tìm được bằng ô tìm kiếm.

## Kiểm tra trạng thái bot

Có 2 cách:

1. Trên dashboard: vào **Kênh** (nhóm **Kết nối**), đọc dòng trạng thái dưới thẻ Telegram (mô tả ở Bước 2). Đây là cách nhanh nhất và dễ đọc nhất.
2. Trong Telegram: gõ `/status`. Bot trả về provider, model, brain đang dùng, phiên của bạn, và cho biết đang xử lý hay đang rảnh.

Nhóm **Hệ thống** ở đầu trang **Cài đặt** cũng hiện nhanh Telegram "Đang bật" hay "Đang tắt", kèm nút tắt sang thẳng trang **Kênh**; cấu hình chi tiết vẫn nằm ở **Kênh**.

## Bảng tra nhanh nút và trạng thái

| Nút / ô | Ở đâu | Tác dụng |
|---|---|---|
| Bật bot Telegram | Thẻ Telegram, trang Kênh | Bật/tắt bot. Phải bấm Lưu & bật mới có hiệu lực |
| Bot token | Thẻ Telegram | Token BotFather cấp. Đã đặt rồi thì để trống nếu không muốn đổi |
| Chat ID được phép dùng | Thẻ Telegram | Whitelist. Nhiều ID cách nhau dấu phẩy |
| Lưu & bật | Thẻ Telegram | Lưu cấu hình rồi tự khởi động lại bot ngay |
| Gửi test | Thẻ Telegram | Bắn một tin thử tới mọi ID trong whitelist. KHÔNG chứng minh bot đang nhận tin |

## Mẹo

- Đổi token hay Chat ID xong luôn bấm lại **Lưu & bật**; Javis tự khởi động lại bot theo cấu hình mới, không cần thao tác gì thêm.
- Câu trả lời quá dài Telegram tự cắt thành nhiều tin nhắn liên tiếp, đọc bình thường.
- Muốn hỏi một chủ đề mới hoàn toàn, không dính ngữ cảnh cũ, gõ `/reset` trước.
- Bot lỡ trả lời lan man hoặc bạn hỏi nhầm, gõ `/stop` để cắt, rồi `/retry` nếu muốn hỏi lại câu vừa rồi.
- Chộp ảnh hoá đơn, danh thiếp, bảng giá rồi gửi kèm caption `/notes ...` là cách nhanh nhất để nhét một thứ vào brain khi đang đứng ngoài cửa hàng.
- Trước khi gửi ảnh/file, kiểm tra `/brain` đang trỏ đúng brain bạn muốn: file rơi vào inbox của brain đó chứ không phải brain mặc định.
- Telegram không hiển thị được bảng markdown, nên Javis được dặn sẵn là trả lời qua kênh này thì viết ngắn kiểu tin nhắn, dùng đậm/nghiêng/`code` thay cho bảng.
- Trên VPS, bảo mật dashboard bằng mật khẩu ở trang [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md) song song với việc đặt Chat ID cho Telegram.

## Sự cố thường gặp

**Dòng trạng thái báo 🔴 409.** Cùng một bot token đang được chạy ở nơi khác (một bản Javis khác, một máy khác, hoặc còn webhook cũ). Một token chỉ được chạy ở đúng 1 nơi. Bot Javis tự xóa webhook khi khởi động; nếu vẫn 409 thì hãy tắt bản Javis kia hoặc tạo bot token mới bằng BotFather. Sau khi xử lý, bấm **Lưu & bật** lại.

**Bấm Gửi test báo thiếu token hoặc Chat ID.** Bạn chưa lưu đủ. Điền cả token và Chat ID, bấm **Lưu & bật** rồi mới Gửi test.

**Gửi test thành công nhưng nhắn cho bot không thấy trả lời.** Test và nhận tin là hai việc khác nhau. Kiểm tra dòng trạng thái có phải 🟢 **Bot đang nhận tin** không. Nếu đang ⚪ hoặc 🔴, xử lý theo dòng đó (bật lại, hoặc sửa lỗi 409).

**Nhắn cho bot bị trả lời "Bạn không có quyền dùng bot Javis này."** Chat ID bạn đặt trong Javis không khớp tài khoản đang nhắn. Lấy lại Chat ID đúng bằng @userinfobot, dán vào ô Chat ID rồi Lưu & bật.

**Tin "🤔 Javis đang xử lý…" đứng yên không đổi chữ.** Lượt đó chưa gọi công cụ nào nên chưa có gì để báo, hoặc engine đang chờ. Xong việc nó sẽ đổi thành dòng vết (`⚙ ...` hoặc `✓ Trả lời trực tiếp`). Nếu nó kẹt mãi ở "🤔" mà không có câu trả lời nào theo sau thì lượt đó đã hỏng, xem dòng trạng thái ở trang **Kênh**.

**Gõ `/tên-skill` bị báo cần engine Claude CLI.** Bạn đang ở engine OpenRouter. Gõ `/cli` để chuyển về Claude rồi gọi lại skill.

**Gửi file lên bot mà Javis nói không đọc được.** Kiểm tra 2 thứ: file có quá 20MB không (trần tải về của Telegram bot API), và có phải video/video note không (Javis chưa xem được hai loại này, hãy gửi dạng file tài liệu hoặc gõ chữ).

**Gửi tin thoại mà Javis nói cần API key Groq.** Đúng như vậy: phần nghe giọng chạy bằng Whisper của Groq. Vào trang **Models**, mục **Groq (API)**, dán key lấy ở console.groq.com rồi lưu. Không cần tắt bật lại bot.

**Javis nghe sai chữ.** Thu lại gần micro hơn, nói chậm và tránh chỗ ồn. Câu quá ngắn (một hai từ) cũng dễ nghe nhầm - nói trọn một câu thì chuẩn hơn hẳn. Với việc có tác động ra ngoài, Javis đọc lại câu nghe được rồi mới làm, nên bạn có cơ hội bắt lỗi trước.

**Javis nói đã tạo file nhưng bạn không nhận được.** Chỉ file vừa tạo/sửa trong chính lượt đó, dưới 50MB, tối đa 10 file mỗi lượt mới được tự đính kèm. File cũ thì bảo Javis gửi lại cụ thể tên file.

**Ảnh cũ trong hội thoại hiện ô xám "Ảnh đã hết hạn".** Vùng cache media (`attachments/` và `inbox/`) đã dọn file quá 30 ngày hoặc vượt trần 300MB. Nội dung đã rút thành ghi chú `.md` vẫn còn nguyên.

**Đổi cấu hình xong bot vẫn như cũ.** Chờ vài giây rồi tải lại trang **Kênh** để dòng trạng thái cập nhật. Nếu vẫn không lên 🟢, xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

## Mức tiết kiệm token áp dụng luôn cho Telegram

Từ **0.24.0**, mức bạn chọn ở trang Cài đặt (**Tối ưu** / **Siêu tiết kiệm**) có hiệu lực cho cả kênh Telegram, không riêng chat trên dashboard.

Trước đó cả hai mức chỉ được nối vào trang dashboard, nên bấm bật xong thì mỗi lượt Telegram vẫn gửi nguyên `CLAUDE.md` + `MEMORY.md`. Không có lỗi nào hiện ra - chỉ là hoá đơn token không giảm ở đúng kênh nhiều người dùng nhất.

Hai mức làm gì:

- **Tối ưu**: thay `CLAUDE.md` + `MEMORY.md` bằng phần ký ức và skill chọn lọc theo đúng câu bạn vừa hỏi.
- **Siêu tiết kiệm**: câu nào không cần tra cứu gì (ví dụ hỏi đáp thường, tính toán ngắn) thì gọi model **đúng một vòng** với một capsule nhỏ, không nạp bảng công cụ.

Câu cần tra cứu, cần gọi nguồn dữ liệu, hay có kèm file thì tự đi đường đầy đủ như cũ - đường tắt chỉ nhận những lượt nó chắc chắn trả lời được. Đường tắt hụt (token gói thuê bao hết hạn chẳng hạn) cũng tự lui về đường đầy đủ, bạn vẫn có câu trả lời.

Lệnh điều khiển lịch (`huỷ lịch...`) luôn do gateway lịch xử lý, đường tắt không cướp lượt đó.

## Liên quan

- [Models & engine](10-models-va-engine.md) - chọn provider và model cho cả dashboard lẫn bot.
- [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) - đấu nguồn dữ liệu để hỏi số liệu thật qua Telegram.
- [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md) và [Việc / Kanban](21-viec-kanban.md) - nơi sinh ra các báo cáo nền gửi về bot.
- [Kênh Zalo](12-zalo.md) - kênh còn lại, đọc và báo tin Zalo về chính bot Telegram này.
- [Quản lý tệp tin](05-quan-ly-tep-tin.md) - xem file bạn gửi lên nằm ở đâu trong brain.
- [Cấu hình .env](16-cau-hinh-env.md) - cấu hình nâng cao qua file môi trường.
