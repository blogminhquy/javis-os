---
bump: minor
title: Each brain pins the tools it uses most, so they skip the search round
---
## vi
### Thêm mới
- **Công cụ hay dùng được ghim sẵn theo từng brain.** Khi brain đấu nhiều nguồn, công cụ phải "tìm rồi mới gọi", tốn thêm một vòng mỗi lần dùng. Giờ Javis tự đếm công cụ nào mỗi brain gọi nhiều nhất và ghim sẵn vài cái (mặc định tối đa 4, Javis Core tự nới tới 8 khi cần): công cụ đã ghim được gọi thẳng. Việc nền như loop được lợi nhiều nhất vì trước đây lần nào cũng phải tìm lại. Không phải cài gì, có thông báo ở chuông khi ghim.
- **Xem và tắt bằng lời.** Hỏi Javis "đang ghim công cụ nào" để xem danh sách kèm số lượt gọi thẳng và số lượt còn phải tìm. Nói "đừng ghim công cụ nữa" để tắt.

### Cải thiện
- **Danh sách ghim tự theo thói quen.** Công cụ lâu không dùng tự rời danh sách, công cụ mới dùng nhiều tự vào. Danh sách của một brain đổi nhiều nhất một lần mỗi ngày và có giới hạn kích thước, nên prompt không phình và phần lưu đệm của nhà cung cấp ít bị làm mới.
- **Điều bạn dặn Javis Core được giữ nguyên.** Một giá trị bạn đặt bằng lời cho bất kỳ núm tự chỉnh nào thì Javis Core không tự đổi lại trong 30 ngày, kể cả sau khi khởi động lại.

## en
### Added
- **Each brain pins the tools it uses most.** When a brain has many sources connected, a tool must be searched for before it is called, one extra round each time. Javis now counts which tools each brain calls most and pins a few of them (up to 4 by default; Javis Core widens that up to 8 when needed): a pinned tool is called directly. Background work such as loops gains the most, because it had to search again on every run. Nothing to set up, and a notice in the bell tells you when tools are pinned.
- **See and switch it off by talking.** Ask Javis "which tools are pinned" for the list with how many calls went direct and how many still needed a search. Say "stop pinning tools" to turn it off.

### Improved
- **The pinned list follows your habits.** A tool you stop using leaves the list and a newly frequent one joins. One brain's list changes at most once a day and has a size bound, so the prompt does not grow and the provider's cache is rarely refreshed.
- **What you tell Javis Core stands.** A value you set by talking, for any self-tuning knob, is not changed back by Javis Core for 30 days, restarts included.
