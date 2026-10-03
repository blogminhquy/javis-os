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

## Chữ hiện lên màn hình (từ 0.67.0)

Giao diện chạy bằng tiếng Anh với người dùng trình duyệt tiếng Anh, nên chữ MỚI viết cho màn hình
không được là tiếng Việt trần:

- **Dashboard (JS, HTML):** thêm khoá vào CẢ `dashboard/i18n/vi.json` lẫn `en.json`, gọi `t("...")`
  (hoặc hàm rào `tw()` của file). `tests/js/test_i18n.mjs` đỏ khi một file JS có chữ Việt trong mã
  chạy mà không nằm trong danh sách ngoại lệ dữ liệu.
- **Server:** chữ trả về cho màn hình (lỗi, thông báo, nhãn) viết `localefmt.chu("tiếng Việt",
  "English")`. Không có request (Telegram, việc nền) thì nó theo `ui_lang` của máy.
- **KHÔNG dịch:** prompt và mô tả tool gửi cho model, regex nhận câu người dùng gõ hay nói, log,
  nội dung ghi vào brain của người dùng. Lý do ở `docs/dev/them-mot-ngon-ngu.md`.

## Viết CHANGELOG.md

Chủ repo đọc nhật ký cập nhật trên màn hình dọc (2026-08-12), nên viết CHO NGƯỜI ĐỌC TRÊN ĐIỆN
THOẠI, không phải cho lập trình viên đọc diff:

- Nhiều nhất 3 đến 4 gạch đầu dòng mỗi phiên bản, mỗi cái 1 đến 2 câu.
- Nói NGƯỜI DÙNG THẤY GÌ KHÁC, đừng kể tên hàm và đường dẫn file. Chi tiết kỹ thuật để trong
  thân commit và phần mô tả PR.
- Dùng `**` và dấu nháy ngược vừa phải. Trang có render markdown, nhưng một dòng dày đặc ký
  hiệu thì đọc trên màn hẹp rất mệt.
- **Từ 0.68.0 viết HAI bản:** khối tiếng Việt trong `CHANGELOG.md` (bản gốc) và khối tiếng Anh
  cùng số phiên bản trong `CHANGELOG.en.md`, cùng số nhóm `###`. Trang Cập nhật hiện bản tiếng Anh
  cho thiết bị đọc tiếng Anh. `tests/python/test_nhat_ky_song_ngu.py` đỏ khi một phiên bản từ
  0.66.0 trở đi thiếu bản tiếng Anh, nên khối xí chỗ số phiên bản cũng phải có ở cả hai file.

## Ngôn ngữ của commit, PR và code (từ 0.68.0)

Repo mở cho người đóng góp quốc tế, nên phần NGƯỜI NGOÀI ĐỌC viết bằng tiếng Anh:

- **Commit message, tiêu đề và mô tả PR:** tiếng Anh.
- **Module, tên hàm, comment MỚI:** tiếng Anh. Sửa trong một file sẵn có thì theo ngôn ngữ của
  file đó cho nhất quán; không dịch lại phần code không đụng tới. Bảng từ điển định danh tiếng
  Việt cho người nước ngoài ở `docs/dev/GLOSSARY.md`, kiến trúc ở `ARCHITECTURE.md`.
- **Giữ tiếng Việt:** `CHANGELOG.md` (bản gốc, chủ repo đọc), file quy ước này, spec trong
  `docs/dev/`, và prompt gửi cho model (lý do ở `docs/dev/them-mot-ngon-ngu.md`).
- PR từ người ngoài không cần đụng `VERSION`/CHANGELOG: người merge tăng số và viết nhật ký.

## Bản dịch README và hướng dẫn cài nhanh (từ 0.69.0)

- `README.md` và `QUICKSTART.en.md` (tiếng Anh) là bản gốc. Bản tiếng Việt ở `docs/i18n/vi/` và
  `QUICKSTART.md` vẫn sửa tay cùng lúc như trước.
- Các bản khác ở `docs/i18n/<mã>/` (Trung, Tây Ban Nha, Nhật, Hindi, Bồ Đào Nha, Hàn, Nga, Đức,
  Pháp, Indonesia) là bản MÁY DỊCH. Thanh chọn ngôn ngữ sinh từ danh sách `LANGS` trong
  `tools/check_translations.py` bằng lệnh `--bars`, đừng sửa tay từng file. Dòng đầu mỗi file ghi
  file gốc và hash của nó lúc dịch. Sửa README tiếng Anh xong KHÔNG bắt buộc dịch lại ngay:
  workflow **Translations** sẽ cảnh báo bản nào đã cũ. Khi dịch lại, chạy
  `python tools/check_translations.py --stamp <file>` để cập nhật hash.
- Hình động trong README nằm ở `docs/assets/diagrams/*.svg`: chữ trong hình là tiếng Anh, mọi
  bản dịch dùng chung. Chú thích (alt) của hình thì dịch theo từng bản.
- `tests/python/test_machine_translations.py` canh link chết, anchor lệch và dấu gạch dài trong
  các bản dịch, nên dịch lại xong phải chạy test này.
- Giao diện app chỉ giữ tiếng Anh và tiếng Việt. Chủ repo chốt ngày 2026-10-03: thêm thứ tiếng
  cho app khi có người dùng thật cần, không làm trước. Tài liệu hướng dẫn đầy đủ cũng chỉ hai
  thứ tiếng.
