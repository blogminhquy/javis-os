---
bump: minor
title: Every Google service can reuse a Google key saved in Javis, and Tag Manager can sign in
---
## vi
### Cải thiện
- **Dùng lại key Google cho mọi dịch vụ Google.** Hàng "Dùng lại key này" giờ nằm ngay đầu form, có cả ở Google Ads, Analytics, Merchant Center, Search Console, và mượn được key (kể cả service account) đã lưu ở bất kỳ dịch vụ Google nào. Google chỉ cho xem Client Secret đúng một lần lúc tạo, nên key trong Javis thường là bản duy nhất còn lại.
- **Đổi key ngay trên kết nối.** Mục "Kết nối lại (đăng nhập / đổi key)" của Gmail, Lịch, Analytics, Ads... giờ mở form đổi key: chọn key đã lưu ở dịch vụ khác, hoặc dán key mới, rồi đăng nhập lại.
- **Báo trước khi mất key.** Xoá kết nối cuối cùng còn giữ một key Google thì hộp xác nhận nói rõ, kèm cách giữ lại.

### Thêm mới
- Gói Google Tag Manager trong Javis Store đăng nhập Google ngay trong dashboard, như Analytics và Ads.

## en
### Improved
- **Reuse a Google key for every Google service.** The "Reuse this key" row now sits at the top of the form, shows on Google Ads, Analytics, Merchant Center and Search Console too, and borrows a key (service accounts included) saved for any other Google service. Google shows a client secret only once, when it is made, so the key kept in Javis is often the only copy left.
- **Change a key right on the connection.** "Reconnect (sign in / change key)" on Gmail, Calendar, Analytics, Ads and the rest now opens a change-key form: pick a key saved for another service, or paste a new one, then sign in again.
- **A warning before a key is lost.** Deleting the last connection that holds a Google key says so in the confirmation, with how to keep it.

### Added
- The Google Tag Manager pack in Javis Store signs in to Google right in the dashboard, like Analytics and Ads.
