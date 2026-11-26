---
bump: minor
title: Bots remember open questions, never drop an owner bell, and split replies on every chat channel
---
## vi
### Thêm mới
- **Bot nhớ mình đang chờ khách trả lời.** Bot hay nhân viên hỏi một khách trong nhóm, khách trả lời sau cả tiếng đồng hồ (kể cả không có dấu hỏi, như "7kg e ơi") thì bot vẫn biết đó là câu trả lời và xét để đáp lại.
- **Bot nhắn nhiều tin ngắn trên Messenger, Zalo OA và Telegram,** như đã làm trên Zalo cá nhân. Bình luận dưới bài đăng vẫn là một câu trả lời.
- **Chỉnh được khoảng cách giữa hai lần báo chuông** ở form bot (chế độ Tự đánh giá): để trống là 10 phút, đặt 0 thì lần nào cũng báo.

### Sửa lỗi
- **Không còn mất chuông báo chủ.** Khách nhắn thêm câu khó trong lúc chờ thì Javis gom lại báo một lần khi hết quãng chờ, kèm số tin và tin mới nhất, trừ khi bạn đã trả lời khách rồi.

## en
### Added
- **Bots remember they are waiting for an answer.** When the bot or a staff member asks a customer something in a group and the answer comes an hour later (even a short one without a question mark), the bot still knows it is the answer and considers replying.
- **Bots send several short messages on Messenger, Zalo OA and Telegram,** as they already did on personal Zalo. A reply under a post stays one reply.
- **The gap between two owner bells is a setting** on the bot form (Auto-judge mode): blank means 10 minutes, 0 rings every time.

### Fixed
- **Owner bells are no longer lost.** If the customer sends more hard messages while waiting, Javis rings once when the gap ends, with how many there were and the latest one, unless you already answered the customer.
