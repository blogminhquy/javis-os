---
bump: minor
title: Block, leave and delete from the chat's Info panel; a deleted chat stays deleted
---
## vi
### Thêm mới
- **Chặn, Rời nhóm, Xoá ngay trong bảng Thông tin của cuộc chat.** Ba thao tác của menu "..." trên danh sách giờ có sẵn ở cuối bảng Thông tin, cùng chữ và cùng dòng nhỏ nói nó có làm trên Zalo hay Fanpage không.
- **Rời nhóm Zalo thì xoá luôn cuộc chat khỏi Javis.** Trước đây cuộc chat còn nằm lại ở bộ lọc Đã ẩn. Câu hỏi xác nhận nói rõ điều này trước khi làm.

### Sửa lỗi
- **Cuộc chat đã xoá không tự hiện lại.** Sau khi xoá, tin cũ của cuộc chat đó (Zalo đọc lại bộ đệm mỗi lần khởi động lại) dựng lại đúng cuộc chat vừa xoá. Giờ chỉ một tin gửi sau lúc xoá mới mở lại nó. Dòng vừa xoá cũng không còn nháy lại trên danh sách trong vài giây.
- **Chặn hay bỏ chặn cuộc chat đang mở thì khung chat và bảng Thông tin đổi theo ngay.**

## en
### Added
- **Block, Leave group and Delete right in a chat's Info panel.** The three actions of the "..." menu in the list now sit at the foot of the Info panel, with the same words and the same small line saying whether it also happens on Zalo or the Page.
- **Leaving a Zalo group also deletes its chat from Javis.** It used to stay under the Hidden filter. The confirmation says so before anything happens.

### Fixed
- **A deleted chat no longer comes back by itself.** After a delete, the chat's old messages (Zalo re-reads its buffer after every restart) rebuilt the very chat just deleted. Now only a message sent after the delete opens it again. The deleted row no longer flickers back in the list for a few seconds either.
- **Blocking or unblocking the open chat updates the chat header and the Info panel at once.**
