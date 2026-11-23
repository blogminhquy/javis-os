---
bump: patch
title: Windows installer signing can be tested with SignPath test-signing
---
## vi
### Cải thiện
- **Ký số bộ cài Windows chạy thử được với chứng chỉ test của SignPath.** Bản ký thử nằm ở trang lượt chạy để tải về kiểm tra, còn bản phát hành vẫn giữ file chưa ký cho tới khi có chứng chỉ thật.

## en
### Improved
- **Windows installer signing can be tried with SignPath's test certificate.** The test-signed file is kept on the workflow run for checking, and the release keeps the unsigned file until the production certificate arrives.
