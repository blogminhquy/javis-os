---
bump: minor
title: Store packs can add inbox channels
---
## vi
### Thêm mới
- **Gói Store thêm được kênh hộp thư.** Gói khai `provides.channels: [channels/<tên>.py]` là có kênh mới ở trang Chatbot và Hội thoại, không phải sửa mã lõi. Kênh chỉ nạp khi gói đang bật và mã còn khớp lúc anh đồng ý cài; gói đổi mã thì phải đồng ý lại. Gói không bao giờ thay được kênh có sẵn, và một kênh lỗi chỉ mất riêng kênh đó.
- **Màn cài gói nói rõ kênh được làm gì.** Trước khi đồng ý, anh thấy gói sẽ thêm kênh vào Hộp thư, nhận tin khách và trả lời dưới tên shop, mở webhook công khai và chạy mã trên máy chủ.

## en
### Added
- **Store packs can add inbox channels.** A pack listing `provides.channels: [channels/<name>.py]` adds a channel to the Chatbot and Conversations pages without core edits. It loads only while the pack is enabled and its code still matches what the owner agreed to; changed code needs consent again. A pack can never replace a built-in channel, and a broken one only loses itself.
- **The install screen says what a channel may do.** Before agreeing, the owner sees that the pack adds an inbox channel, receives customer messages and replies under the shop's name, opens a public webhook, and runs code on the server.
