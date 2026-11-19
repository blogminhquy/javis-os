---
bump: minor
title: Links sent on personal Zalo and WhatsApp show a preview card
---
## vi
### Thêm mới
- **Link Javis gửi trên Zalo cá nhân hiện thẻ xem trước.** Tin có link giờ hiện tiêu đề, mô tả và ảnh của trang ngay dưới chữ, như khi người thật gõ link trong app Zalo. Trước đây chỉ là link trần. Chủ báo ngày 19/11/2026.
  - Áp dụng cho câu trả lời của bot, tin gửi từ Hộp thư và khi nhờ Javis gửi link cho ai đó (tool mới `zalo_send_link`).
  - Cần javis-zalo 1.13.0, Javis tự nâng khi khởi động lại. Trang nào Zalo không đọc được thì tin vẫn đi dạng chữ như cũ.
  - Tin có thẻ link không giữ chữ đậm hay màu, giống tin người gõ có link. Tin nhóm có tag người thì vẫn gửi kiểu cũ để giữ tag.
- **Link Javis gửi trên WhatsApp cũng hiện thẻ xem trước.**

## en
### Added
- **Links Javis sends on personal Zalo show a preview card.** A message with a link now shows the page's title, description and image under the text, as when a person types a link in the Zalo app. Before, it was a bare link. Owner report, 19/11/2026.
  - Covers the bot's replies, messages sent from the Inbox, and asking Javis to send someone a link (new tool `zalo_send_link`).
  - Needs javis-zalo 1.13.0, which Javis moves to on its next restart. When Zalo cannot read the page, the message goes out as plain text as before.
  - A message with a link card has no bold or colours, like a link a person types. A group message that tags someone still goes out the old way to keep the tag.
- **Links Javis sends on WhatsApp show a preview card too.**
