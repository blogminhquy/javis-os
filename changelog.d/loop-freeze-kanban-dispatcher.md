---
bump: patch
title: Pages and chat switches no longer freeze while background jobs write
---
## vi
### Sửa lỗi
- **Mở trang và đổi hội thoại không còn khựng vài giây khi Javis đang làm việc nền.** Bộ điều phối Kanban (chạy 5 giây một lần) ghi kho việc ngay trên luồng chính của máy chủ, nên mỗi khi kho đang bận là mọi cú bấm phải đứng chờ theo, có lúc hơn 1 giây. Giờ phần đó chạy ở luồng phụ.
- **Lần tự cập nhật Claude Code không còn làm máy chủ đứng 3 giây.** Việc đọc danh sách model từ chương trình `claude` cũng chuyển sang luồng phụ.

### Cải thiện
- **Trang `/health/loop` ghi cả những lần khựng ngắn (từ 0,3 giây).** Mỗi lần được tính vào đúng chỗ code gây ra, xếp theo tổng thời gian mất, để lần sau thấy chậm là biết ngay vì đâu.

## en
### Fixed
- **Pages and chat switches no longer stall for seconds while Javis works in the background.** The Kanban dispatcher (every 5 seconds) wrote its job store on the server's main loop, so whenever that store was busy every click waited too, sometimes over a second. That work now runs on a worker thread.
- **The Claude Code self-update no longer freezes the server for 3 seconds.** Reading the model list out of the `claude` program moved to a worker thread as well.

### Improved
- **`/health/loop` now records short freezes too (from 0.3 seconds).** Each one is counted against the code that caused it and ranked by total time lost, so the next slowdown names its own cause.
