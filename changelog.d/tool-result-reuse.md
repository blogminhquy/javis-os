---
bump: minor
title: Leaner tool results in long turns, plus token and quality meters
---
## vi
### Cải thiện
- **Lượt dài tốn ít token hơn, với mọi bộ não.** Model gọi lại đúng công cụ với đúng tham số mà kết quả y hệt lần trước thì nhận một dòng tham chiếu thay vì cả khối chữ lần nữa. Công cụ vẫn chạy lại thật, nên dữ liệu đổi là model nhận bản mới đầy đủ. Với Claude Code và Codex, việc này làm ở cổng hub, và Javis quên sổ của lượt đó mỗi khi chúng nén hội thoại.
- **JSON gọn hơn.** Kết quả JSON thụt lề hay có chữ Việt bị mã hoá được viết gọn lại, cùng nội dung. Tệp, terminal, trang web và skill thì giữ nguyên từng ký tự.
- Chọn mức **Tắt** trên trang Mức dùng là tắt luôn hai cách tiết kiệm này. Số ký tự bớt được hiện chung ở dòng kết quả tool trên trang đó.

### Thêm mới
- **Bộ đo trước và sau** cho người phát triển: `tools/token_bench.py` đo số ký tự mỗi lượt gửi cho model, `tools/quality_eval.py` chạy một bộ câu hỏi qua Javis thật rồi so độ đủ ý của câu trả lời giữa hai lần chạy.

## en
### Improved
- **Long turns cost fewer tokens, on every brain.** When the model calls the same tool with the same arguments and the result is identical, it gets a one-line reference instead of the whole text again. The tool still runs every time, so changed data always reaches the model in full. For Claude Code and Codex this happens at the hub, and Javis forgets the turn's record whenever they compact their conversation.
- **Leaner JSON.** Indented or escaped JSON results are written compactly with the same content. Files, terminal output, web pages and skills stay exactly as they are.
- Choosing **Off** on the Usage page turns both savings off. What they save shows in the tool results line of that page.

### Added
- **Before-and-after meters** for developers: `tools/token_bench.py` measures the characters a turn sends to the model, and `tools/quality_eval.py` runs a set of questions through a real Javis and compares how complete the answers are between two runs.
