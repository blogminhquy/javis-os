---
bump: patch
title: Facebook and Meta Ads tools no longer hand access tokens to the model
---
## vi
### Bảo mật
- **Công cụ Facebook và Meta Ads không còn đưa token cho AI.** Link "trang sau" và thông báo lỗi của Facebook có kèm token truy cập; nay Javis gỡ token trước khi trả kết quả cho model. Dữ liệu bài viết, bình luận và con trỏ phân trang giữ nguyên.

## en
### Security
- **Facebook and Meta Ads tools no longer hand access tokens to the model.** Facebook's "next page" links and error messages carry the access token; Javis now strips it before the result reaches the model. Posts, comments and paging cursors are unchanged.
