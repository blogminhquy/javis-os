---
bump: patch
title: Background jobs no longer stall on steps only the owner can do
---
## vi
### Sửa lỗi
- **Việc nền không còn bị chặn mãi vì điều kiện máy không làm được.** Trước đây AI đặc tả có thể ghi vào điều kiện hoàn thành những bước như nghe kiểm giọng, duyệt, tải file 67 MB qua công cụ chỉ nhận 10 MB, hay bước của việc khác. Việc đã làm xong phần chính vẫn trượt nghiệm thu mỗi lần chạy. Nay AI đặc tả biết engine nền đang dùng làm được gì và tách các bước đó ra mục **Để lại cho bạn** trên thẻ việc, không tính vào nghiệm thu.
- **Người nghiệm thu không đẩy việc về chạy lại vì phần chỉ người làm được.** Nếu mọi điều kiện còn thiếu đều cần người hoặc vượt giới hạn công cụ, và worker đã nói rõ lý do kèm đường dẫn file, việc được coi là xong và phần đó chuyển sang "Để lại cho bạn". Tin báo kết quả cũng ghi rõ các bước này và rung chuông để bạn không bỏ sót.

## en
### Fixed
- **Background jobs no longer stall on criteria a machine cannot meet.** The specifier could write done-criteria such as listening to voice lines, approving, uploading a 67 MB file through a 10 MB tool, or another job's step, so a job that had finished its real work failed the check on every run. The specifier now knows what the background engine can reach and moves those steps to a **Left for you** section on the job card, outside the acceptance check.
- **The checker no longer sends a job back for steps only a person can do.** When every unmet criterion needs a person or is past a tool's limit, and the worker said why with the file path, the job counts as done and those steps move to "Left for you". The result message lists them too and rings so they are not missed.
