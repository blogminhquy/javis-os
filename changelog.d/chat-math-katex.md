---
bump: minor
title: Chat draws math formulas with KaTeX
---
## vi
### Thêm mới
- **Khung chat vẽ được công thức toán.** Công thức viết dạng `$...$`, `$$...$$`, `\(...\)` hoặc `\[...\]` giờ hiện thành phân số, căn, mũ như trong sách thay vì nguyên mã. Thư viện KaTeX chỉ tải lần đầu có công thức; mất mạng thì vẫn thấy mã gốc. Số tiền kiểu "$5 và $10" không bị nhận nhầm.

## en
### Added
- **Chat draws math formulas.** Formulas written as `$...$`, `$$...$$`, `\(...\)` or `\[...\]` now show as real fractions, roots and powers instead of raw code. KaTeX loads only the first time a formula appears; offline, the source text still shows. Money like "$5 and $10" is left alone.
