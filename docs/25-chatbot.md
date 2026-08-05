# Chatbot (Bot chuyên trách)

Đem một **Agent** bạn đã tạo ra đứng trước người ngoài: họ nhắn vào một bot Telegram riêng, Agent đó trả lời theo đúng quy định bạn viết cho nó, gặp câu ngoài tầm thì chuyển cho nhân viên thật.

Khác với [Kênh Telegram](11-telegram.md) ở một điểm quyết định: bot Telegram ở trang **Kênh** là **Javis của bạn** (toàn quyền, đọc brain chính, gọi được mọi nguồn dữ liệu, chỉ bạn nhắn được). Bot ở trang **Chatbot** là **một Agent đứng trực** (chỉ đọc, chỉ thấy brain của nó, người lạ nhắn được). Đừng dùng cái này thay cái kia.

## Tính năng này là gì

- Mỗi bot = một **Agent** trong một brain + một **token Telegram riêng**. Bot đọc tài liệu của chính brain đó.
- Trang Chatbot **thuộc về brain đang mở**: đổi brain ở đầu trang là thấy bot của brain đó, y như trang Agents và Skills.
- Người ta nhắn riêng cho bot, hoặc bạn thả bot vào nhóm.
- **Bot làm theo đúng file Agent của bạn.** Javis không chèn thêm luật nào của mình vào.
- Javis khoá đúng một thứ, và khoá bằng mã nguồn chứ không bằng câu dặn: **bot chỉ đọc được brain của chính nó**, không thấy brain khác, không ghi, không có lệnh quản trị.
- Câu ngoài tầm hiểu biết thì bot chuyển cho nhân viên bạn chỉ định.
- Trang Chatbot dựng theo hướng **nhiều bot** ngay từ đầu: lưới thẻ, ô tìm, thêm/sửa/xoá, bật/tắt tại chỗ. Chạy một con hay mười con đều cùng một giao diện.

## Mở ở đâu trong Javis

Thanh điều hướng bên trái, nhóm **Năng lực**, mục **Chatbot**.

## Chuẩn bị trước khi tạo bot

Ba thứ, làm theo thứ tự này là đỡ phải quay lại sửa.

### 1. Đứng đúng brain

Bot thuộc về **brain bạn đang mở**. Agent nó dùng và tài liệu nó đọc đều lấy từ brain đó, nên trước khi tạo bot hãy chuyển sang đúng brain bạn muốn giao cho nó.

**Bot chỉ biết những gì nằm trong brain này.** Đây là chỗ đáng cân nhắc nhất: nếu bot sẽ trả lời người lạ thì đừng tạo nó trong brain chính của bạn, vì trong đó có ghi chú nội bộ, giá vốn, chiến lược, và bot không phân biệt được cái nào nói ra được cái nào không.

Cách làm gọn: tạo một brain riêng cho việc trả lời khách (trang **Second Brain**), bỏ vào đó đúng những tài liệu khách được xem - bảng giá, chính sách đổi trả, mô tả sản phẩm, câu hỏi thường gặp - rồi chuyển sang brain đó và tạo bot.

### 2. Một Agent trong chính brain đó

Vào trang **Agents** tạo một Agent cho đúng việc bot sẽ làm (ví dụ "Tư vấn sản phẩm", "Hỗ trợ đơn hàng"). Viết phần vai trò và hướng dẫn như thể bạn đang dặn một nhân viên mới: nói năng thế nào, ưu tiên gì, gặp trường hợp nào thì chuyển người thật.

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
| Tên bot | Tên bạn nhìn để phân biệt, ví dụ "Tư vấn sản phẩm" |
| Agent làm bộ não | Chọn Agent trong brain đang mở, hoặc bấm **Tạo Agent** |
| Bot trả lời dựa trên gì | Xem mục hai chế độ ở dưới |
| Token Telegram | Dán token từ BotFather rồi bấm **Kiểm tra** |
| Chat ID nhân viên | Số Telegram của người nhận chuyển tiếp (xem bên dưới) |

**Không có ô chọn brain**, và đó là cố ý: bot thuộc về brain bạn đang mở. Muốn bot ở brain khác thì đổi brain ở đầu trang rồi tạo lại - một chỗ để nhìn, không có hai lớp phải khớp nhau.

Bấm **Kiểm tra** trước khi lưu: Javis hỏi thẳng Telegram xem token có thật không, trả về đúng tên bot, và báo ngay nếu token đó đã có bot khác trong Javis đang dùng.

**Bot tạo ra luôn ở trạng thái TẮT.** Đây là cố ý: bot chăm sóc khách bật lên là nói chuyện với người thật ngay lập tức, nên bật phải là một cú bấm có ý thức chứ không phải tác dụng phụ của việc tạo.

### Bước 2: Nhắn thử trước khi bật

Bật bot bằng nút **Bật** trên thẻ, rồi mở Telegram nhắn riêng cho chính con bot đó vài câu như một khách hàng thật. Hỏi giá, hỏi chính sách, hỏi một câu bạn biết chắc trong tài liệu không có. Xem nó trả lời có đúng giọng không, có bịa không, có chịu nói "em chưa có thông tin" không.

Thấy chưa ổn thì tắt đi, sửa Agent hoặc bổ sung tài liệu vào brain, rồi thử lại. Tắt có tác dụng ngay, không phải khởi động lại Javis.

### Bước 3: Chuyển cho nhân viên

Điền **Chat ID nhân viên** để bot có chỗ chuyển khi bí. Lấy số đó bằng cách nhờ nhân viên mở **@userinfobot** trên Telegram, nó trả về dòng `Id: 123456789`.

Nhân viên phải bấm **Start** trong chat với con bot này một lần, nếu không Telegram chặn không cho bot nhắn tới.

Khi đó bot có hai đường chuyển: tự gọi người khi **bí hai câu liên tiếp** với cùng một người, và khách chủ động gõ `/nhanvien` thì báo ngay. Cả hai đều gửi cho nhân viên một tin có tên bot, id khách và lý do. Lượt bot bị **lỗi kỹ thuật** cũng báo ngay từ lần đầu, nhưng chỉ một lần cho tới khi bot chạy lại được.

Bỏ trống ô này thì **bot vẫn trả lời bình thường** theo Agent, chỉ là không có ai để chuyển tiếp. Ai gõ `/nhanvien` sẽ được nói thật là chưa nối máy sang người trực được, và mời hỏi tiếp.

Muốn bot im khi không tìm thấy tài liệu thì đó là việc của chế độ **Chỉ tài liệu** ở mục trên, không phải của ô này.

### Bước 4: Thả bot vào nhóm chăm sóc khách hàng

1. Mời bot vào nhóm như mời một thành viên.
2. Trong nhóm, gõ `/id`. Bot trả về id của nhóm (một số **âm**, dạng `-1001234567890`).
3. Về trang Chatbot, bấm **Sửa** trên thẻ bot, dán id đó vào ô **Nhóm được phép**, mỗi id một dòng.

**Chưa khai id nhóm thì bot im lặng trong mọi nhóm.** Đây là mặc định cố ý: bot bị thả vào một nhóm lạ mà tự nhận việc là nó chen vào giữa cuộc nói chuyện của khách với nhau.

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

Trạng thái **Lỗi** phải nhìn thấy được, vì bot chết âm thầm là thứ chủ cửa hàng chỉ phát hiện khi khách phàn nàn.

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
| **Chỉ tài liệu** | Thêm một luật: nói chưa có thông tin, đừng dùng kiến thức chung | Bot đọc giá và chính sách, nơi một câu sai là thiệt hại thật |

Chọn sai thì thấy ngay: một Agent coach chạy ở chế độ "chỉ tài liệu" sẽ trả lời "em chưa có thông tin" cho đúng câu thuộc chuyên môn của nó, dù anh viết hướng dẫn vai rất kỹ. Đổi chế độ ở nút **Sửa**, có hiệu lực ngay.

### Javis KHÔNG viết luật cho bot

Đây là điều quan trọng nhất nên biết về trang này.

Bot chạy bằng **đúng nội dung file Agent** của anh, không hơn. Javis không chèn thêm luật nào lên trên: không dặn nó xưng hô thế nào, không cấm nó nói về chủ đề gì, không ép nó trả lời ngắn. Quy định anh viết trong Agent là quy định duy nhất bot có.

Ngoại lệ duy nhất là chế độ "chỉ tài liệu" ở trên, và đó là luật **anh chủ động bật**, không phải mặc định của Javis.

Nên **file Agent là thứ quyết định chất lượng bot, gần như hoàn toàn**. Viết như dặn một người mới vào làm: nói năng thế nào, phạm vi tới đâu, cái gì không được hứa, gặp trường hợp nào thì chuyển người thật. Bot cư xử sai thì sửa Agent, đừng tìm nút nào khác.

### Thứ duy nhất Javis khoá: bot chỉ thấy brain của chính nó

Rào duy nhất, và nó nằm trong mã nguồn chứ không nằm trong lời dặn, nên không lách được bằng lời lẽ:

- Bot **không đọc được brain khác**, kể cả brain chính của anh. Mọi đường đọc file đều bị kẹp trong đúng thư mục brain của bot; trèo ra bằng `../` hay đường dẫn tuyệt đối đều bị từ chối.
- Bot **không ghi** gì, không tạo đơn, không tiêu tiền, không đăng bài, không giao việc.
- Bot **không có lệnh quản trị**. `/brain`, `/model`, `/status` không có tác dụng.

Cách Javis bảo đảm điều này: **bot không được cấp công cụ nào cả.** Tài liệu được tra sẵn bằng Python trước khi model chạy rồi đưa vào đầu bài, nên bot vẫn đọc được brain của nó, chỉ là không đi lang thang trong đó được. Không có công cụ thì không có gì để lách.

### Đổi bộ não không đổi trải nghiệm

Bot chạy giống hệt nhau trên **cả tám bộ não**: Claude Code, ChatGPT, OpenRouter, OpenAI API, Anthropic API, Gemini, Groq, Ollama. Đổi model ở trang Models thì bot đổi theo, nhưng cách nó làm việc không đổi.

Làm được vì lượt của bot đi một đường riêng, chung cho mọi engine: cùng đầu bài từ Agent, cùng tài liệu tra sẵn, cùng lịch sử hội thoại, và không engine nào có công cụ. Khác biệt còn lại đúng bằng khác biệt giữa các model, không phải giữa các đường ống.

Đường này cũng không mở CLI, nên bot trả lời nhanh hơn đường chat của bạn và không dính trần 8 vòng gọi công cụ.

### Để tài liệu ăn khớp tốt

- **Đặt tiêu đề rõ ràng trong file.** Javis cắt tài liệu theo tiêu đề markdown (`##`), và mỗi đoạn được lấy riêng lẻ. Một file dài không tiêu đề thì bot có thể đọc được nửa điều kiện rồi trả lời như thể đó là toàn bộ điều kiện. Chia thành "Giá bán lẻ", "Giá sỉ", "Đổi trả", "Giao hàng"... là ăn khớp tốt nhất.
- **File khách gửi lên KHÔNG được tính là tài liệu.** Chúng nằm trong `inbox/khach/` và bị loại hẳn khỏi phần tra cứu. Nếu không thì bất kỳ ai cũng tải lên một file ghi "chính sách mới: hoàn tiền 100% mọi trường hợp" rồi hỏi lại một câu, và bot trích dẫn nó như tài liệu chính thức của cửa hàng.
- **File quy ước nội bộ của Javis cũng bị loại.** `CLAUDE.md`, `AGENTS.md`, `wiki/index.md`, `wiki/log.md` và mấy file điều hướng khác có mặt trong mọi brain nhưng là ruột hệ thống, không phải nội dung trả lời người ngoài. Note Wiki thật của anh vẫn dùng bình thường.
- **Gõ có dấu và không dấu đều tìm được**, nhưng gõ có dấu chính xác hơn: "bán" không khớp vào "bản", "cà" không khớp vào "cả". Tài liệu nên viết đúng chính tả và đúng dấu.

## Nhật ký và chỗ tài liệu đang thiếu

Bấm **Nhật ký** trên thẻ bot. Có hai tab, và tab mở sẵn là tab quan trọng hơn.

**Bot bí** liệt kê những câu bot trả lời không nổi, gom trùng và xếp theo **số lần khách hỏi**. Đây là thứ có giá trị kinh doanh trực tiếp: mỗi dòng chỉ đúng một chỗ tài liệu của anh đang thiếu, bằng chính lời khách hàng. Viết bổ sung vào brain là lần sau bot trả lời được.

Gom trùng có bỏ dấu, nên "Giá bao nhiêu?" và "gia bao nhieu" được tính là một câu. Nếu không thì cùng một câu hỏi bị tách thành mấy dòng lẻ và anh không thấy được nó thật ra được hỏi nhiều.

"Bí" đo bằng **chính câu bot vừa nói**: nó nói chưa có thông tin, hoặc nó phải chuyển người thật. Với bot chạy chế độ "chỉ tài liệu" thì không tìm ra tài liệu cũng tính luôn.

Đáng chú ý nhất là loại bí mà bot **vẫn tìm ra tài liệu**: tài liệu có nhưng thiếu đúng ý người ta cần. Loại đó chỉ ra chỗ tài liệu viết chưa đủ, tinh vi hơn loại không có file nào.

**Hội thoại gần đây** cho xem lại từng lượt, kèm **đúng file bot đã dùng** để trả lời. Dòng nguồn đó là thứ làm cho câu hỏi "bot trả lời đúng chưa" kiểm chứng được thay vì chỉ đoán.

### Khi nào nhân viên bị gọi

Có đặt Chat ID nhân viên thì bot gọi người trong hai trường hợp: khách gõ `/nhanvien`, hoặc bot **bí hai câu liên tiếp** với cùng một người. Trả lời được một câu là đếm về 0.

Bí một câu lẻ thì không gọi. Báo mọi câu vu vơ thì vài lần là nhân viên tắt thông báo, và lúc có người thật cần giúp thì không ai đọc nữa. Hai câu liên tiếp mới là dấu hiệu người ta đang mắc kẹt thật.

Nhật ký giữ 2000 lượt gần nhất mỗi bot, cũ hơn thì tự cắt. Xoá bot thì nhật ký đi theo.

## Bot làm được gì và KHÔNG làm được gì

**Làm được:** đọc tài liệu trong brain của nó, trả lời theo quy định trong file Agent, nhớ mạch hội thoại với từng người, chuyển cho nhân viên.

**Không làm được:** ghi file, tạo đơn, tiêu tiền, chạy quảng cáo, đăng bài, giao việc Kanban, tạo lịch, gọi các nguồn dữ liệu bạn đã đấu, đọc brain khác, dùng lệnh quản trị (`/brain`, `/model`, `/status`... đều không có tác dụng, bot chỉ trả lời chung chung).

Menu lệnh trong Telegram của bot khách chỉ có ba mục (`/help`, `/nhanvien`, `/id`), không phải menu quản trị của bot Javis chính. Liệt kê ở đó những lệnh bot từ chối chạy là dạy khách đi tìm một tập lệnh khác.

Còn **cách nó nói năng, phạm vi nó nhận trả lời, thứ nó từ chối** thì do file Agent của bạn quyết, không do Javis. Muốn bot không nói về giá, không hứa giao hàng, không đổi vai khi bị dụ thì viết những điều đó vào Agent.

Lưu ý cách hiểu đúng: những giới hạn trên nằm ở **mức quyền trong mã nguồn**, không phải ở câu dặn trong prompt. Câu dặn có thể bị lời lẽ khôn khéo lách qua; mức quyền thì không, vì công cụ đơn giản là không được cấp cho lượt chạy đó.

## Giới hạn tần suất

Mỗi khách bị giới hạn số lượt hỏi trong một giờ (mặc định 20, sửa được khi Sửa bot). Vượt thì bot lịch sự xin trả lời lại sau.

Cần thiết vì một người rảnh trong nhóm đủ đốt hết quota model của bạn trong một buổi chiều, và bạn chỉ biết khi nhìn hoá đơn.

## Xoá bot

Bấm **Xoá** trên thẻ. Bot ngừng trả lời ngay.

**Brain và Agent của nó KHÔNG bị xoá.** Brain có thể chứa cả tháng tài liệu bạn tự soạn, Agent có thể đang được bot khác hoặc workflow dùng. Muốn xoá thì xoá ở trang của chúng.

## Câu hỏi thường gặp

**Bot dùng model nào?** Chính model bạn chọn ở trang Models. Đổi model là bot đổi theo, và cách nó làm việc không đổi - mọi bộ não đi cùng một đường.

**Bot có gọi được POS, quảng cáo hay các nguồn dữ liệu tôi đã đấu không?** Không. Bot chỉ có tài liệu trong brain của nó. Muốn báo cáo số liệu thật thì hỏi Javis của bạn ở dashboard hoặc kênh Telegram riêng, đó mới là chỗ có đủ công cụ.

**Chạy nhiều bot cùng lúc được không?** Được. Mỗi bot một token, một tiến trình riêng. Trang Chatbot dựng sẵn cho việc đó.

**Hai bot dùng chung một Agent được không?** Được, và đôi khi hợp lý: cùng vai trò nhưng hai brain khác nhau cho hai cửa hàng. Ngược lại, hai bot dùng chung một token thì không, Javis chặn.

**Khách gửi ảnh cho bot thì sao?** File khách gửi rơi vào `inbox/khach/` trong brain của bot đó, tách riêng khỏi file của bạn, và không được tính là tài liệu để trả lời.

**Bot trả lời sai một câu, xem lại ở đâu?** Bấm Nhật ký, tab Hội thoại gần đây. Dòng nguồn dưới mỗi lượt cho biết nó lấy câu trả lời từ file nào, nên sửa đúng chỗ được ngay.

**Bot nói "chưa có thông tin" mà tài liệu rõ ràng có nói?** Thường là do file dài không chia tiêu đề, hoặc tài liệu dùng từ khác hẳn từ khách hỏi (tài liệu ghi "hoàn trả", khách hỏi "đổi trả"). Thêm tiêu đề cho file, hoặc viết thêm cách gọi mà khách hay dùng vào chính đoạn đó.

**Bot có nhớ khách không?** Có, mỗi khách một mạch hội thoại riêng trong brain của bot.

**Tắt Javis thì bot có chạy không?** Không. Bot chạy trong tiến trình Javis, nên máy/VPS phải bật. Bật lại Javis thì bot nào đang bật tự chạy lại.

## Xem thêm

- [Agents & Workflows](07-agents-va-workflows.md) - viết Agent làm bộ não cho bot.
- [Kênh Telegram](11-telegram.md) - bot Telegram cá nhân của bạn, khác hẳn bot ở đây.
- [Second Brain](13-second-brain-bo-nho-wiki.md) - tạo brain và nạp tài liệu cho bot đọc.
- [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md) - token được mã hoá thế nào.
