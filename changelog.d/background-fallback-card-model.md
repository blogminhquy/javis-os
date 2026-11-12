---
bump: patch
title: Background fallback runs the model picked on the provider card
---
## vi
### Sửa lỗi
- **Việc nền chạy dự phòng bằng đúng model anh chị chọn trên thẻ.** Trước đây lựa chọn đó bị bỏ qua: khi model việc nền hết lượt và việc rơi sang Claude Code, nó chạy model mặc định của CLI, thường là model tốn hạn mức nhất. Thẻ chưa chọn model thì vẫn chạy như cũ.

## en
### Fixed
- **Background fallback runs the model you picked on the card.** That choice was ignored before: when the background model ran out and the work moved to Claude Code, it ran the CLI's own default model, usually the one that uses the plan up fastest. A card with no model picked runs as before.
