---
bump: patch
title: The plan usage ring no longer stays red after switching models
---
## vi
### Sửa lỗi
- **Vòng hạn mức gói hết kẹt đỏ sau khi đổi model.** Chọn model khác, hoặc chat xong một lượt bình thường, là vòng tròn đọc lại số ngay thay vì giữ màu đỏ cũ tới 1 tiếng.
- **Một model chạm hạn mức riêng không còn làm đỏ cả gói.** Ví dụ Opus hay Fable bị chặn riêng thì vòng tròn vẫn theo số phiên 5 giờ và tuần, kèm một dòng nhắc tên model đó.

## en
### Fixed
- **The plan usage ring no longer stays red after switching models.** Picking another model, or finishing a normal turn, rereads the meters at once instead of keeping the old red for up to an hour.
- **One model hitting its own limit no longer paints the whole plan red.** When only Opus or Fable is refused, the ring follows the 5-hour and weekly meters and a short line names that model.
