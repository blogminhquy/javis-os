---
bump: minor
title: Admin channel chats show under Javis Core and their agent; agent cards show tags
---
## vi
### Thêm mới
- **Bot Zalo ở Kênh Admin gọi được cộng sự như Telegram.** Gõ `@<tên> <câu hỏi>` để hỏi một câu, hoặc `/agent <tên>` để cộng sự đó trả lời cả chat.
- **Thẻ trợ lý ở trang Cộng sự hiện tag ngay dưới tên**, cạnh avatar. Chữ "Hệ thống" của Javis Core cũng xuống dòng này. Cột hẹp thì tag dư gộp thành "+n".

### Sửa lỗi
- **Chat từ Zalo và Telegram (Kênh Admin) nay hiện trong lịch sử của Javis Core**, còn chat gọi một cộng sự thì hiện trong lịch sử của cộng sự đó, có nhãn TG hoặc zalo.
- **Lệnh `/brain`, `/reset`, `/stop`, `/model` trên bot Zalo admin tác động đúng cuộc chat đang nói.** Trước đây chúng đổi nhầm một phiên khác nên chat có thể rơi sang brain mặc định.
- **Bot chuyên trách không được dùng chung token với bot Zalo admin nữa.** Dùng chung khiến tin nhắn bị chia đôi và một nửa chui vào hộp thư khách, mất khỏi chat của bạn.

## en
### Added
- **The Zalo bot on the Admin channels page can call a partner, like Telegram.** Type `@<name> <question>` to ask once, or `/agent <name>` to let that partner answer the whole chat.
- **Assistant cards on the Partners page show their tags right under the name**, beside the avatar. Javis Core's "System" badge moved to that line too. In a narrow column the extra tags fold into "+n".

### Fixed
- **Chats from Zalo and Telegram (Admin channels) now show in Javis Core's history**, and a chat that called a partner shows in that partner's history, labelled TG or zalo.
- **`/brain`, `/reset`, `/stop` and `/model` on the Zalo admin bot act on the chat you are in.** Before, they changed another session, so the chat could land in the default brain.
- **A dedicated bot can no longer share the Zalo admin bot's token.** Sharing it split the messages and half of them went to the customer inbox, missing from your chat.
