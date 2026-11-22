---
bump: minor
title: Zalo Bot inspects customer videos, transcribes audio files, and guards photo and voice downloads
---
## vi
### Thêm mới
- **Video gửi cho bot Zalo được xem theo khung hình và nghe lời nói.** Khi lượt nhắn được phép trả lời, Javis cắt các khung hình theo thời gian kèm bản chép lời nói (đánh dấu là dữ liệu đính kèm) với giới hạn 180 giây để không chặn các cuộc trò chuyện khác.
- **File âm thanh gửi cho bot Zalo được chép lời như dữ liệu đính kèm.** Nội dung chép lời nằm trong khối dữ liệu riêng thay vì coi như câu lệnh thoại.

### Sửa lỗi
- **Ảnh và tin thoại gửi cho bot Zalo không còn thành file 0 byte.** Khi máy chủ Zalo trả HTTP 202 kèm nội dung rỗng, Javis chờ và hỏi lại trong giới hạn 60 giây qua bộ tải kết nối trực tiếp (bỏ qua `HTTPS_PROXY`, ghim IP công khai), chỉ lưu ảnh khi đúng định dạng và từ chối trang lỗi hay file rỗng.
- **Video thiếu thời lượng ở phần vỏ file và ảnh 0 byte đều được xử lý an toàn.** Video không còn bị rút về một khung hình đầu tiên, và ảnh 0 byte bị từ chối kèm lý do rõ ràng.

## en
### Added
- **Zalo Bot inspects customer videos by sampling frames over time and transcribing speech.** Video work runs off the polling loop after group permission checks with a 180-second timeout, fencing transcribed speech as attached data.
- **Audio files sent to Zalo Bot are transcribed inside an attached-data fence.** Their transcript is treated as untrusted file data rather than a spoken voice command.

### Fixed
- **Photos and voice messages sent to Zalo Bot no longer save as 0-byte files.** When Zalo answers HTTP 202 while a file is not ready yet, Javis retries within a 60-second budget through the direct IP-pinned downloader (with `HTTPS_PROXY` bypassed), checks image magic bytes, and refuses empty bodies or error pages.
- **Videos missing container duration and 0-byte images are handled safely.** Videos without header duration no longer collapse to a single opening frame, and 0-byte images are refused with a clear reason.
