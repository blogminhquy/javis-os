---
bump: patch
title: Zalo Bot photos and voice messages no longer arrive as empty files
---
## vi
### Sửa lỗi
- **Ảnh và tin thoại gửi cho Zalo Bot không còn thành file 0 byte.** Khi máy chủ Zalo chưa kịp có file, Javis chờ chút rồi tải lại, vẫn qua proxy của máy như trước. Tải hỏng thì bot nói thật là chưa xem hay chưa nghe được và nhờ khách gửi lại, không đoán nội dung.
- **File và video gửi qua Zalo đang chờ máy chủ Zalo chuẩn bị thì được đợi thêm vài giây**, không còn báo nhầm là link đã hết hạn.
- **Video không ghi thời lượng ở phần đầu file vẫn được xem đủ cả clip**, không chỉ một khung hình ở giây đầu tiên.

## en
### Fixed
- **Photos and voice messages sent to Zalo Bot no longer turn into 0-byte files.** When Zalo's server does not have the file yet, Javis waits a moment and asks again, still through the server's proxy as before. If it still fails, the bot says plainly it has not seen or heard it and asks the customer to resend, without guessing.
- **Files and videos sent over Zalo that the Zalo server is still preparing get a few more seconds**, instead of being reported as an expired link.
- **Videos without a duration in their header are sampled across the whole clip**, not reduced to one frame at the first second.
