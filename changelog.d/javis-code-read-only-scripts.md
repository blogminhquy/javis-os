---
bump: minor
title: javis_code runs read-only scripts that chain tool calls and return only the result
---
## vi
### Thêm mới
- **Javis chạy được code đọc dữ liệu (`javis_code`).** Model viết một đoạn Python ngắn, gọi nối nhiều tool đọc (lật trang, tra từng đơn, ghép hai nguồn), tự tính rồi chỉ trả phần kết quả, nên dữ liệu thô không chiếm token trong khung chat.
- **Chỉ đọc, chạy cách ly.** Đoạn code chạy trong tiến trình riêng, không có khoá, không đọc file, không ra mạng, và chỉ gọi được tool đọc rõ ràng qua đúng lớp kiểm quyền như bình thường.
- **Có trần an toàn.** Tối đa 40 lần gọi, 120 giây mỗi lượt. Không chạy được thì model tự gọi tool như cũ. Tắt bằng `JAVIS_CODE_MODE=0`.

## en
### Added
- **Javis can run read-only scripts (`javis_code`).** The model writes a short Python script that chains several read calls (paging, looking up each order, joining two sources), computes, and returns only the result, so raw data no longer costs tokens in the chat.
- **Read only and isolated.** The script runs in its own process with no keys, no files and no network, and can call only plainly read-only tools through the usual permission checks.
- **Safe caps.** At most 40 calls and 120 seconds per run. If it cannot run, the model calls the tools itself as before. Turn it off with `JAVIS_CODE_MODE=0`.
