# changelog.d

Mỗi PR thêm **đúng một file** ở đây thay vì sửa `VERSION` và đầu `CHANGELOG.md`. Sau khi PR merge
vào `main`, workflow **Release** (`.github/workflows/release.yml`) tự đánh số, chép nội dung vào
`CHANGELOG.md` + `CHANGELOG.en.md`, xoá file này và phát hành image. Tên file mỗi PR một khác nên
các PR chạy song song không bao giờ xung đột vì số phiên bản.

Tên file: chữ thường, số và gạch nối, ví dụ `zalo-gui-anh-loi.md`. Mẫu:

```
---
bump: patch
title: Zalo images no longer fail on large files
---
## vi
### Sửa lỗi
- **Gửi ảnh Zalo lớn không còn lỗi.** Câu ngắn nói người dùng thấy gì khác.

## en
### Fixed
- **Large Zalo images send again.** The same content in English.
```

- `bump: patch` khi chỉ sửa lỗi, `bump: minor` khi có gì mới.
- `title`: tiếng Anh, không kèm số phiên bản hay `(#PR)`. Bot dùng nó làm tiêu đề commit phát hành.
- Nhóm tiếng Việt: `Thêm mới`, `Sửa lỗi`, `Cải thiện`, `Bảo mật`. Tiếng Anh tương ứng: `Added`,
  `Fixed`, `Improved`, `Security`, cùng thứ tự.
- Kiểm tra trên máy: `python tools/release.py check`.

Quy tắc đầy đủ ở `docs/quy-uoc-dev.md`.
