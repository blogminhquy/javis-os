---
bump: minor
title: Antigravity resumes the main chat's thread and recovers a lost one in the same turn
---
## vi
### Thêm mới
- **Antigravity nhớ mạch ở khung chat chính.** Từ lượt thứ hai chỉ gửi câu hỏi mới, không gửi lại cả lịch sử, nên nhanh và nhẹ hơn. Mạch bị mất hay đổi tài khoản thì Javis tự chạy lại ngay trong lượt đó với đủ ngữ cảnh. Tắt bằng `JAVIS_AGY_RESUME=0`.
- **Thẻ Antigravity ở trang Models ghi bản agy đang chạy, lần cập nhật gần nhất và lỗi nếu có.**

### Sửa lỗi
- **Số token của Antigravity đúng theo từng lượt.** Trước đây con số cộng dồn cả mạch nên đẩy việc nén mạch sớm.
- **Gợi ý tool MCP cho Antigravity gọi đúng tên** `call_mcp_tool` kèm ServerName.

## en
### Added
- **Antigravity keeps its thread in the main chat.** From the second turn only the new question is sent, not the whole history, so turns are faster and lighter. A lost thread or a switched account reruns in the same turn with full context. Turn it off with `JAVIS_AGY_RESUME=0`.
- **The Antigravity card on the Models page shows the agy version, its last update and any update error.**

### Fixed
- **Antigravity token counts are per turn.** They used to add up over the whole thread and pushed compaction too early.
- **The MCP tool hint for Antigravity names the real tool,** `call_mcp_tool` with its ServerName.
