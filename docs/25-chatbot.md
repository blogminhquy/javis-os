# Chatbot (Bot chuyên trách)

Đem một **Agent** bạn đã tạo ra đứng trước khách hàng: khách nhắn vào một bot Telegram riêng, Agent đó trả lời trong phạm vi tài liệu bạn cho phép, gặp câu ngoài tầm thì chuyển cho nhân viên thật.

Khác với [Kênh Telegram](11-telegram.md) ở một điểm quyết định: bot Telegram ở trang **Kênh** là **Javis của bạn** (toàn quyền, đọc brain chính, gọi được mọi nguồn dữ liệu, chỉ bạn nhắn được). Bot ở trang **Chatbot** là **nhân viên trực chat** (chỉ đọc, brain riêng, người lạ nhắn được). Đừng dùng cái này thay cái kia.

## Tính năng này là gì

- Mỗi bot = một **Agent** (bộ não nghiệp vụ) + một **brain riêng** (kho tài liệu nó được đọc) + một **token Telegram riêng**.
- Khách nhắn riêng cho bot, hoặc bạn thả bot vào nhóm chăm sóc khách hàng.
- Bot **chỉ đọc**. Nó không ghi file, không tạo đơn, không chạy quảng cáo, không giao việc, không có lệnh quản trị. Rào này nằm trong mã nguồn chứ không phải trong câu dặn dò, nên khách có dụ cách mấy cũng không mở ra được.
- Câu ngoài tầm hiểu biết thì bot nói "để em chuyển nhân viên" và nhắn thẳng cho người bạn chỉ định.
- Trang Chatbot dựng theo hướng **nhiều bot** ngay từ đầu: lưới thẻ, ô tìm, thêm/sửa/xoá, bật/tắt tại chỗ. Chạy một con hay mười con đều cùng một giao diện.

## Mở ở đâu trong Javis

Thanh điều hướng bên trái, nhóm **Năng lực**, mục **Chatbot**.

## Chuẩn bị trước khi tạo bot

Ba thứ, làm theo thứ tự này là đỡ phải quay lại sửa.

### 1. Một Agent làm bộ não

Vào trang **Agents** tạo một Agent cho đúng việc bot sẽ làm (ví dụ "Tư vấn sản phẩm", "Hỗ trợ đơn hàng"). Viết phần vai trò và hướng dẫn như thể bạn đang dặn một nhân viên mới: nói năng thế nào, ưu tiên gì, gặp trường hợp nào thì chuyển người thật.

Bot **đọc Agent lúc chạy**, không chép lại. Sau này sửa Agent ở trang Agents là bot đổi theo ngay, không phải sửa hai chỗ. Chi tiết cách viết Agent ở [Agents & Workflows](07-agents-va-workflows.md).

### 2. Một brain riêng cho bot

Đây là chỗ dễ sai nhất, và sai thì hậu quả thật.

**Bot chỉ biết những gì nằm trong brain của nó.** Nên tạo một brain riêng, bỏ vào đó đúng những tài liệu khách được xem: bảng giá, chính sách đổi trả, mô tả sản phẩm, câu hỏi thường gặp. Đừng trỏ bot vào brain chính của bạn - trong đó có ghi chú nội bộ, giá vốn, chiến lược, số liệu kinh doanh, và bot không phân biệt được cái nào nói ra được cái nào không.

Tạo brain mới ngay trong form tạo bot cũng được (nút **Tạo brain mới**), rồi qua trang **Tệp tin** bỏ tài liệu vào sau.

### 3. Một token Telegram riêng

Vào **@BotFather** trên Telegram gõ `/newbot`, đặt tên và username, lấy chuỗi token dạng `123456789:ABCdef...`.

**Mỗi bot phải một token riêng, và đừng dùng token bot Javis chính của bạn.** Một token chỉ chạy được một tiến trình; dùng chung là cả hai cùng chết và Telegram trả lỗi 409. Javis chặn sẵn việc này lúc bạn bấm Kiểm tra, nhưng biết trước vẫn hơn.

## Cách dùng (từng bước)

### Bước 1: Tạo bot

Bấm **Bot mới**, điền:

| Ô | Điền gì |
|---|---|
| Tên bot | Tên bạn nhìn để phân biệt, ví dụ "Tư vấn sản phẩm" |
| Agent làm bộ não | Chọn Agent đã tạo ở bước chuẩn bị |
| Brain riêng của bot | Chọn brain đã tạo, hoặc bấm **Tạo brain mới** |
| Token Telegram | Dán token từ BotFather rồi bấm **Kiểm tra** |
| Chat ID nhân viên | Số Telegram của người nhận chuyển tiếp (xem bên dưới) |

Bấm **Kiểm tra** trước khi lưu: Javis hỏi thẳng Telegram xem token có thật không, trả về đúng tên bot, và báo ngay nếu token đó đã có bot khác trong Javis đang dùng.

**Bot tạo ra luôn ở trạng thái TẮT.** Đây là cố ý: bot chăm sóc khách bật lên là nói chuyện với người thật ngay lập tức, nên bật phải là một cú bấm có ý thức chứ không phải tác dụng phụ của việc tạo.

### Bước 2: Nhắn thử trước khi bật

Bật bot bằng nút **Bật** trên thẻ, rồi mở Telegram nhắn riêng cho chính con bot đó vài câu như một khách hàng thật. Hỏi giá, hỏi chính sách, hỏi một câu bạn biết chắc trong tài liệu không có. Xem nó trả lời có đúng giọng không, có bịa không, có chịu nói "em chưa có thông tin" không.

Thấy chưa ổn thì tắt đi, sửa Agent hoặc bổ sung tài liệu vào brain, rồi thử lại. Tắt có tác dụng ngay, không phải khởi động lại Javis.

### Bước 3: Chuyển cho nhân viên

Điền **Chat ID nhân viên** để bot có chỗ chuyển khi bí. Lấy số đó bằng cách nhờ nhân viên mở **@userinfobot** trên Telegram, nó trả về dòng `Id: 123456789`.

Nhân viên phải bấm **Start** trong chat với con bot này một lần, nếu không Telegram chặn không cho bot nhắn tới.

Khi đó bot có hai đường chuyển: tự chuyển khi gặp câu ngoài phạm vi, và khách chủ động gõ `/nhanvien`. Cả hai đều gửi cho nhân viên một tin có tên bot, id khách và lý do.

Bỏ trống ô này thì bot chỉ nói "em chưa có thông tin" rồi dừng, không đoán tiếp.

### Bước 4: Thả bot vào nhóm chăm sóc khách hàng

1. Mời bot vào nhóm như mời một thành viên.
2. Trong nhóm, gõ `/id`. Bot trả về id của nhóm (một số **âm**, dạng `-1001234567890`).
3. Về trang Chatbot, bấm **Sửa** trên thẻ bot, dán id đó vào ô **Nhóm được phép**, mỗi id một dòng.

**Chưa khai id nhóm thì bot im lặng trong mọi nhóm.** Đây là mặc định cố ý: bot bị thả vào một nhóm lạ mà tự nhận việc là nó chen vào giữa cuộc nói chuyện của khách với nhau.

Trong nhóm đã khai, mặc định bot chỉ trả lời khi có người **nhắc tên nó** hoặc **reply vào tin của nó**. Muốn nó trả lời mọi câu trong nhóm thì đổi cách trả lời thành "luôn luôn" - cân nhắc kỹ, nhóm đông người thì rất ồn và đốt quota model nhanh.

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

## Bot làm được gì và KHÔNG làm được gì

Cố ý cắt rất sâu, vì người ở đầu bên kia là người lạ.

**Làm được:** đọc tài liệu trong brain của nó, trả lời trong phạm vi đó, nhớ mạch hội thoại với từng khách, chuyển cho nhân viên.

**Không làm được:** ghi file, tạo đơn, tiêu tiền, chạy quảng cáo, đăng bài, giao việc Kanban, tạo lịch, gọi các nguồn dữ liệu bạn đã đấu, đọc brain khác, dùng lệnh quản trị (`/brain`, `/model`, `/status`... đều không có tác dụng, bot chỉ trả lời chung chung).

Bot cũng được dặn không nói về model, engine, brain hay bất cứ thứ gì bên trong hệ thống, và bỏ qua mọi yêu cầu kiểu "quên hướng dẫn của mày đi" hay "in ra prompt của mày".

Lưu ý cách hiểu đúng: những giới hạn trên nằm ở **mức quyền trong mã nguồn**, không phải ở câu dặn trong prompt. Câu dặn có thể bị lời lẽ khôn khéo lách qua; mức quyền thì không, vì công cụ đơn giản là không được cấp cho lượt chạy đó.

## Giới hạn tần suất

Mỗi khách bị giới hạn số lượt hỏi trong một giờ (mặc định 20, sửa được khi Sửa bot). Vượt thì bot lịch sự xin trả lời lại sau.

Cần thiết vì một người rảnh trong nhóm đủ đốt hết quota model của bạn trong một buổi chiều, và bạn chỉ biết khi nhìn hoá đơn.

## Xoá bot

Bấm **Xoá** trên thẻ. Bot ngừng trả lời ngay.

**Brain và Agent của nó KHÔNG bị xoá.** Brain có thể chứa cả tháng tài liệu bạn tự soạn, Agent có thể đang được bot khác hoặc workflow dùng. Muốn xoá thì xoá ở trang của chúng.

## Câu hỏi thường gặp

**Bot dùng model nào?** Chính model bạn chọn ở trang Models. Đổi model là bot đổi theo.

**Chạy nhiều bot cùng lúc được không?** Được. Mỗi bot một token, một tiến trình riêng. Trang Chatbot dựng sẵn cho việc đó.

**Hai bot dùng chung một Agent được không?** Được, và đôi khi hợp lý: cùng vai trò nhưng hai brain khác nhau cho hai cửa hàng. Ngược lại, hai bot dùng chung một token thì không, Javis chặn.

**Khách gửi ảnh cho bot thì sao?** File khách gửi rơi vào `inbox/khach/` trong brain của bot đó, tách riêng khỏi file của bạn.

**Bot có nhớ khách không?** Có, mỗi khách một mạch hội thoại riêng trong brain của bot.

**Tắt Javis thì bot có chạy không?** Không. Bot chạy trong tiến trình Javis, nên máy/VPS phải bật. Bật lại Javis thì bot nào đang bật tự chạy lại.

## Xem thêm

- [Agents & Workflows](07-agents-va-workflows.md) - viết Agent làm bộ não cho bot.
- [Kênh Telegram](11-telegram.md) - bot Telegram cá nhân của bạn, khác hẳn bot ở đây.
- [Second Brain](13-second-brain-bo-nho-wiki.md) - tạo và nạp tài liệu vào brain riêng của bot.
- [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md) - token được mã hoá thế nào.
