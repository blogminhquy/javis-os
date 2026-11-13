---
bump: patch
title: OpenAI Compatible and Claude Compatible always show models to pick
---
## vi
### Sửa lỗi
- **Thẻ OpenAI Compatible và Claude Compatible không còn báo "Chưa lấy được danh sách model" oan.** Javis đọc được danh sách model của nhiều kiểu cổng hơn, và Base URL gõ thiếu `/v1` thì tự tìm đúng địa chỉ. Máy nâng cấp từ bản cũ cũng tự hiện lại model.
- **Tên model bạn tự gõ luôn nằm trong bảng chọn**, kể cả khi cổng có danh sách riêng hoặc tạm thời không trả danh sách.
- **Khi thật sự không có danh sách, bảng chọn nói rõ vì sao** (sai địa chỉ, key bị từ chối, cổng không báo model) và có lối bấm sang trang Models để sửa. Sửa xong mở lại là thấy ngay, không phải chờ vài phút.
- **Key vừa kết nối không còn tự biến mất** nếu đúng lúc đó Javis đang tải danh sách model của một thẻ khác.

## en
### Fixed
- **The OpenAI Compatible and Claude Compatible cards no longer say "Could not load the model list" by mistake.** Javis reads the model list of more kinds of gateways, and a Base URL typed without `/v1` finds the right address on its own. A machine upgraded from an older version gets its models back too.
- **A model name you typed always stays in the picker**, even when the gateway has its own list or stops listing for a while.
- **When there really is no list, the picker says why** (wrong address, refused key, a gateway that lists nothing) with a link to the Models page to fix it. After the fix the list shows on the next open, with no wait of several minutes.
- **A key you just connected no longer disappears** when Javis happened to be loading another card's model list at that moment.
