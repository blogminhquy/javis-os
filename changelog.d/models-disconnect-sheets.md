---
bump: minor
title: New Models page, Disconnect on every card, Advanced API key, extra Google accounts, quota routing fixes
---
## vi
### Thêm mới
- **Trang Model làm mới theo kiểu trang Nhiệm vụ.** Mỗi thẻ có logo thật của nhà cung cấp, hàng nút có icon (Dùng cho việc nền, Kiểm tra, Thêm tài khoản hay key, Ngắt) và nút ⋯ mở bảng kéo từ dưới lên với đủ thao tác. Thẻ chạy việc nền mang nhãn VIỆC NỀN.
- **API key nâng cao.** Cắm nhiều key của các nhà bán khác nhau (Kimi, MiniMax, bên bán lại Claude...), mỗi key một địa chỉ. Key đang dùng hết lượt thì Javis tự sang key kế.
- **Antigravity có nút Ngắt, và thêm được tài khoản Google** trên máy Linux hoặc VPS để xoay vòng khi một tài khoản hết lượt.

### Sửa lỗi
- **Gói Google hết lượt thì chat chuyển sang thẻ khác thật.** Trước đây Javis không đánh dấu Antigravity hết lượt, nên cứ chạy lại nó và báo "chưa có bộ não nào khác" dù ChatGPT đang đăng nhập.
- **Chọn ChatGPT là ChatGPT chạy.** Một dấu "hết lượt" cũ không còn kéo chat về Google: chọn thẻ nào thì thẻ đó được thử, và thẻ đang tạm nghỉ hiện rõ tới mấy giờ kèm nút Dùng lại ngay.

### Cải thiện
- **Không còn menu xổ xuống.** Chọn model, độ sâu suy nghĩ (giữ nguyên thanh trượt, có nút tia sét), menu từng key, form thêm và câu hỏi trước khi Ngắt đều là bảng kéo lên. Gói Claude ghi đúng tên Pro và Ultra.

## en
### Added
- **A new Models page in the Tasks page's style.** Each card shows the provider's real logo, a row of icon buttons (Use for background work, Check, Add an account or key, Disconnect) and a ⋯ button that opens a pull-up sheet with every action. The card that runs background work carries a BACKGROUND badge.
- **Advanced API key.** Plug in keys from different sellers (Kimi, MiniMax, Claude resellers...), each with its own address. When the key in use runs out, Javis moves to the next key.
- **Antigravity gets Disconnect, and extra Google accounts** on Linux machines or a VPS, used in turn when one runs out.

### Fixed
- **A Google plan out of quota now hands the chat to another card.** Javis did not mark Antigravity as out of quota, so it kept running it and said "no other brain is connected" while ChatGPT was signed in.
- **Choosing ChatGPT runs ChatGPT.** An old out-of-quota mark no longer pulls the chat back to Google: the card you choose is tried, and a resting card shows until when, with Use again now.

### Improved
- **No more drop-down menus.** The model picker, effort (the same slider, with its Fast mode bolt), each key's menu, the add forms and the Disconnect question are pull-up sheets. Claude plans read Pro and Ultra.
