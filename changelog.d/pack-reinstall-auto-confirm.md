---
bump: minor
title: Reinstalling a Store pack no longer asks to confirm Auto for each assistant
---
## vi
### Thêm mới
- **Nút "Đúng trợ lý cũ, xác nhận tất cả" theo gói** trên trang Cộng sự. Khi Javis vẫn phải hỏi về nhiều trợ lý của cùng một gói, bấm một lần là xong, không phải mở từng thẻ.

### Sửa lỗi
- **Cài lại gói Store không còn bắt xác nhận Auto từng trợ lý.** Gỡ rồi cài lại một gói (ví dụ ECC: Đội lập trình), Javis tự nhận các trợ lý của gói là trợ lý cũ: công tắc Auto, mục tiêu và cuộc trò chuyện giữ nguyên. File bạn tự tạo trùng tên một trợ lý cũ thì vẫn được hỏi như trước.
- **Trợ lý chưa bật Auto và không có mục tiêu đang mở không còn báo "Cần xác nhận"** khi file của nó mất rồi có lại.

## en
### Added
- **A "Same assistants, confirm all" button per pack** on the Collaborators page. When Javis still has to ask about several assistants of one pack, one click answers for all of them.

### Fixed
- **Reinstalling a Store pack no longer asks to confirm Auto for each assistant.** Uninstall a pack and install it again (for example ECC: Engineering team) and Javis takes its assistants back as the same ones: Auto switch, goals and conversations stay. A file you wrote yourself under an old assistant's name is still asked about, as before.
- **An assistant with Auto off and no open goal no longer shows "Needs confirmation"** when its file goes missing and comes back.
