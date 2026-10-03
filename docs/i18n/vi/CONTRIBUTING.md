# Đóng góp cho Javis OS

*[English](../../../CONTRIBUTING.md) · **Tiếng Việt***

Cảm ơn bạn đã muốn đóng góp. Từ 0.68.0, bản gốc của hướng dẫn này là bản tiếng Anh ở gốc repo
(để người đóng góp ở mọi nước đọc được); bản tiếng Việt này đi song song và nói cùng một nội dung.

Tham gia là đồng ý theo [Quy tắc ứng xử](../../../CODE_OF_CONDUCT.md). Lỗi bảo mật báo theo
[SECURITY.md](../../../SECURITY.md), không bao giờ qua Issue công khai.

## Góp sức theo cách nào

- **Báo lỗi** hoặc **đề xuất tính năng**: mở [Issue](https://github.com/blogminhquy/javis-os/issues/new/choose) theo mẫu có sẵn.
- **Dịch** giao diện, tài liệu hoặc kho Kết nối sang thứ tiếng của bạn (xem mục [Dịch thuật](#dịch-thuật)).
- **Thêm kết nối** vào kho Kết nối, một **plugin** (tool Python mọi bộ não gọi được) hay một **skill** (bí quyết viết trong file markdown).
- **Sửa code.** Đọc [ARCHITECTURE.md](../../../ARCHITECTURE.md) trước (tiếng Anh). Người nước ngoài dùng [docs/dev/GLOSSARY.md](../../dev/GLOSSARY.md) để đọc tên hàm tiếng Việt.

Thay đổi lớn hơn một bản sửa nhỏ thì mở Issue trước để bàn hướng, tránh code xong mà hướng không
khớp với dự án.

## Dựng môi trường

```bash
git clone https://github.com/<bạn>/javis-os.git && cd javis-os
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m uvicorn main:app --app-dir server --port 7777   # http://localhost:7777
```

Muốn cài trọn gói (kèm các bộ não CLI) thì chạy `install.sh` (Linux/macOS) hoặc `install.ps1`
(Windows). Để thử nghiệm không đụng dữ liệu thật, trỏ `JAVIS_STATE_DIR` và `BRAINS_DIR` vào một
thư mục nháp.

## Chạy test

```bash
python tests/run.py          # chạy hết (Python + JS), khoảng 7 phút
python tests/run.py --py     # chỉ Python
python tests/run.py --js     # chỉ JS (cần node)
python tests/run.py i18n     # chỉ file test có chữ "i18n" trong tên
```

Script tự tìm `.venv`, chạy được từ bất kỳ thư mục nào trong repo. Mỗi test là một script thường
in ra dòng `ok`/`FAIL`; chạy thẳng `python tests/python/test_<tên>.py` để xem chi tiết. CI chạy
đúng bộ test này trên mọi PR.

## Quy trình

1. **Fork** repo, tạo nhánh đặt tên theo việc đang làm (`fix-mobile-zoom`, `add-spanish-ui`).
2. Code rồi tự chạy test. PR chưa chạy test dễ vướng lỗi vặt mà CI mới bắt được.
3. Mở PR nhắm vào `main` của `blogminhquy/javis-os`. Mẫu PR hỏi **vì sao** cần thay đổi, không
   chỉ **cái gì** đã đổi: cái gì thì đọc diff là thấy.
4. CI phải xanh. Người giữ repo tự xem từng PR; PR từ bên ngoài không có merge tự động.

**Số phiên bản và nhật ký:** mỗi lần merge vào `main` là một phiên bản mới (`VERSION` cùng một
mục trong cả [CHANGELOG.md](../../../CHANGELOG.md) tiếng Việt lẫn
[CHANGELOG.en.md](../../../CHANGELOG.en.md) tiếng Anh). Người đóng góp từ bên ngoài không cần
đụng tới ba file này: người giữ repo tăng số và viết nhật ký lúc merge.

## Quy ước code

- **Đúng phạm vi.** Không refactor hay thêm tính năng ngoài việc của PR.
- **Comment giải thích vì sao** (ràng buộc ẩn, cách lách, lỗi từng gặp), không lặp lại cái dòng
  code bên dưới đã nói.
- **Không dùng em dash (U+2014) hay en dash (U+2013)** ở bất cứ đâu: code, tài liệu, chuỗi. Dùng
  gạch nối, dấu phẩy hoặc hai chấm. Hai dấu này làm giọng đọc TTS khựng, và test kiểm chữ Javis hiện lên hay đọc ra.
- **Ngôn ngữ của code:** module, tên hàm và comment MỚI viết bằng tiếng Anh. Sửa một file có sẵn
  thì theo ngôn ngữ của file đó cho nhất quán; không cần dịch phần code mình không sửa.
- **Chữ hiện lên màn hình không viết cứng một thứ tiếng:**
  - Dashboard: thêm khoá vào cả `dashboard/i18n/vi.json` lẫn `dashboard/i18n/en.json` rồi gọi
    `t("khoa.cua.ban")`. `tests/js/test_i18n.mjs` đỏ khi JS có chữ Việt trong mã chạy.
  - Server: viết `localefmt.chu("tiếng Việt", "English")`.
  - Prompt và mô tả tool gửi cho model AI là chuyện khác: giữ nguyên (tiếng Việt). Model đọc tốt
    và vẫn trả lời theo ngôn ngữ người dùng.
- **Commit message và mô tả PR** ưu tiên viết tiếng Anh.

Quy tắc làm việc riêng của người giữ repo (xí chỗ số phiên bản, cách merge, cách viết nhật ký)
nằm ở [docs/quy-uoc-dev.md](../../quy-uoc-dev.md).

## Dịch thuật

Javis vốn đã **trả lời** bằng bất kỳ thứ tiếng nào người dùng viết. Bản dịch thêm vào là giao
diện, tài liệu và giọng đọc bằng thứ tiếng đó. Ba cách góp, từ nhỏ tới lớn:

1. **README.** README và hướng dẫn cài nhanh bằng các thứ tiếng khác (Trung, Tây Ban Nha, Nhật, Hindi, Bồ Đào Nha, Hàn, Nga, Đức, Pháp, Indonesia) trong
   `docs/i18n/<mã>/` là bản máy dịch: người bản xứ sửa lại thì rất quý, chỉ cần giữ dòng đánh dấu
   `translated-from` ở đầu file. Thêm thứ tiếng mới thì dịch [README.md](../../../README.md) và
   [QUICKSTART.en.md](../../../QUICKSTART.en.md) vào `docs/i18n/<mã>/` (ví dụ
   `docs/i18n/fr/README.md`), sửa link tương đối (lùi ba cấp: `../../../`), thêm thứ tiếng vào
   `LANGS` trong `tools/check_translations.py`, rồi chạy `python tools/check_translations.py --bars`
   (viết lại thanh chọn ngôn ngữ và hàng lá cờ ở mọi README và hướng dẫn cài nhanh) và `--stamp <file>` (gắn
   dòng đánh dấu).
2. **Giao diện.** Chép `dashboard/i18n/en.json` thành `dashboard/i18n/<mã>.json` rồi dịch phần
   giá trị, không đụng tới khoá. Dịch dở cũng được: khoá nào chưa dịch sẽ hiện tiếng Anh.
3. **Trọn một ngôn ngữ.** Đăng ký trong `server/lang_registry.py` để giọng đọc, định dạng ngày
   và tiền tệ cũng theo; tuỳ chọn thêm `system/mcp-catalog.<mã>.json` cho kho Kết nối. Từng bước ở
   [sổ tay thêm ngôn ngữ](../../dev/them-mot-ngon-ngu.md).

Bản gốc của README và hướng dẫn cài nhanh là tiếng Anh. Khi bản gốc đổi, workflow
**Translations** liệt kê bản dịch nào đã cũ (chỉ cảnh báo, không bao giờ làm đỏ build); dịch lại
xong thì chạy `python tools/check_translations.py --stamp <file>`. Riêng giao diện app chỉ giữ
tiếng Anh và tiếng Việt, và chỉ thêm thứ tiếng khi có người dùng thật cần.

## Cần hỏi

Hỏi trong Issue, hoặc bình luận ngay trên PR đang làm. Hỏi bằng tiếng Việt hay tiếng Anh đều được.
