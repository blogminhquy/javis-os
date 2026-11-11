---
bump: patch
title: Sign in to MCP servers whose OAuth metadata sits on another host
---
## vi
### Sửa lỗi
- **Đăng nhập được MCP có thông tin OAuth đặt ở máy chủ khác (impact.com).** Trước đây thẻ kết nối báo máy chủ không khai OAuth chuẩn MCP. Nay Javis đọc thông tin đó khi nó nằm trên https công khai, do chính địa chỉ MCP đã khai trả về, và đúng là của địa chỉ đó.
### Bảo mật
- **Kết nối Chỉ đọc không còn xin phạm vi dạng `mcp:write`.** Khi đăng nhập theo kiểu Javis tự dò và máy chủ có sẵn phạm vi đọc (vd `mcp:read`), kết nối đặt Chỉ đọc bỏ các phạm vi có tên kết thúc bằng `write`. Kiểm tra tên tool của hub vẫn là lớp chặn chính. Nâng mức quyền sau đó thì phải đăng nhập lại.
## en
### Fixed
- **MCP servers with OAuth metadata on another host sign in (impact.com).** The card used to say the server declares no standard MCP OAuth. Javis now reads that metadata when it is on public https, returned by the MCP URL that was entered, and names that URL.
### Security
- **Read-only connections stop asking for `mcp:write` style scopes.** On a discovered sign-in where the server offers a read scope (for example `mcp:read`), a connection set to read-only leaves out scopes whose name ends in `write`. The hub's tool-name check stays the main guard. Raising the level later needs a new sign-in.
