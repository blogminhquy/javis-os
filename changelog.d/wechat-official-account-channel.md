---
bump: minor
title: WeChat Official Account joins the chatbot channels
---
## vi
### Thêm mới
- **Chatbot trả lời được trên WeChat.** Ở Chatbot, Thêm kênh có thêm **WeChat**: bot chuyên trách trả lời người theo dõi WeChat Official Account của bạn, mọi cuộc chat vào chung Hộp thư và bạn tiếp quản được như các kênh khác.
- **Cài đặt gọn.** Form hiện sẵn địa chỉ webhook và Token để dán sang WeChat; bên Javis chỉ cần dán AppID và AppSecret. Bấm Kiểm tra là biết ngay IP nào cần thêm vào whitelist.
- **Cần biết:** WeChat chỉ cho tài khoản đã xác minh (hoặc tài khoản thử nghiệm) trả lời qua API, chỉ trong 48 giờ sau tin cuối của khách, gửi được chữ và ảnh. Hướng dẫn từng bước ở tài liệu 36.

### Bảo mật
- **Tin WeChat giả bị chặn từ cửa.** Javis kiểm chữ ký từng tin, từ chối yêu cầu cũ quá 15 phút, và tài khoản bật Chế độ an toàn thì chỉ nhận tin đã mã hoá.

## en
### Added
- **Chatbots now answer on WeChat.** Chatbot, Add channel has a new **WeChat** entry: a dedicated bot answers the followers of your WeChat Official Account, every chat lands in the shared Inbox and you can take over as on the other channels.
- **Short setup.** The form shows the webhook address and the Token to paste into WeChat; on the Javis side you paste only the AppID and AppSecret. Check tells you right away which IP to add to the whitelist.
- **Good to know:** WeChat lets only a verified account (or the sandbox test account) reply through the API, only within 48 hours of the follower's last message, with text and images. Step-by-step guide in doc 36.

### Security
- **Forged WeChat messages stop at the door.** Javis checks the signature of every message, refuses a request more than 15 minutes old, and an account in Safe mode accepts encrypted messages only.
