---
bump: minor
title: Every Google service can reuse a Google key saved in Javis, and Tag Manager can sign in
---
## vi
### Cải thiện
- **Dùng lại key Google cho mọi dịch vụ Google.** Nút "Dùng lại key này" giờ hiện cả ở Google Ads, Analytics, Merchant Center, Search Console, và mượn được key đã lưu ở bất kỳ dịch vụ Google nào khác. Google chỉ cho xem Client Secret đúng một lần lúc tạo, nên key đã lưu trong Javis thường là bản duy nhất còn lại.
- **Dùng lại cả service account.** Đã đấu Google Sheets bằng service account thì Search Console mượn lại được, khỏi tải file lần nữa.
- Nút (i) cạnh hàng "Dùng lại key" nói cần kiểm gì khi Google báo `redirect_uri_mismatch`.

### Thêm mới
- Gói Google Tag Manager trong Javis Store đăng nhập Google ngay trong dashboard, như Analytics và Ads.

## en
### Improved
- **Reuse a Google key for every Google service.** The "Reuse this key" button now shows on Google Ads, Analytics, Merchant Center and Search Console too, and borrows a key saved for any other Google service. Google shows a client secret only once, when it is made, so the key kept in Javis is often the only copy left.
- **Reuse a service account too.** Once Google Sheets is connected with a service account, Search Console can borrow it instead of asking for the file again.
- An (i) next to the "Reuse key" row says what to check when Google answers `redirect_uri_mismatch`.

### Added
- The Google Tag Manager pack in Javis Store signs in to Google right in the dashboard, like Analytics and Ads.
