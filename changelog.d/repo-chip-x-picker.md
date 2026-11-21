---
bump: minor
title: Clear X on the repo chip and in the repo list; a repo no longer jumps back
---
## vi
### Thêm mới
- **Nút X rõ ràng để bỏ repository.** Viên repository dưới khung chat có nút X, bấm một lần là bỏ. Trong bảng chọn, mỗi repository đã chọn cũng có nút X riêng. Viên thư mục ghim bên cạnh và viên repository ở trang Nhóm có cùng nút này.
- **Khó bấm nhầm hơn.** Dòng repository đã chọn không còn tự bỏ khi chạm vào, chỉ nút X mới bỏ. Repository chưa chọn có dấu cộng, chạm một lần là thêm.

### Sửa lỗi
- **Repository không còn "nhảy về" cái cũ.** Trước đây đổi sang repository khác mà cái cũ còn thay đổi chưa lưu thì cả lần đổi bị từ chối, cái mới chọn cũng mất theo. Giờ thêm và bỏ là hai việc riêng, cái mới luôn được giữ.
- **Không còn kẹt khi repository có thay đổi chưa lưu.** Javis hỏi ngay tại dòng đó: giữ lại, hay bỏ và xoá các thay đổi. Trước đây chỉ hiện một câu lỗi kèm đường dẫn máy chủ và không có cách nào bỏ.

## en
### Added
- **A clear X to remove a repository.** The repository chip under the chat box has an X: one tap removes it. In the picker, every chosen repository has its own X too. The pinned folder chip next to it and the repository chip on the Teams page get the same X.
- **Harder to tap the wrong thing.** A chosen repository no longer drops when its row is touched, only its X removes it. Any other repository shows a plus: one tap adds it.

### Fixed
- **A repository no longer "jumps back" to the old one.** Switching to another repository while the old one held unsaved changes used to be refused as a whole, so the new pick was lost too. Adding and removing are separate now, and the new pick always stays.
- **No more dead end on a repository with unsaved changes.** Javis asks right on that row: keep it, or remove it and delete the changes. Before, there was only an error with a server path and no way to remove it.
