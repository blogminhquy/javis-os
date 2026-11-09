---
bump: patch
title: Keep account security files out of git and Docker images
---
## vi
### Bảo mật
- **Các file bảo mật tài khoản không còn lọt vào git hay image Docker.** Dấu vân tay tài khoản, nhật ký bảo mật, danh sách mạng đã đăng nhập và thông tin phiên giờ nằm trong danh sách bỏ qua, nên `git add -A` hay `docker build` trên máy không mang chúng theo nữa.

## en
### Security
- **Account security files stay out of git and Docker images.** The account fingerprint, security log, sign-in networks and session details are now ignored, so `git add -A` or a local `docker build` no longer picks them up.
