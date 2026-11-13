---
bump: patch
title: Dictation stops at once and the rewrite is much faster
---
## vi
### Sửa lỗi
- **Bấm dừng ghi âm phản hồi ngay.** Thanh ghi chuyển sang "Đang viết lại câu cho đúng" ngay khi bấm, và đoạn ghi âm được gửi đi nghe lại luôn chứ không chờ trình duyệt đóng mic xong.
- **Bước viết lại câu nhanh hơn nhiều.** Lớp sửa từ trước đó có lúc tốn vài giây, nay chỉ vài phần trăm giây. Model nhanh không còn "nghĩ" hết lượt rồi trả câu rỗng, máy chạy gói đăng ký thì model chính nghĩ ở mức thấp nhất cho việc này.
- **Đọc dài không còn mất chữ.** Câu dài hơn khoảng 2.000 ký tự trước đây bị cắt cụt sau bước viết lại, nay giữ đủ từng chữ.
- **Bớt đổi nhầm chữ thường thành tên riêng.** "đã viết" không còn thành "Javis", "cần và" không còn thành "Canva".

## en
### Fixed
- **Stopping a dictation answers at once.** The bar switches to "rewriting" the moment stop is pressed, and the recording goes to be heard right away instead of waiting for the browser to close the mic.
- **The rewrite step is much faster.** The word fix that runs first could take several seconds and now takes a few hundredths of one. The quick model no longer spends its whole turn thinking and returns nothing, and on a subscription the main model thinks at its lowest level for this job.
- **Long dictations no longer lose words.** Text over about 2,000 characters used to come back cut after the rewrite; every word is kept now.
- **Fewer everyday words turned into names.** Common Vietnamese word pairs that merely sound like "Javis" or "Canva" are no longer replaced by those names.
