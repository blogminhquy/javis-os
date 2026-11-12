---
bump: patch
title: Hooks and git config planted in a repo can no longer read the GitHub token
---
## vi
### Bảo mật
- **Hook và cấu hình git trong repo không còn đọc được token GitHub.** Trước đây một hook nằm trong bản clone (ví dụ do `npm install` kiểu husky cài, hoặc do model tạo) chạy đúng lúc Javis tải về hay đẩy code và thấy được token. Giờ các lệnh git có mang token của Javis bỏ qua mọi hook của repo.
- **Token chỉ đi tới đúng repo trên GitHub.** Nếu cấu hình git của bản clone bị sửa để lái kết nối sang nơi khác (đổi `origin`, `insteadOf`, proxy), Javis dừng lại và nói rõ dòng nào cần gỡ, thay vì gửi token đi.
- **Thay đổi cần biết:** hook `pre-push` của repo không còn chạy khi Javis đẩy code (bộ kiểm tra của Javis và CI vẫn chạy như cũ). Repo dùng Git LFS: file LFS mới tạo trong chat chưa được tải lên theo lần đẩy.

## en
### Security
- **Hooks and git config inside a repo can no longer read the GitHub token.** A hook sitting in the clone (installed husky-style by `npm install`, or written by the model) used to run while Javis fetched or pushed, and could see the token. Javis's git calls that carry the token now ignore every hook of the repo.
- **The token only goes to the repo on GitHub.** If the clone's git config was changed to steer the connection elsewhere (a different `origin`, `insteadOf`, a proxy), Javis stops and names the setting to remove instead of sending the token.
- **Worth knowing:** a repo's `pre-push` hook no longer runs when Javis pushes (Javis's own checks and CI run as before). Repos using Git LFS: new LFS files made in a chat are not uploaded by the push yet.
