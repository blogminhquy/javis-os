# Trò chuyện & giọng nói

Đây là màn hình chính của Javis OS: quả cầu tri thức 3D ở giữa, khung hội thoại bên phải, số liệu kinh doanh bên trái. Bạn ra lệnh cho Javis bằng cách gõ chữ hoặc nói, và Javis trả lời bằng chữ kèm đọc ra tiếng.

Nếu chưa cài đặt xong lần đầu, xem [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md) trước.

## Tính năng này là gì

Một chỗ duy nhất để làm việc với Javis:

- Gõ tin nhắn như chat bình thường.
- Nói bằng giọng, Javis nghe rồi tự gửi khi bạn ngừng nói.
- Javis trả lời bằng chữ, đồng thời đọc thành tiếng bằng giọng Việt.
- Đính kèm file hoặc ảnh vào tin nhắn để Javis đọc.
- Xem quả cầu tri thức phản ứng theo âm thanh (sáng lên khi nghe / khi đọc).

Câu trả lời được xử lý bởi bộ não Claude Code chạy nền. Trong lúc Javis suy nghĩ, một thanh trạng thái nhỏ hiện các bước Javis đang làm (gọi công cụ, đọc dữ liệu...).

## Mở ở đâu trong Javis

Màn hình này chính là mục **Javis (3D)** trên thanh điều hướng bên trái, cũng là màn hình mặc định khi bạn mở dashboard (mặc định ở cổng 7777). Không cần bấm gì thêm, mở trang lên là đã ở đây.

Các khu vực trên màn hình:

| Khu vực | Vị trí | Nội dung |
|---|---|---|
| SỐ LIỆU KINH DOANH | Cột trái | Các thẻ số liệu (doanh thu, đơn...) |
| Quả cầu 3D + trạng thái | Chính giữa | Đồ thị tri thức, dòng chữ trạng thái (SẴN SÀNG, ĐANG NGHE...) |
| HỘI THOẠI | Cột phải | Lịch sử chat với Javis |
| Thanh nhập liệu | Dưới cùng | Nút mic, nút kẹp file, ô gõ chữ, nút gửi |

## Cách dùng (từng bước)

### Gõ chữ để hỏi

1. Bấm vào ô nhập ở dưới cùng (chỗ ghi "Nói với Javis, gõ ở đây, hoặc kéo/dán file vào...").
2. Gõ câu hỏi.
3. Nhấn phím **Enter** để gửi. Muốn xuống dòng trong cùng một tin nhắn thì nhấn **Shift + Enter**.
4. Hoặc bấm nút gửi (hình mũi tên) ở góc phải thanh nhập.

Câu trả lời của Javis hiện dần ở cột HỘI THOẠI bên phải, chữ chạy ra theo thời gian thực.

### Nói bằng giọng - giữ phím Cách

Cách nhanh nhất để nói một câu:

1. Đảm bảo con trỏ **không** đang nằm trong ô gõ chữ hay ô nhập nào (nếu đang gõ thì phím Cách sẽ ra dấu cách chứ không bật mic).
2. **Giữ phím Cách (Space)**. Dòng chữ giữa màn hình đổi thành **ĐANG NGHE**, nút mic sáng lên.
3. Nói câu của bạn. Chữ bạn nói hiện ngay dưới trạng thái để bạn thấy Javis nghe đúng chưa.
4. **Thả phím Cách** ra. Javis tự gửi toàn bộ câu vừa nói và bắt đầu trả lời.

Lần đầu bấm mic, trình duyệt sẽ hỏi quyền dùng micro. Bấm cho phép. Nếu từ chối, Javis không nghe được và sẽ báo "Anh cần cấp quyền microphone cho trang này.".

### Nói bằng giọng - bấm nút mic (chế độ rảnh tay)

Nút mic (hình micro to, bên trái thanh nhập) bật **chế độ luôn nghe**, tiện khi bạn không muốn giữ phím:

1. Bấm nút mic một lần. Trạng thái đổi thành **ĐANG NGHE • LUÔN** và nút mic sáng.
2. Cứ nói tự nhiên. Khi bạn ngừng nói một chút (khoảng 1,5 giây im lặng), Javis tự chốt câu và gửi đi.
3. Sau khi trả lời xong, Javis tự bật mic nghe lại, không cần bạn bấm.
4. Muốn tắt chế độ này: bấm lại nút mic, hoặc nhấn phím **Esc**.

Trong chế độ rảnh tay, khi bạn bắt đầu nói thì Javis tự ngắt phần nó đang đọc để lắng nghe, nên bạn có thể chen ngang bất cứ lúc nào.

### Nghe Javis trả lời bằng giọng

Mặc định Javis **đọc thành tiếng** mọi câu trả lời bằng giọng Việt (công nghệ Edge TTS trên máy chủ). Quả cầu 3D sáng theo nhịp giọng đọc.

Bật/tắt đọc bằng giọng, có 2 chỗ làm cùng một việc:

- Nút hình **loa** ở góc trên phải (tên gợi ý khi rê chuột: "Bật/tắt giọng Javis"). Loa gạch chéo = đang tắt tiếng.
- Vào **Cài đặt → Giọng nói, thương hiệu & truy cập**, gạt công tắc **"Đọc trả lời bằng giọng"**.

Hai chỗ này đồng bộ với nhau và ghi nhớ lựa chọn sau khi tải lại trang, nên bạn chỉ cần đặt một lần.

### Chọn giọng đọc và tốc độ

Trong **Cài đặt → Giọng nói, thương hiệu & truy cập** có bảng chọn giọng:

| Tuỳ chọn | Giá trị | Ghi chú |
|---|---|---|
| Giọng đọc | **Ngọc Thu** | Nữ, tự nhiên và ấm áp (mặc định; mã Edge: `vi-VN-HoaiMyNeural`) |
| Giọng đọc | **Nam Minh** | Nam, trầm (mã Edge: `vi-VN-NamMinhNeural`) |
| Tốc độ | Thanh trượt 0.70× đến 1.80× | Mặc định 1.10× |
| Ngôn ngữ nghe | **Tiếng Việt** (vi-VN) | Mặc định |
| Ngôn ngữ nghe | **Tiếng Anh** (en-US) | Dùng khi bạn nói toàn tiếng Anh |

Các bước:

1. Chọn Ngọc Thu hoặc Nam Minh.
2. Kéo thanh **TỐC ĐỘ** để chỉnh nhanh/chậm; số bên cạnh hiện tốc độ hiện tại (ví dụ 1.10×).
3. Bấm **▶ Nghe thử** để nghe một câu chào mẫu bằng giọng vừa chọn.
4. "Ngôn ngữ nghe" là ngôn ngữ Javis dùng để nhận diện lời bạn nói, khác với giọng đọc trả lời. Để mặc định Tiếng Việt trừ khi bạn quen nói tiếng Anh.

Mọi lựa chọn giọng, tốc độ, ngôn ngữ nghe đều được ghi nhớ cho lần sau.

### Gửi file kèm trong chat

Bạn có thể đưa file hoặc ảnh vào tin nhắn để Javis đọc. Ba cách:

1. Bấm nút **kẹp giấy** (bên cạnh nút mic) rồi chọn file. Có thể chọn nhiều file.
2. **Kéo - thả** file từ máy vào cửa sổ Javis (một lớp phủ hiện lên báo chỗ thả).
3. **Dán ảnh** trực tiếp bằng Ctrl + V (tiện khi bạn vừa chụp màn hình).

File hiện thành thẻ nhỏ phía trên thanh nhập. Đợi thẻ báo tải xong, sau đó gõ hoặc nói yêu cầu rồi gửi như bình thường. Bấm dấu ✕ trên thẻ để bỏ file khỏi tin nhắn.

Quan trọng về cách Javis xử lý file:

- **Mặc định: chỉ đọc.** Javis đọc nội dung file (ảnh thì xem và mô tả) rồi trả lời, **không** tự lưu vào đâu.
- **Chỉ lưu khi bạn yêu cầu rõ.** Muốn Javis cất file vào bộ nhớ (Second Brain), hãy nói rõ trong tin nhắn, ví dụ "lưu vào source", "ingest cái này", hoặc "ghi vào second brain". Khi đó Javis mới chuyển file thành ghi chú và lưu vào thư mục Sources của vault. Xem thêm [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md) và [Quản lý tệp tin](05-quan-ly-tep-tin.md).

### Dừng khi Javis đang trả lời

Khi Javis đang suy nghĩ hoặc đang đọc, nút gửi ở thanh nhập biến thành **nút dừng** (hình vuông). Có 2 cách ngắt:

1. Bấm **nút dừng** (hình vuông) trên thanh nhập.
2. Nhấn phím **Esc**.

Cả hai đều ngắt lệnh đang chạy và dừng đọc ngay lập tức, trả trạng thái về SẴN SÀNG. Riêng phím Esc còn tắt luôn chế độ rảnh tay nếu đang bật.

### Phóng to khung chat thành không gian làm việc (chat workspace)

Khi làm việc lâu trong chat, hãy phóng to nó thành một không gian làm việc thật sự:

1. Bấm nút **⛶** ở góc mục HỘI THOẠI (hoặc nút **🕘 Lịch sử** góc trên phải màn hình). Khung chat mở rộng gần hết màn hình: cột trái là **lịch sử hội thoại** (mở lại/tìm/đổi tên/xoá phiên cũ - xem [Phiên hội thoại](04-phien-hoi-thoai.md)), cột phải là nội dung chat căn giữa cho dễ đọc, ô nhập cao hơn để gõ dài.
2. Thu nhỏ lại: bấm nút **✕ Thu nhỏ (Esc)** ở đầu lớp nổi, hoặc nhấn phím **Esc**.

Vài tiện ích trong khung chat (cả khi phóng to lẫn thu nhỏ):

- Rê chuột vào câu trả lời của Javis sẽ thấy nút **⧉** để copy cả tin nhắn; mỗi khối code cũng có nút **⧉ Copy** riêng ở góc.
- Tin nhắn dài của bạn được thu gọn sau 10 dòng, bấm **Xem thêm** để mở.
- Khi bạn đang cuộn lên đọc lại mà Javis trả lời tiếp, khung chat KHÔNG giật xuống; một nút **↓ Tin mới** hiện ở đáy để bấm nhảy xuống khi sẵn sàng.
- Gõ nhiều dòng bằng **Shift+Enter** (Enter để gửi); dán ảnh từ clipboard hoặc kéo thả file vào bất cứ đâu trong khung chat để đính kèm.

## Hỏi số liệu kinh doanh

Bảng thẻ số liệu cố định ở cột trái đã được gỡ (từ bản 0.9.165). Trước đây mỗi lần mở dashboard là Javis lại tự chạy một lượt quét các nguồn đã kết nối để đắp bảng đó, tốn hạn mức mà phần lớn thời gian không ai nhìn tới.

Giờ muốn xem số thì cứ hỏi thẳng trong chat ("doanh thu hôm nay thế nào", "so với tuần trước"). Javis gọi đúng nguồn đang đấu (POS, kênh, quảng cáo...) và trả lời bằng lời, nên chỉ chạy khi bạn thật sự cần. Chi tiết về nguồn số liệu xem [MCP & số liệu kinh doanh](09-mcp-va-so-lieu.md).

## Ý nghĩa dòng chữ trạng thái giữa màn hình

Dòng chữ ngay dưới quả cầu cho biết Javis đang làm gì:

| Chữ hiện | Nghĩa |
|---|---|
| SẴN SÀNG | Đang nghỉ, chờ bạn |
| ĐANG NGHE | Đang nghe bạn nói (giữ phím Cách) |
| ĐANG NGHE • LUÔN | Chế độ rảnh tay đang bật |
| ĐANG SUY NGHĨ | Bộ não đang xử lý câu hỏi |
| ĐANG NÓI | Javis đang đọc câu trả lời |

## Bảng phím tắt

| Thao tác | Kết quả |
|---|---|
| Giữ **Space** (khi không ở ô nhập) | Bật mic, nghe cho tới khi thả phím |
| Thả **Space** | Gửi câu vừa nói |
| **Enter** | Gửi tin nhắn đang gõ |
| **Shift + Enter** | Xuống dòng trong tin nhắn |
| **Ctrl + V** | Dán ảnh từ bộ nhớ tạm vào chat |
| **Esc** | Dừng Javis đang trả lời/đọc, tắt chế độ rảnh tay, thu nhỏ khung chat phóng to |

## Mẹo

- Muốn nói dài nhiều câu mà không sợ Javis gửi sớm, dùng chế độ rảnh tay (nút mic) và nói liền mạch; chỉ ngừng hẳn khi thật sự nói xong.
- Nghe Javis đọc lâu, muốn im lặng đọc chữ: tắt công tắc "Đọc trả lời bằng giọng", câu trả lời vẫn hiện đầy đủ dạng chữ.
- Đưa nhiều ảnh chụp màn hình cùng lúc bằng cách kéo - thả tất cả vào cửa sổ, Javis xử lý từng cái.
- Nếu bạn quen nói tiếng Anh, đổi "Ngôn ngữ nghe" sang Tiếng Anh để nhận diện chính xác hơn.

## Sự cố thường gặp

- **Giữ phím Cách không bật mic.** Con trỏ đang nằm trong ô gõ chữ hoặc một ô nhập khác. Bấm ra vùng trống của trang rồi giữ lại phím Cách.
- **Trình duyệt không nghe được.** Javis báo "Trình duyệt không hỗ trợ giọng nói. Dùng Chrome/Edge." Hãy mở dashboard bằng Chrome hoặc Edge.
- **Micro không hoạt động.** Trình duyệt chặn quyền micro. Vào phần quyền của trang trong trình duyệt và cho phép micro, rồi tải lại trang.
- **Không nghe thấy Javis đọc.** Kiểm tra nút loa ở góc trên phải có bị gạch chéo (tắt tiếng) không; kiểm tra âm lượng máy. Bấm "▶ Nghe thử" để kiểm tra riêng phần đọc.
- **Câu trả lời trống.** Nếu ô trả lời hiện dòng gợi ý thử lại hoặc đổi model, có thể do model đang chọn gặp trục trặc. Xem [Models & engine](10-models-va-engine.md) để đổi model/engine.
- **File tải mãi không xong.** File lớn hoặc mạng chậm; thẻ file sẽ báo lỗi cụ thể (quá thời gian tải, lỗi máy chủ). Thử lại với file nhỏ hơn hoặc kiểm tra kết nối.

Vẫn kẹt? Xem [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).
