---
bump: patch
title: GitHub connects and disconnects go in the security log, and a failed check says so
---
## vi
### Bảo mật
- **Mỗi lần kết nối, đổi tài khoản hay ngắt GitHub đều vào nhật ký bảo mật.** Ghi tài khoản Javis đã làm, IP thật và thiết bị, rồi báo ngay cho chủ. Javis tự gia hạn token thì không ghi.

### Sửa lỗi
- **Kiểm tra GitHub bị lỗi thì hiện "Không kiểm tra được", không còn báo nhầm "Chưa kết nối".** Áp dụng cho thẻ GitHub, khung chat, Team và ô sao lưu brain, kèm lý do và nút Thử lại.

## en
### Security
- **Every GitHub connect, account switch and disconnect goes in the security log.** It names the Javis account, the real IP and the device, and alerts the owner. A token renewal by Javis is not logged.

### Fixed
- **A failed GitHub check now reads "Could not check" instead of a false "Not connected".** This covers the GitHub card, the chat box, Teams and the brain backup box, with the reason and a Retry button.
