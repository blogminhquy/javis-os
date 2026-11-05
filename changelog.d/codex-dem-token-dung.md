---
bump: patch
title: Codex counts tokens once per request, and large tool results can be trimmed
---
## vi
### Sửa lỗi
- **Codex không còn đếm trùng token.** Codex có lúc báo số dùng lặp lại cho cùng một request, Javis từng cộng cả lần lặp nên số token của lượt bị thổi lên. Nay chỉ tính phần tăng thật. Ý tưởng và bản đầu của kubintran (#999).
- **Xoay mạch Codex nhìn đúng độ dài mạch.** Trước đây Javis lấy tổng token của cả lượt, nên một lượt chạy nhiều vòng tool trông như mạch rất dài. Nay lấy input của request cuối mà Codex đo được; không đo được thì dùng số cũ như trước. Xoay mạch vẫn bật như cũ.

### Cải thiện
- **Kết quả JSON lớn từ `javis_run_tool` lấy được từng phần.** Model chỉ định đường dẫn, trường và trang cần lấy, đỡ tốn ngữ cảnh. Tool vẫn chạy đúng một lần qua gateway; có lỗi hay dữ liệu lạ thì trả nguyên kết quả gốc.

## en
### Fixed
- **Codex no longer double counts tokens.** Codex sometimes repeats its usage report for the same request, and Javis added every repeat, inflating the turn's tokens. Only the real increase counts now. Idea and first version by kubintran (#999).
- **Codex thread rotation sees the real thread size.** Javis used the whole turn total, so a turn with many tool rounds looked like a huge thread. It now uses the input of the last request as Codex measured it, falling back to the old number when there is no measurement. Rotation stays on as before.

### Improved
- **Large JSON results from `javis_run_tool` can be fetched in parts.** The model names the pointer, fields and page it needs, saving context. The tool still runs exactly once through the gateway; on any error or unknown shape the original result is returned.
