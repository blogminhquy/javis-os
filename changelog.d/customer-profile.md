---
bump: minor
title: Bots keep a profile of each customer and read it on every reply
---
## vi
### Thêm mới
- **Hồ sơ khách hàng.** Sau khi một cuộc chat riêng im khoảng 15 phút, model chạy nền tự ghi lại những gì cần nhớ về khách: tên, cách xưng hô, liên hệ, đang quan tâm gì, đã chốt gì, việc còn dang dở. Lần sau bot đọc hồ sơ này cùng 30 tin gần nhất nên không phải hỏi lại, kể cả khi khách quay lại sau vài tháng.
- **Ô ghi chú về khách thành mục Hồ sơ khách hàng** trong khung Thông tin của trang Hội thoại, dài tới 4.000 ký tự. Bạn vẫn sửa, ghi thêm hay xoá trắng được, phần bạn viết được giữ lại ở lần cập nhật sau.

### Cải thiện
- **Chỉ chat riêng mà bot đã trả lời mới có hồ sơ.** Nhóm và các cuộc chat của bạn bè, người nhà trên nick Zalo cá nhân thì không. Mỗi 5 phút Javis làm tối đa 5 hồ sơ nên không tốn hạn mức dồn dập.

## en
### Added
- **Customer profile.** After a private chat has been quiet for about 15 minutes, the background model writes down what is worth remembering about the customer: name, how to address them, contact details, what they are interested in, what was agreed, what is still open. The bot then reads this profile along with the last 30 messages, so it does not ask again, even when the customer comes back months later.
- **The note about the customer becomes the Customer profile section** of the Info panel on the Conversations page, up to 4,000 characters. You can still edit, add to or empty it, and what you write is kept at the next update.

### Improved
- **Only private chats the bot has answered in get a profile.** Groups do not, nor do chats with friends and family on a personal Zalo account. Javis writes at most 5 profiles every 5 minutes, so it does not burn through your plan in one go.
