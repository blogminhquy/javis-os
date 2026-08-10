# Kênh Zalo Bot

Hỏi Javis ngay trên Zalo, không cần mở dashboard và không cần cài Telegram. Bạn nhắn cho một bot Zalo riêng như nhắn cho một người, Javis trả lời bằng chính bộ não và bộ nhớ đang chạy trên máy hoặc VPS của bạn.

Đây là kênh dùng **API chính thức** của Zalo, nên không có rủi ro khoá tài khoản.

## Đừng lẫn với hai thứ Zalo khác trong Javis

Javis có ba chỗ dính tới Zalo. Đọc bảng này một lần rồi khỏi phải đoán.

| | Trang | Là ai | Để làm gì |
|---|---|---|---|
| **Kênh Zalo Bot** (trang này) | Kênh | Một bot riêng | **Bạn** nhắn cho Javis |
| [Chatbot](25-chatbot.md) | Chatbot | Một bot riêng, đứng tên Agent | **Khách** nhắn cho Javis |
| [Zalo Agent MCP](12-zalo.md) | Kết nối | Chính tài khoản Zalo của bạn | Javis **thao tác thay bạn** |

Hai cái đầu dùng API chính thức, an toàn, nhưng chỉ thấy được thứ người ta nhắn thẳng cho bot. Cái thứ ba đăng nhập tài khoản thật của bạn nên đọc được hội thoại và nhắn cho bất kỳ ai, đổi lại tài khoản có thể bị hạn chế hoặc khoá.

Dùng cả ba cùng lúc cũng được, chúng không đụng nhau.

## Lấy bot token

1. Mở app Zalo, tìm Official Account **Zalo Bot Manager**.
2. Trong khung chat, chọn **Tạo bot**.
3. Đặt tên bot. Tên **bắt buộc mở đầu bằng chữ "Bot"**, ví dụ "Bot Javis Của Tôi".
4. Zalo gửi token về cho bạn bằng tin nhắn, dạng `123456789:abc-xyz`.

Token này **không hết hạn** cho tới khi bạn tự đặt lại trong Zalo Bot Manager. Giữ kín, ai có token là điều khiển được bot.

## Bật kênh

1. Mở dashboard, nhóm **Kết nối**, mục **Kênh**.
2. Kéo xuống thẻ **Zalo**.
3. Tích **Bật bot Zalo**, dán token vào ô Bot token.
4. **Ô "Chat ID được phép dùng" cứ để trống.** Bấm **Lưu & bật**.
5. Mở Zalo trên điện thoại, tìm đúng bot vừa tạo, nhắn cho nó một câu bất kỳ.
6. Bot đáp lại kèm một **mã ghép nối** gồm 4 chữ số.
7. Quay lại thẻ Zalo trên dashboard. Bạn sẽ thấy một khối **Đang chờ bạn cho phép** với tên Zalo của bạn và đúng mã đó. Bấm **Cho phép**.
8. Nhắn lại cho bot. Lần này Javis trả lời thật.

### Vì sao phải làm vòng vèo như vậy

Zalo không có công cụ nào để bạn tự tra id Zalo của chính mình, và id đó là một chuỗi như `6ede9afa66b88fe6d6a9` chứ không phải con số dễ đọc. Nên thay vì bắt bạn đi tìm nó, Javis đảo chiều: ai nhắn cho bot thì hiện lên dashboard kèm **tên Zalo thật**, bạn bấm một nút là xong.

Mã ghép nối để bạn chắc chắn đang cho phép đúng người khi có hai người trùng tên. Hỏi họ đọc mã trong tin bot vừa trả lời rồi đối chiếu.

### Ô Chat ID trống nghĩa là CHƯA AI được phép

Chỗ này Javis **cố ý làm khác Telegram**, đừng ngạc nhiên.

Bên [Telegram](11-telegram.md), để trống ô Chat ID nghĩa là ai tìm ra bot cũng dùng được, và tài liệu phải dặn bạn đừng để trống. Bên Zalo, để trống nghĩa là **chưa ai được phép cả**, mọi người nhắn tới đều rơi vào hàng chờ.

Nếu không làm vậy thì chính cái luồng hướng dẫn ở trên sẽ tạo ra một con bot mà bất kỳ ai cũng chạm được vào brain của bạn, trong khoảng thời gian từ lúc bạn bật bot tới lúc bấm Cho phép.

## Dùng được gì qua Zalo

Giống Telegram gần hết: hỏi số liệu qua MCP, đọc và ghi file trong brain, gọi skill, giao việc nền, đặt nhắc hẹn. Mọi engine đều dùng được vì công cụ đi qua MCP Hub chứ không gắn riêng vào bộ não nào.

Các lệnh gõ nhanh (`/status`, `/reset`, `/stop`, `/model`, `/brain`, `/notes`...) cũng dùng được, nhưng **Zalo không hiện menu lệnh** như Telegram nên bạn phải gõ tay.

Kết quả việc nền và nhắc hẹn đặt từ Zalo sẽ **tự về đúng khung chat Zalo đó**, không rơi sang Telegram.

### Ra lệnh bằng ghi âm (tin thoại)

Bấm giữ micro trong Zalo, nói, thả tay. Javis nghe câu đó thành chữ và làm y như bạn gõ tay.

**Cần API key của Groq** - chỗ Javis mượn để chuyển giọng nói thành chữ (model Whisper). Vào dashboard, trang **Models**, mục **Groq (API)**, dán key lấy ở [console.groq.com](https://console.groq.com) rồi lưu. Chưa đấu thì gửi tin thoại Javis sẽ nói rõ là cần dán key, không im lặng. Dán xong dùng được ngay, không cần tắt bật lại bot.

Đây là **cùng một key với kênh Telegram**: đấu một lần là hai kênh cùng nghe được.

Vài điều nên biết:

- **Việc có tác động ra ngoài thì Javis hỏi lại trước.** Gửi tin, đăng bài, đặt lịch, tiêu tiền, sửa file: Javis mở đầu bằng một dòng "Em nghe: ..." rồi chờ bạn xác nhận. Hỏi số liệu, tra cứu, tóm tắt thì làm thẳng.
- **File ghi âm không lưu vào brain.** Nghe xong lấy chữ là xong.
- Nghe không ra chữ, file quá lớn, hay Groq trả lỗi thì bot nói rõ lý do. Không có ngả nào im lặng.
- **Một rủi ro riêng của Zalo:** Zalo chưa công bố khuôn dữ liệu của tin thoại, nên có khả năng Javis không tìm thấy đường dẫn file ghi âm trong tin Zalo gửi về. Gặp ca đó, bot nói thẳng là không tải được file, và server ghi một dòng `[zalo voice] không tìm ra đường dẫn file thoại trong payload` kèm mẫu dữ liệu. Gửi dòng đó cho người phát triển là sửa được ngay. Bên Telegram không có rủi ro này vì khuôn dữ liệu đã công bố rõ.

## Bốn chỗ Zalo làm được ít hơn Telegram

Nói trước để bạn không tưởng là lỗi.

**Không có tin trạng thái.** Zalo không cho sửa và không cho xoá tin đã gửi, nên Javis không thể hiện dòng "đang gọi công cụ..." rồi cập nhật nó như bên Telegram. Trong lúc chờ bạn chỉ thấy chấm "đang nhập". Bù lại, câu trả lời có kèm một dòng vết ở cuối kiểu `⚙ pos_statistics · Read · 8s` cho biết lượt đó đã chạm vào công cụ nào.

**Không gửi được file tài liệu.** Zalo Bot chưa có API gửi tài liệu, nên PDF, bảng tính, .docx không đi qua kênh này được. Javis sẽ nói thẳng là chưa gửi được và đưa đường dẫn trong brain để bạn tự mở, chứ không im lặng nuốt file. Ảnh thì đang thử nghiệm.

**Trần 2000 ký tự một tin** (Telegram là 4096). Câu trả lời dài tự cắt thành nhiều tin liên tiếp.

**Không có nút bấm.** Khi Javis phải hỏi lại một tham số, nó hạ xuống dạng câu hỏi kèm danh sách đánh số, bạn nhắn lại con số.

## Nút Gửi test

Bấm **Gửi test** để bắn một tin thử tới mọi ID đã cho phép. Nó chứng minh token và Chat ID đúng, **không** chứng minh bot đang nhận tin. Muốn biết bot có nhận tin không thì đọc dòng trạng thái, phải là **Bot đang nhận tin**.

## Sự cố thường gặp

**Dán token xong báo "Token không hợp lệ (Zalo từ chối)".** Kiểm lại xem có phải bạn dán nhầm token Telegram không. Hai kênh dùng hai token hoàn toàn khác nhau.

**Nhắn cho bot mà không thấy gì.** Xem dòng trạng thái dưới thẻ Zalo. Nếu là "Bot đang nhận tin" mà vẫn im, kiểm khối **Đang chờ bạn cho phép**: nhiều khả năng bạn chưa bấm Cho phép cho chính mình.

**Bot đáp mãi một câu xin mã ghép nối.** Đúng là chưa được cho phép. Vào dashboard bấm Cho phép rồi nhắn lại.

**Bot báo lỗi hạn mức.** Zalo chưa công bố con số hạn mức nào. Gặp lỗi 429 thì Javis tự nghỉ một phút rồi thử lại, và hiện lỗi ra dòng trạng thái.

**Bot xanh nhưng không trả lời ai.** Xem log server, tìm dòng `[zalo getUpdates] khuôn phản hồi lạ`. Tài liệu Zalo chưa công bố khuôn phản hồi của `getUpdates` nên Javis nhận nhiều khuôn và kêu ra khi gặp khuôn chưa biết. Gửi dòng đó cho người phát triển là sửa được nhanh.

## Liên quan

- [Kênh Telegram](11-telegram.md) - kênh còn lại, nhiều tính năng hơn nhưng người Việt ít dùng.
- [Chatbot](25-chatbot.md) - bot cho KHÁCH nhắn, cũng chạy được trên Zalo.
- [Zalo Agent MCP](12-zalo.md) - đăng nhập tài khoản Zalo cá nhân để Javis thao tác thay bạn.
- [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md) - nơi sinh ra các báo cáo nền gửi về kênh này.
