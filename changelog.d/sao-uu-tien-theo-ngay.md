---
bump: patch
title: Priority stars count per day of the task
---
## vi
### Sửa lỗi
- **Gắn sao trước cho việc ngày mai được rồi.** Sao ưu tiên giờ tính theo ngày của chính việc đó: mỗi ngày tối đa 3 sao riêng, sao của hôm nay không còn chặn việc gắn sao cho ngày mai, và gắn sao việc ngày mai thì việc vẫn nằm ở ngày mai (trước đây bị kéo về hôm nay). Chỉ việc chưa có ngày hoặc đã quá hạn mới được đưa về hôm nay khi gắn sao.

## en
### Fixed
- **You can star tomorrow's tasks ahead of time.** A priority star now counts for its task's own day: each day has its own 3 slots, today's stars no longer block starring tomorrow, and starring a task for tomorrow keeps it on tomorrow (it used to be pulled to today). Only an undated or overdue task is brought to today when starred.
