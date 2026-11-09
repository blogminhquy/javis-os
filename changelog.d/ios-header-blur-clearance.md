---
bump: patch
title: Keep the iPhone home-screen app's header buttons out of iOS's top blur
---
## vi
### Sửa lỗi
- **App Javis trên màn hình chính iPhone (iOS 26/27) hết nhoè hàng nút trên cùng**, kể cả máy chưa xoá icon và thêm lại. Máy nào iOS vẫn vẽ trang dưới đồng hồ thì thanh trên cùng tự cao thêm một chút, nút menu, chuông và nút + nằm dưới vùng iOS làm mờ.
- Máy đã hết nhoè thì không đổi gì. Muốn lấy lại khoảng trống đó: xoá icon Javis rồi thêm vào màn hình chính lại.

## en
### Fixed
- **The iPhone home-screen app (iOS 26/27) no longer blurs the top row of buttons**, even on a phone that kept its old icon. Where iOS still draws the page under the clock, the top bar grows a little so the menu, bell and + buttons sit below the area iOS blurs.
- Phones without the blur look the same as before. To get that space back, remove the Javis icon and add it to the Home Screen again.
