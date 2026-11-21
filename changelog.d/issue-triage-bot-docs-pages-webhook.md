---
bump: minor
title: Bot finds its documents after a hand-over, Facebook Pages uses every connection, longer webhook instructions
---
## vi
### Thêm mới
- **Chỉnh được số ảnh bot gửi mỗi câu trả lời.** Mặc định vẫn 4 ảnh. Máy nào cần nhiều hơn (cho khách xem phòng, xem mẫu) thì đặt biến `JAVIS_BOT_MAX_IMAGES`, tối đa 20, rồi khởi động lại Javis.

### Sửa lỗi
- **Bot Zalo cá nhân không còn nói "chưa có thông tin" sau khi bạn nhắn tay.** Lượt bot nhận lại cuộc chat có kèm một dòng ghi chú của Javis, và dòng đó lọt vào câu tìm tài liệu nên bot tìm trượt. Giờ bot chỉ tìm theo đúng lời khách.
- **Facebook Trang dùng đúng kết nối.** Có hai kết nối Facebook Trang thì trước đây chỉ kết nối đầu tiên được dùng, kể cả khi bạn đã tắt nó. Giờ kết nối đang tắt không bao giờ được dùng, và Trang của mọi kết nối đang bật đều thấy và đăng được. Meta Ads cũng bỏ qua kết nối đang tắt.
- **Nội dung webhook dài tới 5.000 ký tự.** Trước đây phần sau ký tự thứ 2.000 bị cắt mà không báo. Ô nhập giờ dừng đúng ở 5.000.

## en
### Added
- **The number of images a bot sends per reply is adjustable.** The default stays at 4. A machine that needs more (showing a room or product samples) sets `JAVIS_BOT_MAX_IMAGES`, up to 20, then restarts Javis.

### Fixed
- **The personal Zalo bot no longer says "no information" after you typed by hand.** The turn that hands the chat back to the bot carries a note from Javis, and that note leaked into the document search, so the search missed. The bot now searches with the customer's words only.
- **Facebook Pages uses the right connection.** With two Facebook Pages connections only the first was ever used, even after you turned it off. A connection that is off is now never used, and the Pages of every connection that is on can be seen and posted to. Meta Ads also skips a connection that is off.
- **Webhook instructions can be up to 5,000 characters.** Everything after character 2,000 used to be cut without a word. The box now stops at exactly 5,000.
