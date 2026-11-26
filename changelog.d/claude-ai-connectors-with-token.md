---
bump: patch
title: claude.ai and ChatGPT connectors work again next to the long-lived token
---
## vi
### Sửa lỗi
- **Kết nối thêm trên claude.ai (Gmail, Lịch, Drive...) dùng lại được khi Claude Code chạy bằng token dài hạn.** Token từ `claude setup-token` chỉ được Claude Code cho quyền gọi model, không kéo được kết nối claude.ai. Nay nếu máy còn phiên đăng nhập claude.ai đầy đủ, Javis chạy bằng phiên đó để có đủ kết nối, còn token giữ làm dự phòng: phiên hết thì lượt đó tự chạy lại bằng token, bot và việc nền không dừng. Thẻ Claude Code ở trang Models nói rõ kết nối claude.ai đang bật hay tắt, kèm nút Bật kết nối claude.ai để đăng nhập lại một lần.
- **Đăng nhập ChatGPT bằng trình duyệt xin đủ quyền như Codex.** Trước đây thiếu quyền dùng app và kết nối của ChatGPT nên Codex không thấy chúng. Ai đã đăng nhập theo đường này thì đăng nhập lại một lần để có đủ.

## en
### Fixed
- **Connectors added on claude.ai (Gmail, Calendar, Drive...) work again while Claude Code runs on the long-lived token.** Claude Code gives a `claude setup-token` token model access only, never claude.ai connectors. Now, when the machine still has a full claude.ai sign-in, Javis runs on it so every connector loads, and keeps the token as the backup: once the sign-in ends, that turn runs again on the token and bots and background work keep going. The Claude Code card on the Models page says whether claude.ai connectors are on or off, with a Turn on claude.ai connectors button for a one-time sign-in.
- **The ChatGPT browser sign-in asks for the same access as Codex.** It used to leave out ChatGPT apps and connectors, so Codex could not see them. Anyone who signed in this way signs in once more to get them.
