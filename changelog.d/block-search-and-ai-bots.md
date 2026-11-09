---
bump: minor
title: Keep a leaked admin link out of search engines and away from AI bots
---
## vi
### Bảo mật
- **Lỡ lộ link quản trị thì Google không đưa lên kết quả tìm kiếm.** Mọi trang của Javis giờ mang lệnh `noindex`, kể cả màn hình đăng nhập và link chia sẻ.
- **Bot AI không đọc được Javis.** GPTBot, ClaudeBot, PerplexityBot, công cụ SEO và máy quét như Shodan, Censys nhận lỗi 403, không thấy chữ nào. Javis cũng có `/robots.txt` cấm chúng.
- Trình duyệt thật, khung xem trước link khi dán vào Zalo hay Telegram, webhook và Javis Gate vẫn chạy như cũ. Cần tắt lớp chặn thì đặt `JAVIS_BLOCK_BOTS=0`.

## en
### Security
- **A leaked admin link stays out of Google.** Every Javis page now carries `noindex`, the login screen and share links included.
- **AI bots cannot read Javis.** GPTBot, ClaudeBot, PerplexityBot, SEO tools and scanners such as Shodan and Censys get a 403 and see nothing. Javis also serves a `/robots.txt` that forbids them.
- Real browsers, link previews in Zalo or Telegram, webhooks and Javis Gate work as before. To turn the blocking off, set `JAVIS_BLOCK_BOTS=0`.
