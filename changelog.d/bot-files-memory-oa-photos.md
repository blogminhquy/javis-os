---
bump: patch
title: Bots stop sending work files, Zalo OA photos are seen, memory keeps its history
---
## vi
### Sửa lỗi
- **Bot Zalo không còn gửi nhầm file làm việc.** Ở mức Toàn quyền (kể cả chat riêng của chủ với bot), file ghi trong lượt như sổ nhật ký, file `.md`, script trong `/tmp` từng bị gửi đi như ảnh. Giờ bot chỉ gửi ảnh mà câu trả lời chèn bằng `![](...)`.
- **Bot Zalo OA xem được ảnh khách gửi.** Ảnh Zalo trả về không có đuôi được lưu đúng `.jpg`/`.png`; ảnh chưa sẵn thì Javis thử lại, vẫn rỗng thì bot nhờ khách gửi lại thay vì nói "chưa xem được".
- **Bộ nhớ tự học không còn ghi đè file cũ và bớt báo mâu thuẫn giả.** Một ghi nhớ đã có không bao giờ bị thay bằng bản tóm tắt. Nhãn chung như "GROUP:" hay tiêu đề "Bài học tự học" không còn làm hai ghi nhớ không liên quan bị báo là mâu thuẫn.

## en
### Fixed
- **Zalo bots no longer send work files by mistake.** At Full access (the owner's own chat with the bot included), files written during the turn such as logs, `.md` files and scripts in `/tmp` went out as images. A bot now sends only the images its reply embeds with `![](...)`.
- **Zalo OA bots can see the photos customers send.** A photo Zalo serves without an extension is saved as `.jpg`/`.png`; a photo not ready yet is fetched again, and if it stays empty the bot asks the customer to resend instead of saying it cannot see it.
- **Self-learning no longer overwrites a memory and flags fewer false conflicts.** An existing memory is never replaced by a summary. Shared labels like "GROUP:" or the heading the core writes for learned lessons no longer mark two unrelated memories as conflicting.
