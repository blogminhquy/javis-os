# ChatGPT Web: dùng gói ChatGPT của bạn làm bộ não cho Javis

Model `chatgpt-web` cho Javis chạy bằng **một phiên trình duyệt thật trên chatgpt.com** thay vì
gọi API. Nghĩa là nó tiêu gói ChatGPT bạn đang trả tiền, không tốn thêm API key nào.

Trang này là hướng dẫn đầy đủ. Trên thẻ ChatGPT trong Javis chỉ còn phần tóm tắt và một đường
link về đây, vì một thẻ cài đặt không phải chỗ để đọc ba màn hình chữ.

---

## 1. Cài hai thứ Javis cần

Vào **Năng lực → Công cụ**, khối **Công cụ tuỳ chọn** ở đầu trang, bấm cài cả hai:

| Mục | Nặng bao nhiêu | Để làm gì |
|---|---|---|
| Thư viện lái trình duyệt (playwright) | ~143 MB | Cho Javis điều khiển được trình duyệt |
| Trình duyệt (Chromium) | ~100 MB | Chính cái trình duyệt đó |

Cả hai tải vào ổ dữ liệu nên **sống qua mỗi lần cập nhật Javis**, không phải cài lại.

Cài xong thì **khởi động lại Javis** một lần.

> **Vì sao không cài sẵn:** hai thứ này cộng lại hơn 240 MB, mà phần lớn máy chạy Javis là VPS
> không màn hình và không bao giờ dùng tới. Nhét vào bản cài là bắt tất cả mọi người trả tiền
> băng thông và ổ đĩa cho tính năng của thiểu số, mỗi lần cập nhật một lần.

---

## 2. Lấy cookie phiên từ máy của bạn

Javis **không hỏi mật khẩu ChatGPT** và không có đường nào để nhận mật khẩu. Nó chỉ nhận một
cookie phiên, thứ trình duyệt của bạn đã có sẵn sau khi bạn đăng nhập.

### Trên máy tính

1. Mở **chatgpt.com** và đăng nhập như bình thường.
2. Bấm `F12` để mở DevTools (Mac: `Cmd + Option + I`).
3. Chọn tab **Application** (Firefox gọi là **Storage**).
4. Cột trái: **Cookies → https://chatgpt.com**
5. Tìm dòng tên `__Secure-next-auth.session-token`.
6. Bấm vào nó, copy toàn bộ cột **Value**. Chuỗi này rất dài, nhớ lấy hết.

### Trên điện thoại

Điện thoại không có DevTools. Lấy cookie trên máy tính rồi dán qua, vì cookie phiên **không
buộc vào thiết bị**.

---

## 3. Dán vào Javis

**Kết nối → Models → thẻ OpenAI OAuth (ChatGPT) → Đăng nhập bằng cookie.**

Dán vào ô rồi bấm nút. Javis nhận **ba kiểu dán**, không cần để ý mình đang cầm kiểu nào:

- Chỉ mỗi giá trị token: `eyJhbGciOi...`
- Cả chuỗi cookie: `a=1; __Secure-next-auth.session-token=eyJ...; b=2`
- File JSON xuất từ tiện ích cookie: `[{"name": "...", "value": "..."}]`

Xong thì chọn model `chatgpt-web` ở ô chọn model.

---

## 4. Những điều nên biết trước khi dùng

### Memory và Custom instructions của bạn sẽ ảnh hưởng câu trả lời

Mỗi lượt của engine này là **một cuộc chat thật trên chatgpt.com**, nên mọi thứ tài khoản bạn
đã dạy ChatGPT đều tác động vào. Muốn Javis trả lời thuần theo system prompt của nó thì tắt
Memory và Custom instructions trong cài đặt ChatGPT.

Đây là khác biệt lớn nhất so với đi đường API.

### Cookie mạnh ngang mật khẩu

Ai cầm được cookie đó là vào được cả tài khoản ChatGPT của bạn. Javis **không ghi nó ra log,
không trả nó về màn hình, không lưu ở đâu ngoài hồ sơ trình duyệt** - đúng chỗ một phiên đăng
nhập vẫn nằm. Đường `/web-chat/cookie` cũng đòi phiên đăng nhập dashboard thật, không nhận API
token.

Muốn thu hồi: đăng xuất tất cả thiết bị trong cài đặt ChatGPT là cookie đó chết.

### Cookie sẽ hết hạn

Vài tuần một lần. Lúc đó thẻ ChatGPT quay về "Chưa đăng nhập", bạn lấy cookie mới rồi dán lại.

### Cookie Cloudflare thì đừng mang sang

Nếu bạn copy cả đám cookie, trong đó có `cf_clearance` và `__cf_bm`, Javis sẽ **tự bỏ chúng
đi**. Không phải vì vô dụng mà vì **có hại**: chúng buộc vào IP, User-Agent và chữ ký TLS của
đúng cái máy đã tạo ra chúng. Mang vé của máy khác sang là Cloudflare thấy vé không khớp và
chặn, trong khi để yên thì Chromium trên máy chủ tự xin được vé đúng của chính nó.

---

## 5. Khi không chạy

| Thẻ nói gì | Nghĩa là | Làm gì |
|---|---|---|
| Chưa có thư viện lái trình duyệt | Thiếu playwright | Cài ở trang Công cụ, rồi khởi động lại |
| Chưa có trình duyệt nào Javis lái được | Thiếu Chromium | Cài ở trang Công cụ. Câu báo có kèm thư mục Javis đã tìm và thấy gì trong đó |
| Đã nạp cookie nhưng trang vẫn báo chưa đăng nhập | Cookie hết hạn hoặc copy thiếu | Lấy lại từ đầu, nhớ copy HẾT chuỗi |
| Không thấy model `chatgpt-web` trong ô chọn model | Máy chưa đủ đồ, hoặc chưa khởi động lại | Xem lại mục 1 |
| Không thấy khối ChatGPT Web trên thẻ | Đang bị ép tắt | Bỏ biến môi trường `JAVIS_ENABLE_WEB_CHAT=0` đi rồi khởi động lại |

### Chạy trên VPS

Chạy được. Chromium chạy ẩn, không cần máy chủ có màn hình.

Điều **chưa ai kiểm chứng**: Cloudflare nhìn một IP trung tâm dữ liệu có khó tính hơn không.
Gặp chuyện lạ thì báo lại kèm ảnh chụp màn hình.

---

## 6. Vì sao phải có trình duyệt, không dán mỗi cookie như MCP khác

Câu hỏi hợp lý, và câu trả lời quyết định cả thiết kế.

Substack và phần lớn dịch vụ khác không có lớp chống bot trước API: có cookie là gọi API được,
hết. chatgpt.com có **hai lớp nữa**, và cả hai đều không mang cookie sang máy khác được:

1. **Cloudflare.** Cookie `cf_clearance` buộc vào IP + User-Agent + chữ ký TLS của đúng máy đã
   giải thử thách.
2. **Sentinel của OpenAI.** Trước mỗi tin nhắn, trang gọi `/backend-api/sentinel/chat-requirements`
   và đòi một token proof-of-work do **JavaScript trong trang** tự tính.

Một trình duyệt thật giải cả hai lớp đó miễn phí, vì nó chính là thứ hai lớp kia muốn thấy. Tự
viết lại phần proof-of-work bằng Python thì làm được, nhưng hỏng mỗi lần OpenAI đổi thuật toán.

Nên trình duyệt ở lại. Thứ bỏ được là **thao tác đăng nhập**, và đó là lý do có đường dán cookie.
