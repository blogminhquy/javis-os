---
bump: patch
title: Read aloud no longer speaks English sentences in Vinglish
---
## vi
### Sửa lỗi
- **Đọc thành tiếng không còn "Vinglish".** Câu tiếng Anh nằm trong câu trả lời tiếng Việt, hay câu trả lời tiếng Anh có nhắc một tên tiếng Việt, giờ được đọc đúng giọng Anh thay vì bị phiên âm kiểu "The quých bờ rao phóc".
- Từ tiếng Anh lẻ trong câu tiếng Việt ("GitHub Actions", "deploy") vẫn đọc theo kiểu người Việt nói như trước. Giọng chỉ nói tiếng Việt (Hoài My, Nam Minh) vẫn phiên âm hết, nên muốn nghe tiếng Anh chuẩn thì chọn Emma hoặc "Tự động theo thứ tiếng".
- Với giọng "Tự động theo thứ tiếng", câu tiếng Anh giữa đoạn tiếng Việt giờ chuyển sang giọng Emma, không còn bị Hoài My đọc.

## en
### Fixed
- **Read aloud no longer speaks English in "Vinglish".** An English sentence inside a Vietnamese answer, or an English answer that mentions a Vietnamese name, is now read as English instead of being respelled Vietnamese-style.
- Single English terms inside Vietnamese ("GitHub Actions", "deploy") are still read the way Vietnamese speakers say them. Vietnamese-only voices (Hoai My, Nam Minh) still respell everything, so pick Emma or "Auto by language" to hear proper English.
- With the "Auto by language" voice, an English sentence in the middle of Vietnamese text now switches to Emma instead of being read by Hoai My.
