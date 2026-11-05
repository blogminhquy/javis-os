---
bump: minor
title: Ship Cloudflare's security-audit skill as a system skill
---
## vi
### Thêm mới
- **Skill hệ thống mới `security-audit`.** Javis giờ có sẵn quy trình rà soát bảo mật của Cloudflare trong mọi brain: hỏi nhanh về bảo mật thì chỉ dùng phần liên quan, còn bảo "audit bảo mật repo này" thì chạy đủ 6 bước (dò kiến trúc, săn lỗi theo vùng, kiểm chứng độc lập từng lỗi, xuất báo cáo kèm cách sửa). Giấy phép MIT, ghi nguồn đầy đủ.

## en
### Added
- **New `security-audit` system skill.** Every brain now ships Cloudflare's security review workflow: a quick security question uses only the relevant part, while "security audit this repo" runs all six phases (architecture recon, hunting by area, independent verification of each finding, a report with fixes). MIT licensed, with attribution.
