---
bump: patch
title: Zalo Bot photos, voice messages and videos no longer turn into empty files
---
## vi
### Sửa lỗi
- **Ảnh gửi cho bot Zalo không còn thành file 0 byte.** Máy chủ ảnh Zalo trả HTTP 202 với nội dung rỗng trong lúc ảnh chưa sẵn sàng, và Javis cũ lưu luôn file `.jpg` rỗng rồi báo "đã tải về". Giờ Javis chờ và hỏi lại vài lần; ảnh và tin thoại đi qua bộ tải có kiểm tra: rỗng, trang lỗi, lỗi HTTP hay quá lớn thì không lưu gì và nói rõ bước nào hỏng. Ảnh chỉ được giữ khi mấy byte đầu đúng là ảnh.
- **Video gửi cho bot Zalo được xem theo khung hình và nghe lời nói**, như bot khách trên Zalo cá nhân. Lời nói trong video được ghi là dữ liệu kèm theo, không phải lệnh.
- **Video thiếu thời lượng ở phần vỏ file** không còn bị rút về một khung hình đầu tiên.
- **Xem ảnh không còn gửi một ảnh rỗng cho model**: file 0 byte bị từ chối kèm lý do.

## en
### Fixed
- **Photos sent to the Zalo Bot no longer become 0-byte files.** Zalo's photo servers answer HTTP 202 with an empty body while a photo is not ready yet, and Javis saved that as an empty `.jpg` and said it was downloaded. Javis now waits and asks again a few times; photos and voice messages go through the guarded downloader: an empty body, an error page, an HTTP error or an oversized file keeps nothing and names the failing step. A photo is kept only when its first bytes prove an image.
- **Videos sent to the Zalo Bot are looked at as frames over time, with their speech heard**, like the customer bot on personal Zalo. The speech is marked as attached data, not a command.
- **A video without a container duration** is no longer reduced to its first frame.
- **Looking at an image never sends an empty image to the model**: a 0-byte file is refused with the reason.
