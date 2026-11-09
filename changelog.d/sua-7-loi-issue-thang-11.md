---
bump: patch
title: Fix seven reported bugs (Codex tools, memory frontmatter, Ollama Local teams, proxy, GitHub checks, CapCut)
---
## vi
### Sửa lỗi
- **ChatGPT (Codex) không còn mất công cụ khi chat nghỉ vài phút rồi nhắn tiếp.** Lịch, Zalo, Drive dùng được ngay ở lượt sau. Trên Windows, việc nền Codex mức "Được ghi" ghi được file trở lại.
- **Ký ức không còn bị hỏng hay mất thông tin sau lượt chat.** Ký ức có dấu hai chấm trong mô tả giữ nguyên loại, mô tả và thẻ. Ký ức đã hỏng từ trước tự lành khi sửa trong app.
- **Ollama Local chạy được việc nhóm và việc nền.** Hết báo "engine chưa sẵn sàng" khi Ollama ở máy nhà không đặt khoá.
- **Kết nối ổn hơn:** chạy sau Caddy (VPS Hostinger) thì nút Đăng nhập Facebook không còn bị khoá, thẻ CapCut đăng nhập được, GitHub trong chat dùng đúng Lệnh kiểm tra đã lưu và hiểu repo đặt app trong thư mục con.

## en
### Fixed
- **ChatGPT (Codex) keeps its tools when a chat resumes after a few idle minutes.** Calendar, Zalo and Drive work on the next turn. On Windows, Codex background work at the "Can write" level writes files again.
- **Memories no longer break or lose their details after a chat turn.** A memory with a colon in its description keeps its type, description and tags. A memory already broken heals when edited in the app.
- **Ollama Local runs Team jobs and background work.** No more "engine is not ready" when Ollama at home has no key.
- **Steadier connections:** behind Caddy (Hostinger VPS) the Facebook sign-in button is no longer locked, the CapCut card signs in, and GitHub in chat uses the saved check commands and understands apps in a subfolder.
