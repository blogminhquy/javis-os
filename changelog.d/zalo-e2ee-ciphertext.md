---
bump: patch
title: Encrypted Zalo chats show a clear line instead of scrambled text
---
## vi
### Sửa lỗi
- **Cuộc chat Zalo bật mã hoá đầu cuối không còn hiện chuỗi ký tự lạ.** Zalo chỉ cho app trên máy đã bật mã hoá đọc những tin này, nên Hộp thư nay hiện "Tin nhắn mã hoá đầu cuối: chỉ xem được trong app Zalo". Bot không trả lời những tin đó nữa và không báo nhầm "có người gọi A.I.". Tin đã lưu từ trước cũng được đổi lại khi Javis khởi động.

## en
### Fixed
- **End-to-end encrypted Zalo chats no longer show scrambled text.** Only the Zalo app on a device that joined the encryption can read them, so the inbox now says "End-to-end encrypted message: open the Zalo app to read it". The bot no longer answers them or reports a false "someone asked for A.I.". Messages stored earlier are relabelled when Javis starts.
