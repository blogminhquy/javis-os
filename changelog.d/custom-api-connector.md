---
bump: minor
title: Connect any REST API with an API key
---
## vi
### Thêm mới
- **Kết nối API tuỳ chỉnh.** Dịch vụ nào có REST API và API key mà chưa có MCP (POS, CRM, vận chuyển, hoá đơn điện tử...) giờ nối được ở trang Kết nối: dán địa chỉ gốc và key, mọi bộ não gọi được API đó.
- **Key không bao giờ tới tay model.** Key được mã hoá, server tự gắn vào lời gọi và chỉ gửi tới đúng máy chủ đã khai; key có lọt trong kết quả cũng bị che.
- **Mặc định chỉ đọc.** Ở mức Chỉ đọc Javis chỉ gọi GET; muốn tạo, sửa, xoá trên dịch vụ đó thì nâng kết nối lên Toàn quyền.

## en
### Added
- **Custom API connection.** Any service with a REST API and an API key but no MCP (POS, CRM, shipping, e-invoices...) now connects on the Connections page: paste the base URL and the key, and every engine can call that API.
- **The key never reaches the model.** It is encrypted, the server adds it to each call and only sends it to the host you entered; a key echoed in a result is masked.
- **Read-only by default.** At Read-only Javis only calls GET; to create, edit or delete on that service, raise the connection to Full access.
