---
bump: patch
title: Long answers stream without stutter, the home screen rests lighter
---
## vi
### Cải thiện
- **Câu trả lời dài chảy ra không còn khựng.** Trong lúc chữ đang về, Javis chỉ vẽ lại đoạn đang viết dở, các đoạn đã xong giữ nguyên. Đo với một câu trả lời 20.000 ký tự trên điện thoại yếu: thời gian vẽ từ 5,4 giây xuống 1 giây, hết hẳn các lần đứng hình.
- **Màn chính lúc rảnh nhẹ máy hơn.** Nền sao sau quả cầu vẽ thưa lại khi không ai nói và Javis không nghĩ, nhìn vẫn như cũ. Điện thoại đỡ nóng và đỡ hao pin khi để mở.

### Sửa lỗi
- **Trang Models không còn làm app ì dần.** Mỗi lần mở trang để lại một lớp theo dõi thao tác kéo thả không bao giờ gỡ. Nay chỉ còn một lớp dùng chung.

## en
### Improved
- **Long answers stream without stutter.** While text is arriving, Javis only redraws the block being written and leaves the finished ones alone. Measured with a 20,000 character answer on a slow phone: render time from 5.4 seconds down to 1 second, and no more freezes.
- **The home screen rests lighter.** The starfield behind the sphere draws less often when nobody is speaking and Javis is not thinking, and looks the same. A phone left open runs cooler and uses less battery.

### Fixed
- **The Models page no longer slows the app down over time.** Every visit left a set of drag listeners behind that was never removed. One shared set remains.
