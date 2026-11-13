---
bump: minor
title: The Windows installer says what it changes, and is ready for free code signing
---
## vi
### Thêm mới
- **Bộ cài Windows báo trước mọi thay đổi trên máy.** Trước khi cài có một trang liệt kê những gì sẽ được tải và cài (Javis, Git, Python, Node.js, các công cụ AI), kèm cam kết quyền riêng tư và cách gỡ.
- **Hai lựa chọn mới khi cài.** Có thể bỏ tích "tự chạy khi đăng nhập Windows" và "cài các công cụ AI dòng lệnh". Để nguyên thì bộ cài làm như trước.
- **Có trang chính sách ký số và chính sách quyền riêng tư.** Nói rõ Javis không theo dõi, không gửi số liệu sử dụng, và tự nó chỉ tải file công khai để kiểm tra cập nhật.
- **Sẵn sàng ký số miễn phí qua SignPath Foundation.** Phần ký trong quy trình dựng bộ cài đã nối xong và đang tắt, sẽ bật khi dự án được SignPath chấp nhận. Bộ cài hiện vẫn chưa ký.

## en
### Added
- **The Windows installer announces every change it makes.** A page before the install lists what will be downloaded and installed (Javis, Git, Python, Node.js, the AI tools), with the privacy statement and how to uninstall.
- **Two new choices in the installer.** "Start when I sign in to Windows" and "install the AI command-line tools" can be unticked. Left alone, the installer does what it did before.
- **A code signing policy and a privacy policy.** They state that Javis has no tracking, sends no usage statistics, and on its own only downloads public files to check for updates.
- **Ready for free code signing through SignPath Foundation.** The signing step in the installer build is wired and switched off; it turns on once SignPath accepts the project. The installer is still unsigned today.
