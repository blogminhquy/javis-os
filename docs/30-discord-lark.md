# 30 - Discord và Lark/Feishu

***Tiếng Việt** · [English](en/30-discord-lark.md)*

Từ 0.85.0 bạn nói chuyện được với Javis ngay trong Discord và Lark (hay Feishu, bản Trung Quốc của Lark). Hai kênh này là **kênh admin**: người nhắn là chính bạn, đủ quyền như trên dashboard (brain, công cụ, việc nền). Cài ở trang **Kênh Admin**, mỗi kênh một tab.

Bot trả lời **khách hàng** là chuyện khác, nằm ở trang **Chatbot**. Discord và Lark hiện chưa có ở đó.

| | Discord | Lark / Feishu |
|---|---|---|
| Javis kết nối thế nào | Gateway: Javis tự mở kết nối, **không cần tên miền** | Kết nối dài: Javis tự mở kết nối, **không cần tên miền** |
| Cần gì | Một bot token | App ID và App Secret của một app tự dùng |
| Trong nhóm | Javis trả lời khi được @nhắc hoặc khi bạn trả lời tin của bot | Javis trả lời khi được @nhắc |
| File | Ảnh và tài liệu, cả hai chiều (tối đa 10 MB khi gửi đi) | Ảnh và tài liệu, cả hai chiều |
| Tin thoại | Chép thành chữ (cần key Groq ở trang Models) | Chép thành chữ (như trên) |
| Lệnh bot | `!stop`, `!new`... (Discord giữ dấu `/` cho lệnh riêng của nó) | `/stop` hoặc `!stop` đều được |

Cả hai kênh **khoá mặc định**: chưa cho phép ai thì không ai dùng được. Người lạ nhắn cho bot sẽ nhận một mã ghép nối 4 số và hiện ở tab của kênh đó, bạn bấm **Cho phép** là xong. Không phải đi tra ID bằng tay.

---

## Discord

### 1. Tạo bot (một lần, khoảng 3 phút)

1. Mở [discord.com/developers/applications](https://discord.com/developers/applications), bấm **New Application**, đặt tên (ví dụ "Javis").
2. Vào mục **Bot**, bấm **Reset Token**, chép chuỗi token. Token chỉ hiện một lần, mất thì reset lại.
3. Vào mục **OAuth2** → **URL Generator**: tích scope **bot**, rồi tích quyền **View Channels**, **Send Messages**, **Read Message History**, **Attach Files**. Mở link được tạo ra để mời bot vào server của bạn.

Không cần bật **Message Content Intent** hay intent đặc quyền nào. Javis chỉ đọc tin nhắn riêng gửi cho bot và tin @nhắc bot, hai loại này Discord vẫn giao đủ chữ khi không có intent đó.

### 2. Nối vào Javis

1. Trang **Kênh Admin** → tab **Discord**: dán token vào ô **Bot token**, bấm **Lưu và bật kênh**.
2. Nhãn cạnh tên kênh chuyển sang **Đang chạy**.
3. Nhắn riêng cho bot một câu trên Discord (bạn phải ở chung ít nhất một server với bot). Bot trả về mã ghép nối, còn trên tab Discord hiện tên bạn kèm đúng mã đó. Bấm **Cho phép**.
4. Bấm **Gửi tin thử** để chắc chiều Javis gửi đi cũng thông.

Trong kênh của server, gõ `@Javis câu hỏi`: Javis trả lời ngay bên dưới, dạng trả lời tin của bạn. Tin nhắn qua lại giữa mọi người trong kênh, không ai @nhắc bot, thì Javis bỏ qua.

### Sự cố thường gặp

- **"Discord từ chối bot token"**: token sai, hoặc bạn đã bấm Reset Token sau khi chép. Reset lại, dán token mới, Lưu.
- **"Bot đang xin một intent chưa được bật"**: không xảy ra với Javis bản này. Nếu gặp, bạn đang chạy bản cũ hơn 0.85.0.
- **Gửi tin thử báo không mở được tin nhắn riêng**: người được phép phải ở chung một server với bot và không chặn tin nhắn riêng từ thành viên server.
- **Bot im trong kênh**: thiếu quyền **View Channels** hoặc **Send Messages** ở kênh đó. Kiểm tra quyền của vai trò bot trong cài đặt kênh.

---

## Lark / Feishu

Lark (open.larksuite.com) và Feishu (open.feishu.cn) là hai nền tảng tách biệt: app tạo bên này không tồn tại bên kia. Doanh nghiệp ở ngoài Trung Quốc đại lục gần như luôn dùng **Lark**, và đó là lựa chọn mặc định ở ô **Nền tảng**.

### 1. Tạo app (một lần, khoảng 5 phút)

1. Mở console nhà phát triển: [open.larksuite.com/app](https://open.larksuite.com/app) cho Lark, [open.feishu.cn/app](https://open.feishu.cn/app) cho Feishu. Bấm **Create Custom App**, đặt tên.
2. Mục **Add features**: thêm **Bot**.
3. Mục **Permissions & Scopes**: thêm quyền đọc tin nhắn riêng gửi cho bot, đọc tin @nhắc bot trong nhóm, gửi tin với tư cách bot, và đọc file trong tin nhắn (tìm theo chữ `im:message` và `im:resource`).
4. Mục **Credentials & Basic Info**: chép **App ID** (dạng `cli_...`) và **App Secret**.

### 2. Nối vào Javis, rồi bật nhận sự kiện

Thứ tự quan trọng: console Lark chỉ cho lưu chế độ "kết nối dài" khi đã có một kết nối đang mở, nên bật Javis trước.

1. Trang **Kênh Admin** → tab **Lark**: chọn **Nền tảng** (Lark hoặc Feishu), dán **App ID** và **App Secret**, bấm **Lưu và bật kênh**. Nhãn chuyển sang **Đang chạy**.
2. Quay lại console, mục **Events & Callbacks**: ở cách nhận sự kiện chọn **Receive events through persistent connection** (nhận qua kết nối dài), lưu. Bấm **Add Events**, thêm sự kiện **Message received** (`im.message.receive_v1`).
3. Mục **Version Management & Release**: tạo phiên bản và phát hành. Công ty có quản trị viên thì cần họ duyệt.
4. Trong Lark, tìm bot theo tên rồi nhắn riêng một câu. Bot trả mã ghép nối, tab Lark hiện bạn kèm mã đó: bấm **Cho phép**.

Trong nhóm, thêm bot vào nhóm rồi gõ `@Javis câu hỏi`. Javis trả lời ngay dưới tin đó. Khi đang làm, Javis thả một biểu tượng cảm xúc "đang làm" lên câu hỏi của bạn, vì Lark không có dấu "đang nhập" cho bot.

### Sự cố thường gặp

- **"Lark từ chối App ID / App Secret"**: chép thiếu ký tự, hoặc chọn nhầm nền tảng (app Lark mà ô Nền tảng để Feishu, hay ngược lại).
- **Đang chạy mà nhắn không thấy trả lời**: chưa thêm sự kiện `im.message.receive_v1`, chưa chọn nhận sự kiện qua kết nối dài, hoặc chưa phát hành phiên bản mới sau khi đổi quyền. Mỗi lần đổi quyền đều phải phát hành lại.
- **"Lark từ chối kết nối ... too many connections"**: cùng một app đang được một máy Javis khác kết nối. Mỗi app chỉ nên gắn với một Javis.
- **Gửi tin thử lỗi "người này chưa thấy được bot"**: phạm vi phát hành của app chưa gồm người đó. Sửa ở phần phạm vi người dùng khi phát hành.
