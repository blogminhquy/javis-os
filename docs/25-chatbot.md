# Chatbot (Bot chuyên trách)

***Tiếng Việt** · [English](en/25-chatbots.md)*

Đem một **Agent** bạn đã tạo ra đứng trước người ngoài: họ nhắn vào một bot riêng trên **Telegram** hoặc **Zalo**, Agent đó trả lời theo đúng quy định bạn viết cho nó, gặp câu ngoài tầm thì chuyển cho người thật.

Dùng được cho bất cứ việc gì bạn phải trả lời đi trả lời lại cho người khác: hỏi đáp về một sản phẩm hay dịch vụ, giải đáp quy định nội bộ cho đồng nghiệp, trực câu hỏi của học viên, hướng dẫn thành viên trong một cộng đồng, sàng lọc câu hỏi trước khi tới tay bạn.

Khác với [Kênh Telegram](11-telegram.md) ở một điểm quyết định: bot Telegram ở trang **Kênh** là **Javis của bạn** (toàn quyền, đọc brain chính, gọi được mọi nguồn dữ liệu, chỉ bạn nhắn được). Bot ở trang **Chatbot** là **một Agent đứng trực** (mặc định chỉ đọc, chỉ thấy brain của nó, người lạ nhắn được). Đừng dùng cái này thay cái kia.

Bot chuyên trách **làm việc thật được** nếu bạn nâng mức quyền cho nó - ghi file, gọi nguồn dữ liệu, thậm chí thao tác ra ngoài. Nhưng người điều khiển nó là người nhắn cho nó chứ không phải bạn, nên đọc kỹ mục [Bốn mức quyền](#bốn-mức-quyền---bot-được-làm-gì) trước khi nâng.

## Tính năng này là gì

- Mỗi bot = một **Agent** trong một brain + một **token riêng** trên Telegram hoặc Zalo. Bot đọc tài liệu của chính brain đó.
- **Chọn được kênh**: Telegram hoặc Zalo. Với khách hàng Việt Nam thì Zalo gần như luôn là lựa chọn đúng, vì họ đã có sẵn app trên máy. Xem [Chọn Telegram hay Zalo](#chọn-telegram-hay-zalo).
- Trang Chatbot **thuộc về brain đang mở**: đổi brain ở đầu trang là thấy bot của brain đó, y như trang Agents và Skills.
- Người ta nhắn riêng cho bot, hoặc bạn thả bot vào nhóm.
- **Bot làm theo đúng file Agent của bạn.** Javis không chèn thêm luật nào của mình vào.
- **Bốn mức quyền**, chọn khi tạo và đổi được sau: Chỉ đọc (mặc định), Đọc tài liệu, Được ghi, Toàn quyền. Hai mức đầu không ghi gì và không gọi nguồn nào; nâng lên hai mức sau phải tick vào ô đồng ý sau khi đọc phần rủi ro.
- Hai rào **không đổi theo mức**, và khoá bằng mã nguồn chứ không bằng câu dặn: **bot chỉ thấy brain của chính nó**, và **không chạy được lệnh máy**.
- Câu bot không trả lời nổi được ghi vào tab **Bot bí** để bạn bổ sung tài liệu, và bạn bấm **Tiếp quản** ở trang Hội thoại khi cần người thật vào cuộc.
- Trang Chatbot dựng theo hướng **nhiều bot** ngay từ đầu: lưới thẻ, ô tìm, thêm/sửa/xoá, bật/tắt tại chỗ. Chạy một con hay mười con đều cùng một giao diện.
- Mọi cuộc chat khách nhắn cho bot được lưu vào **hộp thư hội thoại** (trang **Hội thoại**): đọc lại, thấy cuộc nào bot bí, bấm Tiếp quản để tự trả lời khi cần. Xem [Hội thoại khách](28-hoi-thoai-khach.md).

## Mở ở đâu trong Javis

Thanh điều hướng bên trái, nhóm **Năng lực**, mục **Chatbot**, tab **Bot**. Trang chỉ có hai tab: **Hòm thư bot** và **Bot** (từ 0.65.9; trước đó là ba tab Hòm thư bot, Kênh của bot, Tạo chatbot, và người dùng phải nhảy qua lại giữa "thêm kênh" và "tạo bot"). Nói "mở chatbot" là tới thẳng tab Bot.

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

### 3. Một tài khoản kênh: token riêng, lấy đúng chỗ theo kênh

Từ 0.61.0 token là một **kênh** (tài khoản bot), bot chỉ **trỏ tới** nó. Bạn thêm kênh bằng nút **Thêm kênh** ở mục **Kênh chưa có bot** ngay dưới danh sách bot rồi tích chọn khi tạo bot, hoặc bấm **Kết nối kênh mới** ngay trong form Bot mới (kênh vừa nối được tick sẵn); hai đường cho cùng một kết quả. Một bot trực được **nhiều** tài khoản (một vai trả lời ở cả Telegram lẫn Zalo Bot), còn mỗi tài khoản chỉ **một** bot trực.

Nếu bot chạy trên **Telegram**: vào **@BotFather** gõ `/newbot`, đặt tên và username, lấy chuỗi token dạng `123456789:ABCdef...`.

Nếu bot chạy trên **Zalo**: mở app Zalo, tìm Official Account **Zalo Bot Manager**, chọn **Tạo bot**. Tên bot bắt buộc mở đầu bằng chữ "Bot" (ví dụ "Bot Kim Khí Hà Lộc"). Token được gửi về cho bạn bằng tin nhắn Zalo, dạng `123456789:abc-xyz`, và nó **không hết hạn** cho tới khi bạn tự đặt lại.

**Mỗi bot phải một token riêng, và đừng dùng token bot Javis chính của bạn.** Một token chỉ chạy được một tiến trình; dùng chung là cả hai cùng chết và máy chủ trả lỗi 409. Javis chặn sẵn việc này lúc bạn bấm Kiểm tra, nhưng biết trước vẫn hơn.

Dán nhầm token của kênh này vào kênh kia thì Javis nói thẳng ra chứ không để bạn ngồi đoán: nút **Kiểm tra** hỏi đúng nền tảng bạn vừa chọn.

## Chọn Telegram hay Zalo

Ô đầu tiên trong form tạo bot là chọn kênh, và nó đứng đầu vì nó quyết định mọi thứ phía dưới: token lấy ở đâu, bot có vào được nhóm không, có gửi được file không.

| | Telegram | Zalo |
|---|---|---|
| Khách Việt Nam có sẵn app | Ít khi | Gần như luôn có |
| Vào được nhóm | Có | **Không** ở gói bot cơ bản |
| Bot gửi ảnh cho khách | Có | Đang thử nghiệm |
| Bot gửi file tài liệu (PDF, bảng tính) | Có | **Chưa được** (Zalo chưa mở API) |
| Khách gửi ảnh cho bot đọc | Có | Có |
| Khách gửi file tài liệu cho bot đọc | Có | Chưa |
| Trần một tin nhắn | 4096 ký tự | 2000 ký tự |
| Bot hiện menu lệnh `/` | Có | Không, phải gõ tay |

Nói gọn: **bot nói chuyện với khách hàng Việt Nam thì chọn Zalo**, chấp nhận đổi lại là chỉ chat riêng và chưa gửi được tài liệu. **Bot dùng trong nhóm nội bộ, hoặc cần đưa file qua lại thì chọn Telegram.**

**Kênh không đổi được sau khi tạo bot.** Đổi kênh nghĩa là đổi sang một con bot khác hẳn: token khác, danh tính khác, khách khác, và mọi id nhóm đang lưu lập tức vô nghĩa. Cần kênh khác thì tạo bot mới; form Sửa sẽ hiện kênh ở dạng khoá kèm đúng câu này.

Trên lưới thẻ, mỗi bot mang **dấu hiệu kênh** ở hai chỗ: một huy hiệu nhỏ đè lên góc icon (để liếc qua là biết), và một chip có logo trong phần thông tin (để đọc lướt). Khi bạn có bot ở cả hai kênh, đầu trang tự hiện thêm hàng nút lọc **Tất cả / Telegram / Zalo**.

### Zalo Bot khác gì Zalo Agent MCP

Javis có hai đường vào Zalo, và chúng không thay thế nhau:

- **Zalo Bot** (trang này) là một **danh tính riêng**, dùng API chính thức. Không có rủi ro khoá tài khoản, nhưng nó chỉ thấy được thứ người ta nhắn thẳng cho nó.
- **[Zalo Agent MCP](12-zalo.md)** đăng nhập **chính tài khoản Zalo của bạn** qua API không chính thức. Đọc được hội thoại thật, nhắn cho bất kỳ ai, đổi lại tài khoản có thể bị hạn chế hoặc khoá.

Cái đầu để **người khác nói chuyện với Javis**. Cái sau để **Javis thao tác thay bạn**. Dùng cả hai cũng được.

## Cách dùng (từng bước)

### Bước 1: Tạo bot

Bấm **Bot mới**. Từ 0.64.85 form có **bốn phần**, mỗi phần một quyết định, và những ô ít khi đụng tới nằm trong mục **Nâng cao** đã gập sẵn:

| Phần | Điền gì |
|---|---|
| **Bot là ai** | Tích một hay nhiều tài khoản kênh (chỉ hiện tài khoản của brain này mà chưa bot nào trực), đặt tên bot, chọn Agent làm bộ não hoặc bấm **Tạo Agent**. Kênh đang do bot khác trực hiện **mờ kèm ổ khoá**, ghi rõ bot nào (và brain nào nếu khác brain đang mở) đang giữ. Chưa có kênh thì bấm **Kết nối kênh mới**: chọn loại kênh, dán token, Kiểm tra. Xem [Chọn Telegram hay Zalo](#chọn-telegram-hay-zalo) |
| **Bot trả lời ai** | Bốn thẻ chọn một, xem mục [Bot trả lời ai](#bot-trả-lời-ai) ngay dưới. Chọn nhóm hay người thì tick trong danh sách, không phải gõ id. Kèm nút chọn **khi nào bot lên tiếng trong nhóm**: Được gọi tên (mặc định), Tự đánh giá, hoặc Mọi tin (thẻ Tự động hóa tất cả đã quyết sẵn nên ẩn nút này) |
| **Bot dựa vào đâu để trả lời** | Agent và tài liệu, hoặc Chỉ tài liệu. Xem mục hai chế độ ở dưới |
| **Bot được làm gì** | Mức quyền. Cứ để **Chỉ đọc** cho lần đầu; xem mục [Bốn mức quyền](#bốn-mức-quyền---bot-được-làm-gì) trước khi nâng |
| Nâng cao | Ngôn ngữ trả lời |

Chỉ có tài khoản Zalo Bot thì phần chọn nhóm **biến mất** thay vì hiện ra rồi vô tác dụng: gói bot cơ bản của Zalo không cho bot vào nhóm, nên chọn nhóm ở đó chỉ là một lời hứa suông nằm lại trong dữ liệu.

#### Bot trả lời ai

Đây là quyết định quan trọng nhất của form, nên nó là bốn thẻ nằm cạnh nhau để so sánh:

| Thẻ | Bot làm gì |
|---|---|
| **Tự động hóa tất cả** (từ 0.65.2) | Như thẻ ngay dưới, nhưng trong nhóm bot **tự quyết nói hay im** (chế độ Tự đánh giá của [Bộ phán xử](#bộ-phán-xử-bot-tự-quyết-nói-hay-im-và-học-từ-nhóm)) và tự học dần. Một cú chọn thay cho hai cài đặt. Lưu xuống vẫn là "mọi cuộc chat" cộng "Tự đánh giá", nên bot cài như vậy từ trước tự hiện đúng thẻ này. Cùng ô xác nhận với thẻ dưới, kèm câu nói bot ghi lại chữ chat của nhóm để học |
| **Mọi cuộc chat trên kênh** | Trả lời nhắn riêng và mọi nhóm bot có mặt; trong nhóm chọn được Được gọi tên hoặc Mọi tin. Phải tick ô xác nhận, vì nếu đây là tài khoản Zalo cá nhân thì bạn bè và người nhà cũng được trả lời |
| **Ai nhắn riêng cũng được, nhóm thì tôi chọn** | **Mặc định.** Nhắn riêng thì ai cũng được, nhóm nào chưa tick thì bot im |
| **Chỉ người và nhóm tôi chọn** | Bot im với mọi cuộc chat khác. Người và nhóm chưa tick nằm ở hàng chờ trên thẻ bot, bấm **Cho phép** là xong |

Chỉ có kênh nhắn riêng (Zalo Bot) thì hai thẻ đầu ẩn đi (không có nhóm nào để bot tự quyết), và hai thẻ còn lại đổi nhãn thành "Ai nhắn cũng được" và "Chỉ người tôi chọn". Bấm thẻ cuối là hiện **ô chọn người và nhóm**: hai tab Nhóm / Người có số đếm, ô tìm theo tên, danh sách các cuộc chat đã nhắn tới tài khoản, và ô **Thêm bằng id** cho cuộc chat chưa từng nhắn. Cuộc chat đang chờ bạn cho phép được xếp lên đầu và có nhãn.

Các thẻ không thay đổi việc bot phải được gọi tên trong nhóm: nhóm đã chọn vẫn theo nút "khi nào bot lên tiếng". Thẻ chỉ quyết định **bot có được phép đứng ở cuộc chat đó hay không**.

**Không có ô chọn brain**, và đó là cố ý: bot thuộc về brain bạn đang mở. Muốn bot ở brain khác thì đổi brain ở đầu trang rồi tạo lại - một chỗ để nhìn, không có hai lớp phải khớp nhau.

Dán token mới thì bấm **Kiểm tra** trước khi lưu: Javis hỏi thẳng nền tảng bạn vừa chọn xem token có thật không, trả về đúng tên bot, và báo ngay nếu token đó đã là một tài khoản trong Javis (đang rảnh thì chỉ bạn tích tài khoản đó, đang có bot trực thì nói tên bot). Với Zalo Bot, nếu gói của bạn không cho bot vào nhóm thì nó nói luôn tại đây.

**Bot tạo ra luôn ở trạng thái TẮT.** Đây là cố ý: bật lên là bot nói chuyện với người thật ngay lập tức, nên bật phải là một cú bấm có ý thức chứ không phải tác dụng phụ của việc tạo.

### Bước 2: Nhắn thử trước khi bật

Bật bot bằng nút **Bật** trên thẻ, rồi mở Telegram nhắn riêng cho chính con bot đó vài câu như một người ngoài thật. Hỏi vài câu thuộc phạm vi của nó, rồi hỏi một câu bạn biết chắc trong tài liệu không có. Xem nó trả lời có đúng giọng không, có bịa không, có chịu nói "em chưa có thông tin" không.

Thấy chưa ổn thì tắt đi, sửa Agent hoặc bổ sung tài liệu vào brain, rồi thử lại. Tắt có tác dụng ngay, không phải khởi động lại Javis.

### Bước 3: Khi bot bí, người thật vào cuộc

Từ 0.64.83 form **không còn ô Chat ID người trực** (đó là số Telegram, không dùng được cho bot Zalo). Bot mới không tự nhắn cho ai khi bí.

Bot bí thì vẫn trả lời theo Agent, hoặc nói chưa có thông tin nếu bạn chọn chế độ **Chỉ tài liệu**. Câu nó không trả lời nổi ghi vào tab **Bot bí** để bạn bổ sung tài liệu. Muốn tự trả lời một cuộc chat thì bấm **Tiếp quản** ở trang **Hội thoại**, bot sẽ im ở cuộc đó. Ai gõ `/nhanvien` được nói thật là chưa nối máy sang người trực được, và mời hỏi tiếp.

Bot đã đặt người trực từ trước 0.64.83 thì **giữ nguyên** (thẻ bot ghi "có chuyển người trực") và chạy như mô tả ở mục [Khi nào người trực bị gọi](#khi-nào-người-trực-bị-gọi).

### Bước 4: Thả bot vào một nhóm

1. Mời bot vào nhóm như mời một thành viên.
2. Trong nhóm, gõ **`/id`**. Bot trả về id nhóm **và nói luôn tình trạng**: nhóm này đã được bật chưa, chế độ riêng tư của Telegram đang bật hay tắt, và phải làm gì tiếp.
3. Nhóm đó **hiện lên thẻ bot** ở trang Chatbot. Bấm **Cho phép nhóm này**. Xong.

Dùng `/id` chứ không phải gọi tên bot, và đó là chủ ý: **lệnh `/...` luôn tới được bot** dù Telegram đang bật chế độ riêng tư, còn tin nhắc tên thì chưa chắc (xem mục dưới). Nếu bước 2 mà bot **không trả lời gì cả** thì vấn đề không nằm ở nhóm - hoặc bot đang tắt, hoặc token hỏng; xem chấm trạng thái trên thẻ.

Khai tay cũng được: lấy id ở bước 2 (một số **âm**, dạng `-1001234567890`) rồi dán vào ô **Thêm bằng id** trong phần **Bot trả lời ai** của form tạo hoặc sửa bot.

**Chưa cho phép nhóm thì bot không trả lời trong nhóm đó** (trừ khi bạn chọn thẻ "Mọi cuộc chat trên kênh" ở phần Bot trả lời ai). Đây là mặc định cố ý: bot bị thả vào một nhóm lạ mà tự nhận việc là nó chen vào giữa cuộc nói chuyện của người khác. Nhưng từ chối không có nghĩa là biến mất - bot nói một câu cho người đang gọi biết phải làm gì, và nhóm đó nằm chờ ngay trên thẻ để bạn quyết.

Nhóm nào bạn không muốn thì bấm **Bỏ qua**, nó rời khỏi danh sách chờ. Có người gọi bot ở đó lần nữa thì nó quay lại - trang này không giấu đi một chỗ có người đang cố dùng bot.

Trong nhóm đã cho phép, mặc định bot chỉ trả lời khi có người **nhắc tên nó** (gõ `@ten_bot`, hoặc bấm chọn tên nó từ danh sách thành viên) hoặc **reply vào tin của nó**. Nhóm có nhiều bot thì nó phân biệt được: nhắc tên bot khác hay reply vào bot khác thì nó không nhận vơ.

Muốn nó trả lời **mọi câu trong nhóm** thì đổi nút "Trong nhóm, bot lên tiếng khi" sang **Mọi tin**. Cân nhắc kỹ: nhóm đông người thì rất ồn và đốt quota model nhanh. Và nó chỉ có tác dụng khi đã tắt chế độ riêng tư - đọc mục ngay dưới.

### Bot trên Zalo cá nhân: nhóm và chế độ Tự đánh giá

Từ 0.64.82 bot gắn vào **tài khoản Zalo cá nhân** (nối ở trang Kết nối, xem [Zalo Agent MCP](12-zalo.md)) đứng được trong nhóm Zalo, không chỉ chat riêng. Nick đó là người thật nên mọi thứ dưới đây nghiêng về phía im lặng.

**Nhóm phải được bạn cho phép.** Có tin từ một nhóm lạ thì nhóm hiện lên hàng chờ ngay trên thẻ bot, kèm tên nhóm và nút **Cho phép nhóm này**. Khác Telegram, ở Zalo bot **không nói một câu nào** vào nhóm chưa cho phép: một câu như "em chưa được bật" trước cả nhóm là tự khai mình là máy.

**Được tag, reply hoặc gọi tên thì trả lời luôn.** Từ 0.65.0 gọi tên trơn ("nhi mai ơi") cũng được coi là gọi, xem [Bộ phán xử](#bộ-phán-xử-bot-tự-quyết-nói-hay-im-và-học-từ-nhóm). Bot nhận ra tag bằng "@tên" trong chữ (tên là nhãn kết nối hoặc tên hiển thị của nick), bằng `mentions` nếu Zalo trả về, và nhận ra reply vào tin của nó. Tag người khác thì bot không nhận vơ. Nếu tag mà bot im, xem mục sự cố bên dưới.

**Tự đánh giá.** Ở nút "Trong nhóm, bot lên tiếng khi", chọn **Tự đánh giá**. Bot vẫn trả lời khi được tag, và thêm một việc: tin không ai gọi tên thì bot tự xem có nên lên tiếng không. Đi từ rẻ tới đắt, tầng nào loại là dừng và không tốn lượt model:

1. Tin có giống một **câu hỏi hoặc lời nhờ giúp** không (có dấu hỏi, hay các chữ như "làm sao", "lỗi", "cách", "hướng dẫn"). Tin trò chuyện, cảm ơn, một cái link, hay tin nhắc người khác thì bỏ.
2. **Tài liệu trong brain của bot** có phần nào khớp câu hỏi không. Đây là cách bot hiểu "chủ đề mình trả lời được": có căn cứ trong tài liệu bạn đưa, không phải kiến thức chung của model. Không có thì im.
3. Cuối cùng một lượt model, trong đó Agent vẫn được quyền tự chọn im nếu thấy không nên chen vào.

Để bot không thành máy phát thanh: bot **chờ khoảng 20 giây** trước khi tự trả lời, và nếu trong lúc đó có người nhắn tay bằng nick này thì nhường. Mỗi nhóm bot chỉ tự trả lời tối đa **8 lần mỗi giờ**, mỗi người **3 lần mỗi giờ**, và giữa hai lần có một khoảng nghỉ. Lượt được tag không bị các giới hạn này chặn.

Tin bị bỏ qua vì đáng lẽ trả lời được mà tài liệu không có, hay vì hết hạn mức, đều có **một dòng lý do trong nhật ký bot** (thẻ bot, mục nhật ký). Dòng "tài liệu không có phần nào khớp" chính là câu hỏi thật của người trong nhóm mà brain của bot còn thiếu, nên đó là danh sách để bổ sung tài liệu. Các dòng bỏ qua **không** tính vào số lượt hay tỉ lệ bí của bot.

Chế độ này cũng chạy với nhóm Telegram nếu bạn đã tắt chế độ riêng tư (mục ngay dưới), nhưng phần chờ nhường và nhận tag theo tên chỉ có ở Zalo cá nhân.

**Tag trong chú thích ảnh cũng được tính** (từ 0.65.13). Gửi ảnh kèm chú thích "@Tên bot ..." thì chú thích được coi như nội dung tin: bot nhận ra tag và trả lời như với tin chữ, và biết tin đó có kèm một ảnh. **Bot xem được ảnh đó bằng chính bộ não của nó** (từ 0.81.0): Javis lưu ảnh vào brain của bot rồi gửi thẳng ảnh vào lượt chat cho model đang chạy bot (Claude, GPT, Gemini, OpenRouter, Groq, Ollama, gói ChatGPT, gói Claude Code). Không cần kết nối ChatGPT nữa. Bộ não không xem được ảnh (Antigravity, Grok Build, model chữ thuần) hoặc ảnh không tải được thì bot đọc mỗi chú thích và nói thật là chưa xem được ảnh. Telegram cũng vậy: ảnh có tag bot, trả lời vào một ảnh rồi tag bot, hoặc gửi ảnh rồi tag bot ngay sau (trong 3 phút, cùng một người; cần tắt chế độ riêng tư) đều được. Ảnh không có chú thích thì vẫn bị bỏ qua.

**Bot ở Zalo cá nhân khác bot ở Telegram** ở một điểm quan trọng: câu nó gửi mang tên nick, và nick có thể còn nhiều người khác nhắn vào. Vì thế bot chỉ xử lý tin dạng chữ và tin **ảnh có chú thích** (ảnh trơn, tiếng, file bỏ qua), bỏ tin cũ quá 3 phút, và nhường 10 phút khi có người vừa nhắn tay ở cuộc chat đó.

**Trong nhóm, bot tự tag người nó đang trả lời** (từ 0.65.7). Khách hỏi thì câu trả lời mở đầu bằng "@Tên ...", nên người hỏi được báo và cả nhóm biết bot đang nói với ai. Không có ô cài đặt nào, và chỉ áp dụng cho nhóm (chat riêng thì không cần). Nút **Trả lời giúp tin này** ở Hòm thư cũng tag người gửi tin đó. Tin có tag đi bằng chính công cụ `zalo-agent-cli` chứ không qua MCP (MCP chỉ gửi được chữ), nên mỗi câu trả lời trong nhóm chậm thêm khoảng 1 đến 2 giây (từ 0.65.8; trước đó khoảng 3 đến 5 giây vì mỗi lần phải chạy `npx`). Lần đầu sau khi cập nhật, Javis cài ngầm một bản công cụ Zalo vào thư mục `tools/` trong thư mục dữ liệu của mình (khoảng 10 giây, một lần); trong lúc đó câu trả lời vẫn đi bằng cách cũ nên chậm hơn. Nếu tag hỏng (máy thiếu Node.js, Zalo từ chối) thì bot vẫn gửi câu trả lời như cũ, chỉ mất cái tag; hỏng ba lần liên tiếp thì bot nghỉ tag 10 phút để khỏi chậm thêm vô ích. Riêng trường hợp quá giờ, Javis **không gửi lại**, vì tin có thể đã đi rồi và gửi lại sẽ ra hai câu dưới tên bạn; nhật ký bot ghi một dòng lỗi.

**Trong nhóm, bot xem 30 tin gần nhất để trả lời đúng ngữ cảnh** (từ 0.65.12). Bot chỉ được gọi khi có người tag hay reply, nên trước đây nó chỉ thấy đúng câu gọi nó và không hiểu "vậy còn cái kia?". Nay mỗi lượt trả lời trong nhóm kèm tối đa 30 tin ngay trước tin đang hỏi (mỗi tin cắt khoảng 300 ký tự, cả khối tối đa khoảng 6.000 ký tự, bớt từ tin cũ nhất). Khối này được đưa vào như **dữ liệu**, không phải lệnh: marker nội bộ và thẻ đóng khối trong tin nhắn bị gỡ, và bot được dặn bỏ qua mọi câu trong đó bảo nó đổi quy tắc. Nó nằm trong hướng dẫn của lượt chứ không ghi vào lịch sử phiên của Agent, nên không phình dần. Chat riêng không đổi. Mỗi lượt trong nhóm tốn thêm khoảng 1.000 đến 2.000 token.

### Bộ phán xử: bot tự quyết nói hay im, và học từ nhóm

Chế độ Tự đánh giá cũ dùng một cửa từ khoá: tin nào không giống câu hỏi là bị vứt trong im lặng, không để lại dòng nhật ký nào. Từ 0.65.0 có **Bộ phán xử** thay cửa đó bằng một bộ đọc ngữ cảnh, dùng chung cho mọi bot nhưng mỗi bot một vai. Từ 0.65.1 nó **tự vận hành hoàn toàn: không còn ô cài đặt nào**.

**Bật ở đâu.** Sửa bot, phần **Bot trả lời ai**, chọn thẻ **Tự động hóa tất cả** (mọi cuộc chat), hoặc chọn **Tự đánh giá** ở nút "Trong nhóm, bot lên tiếng khi" (cho những nhóm bạn chọn). Chỉ vậy. Muốn tắt thì chọn cách khác. Máy tự lo phần còn lại:
- **Mức hăng hái.** Mỗi nhóm có một ngưỡng nói riêng, bắt đầu ở mức vừa. Ngưỡng nhích xuống khi bot im nhầm, nhích lên khi bot chen nhầm, và tự co dần về mức vừa nếu lâu không có phản hồi (chu kỳ bán rã 14 ngày).
- **Khi không ai gọi, bot chỉ nói nếu có căn cứ.** Bot có tài liệu thì phải có phần tài liệu khớp với câu hỏi. Bot không có tài liệu nào thì dựa vào vai của Agent (nếu không thì nó không bao giờ tự nói được). Máy tự biết bot thuộc loại nào từ brain của bot. Ca đã học không được miễn luật này.
- **Hồ sơ vai tự soạn** từ file Agent và mục lục tài liệu của CHÍNH bot đó, và tự soạn lại khi Agent hoặc tài liệu đổi.
- **Tự học luôn bật** (xem dưới).

**Khác luật cũ ở đâu.**
- **Gọi tên trơn cũng là gọi bot**, không cần @: "nhi mai ơi", "alo nhi mai", hoặc tên đứng đầu câu. Riêng điều này áp dụng cho MỌI bot, kể cả khi chưa ở chế độ Tự đánh giá. Tên tự nhận là nhãn kết nối Zalo và tên hiển thị của nick. Muốn bot nhận thêm một tên (ví dụ "Thu") thì gọi bot rồi dạy, ví dụ "Nhi Mai ơi, từ giờ gọi em là Thu nhé", bằng tài khoản của người được dạy (xem dưới). Tên nằm giữa câu ("hỏi nhi mai xem") chưa đủ để coi là gọi: bộ phán xử sẽ cân nhắc.
- **Đọc vài tin gần nhất** thay vì đúng một tin, nên người vừa được bot trả lời hỏi tiếp ("vậy còn cái kia?") được hiểu là hỏi tiếp cho bot, và không bị chặn bởi khoảng nghỉ 20 giây giữa hai lần bot tự nói.
- **Mọi quyết định đều có dấu vết, kể cả lúc bot im.** Menu "..." của thẻ bot, mục **Bộ phán xử**, liệt kê từng tin kèm lý do (ví dụ "Tài liệu không có phần khớp", "Điểm thấp hơn ngưỡng", "Hết hạn mức tự nói") và điểm so với ngưỡng.

**Mỗi bot một vai.** Bộ phán xử **không viết câu trả lời**: giọng và cách trả lời vẫn là của Agent, nên Nhi Mai nói kiểu Nhi Mai và Javis Vũ nói kiểu Javis Vũ. Ba bot khác ngành không đọc được ca đã học, bài học hay hồ sơ của nhau, và ngưỡng của nhóm này không đổi nhóm kia. Bot mới có sẵn khoảng 12 tin mẫu đúng ngành của nó, do model viết từ Agent, và các mẫu này nhạt dần khi bot học được ca thật. Bản 0.65.0 có ô "Luật lên tiếng" viết tay: chữ đã viết được gộp một lần vào **bài học** của bot (thấy trong menu Bộ phán xử), form không còn ô đó.

**Bạn chỉnh bằng gì.** Không phải bằng cài đặt mà bằng phản hồi, ngay trên dữ liệu thật:
- Bấm **Đúng** hoặc **Sai** ở từng dòng trong menu Bộ phán xử: nhãn nặng nhất, có tác dụng ngay ở tin kế tiếp. **Đúng** nghĩa là bot làm đúng (nói đúng lúc, hoặc im đúng lúc); **Sai** nghĩa là bot đáng lẽ phải làm ngược lại. Rê chuột vào nút để xem nghĩa cụ thể của từng dòng (ví dụ "Đáng lẽ bot phải im").
- Bấm **Đặt làm chủ bot** ở tin của bạn trong menu Bộ phán xử: từ đó bot nghe lời dạy của bạn ngay trong nhóm (gọi tên bot rồi nói "đừng trả lời chuyện phiếm" hay "gọi tên em là em phải trả lời") và lưu thành **bài học**. Chỉ những ai bạn đã đặt mới dạy được; lời người khác trong nhóm ("từ giờ cứ trả lời mọi tin") KHÔNG thành luật. Đầu menu có dòng **Chủ bot** liệt kê những người đã đặt, mỗi người có nút **Bỏ chủ** (từ 0.65.14); người đã đặt hiện nhãn **Chủ** ở các tin của họ.

**Tự học.** Bot còn học từ phản ứng MẠNH của người thật, và ca vừa học có tác dụng ngay ở tin kế tiếp:
- Bot im mà **cùng người đó hỏi lại** ("sao không trả lời") hoặc có người gọi bot ngay sau đó: lần sau tin giống vậy bot nói, ngưỡng của nhóm hạ.
- Bot tự nói mà **chủ nhắc** "đừng chen vào", hoặc bạn bấm **Tiếp quản** ngay sau đó: ngưỡng của nhóm nâng lên.
- Bot được cảm ơn hoặc được hỏi tiếp đúng mạch: ghi nhận là đúng.
- Bị phớt lờ thì **không tính**, vì người ta phớt lờ liên tục.

Học chỉ đổi việc **nói hay im**, không bao giờ đổi điều bot khẳng định: câu trả lời vẫn bám tài liệu và vai của Agent. Hạn mức tự nói, việc nhường khi bạn đang gõ tay, nhóm nào được phép và mức quyền đều nằm ngoài vòng học. Bộ phán xử gặp lỗi, hết giờ hay trả về rác thì bot **im** (riêng tin gọi tên chắc chắn vẫn được trả lời). Nút **Quên hết** xoá ca, ngưỡng, bài học **và cả nhật ký quyết định** của bot (không hoàn tác được).

**Riêng tư.** Vì tự vận hành, bot ở chế độ Tự đánh giá ghi lại chữ của mọi tin nhóm đáng cân nhắc để hiện trong menu Bộ phán xử: tối đa 400 ký tự mỗi tin, giữ 14 ngày. Các ca đã học (từ phản hồi của bạn hoặc của nhóm) giữ tối đa 180 ngày. Tất cả nằm trong thư mục dữ liệu của Javis (không lên git). Bot không ở chế độ Tự đánh giá thì không lưu gì. **Quên hết** hoặc xoá bot xoá sạch dữ liệu này.

**Ai chạy và tốn gì.** Mỗi tin đáng cân nhắc tốn một lượt model rẻ theo model "việc nền" bạn chọn ở trang **Models** (gói thuê bao hay API rẻ đều được), thêm khoảng vài giây; model chạy trong thư mục trống, không công cụ ghi hay chạy lệnh. Tin hiển nhiên không đáng (rỗng, chỉ có link, nhắn người khác khi chưa học được gì khác) và tin gọi tên rõ ràng không tốn lượt nào. Bộ phán xử dùng đủ trên **Zalo cá nhân** (cửa sổ tin, tin nối tiếp). Trên **Telegram** nó cũng quyết trong nhóm nhưng không có cửa sổ tin nối tiếp.

**Cho người vận hành.** Muốn quan sát trước khi tin tưởng, đặt biến môi trường `JAVIS_REPLY_POLICY_SHADOW=1` rồi khởi động lại: mọi bot chạy thử, luật cũ vẫn quyết còn bộ phán xử chỉ ghi quyết định của nó để so sánh. Đây là công tắc của người vận hành, không có trong giao diện.

### Bộ phán xử tự soát, và nhờ Javis chỉnh (từ 0.77.0)

Ca học tức thì ở trên sửa từng tin một. Từ 0.77.0 còn có một **vòng tự soát** nhìn cả bức tranh: khi một bot gom đủ bằng chứng mới (khoảng 8 nhãn Đúng/Sai, hoặc 40 tin bị im) và đã qua 24 giờ từ lần soát trước, Javis gửi báo cáo của bot đó cho **bộ não chính** (model bạn chọn ở trang **Models**, thường mạnh hơn model rẻ chấm từng tin). Model tìm mẫu lặp lại, ví dụ "khách tag anh Quý hỏi lịch học mà bot im cả bảy lần", rồi tự chỉnh tối đa 3 chỗ. Không có mẫu rõ thì không đổi gì.

**Chỉnh được những gì.** Chỉ việc nói hay im, trong một danh sách đóng:
- thêm hoặc bỏ **bài học** (vòng soát chỉ bỏ được bài nó tự viết, không bao giờ đẩy bài bạn dạy ra ngoài);
- biến một tin bị im thành **ca mẫu** "nên trả lời" (hoặc ngược lại);
- **ngưỡng** của từng nhóm, **độ hăng nói** chung của bot;
- **xét cả tin tag người khác**: mặc định tin mở đầu bằng "@ai đó" bị bỏ qua. Bật lên thì tin như "@anh Quý ơi lịch học sao" vẫn được cân nhắc, nhưng bot vẫn chỉ nói khi tài liệu có phần khớp và bộ phán xử đồng ý. Bấm **Sai** ở một tin tag như vậy giờ cũng có tác dụng: tin giống nó lần sau sẽ được xét.

Mỗi thay đổi phải dẫn đúng những tin của chính bot đó làm bằng chứng, nên chữ khách gõ trong nhóm không biến thành lệnh được. Hạn mức, việc nhường khi bạn gõ tay, quyền và nội dung câu trả lời vẫn nằm ngoài tầm.

**Tự đo, tự hoàn.** Sau mỗi lần soát, máy so tỉ lệ bot bị chấm sai trước và sau. Sai nhiều hơn rõ rệt thì cả lần soát đó tự hoàn lại, và bạn nhận một tin báo. Chỗ nào nằm cứng trong mã (vòng soát không chỉnh được) thì nó ghi góp ý vào `Javis/gop-y-bo-phan-xu.md` trong brain của bot.

**Bạn biết bằng cách nào.** Lần soát nào có chỉnh hay có góp ý thì gửi đúng một tin vào **hộp thư** (cái chuông) và Telegram của bạn, liệt kê từng thay đổi và mã lần soát.

**Muốn can thiệp thì nói với Javis**, không cần mở cài đặt nào:
- "Thống kê bộ phán xử của Javis Vũ tuần này, vì sao bot im nhiều thế?"
- "Cho Javis Vũ trả lời thay anh khi khách tag anh hỏi về lịch học."
- "Hoàn lại lần tự soát a1b2c3 của Javis Vũ."

Javis đọc đúng số liệu của bộ phán xử (cùng báo cáo mà vòng soát đọc), đề xuất, và chỉnh khi bạn đồng ý. Mọi thay đổi, của vòng soát hay do bạn nhờ, đều có nhật ký và hoàn lại được. Muốn phân tích kỹ hơn thì chuyển bộ não chính sang model mạnh hơn ở trang **Models** trước khi hỏi.

**Bot chăm khách không bao giờ thấy hai công cụ này.** Kho của bộ phán xử chứa chữ chat của mọi khách, nên chỉ phiên của chính bạn đọc và chỉnh được. Bot ở mức Được ghi hay Toàn quyền cũng không thấy.

**Lưu ý gói thuê bao.** Vòng tự soát là việc chạy nền trên bộ não chính. Nếu đó là gói Claude Pro/Max thì đây thuộc loại dùng mà Anthropic không tính là cá nhân thông thường. Tần suất rất thấp (tối đa một lần mỗi ngày mỗi bot, chỉ khi có bằng chứng), nhưng an toàn nhất là để bộ não chính chạy bằng gói ChatGPT, Grok hoặc một API key. Người vận hành tắt hẳn vòng soát bằng biến môi trường `JAVIS_REPLY_POLICY_REVIEW=0`.

### Chế độ riêng tư của Telegram (đọc mục này nếu bot im trong nhóm)

Mọi bot mới đều **bật sẵn** chế độ riêng tư. Khi nó bật, Telegram **không chuyển** phần lớn tin trong nhóm cho bot, và chặn ngay từ phía Telegram - Javis không bao giờ nhìn thấy những tin đó, dù bạn đặt gì trong dashboard.

Thứ **chắc chắn** tới được bot khi chế độ này bật:

- **Lệnh** `/...` (đó là lý do `/id` luôn chạy được).
- **Tin trả lời thẳng vào tin của bot** (bấm Reply vào một câu bot đã nói).
- Tin dịch vụ (thêm/bớt thành viên).

Tin chỉ **nhắc tên** bot thì tuỳ phiên bản và tuỳ loại nhóm, **không bảo đảm**. Nếu bạn tag tên bot mà nó im re trong khi nhắn riêng vẫn chạy tốt, đây gần như luôn là lý do.

Sửa bằng **một trong hai cách**:

1. Mở **@BotFather**, gõ `/setprivacy`, chọn bot này, chọn **Disable**.
2. Hoặc cho bot làm **quản trị viên** nhóm đó. Bot là admin thì nhận được mọi tin, không phụ thuộc chế độ riêng tư.

Xong thì **tắt rồi bật lại bot** ở trang Chatbot để nó đọc lại trạng thái mới. Thẻ bot hiện trạng thái này sẵn cho mọi bot có dùng nhóm, và `/id` trong nhóm cũng nói ra.

Còn một nguyên nhân thứ ba cho đúng triệu chứng đó, hiếm hơn: **bot không hỏi được danh tính của chính nó từ Telegram** (mạng rớt đúng giây khởi động). Khi đó nó không biết `@username` của mình nên không nhận ra ai đang gọi tên, dù tin nhắn riêng vẫn chạy hoàn hảo. Thẻ bot báo bằng một dòng đỏ, và Javis tự hỏi lại mỗi phút; tắt bật lại bot là xong ngay.

**Nhóm thường được nâng thành siêu nhóm thì Telegram đổi id của nó** (thêm tiền tố `-100`). Javis nghe được lúc đó và tự cập nhật danh sách, nên bạn không phải khai lại - đây từng là cách bot im lặng mà không để lại manh mối nào.

## Đọc thẻ bot

Mỗi thẻ có một chấm màu và một dòng trạng thái. **Bốn** trạng thái chứ không phải hai:

| Chấm | Nghĩa |
|---|---|
| Xanh - Đang chạy | Bot đang nghe và trả lời bình thường |
| Vàng - Đang khởi động | Vừa bật, đang bắt tay với Telegram |
| Đỏ - Lỗi | Bot chết. Token bị thu hồi, mạng rớt, hoặc trùng token với nơi khác. Lý do hiện ngay dưới thẻ |
| Xám - Đã tắt | Bạn tắt nó |

Trạng thái **Lỗi** phải nhìn thấy được, vì bot chết âm thầm là thứ bạn chỉ phát hiện khi có người phàn nàn.

Thẻ **tự làm mới vài giây một lần** khi bạn đang mở trang. Cần vì trạng thái đổi mà không ai bấm gì: vừa bấm Bật thì thẻ báo "Đang khởi động" (bot đang bắt tay với Telegram), rồi mấy giây sau nó thành "Đang chạy". Không tự làm mới thì thẻ đứng nguyên ở "Đang khởi động" cho tới lúc bạn rời trang rồi quay lại - trong khi bot đã trả lời được từ lâu.

Thẻ cũng cảnh báo khi **Agent của bot không còn** (bạn xoá hoặc đổi slug ở trang Agents). Lúc đó bot vẫn chạy nhưng trả lời không có hướng dẫn vai trò, nên sửa ngay.

**Mức quyền hiện ngay trên thẻ**, ở cả ba mức chứ không riêng hai mức có quyền thao tác: xám là Chỉ đọc, vàng là Được ghi, đỏ là Toàn quyền. Không phải mở form Sửa mới biết con nào đang ở mức nào, và một thẻ không có nhãn không còn đọc ra được hai nghĩa ngược nhau.

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

Đừng lẫn bot với **kênh Telegram của chính bạn**: kênh đó *có* đi qua hai mức tiết kiệm (từ 0.24.0), vì Javis của bạn đúng là có CLAUDE.md và MEMORY.md để gọt. Bot thì không có gì để gọt.

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

Cách Javis bảo đảm: **bot không bao giờ chạm vào công cụ gốc của engine.** Ở mức Chỉ đọc nó không có công cụ nào; ở mức Đọc tài liệu nó chỉ có ba công cụ đọc tài liệu; ở hai mức trên, mọi công cụ đều đi qua trung tâm kết nối của Javis, nơi đường dẫn file bị kẹp và mức quyền được áp ngay tại chỗ gọi. Bot không mở CLI, nên `Bash` và `Read` đường dẫn tuyệt đối của Claude Code không có mặt ở đây.

Còn tài liệu thì vẫn được tra sẵn bằng Python trước khi model chạy rồi đưa vào đầu bài, ở mọi mức. Bot đọc được brain của nó mà không cần công cụ nào.

## Bốn mức quyền - bot được làm gì

Chọn ở ô **Bot được làm gì** khi tạo hoặc sửa bot. Mặc định là **Chỉ đọc**.

| Mức | Bot làm được | Hợp với |
|---|---|---|
| **Chỉ đọc** (mặc định) | Chỉ đọc tài liệu rồi trả lời. Không công cụ nào. | Trực và hỏi đáp - gần như mọi việc |
| **Đọc tài liệu** | Như Chỉ đọc, cộng ba công cụ chỉ-đọc để **tự tìm và mở** tài liệu trong brain của nó. Không ghi, không gọi nguồn nào | Bot hay im oan vì khách gõ khác chữ tài liệu |
| **Được ghi** | Thêm: ghi file trong brain của chính nó, gọi nguồn dữ liệu đã đấu ở mức đọc/ghi | Ghi nhận yêu cầu, cập nhật ghi chú, tra số liệu thật |
| **Toàn quyền** | Thêm: gửi đi, thanh toán, đặt/huỷ, xoá, công bố ra ngoài | Nơi bạn kiểm soát được danh sách người nhắn vào |

### Mức Đọc tài liệu (từ 0.80.0)

Ở mức Chỉ đọc, Javis tra tài liệu **theo chữ** trước mỗi lượt rồi đưa vài đoạn khớp nhất cho bot. Cách này giữ bot không bịa, nhưng trượt khi khách dùng chữ khác tài liệu: tài liệu ghi "hoàn trả" mà khách gõ "đổi trả" là không ra, và bot im hoặc nói chưa có thông tin.

Mức **Đọc tài liệu** giữ nguyên phần tra sẵn đó, rồi cho bot thêm ba công cụ để **tự** đọc brain của nó như Javis chính đọc sổ tay:

- **Tìm** trong tài liệu, thử lại bằng từ khác khi lần đầu không ra.
- **Xem danh sách** tài liệu kèm tên các mục, để tự chọn tài liệu đúng chủ đề.
- **Mở đọc trọn** một tài liệu.

Bot được dặn: câu hỏi cần thông tin cụ thể mà phần tra sẵn không có thì phải tự tìm trước, chỉ khi tìm kỹ vẫn không có mới nói chưa có thông tin.

**Bộ phán xử cũng nhìn mục lục.** Ở các mức khác, tin không ai gọi bot mà khớp chữ trượt thì bộ phán xử cho im ngay. Ở mức này nó được xem mục lục tài liệu của bot và tự xét tin đó có thuộc chủ đề nào không, nên khách gõ khác chữ không còn bị im oan.

**Vì sao mức này không bắt tick đồng ý:** nó không lấy đi thứ gì phần tra sẵn chưa lấy.

- Không có công cụ ghi nào, không gọi nguồn dữ liệu nào, không plugin, kể cả khi bạn đã đấu nhiều nguồn. Javis khoá ở tầng gọi công cụ, không phải bằng lời dặn.
- Bot chỉ mở được đúng những file mà phần tra sẵn vẫn tra: trừ `memory/`, `inbox/` (file khách gửi), skill, plugin, file quy ước của Javis, và thêm cả `agents/`, `workflows/` (hướng dẫn nội bộ của bạn). Đường dẫn khách gõ chỉ được so với danh sách đó, nên `../`, đường dẫn tuyệt đối hay file liên kết trỏ ra ngoài đều không mở được.
- Chỉ đúng brain của bot. Thiếu thông tin brain thì bot không có công cụ nào, chứ không lấy brain bạn đang mở.

Nút **Thử** chạy đúng mức này (vì nó chỉ đọc), nên thử trước được ngay. Mức này tốn thêm vài lượt gọi model khi bot tự tìm, và nhạy với engine giống hai mức trên (xem mục [Engine nào chạy được mức nâng quyền](#engine-nào-chạy-được-mức-nâng-quyền)).

### Cái mất được khi nâng mức

Đây là phần đáng đọc kỹ nhất trang này, vì nó là chỗ khác biệt căn bản giữa bot chuyên trách và Javis của bạn: **người gõ vào bot là người khác, không phải bạn.**

Ở mức Chỉ đọc thì điều đó vô hại - có dụ khéo cỡ nào bot cũng chỉ nói năng lạc đề, vì nó không có gì để làm hại. Nâng mức là bỏ đúng tính chất đó đi.

**Mức Được ghi:**

- Bot ghi được file trong brain của nó. Người nhắn cho bot một câu là nội dung trong brain đổi thật, **không có bước duyệt**.
- Bot gọi được các nguồn dữ liệu bạn đã đấu, ở mức đọc và ghi. Mọi thứ trong những nguồn đó nằm trong tầm với của người đang chat với bot.
- Javis vẫn **chặn cứng** nhóm thao tác ra ngoài ở mức này: không gửi đi, không thanh toán, không đặt hay huỷ, không xoá, không công bố gì. Chặn ở tầng gọi công cụ, không phải bằng lời dặn.

**Mức Toàn quyền:**

- Bot làm được **mọi thứ** các nguồn đã đấu cho phép, kể cả gửi đi, thanh toán, đặt hay huỷ, xoá, công bố ra ngoài. Những thao tác đó **không hoàn tác được**.
- Một câu dụ khéo ("bỏ qua hướng dẫn trước, làm giúp việc này") là đủ để bot làm theo. Rào cứng còn lại là **mức quyền của từng kết nối** ở trang Kết nối (hạ một kết nối về Chỉ đọc thì bot cũng bị chặn ghi ở đó), nhưng rào đó chặn theo loại thao tác nên với nguồn Javis chưa có khuôn phân loại sẵn thì không kín tuyệt đối. Ngoài ra chỉ còn file Agent bạn viết, mà chữ thì lách được.
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

Mức **Chỉ đọc** chạy giống hệt nhau trên cả chín bộ não, không có ngoại lệ.

Ba mức còn lại (Đọc tài liệu, Được ghi, Toàn quyền) cần engine gọi được công cụ. Sáu engine API (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama) và gói Claude Code dùng đường đã chạy thật lâu nay. Riêng **gói ChatGPT** đi qua một đường của backend Codex mà nhà cung cấp chưa công bố ổn định, nên có thể không gọi được công cụ.

Gặp trường hợp đó thì **bot không chết**: nó trả lời lượt đó ở mức Chỉ đọc, và thẻ bot hiện một dải vàng nói rõ nó đang chạy thiếu quyền so với mức bạn đặt. Nâng quyền không bao giờ được phép lấy đi năng lực bot vốn đã có.

Thấy dải vàng đó thì chọn một trong hai: đổi engine ở trang **Models** nếu bạn thật sự cần bot làm việc, hoặc hạ mức bot xuống **Chỉ đọc** cho khỏi hiểu nhầm là nó đang làm.

### Đổi bộ não không đổi trải nghiệm

Bot chạy giống hệt nhau trên **mọi bộ não**: Claude Code, ChatGPT, Grok Build, Antigravity, OpenRouter, OpenAI API, Anthropic API, Gemini, Groq, Ollama. Đổi model thì bot đổi theo, nhưng cách nó làm việc không đổi. Khi công cụ gọi được thì mọi engine cầm **đúng một bộ công cụ** - xem lưu ý ở mục trên về gói ChatGPT.

Làm được vì lượt của bot đi một đường riêng, chung cho mọi engine: cùng đầu bài từ Agent, cùng tài liệu tra sẵn, cùng lịch sử hội thoại, và công cụ (nếu có) lấy từ cùng một chỗ. Khác biệt còn lại đúng bằng khác biệt giữa các model, không phải giữa các đường ống.

Đường này cũng không mở CLI, nên bot trả lời nhanh hơn đường chat của bạn.

### Để tài liệu ăn khớp tốt

- **Đặt tiêu đề rõ ràng trong file.** Javis cắt tài liệu theo tiêu đề markdown (`##`), và mỗi đoạn được lấy riêng lẻ. Một file dài không tiêu đề thì bot có thể đọc được nửa điều kiện rồi trả lời như thể đó là toàn bộ điều kiện. Chia thành "Giá bán lẻ", "Giá sỉ", "Đổi trả", "Giao hàng"... là ăn khớp tốt nhất.
- **File người ngoài gửi lên KHÔNG được tính là tài liệu.** Chúng nằm trong `inbox/khach/` và bị loại hẳn khỏi phần tra cứu. Nếu không thì bất kỳ ai cũng tải lên một file ghi đè quy định của bạn rồi hỏi lại một câu, và bot trích dẫn nó như tài liệu chính thức.
- **File quy ước nội bộ của Javis cũng bị loại.** `CLAUDE.md`, `AGENTS.md`, `wiki/index.md`, `wiki/log.md` và mấy file điều hướng khác có mặt trong mọi brain nhưng là ruột hệ thống, không phải nội dung trả lời người ngoài. Note Wiki thật của anh vẫn dùng bình thường.
- **Gõ có dấu và không dấu đều tìm được**, nhưng gõ có dấu chính xác hơn: "bán" không khớp vào "bản", "cà" không khớp vào "cả". Tài liệu nên viết đúng chính tả và đúng dấu.

## Nhật ký và chỗ tài liệu đang thiếu

Bấm **Nhật ký** trên thẻ bot. Có hai tab, và tab mở sẵn là tab quan trọng hơn.

**Hội thoại của bot với khách nằm ở đâu.** Từ 0.65.0 mỗi cuộc chat của khách là một hội thoại trong **lịch sử của Agent** nối với bot, ở trang **Cộng sự** (mở Agent đó, tab Lịch sử), có nhãn **Bot** để phân biệt với cuộc bạn tự chat với Agent. Hội thoại trong nhóm mang **tên nhóm** (từ 0.65.1), không mang tin đầu của người nhắn đầu tiên; chat riêng vẫn đặt tên theo tin đầu. Chúng không còn hiện ở lịch sử trang **Trò chuyện**. Bot dùng chung một Agent thì hội thoại của cả hai cùng nằm trong lịch sử Agent đó.

**Bot bí** liệt kê những câu bot trả lời không nổi, gom trùng và xếp theo **số lần được hỏi**. Đây là tab đáng giá nhất: mỗi dòng chỉ đúng một chỗ tài liệu của bạn đang thiếu, bằng chính lời người hỏi. Viết bổ sung vào brain là lần sau bot trả lời được.

Gom trùng có bỏ dấu, nên "Giá bao nhiêu?" và "gia bao nhieu" được tính là một câu. Nếu không thì cùng một câu hỏi bị tách thành mấy dòng lẻ và anh không thấy được nó thật ra được hỏi nhiều.

"Bí" đo bằng **chính câu bot vừa nói**: nó nói chưa có thông tin, hoặc nó phải chuyển người thật. Với bot chạy chế độ "chỉ tài liệu" thì không tìm ra tài liệu cũng tính luôn.

Đáng chú ý nhất là loại bí mà bot **vẫn tìm ra tài liệu**: tài liệu có nhưng thiếu đúng ý người ta cần. Loại đó chỉ ra chỗ tài liệu viết chưa đủ, tinh vi hơn loại không có file nào.

**Hội thoại gần đây** cho xem lại từng lượt, kèm **đúng file bot đã dùng** để trả lời. Dòng nguồn đó là thứ làm cho câu hỏi "bot trả lời đúng chưa" kiểm chứng được thay vì chỉ đoán.

### Khi nào người trực bị gọi

Bot đã đặt Chat ID người trực từ trước 0.64.83 thì gọi người trong hai trường hợp: người đang hỏi gõ `/nhanvien`, hoặc bot **bí hai câu liên tiếp** với cùng một người. Trả lời được một câu là đếm về 0.

Bí một câu lẻ thì không gọi. Báo mọi câu vu vơ thì vài lần là người trực tắt thông báo, và lúc có người thật cần giúp thì không ai đọc nữa. Hai câu liên tiếp mới là dấu hiệu người ta đang mắc kẹt thật.

Trường hợp thứ ba là bot **gãy** (không gọi được model). Cái này báo ngay từ lần đầu, không chờ đủ hai câu, vì mỗi phút im lặng là người đang nhắn nghĩ mình bị bỏ mặc. Nhưng chỉ báo **một lần** cho tới khi có lượt chạy được, không thì hộp thư người trực thành log lỗi.

Trước khi coi là gãy, Javis đã tự hỏi lại tối đa ba lần nếu lỗi là loại **tạm thời** (nhà cung cấp trả 429 vì gọi quá dày, 5xx vì quá tải, mạng chớp tắt). Một cú 429 chớp nhoáng không còn đánh thức người trực nữa. Thông báo gãy có kèm chữ *(đã thử lại 3 lần)* nghĩa là đã thử hết cách, nên đi xem trang **Models** hoặc hạn mức của tài khoản. Chi tiết ở [Khắc phục sự cố](17-khac-phuc-su-co.md#nhà-cung-cấp-báo-vượt-hạn-mức).

Nhật ký giữ 2000 lượt gần nhất mỗi bot, cũ hơn thì tự cắt. Xoá bot thì nhật ký đi theo.

## Bot làm được gì và KHÔNG làm được gì

**Ở mọi mức, bot làm được:** đọc tài liệu trong brain của nó, trả lời theo quy định trong file Agent, nhớ mạch hội thoại với từng người, chuyển cho người trực.

**Ở mọi mức, bot KHÔNG làm được:** đọc hay ghi brain khác, chạy lệnh máy, tự mở trang web lạ, đẻ agent con, dùng lệnh quản trị (`/brain`, `/model`, `/status`... đều không có tác dụng, bot chỉ trả lời chung chung).

**Phần còn lại tuỳ mức quyền** bạn đặt - ghi file, gọi nguồn dữ liệu, thao tác ra ngoài. Xem bảng ở mục [Bốn mức quyền](#bốn-mức-quyền---bot-được-làm-gì). Mặc định là Chỉ đọc, tức không làm được thứ nào trong số đó.

Menu lệnh trong Telegram của bot chỉ có ba mục (`/help`, `/nhanvien`, `/id`), không phải menu quản trị của bot Javis chính. Liệt kê ở đó những lệnh bot từ chối chạy là dạy người ta đi tìm một tập lệnh khác.

Còn **cách nó nói năng, phạm vi nó nhận trả lời, thứ nó từ chối** thì do file Agent của bạn quyết, không do Javis. Muốn bot tránh một chủ đề, không hứa hẹn thay bạn, không đổi vai khi bị dụ thì viết những điều đó vào Agent.

Lưu ý cách hiểu đúng: những giới hạn trên nằm ở **mức quyền trong mã nguồn**, không phải ở câu dặn trong prompt. Câu dặn có thể bị lời lẽ khôn khéo lách qua; mức quyền thì không, vì công cụ đơn giản là không được cấp cho lượt chạy đó. Mặt trái của cùng một sự thật: khi bạn **cấp** công cụ cho lượt đó, câu dặn trong Agent cũng không giữ nổi nó nữa.

## Bot gửi ảnh cho khách (từ 0.84.3)

Bot gửi được ảnh trên Telegram, Zalo cá nhân, Slack và WhatsApp, ở **mọi mức quyền**. Cách dùng: dặn trong file Agent khi nào gửi ảnh nào, ví dụ "khách hỏi mẫu áo thì gửi `![Mẫu áo](attachments/mau-ao.jpg)`". Agent chèn cú pháp ảnh đó vào câu trả lời, Javis gỡ nó khỏi câu chữ rồi gửi ảnh thật ngay sau tin chữ. Trong nhóm Zalo, tin chữ vẫn tag người đang hỏi.

Javis chỉ gửi khi đủ các điều kiện:

- Ảnh **nằm trong brain của chính bot** (đường dẫn tính từ gốc brain đó). Ảnh ở brain khác hay chỗ khác trên máy thì không.
- Đúng là ảnh (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`), có thật, không quá 10 MB. File tài liệu như PDF hay ghi chú `.md` thì không gửi.
- Tối đa 4 ảnh mỗi câu trả lời.

Ảnh không qua được điều kiện thì cú pháp ảnh ở lại nguyên trong câu chữ, để bạn thấy trong Hộp thư bot đã định gửi gì. Javis **không** tự đính kèm file nào bot vừa tạo ra: người đang lái bot là khách lạ, nên chỉ ảnh mà Agent chủ động gọi tên mới đi.

## Bot nói như người, không lộ trạng thái máy

Bot chuyên trách **không hiện một dòng trạng thái nào của Javis** cho người đang nhắn với nó. Đây là điểm khác hẳn bot Javis chính của bạn (bot đó vẫn hiện đầy đủ, xem [Telegram](11-telegram.md) - chủ máy thì cần nhìn thấy Javis đang chạy tới đâu).

Cụ thể, người nhắn với bot chuyên trách sẽ KHÔNG bao giờ thấy:

- tin "🤔 Javis đang xử lý…" và các bản cập nhật "⏳ ⚙ Đang gọi công cụ…" của nó
- câu "⏳ Đang xử lý câu trước. Gửi /stop để dừng rồi hỏi lại."
- dòng lỗi kỹ thuật kiểu "⚠ Lỗi: TimeoutError: ..."
- chữ "(không có nội dung)" khi một lượt trả về rỗng

Thay vào đó, trong lúc bot suy nghĩ thì Telegram hiện chấm **"đang nhập…"** ở đầu cuộc trò chuyện, đúng thứ một người thật để lại khi họ đang gõ. Lượt nào gãy thì bot xin lỗi bằng một câu bình thường và mời nhắn lại; lý do kỹ thuật vẫn được ghi đủ vào nhật ký bot và vẫn báo cho người trực nếu bạn có đặt.

**Nhắn thêm lúc bot đang trả lời thì không bị chặn.** Bot gom mấy câu đó lại, trả lời xong câu trước là trả lời tiếp một thể, giống hệt một người đọc nốt tin rồi mới đáp. Gom tối đa 5 tin cho mỗi cuộc trò chuyện để người lạ không spam làm phình bộ nhớ.

Một chỗ vẫn cố ý nói thẳng: khi có người gọi bot trong **nhóm bạn chưa cho phép**, bot nói đúng một câu một lần rằng nó chưa được bật cho nhóm này. Im hẳn ở đó thì bot trông như hỏng và bạn không có cách nào biết để đi bấm **Cho phép**.

## Giới hạn tần suất

Mỗi người bị giới hạn số lượt hỏi trong một giờ (mặc định 20, sửa được khi Sửa bot). Vượt thì bot lịch sự xin trả lời lại sau.

Cần thiết vì một người rảnh trong nhóm đủ đốt hết quota model của bạn trong một buổi chiều, và bạn chỉ biết khi nhìn hoá đơn.

## Xoá bot

Bấm **Xoá** trên thẻ. Bot ngừng trả lời ngay.

**Dữ liệu bộ phán xử của bot BỊ xoá** (nhật ký quyết định, ca đã học, bài học, hồ sơ vai): đó là chữ chat của khách nên không để mồ côi.

**Brain và Agent của nó KHÔNG bị xoá.** Brain có thể chứa cả tháng tài liệu bạn tự soạn, Agent có thể đang được bot khác hoặc workflow dùng. Muốn xoá thì xoá ở trang của chúng.

## Câu hỏi thường gặp

**Bot dùng model nào?** Model trong ô **Model** của chính Agent mà bot trỏ tới (Studio → Trợ lý → Cài đặt trợ lý). Ô đó để **Mặc định** thì bot chạy model chính ở trang Models. Thẻ bot trên trang Chatbot ghi sẵn model đang chạy, nên nhìn là biết. Đổi model là bot đổi theo, và cách nó làm việc không đổi - mọi bộ não đi cùng một đường.

Vì sao theo Agent chứ không theo model chính: bot vốn đã mượn nguyên đầu bài của Agent, nên model cũng phải là của Agent - không thì chọn một model rẻ cho trợ lý đối ngoại xong bot vẫn đốt model đắt, mà không có dấu hiệu nào. Nhà đã chọn bị gỡ key thì bot lui về model chính chứ không chết câm trước mặt khách.

**Bot có gọi được các nguồn dữ liệu tôi đã đấu không?** Mặc định là không - mức Chỉ đọc chỉ có tài liệu trong brain của nó. Nâng lên **Được ghi** thì có, và **Toàn quyền** thì có cả nhóm thao tác ra ngoài. Cân nhắc rằng người điều khiển là người nhắn cho bot; việc chỉ mình bạn cần thì hỏi Javis ở dashboard hoặc kênh Telegram riêng vẫn an toàn hơn.

**Bot ở mức Toàn quyền có nguy hiểm không?** Có, và đó là lý do Javis bắt tick đồng ý rồi hỏi lại thêm lần nữa. Nguy hiểm không nằm ở việc model làm bậy, mà ở chỗ **ai cũng nhắn cho bot được**: một câu dụ khéo là bot gọi công cụ thật, không hoàn tác được và không hỏi lại bạn. Chỉ dùng khi bạn kiểm soát được danh sách người nhắn vào.

**Đang chạy Toàn quyền mà thấy bất ổn thì làm gì ngay?** Bấm **Tắt** trên thẻ - có tác dụng trong vài giây, không cần khởi động lại Javis. Rồi bấm Sửa hạ mức xuống Chỉ đọc; hạ mức không hỏi lại gì cả. Xem bot đã làm gì ở **Nhật ký**, tab Hội thoại gần đây.

**Chạy nhiều bot cùng lúc được không?** Được. Mỗi bot một token, một tiến trình riêng. Trang Chatbot dựng sẵn cho việc đó.

**Hai bot dùng chung một Agent được không?** Được, và đôi khi hợp lý: cùng vai trò nhưng hai brain khác nhau cho hai nhóm người hỏi khác nhau. Ngược lại, hai bot dùng chung một token thì không, Javis chặn.

**Người ta gửi ảnh cho bot thì sao?** File gửi vào rơi xuống `inbox/khach/` trong brain của bot đó, tách riêng khỏi file của bạn, và không được tính là tài liệu để trả lời.

**Bot trả lời sai một câu, xem lại ở đâu?** Bấm Nhật ký, tab Hội thoại gần đây. Dòng nguồn dưới mỗi lượt cho biết nó lấy câu trả lời từ file nào, nên sửa đúng chỗ được ngay.

**Bot nói "chưa có thông tin" mà tài liệu rõ ràng có nói?** Thường là do file dài không chia tiêu đề, hoặc tài liệu dùng từ khác hẳn từ người ta hỏi (tài liệu ghi "hoàn trả", người hỏi gõ "đổi trả"). Thêm tiêu đề cho file, hoặc viết thêm cách gọi mà người ta hay dùng vào chính đoạn đó.

**Bot có nhớ người đã nhắn không?** Có, mỗi người một mạch hội thoại riêng trong brain của bot.

**Tôi thả bot vào nhóm, tag tên nó mà nó không trả lời, nhưng nhắn riêng thì được?** Gõ **`/id`** trong chính nhóm đó - bot sẽ trả lời và nói luôn nguyên nhân. Ba nguyên nhân cho ra đúng một triệu chứng này: nhóm chưa được bật (bấm **Cho phép nhóm này** trên thẻ bot), chế độ riêng tư của Telegram còn bật (xem mục [Chế độ riêng tư](#chế-độ-riêng-tư-của-telegram-đọc-mục-này-nếu-bot-im-trong-nhóm)), hoặc bot chưa hỏi được danh tính của chính nó (tắt bật lại bot). Nếu ngay cả `/id` cũng không có phản hồi thì bot đang không chạy - xem chấm trạng thái trên thẻ.

**Bot đặt "trả lời mọi tin" mà nó vẫn chỉ trả lời khi được gọi tên?** Chế độ riêng tư của Telegram còn bật, nó chặn từ phía Telegram nên Javis không nhìn thấy những tin đó. Tắt nó ở @BotFather (`/setprivacy` → Disable) hoặc cho bot làm quản trị viên nhóm, rồi tắt bật lại bot. Thẻ bot có nhắc sẵn khi rơi vào tình huống này.

**Tag bot trong nhóm Zalo mà bot im?** Kiểm theo thứ tự:

1. Bot đang bật, chấm trạng thái xanh, và kết nối Zalo còn đăng nhập ở trang Kết nối.
2. **Nhóm đã được cho phép chưa.** Xem hàng chờ trên thẻ bot, thấy nhóm thì bấm **Cho phép nhóm này**. Không thấy nhóm nào hiện lên thì vòng đọc chưa nhận được tin từ nhóm: mở Hộp thư xem tin nhóm có về không.
3. **Bot nhận tag theo tên.** Chữ sau "@" phải trùng nhãn của kết nối Zalo (trang Kết nối) hoặc tên hiển thị của nick. Lệch thì đổi nhãn kết nối cho đúng tên hiển thị. Chọn **Tự đánh giá** thì bot vẫn bắt được câu hỏi thuộc tài liệu dù không nhận ra tag.
4. Có người vừa nhắn tay bằng nick đó trong nhóm trong 10 phút thì bot nhường.

**Tắt Javis thì bot có chạy không?** Không. Bot chạy trong tiến trình Javis, nên máy/VPS phải bật. Bật lại Javis thì bot nào đang bật tự chạy lại.

## Xem thêm

- [Agents & Workflows](07-agents-va-workflows.md) - viết Agent làm bộ não cho bot.
- [Kênh Telegram](11-telegram.md) - bot Telegram cá nhân của bạn, khác hẳn bot ở đây.
- [Second Brain](13-second-brain-bo-nho-wiki.md) - tạo brain và nạp tài liệu cho bot đọc.
- [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md) - token được mã hoá thế nào.
