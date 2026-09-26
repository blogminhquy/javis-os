# Quy ước dev (phiên Claude Code làm việc trên repo này)

File này tách khỏi `CLAUDE.md` ngày 2026-09-22. Lý do: `CLAUDE.md` là system prompt đi vào
MỌI lượt chat của Javis, có trần ngân sách (`tests/python/test_prompt_budget.py`), mà quy ước
dev thì người dùng Javis không bao giờ cần. Để ở đây thì viết bao nhiêu cũng được, không đánh
thuế lên lượt chat nào cả.

## Nhánh, PR và merge

- Vẫn phát triển trên nhánh riêng và mở PR như thường lệ.
- CI xanh rồi thì **merge thẳng vào `main`** (rebase/squash, giữ lịch sử thẳng, repo này không
  dùng merge commit). Chủ repo cho phép từ 2026-07-30 để thay đổi lên VPS thử được ngay, không
  cần hỏi lại mỗi lần. Khác biệt duy nhất so với thường lệ là merge không chờ ai duyệt tay.
- **CI đỏ thì KHÔNG merge.** Sửa cho xanh đã.
- Chủ repo nhắc lại ngày 2026-09-26: **mỗi lần merge vào `main` phải phát hành số phiên bản
  mới**, tăng `VERSION` và cập nhật `CHANGELOG.md` trong cùng PR để các máy khác nhận biết
  có bản cập nhật. Trước khi merge, kiểm tra số này lớn hơn phiên bản hiện tại trên
  `origin/main`; sau khi merge, xác nhận luồng build/phát hành bản cập nhật thành công.
  Không coi việc merge code là đã phát hành xong nếu bản mới chưa được xuất bản.

## Đặt xí chỗ số phiên bản TRƯỚC khi code

Chủ repo yêu cầu 2026-09-22, sau ba lần trùng số liên tiếp: 0.63.3, 0.63.8 và 0.63.10 đều bị
một PR khác merge trước lấy mất. Lần cuối xảy ra khi PR đã xanh hết CI, phải rebase và đánh số
lại từ đầu.

Nguyên nhân gốc: repo này thường có vài phiên Claude Code chạy song song. Số chọn ở cuối việc
là số chọn bằng thông tin đã cũ.

Quy trình:

1. `git fetch origin main`, đọc `VERSION` trên `origin/main`.
2. Liệt kê các PR **đang mở**, đọc số phiên bản trong tiêu đề. Mọi số ở đó coi như **đã có
   người lấy**, dù `main` chưa mang số đó.
3. Lấy số trống kế tiếp sau tất cả.
4. Đẩy commit bump `VERSION` + `CHANGELOG.md` **ngay đầu nhánh**, kèm PR nháp mang số đó trong
   tiêu đề. Đây mới là hành động đặt xí chỗ: phiên sau đọc được ở bước 2. Phần thân changelog
   viết sau cũng được.
5. Xong mới viết code.

Hai tình huống hay gặp:

- **`main` vẫn vượt qua số đã đặt.** Rebase và đánh số lại. Chỉ `VERSION` và `CHANGELOG.md`
  xung đột nên mất đúng một nhịp, không phải làm lại thay đổi.
- **Một PR mở mang số đã cũ** (ví dụ 2026-09-22: PR #417 còn giữ 0.64.1 trong khi #416 đã phát
  hành chính số đó). Số như vậy nói rằng "có người nhắm", không phải "còn hợp lệ". Chính phiên
  của PR đó phải đánh số lại trước khi merge.

Quy ước này giảm va chạm chứ không diệt hết: hai phiên khởi động cách nhau vài giây vẫn có thể
cùng đọc `main` rồi cùng chọn một số. Cái nó tránh là va chạm ở phút cuối, lúc PR đã xanh và
mọi thứ đã xong.

## Viết CHANGELOG.md

Chủ repo đọc nhật ký cập nhật trên màn hình dọc (2026-08-12), nên viết CHO NGƯỜI ĐỌC TRÊN ĐIỆN
THOẠI, không phải cho lập trình viên đọc diff:

- Nhiều nhất 3 đến 4 gạch đầu dòng mỗi phiên bản, mỗi cái 1 đến 2 câu.
- Nói NGƯỜI DÙNG THẤY GÌ KHÁC, đừng kể tên hàm và đường dẫn file. Chi tiết kỹ thuật để trong
  thân commit và phần mô tả PR.
- Dùng `**` và dấu nháy ngược vừa phải. Trang có render markdown, nhưng một dòng dày đặc ký
  hiệu thì đọc trên màn hẹp rất mệt.
