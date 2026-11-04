---
bump: patch
title: Plan names come from the vendor, so Claude Ultra shows as Ultra
---
## vi
### Sửa lỗi
- **Tên gói hiện đúng như nhà cung cấp đặt.** Anthropic đổi gói Max 20x thành Ultra ngày 30/10/2026 nhưng Javis vẫn ghi "Max", vì trước giờ tên gói lấy từ một bảng điền tay. Nay thẻ Claude Code ở trang Models, vòng tròn hạn mức cạnh ô chat và câu báo hết lượt trên trang Việc đọc đúng tên mà máy chủ Anthropic trả về (Claude Code tự lưu tên này trong file cấu hình của nó, không đụng tới token). Nhà cung cấp đổi tên lần sau thì Javis tự hiện tên mới, không cần ra bản cập nhật. Claude Code bản cũ chưa lưu tên thì Javis chỉ làm gọn mã gói như trước.

## en
### Fixed
- **Plan names now match what the vendor calls them.** Anthropic renamed Max 20x to Ultra on 2026-10-30, but Javis still said "Max" because plan names came from a hand-kept table. The Claude Code card on the Models page, the usage ring next to the chat box and the out-of-quota note on the Tasks page now read the name Anthropic's server returns (Claude Code keeps it in its own config file, no token is touched). The next time a vendor renames a plan, Javis shows the new name without an update. An older Claude Code that does not store the name falls back to the tidied plan code as before.
