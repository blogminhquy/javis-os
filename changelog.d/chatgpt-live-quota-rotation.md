---
bump: patch
title: ChatGPT Live moves to the next account or call path when the plan runs out
---
## vi
### Sửa lỗi
- **Gọi giọng không còn kẹt ở ChatGPT Live khi gói ChatGPT hết lượt.** Trước đây cuộc gọi cứ mở lại đúng tài khoản đã cạn và báo lỗi "You've hit your usage limit" mãi, dù đã đổi model chính sang gói khác. Giờ tài khoản đó được cho nghỉ tới giờ mở lại, cuộc gọi tự chuyển ngay sang tài khoản ChatGPT thứ hai, hết nữa thì sang Live qua API key, rồi đường Cơ bản (trả lời bằng model chính).
- **ChatGPT Live dùng được tài khoản ChatGPT thứ hai.** Trước đây gọi giọng chỉ chạy trên tài khoản 1.
- **Đường Cơ bản không chọn lại ChatGPT đã hết lượt** làm bộ não trả lời nhanh: chờ tới giờ mở lại, lượt nói đi bộ não khác.
- **Lỗi hết lượt chỉ hiện một lần**, kèm giờ mở lại đọc từ câu "try again at 8:42 AM" (đường chat cũng đọc được giờ này).

## en
### Fixed
- **Voice calls no longer stay stuck on ChatGPT Live when the ChatGPT plan runs out.** The call used to reopen the same empty account and show "You've hit your usage limit" again and again, even after the main model was switched to another plan. That account now rests until its reset time and the call moves at once to the second ChatGPT account, then to Live with an API key, then to the Basic path (answered by the main model).
- **ChatGPT Live can run on a second ChatGPT account.** Voice calls used to run on account 1 only.
- **The Basic path no longer picks an exhausted ChatGPT** as its quick-reply brain: until the reset, turns go to another brain.
- **The out-of-quota error shows once**, with the reset time read from "try again at 8:42 AM" (chat reads that time too).
