---
bump: patch
title: Zalo OA webhook saves, photos and shared links arrive, Store updates ring
---
## vi
### Sửa lỗi
- **Lưu được webhook Zalo OA.** Bấm Kiểm tra trên Zalo giờ nhận 200 dù Javis chưa có OA secret key (tin chưa ký vẫn bị bỏ, không tới bot), nên hết cảnh kẹt hai đầu: Zalo chỉ hiện khoá sau khi lưu webhook, còn Javis cần khoá mới tạo kênh.
- **Form Zalo OA và Messenger cảnh báo địa chỉ .ts.net.** Địa chỉ Tailscale chỉ mở trong tailnet nên Zalo không gọi tới được (lỗi 408). Form nói rõ cần tên miền riêng hoặc Cloudflare Tunnel.
- **Ảnh khách gửi qua Zalo OA không còn thành tệp 0 byte.** Javis thử lại kiểu trình duyệt, thử ảnh thu nhỏ, và nếu vẫn không tải được thì giữ nguyên đường dẫn gốc của Zalo trong tin thay vì lưu một tệp rỗng.
- **Link khách chia sẻ qua Zalo OA không còn bị mất.** Thẻ link được đọc cả khi Zalo không để địa chỉ ở trường `url`, kèm tiêu đề và mô tả.
- **Store có bản mới thì chuông kêu thật.** Thông báo này trước bị bộ lọc mặc định "chỉ tin khẩn" xếp vào mục Đã lọc. Bấm vào thông báo giờ mở Store đúng nhóm "Có bản mới".

## en
### Fixed
- **The Zalo OA webhook can be saved.** Zalo's Check button now gets 200 even before Javis has the OA secret key (unsigned events are still dropped and reach no bot), which ends the deadlock: Zalo shows the key only after the webhook is saved, and Javis needs the key to create the channel.
- **The Zalo OA and Messenger forms warn about a .ts.net address.** A Tailscale address only opens inside the tailnet, so Zalo cannot reach it (HTTP 408). The form says to use your own domain or a Cloudflare Tunnel.
- **Photos customers send on Zalo OA are no longer saved as 0-byte files.** Javis retries like a browser, tries the thumbnail, and when it still cannot download, keeps Zalo's original address in the message instead of saving an empty file.
- **Links customers share on Zalo OA are no longer lost.** A link card is read even when Zalo does not put the address under `url`, with its title and description.
- **A Store update really rings the bell.** The default "urgent only" filter used to file this notice under Filtered. Pressing it now opens the Store on the "has an update" group.
