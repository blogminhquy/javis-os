# 29 - Slack và WhatsApp

***Tiếng Việt** · [English](en/29-slack-whatsapp.md)*

Từ 0.71.0 Javis nói chuyện được trên Slack và WhatsApp, theo đúng hai cách như Telegram và Zalo:

- **Kênh điều khiển:** bạn chat với chính Javis (brain, công cụ, việc nền của bạn). Cài ở trang **Kênh**.
- **Bot khách hàng:** một agent chuyên trách trả lời khách hoặc đội nhóm, mọi cuộc chat vào hộp thư chung, tiếp quản được khi cần người thật. Cài ở trang **Chatbot**.

| | Slack | WhatsApp |
|---|---|---|
| Javis kết nối thế nào | Socket Mode: Javis tự mở kết nối, **không cần tên miền** | Webhook: Meta gọi vào Javis, **cần tên miền HTTPS** |
| Nhóm | Kênh (Javis trả lời khi được gọi tên, trong thread) | Chỉ chat riêng |
| File | Ảnh và tài liệu, cả hai chiều | Ảnh và tài liệu, cả hai chiều |
| Tin thoại | Chép thành chữ (cần key Groq ở trang Models) | Chép thành chữ (như trên) |
| Nhắn trước | Lúc nào cũng được | Chỉ trong 24 giờ kể từ tin cuối của người đó |

---

## Slack

### 1. Tạo app Slack (một lần, khoảng 3 phút)

1. Mở [api.slack.com/apps](https://api.slack.com/apps), bấm **Create New App**, chọn **From an app manifest**, chọn workspace.
2. Dán manifest này (YAML) rồi bấm **Create**:

```yaml
display_information:
  name: Javis
features:
  bot_user:
    display_name: Javis
    always_online: true
  app_home:
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false
oauth_config:
  scopes:
    bot:
      - app_mentions:read
      - chat:write
      - im:history
      - im:read
      - im:write
      - channels:history
      - groups:history
      - files:read
      - files:write
      - users:read
settings:
  event_subscriptions:
    bot_events:
      - app_mention
      - message.im
      - message.channels
      - message.groups
  socket_mode_enabled: true
  org_deploy_enabled: false
  token_rotation_enabled: false
```

3. **Basic Information → App-Level Tokens → Generate Token and Scopes**: thêm scope `connections:write`, tạo, chép token bắt đầu bằng `xapp-`.
4. **Install App → Install to Workspace**, rồi chép **Bot User OAuth Token** bắt đầu bằng `xoxb-`.

### 2a. Kênh điều khiển (bạn chat với Javis)

1. Trang **Kênh** → thẻ **Slack**: tích **Bật**, dán bot token và app token, bấm **Lưu**.
2. Mở Slack, tìm app trong mục **Apps**, nhắn một câu bất kỳ. Bạn sẽ hiện trên thẻ kèm mã 4 số; đối chiếu mã rồi bấm **Cho phép**. Danh sách để trống là cố ý: chưa ai chạm được vào brain của bạn cho tới khi bạn cho phép.
3. Từ đó: nhắn riêng cho bot, hoặc gọi `@Javis` trong kênh đã mời bot vào (`/invite @Javis`); bot trả lời trong thread.

Lệnh bot trên Slack bắt đầu bằng `!` thay cho `/`, vì Slack giữ `/` cho lệnh của chính nó: `!stop`, `!new`.

### 2b. Bot khách hàng

1. Dùng một app Slack **riêng** (làm lại bước 1 với tên khác) để khách không bao giờ chạm tới kênh điều khiển của bạn.
2. Trang **Chatbot** → **Tài khoản** → thêm tài khoản, kênh **Slack**, dán cả hai token **cách nhau một dấu cách**: `xoxb-... xapp-...`.
3. Tạo bot ngay trên trang đó và gắn tài khoản vào.

---

## WhatsApp

WhatsApp chỉ chạy qua **WhatsApp Business Cloud API** chính thức của Meta. Javis không đăng nhập WhatsApp cá nhân (làm vậy là vi phạm điều khoản WhatsApp và số rất dễ bị khoá).

### Trước khi bắt đầu

- Javis phải truy cập được qua **HTTPS bằng tên miền** (VPS có tên miền, xem [DEPLOY.md](../DEPLOY.md)). Meta từ chối `http://` và địa chỉ IP.
- Khi chưa đặt mật khẩu đăng nhập, tên miền phải là tên Javis biết (tên miền riêng, xem [15 - Thương hiệu và tên miền](15-thuong-hieu-ten-mien.md), hoặc `JAVIS_ALLOWED_HOSTS`), nếu không Javis trả Meta mã 403.
- Meta có thể tính phí một số cuộc hội thoại; xem trang bảng giá hiện tại của họ.

### 1. Tạo app Meta (một lần)

1. [developers.facebook.com](https://developers.facebook.com) → **My Apps → Create App** → loại **Business** → thêm sản phẩm **WhatsApp**.
2. **WhatsApp → API Setup**: ghi lại **Phone number ID** (là một mã, không phải số điện thoại). Số thử nghiệm miễn phí chỉ nhắn được tối đa 5 số bạn xác minh ở đó; muốn chạy thật thì thêm số thật.
3. **Access token vĩnh viễn**: Business Settings → **Users → System users** → thêm một người dùng hệ thống, gán app với toàn quyền, **Generate token** với `whatsapp_business_messaging` và `whatsapp_business_management`. (Token ở trang API Setup hết hạn sau 24 giờ.)
4. **App settings → Basic**: hiện và chép **App secret**. Javis dùng nó để kiểm mọi lời gọi webhook có đúng là từ Meta.

### 2a. Kênh điều khiển

1. Trang **Kênh** → thẻ **WhatsApp**: tích **Bật**, điền Phone number ID, Access token, App secret, bấm **Lưu**.
2. Thẻ hiện **Callback URL** và **Verify token**. Bên Meta: **WhatsApp → Configuration → Webhook → Edit**, dán cả hai, **Verify and save**, rồi đăng ký trường **messages**.
3. Nhắn cho số doanh nghiệp từ WhatsApp của bạn. Bạn hiện trên thẻ kèm mã; bấm **Cho phép**.

### 2b. Bot khách hàng

1. Dùng một số khác (mỗi số thuộc về một bot).
2. Trang **Chatbot** → **Tài khoản** → thêm tài khoản, kênh **WhatsApp**, dán ba giá trị **cách nhau dấu cách**: `<phone number id> <access token> <app secret>`.
3. Webhook dùng chung Callback URL và Verify token ở trang Kênh: một địa chỉ phục vụ mọi số, Javis tự chia tin theo số mà khách nhắn tới.

### Cửa sổ 24 giờ

WhatsApp chỉ cho doanh nghiệp nhắn tự do trong vòng **24 giờ** kể từ tin cuối người đó gửi. Quá thời gian đó chỉ gửi được tin mẫu (template) đã duyệt. Thực tế là:

- Trả lời tin nhắn thì không bao giờ bị ảnh hưởng.
- Kết quả việc nền (loop, việc Kanban, nhắc hẹn) xong sau hơn 24 giờ kể từ lần cuối bạn nhắn sẽ không gửi được qua WhatsApp. Nó không mất: mọi kết quả đều nằm sẵn trong hộp thư trên dashboard (quả chuông). Nhắn cho bot một câu bất kỳ là mở lại cửa sổ.

---

## Khắc phục sự cố

| Hiện tượng | Nguyên nhân và cách sửa |
|---|---|
| Thẻ Slack báo `invalid_auth` | Bot token sai hoặc bị thu hồi. Cài lại app rồi chép token `xoxb-` mới. |
| Thẻ Slack: app token bị từ chối | Token `xapp-` thiếu `connections:write`, hoặc chưa bật Socket Mode. |
| Slack: không trả lời trong kênh | Mời bot vào (`/invite @Javis`) rồi gọi tên nó. |
| WhatsApp: Meta báo không xác minh được callback | Địa chỉ không phải HTTPS, tên miền chưa được phép, hoặc gõ sai verify token. |
| WhatsApp: tin nhắn không tới đâu cả | Chưa đăng ký trường **messages**, hoặc Phone number ID là của số khác. |
| WhatsApp lỗi 190 | Access token hết hạn: dùng token của System User, không dùng token 24 giờ. |
| WhatsApp lỗi 131047 | Ngoài cửa sổ 24 giờ, xem ở trên. |
