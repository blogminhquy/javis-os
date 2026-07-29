# Kênh Telegram

Bật bot Telegram để hỏi Javis ngay từ điện thoại, không cần mở dashboard. Bạn nhắn cho bot như nhắn cho một người, Javis trả lời bằng chính bộ não và bộ nhớ đang chạy trên máy/VPS của bạn.

## Tính năng này là gì

- Bạn tạo một bot Telegram riêng (miễn phí), dán token vào Javis, giới hạn chỉ tài khoản của bạn được dùng.
- Sau khi bật, mọi tin nhắn thường bạn gửi cho bot sẽ được Javis trả lời. Bot cũng gõ "đang soạn" trong lúc suy nghĩ.
- Có sẵn các lệnh gõ nhanh (bắt đầu bằng dấu `/`) để xem trạng thái, đổi model, dừng câu đang chạy, bắt đầu hội thoại mới.
- Nếu bạn dùng engine Claude (Claude Code) thì qua Telegram Javis vẫn có đủ MCP và skill: hỏi số liệu bán hàng, quảng cáo, đọc vault đều được. Nếu dùng engine OpenRouter thì chỉ là chat thuần, không có MCP.
- Trả lời chạy nền: đang trả lời câu này bạn vẫn gửi được `/stop` để cắt ngang.

Xem thêm engine và model ở [Models & engine](10-models-va-engine.md), công cụ MCP ở [MCP & số liệu kinh doanh](09-mcp-va-so-lieu.md).

## Mở ở đâu trong Javis

1. Mở dashboard Javis (mặc định `http://localhost:7777`).
2. Nhìn thanh điều hướng bên trái, bấm mục **Kênh**.
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

1. Vào **Kênh** trên dashboard, tới thẻ **Telegram**.
2. Tích ô **Bật bot Telegram**.
3. Dán chuỗi token vào ô **Bot token**. (Nếu trước đó đã đặt token, cạnh nhãn hiện chữ "đã đặt"; để trống ô này nếu không muốn đổi token.)
4. Dán Chat ID vào ô **Chat ID được phép dùng**. Nhiều người dùng chung thì dán nhiều ID cách nhau dấu phẩy, ví dụ `123456789, 987654321`.
5. Bấm **Lưu & bật**.

Javis lưu cấu hình và tự khởi động lại bot ngay sau khi bấm Lưu (bạn không cần bấm nút riêng để restart). Dòng trạng thái dưới thẻ sẽ báo "Đã lưu, đang khởi động bot…" rồi tự cập nhật sau gần 2 giây.

### Bước 2: Kiểm tra bot đã nhận tin

Dòng chữ nhỏ ngay dưới 2 nút là trạng thái thật của bot. Ý nghĩa từng dòng:

| Dòng trạng thái | Nghĩa |
|---|---|
| 🟢 Bot đang nhận tin | Bot chạy tốt, nhắn cho bot là Javis trả lời |
| ⚪ Bot CHƯA bật | Chưa tích "Bật bot Telegram" rồi Lưu |
| ⚪ Chưa có bot token | Đã bật nhưng chưa dán token |
| ⏳ Đang khởi động bot | Bot vừa được bật, chờ vài giây |
| 🔴 409 | Cùng token này đang bị chạy (poll) ở nơi khác, hoặc còn webhook. Xem mục Sự cố bên dưới |
| ⚠ Lỗi bot | Có lỗi khác, dòng sẽ kèm mô tả chi tiết |
| ⚪ Bot đã tắt | Bot đã dừng (chưa bật lại) |

Lưu ý quan trọng: gửi test thành công KHÔNG có nghĩa bot đang nhận tin. Test chỉ chứng minh token và Chat ID đúng. Muốn biết bot có nhận tin hay không, hãy xem dòng trạng thái phải là 🟢 **Bot đang nhận tin**.

### Bước 3: Gửi tin test (tùy chọn)

1. Bấm nút **Gửi test**.
2. Nếu token và Chat ID hợp lệ, Javis gửi vào chat Telegram của bạn một tin: "Javis Telegram đã kết nối. Nhắn câu hỏi bất kỳ nhé." Dòng trạng thái báo "Đã gửi tin test."
3. Nếu chưa lưu đủ token và Chat ID, nút test báo thiếu cấu hình. Hãy Lưu & bật trước rồi thử lại.

### Bước 4: Hỏi Javis qua Telegram

1. Mở chat với bot của bạn trên Telegram.
2. Gõ một câu hỏi bất kỳ như đang chat bình thường, vd "Hôm nay có task gì cần làm?" hoặc "Tóm tắt vault giúp tôi".
3. Bot hiện "đang soạn" rồi gửi câu trả lời. Câu trả lời dài sẽ được tự chia thành nhiều tin.
4. Trong lúc bot đang trả lời, nếu bạn gửi câu mới, bot báo "Đang xử lý câu trước. Gửi /stop để dừng rồi hỏi lại." Mỗi lúc chỉ chạy 1 lượt.

## Các lệnh gõ nhanh trong Telegram

Gõ dấu `/` trong chat (hoặc bấm nút Menu của bot) sẽ hiện danh sách lệnh. Các lệnh có sẵn:

| Lệnh | Tác dụng |
|---|---|
| `/help` | Xem hướng dẫn và danh sách lệnh |
| `/status` | Xem provider, model, vault đang dùng và bot có đang bận trả lời không |
| `/skills` | Liệt kê các skill có trong vault (gõ `/tên-skill` để gọi) |
| `/agents` | Liệt kê agent và cho biết có lượt nào đang chạy không |
| `/workflows` | Liệt kê workflow |
| `/model` | Xem hoặc đổi model. Gõ `/model` không kèm gì để mở bảng nút bấm chọn; hoặc gõ thẳng tên (vd `/model sonnet`) |
| `/brain` | Xem hoặc đổi brain (vault) cho RIÊNG phiên của bạn. Gõ `/brain` để mở bảng nút chọn; hoặc gõ thẳng tên (vd `/brain Kim Khí`). Đổi xong hội thoại reset để nạp đúng bộ nhớ brain mới; người khác và dashboard không bị ảnh hưởng. File bạn gửi lên cũng rơi vào inbox của brain đã chọn |
| `/retry` | Gửi lại câu hỏi gần nhất |
| `/stop` | Dừng ngay câu đang trả lời |
| `/reset` | Bắt đầu hội thoại mới (quên ngữ cảnh cũ) |
| `/cli` | Chuyển sang engine Claude (có đủ MCP và skill) |
| `/or` | Chuyển sang engine OpenRouter (chat thuần, không MCP) |

Chi tiết cách gõ `/model`:

- Bảng nút bấm khi gõ `/model`: chọn provider ĐÃ KẾT NỐI (Claude Code, ChatGPT, OpenRouter, Claude API, OpenAI API - provider đang dùng có dấu ✓ kèm số model), rồi tới lưới model 2 cột, 8 model một trang, nút ◀ ▶ lật trang. Danh sách model lấy TRỰC TIẾP từ provider (OpenRouter hiện đầy đủ vài trăm model, ChatGPT hiện model Codex), không phải danh sách cứng.
- Gõ thẳng tên cũng được: tên có dấu `/` (vd `openai/gpt-4o`) là model OpenRouter; `gpt-...` hoặc `...-codex` là model ChatGPT (cần đã kết nối OAuth); còn lại (vd `opus`, `sonnet`, `fable`) là model Claude.

## MCP và skill qua Telegram

- Khi engine là **Claude** (dùng `/cli` hoặc chọn provider Claude trong Models): qua Telegram Javis dùng được MCP và skill. Bạn có thể hỏi số liệu bán hàng, quảng cáo, đọc và ghi file trong vault, gọi skill bằng cú pháp `/tên-skill`.
- Khi engine là **OpenRouter** (dùng `/or`): chỉ chat thuần, không có MCP. Nếu bạn gõ một `/tên-skill` trong lúc đang ở OpenRouter, bot nhắc: "Skill cần engine Claude CLI. Gửi /cli để đổi, rồi /tên-skill lại."
- Đổi engine ngay trong Telegram: gõ `/cli` để về Claude, `/or` để sang OpenRouter. Đổi ở đây cũng đổi luôn cho toàn hệ Javis (dashboard và bot dùng chung một cấu hình model).
- Muốn dùng `/or` thì cần đã đặt OpenRouter key trong trang [Models & engine](10-models-va-engine.md); chưa có key bot sẽ nhắc.

## Giới hạn quyền: chỉ mình bạn dùng bot

- Ô **Chat ID được phép dùng** chính là whitelist. Chỉ các tài khoản Telegram có ID trong danh sách mới nhắn được với bot. Người lạ nhắn vào sẽ nhận: "Bạn không có quyền dùng bot Javis này."
- Nếu để trống ô Chat ID: bất kỳ ai tìm ra bot đều dùng được. Không nên để trống, vì bot có thể chạm vào vault và số liệu của bạn. Luôn đặt ít nhất 1 Chat ID.
- Cho thêm người dùng chung 1 bot: thêm Chat ID của họ vào ô, cách nhau dấu phẩy, rồi **Lưu & bật**. Nút **Gửi test** sẽ gửi tin thử tới TẤT CẢ ID và báo rõ ID nào lỗi (thường do người đó chưa bấm Start bot). Thông báo nền (vd loop tự tạm dừng) cũng gửi tới tất cả ID.
- Mỗi người có **mạch hội thoại riêng**: ngữ cảnh của từng Chat ID tách biệt, không lẫn sang người khác, và hai người có thể nhắn cùng lúc mà không phải chờ nhau. `/reset` và `/stop` chỉ tác động phiên của chính người gõ. Tuy vậy tất cả vẫn **chung một vault và cùng quyền** (ai cũng đọc/ghi được dữ liệu, số liệu, brain của bạn) - chỉ thêm ID người bạn tin tưởng. Cần tách bạch hoàn toàn cả dữ liệu thì dựng Javis + bot riêng cho mỗi người.

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

1. Trên dashboard: vào **Kênh**, đọc dòng trạng thái dưới thẻ Telegram (mô tả ở Bước 2). Đây là cách nhanh nhất và dễ đọc nhất.
2. Trong Telegram: gõ `/status`. Bot trả về provider, model, vault đang dùng, và cho biết đang bận trả lời hay đang rảnh.

Nhóm **Hệ thống** trong **Cài đặt** cũng hiện nhanh Telegram đang Bật hay Tắt; cấu hình chi tiết vẫn nằm ở **Kênh**.

## Mẹo

- Đổi token hay Chat ID xong luôn bấm lại **Lưu & bật**; Javis tự khởi động lại bot theo cấu hình mới, không cần thao tác gì thêm.
- Câu trả lời quá dài Telegram tự cắt thành nhiều tin nhắn liên tiếp, đọc bình thường.
- Muốn hỏi một chủ đề mới hoàn toàn, không dính ngữ cảnh cũ, gõ `/reset` trước.
- Bot lỡ trả lời lan man hoặc bạn hỏi nhầm, gõ `/stop` để cắt, rồi `/retry` nếu muốn hỏi lại câu vừa rồi.
- Trên VPS, bảo mật dashboard bằng mật khẩu ở trang [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md) song song với việc đặt Chat ID cho Telegram.

## Sự cố thường gặp

**Dòng trạng thái báo 🔴 409.** Cùng một bot token đang được chạy ở nơi khác (một bản Javis khác, một máy khác, hoặc còn webhook cũ). Một token chỉ được chạy ở đúng 1 nơi. Bot Javis tự xóa webhook khi khởi động; nếu vẫn 409 thì hãy tắt bản Javis kia hoặc tạo bot token mới bằng BotFather. Sau khi xử lý, bấm **Lưu & bật** lại.

**Bấm Gửi test báo thiếu token hoặc Chat ID.** Bạn chưa lưu đủ. Điền cả token và Chat ID, bấm **Lưu & bật** rồi mới Gửi test.

**Gửi test thành công nhưng nhắn cho bot không thấy trả lời.** Test và nhận tin là hai việc khác nhau. Kiểm tra dòng trạng thái có phải 🟢 **Bot đang nhận tin** không. Nếu đang ⚪ hoặc 🔴, xử lý theo dòng đó (bật lại, hoặc sửa lỗi 409).

**Nhắn cho bot bị trả lời "Bạn không có quyền dùng bot Javis này."** Chat ID bạn đặt trong Javis không khớp tài khoản đang nhắn. Lấy lại Chat ID đúng bằng @userinfobot, dán vào ô Chat ID rồi Lưu & bật.

**Gõ `/tên-skill` bị báo cần engine Claude CLI.** Bạn đang ở engine OpenRouter. Gõ `/cli` để chuyển về Claude rồi gọi lại skill.

**Đổi cấu hình xong bot vẫn như cũ.** Chờ vài giây rồi tải lại trang **Kênh** để dòng trạng thái cập nhật. Nếu vẫn không lên 🟢, xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

Xem cấu hình nâng cao qua file môi trường ở [Cấu hình .env](16-cau-hinh-env.md).
