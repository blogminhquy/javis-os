---
bump: patch
title: Chat GitHub icon no longer stays orange after a merge
---
## vi
### Sửa lỗi
- **Biểu tượng GitHub trong danh sách chat không còn kẹt màu cam sau khi đã merge.** Khung chat có hai repo mà chỉ một repo có việc thì giờ hiện đúng màu "đã merge". Repo kia nếu chưa đụng tới thì không kéo trạng thái lệch đi nữa.
- **Repo bị chặn ở bước kiểm tra trước khi đẩy giờ hiện màu đỏ "cần người xem"**, kèm lý do. Trước đây nó cứ nhấp nháy cam như đang làm, nhất là sau khi khởi động lại Javis, trông như Javis bỏ quên repo đó.

## en
### Fixed
- **The chat's GitHub icon no longer stays orange after a merge.** A chat with two repos where only one had work now shows "merged". An untouched repo no longer skews the state.
- **A repo blocked by the pre-push checks now shows red "needs a person"** with the reason. It used to pulse orange as if Javis were working on it, mostly after a restart, so the repo looked forgotten.
