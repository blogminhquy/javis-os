---
bump: minor
title: Claude Compatible is back, OpenAI Compatible and Claude Compatible take several keys
---
## vi
### Thêm mới
- **OpenAI Compatible thêm được nhiều key.** Đây là đường API key nâng cao: mỗi key một địa chỉ (NVIDIA Build, Kimi, OpenRouter, LiteLLM...), Javis tự lấy danh sách model của từng cổng, key đang dùng hết lượt thì tự sang key kế. Cổng nào không báo danh sách model thì mở thêm ô gõ tên model.

### Sửa lỗi
- **Thẻ Claude Compatible quay lại.** Bản 0.477.0 đổi tên nó thành "API key nâng cao" nên đường Claude Compatible biến mất. Giờ nó là thẻ riêng như cũ, vẫn thêm được nhiều key, key đã lưu giữ nguyên.

## en
### Added
- **OpenAI Compatible takes several keys.** This is the advanced API key route: each key has its own address (NVIDIA Build, Kimi, OpenRouter, LiteLLM...), Javis reads each gateway's model list, and when the key in use runs out it moves to the next one. A gateway that lists no models opens a box for the model name.

### Fixed
- **The Claude Compatible card is back.** Version 0.477.0 renamed it "Advanced API key", so the Claude Compatible route disappeared. It is its own card again, still with several keys, and saved keys are kept.
