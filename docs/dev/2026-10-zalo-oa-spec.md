# Kênh Zalo OA và chuyện "Zalo OA MCP" (0.412.0)

Chủ repo yêu cầu 30/10/2026: "Nghiên cứu thêm Zalo OA MCP và làm kênh chatbot luôn". Ghi lại ở đây
những gì đã tra được, cái gì đã chốt và cái gì còn phải thử với một OA thật.

## 1. Đã có MCP Zalo OA nào dùng được chưa

- **ardennguyen/zalo-agent-cli** (npm, có `mcp-server.js` chạy stdio): bọc OA Open API v3 và cả tài
  khoản cá nhân (API không chính thức). Giấy phép **CC BY-NC-SA 4.0**, cấm dùng thương mại, nên
  KHÔNG đóng gói vào Javis (MIT) và không chép mã. Chủ OA dùng cho việc riêng thì tự cài như mọi
  MCP ngoài ở trang Kết nối.
- Các wrapper khác trên GitHub (zalo-node-oa, zalo-oa-api-wrapper, zalo-api Ruby) là thư viện gọi
  API, không phải MCP.
- Kết luận: một MCP rời không giải được việc chính là **bot trả lời khách**. Muốn bot trả lời thì tin
  phải ĐI VÀO Javis (webhook) và đi qua đúng đường của Bot chuyên trách (Agent, giờ trực, Hộp thư,
  tiếp quản). Nên làm thành một KÊNH trong `server/channels`, như Messenger và WhatsApp. Công cụ
  phía chủ (gửi tin cho người quan tâm, gửi hàng loạt, đọc danh sách người quan tâm) để bước sau,
  dùng chung `TokenKeeper` nên không phải lo token xoay vòng thêm lần nữa.

## 2. Giao thức (tra qua tài liệu cộng đồng, mạng của phiên dev chặn developers.zalo.me)

- Làm mới token: `POST https://oauth.zaloapp.com/v4/oa/access_token`, header `secret_key: <App secret>`,
  form `refresh_token`, `app_id`, `grant_type=refresh_token`. Trả `access_token`, `refresh_token`,
  `expires_in` (90000 giây). Refresh token dùng MỘT lần, sống khoảng 3 tháng.
- Gửi tin tư vấn: `POST https://openapi.zalo.me/v3.0/oa/message/cs`, header `access_token`, body
  `{"recipient": {"user_id"}, "message": {"text"}}`. Ảnh: upload `/v2.0/oa/upload/image` lấy
  `attachment_id`, gửi template `media`. File: upload `/v2.0/oa/upload/file` lấy `token`.
- Thông tin OA: `GET /v2.0/oa/getoa`. Tên khách: `GET /v3.0/oa/user/detail?data={"user_id":...}`.
- Webhook: Zalo POST JSON có `app_id`, `event_name` (`user_send_text`, `user_send_image`...),
  `timestamp`, `sender.id`, `recipient.id` (OA id), `message.msg_id`, `message.text`,
  `message.attachments[].payload.url`. Chữ ký ở header `X-ZEvent-Signature: mac=<hex>`,
  hex = sha256(app_id + body thô + timestamp + OA secret key). Một bản cài cộng đồng dùng
  HMAC-SHA256(OA secret key, body); Javis nhận cả hai vì cả hai đều cần khoá bí mật.
- Zalo bắt xác thực tên miền webhook bằng file `zalo_verifier<mã>.html` hoặc thẻ meta. Javis phục vụ
  file cho các mã chủ đã lưu (`settings.zalo_oa.site_codes`), mã lạ trả 404.

## 3. Quyết định thiết kế

- **Một chuỗi bí mật cho mỗi tài khoản** (kho tài khoản kênh chỉ giữ một chuỗi mã hoá): chủ dán
  "App ID, App secret, OA secret, Refresh token"; sau lần làm mới đầu Javis ghi lại thành JSON có
  access token, hạn và OA id.
- **TokenKeeper là chỗ duy nhất làm mới token**, khoá theo từng tài khoản, ghi cặp mới vào kho TRƯỚC
  khi dùng. Không có id tài khoản thì không làm mới (không lưu được cặp mới là mất OA).
- Bấm **Kiểm tra** ở form phải làm mới một lần để biết khoá đúng và OA nào, việc đó tiêu luôn refresh
  token vừa dán. Cặp mới chờ trong RAM 30 phút (`_PENDING`), lần đầu đọc tài khoản vừa lưu thì thay vào
  và ghi xuống kho. Javis khởi động lại giữa hai bước thì chủ dán refresh token mới; chấp nhận vì ghi
  cặp chờ xuống đĩa nghĩa là thêm một chỗ cất bí mật.
- Thiếu OA secret key thì bot KHÔNG chạy: mọi webhook sẽ 401 và bot trông như khoẻ mà không nghe gì.

## 4. Còn phải thử với một OA thật

- Đúng thứ tự ghép chuỗi chữ ký và nguồn `timestamp` (lấy từ body). Test đang canh công thức đã ghi.
- Tên trường gói OA trong `getoa` (đang đọc `package_name` hoặc `oa_type`, thiếu thì để trống).
- Mã lỗi khung tư vấn (-230) và gói (-224); mã lạ vẫn hiện nguyên câu của Zalo.
- Bước sau: luồng OAuth v4 ngay trong Javis (nút "Cho phép OA", PKCE, callback) để chủ khỏi vào
  API Explorer; và bộ tool `zalo_oa_*` phía chủ.
