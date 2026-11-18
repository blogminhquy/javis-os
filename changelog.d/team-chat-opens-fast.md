---
bump: minor
title: A team chat opens at once and loads older messages as you scroll up
---
## vi
### Sửa lỗi
- **Mở một team không còn kẹt lâu ở "Đang tải tin nhắn của nhóm".** Mỗi lần mở, máy chủ từng cộng lại chi phí model của cả team từ trước tới nay, team càng lâu càng chậm, trong khi màn hình không còn hiện con số đó. Giờ bỏ hẳn bước này khi mở team.

### Cải thiện
- **Team chỉ tải các tin gần nhất, cuộn lên mới tải tiếp tin cũ.** Gần tới đầu khung chat là tự tải thêm một trang, giữ nguyên chỗ đang đọc, giống khung chat chính và trang Chatbot. Lúc đang tải hiện dòng "Đang tải tin cũ...".

## en
### Fixed
- **Opening a team no longer hangs on "Loading the team's messages".** Each open used to add up every model call the team ever made, slower the older the team, although the page no longer shows those figures. Opening a team skips that now.

### Improved
- **A team loads only its latest messages, and older ones as you scroll up.** Near the top of the chat the next page loads by itself and you stay on the same message, like the main chat and the Chatbot page. A "Loading older messages..." line shows meanwhile.
