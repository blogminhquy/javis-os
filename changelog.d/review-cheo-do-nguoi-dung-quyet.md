---
bump: minor
title: Cross review is the user's call, off by default, on the chat's own model
---
## vi
### Cải thiện
- **Review chéo trên GitHub giờ do bạn quyết, mặc định tắt.** CI xanh là Javis merge, không tự gọi thêm model nào để review. Muốn review thì bật cho từng repo (thẻ GitHub, dấu ba chấm, Review chéo), bấm **Review ngay** ở biểu tượng GitHub của cuộc trò chuyện, hoặc nhắn "review PR này".
- **Mặc định review bằng chính model đang chat**, không bắt buộc phải là model khác hãng. Chọn model khác được, theo repo hay mỗi lần review.
- **Phát hiện chờ bạn chọn.** Javis không tự gửi đi sửa nữa: dừng merge, hiện danh sách lỗi kèm hai nút **Sửa các lỗi này** và **Bỏ qua, merge**.

## en
### Improved
- **GitHub cross review is now your call, off by default.** Green CI merges, with no extra model called to review. To review, turn it on per repo (GitHub card, the "..." menu, Cross review), press **Review now** on the chat's GitHub icon, or say "review this PR".
- **The review runs on the model you are chatting with by default**; it no longer has to be another vendor. Another model can be picked per repo or per review.
- **Findings wait for your pick.** Javis no longer sends them off to be fixed: it holds the merge and lists them with **Fix them** and **Skip and merge**.
