---
bump: minor
title: Cold cache opens a fresh thread, and the Usage page shows where Claude tokens go
---
## vi
### Thêm mới
- **Chat dài quay lại sau hơn 1 giờ nghỉ không còn đọc lại cả mạch.** Bộ nhớ đệm của Claude Code và ChatGPT chỉ sống khoảng 1 giờ. Khi nó đã nguội và mạch cũ to gấp đôi trở lên so với một mạch mới mồi từ bản ghi hội thoại, Javis mở mạch mới và báo một dòng trong chat, đỡ được phần lớn số token phải ghi lại. Chat đang bật Giữ ấm bộ nhớ đệm thì giữ nguyên mạch.
- **Trang Mức dùng có bảng "Vì sao tốn token (Claude)".** Đếm từ từng lượt gọi Claude Code đã ghi trên máy: số lần và số token mất vì cache nguội, vì đổi model giữa chat, và phần token nằm ở các lượt có ngữ cảnh trên 200k. Cache nguội ngốn từ 5% token vào trở lên thì phần Đề xuất cảnh báo.

## en
### Added
- **A long chat resumed after more than an hour no longer re-reads its whole thread.** The Claude Code and ChatGPT prompt cache lives about an hour. Once it has gone cold and the old thread is at least twice the size of a fresh one seeded from the saved conversation, Javis starts a fresh thread and says so in one line in the chat, saving most of the tokens that would have been written again. A chat kept warm by cache keep-warm keeps its thread.
- **The Usage page has a "Where Claude tokens go" table.** Counted from every Claude Code request logged on the machine: how many times and how many tokens were lost to a cold cache and to a model switch mid-chat, and the share of tokens in requests with more than 200k of context. Suggestions warn when the cold cache takes 5% or more of input tokens.
