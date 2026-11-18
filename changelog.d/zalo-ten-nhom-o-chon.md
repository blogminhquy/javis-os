---
bump: patch
title: Ticked Zalo groups in the bot form keep their names
---
## vi
### Sửa lỗi
- **Ô chọn nhóm của Chatbot không còn hiện id trần.** Nhóm đã tick mà ô tìm lọc mất, hoặc cũ hơn 80 cuộc chat gần nhất, trước đây hiện thành dãy số dài. Giờ nhóm nào cũng mang tên thật lấy từ Hộp thư, nhóm chưa rõ tên thì hiện "Nhóm …" kèm đuôi id.

## en
### Fixed
- **The Chatbot group picker no longer shows bare ids.** A ticked group hidden by the search box, or older than the 80 latest chats, used to show as a long number. Every group now keeps its real name from the inbox, and a group with no known name reads "Group …" with the end of its id.
