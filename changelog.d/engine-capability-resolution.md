---
bump: minor
title: Unified provider and model capability checks across agents, teams, and runtime
---
## vi
### Thêm mới
- **Một nguồn quy tắc chung (`server/engine_capability.py`)** kiểm tra khả năng và cấu hình hiệu lực của từng cặp `provider / model` theo 4 chế độ chạy (`solo_chat`, `team_text`, `team_tool_full`, `team_tool_gated`), tách bạch 4 tầng bằng chứng và không tự đổi sang provider khác hay model chính khi lỗi.
- **Xem trước tác động trước khi đổi cấu hình dùng chung:** `POST /models/main/impact` và `POST /agents/impact` cảnh báo những cộng sự, nhóm và quy trình sẽ bị ảnh hưởng trước khi lưu.

### Cải thiện
- **Kiểm tra cấu hình ngay từ đầu trên mọi đường vào:** lưu cộng sự (`POST /agents` và công cụ admin), tạo nhóm, thêm thành viên, đổi trưởng nhóm và nhập gói nhóm (`team_bundle`) đều dùng chung một quy tắc, giữ nguyên cặp `provider / model` khi xuất/nhập nhóm.
- **Giao diện Cộng sự, Nhóm và Model:** hiển thị rõ model hiệu lực, nguồn kế thừa, trạng thái từng chế độ chạy và cách sửa ngay tại chỗ; bỏ hành vi tự chọn ngầm provider/model đầu tiên; ánh xạ rõ các mã lỗi thay cho "Không rõ lý do" và thay nút Thử lại bằng "Sửa cấu hình" khi gặp lỗi cấu hình.
- **Ngăn lặp bước hỏng cấu hình khi làm việc nhóm:** việc bị chặn bởi lỗi cấu hình dừng ngay với `block_kind="config"`, chỉ gửi một thông báo kèm hướng dẫn theo đúng các provider chạy được trên máy, và nút Thử lại kiểm tra lại cấu hình hiện tại trước khi chạy.

## en
### Added
- **Unified capability and resolution rules (`server/engine_capability.py`)** evaluating each `provider / model` pair across four run modes (`solo_chat`, `team_text`, `team_tool_full`, `team_tool_gated`) with four separate evidence layers and no silent fallback to another provider or the main model.
- **Impact preview before changing shared configs:** `POST /models/main/impact` and `POST /agents/impact` surface affected assistants, teams, and workflows before saving.

### Improved
- **Consistent upfront validation across all entry points:** `POST /agents`, team admin tools, team creation, member addition, leader changes, and team bundle export/import share one validation contract and preserve per-member `provider / model` pairs.
- **Clearer configuration UX:** shows effective `provider / model`, inheritance source, per-mode capability chips, and inline fixes; removes silent first-provider/model auto-selection; maps all error codes cleanly instead of "Unknown reason" and replaces Retry with "Fix config" on configuration errors.
- **Single-notice config blocks in team jobs:** configuration errors block the job once with `block_kind="config"` and machine-accurate provider choices, and retry re-checks the current config before queuing a new step.
