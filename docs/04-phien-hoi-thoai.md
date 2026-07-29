# Phiên hội thoại

Mọi cuộc trò chuyện bạn nói với Javis đều được lưu lại tự động. Trang này hướng dẫn cách xem lại, tìm kiếm, đổi tên, xoá và mở tiếp một cuộc trò chuyện cũ, kể cả cuộc đã diễn ra từ nhiều ngày trước.

Nếu bạn chưa quen với màn hình chat, đọc trước [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md).

## Tính năng này là gì

Javis tự lưu lại từng lượt hỏi và trả lời vào một cơ sở dữ liệu trên máy của bạn. Nhờ vậy bạn không mất nội dung khi tắt trình duyệt hay khởi động lại máy chủ. Cụ thể bạn có thể:

- Xem danh sách các cuộc trò chuyện cũ, mới nhất nằm trên đầu.
- Tìm kiếm toàn văn: gõ một từ khoá và Javis tìm trong nội dung của mọi cuộc trò chuyện.
- Mở lại một cuộc cũ và trò chuyện tiếp đúng mạch cũ.
- Đổi tên cho dễ nhớ.
- Xoá cuộc không cần nữa.

Một điểm quan trọng: các cuộc trò chuyện được gắn theo "bộ não" (vault) đang chọn. Khi bạn đổi bộ não ở thanh chọn vault, danh sách lịch sử cũng đổi theo để chỉ hiện các cuộc thuộc bộ não đó. Xem thêm cách chọn bộ não ở [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md).

## Nơi lưu dữ liệu

Toàn bộ lịch sử nằm trong một tệp duy nhất tên `conversations.db`.

| Mục | Giá trị mặc định | Ghi chú |
|---|---|---|
| Tên tệp | `conversations.db` | Định dạng SQLite |
| Thư mục | Thư mục `server/` của Javis | Cùng chỗ với `settings.json` |
| Biến môi trường đổi vị trí tệp | `JAVIS_SESSIONS_DB` | Trỏ tới đường dẫn tệp `.db` khác |
| Biến môi trường đổi thư mục gốc | `JAVIS_STATE_DIR` | Đổi cả thư mục chứa trạng thái |

Nếu bạn muốn dời tệp lịch sử sang chỗ khác (ví dụ ổ dữ liệu riêng), đặt biến `JAVIS_SESSIONS_DB` trong tệp cấu hình. Chi tiết cách chỉnh biến môi trường xem [Cấu hình .env](16-cau-hinh-env.md).

Mỗi cuộc trò chuyện lưu kèm: tên (title), bộ não, engine đang dùng, model, kênh sinh ra nó, số tin nhắn, thời gian tạo và thời gian cập nhật gần nhất. Từng lượt hỏi và đáp lưu riêng để có thể tìm kiếm và mở lại chính xác.

## Cuộc trò chuyện đến từ Telegram

Danh sách này không chỉ có các cuộc bạn mở trên web. Những gì bạn nhắn với Javis qua **Telegram** cũng được lưu vào đây và mang nhãn **TG** trong danh sách, nên ngồi máy tính bạn vẫn đọc lại và tìm kiếm được cuộc đã nói lúc đang đi đường.

Vì trên Telegram gần như không ai bấm bắt đầu cuộc mới, Javis tự cắt sang cuộc mới khi bạn nghỉ quá 12 tiếng hoặc khi cuộc hiện tại đã dài khoảng 100 lượt. Việc cắt này chỉ để bản lưu dễ đọc, không làm Javis quên mạch trong lúc bạn đang trò chuyện trên Telegram. Các cuộc Telegram cũ hơn 30 ngày được tự cất vào kho lưu nên không hiện ở danh sách mặc định, nhưng vẫn tìm được bằng ô tìm kiếm. Chi tiết ở [Telegram](11-telegram.md).

## Mở ở đâu trong Javis

Lịch sử giờ nằm ở **cột trái của chat phóng to** (chat workspace), giống bố cục Claude/Cowork:

1. Bấm nút **🕘 Lịch sử** ở góc trên bên phải màn hình (hoặc bấm nút **⛶** trên khung Hội thoại để phóng to chat, rồi bấm **🕘 Lịch sử** ở góc trái thanh tiêu đề).
2. Khung chat mở rộng gần hết màn hình; cột bên trái là **sidebar Lịch sử** gồm: nút **＋ Hội thoại mới** trên cùng, ô tìm kiếm, và danh sách các cuộc trò chuyện nhóm theo thời gian (**Hôm nay / Hôm qua / 7 ngày qua / Cũ hơn**).
3. Cuộc đang mở được tô sáng trong danh sách để bạn biết mình đang ở đâu.

Ẩn/hiện sidebar: bấm nút **🕘 Lịch sử** trên thanh tiêu đề của khung chat (trạng thái được nhớ cho lần sau). Trên màn hình hẹp (dưới ~900px), sidebar tự ẩn và mở dạng ngăn kéo nổi; nhấn **Esc** đóng ngăn kéo trước, nhấn lần nữa mới thu nhỏ chat.

## Cách dùng (từng bước)

### Xem lại danh sách cuộc trò chuyện

1. Mở chat phóng to (nút **⛶** hoặc **🕘 Lịch sử**).
2. Danh sách bên trái hiện các cuộc thuộc bộ não đang chọn, nhóm theo thời gian, cuộc cập nhật gần nhất nằm trên cùng (tối đa 100 cuộc).
3. Mỗi dòng cho biết: tên cuộc trò chuyện, giờ (hoặc ngày), engine đã dùng và số tin nhắn (ví dụ `12 tin`).
4. Nếu chưa có cuộc nào, sidebar hiện dòng "Chưa có hội thoại nào."

Cuộc chưa được đặt tên sẽ hiện tạm câu hỏi đầu tiên của bạn làm tên. Javis cũng tự đặt tên rút gọn từ câu hỏi đầu (khoảng 48 ký tự) ngay sau lượt trả lời đầu tiên.

### Tìm kiếm toàn văn

1. Mở sidebar Lịch sử (trong chat phóng to).
2. Bấm vào ô có chữ mờ **Tìm trong mọi hội thoại…** ở phía trên.
3. Gõ từ khoá. Javis tự tìm sau khi bạn ngừng gõ một chút, không cần bấm Enter.
4. Kết quả hiện các dòng khớp, kèm đoạn trích ngắn quanh từ khoá; phần trùng từ khoá được tô đậm màu vàng để dễ nhận ra.
5. Mỗi kết quả cho biết vai trò của tin nhắn (bạn hỏi hay Javis trả lời) và thời điểm.
6. Bấm vào một kết quả để mở thẳng cuộc trò chuyện chứa đoạn đó.
7. Xoá hết chữ trong ô tìm kiếm để quay lại danh sách đầy đủ.

Nếu không có dòng nào khớp, sidebar hiện "Không tìm thấy." Tìm kiếm chỉ quét các cuộc thuộc bộ não đang chọn. Muốn tìm ở bộ não khác, đổi bộ não trước rồi tìm lại.

### Mở lại và trò chuyện tiếp một cuộc cũ

1. Trong danh sách (hoặc kết quả tìm kiếm), bấm vào cuộc bạn muốn mở.
2. Khung chat bên phải nạp lại NGAY toàn bộ lượt hỏi và đáp cũ, dòng đó được tô sáng trong danh sách.
3. Gõ câu mới như bình thường. Javis nối tiếp đúng mạch cuộc cũ, không bắt đầu lại từ đầu.

Với engine Claude Code CLI, Javis nhớ cả phiên gốc của CLI để tiếp tục đúng ngữ cảnh công cụ đã dùng. Với các engine gọi qua API (ví dụ OpenRouter, OpenAI, Anthropic API), Javis nạp lại các lượt cũ từ cơ sở dữ liệu để giữ mạch. Xem thêm về engine ở [Models & engine](10-models-va-engine.md).

### Bắt đầu một cuộc trò chuyện mới

1. Mở sidebar Lịch sử.
2. Bấm nút **＋ Hội thoại mới** trên cùng.
3. Khung chat được dọn trống, bạn bắt đầu cuộc mới. Cuộc mới chỉ được lưu vào lịch sử sau khi bạn gửi câu đầu tiên.

### Đổi tên một cuộc trò chuyện

1. Trong danh sách, đưa chuột vào dòng cuộc cần đổi tên. Hai biểu tượng nhỏ hiện ra bên phải.
2. Bấm biểu tượng cây bút **✎** (chú thích khi rê chuột: "Đổi tên").
3. Một ô nhập hiện ra với dòng "Tên mới cho hội thoại:". Gõ tên mới rồi bấm OK.
4. Danh sách tự cập nhật tên vừa đặt.

Tên tối đa khoảng 120 ký tự, phần thừa sẽ bị cắt bớt. Nếu bạn bấm Huỷ, tên giữ nguyên.

### Xoá một cuộc trò chuyện

1. Trong danh sách, đưa chuột vào dòng cuộc cần xoá.
2. Bấm biểu tượng thùng rác **🗑** (chú thích khi rê chuột: "Xoá").
3. Một hộp xác nhận hiện ra: "Xoá hội thoại này?". Bấm OK để xoá, bấm Huỷ để giữ lại.
4. Cuộc và toàn bộ tin nhắn của nó bị xoá khỏi cơ sở dữ liệu, danh sách tự cập nhật.

Lưu ý: xoá là vĩnh viễn, không có thùng rác khôi phục. Cân nhắc kỹ trước khi xoá cuộc quan trọng.

## Bảng thao tác nhanh

| Thao tác | Nút / phím | Vị trí |
|---|---|---|
| Mở chat phóng to + lịch sử | `🕘 Lịch sử` (góc phải màn hình) hoặc `⛶` | Khung Hội thoại |
| Ẩn/hiện sidebar lịch sử | `🕘 Lịch sử` | Thanh tiêu đề khung chat phóng to |
| Thu nhỏ chat | `✕ Thu nhỏ` hoặc phím `Esc` | Thanh tiêu đề |
| Tìm toàn văn | Ô "Tìm trong mọi hội thoại…" | Đầu sidebar |
| Cuộc mới | `＋ Hội thoại mới` | Đầu sidebar |
| Mở lại cuộc | Bấm vào dòng | Danh sách (cuộc đang mở được tô sáng) |
| Đổi tên | `✎` | Hiện khi rê chuột vào dòng |
| Xoá | `🗑` | Hiện khi rê chuột vào dòng |

## Mẹo

- Đặt tên rõ ràng cho các cuộc quan trọng ngay sau khi làm xong, để sau này tìm nhanh mà không phải đọc lại từng cuộc.
- Muốn giữ mạch cho một chủ đề dài, hãy mở lại đúng cuộc cũ thay vì bấm **+ Mới**. Như vậy Javis vẫn nhớ ngữ cảnh trước đó.
- Khi làm một việc mới hoàn toàn không liên quan, bấm **+ Mới** để Javis không lẫn ngữ cảnh cũ vào câu trả lời.
- Tìm kiếm quét cả nội dung tin nhắn, nên bạn có thể tìm theo một con số, một tên khách hàng hay một cụm từ đã trao đổi, không chỉ theo tên cuộc.
- Danh sách và tìm kiếm luôn theo bộ não đang chọn. Nếu không thấy cuộc cần tìm, kiểm tra xem bạn có đang ở đúng bộ não hay không.

## Đồng bộ khi đổi máy

Lịch sử hội thoại nằm trong tệp `conversations.db` trên chính máy chủ chạy Javis. Tệp này không tự đồng bộ lên đám mây và không tự chuyển sang máy khác.

- Nếu bạn chuyển Javis sang máy hoặc VPS mới mà muốn giữ lịch sử, hãy sao chép tệp `conversations.db` (trong thư mục `server/`) sang cùng vị trí ở máy mới, làm khi máy chủ đang tắt để tránh tệp đang mở.
- Nếu bạn không sao chép tệp, máy mới sẽ bắt đầu với lịch sử trống. Đây là hành vi bình thường, không phải lỗi.
- Không nên mở cùng một tệp `conversations.db` từ hai máy chủ chạy song song, vì có thể gây tranh chấp ghi dữ liệu.
- Khi sao lưu định kỳ, chỉ cần sao lưu tệp `conversations.db` là đủ để giữ toàn bộ lịch sử trò chuyện.

## Sự cố thường gặp

**Bảng lịch sử trống dù trước đó có nhiều cuộc.**
Nhiều khả năng bạn đang ở một bộ não khác. Danh sách chỉ hiện cuộc thuộc bộ não đang chọn. Đổi lại đúng bộ não rồi mở bảng lần nữa.

**Bấm mở bảng nhưng hiện "Lỗi tải danh sách."**
Máy chủ Javis có thể chưa chạy hoặc vừa khởi động lại. Kiểm tra máy chủ đang chạy ở cổng mặc định (7777) rồi thử lại. Xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

**Tìm kiếm báo "Không tìm thấy" dù chắc chắn đã nói câu đó.**
Kiểm tra bạn có đang ở đúng bộ não chứa cuộc đó không. Nếu vẫn không ra, thử từ khoá ngắn hơn hoặc một từ đơn giản hơn thay vì cả câu dài.

**Mở lại cuộc cũ nhưng Javis không nhớ ngữ cảnh trước.**
Với engine Claude Code CLI, khả năng nhớ đầy đủ phụ thuộc vào phiên gốc còn được lưu hay không. Với engine API, Javis nạp lại các lượt cũ từ cơ sở dữ liệu; nếu cuộc quá dài, phần rất cũ có thể bị lược bớt để vừa dung lượng. Trong trường hợp đó, nhắc lại ngắn gọn thông tin quan trọng trong câu hỏi mới.

**Lỡ xoá nhầm một cuộc.**
Xoá là vĩnh viễn, không khôi phục được từ giao diện. Cách phòng ngừa duy nhất là sao lưu tệp `conversations.db` định kỳ (xem mục "Đồng bộ khi đổi máy").

**Đổi tên xong nhưng tên bị cắt ngắn.**
Tên cuộc trò chuyện giới hạn khoảng 120 ký tự. Nếu bạn nhập dài hơn, phần thừa bị bỏ. Hãy đặt tên ngắn gọn, súc tích.
