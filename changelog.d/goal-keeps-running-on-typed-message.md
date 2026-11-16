---
bump: minor
title: A goal keeps running when you type more, and folds your message into the goal
---
## vi
### Cải thiện
- **Gõ thêm lúc đang theo đuổi mục tiêu không còn làm mục tiêu tạm dừng.** Tin bạn gửi được gộp vào mục tiêu: vòng đang chạy đọc nó ở bước kế tiếp, các vòng sau đều mang theo, nên bạn chỉnh hay mở rộng mục tiêu ngay khi Javis đang làm. Mỗi tin như vậy cho thêm một vòng (tối đa 10). Vòng nào báo đạt mà chưa kịp đọc tin của bạn thì Javis vẫn làm thêm một vòng cho tin đó. Nút Dừng vẫn tạm dừng mục tiêu như trước.

## en
### Improved
- **Typing while a goal runs no longer pauses it.** Your message is added to the goal: the running round reads it at its next step and every later round carries it, so you can adjust or widen the goal while Javis works. Each such message gives one more round (10 at most). If a round reports the goal met before it read your message, Javis runs one more round for it. The Stop button still pauses the goal as before.
