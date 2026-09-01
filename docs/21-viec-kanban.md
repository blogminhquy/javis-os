# Việc (Kanban): giao goal cho AI chạy nền

Trang **Việc** là chỗ bạn giao một mục tiêu ("goal") rồi để Javis tự làm ở nền, không cần bạn ngồi canh khung chat. Bạn viết một câu mô tả việc cần xong, AI tự chuẩn hoá thành đặc tả, tự chọn loại worker, tự nhận việc và chạy; xong thì bắn kết quả về Telegram cho đúng người đã giao.

Điểm dễ hiểu nhầm nhất: đây **không phải bảng Trello kéo thả**. Bạn không kéo thẻ, không bấm chạy từng thẻ. Màn hình này để **quan sát hàng đợi và xử lý ngoại lệ**, phần chạy do dispatcher lo.

## Tính năng này là gì

Javis coi hàng đợi việc như một runtime cho AI. Một việc đi qua vòng đời sau:

1. **Bạn giao goal** (từ trang Việc, hoặc nói trong chat, hoặc do trang Tự học đề xuất).
2. **AI đặc tả (triage)**: một lượt chạy ngắn của model nền đọc goal thô rồi trả về JSON gồm intent rõ ràng, một **capability** (`files`, `research`, `mcp-read`, `code`, `external-write`), một **execution_mode** (`suggest`, `auto`, `full`) và danh sách **điều kiện hoàn thành**. Bước này không thực thi gì cả.
3. **Vào hàng đợi**: task chuyển sang trạng thái sẵn sàng, chờ tới lượt.
4. **Dispatcher claim task**: mỗi task được đúng một worker giữ (khoá bằng transaction trong SQLite), có thời hạn giữ 90 giây và nhịp báo sống 20 giây một lần.
5. **Worker chạy**: một tiến trình AI headless làm việc trong brain, tự kiểm tra kết quả rồi báo cáo ngắn.
6. **Kết thúc**: hoàn thành, hoặc dừng lại chờ bạn (thiếu thông tin, thiếu quyền, hoặc bạn đã tick "Yêu cầu duyệt kết quả").

Worker dùng chung **engine nền** với các tính năng chạy ngầm khác, nên Claude Code, ChatGPT/Codex và các provider API (OpenRouter, OpenAI, Anthropic, Google Gemini) đều chạy được hàng đợi này. Xem [Models & engine](10-models-va-engine.md).

Đừng nhầm ba thứ tên gần giống nhau:

| Thứ | Là gì | Đọc ở đâu |
| --- | --- | --- |
| **Việc** (trang này) | Hàng đợi việc làm MỘT LẦN, AI tự chạy nền | trang này |
| **Việc định kỳ** | Loop lặp theo chu kỳ và nhắc hẹn có mốc giờ | [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md) |
| Checkbox `- [ ]` trong note | Việc tự tay bạn tick trong file markdown | [Task & Dataview trong note](19-task-va-dataview.md) |

## Mở ở đâu trong Javis

Ở thanh điều hướng bên trái, mở nhóm **Việc** rồi bấm mục **Việc**. Tiêu đề trang là **Việc (Kanban)** với dòng phụ "AI tự đặc tả, điều phối và chạy task nền".

Bảng gắn với **brain đang chọn** ở đầu dashboard. Đổi brain là đổi luôn bảng việc, mỗi brain một hàng đợi riêng.

Ngay dưới tiêu đề có một chấm tròn và dòng chữ về dispatcher:

- "Dispatcher đang chạy · tối đa 2 worker" (chấm sáng): tiến trình điều phối của server đang sống.
- "Dispatcher chưa chạy" (chấm tối): tiến trình điều phối chưa lên.

Lưu ý quan trọng: dòng này chỉ nói tiến trình có sống hay không, **không** nói bảng của brain này có được tự chạy hay không. Cái quyết định chuyện đó là **Chế độ dispatcher** ở ngay bên dưới.

## Cách dùng (từng bước)

### Bước 1: Chọn chế độ dispatcher

Ở khối **Chế độ dispatcher** có 3 nút:

| Nút | Nghĩa thực tế |
| --- | --- |
| **Tắt** | Mặc định của một bảng mới. AI không tự nhận việc nào. |
| **Quan sát** | AI cũng không tự nhận việc. Bạn dùng khi muốn xếp việc vào hàng đợi trước rồi tự bấm chạy. |
| **AI tự vận hành** | Dispatcher tự quét hàng đợi và tự chạy việc. |

Chỉ **AI tự vận hành** mới khiến việc tự chạy. Hai chế độ còn lại đều làm dispatcher đứng yên với brain này, khác biệt nằm ở nút **Tạm dừng AI**: nút đó vừa đặt chế độ về **Tắt** vừa huỷ mọi worker đang chạy của brain hiện tại.

Đổi chế độ có hiệu lực ngay, không cần khởi động lại.

### Bước 2: Giao một goal

Bấm **+ Giao goal** ở góc phải để mở form (bấm lần nữa để đóng). Form có:

- **Goal**: một câu ngắn nói rõ việc cần xong. Ví dụ gợi ý ngay trong ô nhập: "Phân tích sản phẩm bán chạy tuần này và soạn 3 bài đăng". Bỏ trống là Javis báo "Nhập tiêu đề".
- **Ngữ cảnh và đầu ra mong muốn**: ô nhiều dòng, viết tự nhiên cũng được. Đây là chỗ bạn nói rõ đầu ra muốn nhận (file gì, đặt ở đâu, dài bao nhiêu, lấy số liệu từ nguồn nào). Bỏ trống thì Javis lấy luôn nội dung ô Goal.
- **Route**: chọn **AI tự chọn worker** (mặc định) để AI tự quyết, hoặc chọn một mục **Workflow: `<tên>`** để ép việc chạy qua đúng workflow đó. Danh sách workflow lấy từ brain đang chọn, xem [Agents & Workflows](07-agents-va-workflows.md).
- **Ưu tiên**: **🔺 Cao**, **🔼 Vừa** (mặc định), **🔽 Thấp**. Việc ưu tiên cao được nhận trước khi hàng đợi đông.
- **Ngoại lệ**: ô tích **Yêu cầu duyệt kết quả**. Tick thì làm xong việc không tự đóng mà dừng ở trạng thái "Cần duyệt ngoại lệ" chờ bạn xem.

Bấm **Giao cho AI** để tạo, hoặc **Huỷ** để đóng form.

Một mẹo nhỏ về chống trùng: nếu bảng đang còn một việc chưa kết thúc có tiêu đề trùng (so khớp sau khi bỏ dấu và bỏ ký tự đặc biệt), Javis trả về đúng việc cũ thay vì tạo bản sao.

### Bước 3: Đọc bảng

Hàng KPI có 4 số:

| KPI | Đếm cái gì |
| --- | --- |
| **Worker đang chạy** | Số worker đang thật sự chạy cho brain này |
| **Đang chờ** | Tổng việc đang chờ đặc tả, chờ phụ thuộc và chờ tới lượt |
| **Cần anh xử lý** | Việc bị chặn cộng việc chờ bạn duyệt |
| **Hoàn thành 24h** | Việc chuyển sang hoàn thành trong 24 giờ qua |

Bên dưới là 4 khung:

- **Đang hoạt động** (nhãn phụ "N worker"): việc đang chạy ngay lúc này.
- **Hàng đợi AI** (nhãn phụ "N task"): việc đang chờ đặc tả, chờ phụ thuộc hoặc chờ tới lượt.
- **Cần anh xử lý** (nhãn phụ "N ngoại lệ"): việc bị chặn và việc chờ duyệt. Khung rỗng hiện dòng "Không có ngoại lệ. AI đang tự vận hành bình thường."
- **Lịch sử gần đây** (nhãn phụ "24 giờ và mới nhất"): việc đã hoàn thành và đã huỷ, tối đa 20 thẻ.

Khung nào chưa có gì thì hiện "Chưa có task."

Mỗi thẻ việc gồm: biểu tượng ưu tiên và tiêu đề, viên trạng thái ở góc phải, dòng thông tin phụ (capability, "attempt 1/3", thời gian đổi gần nhất kiểu "vừa xong" / "12 phút" / "3 giờ"), rồi lý do bị chặn (chữ cam) hoặc 240 ký tự đầu của kết quả, cuối cùng là hàng nút thao tác.

Bảng tự làm tươi 3 giây một lần, nên bạn không cần bấm gì để thấy tiến độ.

### Bước 4: Mở chi tiết một việc

Bấm vào thân thẻ để mở ngăn chi tiết trượt ra từ cạnh màn hình. Trong đó có:

- Nội dung intent đầy đủ (bản đã được AI đặc tả, không phải câu thô ban đầu).
- Dòng thông tin: trạng thái, capability, "mode `<suggest|auto|full>`", "ưu tiên `<1|2|3>`".
- Hàng nút thao tác giống trên thẻ.
- **Lý do bị chặn** (nếu có).
- **Kết quả** đầy đủ (nếu có).
- **Lần chạy (N)**: từng lần worker cầm việc, kèm trạng thái lần chạy và thời điểm bắt đầu, có lỗi thì hiện lỗi.
- **Nhật ký lifecycle**: từng sự kiện của việc, ví dụ `created`, `claimed`, `specified`, `retry_scheduled`, `blocked`, `completed`, `operator_move`, `auto_archive`.

Đóng ngăn bằng nút **×** góc trên, phím **Esc**, hoặc bấm ra vùng nền tối.

### Bước 5: Xử lý ngoại lệ

Tuỳ trạng thái, thẻ (và ngăn chi tiết) hiện các nút:

| Nút | Hiện khi | Làm gì |
| --- | --- | --- |
| **✓ Duyệt ngoại lệ** | việc đang chờ duyệt | Chốt việc là hoàn thành |
| **↻ Thử lại** | việc bị chặn hoặc chờ duyệt | Đẩy việc về hàng đợi để chạy lại |
| **Dừng task** | việc đang chạy | Huỷ worker đang chạy |
| **Xóa khỏi bảng** | mọi việc không đang chạy | Đưa việc vào lưu trữ, rời khỏi bảng nhưng không mất lịch sử |

**Xóa khỏi bảng** hỏi xác nhận trước: "Xóa task này khỏi bảng? Task sẽ được lưu trữ để không mất lịch sử." Việc đang chạy phải **Dừng task** trước rồi mới xoá được. Nếu thao tác không thành, Javis hiện hộp báo lỗi nguyên văn từ server, hoặc "Không thể cập nhật task".

## Các trạng thái của một việc

Đây là bảng dịch nghĩa đầy đủ những chữ hiện trên viên trạng thái.

| Chữ hiện trên màn hình | Trạng thái trong máy | Nghĩa |
| --- | --- | --- |
| **AI đang đặc tả** | `triage` | Việc mới, đang chờ (hoặc đang được) AI chuẩn hoá thành đặc tả chạy được |
| **Chờ phụ thuộc** | `todo` | Việc có phụ thuộc, phải đợi các việc cha xong đã |
| **Trong hàng đợi** | `ready` | Đã có đặc tả, đang chờ tới lượt được worker nhận |
| **Đang chạy** | `running` | Một worker đang giữ và thực thi |
| **Cần duyệt ngoại lệ** | `review` | Đã làm xong nhưng bạn yêu cầu duyệt kết quả |
| **Cần xử lý** | `blocked` | Bị chặn: thiếu thông tin, thiếu quyền, hoặc lỗi đã hết lượt thử lại |
| **Hoàn thành** | `done` | Xong xuôi |
| **Đã huỷ** | `cancelled` | Bạn dừng, hoặc worker bị huỷ giữa chừng |
| (không hiện trên bảng) | `archived` | Đã lưu trữ: do bạn bấm Xóa khỏi bảng, hoặc do tự dọn sau 3 ngày kể từ khi kết thúc |

Vài đường đi đáng biết:

- Sau bước đặc tả, việc **không** bị tính là đã dùng một lượt thử; số lượt được trả lại để bước thực thi có đủ 3 lần.
- Lỗi tạm thời (timeout, rate limit, 429, mất mạng, engine bận) thì việc **tự** quay lại hàng đợi, tối đa 3 lượt, ghi sự kiện `retry_scheduled`. Hết lượt mới chuyển sang "Cần xử lý".
- Worker chết giữa chừng mà không kịp báo sống thì việc được thu hồi về hàng đợi với sự kiện `reclaimed`, không nằm treo mãi ở "Đang chạy".
- Worker tự thấy thiếu một quyết định hoặc dữ liệu thì trả kết quả bắt đầu bằng `[[NEEDS_INPUT]]`, việc chuyển sang "Cần xử lý" kèm đúng một dòng lý do.

## Bảng tra nhanh nút và trạng thái

| Nút trên đầu trang | Làm gì |
| --- | --- |
| **+ Giao goal** | Mở/đóng form giao việc |
| **Chạy nhịp ngay** | Ép dispatcher nhận và chạy ngay một việc sẵn sàng của brain này. Chạy được cả khi chế độ đang là Tắt hoặc Quan sát. Không có việc nào sẵn sàng thì không có gì xảy ra |
| **↻** | Tải lại bảng ngay, không đợi nhịp 3 giây |
| **Tạm dừng AI** | Đặt chế độ về **Tắt** và huỷ mọi worker đang chạy của brain này |

## Worker nền làm được gì và không làm được gì

Worker là một phiên AI **headless**: không có màn hình, không hỏi lại bạn giữa chừng, không có trình duyệt đã đăng nhập, không có tay bạn để bấm nút. Nó chỉ có bộ công cụ tương ứng với capability mà bước đặc tả đã chọn:

| Capability | Được dùng | Bị chặn |
| --- | --- | --- |
| `files` | Đọc/ghi/sắp xếp file trong brain | Bash, tìm kiếm web |
| `research` | Công cụ file cộng đọc web và tìm kiếm web | Bash |
| `mcp-read` | Công cụ file cộng đọc dữ liệu thật qua các kết nối MCP | Bash, tìm kiếm web |
| `code` | Công cụ file cộng Bash (sửa và kiểm thử code) | Đọc web, tìm kiếm web |
| `external-write` | Công cụ file cộng MCP, nhưng xem luật ngay bên dưới | Bash, tìm kiếm web |

Luật quan trọng nhất: việc thuộc `external-write` (gửi tin, đăng bài, tạo đơn, tạo lịch, đổi thứ gì đó bên ngoài) **chỉ chạy khi execution_mode là `full`**. Không đủ quyền thì việc bị chặn ngay với lý do "Task cần hành động ra ngoài. Chỉ worker mode=full mới được thực thi." Bước đặc tả cũng không tự cho quyền `full`: nó chỉ giữ `full` khi chính lời bạn viết trong goal nói rõ đã cho phép tự hành động (những cụm như "toàn quyền", "tự gửi", "tự đăng", "không cần hỏi"). Không thấy câu cho phép thì nó hạ xuống `auto` để kernel chặn lại.

Nói cách khác: mặc định Javis **không** tự tiêu tiền, không tự gửi tin, không tự đăng bài từ hàng đợi việc. Muốn thế thì phải nói thẳng trong goal.

Ngoài ra worker cũng không thấy repo mã nguồn nằm ngoài brain, và không làm được những việc cần chính chủ đăng nhập (cookie, OTP, quét mã QR, đổi mật khẩu).

## Nhận kết quả: về đúng nơi bạn đã giao việc

Mỗi việc kết thúc ở trạng thái hoàn thành, chờ duyệt hoặc bị chặn đều **tự bắn một tin báo** về đúng kênh đã giao nó, nội dung ngắn gọn kiểu:

- `✅ Việc '<tiêu đề>' đã hoàn thành.` kèm vài dòng đầu của kết quả.
- `✅ Việc '<tiêu đề>' đã làm xong, cần duyệt ngoại lệ.`
- `⚠ Việc '<tiêu đề>' bị chặn, cần anh xem.` kèm dòng `Lý do: ...`

Tin nào cũng kết bằng "Xem chi tiết ở trang Việc." vì chi tiết đầy đủ nằm ở đây chứ không nhồi vào tin nhắn.

Ai nhận tin, nhận ở đâu:

- **Giao trong chat trên dashboard** → kết quả hiện thẳng thành một tin của Javis **trong đúng cuộc trò chuyện đó**. Server ghi vào lịch sử phiên trước rồi mới đẩy lên, nên bạn đóng tab hay F5 xong mở lại vẫn thấy. Đang xem cuộc trò chuyện khác thì tin nằm sẵn ở phiên gốc và phiên đó nổi lên trong **Lịch sử**.
- **Giao từ chat Telegram** → báo về đúng người đã nhắn (việc mang theo chat id của họ).
- **Không rõ ai giao** (tạo tay ngoài chat) → báo về **ID Telegram đầu tiên** trong whitelist; chưa bật bot thì bước này bỏ qua, việc vẫn chạy bình thường. Xem [Kênh Telegram](11-telegram.md).

> Trước 0.9.289 chỉ có đường Telegram. Ai giao việc trên web mà chưa đấu Telegram thì giao xong là im lặng tuyệt đối - không trạng thái, không hồi âm. Giờ chat web là một kênh nhận báo thật, không cần Telegram nữa.

### Việc nào làm chuông kêu (từ 0.52.7)

Chuông **Thông báo** trên thanh trên chỉ nổi chấm đỏ (và chỉ đẩy thông báo ra ngoài trình duyệt) cho việc **cần bạn ra tay**:

| Việc kết thúc ở | Kết quả về khung chat | Vào hòm thư | Chấm đỏ + thông báo đẩy |
|---|---|---|---|
| Bị chặn | có | có | **có** |
| Chờ duyệt ngoại lệ | có | có | **có** |
| Chạy xong trót lọt | có | có | không |

Việc chạy xong vẫn nằm nguyên trong danh sách chuông để bạn mở ra xem lại, chỉ là nó không gọi bạn dậy: kết quả đã rơi thẳng vào đúng khung chat đã giao việc rồi. Đổi cách này vì chủ repo báo (01/09/2026) chuông kêu liên hồi giữa lúc đang trò chuyện.

Đánh đổi cần biết: lúc bạn đi vắng, một việc chạy xong sẽ **không** có gì nhắc. Muốn xem thì mở chuông, hoặc mở lại cuộc trò chuyện đã giao việc.

## Thấy việc nền đang chạy ngay trong khung chat

Từ 0.25.2, ngay trên ô nhập của khung chat có một **dải việc nền**. Nó chỉ hiện khi thật sự có gì đó đang sống, và nói đúng một điều: ngay lúc này có cái gì đang chạy cho bạn không.

| Màu | Nghĩa |
|---|---|
| **Xanh** | Có việc **đang chạy thật**. Chấm nhấp nháy. |
| **Vàng** | Việc **đã giao nhưng không tự chạy** vì chế độ dispatcher chưa phải **AI tự vận hành**. Dải nói luôn phải bật ở đâu. |
| **Xám** | Chỉ còn loop hoặc nhắc hẹn đang chờ tới giờ. |

Dải gom cả ba nguồn: việc Kanban, [loop và nhắc hẹn](08-viec-dinh-ky.md). Việc giao từ chính cuộc trò chuyện đang mở được viền riêng và đếm riêng ("2 việc đang chạy ngầm · 1 của hội thoại này"), vì "máy đang bận" với "việc của tôi đang chạy" là hai chuyện khác nhau. Bấm **Trang Việc** ở góc phải để mở bảng đầy đủ.

Dải tự hỏi lại server mỗi vài giây, và hỏi ngay mỗi khi một lượt chat kết thúc hoặc một việc nền vừa báo kết quả về. Không có việc nào thì nó ẩn hẳn, không chiếm chỗ của khung chat.

> Vì sao có: trước bản này khung chat không hiện một chữ nào về việc nền, nên "Javis đang chạy việc cho tôi" và "Javis quên mất rồi" trông y hệt nhau. Muốn biết phải tự nghĩ ra việc mở trang này, mà không ai có lý do để nghĩ ra.

## Javis tự đính chính khi lỡ hứa suông

Cũng từ 0.25.2, cuối mỗi lượt chat server dò xem câu trả lời có hẹn báo lại không ("có kết quả em báo ngay", "xong em báo anh", "anh chờ em chút"), rồi đối chiếu với việc nền đang có thật. Hứa mà không có gì chạy thì Javis tự dán một dòng đính chính ngay dưới câu trả lời, nói rõ là sẽ không có báo cáo nào tự về và bạn cần làm gì tiếp.

Đây không phải kiểm duyệt: nó không chặn và không sửa câu trả lời, chỉ nói thêm sự thật ở dưới. Lý do là một lượt trả lời kết thúc ngay khi Javis nói xong - không có cơ chế nào đánh thức nó dậy để làm nốt, nên một lời hẹn không kèm việc nền là một lời hẹn sẽ không bao giờ tới.

## Giao việc bằng lời trong chat

Bạn không bắt buộc phải mở trang này. Nói thẳng trong chat kiểu "giao việc nền: rà lại toàn bộ note trong Wiki tháng này rồi liệt kê note thiếu liên kết" là Javis tự tạo một việc trong hàng đợi và gắn danh tính người đang nói để báo kết quả về đúng chỗ.

Javis được dạy chọn công cụ nhỏ nhất đủ dùng, nên nó chỉ tạo việc khi việc đó **làm một lần, cần chạy nền hoặc cần duyệt**. Câu hỏi trả lời được ngay thì nó trả lời luôn; việc lặp theo chu kỳ hoặc có mốc giờ thì nó chuyển sang [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md).

Nhớ rằng việc tạo qua chat vẫn nằm trong hàng đợi của brain đang chat, và vẫn phải có chế độ **AI tự vận hành** thì mới tự chạy. Nếu bảng đang **Tắt**, việc chỉ nằm chờ cho tới khi bạn bật hoặc bấm **Chạy nhịp ngay**.

Từ 0.25.2 Javis **nói ra chuyện đó ngay lúc giao**: giao việc vào một bảng đang **Tắt** hoặc **Quan sát** thì nó báo lại là việc đang xếp hàng chứ chưa chạy, kèm cách bật. Trước đó nó luôn kết bằng "Việc chạy nền, kết quả tự về" bất kể chế độ nào - một lời hứa sai mà chính Javis không có cách nào biết là sai. Dải việc nền ở khung chat cũng chuyển sang màu vàng trong đúng tình huống này.

Việc này chạy trên **mọi bộ não** từ 0.17.1, qua tool `javis_task`. Trước đó chỉ Claude Code và ChatGPT/Codex giao được việc từ chat, vì đường duy nhất là gọi HTTP bằng lệnh máy mà chỉ hai engine đó chạy được. Các engine API (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama) nhận lời rồi không làm gì cả, và không báo lỗi. Nếu bạn từng gặp cảnh "bảo giao việc mà bảng vẫn trống", nhiều khả năng đó là lỗi này.

Hai điều tool đó **không** làm, cố ý:

- **Không tạo được việc mức `full`.** Mức full cho việc tự thao tác thật ra ngoài (tạo đơn, tiêu tiền, chạy quảng cáo, gửi tin) và không hoàn tác được. Javis tạo mức `suggest` hoặc `auto` thôi; muốn full thì bạn tự nâng ở trang này, nơi bạn nhìn thấy rõ mình đang cho phép gì.
- **Không chuyển cột, không huỷ việc, không duyệt việc đang chờ phê duyệt.** Những thao tác đó cần nhìn thấy bảng, nên chúng ở lại trang này.

## Việc do trang Tự học đề xuất

Trang **Tự học** có một công tắc năng lực tên **Việc (Kanban)** cho phép engine học tự đề xuất việc nền từ hội thoại. Công tắc này **mặc định tắt** ở bản hiện tại, sau khi soi một bảng thật và thấy phần lớn việc máy tự đẻ ra là thứ worker headless không thể làm (cần cookie, cần gửi tin ra ngoài, chỉ ngồi chờ người khác duyệt, đụng repo ngoài brain). Việc giờ chỉ sinh ra khi bạn bảo thẳng.

Nếu bạn tự bật lại, các rào sau vẫn giữ:

- Tối đa 3 việc mỗi lượt học, và chỉ lấy đề xuất có độ tự tin đủ cao.
- Đề xuất chứa secret hoặc chứa câu tiêm lệnh bị chặn thẳng.
- Cửa gác "việc bất khả thi" loại trước những việc cần đăng nhập/OTP/QR, việc gửi hay đăng ra ngoài, việc chỉ là ngồi chờ người khác trả lời, và việc đụng mã nguồn ngoài brain. Lý do bị loại được ghi vào nhật ký học.
- Việc do Tự học tạo vào thẳng tầng đặc tả như việc bạn tự giao, và **không** bị ép chờ duyệt: chỉ khi thiếu thông tin, thiếu quyền hoặc bạn bật cờ duyệt thì mới cần bạn can thiệp.

Chi tiết ở [Tự học](22-tu-hoc.md).

## Dữ liệu của bảng nằm ở đâu

- **Nguồn chính**: file `kanban.sqlite3` trong thư mục state của Javis (biến `JAVIS_STATE_DIR`, mặc định là thư mục `server/`). Đây là nơi giữ vòng đời, lần chạy và nhật ký sự kiện. Nó cố tình nằm ngoài brain để việc đang chạy không bị đồng bộ git ghi đè.
- **Bản sao đọc được**: `Javis/kanban.json` trong brain, được ghi lại mỗi lần bảng đổi. File này để sao lưu và để bản Javis cũ đọc được; sửa tay vào đó không đổi được gì trong hàng đợi thật.
- Bảng cũ từ những bản Javis trước được nhập vào đúng một lần, và việc còn kẹt ở trạng thái "đang chạy" của tiến trình cũ được đưa về hàng đợi.
- Việc hoàn thành hoặc đã huỷ quá **3 ngày** tự chuyển sang lưu trữ để bảng không phình ra.

## Giới hạn kỹ thuật

| Thông số | Giá trị |
| --- | --- |
| Số worker chạy song song | 2 (đổi bằng biến môi trường `JAVIS_KANBAN_MAX_WORKERS`, kẹp trong khoảng 1 tới 8, tính chung cho mọi brain) |
| Nhịp quét của dispatcher | 5 giây, và được đánh thức ngay khi có việc mới |
| Thời hạn giữ việc / nhịp báo sống | 90 giây / 20 giây |
| Trần thời gian bước đặc tả | 3 phút |
| Trần thời gian một lần chạy worker | 15 phút |
| Số lần thử lại tối đa | 3 |
| Độ dài kết quả lưu lại | 20.000 ký tự |
| Nhịp làm tươi màn hình | 3 giây |

## Gọi thẳng bằng API

Trang web không phủ hết những gì server làm được. Các endpoint dưới đây có thật, dùng khi bạn muốn tự động hoá hoặc muốn dọn bảng hàng loạt (mọi tham số đi dạng form, kèm `brain=<tên brain>`):

| Endpoint | Việc nó làm |
| --- | --- |
| `GET /kanban` | Toàn bộ dữ liệu bảng |
| `GET /kanban/health` | Chế độ, tình trạng dispatcher, số đếm theo trạng thái |
| `GET /kanban/task/show?id=...` | Một việc kèm lần chạy và nhật ký sự kiện |
| `POST /kanban/task` | Tạo việc. Ngoài các trường có trên form còn nhận `chat_id`, `capability`, `execution_mode`, `deps` (danh sách id cách nhau bằng dấu phẩy) và `idempotency_key` |
| `POST /kanban/run` | Chạy đúng một việc theo id |
| `POST /kanban/task/move` | Chuyển việc sang một trạng thái khác |
| `POST /kanban/purge` | Xoá hẳn việc đã kết thúc. Mặc định chỉ đụng việc đã lưu trữ và đã huỷ; thêm `include_done=1` mới đụng việc hoàn thành |
| `POST /kanban/clear` | Xoá trắng bảng, trừ việc đang chạy. Không hoàn tác được |

Hai endpoint dọn dẹp cuối bảng không có nút trên giao diện, đúng như thiết kế: chúng xoá thật.

## Mẹo

- Viết goal theo kiểu "đầu ra là gì", không phải "hãy suy nghĩ về". Ô **Ngữ cảnh và đầu ra mong muốn** càng nói rõ file đích, độ dài, nguồn số liệu thì bước đặc tả càng ra điều kiện hoàn thành sát, và worker càng ít đi lạc.
- Việc quan trọng thì tick **Yêu cầu duyệt kết quả**. Bạn mất một lần bấm nhưng chắc chắn được đọc kết quả trước khi coi là xong.
- Muốn thử một việc ngay mà chưa muốn bật chế độ tự chạy: để chế độ **Quan sát**, giao việc, rồi bấm **Chạy nhịp ngay**.
- Việc cần dữ liệu thật (doanh thu, lịch, quảng cáo) thì nói thẳng nguồn trong goal, ví dụ "lấy từ POS". Bước đặc tả sẽ chọn `mcp-read` và worker mới được mở các kết nối. Xem [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md).
- Bảng đầy việc chết vì thử nghiệm thì đừng xoá từng thẻ: bấm **Xóa khỏi bảng** cho vài thẻ quan trọng cần giữ lịch sử, còn lại cứ để tự lưu trữ sau 3 ngày.
- Đọc **Nhật ký lifecycle** trong ngăn chi tiết trước khi kết luận "AI làm sai". Rất nhiều lần câu trả lời nằm ở đó: việc bị thu hồi vì hết hạn giữ, hay bị hạ quyền vì thuộc nhóm hành động ra ngoài.

## Sự cố thường gặp

**Dòng trên đầu trang nói "Dispatcher đang chạy" nhưng không việc nào nhúc nhích.**
Đó là hai chuyện khác nhau. Dòng đó nói tiến trình điều phối của server đang sống; việc có được nhận hay không phụ thuộc **Chế độ dispatcher** của brain này. Đặt về **AI tự vận hành**.

**Bấm "Chạy nhịp ngay" mà không có gì xảy ra.**
Nghĩa là không có việc nào ở trạng thái sẵn sàng: hàng đợi rỗng, hoặc việc đang chờ phụ thuộc, hoặc đã đủ 2 worker chạy rồi. Nhìn KPI **Đang chờ** và **Worker đang chạy** để biết bạn đang ở trường hợp nào.

**Việc mãi ở "AI đang đặc tả".**
Bước đặc tả cần một lượt chạy model nền. Engine nền chưa sẵn sàng hoặc hết hạn mức thì việc quay lại hàng đợi và thử lại. Kiểm tra trang [Models & engine](10-models-va-engine.md) và trang [Mức dùng](23-muc-dung-token.md). Khi model nền không gọi được, Javis vẫn có nhánh dự phòng đoán capability theo từ khoá để hàng đợi không đứng hẳn.

**Việc bị chặn với lý do "Task cần hành động ra ngoài. Chỉ worker mode=full mới được thực thi."**
Đây là rào an toàn, không phải lỗi. Việc của bạn thuộc nhóm gửi tin, đăng bài, tạo đơn hoặc đổi thứ gì bên ngoài. Nếu bạn thật sự muốn nó tự làm, giao lại việc và viết rõ trong goal rằng bạn cho phép tự hành động; nếu không, hãy để Javis soạn nháp còn bạn tự bấm gửi.

**Việc bị chặn với lý do bắt đầu bằng "Worker cần thêm thông tin".**
Worker thấy thiếu một quyết định mà đoán bừa sẽ hại. Mở ngăn chi tiết đọc dòng lý do, bổ sung điều còn thiếu bằng cách giao lại một goal rõ hơn, rồi bấm **↻ Thử lại** hoặc xoá việc cũ đi.

**Không bấm được "Xóa khỏi bảng" hay "↻ Thử lại".**
Việc đang chạy không cho đổi trạng thái. Bấm **Dừng task** trước, đợi thẻ rời khỏi khung **Đang hoạt động**, rồi thao tác lại.

**Việc xong rồi mà không thấy báo ở đâu cả.**
Việc giao trong chat web phải mang theo mã phiên chat thì kết quả mới về đúng khung đó. Javis tự gắn khi bạn giao bằng lời trong chat; còn việc tạo tay ở trang này hoặc bằng lệnh curl không có mã phiên nên chỉ đi Telegram. Nếu tin đi Telegram mà im lặng: bot chưa bật, chưa có chat id trong whitelist, hoặc việc không rõ người giao nên tin bay về ID Telegram đầu tiên chứ không về tài khoản bạn nghĩ. Xem [Kênh Telegram](11-telegram.md).

**Javis hứa "em sẽ đợi các việc chạy xong rồi tổng hợp" nhưng chẳng bao giờ tổng hợp.**
Đó là lời hứa suông và đã bị cấm từ 0.9.289: lượt trả lời của Javis kết thúc ngay khi nó nói xong, không có cơ chế nào đánh thức nó dậy để tổng hợp. Việc nền chỉ tự đẩy kết quả **thô** về khung chat. Muốn có bản tổng hợp, giao thêm một việc chuyên đi tổng hợp (dùng `deps` trỏ vào các việc trước), hoặc nhắn lại một câu sau khi kết quả đã về.

**Bảng trống trơn dù hôm qua còn việc.**
Ba khả năng, theo thứ tự hay gặp: bạn đang đứng ở **brain khác** (đổi brain ở đầu dashboard), việc đã kết thúc quá 3 ngày nên tự lưu trữ, hoặc ai đó đã gọi endpoint dọn bảng.

**Việc nền chiếm hết hạn mức của bạn.**
Mỗi việc là một phiên AI thật. Hạ số worker song song bằng `JAVIS_KANBAN_MAX_WORKERS=1`, hoặc đặt chế độ về **Tắt** khi không cần. Theo dõi lượng tiêu thụ ở trang [Mức dùng](23-muc-dung-token.md), chỗ tách riêng "Javis tự chạy" với "Bạn gõ tay".

## Liên quan

- [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md) - việc lặp theo chu kỳ và nhắc hẹn có mốc giờ.
- [Tự học](22-tu-hoc.md) - engine học và công tắc đề xuất việc.
- [Agents & Workflows](07-agents-va-workflows.md) - workflow dùng cho ô Route.
- [Models & engine](10-models-va-engine.md) - engine nào đang chạy worker.
- [Kênh Telegram](11-telegram.md) - nơi nhận báo cáo việc.
- [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) - nguồn dữ liệu thật cho việc `mcp-read`.
- [Mức dùng: token & chi phí](23-muc-dung-token.md) - việc nền tiêu bao nhiêu.
- [Task & Dataview trong note](19-task-va-dataview.md) - checkbox việc trong file markdown, khác hẳn trang này.
- [Cấu hình .env](16-cau-hinh-env.md) - `JAVIS_STATE_DIR`, `JAVIS_KANBAN_MAX_WORKERS`.
