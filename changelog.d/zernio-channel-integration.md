---
bump: minor
title: Add Zernio messaging channel with Instagram support and webhook configuration
---
## vi
### Thêm mới
- Thêm kênh Zernio trong hệ thống Chatbot với hỗ trợ Instagram, tự động gom tin 5 giây, bảo vệ chống trùng lặp durable, xác thực chữ ký HMAC-SHA256 constant-time và tuân thủ tiếp quản (takeover).
- Giao diện cấu hình webhook và chọn tài khoản Instagram đã kết nối trong tab Kênh.
- Hỗ trợ endpoint `/zernio/inbound` và `/webhooks/zernio` cho runtime chatbot và bridge.

## en
### Added
- Add Zernio messaging channel to Chatbot system with Instagram support, 5-second message debounce batching, durable deduplication, constant-time HMAC-SHA256 signature verification, and human takeover compliance.
- Webhook setup interface and connected Instagram account selector in Channels tab.
- Support `/zernio/inbound` and `/webhooks/zernio` routes for chatbot runtime and bridge adapter.
