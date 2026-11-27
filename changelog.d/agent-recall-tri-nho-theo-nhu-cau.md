---
bump: minor
title: Assistants load their memory by search instead of whole, so it scales
---
## vi
### Thêm mới
- **Trí nhớ cộng sự tìm theo nhu cầu.** Cộng sự có bộ nhớ lớn không còn nạp nguyên file vào mỗi lượt. Luôn nạp: phần mở đầu, mục "Luật chủ dặn", mục tên bắt đầu bằng "Luật" hay "Quy tắc", mục tên kết thúc bằng "(luôn nạp)", kèm một bản đồ những gì có trong trí nhớ. Phần còn lại và tài liệu đính kèm được tìm theo từng tin nhắn (chat riêng mọi engine, Telegram, CLI, bước quy trình, lượt nhóm), và trợ lý tự tra thêm bằng công cụ mới `javis_recall`. Trí nhớ 3 MB vẫn chỉ tốn khoảng 1.500 ký tự trong prompt, mỗi lần tìm dưới 40 mili giây. Bộ nhớ dưới 12.000 ký tự chạy y như cũ.
- **Học lúc ghi.** Mỗi đoạn trí nhớ mới được model nền rẻ đọc ngầm một lần, ghi thêm câu hỏi nó trả lời và các cách gọi khác, nên hỏi bằng từ khác vẫn tìm ra. Có trần số lượt mỗi ngày, tắt được bằng `agent_recall.enrich: false`.
- **Tab "Đã học" của cộng sự** hiện trí nhớ đang được tìm theo nhu cầu, và cảnh báo khi luật luôn nạp đã quá dài cần gộp lại.

### Cải thiện
- **Chỉ mục trí nhớ của Javis cập nhật tăng dần.** Thêm hay sửa một ghi nhớ chỉ đọc lại đúng file đó thay vì dựng lại toàn bộ (5.000 ghi nhớ: từ 2,8 giây xuống 0,3 giây), và gõ không dấu cũng tìm ra chữ có "đ".

## en
### Added
- **Assistant memory is searched as needed.** An assistant with a large memory no longer loads the whole file on every turn. Always loaded: the opening text, the owner rules section, sections named as rules, and sections ending with "(always)", plus a map of what the memory holds. The rest and the attached documents are searched for each message (private chat on every engine, Telegram, CLI, workflow steps, team turns), and the assistant looks up more with the new `javis_recall` tool. A 3 MB memory still costs about 1,500 characters of prompt and a search takes under 40 ms. A memory under 12,000 characters works exactly as before.
- **Learning at write time.** Each new memory passage is read once in the background by a cheap model, which adds the questions it answers and other words for its subject, so a question in different words still finds it. Capped per day, switched off with `agent_recall.enrich: false`.
- **The assistant's Learned tab** shows that its memory is searched as needed, and warns when the always-loaded rules have grown too long and should be merged.

### Improved
- **Javis's memory index updates incrementally.** Adding or editing one memory reads only that file instead of rebuilding everything (5,000 memories: from 2.8 s to 0.3 s), and a query typed without diacritics now also matches the Vietnamese letter d with a stroke.
