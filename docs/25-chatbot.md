# Chatbot (Bot chuyên trách)

Đem một **Agent** bạn đã tạo ra đứng trước người ngoài: họ nhắn vào một bot Telegram riêng, Agent đó trả lời theo đúng quy định bạn viết cho nó, gặp câu ngoài tầm thì chuyển cho người thật.

Dùng được cho bất cứ việc gì bạn phải trả lời đi trả lời lại cho người khác: hỏi đáp về một sản phẩm hay dịch vụ, giải đáp quy định nội bộ cho đồng nghiệp, trực câu hỏi của học viên, hướng dẫn thành viên trong một cộng đồng, sàng lọc câu hỏi trước khi tới tay bạn.

Khác với [Kênh Telegram](11-telegram.md) ở một điểm quyết định: bot Telegram ở trang **Kênh** là **Javis của bạn** (toàn quyền, đọc brain chính, gọi được mọi nguồn dữ liệu, chỉ bạn nhắn được). Bot ở trang **Chatbot** là **một Agent đứng trực** (mặc định chỉ đọc, chỉ thấy brain của nó, người lạ nhắn được). Đừng dùng cái này thay cái kia.

Bot chuyên trách **làm việc thật được** nếu bạn nâng mức quyền cho nó - ghi file, gọi nguồn dữ liệu, thậm chí thao tác ra ngoài. Nhưng người điều khiển nó là người nhắn cho nó chứ không phải bạn, nên đọc kỹ mục [Ba mức quyền](#ba-mức-quyền---bot-được-làm-gì) trước khi nâng.

## Tính năng này là gì

- Mỗi bot = một **Agent** trong một brain + một **token Telegram riêng**. Bot đọc tài liệu của chính brain đó.
- Trang Chatbot **thuộc về brain đang mở**: đổi brain ở đầu trang là thấy bot của brain đó, y như trang Agents và Skills.
- Người ta nhắn riêng cho bot, hoặc bạn thả bot vào nhóm.
- **Bot làm theo đúng file Agent của bạn.** Javis không chèn thêm luật nào của mình vào.
- **Ba mức quyền**, chọn khi tạo và đổi được sau: Chỉ đọc (mặc định), Được ghi, Toàn quyền. Nâng mức phải tick vào ô đồng ý sau khi đọc phần rủi ro.
- Hai rào **không đổi theo mức**, và khoá bằng mã nguồn chứ không bằng câu dặn: **bot chỉ thấy brain của chính nó**, và **không chạy được lệnh máy**.
- Câu ngoài tầm hiểu biết thì bot chuyển cho người trực bạn chỉ định.
- Trang Chatbot dựng theo hướng **nhiều bot** ngay từ đầu: lưới thẻ, ô tìm, thêm/sửa/xoá, bật/tắt tại chỗ. Chạy một con hay mười con đều cùng một giao diện.

## Mở ở đâu trong Javis

Thanh điều hướng bên trái, nhóm **Năng lực**, mục **Chatbot**.

## Chuẩn bị trước khi tạo bot

Ba thứ, làm theo thứ tự này là đỡ phải quay lại sửa.

### 1. Đứng đúng brain

Bot thuộc về **brain bạn đang mở**. Agent nó dùng và tài liệu nó đọc đều lấy từ brain đó, nên trước khi tạo bot hãy chuyển sang đúng brain bạn muốn giao cho nó.

**Bot chỉ biết những gì nằm trong brain này.** Đây là chỗ đáng cân nhắc nhất: nếu bot sẽ trả lời người lạ thì đừng tạo nó trong brain chính của bạn, vì trong đó có ghi chú nội bộ, số liệu riêng, dự định chưa công bố, và bot không phân biệt được cái nào nói ra được cái nào không.

Cách làm gọn: tạo một brain riêng cho việc trả lời người ngoài (trang **Second Brain**), bỏ vào đó đúng những tài liệu người ngoài được xem, rồi chuyển sang brain đó và tạo bot.

Nguyên tắc chọn tài liệu bỏ vào: **nếu một câu trong file này lọt ra ngoài mà bạn thấy phiền, thì file đó không thuộc về brain của bot.**

### 2. Một Agent trong chính brain đó

Vào trang **Agents** tạo một Agent cho đúng việc bot sẽ làm. Viết phần vai trò và hướng dẫn như thể bạn đang dặn một người mới nhận việc: nói năng thế nào, ưu tiên gì, gặp trường hợp nào thì chuyển người thật.

Đang ở trang Chatbot mà brain chưa có Agent nào thì bấm **Tạo Agent** để sang thẳng trang Agents, tạo xong quay lại.

Bot **đọc Agent lúc chạy**, không chép lại. Sau này sửa Agent ở trang Agents là bot đổi theo ngay, không phải sửa hai chỗ. Chi tiết cách viết Agent ở [Agents & Workflows](07-agents-va-workflows.md).

### 3. Một token Telegram riêng

Vào **@BotFather** trên Telegram gõ `/newbot`, đặt tên và username, lấy chuỗi token dạng `123456789:ABCdef...`.

**Mỗi bot phải một token riêng, và đừng dùng token bot Javis chính của bạn.** Một token chỉ chạy được một tiến trình; dùng chung là cả hai cùng chết và Telegram trả lỗi 409. Javis chặn sẵn việc này lúc bạn bấm Kiểm tra, nhưng biết trước vẫn hơn.

## Cách dùng (từng bước)

### Bước 1: Tạo bot

Bấm **Bot mới**, điền:

| Ô | Điền gì |
|---|---|
| Tên bot | Tên bạn nhìn để phân biệt các bot với nhau |
| Agent làm bộ não | Chọn Agent trong brain đang mở, hoặc bấm **Tạo Agent** |
| Bot trả lời dựa trên gì | Xem mục hai chế độ ở dưới |
| Bot được làm gì | Mức quyền. Cứ để **Chỉ đọc** cho lần đầu; xem mục [Ba mức quyền](#ba-mức-quyền---bot-được-làm-gì) trước khi nâng |
| Token Telegram | Dán token từ BotFather rồi bấm **Kiểm tra** |
| Chat ID người trực | Số Telegram của người nhận chuyển tiếp (xem bên dưới) |

**Không có ô chọn brain**, và đó là cố ý: bot thuộc về brain bạn đang mở. Muốn bot ở brain khác thì đổi brain ở đầu trang rồi tạo lại - một chỗ để nhìn, không có hai lớp phải khớp nhau.

Bấm **Kiểm tra** trước khi lưu: Javis hỏi thẳng Telegram xem token có thật không, trả về đúng tên bot, và báo ngay nếu token đó đã có bot khác trong Javis đang dùng.

**Bot tạo ra luôn ở trạng thái TẮT.** Đây là cố ý: bật lên là bot nói chuyện với người thật ngay lập tức, nên bật phải là một cú bấm có ý thức chứ không phải tác dụng phụ của việc tạo.

### Bước 2: Nhắn thử trước khi bật

Bật bot bằng nút **Bật** trên thẻ, rồi mở Telegram nhắn riêng cho chính con bot đó vài câu như một người ngoài thật. Hỏi vài câu thuộc phạm vi của nó, rồi hỏi một câu bạn biết chắc trong tài liệu không có. Xem nó trả lời có đúng giọng không, có bịa không, có chịu nói "em chưa có thông tin" không.

Thấy chưa ổn thì tắt đi, sửa Agent hoặc bổ sung tài liệu vào brain, rồi thử lại. Tắt có tác dụng ngay, không phải khởi động lại Javis.

### Bước 3: Chuyển cho người thật

Điền **Chat ID người trực** để bot có chỗ chuyển khi bí. Lấy số đó bằng cách nhờ người đó mở **@userinfobot** trên Telegram, nó trả về dòng `Id: 123456789`.

Người trực phải bấm **Start** trong chat với con bot này một lần, nếu không Telegram chặn không cho bot nhắn tới.

Khi đó bot có hai đường chuyển: tự gọi người khi **bí hai câu liên tiếp** với cùng một người, và người đang hỏi chủ động gõ `/nhanvien` thì báo ngay. Cả hai đều gửi cho người trực một tin có tên bot, id cuộc trò chuyện và lý do. Lượt bot bị **lỗi kỹ thuật** cũng báo ngay từ lần đầu, nhưng chỉ một lần cho tới khi bot chạy lại được.

Bỏ trống ô này thì **bot vẫn trả lời bình thường** theo Agent, chỉ là không có ai để chuyển tiếp. Ai gõ `/nhanvien` sẽ được nói thật là chưa nối máy sang người trực được, và mời hỏi tiếp.

Muốn bot im khi không tìm thấy tài liệu thì đó là việc của chế độ **Chỉ tài liệu** ở mục trên, không phải của ô này.

### Bước 4: Thả bot vào một nhóm

1. Mời bot vào nhóm như mời một thành viên.
2. Trong nhóm, gõ `/id`. Bot trả về id của nhóm (một số **âm**, dạng `-1001234567890`).
3. Về trang Chatbot, bấm **Sửa** trên thẻ bot, dán id đó vào ô **Nhóm được phép**, mỗi id một dòng.

**Chưa khai id nhóm thì bot im lặng trong mọi nhóm.** Đây là mặc định cố ý: bot bị thả vào một nhóm lạ mà tự nhận việc là nó chen vào giữa cuộc nói chuyện của người khác.

Trong nhóm đã khai, mặc định bot chỉ trả lời khi có người **nhắc tên nó** (gõ `@ten_bot`, hoặc bấm chọn tên nó từ danh sách thành viên) hoặc **reply vào tin của nó**. Nhóm có nhiều bot thì nó phân biệt được: nhắc tên bot khác hay reply vào bot khác thì nó không nhận vơ.

Muốn nó trả lời mọi câu trong nhóm thì đổi cách trả lời thành "luôn luôn" - cân nhắc kỹ, nhóm đông người thì rất ồn và đốt quota model nhanh.

## Đọc thẻ bot

Mỗi thẻ có một chấm màu và một dòng trạng thái. **Bốn** trạng thái chứ không phải hai:

| Chấm | Nghĩa |
|---|---|
| Xanh - Đang chạy | Bot đang nghe và trả lời bình thường |
| Vàng - Đang khởi động | Vừa bật, đang bắt tay với Telegram |
| Đỏ - Lỗi | Bot chết. Token bị thu hồi, mạng rớt, hoặc trùng token với nơi khác. Lý do hiện ngay dưới thẻ |
| Xám - Đã tắt | Bạn tắt nó |

Trạng thái **Lỗi** phải nhìn thấy được, vì bot chết âm thầm là thứ bạn chỉ phát hiện khi có người phàn nàn.

Thẻ cũng cảnh báo khi **Agent của bot không còn** (bạn xoá hoặc đổi slug ở trang Agents). Lúc đó bot vẫn chạy nhưng trả lời không có hướng dẫn vai trò, nên sửa ngay.

## Bot tốn bao nhiêu token

Bot **không đi qua** hai mức Tối ưu và Siêu tiết kiệm ở trang Mức dùng. Đó là cố ý, không phải thiếu sót: hai mức đó sinh ra để gọt bớt CLAUDE.md, MEMORY.md và bảng đặc tả công cụ - **ba thứ bot chưa bao giờ có**.

Đo trên một brain mẫu, phần cố định mỗi lượt:

| Đường | Token cố định |
|---|---|
| Chat dashboard, mức Đầy đủ | ~8.900 |
| Chat dashboard, mức Siêu tiết kiệm | ~460 |
| **Bot chuyên trách** | **~20** |

Phần còn lại của một lượt bot là tài liệu tra được - mà đó chính là câu trả lời, không phải phần thừa. Nói cách khác bot đã nhẹ hơn mức tiết kiệm sâu nhất, nên đẩy nó qua hai tầng kia chỉ làm nó **nặng thêm**.

Trên dòng dưới câu trả lời và ở bảng đo, lượt bot hiện là **"Bot chuyên trách"**. Trước 0.23.1 nó bị gộp vào "Đầy đủ" - đúng ngược sự thật, vì đây là đường rẻ nhất hệ thống.

Bot vẫn được tính vào **Mức dùng** như mọi lượt khác, theo đúng nhà cung cấp và model đang chạy.

## Bot trả lời dựa trên cái gì

Mỗi lần có người hỏi, Javis **tra tài liệu trong brain của bot trước**, lấy vài đoạn khớp nhất, rồi đưa thẳng vào đầu bài của lượt đó.

Điều này khác với "bot có quyền đọc brain". Có quyền đọc không có nghĩa là nó chịu đọc: model hoàn toàn có thể trả lời thẳng bằng kiến thức chung của nó, câu vẫn trôi chảy tự tin y hệt, và anh **không phân biệt được từ bên ngoài**. Nên Javis tra trước, không giao việc đó cho model tự quyết.

### Hai chế độ, chọn khi tạo bot

Khác biệt chỉ nằm ở **lúc không tìm thấy tài liệu nào khớp**. Tìm thấy thì hai chế độ hành xử y hệt.

| Chế độ | Không tìm thấy tài liệu thì bot làm gì | Hợp với |
|---|---|---|
| **Chuyên môn của Agent** (mặc định) | Javis không nói gì thêm; Agent tự xử theo quy định anh viết | Bot tư vấn, coach, đào tạo, giải đáp nghiệp vụ |
| **Chỉ tài liệu** | Thêm một luật: nói chưa có thông tin, đừng dùng kiến thức chung | Bot đọc con số và quy định, nơi một câu sai là thiệt hại thật |

Chọn sai thì thấy ngay: một Agent coach chạy ở chế độ "chỉ tài liệu" sẽ trả lời "em chưa có thông tin" cho đúng câu thuộc chuyên môn của nó, dù anh viết hướng dẫn vai rất kỹ. Đổi chế độ ở nút **Sửa**, có hiệu lực ngay.

### Javis KHÔNG viết luật cho bot

Đây là điều quan trọng nhất nên biết về trang này.

Bot chạy bằng **đúng nội dung file Agent** của anh, không hơn. Javis không chèn thêm luật nào lên trên: không dặn nó xưng hô thế nào, không cấm nó nói về chủ đề gì, không ép nó trả lời ngắn. Quy định anh viết trong Agent là quy định duy nhất bot có.

Ngoại lệ duy nhất là chế độ "chỉ tài liệu" ở trên, và đó là luật **anh chủ động bật**, không phải mặc định của Javis.

Nên **file Agent là thứ quyết định chất lượng bot, gần như hoàn toàn**. Viết như dặn một người mới vào làm: nói năng thế nào, phạm vi tới đâu, cái gì không được hứa, gặp trường hợp nào thì chuyển người thật. Bot cư xử sai thì sửa Agent, đừng tìm nút nào khác.

### Hai rào Javis khoá ở MỌI mức

Hai điều dưới đây đúng kể cả khi bạn cho bot toàn quyền. Chúng nằm trong mã nguồn chứ không nằm trong lời dặn, nên không lách được bằng lời lẽ:

- Bot **không thấy brain khác**, kể cả brain chính của bạn. Mọi đường đọc và ghi file đều bị kẹp trong đúng thư mục brain của bot; trèo ra bằng `../` hay đường dẫn tuyệt đối đều bị từ chối ngay.
- Bot **không chạy được lệnh máy**, không tự mở một trang web lạ ra đọc, không đẻ agent con. Bot cũng **không có lệnh quản trị**: `/brain`, `/model`, `/status` không có tác dụng.

Cách Javis bảo đảm: **bot không bao giờ chạm vào công cụ gốc của engine.** Ở mức Chỉ đọc nó không có công cụ nào; ở hai mức trên, mọi công cụ đều đi qua trung tâm kết nối của Javis, nơi đường dẫn file bị kẹp và mức quyền được áp ngay tại chỗ gọi. Bot không mở CLI, nên `Bash` và `Read` đường dẫn tuyệt đối của Claude Code không có mặt ở đây.

Còn tài liệu thì vẫn được tra sẵn bằng Python trước khi model chạy rồi đưa vào đầu bài, ở mọi mức. Bot đọc được brain của nó mà không cần công cụ nào.

## Ba mức quyền - bot được làm gì

Chọn ở ô **Bot được làm gì** khi tạo hoặc sửa bot. Mặc định là **Chỉ đọc**.

| Mức | Bot làm được | Hợp với |
|---|---|---|
| **Chỉ đọc** (mặc định) | Chỉ đọc tài liệu rồi trả lời. Không công cụ nào. | Trực và hỏi đáp - gần như mọi việc |
| **Được ghi** | Thêm: ghi file trong brain của chính nó, gọi nguồn dữ liệu đã đấu ở mức đọc/ghi | Ghi nhận yêu cầu, cập nhật ghi chú, tra số liệu thật |
| **Toàn quyền** | Thêm: gửi đi, thanh toán, đặt/huỷ, xoá, công bố ra ngoài | Nơi bạn kiểm soát được danh sách người nhắn vào |

### Cái mất được khi nâng mức

Đây là phần đáng đọc kỹ nhất trang này, vì nó là chỗ khác biệt căn bản giữa bot chuyên trách và Javis của bạn: **người gõ vào bot là người khác, không phải bạn.**

Ở mức Chỉ đọc thì điều đó vô hại - có dụ khéo cỡ nào bot cũng chỉ nói năng lạc đề, vì nó không có gì để làm hại. Nâng mức là bỏ đúng tính chất đó đi.

**Mức Được ghi:**

- Bot ghi được file trong brain của nó. Người nhắn cho bot một câu là nội dung trong brain đổi thật, **không có bước duyệt**.
- Bot gọi được các nguồn dữ liệu bạn đã đấu, ở mức đọc và ghi. Mọi thứ trong những nguồn đó nằm trong tầm với của người đang chat với bot.
- Javis vẫn **chặn cứng** nhóm thao tác ra ngoài ở mức này: không gửi đi, không thanh toán, không đặt hay huỷ, không xoá, không công bố gì. Chặn ở tầng gọi công cụ, không phải bằng lời dặn.

**Mức Toàn quyền:**

- Bot làm được **mọi thứ** các nguồn đã đấu cho phép, kể cả gửi đi, thanh toán, đặt hay huỷ, xoá, công bố ra ngoài. Những thao tác đó **không hoàn tác được**.
- Một câu dụ khéo ("bỏ qua hướng dẫn trước, làm giúp việc này") là đủ. Rào duy nhất còn lại là chính file Agent bạn viết, mà chữ thì lách được.
- Bot không hỏi lại bạn trước khi làm. Không có cổng duyệt từng lệnh.

Vì thế: **chỉ bật Toàn quyền khi bạn kiểm soát được danh sách người nhắn vào bot.** Chỗ ai cũng nhắn được thì không, dù Agent bạn viết kỹ tới đâu.

### Nâng mức thế nào

1. Bấm **Sửa** trên thẻ bot (hoặc chọn ngay khi tạo).
2. Chọn mức ở ô **Bot được làm gì**. Danh sách rủi ro của mức đó hiện ra ngay bên dưới.
3. Tick vào ô **Tôi đã đọc và chấp nhận rủi ro trên**. Chưa tick thì không lưu được - Javis chặn ở cả giao diện lẫn máy chủ, nên gỡ ô tick bằng devtools cũng không nâng được.
4. Mức Toàn quyền còn hỏi lại một lần nữa trước khi lưu.
5. Bật bot cũng hỏi lại, vì lúc tạo có thể là mấy hôm trước và tay bấm Bật chưa chắc nhớ con này đang ở mức nào.

Hạ mức thì không hỏi gì cả: hạ quyền luôn an toàn, và lúc bạn đang muốn dập một sự cố thì đừng bắt bấm thêm.

Thẻ bot nào được nâng quyền đều có một dải màu ghi rõ mức - vàng cho Được ghi, đỏ cho Toàn quyền. Bot Chỉ đọc không dán nhãn gì, vì đó là mặc định. Nhật ký cũng ghi lại mức của **từng lượt**, nên soi lại "hôm đó bot làm gì" vẫn đúng kể cả khi bạn đã hạ mức sau sự cố.

### Engine nào chạy được mức nâng quyền

Mức **Chỉ đọc** chạy giống hệt nhau trên cả tám bộ não, không có ngoại lệ.

Hai mức nâng quyền cần engine gọi được công cụ. Sáu engine API (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama) và gói Claude Code dùng đường đã chạy thật lâu nay. Riêng **gói ChatGPT** đi qua một đường của backend Codex mà nhà cung cấp chưa công bố ổn định, nên có thể không gọi được công cụ.

Gặp trường hợp đó thì **bot không chết**: nó trả lời lượt đó ở mức Chỉ đọc, và thẻ bot hiện một dải vàng nói rõ nó đang chạy thiếu quyền so với mức bạn đặt. Nâng quyền không bao giờ được phép lấy đi năng lực bot vốn đã có.

Thấy dải vàng đó thì chọn một trong hai: đổi engine ở trang **Models** nếu bạn thật sự cần bot làm việc, hoặc hạ mức bot xuống **Chỉ đọc** cho khỏi hiểu nhầm là nó đang làm.

### Đổi bộ não không đổi trải nghiệm

Bot chạy giống hệt nhau trên **cả tám bộ não**: Claude Code, ChatGPT, OpenRouter, OpenAI API, Anthropic API, Gemini, Groq, Ollama. Đổi model ở trang Models thì bot đổi theo, nhưng cách nó làm việc không đổi. Khi công cụ gọi được thì mọi engine cầm **đúng một bộ công cụ** - xem lưu ý ở mục trên về gói ChatGPT.

Làm được vì lượt của bot đi một đường riêng, chung cho mọi engine: cùng đầu bài từ Agent, cùng tài liệu tra sẵn, cùng lịch sử hội thoại, và công cụ (nếu có) lấy từ cùng một chỗ. Khác biệt còn lại đúng bằng khác biệt giữa các model, không phải giữa các đường ống.

Đường này cũng không mở CLI, nên bot trả lời nhanh hơn đường chat của bạn.

### Để tài liệu ăn khớp tốt

- **Đặt tiêu đề rõ ràng trong file.** Javis cắt tài liệu theo tiêu đề markdown (`##`), và mỗi đoạn được lấy riêng lẻ. Một file dài không tiêu đề thì bot có thể đọc được nửa điều kiện rồi trả lời như thể đó là toàn bộ điều kiện. Chia thành "Giá bán lẻ", "Giá sỉ", "Đổi trả", "Giao hàng"... là ăn khớp tốt nhất.
- **File người ngoài gửi lên KHÔNG được tính là tài liệu.** Chúng nằm trong `inbox/khach/` và bị loại hẳn khỏi phần tra cứu. Nếu không thì bất kỳ ai cũng tải lên một file ghi đè quy định của bạn rồi hỏi lại một câu, và bot trích dẫn nó như tài liệu chính thức.
- **File quy ước nội bộ của Javis cũng bị loại.** `CLAUDE.md`, `AGENTS.md`, `wiki/index.md`, `wiki/log.md` và mấy file điều hướng khác có mặt trong mọi brain nhưng là ruột hệ thống, không phải nội dung trả lời người ngoài. Note Wiki thật của anh vẫn dùng bình thường.
- **Gõ có dấu và không dấu đều tìm được**, nhưng gõ có dấu chính xác hơn: "bán" không khớp vào "bản", "cà" không khớp vào "cả". Tài liệu nên viết đúng chính tả và đúng dấu.

## Nhật ký và chỗ tài liệu đang thiếu

Bấm **Nhật ký** trên thẻ bot. Có hai tab, và tab mở sẵn là tab quan trọng hơn.

**Bot bí** liệt kê những câu bot trả lời không nổi, gom trùng và xếp theo **số lần được hỏi**. Đây là tab đáng giá nhất: mỗi dòng chỉ đúng một chỗ tài liệu của bạn đang thiếu, bằng chính lời người hỏi. Viết bổ sung vào brain là lần sau bot trả lời được.

Gom trùng có bỏ dấu, nên "Giá bao nhiêu?" và "gia bao nhieu" được tính là một câu. Nếu không thì cùng một câu hỏi bị tách thành mấy dòng lẻ và anh không thấy được nó thật ra được hỏi nhiều.

"Bí" đo bằng **chính câu bot vừa nói**: nó nói chưa có thông tin, hoặc nó phải chuyển người thật. Với bot chạy chế độ "chỉ tài liệu" thì không tìm ra tài liệu cũng tính luôn.

Đáng chú ý nhất là loại bí mà bot **vẫn tìm ra tài liệu**: tài liệu có nhưng thiếu đúng ý người ta cần. Loại đó chỉ ra chỗ tài liệu viết chưa đủ, tinh vi hơn loại không có file nào.

**Hội thoại gần đây** cho xem lại từng lượt, kèm **đúng file bot đã dùng** để trả lời. Dòng nguồn đó là thứ làm cho câu hỏi "bot trả lời đúng chưa" kiểm chứng được thay vì chỉ đoán.

### Khi nào người trực bị gọi

Có đặt Chat ID người trực thì bot gọi người trong hai trường hợp: người đang hỏi gõ `/nhanvien`, hoặc bot **bí hai câu liên tiếp** với cùng một người. Trả lời được một câu là đếm về 0.

Bí một câu lẻ thì không gọi. Báo mọi câu vu vơ thì vài lần là người trực tắt thông báo, và lúc có người thật cần giúp thì không ai đọc nữa. Hai câu liên tiếp mới là dấu hiệu người ta đang mắc kẹt thật.

Nhật ký giữ 2000 lượt gần nhất mỗi bot, cũ hơn thì tự cắt. Xoá bot thì nhật ký đi theo.

## Bot làm được gì và KHÔNG làm được gì

**Ở mọi mức, bot làm được:** đọc tài liệu trong brain của nó, trả lời theo quy định trong file Agent, nhớ mạch hội thoại với từng người, chuyển cho người trực.

**Ở mọi mức, bot KHÔNG làm được:** đọc hay ghi brain khác, chạy lệnh máy, tự mở trang web lạ, đẻ agent con, dùng lệnh quản trị (`/brain`, `/model`, `/status`... đều không có tác dụng, bot chỉ trả lời chung chung).

**Phần còn lại tuỳ mức quyền** bạn đặt - ghi file, gọi nguồn dữ liệu, thao tác ra ngoài. Xem bảng ở mục [Ba mức quyền](#ba-mức-quyền---bot-được-làm-gì). Mặc định là Chỉ đọc, tức không làm được thứ nào trong số đó.

Menu lệnh trong Telegram của bot chỉ có ba mục (`/help`, `/nhanvien`, `/id`), không phải menu quản trị của bot Javis chính. Liệt kê ở đó những lệnh bot từ chối chạy là dạy người ta đi tìm một tập lệnh khác.

Còn **cách nó nói năng, phạm vi nó nhận trả lời, thứ nó từ chối** thì do file Agent của bạn quyết, không do Javis. Muốn bot tránh một chủ đề, không hứa hẹn thay bạn, không đổi vai khi bị dụ thì viết những điều đó vào Agent.

Lưu ý cách hiểu đúng: những giới hạn trên nằm ở **mức quyền trong mã nguồn**, không phải ở câu dặn trong prompt. Câu dặn có thể bị lời lẽ khôn khéo lách qua; mức quyền thì không, vì công cụ đơn giản là không được cấp cho lượt chạy đó. Mặt trái của cùng một sự thật: khi bạn **cấp** công cụ cho lượt đó, câu dặn trong Agent cũng không giữ nổi nó nữa.

## Giới hạn tần suất

Mỗi người bị giới hạn số lượt hỏi trong một giờ (mặc định 20, sửa được khi Sửa bot). Vượt thì bot lịch sự xin trả lời lại sau.

Cần thiết vì một người rảnh trong nhóm đủ đốt hết quota model của bạn trong một buổi chiều, và bạn chỉ biết khi nhìn hoá đơn.

## Xoá bot

Bấm **Xoá** trên thẻ. Bot ngừng trả lời ngay.

**Brain và Agent của nó KHÔNG bị xoá.** Brain có thể chứa cả tháng tài liệu bạn tự soạn, Agent có thể đang được bot khác hoặc workflow dùng. Muốn xoá thì xoá ở trang của chúng.

## Câu hỏi thường gặp

**Bot dùng model nào?** Chính model bạn chọn ở trang Models. Đổi model là bot đổi theo, và cách nó làm việc không đổi - mọi bộ não đi cùng một đường.

**Bot có gọi được các nguồn dữ liệu tôi đã đấu không?** Mặc định là không - mức Chỉ đọc chỉ có tài liệu trong brain của nó. Nâng lên **Được ghi** thì có, và **Toàn quyền** thì có cả nhóm thao tác ra ngoài. Cân nhắc rằng người điều khiển là người nhắn cho bot; việc chỉ mình bạn cần thì hỏi Javis ở dashboard hoặc kênh Telegram riêng vẫn an toàn hơn.

**Bot ở mức Toàn quyền có nguy hiểm không?** Có, và đó là lý do Javis bắt tick đồng ý rồi hỏi lại thêm lần nữa. Nguy hiểm không nằm ở việc model làm bậy, mà ở chỗ **ai cũng nhắn cho bot được**: một câu dụ khéo là bot gọi công cụ thật, không hoàn tác được và không hỏi lại bạn. Chỉ dùng khi bạn kiểm soát được danh sách người nhắn vào.

**Đang chạy Toàn quyền mà thấy bất ổn thì làm gì ngay?** Bấm **Tắt** trên thẻ - có tác dụng trong vài giây, không cần khởi động lại Javis. Rồi bấm Sửa hạ mức xuống Chỉ đọc; hạ mức không hỏi lại gì cả. Xem bot đã làm gì ở **Nhật ký**, tab Hội thoại gần đây.

**Chạy nhiều bot cùng lúc được không?** Được. Mỗi bot một token, một tiến trình riêng. Trang Chatbot dựng sẵn cho việc đó.

**Hai bot dùng chung một Agent được không?** Được, và đôi khi hợp lý: cùng vai trò nhưng hai brain khác nhau cho hai nhóm người hỏi khác nhau. Ngược lại, hai bot dùng chung một token thì không, Javis chặn.

**Người ta gửi ảnh cho bot thì sao?** File gửi vào rơi xuống `inbox/khach/` trong brain của bot đó, tách riêng khỏi file của bạn, và không được tính là tài liệu để trả lời.

**Bot trả lời sai một câu, xem lại ở đâu?** Bấm Nhật ký, tab Hội thoại gần đây. Dòng nguồn dưới mỗi lượt cho biết nó lấy câu trả lời từ file nào, nên sửa đúng chỗ được ngay.

**Bot nói "chưa có thông tin" mà tài liệu rõ ràng có nói?** Thường là do file dài không chia tiêu đề, hoặc tài liệu dùng từ khác hẳn từ người ta hỏi (tài liệu ghi "hoàn trả", người hỏi gõ "đổi trả"). Thêm tiêu đề cho file, hoặc viết thêm cách gọi mà người ta hay dùng vào chính đoạn đó.

**Bot có nhớ người đã nhắn không?** Có, mỗi người một mạch hội thoại riêng trong brain của bot.

**Tắt Javis thì bot có chạy không?** Không. Bot chạy trong tiến trình Javis, nên máy/VPS phải bật. Bật lại Javis thì bot nào đang bật tự chạy lại.

## Xem thêm

- [Agents & Workflows](07-agents-va-workflows.md) - viết Agent làm bộ não cho bot.
- [Kênh Telegram](11-telegram.md) - bot Telegram cá nhân của bạn, khác hẳn bot ở đây.
- [Second Brain](13-second-brain-bo-nho-wiki.md) - tạo brain và nạp tài liệu cho bot đọc.
- [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md) - token được mã hoá thế nào.
