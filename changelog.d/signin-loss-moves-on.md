---
bump: patch
title: A model that lost its sign-in hands the turn to the next connected model
---
## vi
### Sửa lỗi
- **ChatGPT (hay Claude, Grok) mất đăng nhập thì Javis tự chuyển sang model khác đã kết nối.** Trước đây chỉ khi hết lượt mới chuyển, còn mất đăng nhập thì lượt nào cũng báo lỗi cho tới khi anh đăng nhập lại.
- **Áp dụng cho cả bot trả lời khách và trợ lý có model riêng.** Bot hay trợ lý đặt model ChatGPT sẽ trả lời bằng model chính trong lúc ChatGPT chưa đăng nhập lại, khách không còn gặp lượt hỏng.
- **Có báo rõ để anh biết.** Khung chat hiện dòng "Đang dùng ... vì ChatGPT mất đăng nhập", ô chọn model gắn nhãn "Mất đăng nhập", và chuông có một thông báo nhắc đăng nhập lại ở trang Models. Đăng nhập xong là dùng lại model cũ ngay.

## en
### Fixed
- **When ChatGPT (or Claude, Grok) loses its sign-in, Javis moves to another connected model by itself.** Before, only running out of quota moved a turn on; a lost sign-in failed every turn until you signed in again.
- **Customer bots and assistants with their own model are covered too.** A bot or an assistant set to ChatGPT answers on the main model while ChatGPT is signed out, so customers no longer hit failed turns.
- **You are told clearly.** The chat shows "Using ... because ChatGPT lost its sign-in", the model picker tags the card "Signed out", and the bell gets one reminder to sign in again on the Models page. After signing in, the old model is used again at once.
