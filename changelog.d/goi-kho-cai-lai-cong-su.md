---
bump: patch
title: Store agents come back after rename or delete, and the Store stops saying installed
---
## vi
### Sửa lỗi
- **Cài lại trợ lý từ Kho nay hiện lại ở trang Cộng sự.** Trước đây đổi tên hay sửa trợ lý của gói, gỡ rồi cài lại thì Javis lặng lẽ bỏ qua. Nay bản của bạn giữ nguyên, bản của gói được cài thêm dưới tên mới (ví dụ `javis-vu-2`) và màn hình nói rõ tên đó.
- **Xoá trợ lý, quy trình, kỹ năng của gói trong app thì Kho thôi báo "Đã cài".** Thẻ hiện lại nút Cài để lấy lại.
- **Gỡ gói dọn sạch kỹ năng:** kể cả kỹ năng đang tắt và bản sao cho Claude Code, nên kỹ năng đã gỡ không còn được nạp ngầm.
- **Brain còn dùng thư mục cũ `Javis/agents`** cài trợ lý từ Kho không còn làm mất các trợ lý đang có.

## en
### Fixed
- **Reinstalling a Store agent brings it back on the Partners page.** Renaming or editing a pack's agent, uninstalling and installing again used to skip it silently. Your copy is kept and the pack's copy is added under a new name (for example `javis-vu-2`), named on screen.
- **Deleting a pack's agents, workflows or skills in the app makes the Store stop saying "Installed".** The card offers Install again.
- **Uninstalling a pack cleans up its skills fully,** including a turned-off skill and the copy Claude Code loads, so a removed skill no longer loads in the background.
- **A brain still on the old `Javis/agents` folder** no longer loses its agents when a Store agent is installed.
