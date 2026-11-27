---
bump: minor
title: Read Facebook Page and post insights, and run SELECT on a read-only Supabase connection
---
## vi
### Thêm mới
- **Javis đọc được số liệu Fanpage và từng bài** (lượt xem, người xem, tương tác, lượt theo dõi, click) bằng Trang đã nối ở thẻ Facebook Messenger, không cần kết nối riêng. Cần tick "Đọc số liệu bài viết" khi nối Trang.
- **Supabase ở mức Chỉ đọc chạy được câu SELECT** khi kết nối là máy chủ MCP chính thức của Supabase có `read_only=true`. Câu ghi, nhiều câu một lúc hay hàm có tác dụng phụ vẫn bị chặn.
### Bảo mật
- **Kết nối MCP tự thêm ở mức Chỉ đọc không còn chạy được tool đổi dữ liệu có tên lạ** như `apply_migration`, `reset_branch`, `pause_project` (trước đây bị nhận nhầm là tool đọc).

## en
### Added
- **Javis reads Facebook Page and post insights** (views, viewers, engagement, follows, clicks) through the Pages connected on the Facebook Messenger card, no separate connection needed. Tick "Read post insights" when connecting the Page.
- **Supabase at Read only can run SELECT** when the connection is Supabase's official MCP server with `read_only=true`. Writes, several statements at once and functions with side effects stay blocked.
### Security
- **A custom MCP connection at Read only can no longer run data-changing tools with unusual names** such as `apply_migration`, `reset_branch`, `pause_project` (they used to be taken for reads).
