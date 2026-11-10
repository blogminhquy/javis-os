---
bump: minor
title: Javis Core runs one improvement loop for everything that tunes itself
---
## vi
### Thêm mới
- **Javis Core giữ một vòng cải tiến chung.** Phần nào của Javis muốn tự điều chỉnh thì đăng ký một "núm chỉnh" với Javis Core. Vòng dời núm theo cùng một cách: mỗi lần một bước, trong khoảng cho phép, nhiều nhất một lần mỗi ngày, có ghi lý do, có thông báo ở chuông và hoàn lại được bằng lời. Vòng này chỉ là mã, không gọi model và không chạm vào lượt chat.
- **Tự học tự chỉnh ngưỡng mở mẻ.** Khi phần lớn các mẻ học gần đây không rút ra được gì (thường gặp khi bạn hay hỏi nhanh một hai câu), Javis Core tự nâng số lượt cần có trước khi mở một mẻ; các mẻ có ích trở lại thì tự hạ xuống. Lượt chưa đủ ngưỡng vẫn nằm chờ và được học cùng các lượt sau.
- **Dặn Javis nên học thế nào, bằng lời.** Nói "đừng ghi doanh thu từng ngày thành ghi nhớ" hay "chỉ ghi nhớ quyết định đã chốt": Javis Core giữ thành một bài học và mọi mẻ tự học đọc nó trước. Xem và thu hồi như bài học của mọi trợ lý.

### Cải thiện
- **Ghi nhớ học sai được tính vào kết quả.** Một ghi nhớ Javis tự học mà bạn bảo xoá được tính là một lần học sai, nên mẻ học sau tự dùng model mạnh hơn một bậc. Ghi nhớ do bạn tự viết bị xoá thì không ảnh hưởng gì.
- **Một chỗ để xem và hoàn lại.** Hỏi Javis "việc nền và tự học đang chỉnh gì": một câu trả lời gồm model của từng việc nền, các núm đang tự chỉnh, các thay đổi gần đây và bài học về cách học.

## en
### Added
- **Javis Core runs one improvement loop.** Any part of Javis that wants to tune itself registers a "knob" with Javis Core. The loop moves every knob the same way: one step at a time, inside its bounds, at most once a day, with its reason logged, a notice in the bell, and a way back by talking. The loop is plain code: it calls no model and does not touch a chat turn.
- **Self-learning tunes when a batch starts.** When most recent batches learned nothing (common when you ask one or two quick questions), Javis Core raises the number of turns a batch needs; when batches are useful again it lowers it. Turns below the bar stay queued and are learned with the next ones.
- **Tell Javis how to learn, by talking.** Say "do not turn each day's revenue into a memory" or "only remember settled decisions": Javis Core keeps it as a lesson and every learning batch reads it first. Review and revoke it like any assistant's lessons.

### Improved
- **A wrongly learned memory counts.** A memory Javis learned by itself that you ask it to forget counts as a learning mistake, so the next batch runs one model stronger. Forgetting a memory you wrote yourself changes nothing.
- **One place to look and to undo.** Ask Javis "what is background work and learning adjusting": one answer with the model of each background job, the knobs being tuned, the recent changes and the lessons about learning.
