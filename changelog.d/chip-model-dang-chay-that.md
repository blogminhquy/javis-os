---
bump: minor
title: The chat's model chip shows the model really answering during a fallback
---
## vi
### Thêm mới
- **Khung chat bị chuyển model thì khung đó chuyển theo luôn.** Khi model đã chọn hết lượt và Javis chuyển sang thẻ dự phòng, chip đổi sang tên model dự phòng với chấm cam, dấu tick trong bảng chọn, chip Effort, vòng hạn mức gói và lệnh `/model` cũng theo model đang chạy. Kéo thanh Effort lúc đó là chỉnh mức của chính model dự phòng. Rê chuột (hoặc giữ) vào chip để xem model đã chọn, hết lượt tới mấy giờ, và model đang chạy.
- **Một dòng ngắn trong chat khi đổi đường**, ví dụ "Antigravity hết lượt → đang dùng Claude Code". Dòng chỉ hiện ở lượt đầu tiên đổi, không lặp lại mỗi câu. Khi model đã chọn có lượt lại, chat báo một dòng "đã quay về" và chip tự xanh lại.
- **Bảng chọn model có nhãn "Hết lượt" và "Đang chạy"** cạnh tên từng nhà, để biết ngay nhà nào đang nghỉ và nhà nào đang làm thay.

### Cải thiện
- Lựa chọn model của bạn không bị đổi khi dự phòng: Javis tự quay về model đã chọn khi nó hồi lượt, chọn tay một model thì Javis thử model đó ngay. Chip cập nhật tại chỗ, không cần tải lại trang hay khởi động lại.

## en
### Added
- **A chat that falls back switches its model display too.** When the chosen model runs out of quota and Javis moves to a fallback card, the chip switches to the fallback model's name with an amber dot, and the picker's tick, the Effort chip, the plan usage ring and `/model` follow the model running. Moving the Effort slider then sets the fallback model's own level. Hover (or press) the chip to see the chosen model, when its quota returns, and the model running.
- **One short line in the chat when the route changes**, for example "Antigravity is out of quota → using Claude Code". It shows on the first turn that moves, not on every message. Once the chosen model has quota again, the chat says so in one line and the chip turns green again.
- **The model picker tags providers "Out of quota" and "Running"**, so you see at once which one is resting and which one is filling in.

### Improved
- Your model choice never changes during a fallback: Javis goes back to the chosen model when its quota returns, and picking a model by hand tries it right away. The chip updates in place, with no page reload or restart.
